"""Bounded official-price collection and provenance checks for ownership research."""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd

from modules.core.project_paths import PROJECT_ROOT, db_path
from modules.data_sources.market_watch import fetch_tpex_daily_quotes, fetch_twse_daily_quotes

DB_PATH = db_path("ownership_research.db")
CHIP_DB = db_path("chip_trends.db")
TAIPEI = ZoneInfo("Asia/Taipei")
MIGRATION = PROJECT_ROOT / "migrations" / "20261011_ownership_research.sql"
FETCHERS: dict[str, Callable[[date], pd.DataFrame]] = {
    "TWSE": fetch_twse_daily_quotes,
    "TPEx": fetch_tpex_daily_quotes,
}


def now_iso() -> str:
    return datetime.now(TAIPEI).isoformat(timespec="seconds")


def _taipei_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI)
    return parsed.astimezone(TAIPEI).isoformat(timespec="seconds")


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    return conn


def price_source_url(market: str, day: date) -> str:
    if market == "TWSE":
        return "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?" + urlencode(
            {"date": day.strftime("%Y%m%d"), "type": "ALLBUT0999", "response": "json"})
    if market == "TPEx":
        return "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?" + urlencode(
            {"l": "zh-tw", "o": "json", "d": f"{day.year - 1911:03d}/{day.month:02d}/{day.day:02d}", "se": "EW"})
    raise ValueError(f"Unsupported market: {market}")


def _valid_price_row(row: object) -> tuple[str, float, float, float, float, int] | None:
    code = str(getattr(row, "code", "") or "").strip()
    if len(code) != 4 or not code.isdigit():
        return None
    try:
        op, high, low, close, volume = (float(getattr(row, key)) for key in ("open", "high", "low", "close", "volume"))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (op, high, low, close, volume)):
        return None
    if min(op, high, low, close) <= 0 or volume <= 0 or int(volume) != volume or high < max(op, close) or low > min(op, close):
        return None
    return code, op, high, low, close, int(volume)


