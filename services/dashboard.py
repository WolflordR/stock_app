"""Small, date-stamped read model for the home market dashboard."""
from __future__ import annotations

import sqlite3
from math import isfinite
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any

from modules.core.project_paths import db_path
from modules.data_sources.market_turnover import market_turnover_ratios
from services.events.company_events import list_events

PRICE_DB = db_path("price_cache.db")
ROTATION_DB = db_path("sector_rotation.db")
STOCK_DB = db_path("stocks.db")
WATCH_DB = db_path("watchlists.db")
SIGNAL_DB = db_path("dashboard_signals.db")
CHIP_DB = db_path("chip_trends.db")
REVENUE_DB = db_path("revenue_cache.db")
MIN_SIGNAL_VOLUME_SHARES = 1_000_000
MIN_SIGNAL_ESTIMATED_TURNOVER_TWD = 200_000_000


def _db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _pct(current: float, prior: float) -> float | None:
    return round((current / prior - 1) * 100, 2) if prior else None


def _price_snapshot() -> tuple[str | None, dict[str, dict[str, Any]], dict[str, Any]]:
    if not PRICE_DB.exists():
        return None, {}, {}
    with _db(PRICE_DB) as conn:
        anchor = conn.execute("SELECT MAX(last_trade_date) FROM price_cache_meta WHERE last_trade_date<=?", (date.today().isoformat(),)).fetchone()[0]
        if not anchor:
            return None, {}, {}
        cutoff = (date.fromisoformat(anchor) - timedelta(days=115)).isoformat()
        # One indexed date-range read; grouping and rolling features stay in memory.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_trade_date ON price_history(trade_date,symbol)")
        rows = conn.execute("SELECT symbol,trade_date,high,low,close,volume FROM price_history WHERE trade_date BETWEEN ? AND ? ORDER BY symbol,trade_date", (cutoff, anchor))
        histories: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            histories[row["symbol"]].append(row)
    stocks: dict[str, dict[str, Any]] = {}
    counters = {"up": 0, "down": 0, "flat": 0, "ma20": 0, "ma60": 0, "high20": 0, "low20": 0, "observed": 0, "ma20_observed": 0, "ma60_observed": 0, "turnover_estimate": 0.0}
    for symbol, history in histories.items():
        if not (symbol.endswith(".TW") or symbol.endswith(".TWO")) or len(history) < 2 or history[-1]["trade_date"] != anchor:
            continue
        latest, prior = history[-1], history[-2]
        close = latest["close"]
        if not close or not prior["close"]:
            continue
        change = _pct(close, prior["close"])
        stock_id = symbol.split(".")[0]
        stocks[stock_id] = {"price": round(close, 2), "change_pct": change, "volume": latest["volume"], "symbol": symbol, "trade_date": anchor}
        counters["observed"] += 1
        counters["up" if close > prior["close"] else "down" if close < prior["close"] else "flat"] += 1
        counters["turnover_estimate"] += close * (latest["volume"] or 0)
        for period in (20, 60):
            if len(history) >= period and all(row["close"] for row in history[-period:]):
                counters[f"ma{period}_observed"] += 1
                counters[f"ma{period}"] += close > mean(row["close"] for row in history[-period:])
        if len(history) >= 21:
            prior20 = history[-21:-1]
            counters["high20"] += close > max(row["high"] or 0 for row in prior20)
            counters["low20"] += close < min(row["low"] or float("inf") for row in prior20)
    breadth = {
        "date": anchor, "observed": counters["observed"],
        "advancing": counters["up"], "declining": counters["down"], "unchanged": counters["flat"],
        "advance_pct": round(counters["up"] / counters["observed"] * 100, 1) if counters["observed"] else None,
        "above_ma20_pct": round(counters["ma20"] / counters["ma20_observed"] * 100, 1) if counters["ma20_observed"] else None,
        "above_ma60_pct": round(counters["ma60"] / counters["ma60_observed"] * 100, 1) if counters["ma60_observed"] else None,
        "new_high20": counters["high20"], "new_low20": counters["low20"],
        "turnover_estimate": round(counters["turnover_estimate"]),
        "coverage_note": "股價快取有當日資料的上市櫃股票；成交額為股價 × 股數估算，並非交易所公布總額",
    }
    return anchor, stocks, breadth


