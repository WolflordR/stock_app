"""Official corporate-action and company-life-cycle evidence, without price adjustment claims."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

import requests

from modules.ownership_research.data import DB_PATH, connect, now_iso

ACTION_ENDPOINTS = {
    "TWSE_EX": "https://www.twse.com.tw/rwd/zh/exRight/TWT49U",
    "TWSE_REDUCTION": "https://www.twse.com.tw/rwd/zh/reducation/TWTAUU",
    "TPEx_EX": "https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ",
    "TPEx_REDUCTION": "https://www.tpex.org.tw/www/zh-tw/bulletin/revivt",
}
CURRENT_COMPANIES = {
    "TWSE": "https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv",
    "TPEx": "https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv",
}
TWSE_DELISTED = "https://www.twse.com.tw/rwd/zh/company/suspendListing"
TPEX_DELISTED = "https://www.tpex.org.tw/www/zh-tw/company/deListed"


def _json(url: str, params: dict[str, object]) -> dict:
    response = requests.get(url, params=params, timeout=25, headers={"User-Agent": "TradeLab/1.0"})
    response.raise_for_status()
    return response.json()


def _csv(url: str) -> str:
    response = requests.get(url, timeout=30, headers={"User-Agent": "TradeLab/1.0"})
    response.raise_for_status()
    return response.content.decode("utf-8-sig")


def parse_official_date(value: object) -> date:
    text = str(value).strip().replace("年", "/").replace("月", "/").replace("日", "")
    parts = [int(v) for v in re.findall(r"\d+", text)]
    if len(parts) == 1 and len(str(parts[0])) in (7, 8):
        digits = str(parts[0])
        parts = [int(digits[:-4]), int(digits[-4:-2]), int(digits[-2:])]
    if len(parts) != 3:
        raise ValueError(f"Unrecognized official date: {value}")
    year, month, day = parts
    return date(year + 1911 if year < 1911 else year, month, day)


def _number(value: object) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "--", "-", "NA", "N/A"}:
        return None
    try:
        result = float(text)
        return result if result >= 0 else None
    except ValueError:
        return None


def _action_rows(key: str, payload: dict, start: date, end: date) -> list[dict]:
    market = "TWSE" if key.startswith("TWSE") else "TPEx"
    if market == "TWSE":
        if (payload.get("stat") != "OK" or payload.get("strDate") != start.strftime("%Y%m%d")
                or payload.get("endDate") != end.strftime("%Y%m%d")):
            raise ValueError(f"TWSE action source status: {payload.get('stat')}")
        fields, data = payload.get("fields", []), payload.get("data", [])
    else:
        if payload.get("stat") != "ok" or payload.get("date") != f"{start:%Y%m%d}~{end:%Y%m%d}":
            raise ValueError("TPEx action response has wrong status/date")
        tables = payload.get("tables") or []
        fields, data = (tables[0].get("fields", []), tables[0].get("data", [])) if tables else ([], [])
    date_col = "資料日期" if key == "TWSE_EX" else "恢復買賣日期" if key.endswith("REDUCTION") else "除權息日期"
    code_col = "股票代號" if market == "TWSE" or key.endswith("REDUCTION") else "代號"
    price_col = ("除權息參考價" if key.endswith("EX") else
                 "恢復買賣參考價" if market == "TWSE" else "減資恢復買賣開始日參考價格")
    previous_col = ("除權息前收盤價" if key.endswith("EX") else
                    "停止買賣前收盤價格" if market == "TWSE" else "最後交易日之收盤價格")
    required = {date_col, code_col, price_col, previous_col}
    if not required.issubset(set(fields)):
        raise ValueError(f"Official action fields changed: missing {sorted(required - set(fields))}")
    result = []
    for values in data:
        item = dict(zip(fields, values))
        code = str(item[code_col]).strip()
        if len(code) != 4 or not code.isdigit():
            continue  # Four-digit ETFs still need the separate company-universe filter.
        ex_date = parse_official_date(item[date_col])
        if not start <= ex_date <= end:
            raise ValueError(f"Official action outside requested interval: {ex_date}")
        reference = _number(item[price_col])
        if reference is None or reference <= 0:
            continue
        if key.endswith("REDUCTION"):
            action_type = "capital_reduction"
        else:
            kind = str(item.get("權/息", ""))
            action_type = "ex_right_dividend" if "權" in kind and "息" in kind else "ex_right" if "權" in kind else "ex_dividend"
        dividend = _number(item.get("現金股利")) if market == "TPEx" else None
        bonus = _number(item.get("每仟股無償配股")) if market == "TPEx" else None
        result.append({"market": market, "stock_id": code, "ex_date": ex_date.isoformat(),
                       "action_type": action_type, "reference_price": reference,
                       "previous_reference_close": _number(item[previous_col]),
                       "cash_dividend": dividend, "stock_dividend_ratio": bonus / 1000 if bonus is not None else None,
                       "raw_json": json.dumps(item, ensure_ascii=False, sort_keys=True)})
    return result


def fetch_action_month(month: date, *, path: Path = DB_PATH,
                       getter: Callable[[str, dict[str, object]], dict] = _json,
                       delay_seconds: float = 0.3) -> dict[str, object]:
    """Save one month of official reference prices, preserving raw rows and source failures."""
    start = month.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    result: dict[str, object] = {"month": start.strftime("%Y-%m"), "sources": {}}
    for key, endpoint in ACTION_ENDPOINTS.items():
        params: dict[str, object] = ({"startDate": start.strftime("%Y%m%d"), "endDate": end.strftime("%Y%m%d"), "response": "json"}
                                     if key.startswith("TWSE") else
                                     {"startDate": start.strftime("%Y/%m/%d"), "endDate": end.strftime("%Y/%m/%d")})
        url = endpoint + "?" + urlencode(params)
        try:
            payload = getter(endpoint, params)
            rows = _action_rows(key, payload, start, end)
            status, error = ("ok", None) if rows else ("empty", "No qualifying four-digit company action")
            digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        except Exception as exc:
            rows, status, error, digest = [], "error", f"{type(exc).__name__}: {exc}", None
        seen_at = now_iso()
        with connect(path) as conn:
            for row in rows:
                conn.execute("""INSERT INTO research_corporate_actions
                    (market,stock_id,ex_date,action_type,cash_dividend,stock_dividend_ratio,reference_price,
                     source_url,published_at,first_seen_at) VALUES (?,?,?,?,?,?,?,?,NULL,?)
                    ON CONFLICT(market,stock_id,ex_date,action_type) DO UPDATE SET
                      cash_dividend=excluded.cash_dividend,stock_dividend_ratio=excluded.stock_dividend_ratio,
                      reference_price=excluded.reference_price,source_url=excluded.source_url""",
                    (row["market"], row["stock_id"], row["ex_date"], row["action_type"],
                     row["cash_dividend"], row["stock_dividend_ratio"], row["reference_price"], url, seen_at))
                conn.execute("""INSERT INTO research_corporate_action_evidence
                    (market,stock_id,ex_date,action_type,previous_reference_close,raw_json,retrieved_at)
                    VALUES (?,?,?,?,?,?,?) ON CONFLICT(market,stock_id,ex_date,action_type) DO UPDATE SET
                      previous_reference_close=excluded.previous_reference_close,raw_json=excluded.raw_json,
                      retrieved_at=excluded.retrieved_at""",
                    (row["market"], row["stock_id"], row["ex_date"], row["action_type"],
                     row["previous_reference_close"], row["raw_json"], seen_at))
            conn.execute("""INSERT INTO research_source_fetches
                (source_key,market,requested_date,source_url,fetched_at,status,row_count,content_sha256,error)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(source_key,market,requested_date) DO UPDATE SET
                  source_url=excluded.source_url,fetched_at=excluded.fetched_at,status=excluded.status,
                  row_count=excluded.row_count,content_sha256=excluded.content_sha256,error=excluded.error""",
                (key, "TWSE" if key.startswith("TWSE") else "TPEx", start.isoformat(),
                 url, seen_at, status, len(rows), digest, error))
            conn.execute("""INSERT INTO research_source_fetch_attempts
                (source_key,market,requested_date,source_url,fetched_at,status,row_count,content_sha256,error)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (key, "TWSE" if key.startswith("TWSE") else "TPEx", start.isoformat(),
                 url, seen_at, status, len(rows), digest, error))
        result["sources"][key] = {"status": status, "rows": len(rows), "error": error}
        if delay_seconds:
            time.sleep(delay_seconds)
    return result


