"""Descriptive ownership/price research with an explicit formal-data gate."""
from __future__ import annotations

import bisect
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from modules.core.project_paths import db_path
from modules.ownership_research.data import DB_PATH
from modules.ownership_research.factors import FactorConfig, load_factors

YAHOO_DB = db_path("price_cache.db")


@dataclass(frozen=True)
class StudyConfig:
    start: date
    end: date
    factor: str = "delta_1w_gt_1000"
    horizons: tuple[int, ...] = (5, 10, 20, 40, 60)
    delay_days: tuple[int, ...] = (3, 7, 14)
    lead_lag_sessions: tuple[int, ...] = (0, 5, 10)
    event_min: float = 0.01
    quantiles: int = 5
    max_entry_delay_sessions: int = 2
    price_source: str = "yahoo_cache"  # descriptive only; adjustment convention unverified
    mode: str = "exploratory"
    nonoverlap: bool = True

    def __post_init__(self) -> None:
        if (self.end < self.start or not self.horizons or any(h < 1 for h in self.horizons)
                or not self.delay_days or any(d < 0 for d in self.delay_days)
                or not self.lead_lag_sessions or any(x < 0 for x in self.lead_lag_sessions)
                or self.quantiles < 2 or self.max_entry_delay_sessions < 0
                or self.price_source not in {"yahoo_cache", "official_raw"}
                or self.mode not in {"exploratory", "formal"}):
            raise ValueError("Invalid study window, horizon, delay, source, or mode")


def load_prices(config: StudyConfig, *, research_path: Path = DB_PATH,
                yahoo_path: Path = YAHOO_DB) -> pd.DataFrame:
    start = config.start.isoformat()
    end = (config.end + timedelta(days=(max(config.horizons) + max(config.lead_lag_sessions) + 15) * 2)).isoformat()
    if config.price_source == "official_raw":
        with sqlite3.connect(research_path) as conn:
            result = pd.read_sql_query("""SELECT market,stock_id,trade_date,open,high,low,close,
                volume_shares AS volume,adjusted_close,adjustment_status FROM research_price_daily
                WHERE trade_date BETWEEN ? AND ? ORDER BY market,stock_id,trade_date""", conn, params=(start, end))
    else:
        with sqlite3.connect(yahoo_path) as conn:
            result = pd.read_sql_query("""SELECT symbol,trade_date,open,high,low,close,volume
                FROM price_history WHERE trade_date BETWEEN ? AND ? AND volume>0
                AND (symbol LIKE '____.TW' OR symbol LIKE '____.TWO')
                ORDER BY symbol,trade_date""", conn, params=(start, end))
        if not result.empty:
            result["market"] = np.where(result["symbol"].str.endswith(".TWO"), "TPEx", "TWSE")
            result["stock_id"] = result["symbol"].str[:4]
            result = result.loc[result["stock_id"].str.fullmatch(r"\d{4}")].drop(columns="symbol")
            result["adjusted_close"] = np.nan
            result["adjustment_status"] = "yfinance_cache_unverified"
    if result.empty:
        return result
    for field in ("open", "high", "low", "close", "volume"):
        result[field] = pd.to_numeric(result[field], errors="coerce")
    return result.loc[(result[["open", "high", "low", "close"]] > 0).all(axis=1)
                      & result["volume"].gt(0)].copy()