def _benchmarks() -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not ROTATION_DB.exists():
        return result
    with _db(ROTATION_DB) as conn:
        for market, label in (("TWSE", "加權指數"), ("TPEx", "櫃買指數")):
            rows = conn.execute("SELECT trade_date,close,source_url FROM benchmark_daily WHERE market=? AND trade_date<=? ORDER BY trade_date DESC LIMIT 2", (market, date.today().isoformat())).fetchall()
            if rows:
                result[market] = {"label": label, "value": rows[0]["close"], "date": rows[0]["trade_date"], "change": round(rows[0]["close"] - rows[1]["close"], 2) if len(rows) > 1 else None, "change_pct": _pct(rows[0]["close"], rows[1]["close"]) if len(rows) > 1 else None, "source_url": rows[0]["source_url"]}
    return result


def _market_limits() -> dict[str, Any]:
    """Return the latest official stock-only counts, combining matching dates only."""
    if not CHIP_DB.exists():
        return {"date": None, "limit_up_count": None, "limit_down_count": None, "markets": {}}
    with _db(CHIP_DB) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_limit_daily'").fetchone():
            return {"date": None, "limit_up_count": None, "limit_down_count": None, "markets": {}}
        rows = conn.execute("""SELECT market,trade_date,limit_up_count,limit_down_count,source_url
            FROM market_limit_daily WHERE trade_date<=? AND trade_date=(
                SELECT MAX(other.trade_date) FROM market_limit_daily AS other
                WHERE other.market=market_limit_daily.market AND other.trade_date<=?)""",
            (date.today().isoformat(), date.today().isoformat())).fetchall()
    markets = {row["market"]: dict(row) for row in rows}
    twse, tpex = markets.get("TWSE"), markets.get("TPEx")
    if twse and tpex and twse["trade_date"] == tpex["trade_date"]:
        return {"date": twse["trade_date"], "limit_up_count": twse["limit_up_count"] + tpex["limit_up_count"], "limit_down_count": twse["limit_down_count"] + tpex["limit_down_count"], "markets": markets}
    return {"date": None, "limit_up_count": None, "limit_down_count": None, "markets": markets}


def _recent_revenue() -> dict[str, Any]:
    """Count already reported monthly revenue without treating it as quarterly earnings."""
    empty = {"report_month": None, "count": 0, "markets": {}, "updated_at": None, "partial": False, "source_urls": {}}
    if not REVENUE_DB.exists():
        return empty
    with _db(REVENUE_DB) as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='monthly_revenue'").fetchone():
            return empty
        month = conn.execute("SELECT MAX(report_month) FROM monthly_revenue WHERE report_month<=?", (date.today().strftime("%Y-%m"),)).fetchone()[0]
        if not month:
            return empty
        rows = conn.execute("SELECT market,COUNT(*) AS count,MAX(updated_at) AS updated_at FROM monthly_revenue WHERE report_month=? AND current_revenue IS NOT NULL GROUP BY market", (month,)).fetchall()
        previous = conn.execute("SELECT MAX(report_month) FROM monthly_revenue WHERE report_month<?", (month,)).fetchone()[0]
        previous_count = conn.execute("SELECT COUNT(*) FROM monthly_revenue WHERE report_month=? AND current_revenue IS NOT NULL", (previous,)).fetchone()[0] if previous else 0
    markets = {row["market"]: row["count"] for row in rows}
    count = sum(markets.values())
    year, month_number = map(int, month.split("-"))
    roc_year = year - 1911
    source_urls = {"上市": f"https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{month_number}_0.html", "上櫃": f"https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{roc_year}_{month_number}_0.html"}
    return {"report_month": month, "count": count, "markets": markets, "updated_at": max((row["updated_at"] for row in rows), default=None), "partial": previous_count > 0 and count < previous_count, "source_urls": source_urls}