def refresh_company_lifecycle(*, path: Path = DB_PATH, first_year: int = 2016,
                              last_year: int | None = None,
                              get_csv: Callable[[str], str] = _csv,
                              get_json: Callable[[str, dict[str, object]], dict] = _json) -> dict[str, object]:
    """Merge official current company files with delisting registers; old listing starts remain unknown."""
    last_year = last_year or date.today().year
    if not 2001 <= first_year <= last_year <= date.today().year:
        raise ValueError("Choose a bounded historical year range")
    seen = now_iso()
    counts: dict[str, object] = {"current": {}, "delisted": {}, "errors": []}
    for market, url in CURRENT_COMPANIES.items():
        try:
            rows = list(csv.DictReader(io.StringIO(get_csv(url))))
            listing_column = "上市日期" if market == "TWSE" else "上櫃日期"
            if not rows or not {"公司代號", listing_column, "出表日期"}.issubset(rows[0]):
                raise ValueError("Current company CSV fields changed")
            report_day = parse_official_date(rows[0]["出表日期"])
            if (date.today() - report_day).days > 30:
                raise ValueError(f"Current company CSV stale as of {report_day}")
            with connect(path) as conn:
                count = 0
                for row in rows:
                    code = str(row["公司代號"]).strip()
                    if len(code) != 4 or not code.isdigit():
                        continue
                    listed = parse_official_date(row[listing_column]).isoformat() if row.get(listing_column) else None
                    shares = _number(row.get("已發行普通股數或TDR原股發行股數"))
                    conn.execute("""INSERT INTO research_security_lifecycle
                        (market,stock_id,listed_at,name_zh,security_type,issued_common_shares,listing_source_url,first_seen_at,validation_status)
                        VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(market,stock_id) DO UPDATE SET
                          listed_at=COALESCE(excluded.listed_at,research_security_lifecycle.listed_at),
                          name_zh=excluded.name_zh,issued_common_shares=excluded.issued_common_shares,
                          listing_source_url=excluded.listing_source_url""",
                        (market, code, listed, row.get("公司簡稱") or row.get("公司名稱"),
                         "ordinary_company_candidate", int(shares) if shares is not None else None,
                         url, seen, "current_snapshot"))
                    count += 1
            counts["current"][market] = count
        except Exception as exc:
            counts["errors"].append(f"{market} current: {type(exc).__name__}: {exc}")
    try:
        payload = get_json(TWSE_DELISTED, {"response": "json"})
        if payload.get("status") != "ok" or not {"終止上市日期", "上市編號"}.issubset(payload.get("fields", [])):
            raise ValueError("TWSE delisting schema changed")
        with connect(path) as conn:
            n = 0
            for row in payload["data"]:
                day, name, code = row[:3]
                if len(str(code)) != 4 or not str(code).isdigit():
                    continue
                delisted = parse_official_date(day).isoformat()
                conn.execute("""INSERT INTO research_security_delisting_events
                    (market,stock_id,delisted_at,name_zh,source_url,first_seen_at)
                    VALUES ('TWSE',?,?,?,?,?) ON CONFLICT(market,stock_id,delisted_at) DO UPDATE SET
                    name_zh=excluded.name_zh,source_url=excluded.source_url""",
                    (str(code), delisted, name, TWSE_DELISTED, seen))
                conn.execute("""INSERT INTO research_security_lifecycle
                    (market,stock_id,delisted_at,name_zh,delisting_source_url,first_seen_at)
                    VALUES ('TWSE',?,?,?,?,?) ON CONFLICT(market,stock_id) DO UPDATE SET
                    delisted_at=CASE WHEN research_security_lifecycle.listing_source_url IS NULL THEN excluded.delisted_at ELSE NULL END,
                    delisting_source_url=CASE WHEN research_security_lifecycle.listing_source_url IS NULL THEN excluded.delisting_source_url ELSE NULL END,
                    validation_status=CASE WHEN research_security_lifecycle.listing_source_url IS NOT NULL
                      THEN 'code_reuse_conflict' ELSE research_security_lifecycle.validation_status END""",
                    (str(code), delisted, name, TWSE_DELISTED, seen))
                n += 1
            counts["delisted"]["TWSE"] = n
    except Exception as exc:
        counts["errors"].append(f"TWSE delisted: {type(exc).__name__}: {exc}")
    otc_count = 0
    for year in range(first_year, last_year + 1):
        try:
            params: dict[str, object] = {"date": str(year), "reason": "-1", "code": ""}
            payload = get_json(TPEX_DELISTED, params)
            tables = payload.get("tables") or []
            if payload.get("stat") != "ok" or not tables or payload.get("date") != str(year):
                raise ValueError("TPEx delisting status/date changed")
            table = tables[0]
            if not {"股票代號", "終止上櫃日期"}.issubset(table.get("fields", [])):
                raise ValueError("TPEx delisting fields changed")
            with connect(path) as conn:
                for values in table.get("data", []):
                    row = dict(zip(table["fields"], values))
                    code = str(row["股票代號"]).strip()
                    if len(code) != 4 or not code.isdigit():
                        continue
                    delisted = parse_official_date(row["終止上櫃日期"]).isoformat()
                    source_url = TPEX_DELISTED + "?" + urlencode(params)
                    conn.execute("""INSERT INTO research_security_delisting_events
                        (market,stock_id,delisted_at,name_zh,source_url,first_seen_at)
                        VALUES ('TPEx',?,?,?,?,?) ON CONFLICT(market,stock_id,delisted_at) DO UPDATE SET
                        name_zh=excluded.name_zh,source_url=excluded.source_url""",
                        (code, delisted, row.get("公司名稱"), source_url, seen))
                    conn.execute("""INSERT INTO research_security_lifecycle
                        (market,stock_id,delisted_at,name_zh,delisting_source_url,first_seen_at)
                        VALUES ('TPEx',?,?,?,?,?) ON CONFLICT(market,stock_id) DO UPDATE SET
                        delisted_at=CASE WHEN research_security_lifecycle.listing_source_url IS NULL THEN excluded.delisted_at ELSE NULL END,
                        delisting_source_url=CASE WHEN research_security_lifecycle.listing_source_url IS NULL THEN excluded.delisting_source_url ELSE NULL END,
                        validation_status=CASE WHEN research_security_lifecycle.listing_source_url IS NOT NULL
                          THEN 'code_reuse_conflict' ELSE research_security_lifecycle.validation_status END""",
                        (code, delisted, row.get("公司名稱"), source_url, seen))
                    otc_count += 1
        except Exception as exc:
            counts["errors"].append(f"TPEx {year} delisted: {type(exc).__name__}: {exc}")
    counts["delisted"]["TPEx"] = otc_count
    return counts
