"""Daily electronics sector rotation metrics from the existing OHLCV cache."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from statistics import mean, median
from zoneinfo import ZoneInfo

from modules.core.project_paths import db_path
from modules.data_sources.market_watch import fetch_tpex_daily_quotes, fetch_twse_daily_quotes
from modules.data_sources.price_cache import init_price_cache
from modules.data_sources.stock_db import DB_PATH as STOCK_DB_PATH
from modules.industry.electronics_universe import DB_PATH, init_sector_db

PRICE_DB_PATH = db_path("price_cache.db")


@contextmanager
def _connection(path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()
WEIGHTS = {
    "advance_ratio": 0.20,
    "median_return": 0.15,
    "volume_expansion_ratio": 0.20,
    "breakout_ratio": 0.15,
    "relative_strength": 0.15,
    "turnover_momentum": 0.15,
}


def _clip(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _price_features(history: list[tuple], window: int, anchor: str) -> dict | None:
    if len(history) < max(window + 1, 21) or history[-1][0] != anchor:
        return None
    latest = history[-1]
    prior = history[-window - 1]
    if not prior[1] or latest[1] is None or not latest[2] or latest[2] <= 0:
        return None
    change = 100 * (latest[1] / prior[1] - 1)
    previous_five = history[-6:-1]
    base_volume = mean([row[2] or 0 for row in previous_five])
    base_turnover = mean([(row[1] or 0) * (row[2] or 0) for row in previous_five])
    turnover = (latest[1] or 0) * (latest[2] or 0)
    prior_high = max((row[3] or 0) for row in history[-21:-1])
    return {
        "return": _clip(change, -10, 10),
        "volume_expanded": base_volume > 0 and (latest[2] or 0) >= 1.5 * base_volume,
        "breakout": prior_high > 0 and latest[1] > prior_high,
        "turnover_ratio": _clip(turnover / base_turnover, 0, 3) if base_turnover > 0 else 0,
    }


def aggregate_sector_metrics(
    histories: dict[str, list[tuple]],
    memberships: dict[str, set[str]],
    anchor: str,
    window: int,
    *,
    minimum_constituents: int = 5,
) -> list[dict]:
    """Pure aggregation; returns all sectors, including unranked small groups."""
    all_features = {symbol: feature for symbol, history in histories.items() if (feature := _price_features(history, window, anchor))}
    market_median = median([feature["return"] for feature in all_features.values()]) if all_features else 0.0
    rows = []
    for slug, symbols in memberships.items():
        features = [all_features[symbol] for symbol in symbols if symbol in all_features]
        n = len(features)
        if not n:
            continue
        returns = [item["return"] for item in features]
        advance_ratio = sum(value > 0 for value in returns) / n
        median_return = median(returns)
        volume_expansion_ratio = sum(item["volume_expanded"] for item in features) / n
        breakout_ratio = sum(item["breakout"] for item in features) / n
        relative_strength = median_return - market_median
        turnover_momentum = median(item["turnover_ratio"] for item in features)
        components = {
            "advance_ratio": advance_ratio,
            "median_return": median_return,
            "volume_expansion_ratio": volume_expansion_ratio,
            "breakout_ratio": breakout_ratio,
            "relative_strength": relative_strength,
            "turnover_momentum": turnover_momentum,
        }
        # All six inputs become bounded 0–100 signals before applying package weights.
        signals = {
            "advance_ratio": advance_ratio * 100,
            "median_return": _clip(50 + 5 * median_return, 0, 100),
            "volume_expansion_ratio": volume_expansion_ratio * 100,
            "breakout_ratio": breakout_ratio * 100,
            "relative_strength": _clip(50 + 5 * relative_strength, 0, 100),
            "turnover_momentum": _clip(50 * turnover_momentum, 0, 100),
        }
        rows.append({
            "trade_date": anchor, "window_days": window, "category_slug": slug,
            "constituent_count": len(symbols), "observed_count": n,
            **components,
            "equal_weight_return": mean(returns),
            "rotation_score": round(sum(WEIGHTS[key] * signals[key] for key in WEIGHTS), 3),
            "rank_eligible": int(len(symbols) >= minimum_constituents and n >= minimum_constituents),
        })
    return rows


def _load_memberships(path=DB_PATH) -> dict[str, set[str]]:
    with _connection(path) as conn:
        rows = conn.execute("""SELECT m.category_slug,e.stock_id,e.market FROM stock_sector_map m
            JOIN official_electronics e ON e.market=m.market AND e.stock_id=m.stock_id
            WHERE e.active=1""")
        memberships: dict[str, set[str]] = defaultdict(set)
        for slug, stock_id, market in rows:
            memberships[slug].add(stock_id + (".TW" if market == "TWSE" else ".TWO"))
    return memberships


def _load_histories(anchor: str, path=PRICE_DB_PATH) -> dict[str, list[tuple]]:
    cutoff = (date.fromisoformat(anchor) - timedelta(days=70)).isoformat()
    with _connection(path) as conn:
        rows = conn.execute("""SELECT symbol,trade_date,close,volume,high FROM price_history
            WHERE trade_date BETWEEN ? AND ? AND (symbol LIKE '%.TW' OR symbol LIKE '%.TWO')
            ORDER BY symbol,trade_date""", (cutoff, anchor))
        histories: dict[str, list[tuple]] = defaultdict(list)
        for symbol, trade_date, close, volume, high in rows:
            histories[symbol].append((trade_date, close, volume, high))
    return histories


def refresh_official_electronics_prices(*, days: int = 7, path=DB_PATH, price_path=PRICE_DB_PATH) -> dict:
    """Fill electronics prices and the full-market relative-strength baseline."""
    init_sector_db(path)
    if price_path == PRICE_DB_PATH:
        init_price_cache()
    memberships = _load_memberships(path)
    symbols = set().union(*memberships.values()) if memberships else set()
    # Fine-sector targets also include verified electronics-adjacent companies.
    with _connection(path) as conn:
        try:
            symbols.update(stock_id + (".TW" if market == "TWSE" else ".TWO")
                           for market, stock_id in conn.execute(
                               "SELECT market,stock_id FROM fine_companies WHERE active=1 AND is_target=1"))
        except sqlite3.OperationalError:
            pass  # V2-only databases remain usable before the fine-sector migration.
    with _connection(STOCK_DB_PATH) as conn:
        symbols.update(row[0] for row in conn.execute("SELECT yfinance_symbol FROM securities WHERE market IN ('TWSE','TPEx')"))
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    end_date = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    rows = []
    trade_dates = []
    for offset in range(max(1, days) - 1, -1, -1):
        day = end_date - timedelta(days=offset)
        listed = fetch_twse_daily_quotes(day)
        otc = fetch_tpex_daily_quotes(day)
        if listed.empty and otc.empty:
            continue
        if listed.empty or otc.empty:
            raise ValueError(f"Incomplete daily quote snapshot for {day}: TWSE={len(listed)} TPEx={len(otc)}")
        trade_dates.append(day.isoformat())
        for suffix, frame in ((".TW", listed), (".TWO", otc)):
            for record in frame.to_dict("records"):
                symbol = str(record["code"]) + suffix
                if symbol not in symbols or record.get("close") is None or record.get("volume") is None or record["volume"] <= 0:
                    continue
                rows.append((symbol, day.isoformat(), record.get("open"), record.get("high"), record.get("low"), record["close"], record.get("volume")))
    if not rows:
        return {"trade_dates": [], "rows": 0}
    touched = {row[0] for row in rows}
    updated_at = now.isoformat(timespec="seconds")
    with _connection(price_path) as conn:
        conn.executemany("""INSERT INTO price_history(symbol,trade_date,open,high,low,close,volume)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(symbol,trade_date) DO UPDATE SET
            open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,volume=excluded.volume""", rows)
        for symbol in touched:
            first_date, last_date, row_count = conn.execute("SELECT MIN(trade_date),MAX(trade_date),COUNT(*) FROM price_history WHERE symbol=?", (symbol,)).fetchone()
            conn.execute("""INSERT INTO price_cache_meta(symbol,last_updated_at,first_cached_date,last_cached_date,last_trade_date,last_checked_date,row_count,source,fetch_status)
                VALUES(?,?,?,?,?,?,?,'twse_tpex_daily','ready') ON CONFLICT(symbol) DO UPDATE SET
                last_updated_at=excluded.last_updated_at,first_cached_date=excluded.first_cached_date,
                last_cached_date=excluded.last_cached_date,last_trade_date=excluded.last_trade_date,
                last_checked_date=excluded.last_checked_date,row_count=excluded.row_count,source=excluded.source,
                fetch_status='ready',last_error=NULL""",
                (symbol, updated_at, first_date, last_date, last_date, last_date, row_count))
    return {"trade_dates": trade_dates, "rows": len(rows), "symbols": len(touched)}


def refresh_sector_metrics(*, anchor: str | None = None, path=DB_PATH, price_path=PRICE_DB_PATH) -> dict:
    init_sector_db(path)
    with _connection(price_path) as conn:
        latest = conn.execute("SELECT MAX(trade_date) FROM price_history WHERE symbol LIKE '%.TW' OR symbol LIKE '%.TWO'").fetchone()[0]
    anchor = anchor or latest
    if not anchor:
        return {"trade_date": None, "rows": 0, "reason": "price_cache_empty"}
    histories = _load_histories(anchor, price_path)
    memberships = _load_memberships(path)
    rows = [row for window in (1, 3, 5) for row in aggregate_sector_metrics(histories, memberships, anchor, window)]
    fields = ["trade_date", "window_days", "category_slug", "constituent_count", "observed_count", "advance_ratio", "median_return", "equal_weight_return", "volume_expansion_ratio", "breakout_ratio", "relative_strength", "turnover_momentum", "rotation_score", "rank_eligible"]
    with _connection(path) as conn:
        conn.executemany(f"INSERT OR REPLACE INTO sector_daily_metrics({','.join(fields)}) VALUES({','.join('?' for _ in fields)})", [tuple(row[field] for field in fields) for row in rows])
    return {"trade_date": anchor, "rows": len(rows), "ranked_rows": sum(row["rank_eligible"] for row in rows)}


def backfill_sector_metrics(*, trade_days: int = 20, path=DB_PATH, price_path=PRICE_DB_PATH) -> list[dict]:
    with _connection(price_path) as conn:
        days = [row[0] for row in conn.execute("""SELECT trade_date FROM price_history
            WHERE symbol LIKE '%.TW' OR symbol LIKE '%.TWO'
            GROUP BY trade_date HAVING COUNT(DISTINCT symbol) >= 500
            ORDER BY trade_date DESC LIMIT ?""", (trade_days,))]
    return [refresh_sector_metrics(anchor=day, path=path, price_path=price_path) for day in reversed(days)]


def get_sector_ranking(*, trade_date: str | None = None, window_days: int = 1, path=DB_PATH) -> list[dict]:
    if window_days not in (1, 3, 5):
        raise ValueError("window_days must be 1, 3, or 5")
    init_sector_db(path)
    with _connection(path) as conn:
        conn.row_factory = sqlite3.Row
        if trade_date is None:
            trade_date = conn.execute("SELECT MAX(trade_date) FROM sector_daily_metrics").fetchone()[0]
        if not trade_date:
            return []
        return [dict(row) for row in conn.execute("""SELECT m.*,c.name_zh,c.type,c.parent_slug FROM sector_daily_metrics m
            JOIN sector_categories c ON c.slug=m.category_slug
            WHERE m.trade_date=? AND m.window_days=? AND m.rank_eligible=1
            ORDER BY m.rotation_score DESC,m.observed_count DESC""", (trade_date, window_days))]