def formal_readiness(*, config: StudyConfig, factors: pd.DataFrame,
                     prices: pd.DataFrame, research_path: Path = DB_PATH) -> list[str]:
    """Never produce a formal outcome from assumed publication or unverified prices."""
    reasons: list[str] = []
    if config.price_source != "official_raw":
        reasons.append("Formal mode requires official price rows")
    if factors.empty or not factors["publication_status"].eq("verified").all() or factors["published_at"].isna().any():
        reasons.append("Ownership publication timestamps are not independently verified")
    if prices.empty or not prices["adjustment_status"].eq("verified_total_return").all() or prices["adjusted_close"].isna().any():
        reasons.append("Corporate-action-adjusted total-return prices are not verified")
    reasons.append("Verified adjusted open and close execution prices are not yet implemented")
    with sqlite3.connect(research_path) as conn:
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_security_lifecycle'").fetchone()
        verified = conn.execute("SELECT COUNT(*) FROM research_security_lifecycle WHERE validation_status='verified_history'").fetchone()[0] if table else 0
    if (not verified or factors.empty or "validation_status" not in factors
            or not factors["validation_status"].eq("verified_history").all()
            or factors["listed_at"].isna().any()):
        reasons.append("Historical ordinary-share listing and delisting status is not verified")
    return reasons


def restrict_to_company_lifecycle(factors: pd.DataFrame, *, research_path: Path) -> pd.DataFrame:
    """Exclude ETFs and post-listing/pre-delisting impossibilities using official company evidence."""
    if factors.empty:
        return factors
    with sqlite3.connect(research_path) as conn:
        table = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_security_lifecycle'").fetchone()
        lifecycle = pd.read_sql_query("""SELECT market,stock_id,listed_at,delisted_at,validation_status
            FROM research_security_lifecycle WHERE security_type='ordinary_company_candidate'
            AND validation_status<>'code_reuse_conflict'""", conn) if table else pd.DataFrame()
    if lifecycle.empty:
        return factors.iloc[0:0].copy()
    joined = factors.merge(lifecycle, on="stock_id", how="inner", validate="many_to_many")
    joined = joined.loc[(joined["listed_at"].isna() | joined["listed_at"].le(joined["report_date"]))
                        & (joined["delisted_at"].isna() | joined["report_date"].lt(joined["delisted_at"]))]
    unambiguous = joined.groupby(["stock_id", "report_date"])["market"].transform("nunique").eq(1)
    return joined.loc[unambiguous].drop_duplicates(["stock_id", "report_date"]).reset_index(drop=True)


def build_event_rows(factors: pd.DataFrame, prices: pd.DataFrame, config: StudyConfig,
                     delay_days: int) -> pd.DataFrame:
    """Enter at a later trading session's open; exit on the exact market-session horizon."""
    if factors.empty or prices.empty:
        return pd.DataFrame()
    price_groups: dict[tuple[str, str], dict[str, tuple[float, float, float, str]]] = {}
    by_stock: dict[str, list[tuple[str, str]]] = {}
    calendars: dict[str, list[str]] = {}
    for market, group in prices.groupby("market", sort=False):
        calendars[market] = sorted(group["trade_date"].unique().tolist())
    for (market, code), group in prices.groupby(["market", "stock_id"], sort=False):
        key = (str(market), str(code))
        price_groups[key] = {str(row.trade_date): (float(row.open), float(row.low), float(row.close), str(row.adjustment_status))
                             for row in group.itertuples(index=False)}
        by_stock.setdefault(str(code), []).append(key)
    rows = []
    for factor_row in factors.itertuples(index=False):
        value = getattr(factor_row, config.factor)
        if pd.isna(value):
            continue
        code = str(factor_row.stock_id)
        keys = by_stock.get(code, [])
        if hasattr(factor_row, "market"):
            keys = [key for key in keys if key[0] == factor_row.market]
        if len(keys) != 1:  # absent or traded on two boards: do not guess the historical market
            continue
        market, _ = keys[0]
        calendar = calendars[market]
        quote = price_groups[keys[0]]
        verified_time = factor_row.publication_status == "verified" and pd.notna(factor_row.published_at)
        available = (date.fromisoformat(str(factor_row.published_at)[:10]) if verified_time
                     else date.fromisoformat(str(factor_row.report_date)) + timedelta(days=delay_days))
        first = bisect.bisect_right(calendar, available.isoformat())
        entry = next((j for j in range(first, min(first + config.max_entry_delay_sessions + 1, len(calendar)))
                      if calendar[j] in quote), None)
        if entry is None:
            continue
        for lag in config.lead_lag_sessions:
            start_idx = entry + lag
            if start_idx >= len(calendar) or calendar[start_idx] not in quote:
                continue
            enter_day = calendar[start_idx]
            enter_open = quote[enter_day][0]
            for horizon in config.horizons:
                exit_idx = start_idx + horizon
                if exit_idx >= len(calendar):
                    continue
                path = [quote.get(calendar[i]) for i in range(start_idx, exit_idx + 1)]
                if any(item is None for item in path):
                    continue  # suspended/missing session is missing, never zero or shifted exit
                if config.mode == "formal" and any(item[3] != "verified_total_return" for item in path):
                    continue
                rows.append({
                    "stock_id": code, "market": market, "report_date": str(factor_row.report_date),
                    "source_url": str(factor_row.source_url), "publication_status": str(factor_row.publication_status),
                    "availability_basis": "verified_published_at" if verified_time else f"assumed_report_plus_{delay_days}_calendar_days",
                    "assumed_available_date": available.isoformat(), "entry_date": enter_day,
                    "exit_date": calendar[exit_idx], "entry_session_index": start_idx,
                    "exit_session_index": exit_idx, "horizon": horizon, "lead_lag_sessions": lag,
                    "factor_value": float(value), "price_change_pct": (path[-1][2] / enter_open - 1) * 100,
                    "max_adverse_pct": (min(item[1] for item in path) / enter_open - 1) * 100,
                })
    return pd.DataFrame(rows)