def _industries() -> tuple[str | None, list[dict[str, Any]], dict[str, dict[str, Any]]]:
    if not ROTATION_DB.exists():
        return None, [], {}
    with _db(ROTATION_DB) as conn:
        anchor = conn.execute("SELECT MAX(trade_date) FROM rotation_daily WHERE trade_date<=?", (date.today().isoformat(),)).fetchone()[0]
        if not anchor:
            return None, [], {}
        rows = [dict(row) for row in conn.execute("SELECT sector_key,l1,l2,l3,rotation_score,return_1d,return_5d,return_20d,turnover_expansion,turnover_share_delta,breadth,breakout_participation,stage,observed_count,trade_date FROM rotation_daily WHERE trade_date=? AND level=3 AND rank_eligible=1 ORDER BY rotation_score DESC LIMIT 80", (anchor,))]
        volume_ratios = {row["sector_key"]: row["volume_ratio"] for row in conn.execute("""SELECT m.sector_key,AVG(s.volume_ratio) AS volume_ratio
            FROM stock_sector_memberships m JOIN rotation_stock_daily s
              ON s.market=m.market AND s.stock_id=m.stock_id
            WHERE s.trade_date=? AND m.valid_to IS NULL AND s.volume_ratio IS NOT NULL
            GROUP BY m.sector_key""", (anchor,))}
        for row in rows:
            row["volume_ratio"] = round(volume_ratios[row["sector_key"]], 2) if row["sector_key"] in volume_ratios else None
        primary = {row["stock_id"]: row["sector_key"] for row in conn.execute("SELECT stock_id,sector_key FROM stock_primary_sector WHERE valid_to IS NULL")}
    by_key = {row["sector_key"]: row for row in rows}
    return anchor, rows, {stock_id: by_key.get(key, {"sector_key": key, "l3": key.split(" > ")[-1], "rotation_score": None}) for stock_id, key in primary.items()}


def _signals(anchor: str | None) -> tuple[str | None, list[dict[str, Any]]]:
    if not SIGNAL_DB.exists():
        return None, []
    with _db(SIGNAL_DB) as conn:
        try:
            signal_date = conn.execute("SELECT MAX(signal_date) FROM daily_signals WHERE signal_date<=?", (anchor or date.today().isoformat(),)).fetchone()[0]
            if not signal_date:
                return None, []
            rows = [dict(row) for row in conn.execute("SELECT * FROM daily_signals WHERE signal_date=? ORDER BY is_new DESC,change_pct DESC", (signal_date,))]
            return signal_date, rows
        except sqlite3.OperationalError:
            return None, []


def _liquid_home_signals(signals: list[dict[str, Any]], signal_date: str | None, *, price_path: Path = PRICE_DB) -> list[dict[str, Any]]:
    """Apply the homepage-only OR liquidity rule using same-day cached share volume."""
    if not signals or not signal_date or not price_path.exists():
        return []
    wanted = {row["stock_id"] for row in signals}
    liquidity: dict[str, tuple[float, float]] = {}
    with _db(price_path) as conn:
        rows = conn.execute("SELECT symbol,close,volume FROM price_history WHERE trade_date=?", (signal_date,))
        for row in rows:
            symbol = row["symbol"]
            if not symbol.endswith((".TW", ".TWO")):
                continue
            stock_id = symbol.split(".", 1)[0]
            if stock_id not in wanted or row["close"] is None or row["volume"] is None:
                continue
            close, volume = float(row["close"]), float(row["volume"])
            if not (isfinite(close) and isfinite(volume) and close > 0 and volume > 0):
                continue
            liquidity[stock_id] = (volume, close * volume)
    filtered = []
    for signal in signals:
        metrics = liquidity.get(signal["stock_id"])
        if not metrics:
            continue
        volume, estimated_turnover = metrics
        if volume <= MIN_SIGNAL_VOLUME_SHARES and estimated_turnover <= MIN_SIGNAL_ESTIMATED_TURNOVER_TWD:
            continue
        filtered.append({**signal, "volume_lots": round(volume / 1_000, 3), "estimated_turnover_twd": round(estimated_turnover)})
    return filtered