def refresh_price_day(day: date, market: str, *, path: Path = DB_PATH,
                      fetcher: Callable[[date], pd.DataFrame] | None = None,
                      force: bool = False) -> dict[str, object]:
    """Store one bounded official day. Empty responses never erase saved rows."""
    source_url = price_source_url(market, day)
    with connect(path) as conn:
        prior = conn.execute("SELECT status,row_count FROM research_source_fetches WHERE source_key='PRICE' AND market=? AND requested_date=?",
                             (market, day.isoformat())).fetchone()
        if prior and prior["status"] == "ok" and not force:
            return {"market": market, "date": day.isoformat(), "status": "cached", "rows": prior["row_count"]}
    fetched_at = now_iso()
    try:
        frame = (fetcher or FETCHERS[market])(day)
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("price fetcher did not return a DataFrame")
        rows = [parsed for item in frame.itertuples(index=False) if (parsed := _valid_price_row(item))]
        if not rows:
            status, error = "empty", "No dated, tradeable OHLCV rows; may be a holiday or source failure"
        else:
            status, error = "ok", None
    except Exception as exc:
        rows, status, error = [], "error", f"{type(exc).__name__}: {exc}"
    digest = hashlib.sha256(json.dumps(sorted(rows), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest() if rows else None
    with connect(path) as conn:
        if rows:
            conn.executemany("""INSERT INTO research_price_daily
                (market,stock_id,trade_date,open,high,low,close,volume_shares,source_url,first_seen_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(market,stock_id,trade_date) DO UPDATE SET
                  open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,
                  volume_shares=excluded.volume_shares,source_url=excluded.source_url""",
                [(market, code, day.isoformat(), op, high, low, close, volume, source_url, fetched_at)
                 for code, op, high, low, close, volume in rows])
        conn.execute("""INSERT INTO research_source_fetches
            (source_key,market,requested_date,source_url,fetched_at,status,row_count,content_sha256,error)
            VALUES ('PRICE',?,?,?,?,?,?,?,?)
            ON CONFLICT(source_key,market,requested_date) DO UPDATE SET
              source_url=excluded.source_url,fetched_at=excluded.fetched_at,status=excluded.status,
              row_count=excluded.row_count,content_sha256=excluded.content_sha256,error=excluded.error""",
            (market, day.isoformat(), source_url, fetched_at, status, len(rows), digest, error))
        conn.execute("""INSERT INTO research_source_fetch_attempts
            (source_key,market,requested_date,source_url,fetched_at,status,row_count,content_sha256,error)
            VALUES ('PRICE',?,?,?,?,?,?,?,?)""",
            (market, day.isoformat(), source_url, fetched_at, status, len(rows), digest, error))
    return {"market": market, "date": day.isoformat(), "status": status, "rows": len(rows), "error": error}


def backfill_prices(start: date, end: date, *, markets: tuple[str, ...] = ("TWSE", "TPEx"),
                    path: Path = DB_PATH, max_days: int = 31, delay_seconds: float = 0.5) -> list[dict[str, object]]:
    """Backfill a small requested window; never launch a 2016-to-today job implicitly."""
    if end < start or (end - start).days + 1 > max_days or max_days < 1:
        raise ValueError(f"Choose a valid window of at most {max_days} calendar days")
    if not markets or any(market not in FETCHERS for market in markets):
        raise ValueError("markets must be TWSE and/or TPEx")
    output = []
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for market in markets:
            output.append(refresh_price_day(day, market, path=path))
            if delay_seconds:
                time.sleep(delay_seconds)
    return output


def sync_ownership_metadata(*, chip_path: Path = CHIP_DB, path: Path = DB_PATH) -> dict[str, int]:
    """Validate existing 17-tier reports without copying or mutating the source DB."""
    if not chip_path.exists():
        return {"reports": 0, "valid": 0, "missing_source": 1}
    with sqlite3.connect(chip_path) as source, connect(path) as target:
        source.row_factory = sqlite3.Row
        if not source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='stock_ownership_distribution_weekly'").fetchone():
            return {"reports": 0, "valid": 0, "missing_source": 1}
        reports = source.execute("""SELECT stock_id,report_date,COUNT(*) AS tier_count,
            MIN(tier) AS min_tier,MAX(tier) AS max_tier,
            MAX(CASE WHEN tier=17 THEN shares END) AS total_shares,
            SUM(CASE WHEN tier BETWEEN 1 AND 15 THEN shares ELSE 0 END) AS holder_tier_shares,
            MAX(CASE WHEN tier=16 THEN shares END) AS adjustment_shares,
            MIN(shares) AS min_shares,MIN(reported_pct) AS min_pct,MAX(reported_pct) AS max_pct,
            MIN(source_url) AS source_url,MIN(updated_at) AS first_seen_at
            FROM stock_ownership_distribution_weekly GROUP BY stock_id,report_date""")
        count = valid_count = 0
        for row in reports:
            valid = (row["tier_count"] == 17 and row["min_tier"] == 1 and row["max_tier"] == 17
                     and row["total_shares"] is not None and row["total_shares"] > 0
                     and row["min_shares"] >= 0 and (row["min_pct"] is None or row["min_pct"] >= 0)
                     and (row["max_pct"] is None or row["max_pct"] <= 100)
                     and row["adjustment_shares"] is not None
                     and row["holder_tier_shares"] - row["adjustment_shares"] == row["total_shares"])
            archived = "tdcc-opendata-archive" in row["source_url"]
            if valid:
                reason = None
            elif (row["tier_count"] == 17 and row["total_shares"] is not None
                  and row["adjustment_shares"] is not None
                  and row["holder_tier_shares"] - row["adjustment_shares"] != row["total_shares"]):
                residual = row["holder_tier_shares"] - row["adjustment_shares"] - row["total_shares"]
                reason = f"Holder tiers less tier-16 adjustment differ from total by {residual:+d} shares"
            elif ((row["min_pct"] is not None and row["min_pct"] < 0)
                  or (row["max_pct"] is not None and row["max_pct"] > 100)):
                reason = f"Reported percentage outside 0–100 range: {row['min_pct']} to {row['max_pct']}"
            else:
                reason = "Incomplete tiers, nonpositive total, or invalid shares/percentage"
            target.execute("""INSERT INTO research_ownership_weekly_meta
                (stock_id,report_date,source_url,first_seen_at,published_at,publication_status,
                 tier_count,total_shares,valid,quality_reason) VALUES (?,?,?,?,NULL,?,?,?,?,?)
                ON CONFLICT(stock_id,report_date) DO UPDATE SET
                  source_url=excluded.source_url,
                  first_seen_at=MIN(research_ownership_weekly_meta.first_seen_at,excluded.first_seen_at),
                  publication_status=CASE WHEN research_ownership_weekly_meta.publication_status='verified' THEN 'verified' ELSE excluded.publication_status END,
                  tier_count=excluded.tier_count,total_shares=excluded.total_shares,
                  valid=excluded.valid,quality_reason=excluded.quality_reason""",
                (row["stock_id"], row["report_date"], row["source_url"],
                 _taipei_timestamp(row["first_seen_at"]),
                 "unverified_archive" if archived else "first_observed", row["tier_count"],
                 row["total_shares"], int(valid), reason))
            count += 1
            valid_count += int(valid)
    return {"reports": count, "valid": valid_count, "missing_source": 0}


def quality_report(*, path: Path = DB_PATH) -> dict[str, object]:
    """Persist and return an honest coverage report; no missing values become zeros."""
    with connect(path) as conn:
        owner = conn.execute("""SELECT COUNT(*) AS reports,SUM(valid) AS valid,
            SUM(publication_status='unverified_archive') AS archived,
            SUM(publication_status='first_observed') AS first_observed,
            MIN(report_date) AS first_week,MAX(report_date) AS last_week,
            COUNT(DISTINCT report_date) AS week_count FROM research_ownership_weekly_meta""").fetchone()
        price = conn.execute("SELECT COUNT(*) AS rows,SUM(adjusted_close IS NOT NULL) AS adjusted,MIN(trade_date) AS first_day,MAX(trade_date) AS last_day FROM research_price_daily").fetchone()
        issues = [dict(row) for row in conn.execute("SELECT stock_id,report_date,quality_reason FROM research_ownership_weekly_meta WHERE valid=0 ORDER BY report_date DESC LIMIT 20")]
        result = {"ownership_reports": owner["reports"], "valid_reports": owner["valid"] or 0,
                  "archive_reports_without_publication_time": owner["archived"] or 0,
                  "first_observed_reports": owner["first_observed"] or 0,
                  "first_week": owner["first_week"], "last_week": owner["last_week"],
                  "week_count": owner["week_count"], "official_price_rows": price["rows"],
                  "adjusted_price_rows": price["adjusted"] or 0,
                  "first_price_day": price["first_day"], "last_price_day": price["last_day"],
                  "sample_issues": issues,
                  "strict_research_ready": bool(owner["week_count"] >= 16 and price["adjusted"] and owner["archived"] == 0)}
        conn.execute("""INSERT INTO research_quality_runs
            (checked_at,first_week,last_week,report_count,valid_report_count,archived_report_count,
             first_observed_count,price_rows,adjusted_price_rows,notes)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (now_iso(),owner["first_week"],owner["last_week"],owner["reports"],owner["valid"] or 0,
             owner["archived"] or 0,owner["first_observed"] or 0,price["rows"],price["adjusted"] or 0,
             "Archived TDCC publication times and adjusted prices require verification before predictive claims."))
    return result
