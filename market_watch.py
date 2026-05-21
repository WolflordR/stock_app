from __future__ import annotations

from datetime import date, datetime, timedelta
import json
import re
import urllib.parse

import pandas as pd

from http_utils import request_text


def _request_text(url):
    return request_text(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
        },
        encoding="utf-8",
    )


def _request_json(url):
    return json.loads(_request_text(url))


def _to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _to_yyyymmdd(value):
    return _to_date(value).strftime("%Y%m%d")


def _to_roc_date(value):
    current_date = _to_date(value)
    roc_year = current_date.year - 1911
    return f"{roc_year:03d}/{current_date.month:02d}/{current_date.day:02d}"


def _roc_compact_to_iso(value):
    raw = str(value or "").strip()
    if len(raw) < 7 or not raw.isdigit():
        return ""
    roc_year = int(raw[:3])
    month = int(raw[3:5])
    day = int(raw[5:7])
    return f"{roc_year + 1911:04d}-{month:02d}-{day:02d}"


def _clean_number(value):
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "--", "---", "----", "除權息", "除息", "除權"}:
        return None
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace(",", "").replace("X", "").replace("null", "")
    if text in {"", "-", "+"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean_text(value):
    if value is None:
        return ""
    return re.sub(r"<[^>]+>", "", str(value)).strip()


def _extract_name(value):
    text = _clean_text(value)
    return re.sub(r"\(.*\)$", "", text).strip()


def _extract_twse_sign(value):
    text = _clean_text(value)
    if "+" in text:
        return 1
    if "-" in text:
        return -1
    return 0


def _signed_change(sign_value, diff_value):
    diff = _clean_number(diff_value)
    if diff is None:
        return 0.0
    sign = _extract_twse_sign(sign_value)
    if sign < 0:
        return -abs(diff)
    if sign > 0:
        return abs(diff)
    return float(diff)


def _build_quote_metrics(quotes_df):
    if quotes_df.empty:
        return quotes_df

    result_df = quotes_df.copy()
    result_df["prev_close"] = result_df["close"] - result_df["change_value"]
    valid_prev_close = result_df["prev_close"].replace(0, pd.NA)
    result_df["change_pct"] = (result_df["change_value"] / valid_prev_close) * 100
    result_df["limit_up"] = (result_df["change_pct"] >= 9.5) & (result_df["close"] >= result_df["high"])
    result_df["limit_down"] = (result_df["change_pct"] <= -9.5) & (result_df["close"] <= result_df["low"])
    result_df["locked_limit_up"] = (
        result_df["limit_up"]
        & (result_df["last_bid_price"].fillna(0) == result_df["close"])
        & (result_df["last_ask_price"].isna() | (result_df["last_ask_price"].fillna(0) == 0))
    )
    result_df["locked_limit_down"] = (
        result_df["limit_down"]
        & (result_df["last_ask_price"].fillna(0) == result_df["close"])
        & (result_df["last_bid_price"].isna() | (result_df["last_bid_price"].fillna(0) == 0))
    )
    return result_df


def fetch_twse_daily_quotes(trade_date):
    formatted_date = _to_yyyymmdd(trade_date)
    url = (
        "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?"
        + urllib.parse.urlencode(
            {
                "date": formatted_date,
                "type": "ALLBUT0999",
                "response": "json",
            }
        )
    )
    try:
        payload = _request_json(url)
    except Exception:
        payload = None

    if not payload:
        latest_df = _fetch_twse_latest_quotes_from_openapi()
        requested_date = _to_date(trade_date).strftime("%Y-%m-%d")
        if latest_df.empty or latest_df.attrs.get("source_date") != requested_date:
            return pd.DataFrame()
        return latest_df.copy()

    if payload.get("stat") != "OK":
        return pd.DataFrame()

    quote_table = next(
        (
            table
            for table in payload.get("tables", [])
            if table.get("title") and "每日收盤行情" in table.get("title")
        ),
        None,
    )
    if not quote_table:
        return pd.DataFrame()

    fields = quote_table.get("fields", [])
    rows = quote_table.get("data", [])
    source_df = pd.DataFrame(rows, columns=fields)
    source_df = source_df[source_df["證券代號"].astype(str).str.fullmatch(r"\d{4}")].copy()

    normalized_df = pd.DataFrame(
        {
            "market": "上市",
            "code": source_df["證券代號"].astype(str).str.strip(),
            "name": source_df["證券名稱"].map(_extract_name),
            "close": source_df["收盤價"].map(_clean_number),
            "open": source_df["開盤價"].map(_clean_number),
            "high": source_df["最高價"].map(_clean_number),
            "low": source_df["最低價"].map(_clean_number),
            "volume": source_df["成交股數"].map(_clean_number),
            "trades": source_df["成交筆數"].map(_clean_number),
            "last_bid_price": source_df["最後揭示買價"].map(_clean_number),
            "last_bid_volume": source_df["最後揭示買量"].map(_clean_number),
            "last_ask_price": source_df["最後揭示賣價"].map(_clean_number),
            "last_ask_volume": source_df["最後揭示賣量"].map(_clean_number),
            "change_value": [
                _signed_change(sign_value, diff_value)
                for sign_value, diff_value in zip(source_df["漲跌(+/-)"], source_df["漲跌價差"])
            ],
        }
    )
    return _build_quote_metrics(normalized_df).dropna(subset=["close"])


def _fetch_twse_latest_quotes_from_openapi():
    rows = _request_json("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
    source_df = pd.DataFrame(rows)
    if source_df.empty:
        return pd.DataFrame()

    source_df = source_df[source_df["Code"].astype(str).str.fullmatch(r"\d{4}")].copy()
    normalized_df = pd.DataFrame(
        {
            "market": "上市",
            "code": source_df["Code"].astype(str).str.strip(),
            "name": source_df["Name"].map(_extract_name),
            "close": source_df["ClosingPrice"].map(_clean_number),
            "open": source_df["OpeningPrice"].map(_clean_number),
            "high": source_df["HighestPrice"].map(_clean_number),
            "low": source_df["LowestPrice"].map(_clean_number),
            "volume": source_df["TradeVolume"].map(_clean_number),
            "trades": source_df["Transaction"].map(_clean_number),
            "last_bid_price": None,
            "last_bid_volume": None,
            "last_ask_price": None,
            "last_ask_volume": None,
            "change_value": source_df["Change"].map(_clean_number),
        }
    )
    normalized_df = _build_quote_metrics(normalized_df).dropna(subset=["close"])
    normalized_df.attrs["source_date"] = _roc_compact_to_iso(source_df["Date"].iloc[0])
    return normalized_df


def fetch_tpex_daily_quotes(trade_date):
    roc_date = _to_roc_date(trade_date)
    url = (
        "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php?"
        + urllib.parse.urlencode(
            {
                "l": "zh-tw",
                "o": "json",
                "d": roc_date,
                "se": "EW",
            }
        )
    )
    try:
        payload = _request_json(url)
    except Exception:
        return pd.DataFrame()
    table = payload.get("tables", [{}])[0]
    fields = table.get("fields", [])
    rows = table.get("data", [])
    if not fields or not rows:
        return pd.DataFrame()

    source_df = pd.DataFrame(rows, columns=fields)
    source_df = source_df[source_df["代號"].astype(str).str.fullmatch(r"\d{4}")].copy()

    normalized_df = pd.DataFrame(
        {
            "market": "上櫃",
            "code": source_df["代號"].astype(str).str.strip(),
            "name": source_df["名稱"].map(_extract_name),
            "close": source_df["收盤 "].map(_clean_number),
            "open": source_df["開盤 "].map(_clean_number),
            "high": source_df["最高 "].map(_clean_number),
            "low": source_df["最低"].map(_clean_number),
            "volume": source_df["成交股數  "].map(_clean_number),
            "trades": source_df[" 成交筆數 "].map(_clean_number),
            "last_bid_price": source_df["最後買價"].map(_clean_number),
            "last_bid_volume": source_df["最後買量<br>(張數)"].map(_clean_number),
            "last_ask_price": source_df["最後賣價"].map(_clean_number),
            "last_ask_volume": source_df["最後賣量<br>(張數)"].map(_clean_number),
            "change_value": source_df["漲跌"].map(_clean_number),
        }
    )
    return _build_quote_metrics(normalized_df).dropna(subset=["close"])


def _find_recent_quotes(anchor_date, max_lookback_days=7):
    current_date = _to_date(anchor_date)
    for offset in range(max_lookback_days + 1):
        probe_date = current_date - timedelta(days=offset)
        listed_df = fetch_twse_daily_quotes(probe_date)
        otc_df = fetch_tpex_daily_quotes(probe_date)
        if listed_df.empty or otc_df.empty:
            continue
        combined_df = pd.concat([listed_df, otc_df], ignore_index=True)
        if not combined_df.empty:
            return probe_date, combined_df
    return current_date, pd.DataFrame()


def load_recent_market_quotes(anchor_date, max_lookback_days=7):
    """往前找最近一個有完整上市/上櫃行情的交易日，供首頁與分析頁共用。"""
    return _find_recent_quotes(anchor_date, max_lookback_days=max_lookback_days)


def build_market_watchlists(anchor_date, top_n=30):
    used_date, quotes_df = load_recent_market_quotes(anchor_date)
    if quotes_df.empty:
        return None

    display_columns = ["market", "code", "name", "close", "change_pct", "volume", "trades"]
    limit_up_df = quotes_df[quotes_df["limit_up"]].sort_values(["change_pct", "volume"], ascending=[False, False])
    limit_down_df = quotes_df[quotes_df["limit_down"]].sort_values(["change_pct", "volume"], ascending=[True, False])
    locked_up_df = quotes_df[quotes_df["locked_limit_up"]].sort_values(["change_pct", "volume"], ascending=[False, False])
    locked_down_df = quotes_df[quotes_df["locked_limit_down"]].sort_values(["change_pct", "volume"], ascending=[True, False])

    return {
        "used_date": used_date.strftime("%Y-%m-%d"),
        "quotes_count": len(quotes_df),
        "limit_up_count": len(limit_up_df),
        "limit_down_count": len(limit_down_df),
        "locked_limit_up_count": len(locked_up_df),
        "locked_limit_down_count": len(locked_down_df),
        "limit_up_df": limit_up_df[display_columns].head(top_n).reset_index(drop=True),
        "limit_down_df": limit_down_df[display_columns].head(top_n).reset_index(drop=True),
        "locked_limit_up_df": locked_up_df[display_columns].head(top_n).reset_index(drop=True),
        "locked_limit_down_df": locked_down_df[display_columns].head(top_n).reset_index(drop=True),
    }


def fetch_twse_disposition():
    try:
        payload = _request_json("https://www.twse.com.tw/rwd/zh/announcement/punish?response=json")
    except Exception:
        return pd.DataFrame()
    rows = payload.get("data", [])
    if not rows:
        return pd.DataFrame()

    source_df = pd.DataFrame(rows, columns=payload.get("fields", []))
    return pd.DataFrame(
        {
            "market": "上市",
            "code": source_df["證券代號"].astype(str).str.strip(),
            "name": source_df["證券名稱"].map(_extract_name),
            "公布日期": source_df["公布日期"].map(_clean_text),
            "累計": source_df["累計"].map(_clean_number),
            "處置起訖時間": source_df["處置起迄時間"].map(_clean_text),
            "處置原因": source_df["處置條件"].map(_clean_text),
            "處置內容": source_df["處置措施"].map(_clean_text),
        }
    )


def fetch_tpex_disposition(anchor_date):
    roc_date = _to_roc_date(anchor_date)
    url = (
        "https://www.tpex.org.tw/web/bulletin/disposal_information/disposal_information_result.php?"
        + urllib.parse.urlencode(
            {
                "l": "zh-tw",
                "o": "json",
                "d": roc_date,
                "sd": roc_date,
                "ed": roc_date,
            }
        )
    )
    try:
        payload = _request_json(url)
    except Exception:
        return pd.DataFrame()
    tables = payload.get("tables", [])
    if not tables:
        return pd.DataFrame()

    table = tables[0]
    fields = table.get("fields", [])
    rows = table.get("data", [])
    if not rows:
        return pd.DataFrame()

    source_df = pd.DataFrame(rows, columns=fields)
    return pd.DataFrame(
        {
            "market": "上櫃",
            "code": source_df["證券代號"].astype(str).str.extract(r"(\d+)")[0].fillna(""),
            "name": source_df["證券名稱"].map(_extract_name),
            "公布日期": source_df["公布日期"].map(_clean_text),
            "累計": source_df["累計"].map(_clean_number),
            "處置起訖時間": source_df["處置起訖時間"].map(_clean_text),
            "處置原因": source_df["處置原因"].map(_clean_text),
            "處置內容": source_df["處置內容"].map(_clean_text),
        }
    )


def build_disposition_watchlist(anchor_date):
    listed_df = fetch_twse_disposition()
    otc_df = fetch_tpex_disposition(anchor_date)
    combined_df = pd.concat([listed_df, otc_df], ignore_index=True)
    if combined_df.empty:
        return None

    combined_df = combined_df[combined_df["code"].astype(str).str.fullmatch(r"\d{4}")].copy()
    combined_df["累計"] = combined_df["累計"].fillna(0).astype(int)
    combined_df = combined_df.sort_values(["公布日期", "market", "code"], ascending=[False, True, True]).reset_index(drop=True)
    return {
        "count": len(combined_df),
        "df": combined_df,
    }