def _enrich_large_holder_signals(signals: list[dict[str, Any]], signal_date: str | None, *, chip_path: Path = CHIP_DB) -> list[dict[str, Any]]:
    """Attach TDCC weekly percentage changes while retaining every liquid signal."""
    enriched = [{**signal, "large_holder_pct": None, "large_holder_change_pp": None,
                 "ownership_report_date": None, "ownership_previous_date": None} for signal in signals]
    if not enriched or not signal_date or not chip_path.exists():
        return enriched
    current_day = date.fromisoformat(signal_date)
    wanted = sorted({row["stock_id"] for row in enriched})
    by_stock: dict[str, dict[str, float]] = defaultdict(dict)
    try:
        with _db(chip_path) as conn:
            dates = [row[0] for row in conn.execute(
                "SELECT DISTINCT report_date FROM stock_ownership_distribution_weekly WHERE report_date<=? ORDER BY report_date DESC LIMIT 2",
                (signal_date,),
            )]
            if len(dates) != 2 or (current_day - date.fromisoformat(dates[0])).days > 14 or (date.fromisoformat(dates[0]) - date.fromisoformat(dates[1])).days > 14:
                return enriched
            for start in range(0, len(wanted), 400):
                batch = wanted[start:start + 400]
                placeholders = ",".join("?" for _ in batch)
                rows = conn.execute(
                    f"""SELECT stock_id,report_date,
                        MAX(CASE WHEN tier=15 THEN shares END) AS large_shares,
                        MAX(CASE WHEN tier=17 THEN shares END) AS total_shares,
                        COUNT(*) AS tier_count
                        FROM stock_ownership_distribution_weekly
                        WHERE stock_id IN ({placeholders}) AND report_date IN (?,?)
                        GROUP BY stock_id,report_date""",
                    [*batch, *dates],
                )
                for row in rows:
                    if row["tier_count"] != 17 or row["large_shares"] is None or not row["total_shares"]:
                        continue
                    by_stock[row["stock_id"]][row["report_date"]] = row["large_shares"] / row["total_shares"] * 100
    except (sqlite3.Error, ValueError):
        return enriched
    for signal in enriched:
        weekly = by_stock.get(signal["stock_id"], {})
        if dates[0] in weekly:
            signal["large_holder_pct"] = round(weekly[dates[0]], 4)
            signal["ownership_report_date"] = dates[0]
        if dates[0] in weekly and dates[1] in weekly:
            signal["large_holder_change_pp"] = round(weekly[dates[0]] - weekly[dates[1]], 4)
            signal["ownership_previous_date"] = dates[1]
    return enriched


def _rising_large_holder_signals(signals: list[dict[str, Any]], signal_date: str | None, *, chip_path: Path = CHIP_DB) -> list[dict[str, Any]]:
    """Retain only signals with a verified rise for the optional homepage filter."""
    return [row for row in _enrich_large_holder_signals(signals, signal_date, chip_path=chip_path)
            if row["large_holder_change_pp"] is not None and row["large_holder_change_pp"] > 0]


def _large_holder_strategy_signals(prices: dict[str, dict[str, Any]], signal_date: str | None,
                                   eligible_codes: set[str], *, price_path: Path = PRICE_DB,
                                   chip_path: Path = CHIP_DB) -> list[dict[str, Any]]:
    """Create a standalone weekly TDCC signal, independent of technical strategies."""
    if not signal_date:
        return []
    candidates = [{"stock_id": stock_id, "signal_date": signal_date,
                   "strategy": "large_holder_increase", "price": price["price"],
                   "change_pct": price["change_pct"], "volume_ratio": None,
                   "distance_to_high_pct": None, "is_new": 0}
                  for stock_id, price in prices.items()
                  if stock_id in eligible_codes and price.get("trade_date") == signal_date]
    liquid = _liquid_home_signals(candidates, signal_date, price_path=price_path)
    rising = _rising_large_holder_signals(liquid, signal_date, chip_path=chip_path)
    return sorted(rising, key=lambda row: row["large_holder_change_pp"], reverse=True)


def _watchlist_codes() -> list[dict[str, Any]]:
    if not WATCH_DB.exists():
        return []
    with _db(WATCH_DB) as conn:
        try:
            return [dict(row) for row in conn.execute("SELECT DISTINCT stock_code,stock_name FROM watchlist_items ORDER BY stock_code LIMIT 100")]
        except sqlite3.OperationalError:
            return []


