"""Official TWSE/TPEx daily credit balances and TDCC weekly ownership snapshots.

Collection runs in the worker, never in a page request. Balances are trading units
(one board lot for these reports); TDCC quantities are shares, not lots.
"""
from __future__ import annotations

import sqlite3
import time
import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import requests

from modules.core.project_paths import PROJECT_ROOT, db_path

DB_NAME = "chip_trends.db"
TWSE_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN"
TPEX_URL = "https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php"
TDCC_URL = "https://openapi.tdcc.com.tw/v1/opendata/1-5"
TDCC_ARCHIVE_API = "https://api.github.com/repos/wirelessr/tdcc-opendata-archive/contents/snapshots"
TDCC_ARCHIVE_RAW = "https://raw.githubusercontent.com/wirelessr/tdcc-opendata-archive/main/snapshots"
SOURCE_URLS = {"TWSE": "https://www.twse.com.tw/zh/trading/margin/mi-margn.html", "TPEx": "https://www.tpex.org.tw/zh-tw/mainboard/trading/margin-trading/transactions.html", "TDCC": "https://openapi.tdcc.com.tw/"}
TIERS = {400: range(12, 16), 600: range(13, 16), 800: range(14, 16), 1000: range(15, 16)}


def connect(path: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(path or str(db_path(DB_NAME)), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript((PROJECT_ROOT / "migrations" / "20261009_chip_trends.sql").read_text(encoding="utf-8"))
    conn.executescript((PROJECT_ROOT / "migrations" / "20261014_market_limit_stocks.sql").read_text(encoding="utf-8"))
    if "margin_previous_thousand_twd" not in {row[1] for row in conn.execute("PRAGMA table_info(market_margin_short_daily)")}:
        conn.execute("ALTER TABLE market_margin_short_daily ADD COLUMN margin_previous_thousand_twd INTEGER")
    return conn


def integer(value: Any) -> int | None:
    if value is None or str(value).strip() in {"", "--", "-", "N/A"}:
        return None
    return int(str(value).replace(",", ""))


def real(value: Any) -> float | None:
    if value is None or str(value).strip() in {"", "--", "-", "N/A"}:
        return None
    return float(str(value).replace(",", ""))


def ratio(short_lots: int | None, margin_lots: int | None) -> float | None:
    return round(short_lots / margin_lots * 100, 4) if short_lots is not None and margin_lots and margin_lots > 0 else None


def _requested_date(payload: dict, requested: date) -> bool:
    return payload.get("date") == requested.strftime("%Y%m%d")


def parse_twse(payload: dict, day: date) -> tuple[dict, list[dict]] | None:
    if payload.get("stat") != "OK" or not _requested_date(payload, day):
        return None
    tables = payload.get("tables") or []
    summary = next((t for t in tables if any(r[0] == "融資(交易單位)" for r in t.get("data", []))), None)
    detail = next((t for t in tables if len(t.get("fields", [])) >= 16 and t.get("fields", [None])[0] == "代號"), None)
    if not summary or not detail:
        raise ValueError("TWSE margin report fields changed")
    expected = {2: "買進", 3: "賣出", 4: "現金償還", 5: "前日餘額", 6: "今日餘額", 8: "買進", 9: "賣出", 10: "現券償還", 11: "前日餘額", 12: "今日餘額"}
    if any(detail["fields"][index] != label for index, label in expected.items()):
        raise ValueError("TWSE margin report column order changed")
    by_label = {r[0]: r for r in summary["data"]}
    m, s, amount = (by_label.get(k) for k in ("融資(交易單位)", "融券(交易單位)", "融資金額(仟元)"))
    if not m or not s:
        raise ValueError("TWSE market totals missing")
    market = dict(margin_balance_lots=integer(m[5]), margin_previous_lots=integer(m[4]), short_balance_lots=integer(s[5]), short_previous_lots=integer(s[4]), margin_balance_thousand_twd=integer(amount[5]) if amount else None, margin_previous_thousand_twd=integer(amount[4]) if amount else None)
    rows = []
    for r in detail["data"]:
        code = str(r[0]).strip()
        if len(code) != 4 or not code.isdigit():
            continue
        values = [integer(r[i]) for i in (5, 2, 3, 4, 6, 11, 9, 8, 10, 12, 7, 13)]
        if values[4] is None or values[9] is None:
            continue
        rows.append(dict(stock_id=code, market="TWSE", trade_date=day.isoformat(), margin_previous_lots=values[0], margin_buy_lots=values[1], margin_sell_lots=values[2], margin_cash_repayment_lots=values[3], margin_balance_lots=values[4], short_previous_lots=values[5], short_sell_lots=values[6], short_buy_lots=values[7], short_repayment_lots=values[8], short_balance_lots=values[9], margin_limit_lots=values[10], short_limit_lots=values[11], margin_usage_pct=None, short_usage_pct=None))
    if not rows:
        raise ValueError("TWSE stock report empty")
    return market, rows


def parse_tpex(payload: dict, day: date) -> tuple[dict, list[dict]] | None:
    if payload.get("stat") != "ok" or not _requested_date(payload, day):
        return None
    table = next((t for t in payload.get("tables", []) if len(t.get("fields", [])) >= 20 and t["fields"][0] == "代號"), None)
    if table is not None and not table.get("data"):
        return None
    if not table:
        raise ValueError("TPEx margin report fields changed")
    expected = {2: "前資餘額(張)", 3: "資買", 4: "資賣", 5: "現償", 6: "資餘額", 10: "前券餘額(張)", 11: "券賣", 12: "券買", 13: "券償", 14: "券餘額"}
    if any(table["fields"][index] != label for index, label in expected.items()):
        raise ValueError("TPEx margin report column order changed")
    rows = []
    totals = dict(margin_balance_lots=0, margin_previous_lots=0, short_balance_lots=0, short_previous_lots=0, margin_balance_thousand_twd=None, margin_previous_thousand_twd=None)
    for r in table["data"]:
        # Market totals cover the complete official report, including ETFs.
        for key, index in (("margin_previous_lots", 2), ("margin_balance_lots", 6), ("short_previous_lots", 10), ("short_balance_lots", 14)):
            value = integer(r[index])
            if value is None:
                raise ValueError(f"TPEx {key} missing; cannot safely aggregate")
            totals[key] += value
        code = str(r[0]).strip()
        if len(code) != 4 or not code.isdigit():
            continue
        values = [integer(r[i]) for i in (2, 3, 4, 5, 6, 10, 11, 12, 13, 14, 9, 17)]
        rows.append(dict(stock_id=code, market="TPEx", trade_date=day.isoformat(), margin_previous_lots=values[0], margin_buy_lots=values[1], margin_sell_lots=values[2], margin_cash_repayment_lots=values[3], margin_balance_lots=values[4], short_previous_lots=values[5], short_sell_lots=values[6], short_buy_lots=values[7], short_repayment_lots=values[8], short_balance_lots=values[9], margin_limit_lots=values[10], short_limit_lots=values[11], margin_usage_pct=real(r[8]), short_usage_pct=real(r[16])))
    if not rows:
        raise ValueError("TPEx stock report empty")
    return totals, rows


def parse_tdcc(payload: list[dict]) -> tuple[str, list[dict]]:
    if not isinstance(payload, list) or not payload:
        raise ValueError("TDCC distribution empty")
    parsed = []
    report_dates = set()
    for source in payload:
        code = str(source.get("證券代號", "")).strip()
        if len(code) != 4 or not code.isdigit():
            continue
        date_text = str(next((v for k, v in source.items() if k.lstrip("\ufeff") == "資料日期"), ""))
        day = datetime.strptime(date_text, "%Y%m%d").date().isoformat()
        tier = integer(source.get("持股分級"))
        if tier is None or not 1 <= tier <= 17:
            raise ValueError("TDCC tier changed")
        report_dates.add(day)
        parsed.append(dict(stock_id=code, report_date=day, tier=tier, holder_count=integer(source.get("人數")), shares=integer(source.get("股數")), reported_pct=real(source.get("占集保庫存數比例%"))))
    if not parsed or len(report_dates) != 1 or any(r["holder_count"] is None or r["shares"] is None for r in parsed):
        raise ValueError("TDCC snapshot incomplete or mixed dates")
    return report_dates.pop(), parsed


def _write_rows(conn: sqlite3.Connection, table: str, rows: list[dict], source_url: str) -> None:
    if not rows:
        return
    now = datetime.now().isoformat(timespec="seconds")
    data = [{**row, "source_url": source_url, "updated_at": now} for row in rows]
    columns = list(data[0])
    placeholders = ",".join("?" for _ in columns)
    conn.executemany(f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})", [tuple(row.get(c) for c in columns) for row in data])


def _status(conn: sqlite3.Connection, source: str, day: str | None, error: str | None = None) -> None:
    if error:
        conn.execute("INSERT INTO chip_source_status(source,last_error) VALUES (?,?) ON CONFLICT(source) DO UPDATE SET last_error=excluded.last_error", (source, error[:500]))
    else:
        conn.execute("INSERT INTO chip_source_status(source,last_success_date,last_success_at,last_error) VALUES (?,?,?,NULL) ON CONFLICT(source) DO UPDATE SET last_success_date=MAX(COALESCE(chip_source_status.last_success_date,''),excluded.last_success_date),last_success_at=excluded.last_success_at,last_error=NULL", (source, day, datetime.now().isoformat(timespec="seconds")))


def refresh_margin_day(day: date, *, session: requests.Session | None = None, path: str | None = None, markets: set[str] | None = None) -> dict:
    client = session or requests.Session()
    result: dict[str, Any] = {"date": day.isoformat(), "markets": {}, "errors": {}}
    requests_to_make = (("TWSE", TWSE_URL, {"date": day.strftime("%Y%m%d"), "response": "json", "selectType": "ALL"}, parse_twse), ("TPEx", TPEX_URL, {"l": "zh-tw", "o": "json", "d": f"{day.year-1911}/{day:%m/%d}"}, parse_tpex))
    with connect(path) as conn:
        for market, url, params, parser in requests_to_make:
            if markets is not None and market not in markets:
                continue
            try:
                for attempt in range(3):
                    response = client.get(url, params=params, timeout=25, headers={"User-Agent": "Mozilla/5.0 TradeLab/1.0 (official public report)"})
                    response.raise_for_status()
                    try:
                        payload = response.json()
                        break
                    except ValueError:
                        if attempt == 2:
                            raise
                        time.sleep(1.5 * (attempt + 1))
                parsed = parser(payload, day)
                if parsed is None:
                    result["markets"][market] = "no_report"
                    continue
                totals, stocks = parsed
                source_url = response.url
                with conn:
                    _write_rows(conn, "market_margin_short_daily", [{"market": market, "trade_date": day.isoformat(), **totals}], source_url)
                    _write_rows(conn, "stock_margin_short_daily", stocks, source_url)
                    _status(conn, market, day.isoformat())
                result["markets"][market] = len(stocks)
            except Exception as exc:
                result["errors"][market] = str(exc)
                with conn:
                    _status(conn, market, None, str(exc))
    return result


def refresh_tdcc(*, session: requests.Session | None = None, path: str | None = None) -> dict:
    client = session or requests.Session()
    with connect(path) as conn:
        try:
            response = client.get(TDCC_URL, timeout=90, headers={"User-Agent": "TradeLab/1.0 (official public report)"})
            response.raise_for_status()
            day, rows = parse_tdcc(response.json())
            with conn:
                _write_rows(conn, "stock_ownership_distribution_weekly", rows, response.url)
                _status(conn, "TDCC", day)
            return {"date": day, "rows": len(rows), "stocks": len({r["stock_id"] for r in rows})}
        except Exception as exc:
            with conn:
                _status(conn, "TDCC", None, str(exc))
            return {"error": str(exc)}


def backfill_tdcc_archive(*, year: int = 2026, session: requests.Session | None = None, path: str | None = None) -> dict:
    """Import archived copies of TDCC's original weekly 1-5 CSV files.

    The archive is a third-party mirror. An existing official snapshot for a
    matching week must agree row-for-row before any historical import proceeds.
    Each CSV is checked for its advertised date and all 17 official tiers.
    """
    client = session or requests.Session()
    response = client.get(f"{TDCC_ARCHIVE_API}/{year}", timeout=30)
    response.raise_for_status()
    files = sorted(item["name"] for item in response.json() if item.get("type") == "file" and item["name"].startswith(f"{year}-") and item["name"].endswith(".csv"))
    if not files:
        raise ValueError(f"No archived TDCC weekly files for {year}")
    result: dict[str, Any] = {"year": year, "weeks_imported": 0, "weeks_existing": 0, "rows_imported": 0, "errors": []}
    with connect(path) as conn:
        existing = {row[0] for row in conn.execute("SELECT DISTINCT report_date FROM stock_ownership_distribution_weekly WHERE report_date BETWEEN ? AND ?", (f"{year}-01-01", f"{year}-12-31"))}
        # Verify the newest overlapping original snapshot first. This catches
        # a stale or modified mirror before filling earlier weeks.
        overlap = next((name for name in reversed(files) if name[:-4] in existing), None)
        if overlap:
            _read_tdcc_archived_week(client, conn, year, overlap, verify_existing=True)
        for name in files:
            day = name[:-4]
            if day in existing:
                result["weeks_existing"] += 1
                continue
            try:
                rows, source_url = _read_tdcc_archived_week(client, conn, year, name)
                with conn:
                    _write_rows(conn, "stock_ownership_distribution_weekly", rows, source_url)
                result["weeks_imported"] += 1
                result["rows_imported"] += len(rows)
            except Exception as exc:
                result["errors"].append({"week": day, "error": str(exc)})
    return result


def _read_tdcc_archived_week(client: requests.Session, conn: sqlite3.Connection, year: int, name: str, *, verify_existing: bool = False) -> tuple[list[dict], str]:
    source_url = f"{TDCC_ARCHIVE_RAW}/{year}/{name}"
    response = client.get(source_url, timeout=45)
    response.raise_for_status()
    day, rows = parse_tdcc(list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")))))
    if day != name[:-4]:
        raise ValueError(f"TDCC archive filename/date mismatch: {name} versus {day}")
    by_stock: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        if row["holder_count"] < 0 or row["shares"] < 0:
            raise ValueError(f"Invalid TDCC quantity on {day}")
        by_stock[row["stock_id"]].add(row["tier"])
    if len(by_stock) < 1000 or any(tiers != set(range(1, 18)) for tiers in by_stock.values()) or len(rows) != len(by_stock) * 17:
        raise ValueError(f"Incomplete TDCC archive snapshot on {day}")
    if verify_existing:
        stored = {(r[0], r[1]): (r[2], r[3], r[4]) for r in conn.execute("SELECT stock_id,tier,holder_count,shares,reported_pct FROM stock_ownership_distribution_weekly WHERE report_date=?", (day,))}
        archived = {(r["stock_id"], r["tier"]): (r["holder_count"], r["shares"], r["reported_pct"]) for r in rows}
        if stored != archived:
            raise ValueError(f"TDCC archive does not match saved snapshot on {day}")
    return rows, source_url


def backfill_margin(days: int = 370, *, end: date | None = None, path: str | None = None) -> dict:
    end = end or date.today()
    client = requests.Session()
    with connect(path) as conn:
        existing = {(row["market"], row["trade_date"]) for row in conn.execute("SELECT market,trade_date FROM market_margin_short_daily WHERE trade_date>=? AND trade_date<=?", ((end - timedelta(days=days)).isoformat(), end.isoformat()))}
    fetched = 0
    failures = []
    for offset in range(days - 1, -1, -1):
        day = end - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        needed = {market for market in ("TWSE", "TPEx") if (market, day.isoformat()) not in existing}
        if not needed:
            continue
        result = refresh_margin_day(day, session=client, path=path, markets=needed)
        fetched += sum(isinstance(v, int) for v in result["markets"].values())
        if result["errors"]:
            failures.append(result)
        time.sleep(0.35)
    return {"days": days, "market_days_written": fetched, "failures": failures}


def _dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(row) for row in rows]


def market_history(market: str = "TWSE", days: int = 370, *, path: str | None = None) -> dict:
    if market not in {"TWSE", "TPEx", "combined"}:
        raise ValueError("Unknown market")
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with connect(path) as conn:
        rows = _dicts(conn.execute("SELECT * FROM market_margin_short_daily WHERE trade_date >= ? ORDER BY trade_date", (cutoff,)).fetchall())
        status = _dicts(conn.execute("SELECT * FROM chip_source_status WHERE source IN ('TWSE','TPEx')").fetchall())
    by_day: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        by_day[row["trade_date"]][row["market"]] = row
    output = []
    for day, markets in sorted(by_day.items()):
        if market == "combined":
            if "TWSE" not in markets or "TPEx" not in markets:
                continue
            a, b = markets["TWSE"], markets["TPEx"]
            row = {"trade_date": day, "market": market, "margin_balance_lots": a["margin_balance_lots"] + b["margin_balance_lots"], "short_balance_lots": a["short_balance_lots"] + b["short_balance_lots"], "margin_previous_lots": a["margin_previous_lots"] + b["margin_previous_lots"] if a["margin_previous_lots"] is not None and b["margin_previous_lots"] is not None else None, "short_previous_lots": a["short_previous_lots"] + b["short_previous_lots"] if a["short_previous_lots"] is not None and b["short_previous_lots"] is not None else None, "margin_balance_thousand_twd": None, "margin_previous_thousand_twd": None, "source_url": None}
        else:
            row = markets.get(market)
            if not row:
                continue
        row = dict(row)
        row["margin_change_lots"] = row["margin_balance_lots"] - row["margin_previous_lots"] if row["margin_previous_lots"] is not None else None
        row["margin_balance_yi_twd"] = round(row["margin_balance_thousand_twd"] / 100000, 4) if row["margin_balance_thousand_twd"] is not None else None
        row["margin_change_yi_twd"] = round((row["margin_balance_thousand_twd"] - row["margin_previous_thousand_twd"]) / 100000, 4) if row["margin_balance_thousand_twd"] is not None and row.get("margin_previous_thousand_twd") is not None else None
        row["short_change_lots"] = row["short_balance_lots"] - row["short_previous_lots"] if row["short_previous_lots"] is not None else None
        row["short_to_margin_pct"] = ratio(row["short_balance_lots"], row["margin_balance_lots"])
        output.append(row)
    for index, row in enumerate(output):
        five = output[index - 5] if index >= 5 else None
        if five and (date.fromisoformat(row["trade_date"]) - date.fromisoformat(five["trade_date"])).days > 14:
            five = None
        row["margin_5d_change_lots"] = row["margin_balance_lots"] - five["margin_balance_lots"] if five else None
        row["margin_5d_change_yi_twd"] = round((row["margin_balance_thousand_twd"] - five["margin_balance_thousand_twd"]) / 100000, 4) if five and row["margin_balance_thousand_twd"] is not None and five["margin_balance_thousand_twd"] is not None else None
        row["short_5d_change_lots"] = row["short_balance_lots"] - five["short_balance_lots"] if five else None
        row["ratio_5d_change_pp"] = round(row["short_to_margin_pct"] - five["short_to_margin_pct"], 4) if five and row["short_to_margin_pct"] is not None and five["short_to_margin_pct"] is not None else None
    return {"market": market, "unit": "張（交易單位）", "ratio_formula": "融券餘額張數 ÷ 融資餘額張數 × 100%", "rows": output, "latest": output[-1] if output else None, "source_status": status, "source_urls": SOURCE_URLS}


def stock_margin_history(stock_id: str, days: int = 370, *, path: str | None = None) -> dict:
    cutoff = (date.today() - timedelta(days=days)).isoformat() if days else "0000-01-01"
    with connect(path) as conn:
        rows = _dicts(conn.execute("SELECT * FROM stock_margin_short_daily WHERE stock_id=? AND trade_date>=? ORDER BY trade_date", (stock_id, cutoff)).fetchall())
    for row in rows:
        row["margin_change_lots"] = row["margin_balance_lots"] - row["margin_previous_lots"] if row["margin_previous_lots"] is not None else None
        row["short_change_lots"] = row["short_balance_lots"] - row["short_previous_lots"] if row["short_previous_lots"] is not None else None
        row["short_to_margin_pct"] = ratio(row["short_balance_lots"], row["margin_balance_lots"])
    return {"stock_id": stock_id, "unit": "張", "rows": rows, "latest": rows[-1] if rows else None, "source_urls": SOURCE_URLS}


def ownership_history(stock_id: str, days: int = 750, *, path: str | None = None) -> dict:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    with connect(path) as conn:
        rows = _dicts(conn.execute("SELECT * FROM stock_ownership_distribution_weekly WHERE stock_id=? AND report_date>=? ORDER BY report_date,tier", (stock_id, cutoff)).fetchall())
    by_date: dict[str, dict[int, dict]] = defaultdict(dict)
    for row in rows:
        by_date[row["report_date"]][row["tier"]] = row
    output = []
    for day, tiers in sorted(by_date.items()):
        if 17 not in tiers:
            continue
        total_shares = tiers[17]["shares"]
        values = {}
        for threshold, grade_range in TIERS.items():
            if not all(grade in tiers for grade in grade_range):
                continue
            shares = sum(tiers[grade]["shares"] for grade in grade_range)
            values[str(threshold)] = {"shares": shares, "lots": shares / 1000, "holders": sum(tiers[grade]["holder_count"] for grade in grade_range), "pct": round(shares / total_shares * 100, 4) if total_shares else None}
        small = None
        if all(grade in tiers for grade in (1, 2, 3)):
            shares = sum(tiers[grade]["shares"] for grade in (1, 2, 3))
            small = {"shares": shares, "holders": sum(tiers[grade]["holder_count"] for grade in (1, 2, 3)), "pct": round(shares / total_shares * 100, 4) if total_shares else None}
        output.append({"report_date": day, "total_shares": total_shares, "large": values, "small_10": small})
    archive_url = next((row["source_url"] for row in rows if row["source_url"].startswith(TDCC_ARCHIVE_RAW)), None)
    return {"stock_id": stock_id, "frequency": "weekly", "thresholds": {str(k): f"{k * 1000 + 1:,} 股以上（逾{k}張）" for k in TIERS}, "rows": output, "latest": output[-1] if output else None, "source_url": SOURCE_URLS["TDCC"], "archive_url": archive_url}
