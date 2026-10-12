"""Official quarterly income statement and valuation history for stock pages.

MOPS income statements are year-to-date. Single-quarter EPS and gross margin
are derived only when the preceding quarter of the same year is available.
The period is an accounting period, not a verified publication timestamp.
"""
from __future__ import annotations

import io
import math
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd

from modules.core.http_utils import request_json, request_text
from modules.core.project_paths import db_path


DB_PATH = db_path("financial_eps.db")
MOPS_MARKETS = {"TWSE": "sii", "TPEx": "otc"}
MOPS_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t163sb04"
TWSE_INFOHUB_URL = "https://wwwc.twse.com.tw/rwd/zh/IIH/company/financial"
TPEX_PE_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate"


def _connect(path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS stock_income_quarterly (
        market TEXT NOT NULL, code TEXT NOT NULL, report_year INTEGER NOT NULL,
        report_quarter INTEGER NOT NULL, revenue_ytd REAL, gross_profit_ytd REAL,
        basic_eps_ytd REAL, source_url TEXT NOT NULL, first_observed_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (market, code, report_year, report_quarter)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_income_stock_latest
        ON stock_income_quarterly(market, code, report_year DESC, report_quarter DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS income_refresh_state (
        market TEXT NOT NULL, report_year INTEGER NOT NULL, report_quarter INTEGER NOT NULL,
        last_attempt_at TEXT NOT NULL, last_success_at TEXT, row_count INTEGER,
        error TEXT, PRIMARY KEY (market, report_year, report_quarter)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS stock_pe_history (
        market TEXT NOT NULL, code TEXT NOT NULL, data_date TEXT NOT NULL,
        pe_ratio REAL, source_url TEXT NOT NULL, checked_at TEXT NOT NULL,
        PRIMARY KEY (market, code, data_date)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_pe_stock_latest
        ON stock_pe_history(market, code, data_date DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS pe_refresh_state (
        market TEXT NOT NULL, code TEXT NOT NULL, last_attempt_at TEXT NOT NULL,
        last_success_at TEXT, error TEXT, PRIMARY KEY (market, code)
    )""")
    return conn


def _number(value: object) -> float | None:
    text = str("" if value is None else value).strip().replace(",", "")
    if not text or text in {"--", "-", "—", "nan", "None", "N/A"}:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        result = float(text)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _mops_url(market: str, year: int, quarter: int) -> str:
    return (f"{MOPS_URL}?step=1&firstin=1&TYPEK={MOPS_MARKETS[market]}"
            f"&year={year - 1911}&season={quarter:02d}")


def parse_mops_income_html(html: str, market: str, year: int, quarter: int, source_url: str) -> list[dict]:
    if "FOR SECURITY REASONS" in html or "無法呈現" in html and len(html) < 5000:
        raise ValueError("MOPS rejected historical income statement request")
    rows: list[dict] = []
    try:
        tables = pd.read_html(io.StringIO(html), flavor="lxml")
    except ValueError as exc:
        raise ValueError("MOPS income statement tables missing") from exc
    for table in tables:
        columns = {re.sub(r"\s+", "", str(col)): col for col in table.columns}
        code_col = columns.get("公司代號")
        eps_col = next((value for name, value in columns.items() if name.startswith("基本每股盈餘")), None)
        if code_col is None or eps_col is None:
            continue
        revenue_col = columns.get("營業收入")
        gross_col = columns.get("營業毛利（毛損）淨額") or columns.get("營業毛利（毛損）")
        for item in table.to_dict("records"):
            code = str(item[code_col]).strip()
            if not re.fullmatch(r"\d{4}", code):
                continue
            rows.append({
                "market": market, "code": code, "report_year": year,
                "report_quarter": quarter,
                "revenue_ytd": _number(item.get(revenue_col)) if revenue_col else None,
                "gross_profit_ytd": _number(item.get(gross_col)) if gross_col else None,
                "basic_eps_ytd": _number(item.get(eps_col)),
                "source_url": source_url,
            })
    if not rows:
        raise ValueError("MOPS income statement has no reported companies yet")
    return rows


def _periods(today: date, count: int) -> list[tuple[int, int]]:
    year, quarter = today.year, (today.month - 1) // 3
    if quarter == 0:
        year, quarter = year - 1, 4
    out = []
    for _ in range(count):
        out.append((year, quarter))
        quarter -= 1
        if quarter == 0:
            year, quarter = year - 1, 4
    return out


def refresh_financial_history(*, path: str | Path = DB_PATH, lookback_quarters: int = 7,
                              max_requests: int | None = None, recent_quarters: int = 2,
                              today: date | None = None) -> dict:
    """Resume by market/quarter; retry recent partial filings daily, older ones once."""
    today = today or date.today()
    now = datetime.now().isoformat(timespec="seconds")
    requests_made = 0
    imported = 0
    errors: list[str] = []
    with _connect(path) as conn:
        plan = [(market, year, quarter, index < recent_quarters)
                for index, (year, quarter) in enumerate(_periods(today, lookback_quarters))
                for market in MOPS_MARKETS]
        for market, year, quarter, recent in plan:
            state = conn.execute("""SELECT last_success_at FROM income_refresh_state
                WHERE market=? AND report_year=? AND report_quarter=?""", (market, year, quarter)).fetchone()
            if state and state["last_success_at"] and (not recent or state["last_success_at"][:10] == today.isoformat()):
                continue
            if max_requests is not None and requests_made >= max_requests:
                break
            requests_made += 1
            url = _mops_url(market, year, quarter)
            try:
                html = request_text(url, timeout=35)
                rows = parse_mops_income_html(html, market, year, quarter, url)
                conn.executemany("""INSERT INTO stock_income_quarterly
                    (market, code, report_year, report_quarter, revenue_ytd, gross_profit_ytd,
                     basic_eps_ytd, source_url, first_observed_at, updated_at)
                    VALUES (:market, :code, :report_year, :report_quarter, :revenue_ytd,
                     :gross_profit_ytd, :basic_eps_ytd, :source_url, :now, :now)
                    ON CONFLICT(market, code, report_year, report_quarter) DO UPDATE SET
                    revenue_ytd=COALESCE(excluded.revenue_ytd,stock_income_quarterly.revenue_ytd),
                    gross_profit_ytd=COALESCE(excluded.gross_profit_ytd,stock_income_quarterly.gross_profit_ytd),
                    basic_eps_ytd=COALESCE(excluded.basic_eps_ytd,stock_income_quarterly.basic_eps_ytd),
                    source_url=excluded.source_url,
                    updated_at=excluded.updated_at""", [{**row, "now": now} for row in rows])
                conn.execute("""INSERT INTO income_refresh_state VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(market,report_year,report_quarter) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at,last_success_at=excluded.last_success_at,
                    row_count=excluded.row_count,error=NULL""",
                    (market, year, quarter, now, now, len(rows), None))
                imported += len(rows)
            except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
                errors.append(f"{market} {year}Q{quarter}: {exc}")
                conn.execute("""INSERT INTO income_refresh_state VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(market,report_year,report_quarter) DO UPDATE SET
                    last_attempt_at=excluded.last_attempt_at,error=excluded.error""",
                    (market, year, quarter, now, None, None, str(exc)))
            conn.commit()
    return {"requests": requests_made, "rows": imported, "errors": errors}


def _parse_twse_pe(payload: dict, code: str, checked_at: str) -> list[dict]:
    if payload.get("info", {}).get("status") != "success" or str(payload["info"]["data"].get("code")) != code:
        raise ValueError("TWSE InfoHub stock response invalid")
    chart = payload.get("chart", {}).get("pe", {})
    months = chart.get("categories", [])
    values = chart.get("series", [{}])[0].get("data", [])
    if not months or len(months) != len(values):
        raise ValueError("TWSE InfoHub PE history missing")
    url = f"{TWSE_INFOHUB_URL}?code={quote(code)}"
    return [{"market": "TWSE", "code": code, "data_date": f"{month[:4]}-{month[4:6]}-01",
             "pe_ratio": _number(value), "source_url": url, "checked_at": checked_at}
            for month, value in zip(months, values) if re.fullmatch(r"\d{6}", str(month))]


def _parse_tpex_pe(payload: dict, code: str, requested: date, checked_at: str) -> dict | None:
    tables = payload.get("tables") or []
    if not tables:
        raise ValueError("TPEx PE table missing")
    table = tables[0]
    fields = table.get("fields") or []
    if "股票代號" not in fields or "本益比" not in fields:
        raise ValueError("TPEx PE columns changed")
    reported_date = str(table.get("date") or "")
    expected_date = f"{requested.year - 1911}/{requested.month:02d}/{requested.day:02d}"
    if reported_date != expected_date:
        return None
    code_index, pe_index = fields.index("股票代號"), fields.index("本益比")
    match = next((row for row in table.get("data", []) if str(row[code_index]).strip() == code), None)
    if match is None:
        return None
    return {"market": "TPEx", "code": code, "data_date": requested.isoformat(),
            "pe_ratio": _number(match[pe_index]),
            "source_url": f"{TPEX_PE_URL}?date={quote(expected_date)}&cate=",
            "checked_at": checked_at}


def _quarter_end(year: int, quarter: int) -> date:
    month = quarter * 3
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    result = next_month - timedelta(days=1)
    while result.weekday() >= 5:
        result -= timedelta(days=1)
    return result


def refresh_stock_pe(code: str, market: str, *, path: str | Path = DB_PATH,
                     today: date | None = None) -> dict:
    """Fetch only on cache miss; a source outage keeps stored history intact."""
    if market not in MOPS_MARKETS or not re.fullmatch(r"\d{4}", str(code)):
        raise ValueError("invalid market or stock code")
    today = today or date.today()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect(path) as conn:
        state = conn.execute("SELECT last_attempt_at FROM pe_refresh_state WHERE market=? AND code=?",
                             (market, code)).fetchone()
        if state and state["last_attempt_at"][:10] == today.isoformat():
            return {"cached": True, "rows": 0}
        try:
            if market == "TWSE":
                payload = request_json(f"{TWSE_INFOHUB_URL}?code={quote(code)}", timeout=20)
                rows = _parse_twse_pe(payload, code, now)
            else:
                rows = []
                for year, quarter in _periods(today, 5):
                    trade_day = _quarter_end(year, quarter)
                    url = f"{TPEX_PE_URL}?date={quote(f'{trade_day.year - 1911}/{trade_day.month:02d}/{trade_day.day:02d}')}&cate="
                    row = _parse_tpex_pe(request_json(url, timeout=20), code, trade_day, now)
                    if row:
                        rows.append(row)
            if not rows:
                raise ValueError("no verified PE rows returned")
            conn.executemany("""INSERT INTO stock_pe_history VALUES
                (:market,:code,:data_date,:pe_ratio,:source_url,:checked_at)
                ON CONFLICT(market,code,data_date) DO UPDATE SET
                pe_ratio=excluded.pe_ratio,source_url=excluded.source_url,
                checked_at=excluded.checked_at""", rows)
            conn.execute("""INSERT INTO pe_refresh_state VALUES (?,?,?,?,?)
                ON CONFLICT(market,code) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,
                last_success_at=excluded.last_success_at,error=NULL""",
                (market, code, now, now, None))
            conn.commit()
            return {"cached": False, "rows": len(rows)}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            conn.execute("""INSERT INTO pe_refresh_state VALUES (?,?,?,?,?)
                ON CONFLICT(market,code) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,
                error=excluded.error""", (market, code, now, None, str(exc)))
            conn.commit()
            return {"cached": False, "rows": 0, "error": str(exc)}


def get_stock_financial_trends(code: str, market: str, *, path: str | Path = DB_PATH,
                               refresh_pe: bool = True, today: date | None = None) -> dict:
    if market not in MOPS_MARKETS or not re.fullmatch(r"\d{4}", str(code)):
        return {"quarters": [], "pe_history": [], "source_error": "invalid stock"}
    if refresh_pe:
        refresh_stock_pe(code, market, path=path, today=today)
    with _connect(path) as conn:
        income = [dict(row) for row in conn.execute("""SELECT * FROM stock_income_quarterly
            WHERE market=? AND code=? ORDER BY report_year DESC,report_quarter DESC LIMIT 9""",
            (market, code)).fetchall()]
        pe = [dict(row) for row in conn.execute("""SELECT data_date,pe_ratio,source_url
            FROM stock_pe_history WHERE market=? AND code=? ORDER BY data_date DESC LIMIT 18""",
            (market, code)).fetchall()]
        state = conn.execute("SELECT error FROM pe_refresh_state WHERE market=? AND code=?",
                             (market, code)).fetchone()
    by_period = {(row["report_year"], row["report_quarter"]): row for row in income}
    quarters = []
    for row in income[:4]:
        year, quarter = row["report_year"], row["report_quarter"]
        prev = by_period.get((year, quarter - 1)) if quarter > 1 else None
        eps = row["basic_eps_ytd"] if quarter == 1 else (
            row["basic_eps_ytd"] - prev["basic_eps_ytd"]
            if prev and row["basic_eps_ytd"] is not None and prev["basic_eps_ytd"] is not None else None)
        revenue = row["revenue_ytd"] if quarter == 1 else (
            row["revenue_ytd"] - prev["revenue_ytd"]
            if prev and row["revenue_ytd"] is not None and prev["revenue_ytd"] is not None else None)
        gross = row["gross_profit_ytd"] if quarter == 1 else (
            row["gross_profit_ytd"] - prev["gross_profit_ytd"]
            if prev and row["gross_profit_ytd"] is not None and prev["gross_profit_ytd"] is not None else None)
        pe_rows = [item for item in pe if item["data_date"][:7] == f"{year}-{quarter * 3:02d}"]
        quarters.append({"period": f"{year} Q{quarter}", "report_year": year,
                         "report_quarter": quarter,
                         "eps_single_quarter": round(eps, 4) if eps is not None else None,
                         "gross_margin_pct": round(100 * gross / revenue, 2)
                         if revenue is not None and revenue > 0 and gross is not None else None,
                         "pe_ratio_quarter_end": pe_rows[0]["pe_ratio"] if pe_rows else None,
                         "pe_data_date": pe_rows[0]["data_date"] if pe_rows else None,
                         "source_url": row["source_url"]})
    return {"quarters": list(reversed(quarters)), "pe_history": list(reversed(pe)),
            "source_error": state["error"] if state and state["error"] else None,
            "income_source": "MOPS 官方綜合損益表（歷史季報）",
            "pe_source": "TWSE 投資資訊中心" if market == "TWSE" else "TPEx 個股本益比",
            "note": "單季 EPS 與毛利率由年初累計財報相減；本益比採季末月份或交易日官方數值。季別不是實際公布日。"}