def build_dashboard() -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    anchor, prices, breadth = _price_snapshot()
    benchmark = _benchmarks()
    industry_date, industries, stock_industry = _industries()
    signal_date, all_signals = _signals(anchor)
    names: dict[str, str] = {}
    if STOCK_DB.exists():
        with _db(STOCK_DB) as conn:
            names = {row["code"]: row["name_zh"] for row in conn.execute("SELECT code,name_zh FROM securities")}
    technical_signals = _enrich_large_holder_signals(_liquid_home_signals(all_signals, signal_date), signal_date)
    ownership_signals = _large_holder_strategy_signals(prices, anchor, set(names))
    signals = technical_signals + ownership_signals
    display_signal_date = max((day for day in (signal_date, anchor if ownership_signals else None) if day), default=None)
    for signal in signals:
        signal["name"] = names.get(signal["stock_id"], signal["stock_id"])
        sector = stock_industry.get(signal["stock_id"], {})
        signal["industry"] = sector.get("l3")
        signal["industry_score"] = sector.get("rotation_score")
    end = date.today() + timedelta(days=14)
    event_bundle = list_events(start_date=(date.today() - timedelta(days=7)).isoformat(), end_date=end.isoformat())
    watch_items = _watchlist_codes()
    watch_codes = {item["stock_code"] for item in watch_items}
    active_signals: dict[str, list[str]] = defaultdict(list)
    for signal in [*all_signals, *ownership_signals]:
        active_signals[signal["stock_id"]].append(signal["strategy"])
    events_by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in event_bundle["rows"]:
        event["is_watchlist"] = event["stock_id"] in watch_codes
        event["has_signal"] = event["stock_id"] in active_signals
        events_by_stock[event["stock_id"]].append(event)
    watchlist = []
    for item in watch_items:
        stock_id = item["stock_code"]
        sector = stock_industry.get(stock_id, {})
        future_events = [event for event in events_by_stock[stock_id] if event["event_date"] >= date.today().isoformat()]
        watchlist.append({"stock_id": stock_id, "name": item["stock_name"] or names.get(stock_id, stock_id), **prices.get(stock_id, {}), "industry": sector.get("l3"), "industry_score": sector.get("rotation_score"), "signals": active_signals.get(stock_id, []), "next_event": future_events[0] if future_events else None})
    important = []
    for signal in signals:
        if not signal["is_new"]:
            continue
        for event in events_by_stock[signal["stock_id"]]:
            days = (date.fromisoformat(event["event_date"]) - date.today()).days
            if 0 <= days <= 7:
                important.append({"stock_id": signal["stock_id"], "name": signal["name"], "strategy": signal["strategy"], "event_type": event["event_type"], "event_date": event["event_date"], "days_until": days, "status": event["status"], "title": event["title"]})
                break
    tsmc = prices.get("2330")
    return {
        "last_updated": now, "market": {"benchmarks": benchmark, "turnover_estimate": breadth.get("turnover_estimate"), "turnover_ratios": market_turnover_ratios(), "tsmc": tsmc, "price_date": anchor},
        "breadth": {**breadth, "limits": _market_limits()}, "industry_date": industry_date, "industries": industries,
        "recent_revenue": _recent_revenue(),
        "signal_date": display_signal_date, "signals": signals, "events": event_bundle,
        "watchlist": watchlist, "important_events": important[:20],
        "strategy_performance": [{"strategy": label, "window": window, "signals": None, "win_rate": None, "average_return": None, "median_return": None, "max_drawdown": None} for label in ("Breakout", "Cup / Bowl Bottom", "Early Momentum") for window in (20, 60, 120)],
        "data_quality": {"price": "ready" if anchor else "unavailable", "industry": "ready" if industry_date else "unavailable", "signals": "ready" if display_signal_date else "unavailable", "events": "error" if any(state["last_error"] for state in event_bundle["source_state"]) else "ready" if event_bundle["source_state"] else "unavailable"},
    }