def _nonoverlapping(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty:
        return events
    events = events.sort_values(["horizon", "lead_lag_sessions", "stock_id", "entry_date", "report_date"])
    keep = []
    last_exit: dict[tuple[int, int, str], int] = {}
    for row in events.itertuples():
        key = (row.horizon, row.lead_lag_sessions, row.stock_id)
        if row.entry_session_index > last_exit.get(key, -1):
            keep.append(row.Index)
            last_exit[key] = row.exit_session_index
    return events.loc[keep].reset_index(drop=True)


def summarize_events(events: pd.DataFrame, config: StudyConfig) -> dict[str, object]:
    correlation = []
    groups = []
    event_study = []
    for lag in config.lead_lag_sessions:
        for horizon in config.horizons:
            raw_view = events.loc[(events["lead_lag_sessions"] == lag) & (events["horizon"] == horizon)] if not events.empty else pd.DataFrame()
            view = _nonoverlapping(raw_view) if config.nonoverlap else raw_view
            n = len(view)
            pearson = float(view["factor_value"].corr(view["price_change_pct"], method="pearson")) if n >= 3 else np.nan
            spearman = float(view["factor_value"].corr(view["price_change_pct"], method="spearman")) if n >= 3 else np.nan
            correlation.append({"lead_lag_sessions": lag, "horizon": horizon, "n": n,
                                "stock_count": int(view["stock_id"].nunique()) if n else 0,
                                "pearson": _finite(pearson), "spearman": _finite(spearman)})
            if lag != 0:
                continue
            if n:
                try:
                    bins = pd.qcut(view["factor_value"], config.quantiles, duplicates="drop")
                    quantile_frame = view.assign(quantile=bins)
                    for idx, (_, section) in enumerate(quantile_frame.groupby("quantile", observed=True), start=1):
                        groups.append({"horizon": horizon, "group": idx, "n": len(section),
                                       "stock_count": int(section["stock_id"].nunique()),
                                       "factor_min": float(section["factor_value"].min()),
                                       "factor_max": float(section["factor_value"].max()),
                                       "mean_price_change_pct": float(section["price_change_pct"].mean()),
                                       "median_price_change_pct": float(section["price_change_pct"].median()),
                                       "up_fraction": float(section["price_change_pct"].gt(0).mean())})
                except ValueError:  # all values identical: no honest quantile boundary
                    pass
            selected = raw_view.loc[raw_view["factor_value"].ge(config.event_min)] if n else raw_view
            if config.nonoverlap:
                selected = _nonoverlapping(selected)
            event_study.append({"horizon": horizon, "threshold": config.event_min, "n": len(selected),
                                "stock_count": int(selected["stock_id"].nunique()) if len(selected) else 0,
                                "mean_price_change_pct": _finite(selected["price_change_pct"].mean()),
                                "median_price_change_pct": _finite(selected["price_change_pct"].median()),
                                "up_fraction": _finite(selected["price_change_pct"].gt(0).mean()) if len(selected) else None,
                                "mean_max_adverse_pct": _finite(selected["max_adverse_pct"].mean())})
    return {"correlations_and_lead_lag": correlation, "quantile_price_changes": groups,
            "event_study": event_study}


def _finite(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def run_study(config: StudyConfig, *, factor_config: FactorConfig = FactorConfig(),
              chip_path: Path | None = None, research_path: Path = DB_PATH,
              yahoo_path: Path = YAHOO_DB) -> dict[str, object]:
    factor_options = {"config": factor_config, "research_path": research_path}
    if chip_path is not None:
        factor_options["chip_path"] = chip_path
    factors = load_factors(config.start, config.end, **factor_options)
    raw_factor_rows = len(factors)
    factors = restrict_to_company_lifecycle(factors, research_path=research_path)
    if config.factor not in factors.columns and not factors.empty:
        raise ValueError(f"Unknown factor {config.factor}")
    prices = load_prices(config, research_path=research_path, yahoo_path=yahoo_path)
    if config.mode == "formal":
        reasons = formal_readiness(config=config, factors=factors, prices=prices, research_path=research_path)
        if reasons:
            return {"mode": "formal", "status": "blocked", "reasons": reasons,
                    "raw_factor_rows": raw_factor_rows, "factor_rows": len(factors),
                    "price_rows": len(prices), "event_count": 0}
    if factors.empty or prices.empty:
        return {"mode": config.mode, "status": "no_overlap", "event_count": 0,
                "raw_factor_rows": raw_factor_rows, "factor_rows": len(factors), "price_rows": len(prices),
                "reason": "No verified company-universe overlap or priced factor observations"}
    effective = factors[config.factor].notna()
    result: dict[str, object] = {
        "mode": config.mode, "status": "descriptive_only" if config.mode == "exploratory" else "formal",
        "factor": config.factor, "raw_factor_rows": raw_factor_rows,
        "factor_rows": len(factors), "effective_factor_rows": int(effective.sum()),
        "factor_valid_counts": {name: int(factors[name].notna().sum()) for name in factors.columns
                                if name.startswith(("pct_gt_", "delta_", "speed_", "acceleration_", "consecutive_", "large_minus_small"))},
        "factor_report_period": [str(factors["report_date"].min()), str(factors["report_date"].max())],
        "ownership_source_status_counts": {key: int(value) for key, value in factors["publication_status"].value_counts().items()},
        "price_period": [str(prices["trade_date"].min()), str(prices["trade_date"].max())],
        "price_source": config.price_source, "price_adjustment": "unverified; price change, not total return",
        "entry_rule": "first traded market session strictly after assumed/verified availability, open price",
        "exit_rule": "close on exact Nth subsequent market session; complete traded path required",
        "nonoverlap_per_stock_horizon": config.nonoverlap,
        "universe_status": "official current-company and delisting registers; historical completeness unverified",
        "limitations": ["Unknown historical TDCC publication times use explicit assumed delays",
                        "Yahoo cache adjustment convention and historical-stock coverage are unverified" if config.price_source == "yahoo_cache" else "Official raw prices omit corporate-action adjustment",
                        "Cross-sectional and regime dependence remain; correlations are descriptive, not causal or significant trading claims"],
        "sensitivity": [],
    }
    for delay in config.delay_days:
        events = build_event_rows(factors, prices, config, delay)
        summary = summarize_events(events, config)
        result["sensitivity"].append({"assumed_delay_calendar_days": delay, "event_rows": len(events), **summary})
    return result
