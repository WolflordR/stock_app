from __future__ import annotations

import json
import re
from datetime import date, timedelta
from functools import lru_cache
from requests import HTTPError

import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup

from active_etf_history_store import load_etf_change_snapshot_summaries
from active_etf_history_store import load_etf_change_refresh_state
from active_etf_history_store import persist_etf_change_snapshot
from active_etf_history_store import upsert_etf_change_refresh_state
from industry_utils import fill_missing_industry


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ETFINFO_ACTIVE_URL = "https://www.etfinfo.tw/active"
ETFINFO_ETF_ACTIVE_URL = "https://www.etfinfo.tw/etf/{code}/active"
TWSE_ETF_INFO_URL = "https://www.twse.com.tw/zh/ETFortune/etfInfo/{code}"
GOALSTAR_FUND_INFO_URL = "https://goal-star.com/api/funds/{code}"
GOALSTAR_FUND_SHARES_URL = "https://goal-star.com/api/funds/{code}/shares"
GOALSTAR_FUND_STOCK_HISTORY_URL = "https://goal-star.com/api/funds/{code}/shares/{stock_symbol}"

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/json,*/*;q=0.8",
}

GOALSTAR_STATUS_TO_LABEL = {
    "new": "新增",
    "clear": "刪除",
    "increase": "加碼",
    "decrease": "減碼",
    "unchanged": "持平",
}


def _fetch_text(url, *, verify=True):
    response = requests.get(
        url,
        headers=REQUEST_HEADERS,
        timeout=30,
        verify=verify,
    )
    response.raise_for_status()
    return response.text


def _fetch_json(url, *, verify=True):
    response = requests.get(
        url,
        headers=REQUEST_HEADERS,
        timeout=30,
        verify=verify,
    )
    response.raise_for_status()
    return response.json()


def _fetch_json_with_params(url, params=None, *, verify=True):
    response = requests.get(
        url,
        headers=REQUEST_HEADERS,
        timeout=30,
        verify=verify,
        params=params or None,
    )
    response.raise_for_status()
    return response.json()


def _decode_nuxt_ref(payload, index):
    return _decode_nuxt_value(payload, payload[index], from_ref=True)


def _decode_nuxt_value(payload, value, *, from_ref=False):
    if isinstance(value, int) and not from_ref:
        if 0 <= value < len(payload):
            return _decode_nuxt_ref(payload, value)
        return value
    if isinstance(value, list):
        if value and isinstance(value[0], str) and value[0] in {"ShallowReactive", "Reactive", "ShallowRef", "Ref"}:
            if len(value) >= 2:
                return _decode_nuxt_value(payload, value[1], from_ref=False)
            return None
        return [_decode_nuxt_value(payload, item, from_ref=False) for item in value]
    if isinstance(value, dict):
        return {key: _decode_nuxt_value(payload, item, from_ref=False) for key, item in value.items()}
    return value


def _extract_payload_url(html, pattern):
    match = re.search(pattern, html)
    if not match:
        raise ValueError("找不到 payload 資料來源")
    return "https://www.etfinfo.tw" + match.group(1)


def _extract_nuxt_data_payload(html):
    match = re.search(
        r'<script type="application/json" data-nuxt-data="nuxt-app" data-ssr="true" id="__NUXT_DATA__">(.*?)</script>',
        html,
        re.S,
    )
    if not match:
        raise ValueError("找不到 __NUXT_DATA__")
    return json.loads(match.group(1))


def _find_nuxt_root(payload, required_keys):
    for item in payload[:16]:
        if isinstance(item, dict) and all(key in item for key in required_keys):
            return item
    raise ValueError(f"找不到 Nuxt root keys: {required_keys}")


def _to_float(value):
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) else None


def _to_int(value):
    numeric = pd.to_numeric(value, errors="coerce")
    return int(numeric) if pd.notna(numeric) else None


def _format_pct(value):
    return "-" if value is None or pd.isna(value) else f"{value:.2f}%"


def _format_amount_100m(value):
    return "-" if value is None or pd.isna(value) else f"{value:,.1f}"


def _format_people_10k(value):
    return "-" if value is None or pd.isna(value) else f"{value:,.2f}"


def _format_shares(value):
    return "-" if value is None or pd.isna(value) else f"{int(round(value)):,}"


def _format_lots(value):
    return "-" if value is None or pd.isna(value) else f"{value / 1000:,.1f}"


def _format_amount_ntd_100m(value):
    return "-" if value is None or pd.isna(value) else f"{value / 100000000:,.2f}"


def _classify_change_type(change_row):
    new_weight = _to_float(change_row.get("newWeight"))
    old_weight = _to_float(change_row.get("oldWeight"))
    shares_delta = _to_int(change_row.get("sharesDelta")) or 0
    new_shares = _to_int(change_row.get("newShares")) or 0
    old_shares = _to_int(change_row.get("oldShares")) or 0

    if old_shares <= 0 and new_shares > 0:
        return "新增"
    if old_weight and old_weight > 0 and (new_weight == 0 or new_shares <= 1000):
        return "刪除"
    if shares_delta > 0:
        return "加碼"
    if shares_delta < 0:
        return "減碼"
    return "持平"


def _goalstar_label_from_status(status):
    return GOALSTAR_STATUS_TO_LABEL.get(str(status or "").strip().lower(), "持平")

def _is_target_active_etf(item):
    code = str(item.get("code") or "").strip().upper()
    name = str(item.get("name") or "").strip()
    return code.endswith("A") and name.startswith("主動")


@lru_cache(maxsize=1)
def load_active_etf_summary():
    html = _fetch_text(ETFINFO_ACTIVE_URL)
    try:
        payload_url = _extract_payload_url(html, r'href="(/active/_payload\.json\?[^"]+)"')
        payload = _fetch_json(payload_url)
        root = payload[2]
    except ValueError:
        payload = _extract_nuxt_data_payload(html)
        root = _find_nuxt_root(payload, ["active-summary-weekly-0"])
    decoded = _decode_nuxt_ref(payload, root["active-summary-weekly-0"])
    items = [item for item in decoded.get("etfs", []) if _is_target_active_etf(item)]
    return {
        "updated_at": decoded.get("updatedAt"),
        "latest_market_date": decoded.get("latestMarketDate"),
        "items": items,
    }


@lru_cache(maxsize=32)
def load_active_etf_detail(code):
    normalized_code = str(code).strip().upper()
    html = _fetch_text(ETFINFO_ETF_ACTIVE_URL.format(code=normalized_code))
    try:
        payload_url = _extract_payload_url(
            html,
            rf'href="(/etf/{re.escape(normalized_code)}/active/_payload\.json\?[^"]+)"',
        )
        payload = _fetch_json(payload_url)
        payload_root = payload[2]
    except ValueError:
        payload = _extract_nuxt_data_payload(html)
        payload_root = _find_nuxt_root(
            payload,
            [
                f"active-changes-{normalized_code}",
                f"etf-detail-base-{normalized_code}",
            ],
        )
    detail_key = f"active-changes-{normalized_code}"
    base_key = f"etf-detail-base-{normalized_code}"
    decoded_detail = _decode_nuxt_ref(payload, payload_root[detail_key])
    decoded_base = _decode_nuxt_ref(payload, payload_root[base_key])
    return {
        "active": decoded_detail,
        "base": decoded_base,
    }


@lru_cache(maxsize=64)
def load_twse_etf_basic_info(code):
    normalized_code = str(code).strip().upper()
    html = _fetch_text(TWSE_ETF_INFO_URL.format(code=normalized_code), verify=False)
    text = " ".join(BeautifulSoup(html, "html.parser").stripped_strings)

    def extract(pattern):
        match = re.search(pattern, text)
        return match.group(1).strip() if match else ""

    return {
        "code": normalized_code,
        "issuer": extract(r"發行公司\s*(.*?)\s*基金經理人"),
        "manager": extract(r"基金經理人\s*(.*?)\s*標的指數"),
        "benchmark": extract(r"標的指數\s*(.*?)\s*投資策略"),
        "aum_100m": _to_float(extract(r"資產規模\(億元\)\s*([0-9,\.]+)")),
        "beneficiary_10k": _to_float(extract(r"受益人次\(萬人\)\s*([0-9,\.]+)")),
    }


@lru_cache(maxsize=64)
def load_goalstar_fund_info(code):
    normalized_code = str(code).strip().upper()
    return _fetch_json(GOALSTAR_FUND_INFO_URL.format(code=normalized_code))


@lru_cache(maxsize=512)
def load_goalstar_fund_shares(code, date=None):
    normalized_code = str(code).strip().upper()
    normalized_date = str(date).strip() if date else ""
    params = {"date": normalized_date} if normalized_date else None
    return _fetch_json_with_params(
        GOALSTAR_FUND_SHARES_URL.format(code=normalized_code),
        params=params,
    )


def try_load_goalstar_fund_shares(code, date=None):
    try:
        return load_goalstar_fund_shares(code, date), None
    except HTTPError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code in {401, 402, 403, 404}:
            return None, status_code
        raise


@lru_cache(maxsize=2048)
def load_goalstar_fund_stock_history(code, stock_symbol, days=35):
    normalized_code = str(code).strip().upper()
    normalized_stock = str(stock_symbol).strip().upper()
    normalized_days = int(days)
    return _fetch_json_with_params(
        GOALSTAR_FUND_STOCK_HISTORY_URL.format(code=normalized_code, stock_symbol=normalized_stock),
        params={"days": normalized_days},
    )


def _discover_goalstar_snapshot_dates(code, reference_holdings_df, days=30):
    if reference_holdings_df is None or reference_holdings_df.empty:
        return []

    ranked_symbols = (
        reference_holdings_df.sort_values(["weight", "shares"], ascending=[False, False])["code"]
        .dropna()
        .astype(str)
        .tolist()
    )

    discovered_dates = set()
    history_days = max(int(days) + 8, 38)
    for stock_symbol in ranked_symbols[:10]:
        history_payload = load_goalstar_fund_stock_history(code, stock_symbol, history_days)
        for item in history_payload.get("items", []):
            date_text = str(item.get("date") or "").strip()
            if date_text:
                discovered_dates.add(date_text)
        if len(discovered_dates) >= days:
            break

    return sorted(discovered_dates)[-int(days):]


@lru_cache(maxsize=128)
def _discover_goalstar_share_dates_from_calendar(code, days=30):
    normalized_code = str(code).strip().upper()
    target_days = max(int(days), 1)
    discovered_dates = []
    seen_dates = set()
    cursor = date.today()
    max_calendar_span = max(target_days * 4, 60)

    for _ in range(max_calendar_span):
        if cursor.weekday() < 5:
            snapshot_date = cursor.isoformat()
            payload, status_code = try_load_goalstar_fund_shares(normalized_code, snapshot_date)
            if payload is not None and (payload.get("items") or []):
                if snapshot_date not in seen_dates:
                    discovered_dates.append(snapshot_date)
                    seen_dates.add(snapshot_date)
                    if len(discovered_dates) >= target_days:
                        break
            elif status_code not in {401, 402, 403, 404, None}:
                break
        cursor -= timedelta(days=1)

    return sorted(discovered_dates)


def _goalstar_items_to_changes_df(current_items, previous_items):
    current_df = pd.DataFrame(current_items or [])
    previous_df = pd.DataFrame(previous_items or [])

    current_by_symbol = {
        str(row.get("stock_symbol") or "").strip(): row
        for row in (current_df.to_dict("records") if not current_df.empty else [])
        if str(row.get("stock_symbol") or "").strip()
    }
    previous_by_symbol = {
        str(row.get("stock_symbol") or "").strip(): row
        for row in (previous_df.to_dict("records") if not previous_df.empty else [])
        if str(row.get("stock_symbol") or "").strip()
    }

    rows = []
    for stock_symbol in sorted(set(current_by_symbol) | set(previous_by_symbol)):
        current_row = current_by_symbol.get(stock_symbol) or {}
        previous_row = previous_by_symbol.get(stock_symbol) or {}

        new_shares = _to_float(current_row.get("shares"))
        if new_shares is None:
            new_shares = 0.0
        old_shares = _to_float(previous_row.get("shares"))
        if old_shares is None:
            diff_value = _to_float(current_row.get("diff"))
            old_shares = max(new_shares - (diff_value or 0.0), 0.0)

        status = str(current_row.get("status") or "").strip().lower()
        diff_shares = _to_float(current_row.get("diff"))
        if diff_shares is None:
            diff_shares = new_shares - old_shares

        new_weight = _to_float(current_row.get("ratio"))
        if new_weight is None:
            new_weight = 0.0
        old_weight = _to_float(previous_row.get("ratio"))
        if old_weight is None:
            old_weight = 0.0

        if not status:
            if old_shares <= 0 and new_shares > 0:
                status = "new"
            elif old_shares > 0 and new_shares <= 0:
                status = "clear"
            elif diff_shares > 0:
                status = "increase"
            elif diff_shares < 0:
                status = "decrease"
            else:
                status = "unchanged"

        if status == "unchanged" and abs(diff_shares) < 1e-9:
            continue

        price = _to_float(current_row.get("close"))
        if price is None:
            price = _to_float(previous_row.get("close"))
        value_shares = new_shares if new_shares > 0 else old_shares
        holding_amount_ntd = (value_shares * price) if price is not None else None
        holding_amount_100m = (holding_amount_ntd / 100000000) if holding_amount_ntd is not None else None

        rows.append(
            {
                "code": current_row.get("stock_symbol") or previous_row.get("stock_symbol") or stock_symbol,
                "name": current_row.get("stock_name") or previous_row.get("stock_name") or stock_symbol,
                "industry": current_row.get("industry") or previous_row.get("industry") or None,
                "change_label": _goalstar_label_from_status(status),
                "shares_delta": diff_shares,
                "shares_delta_lots": diff_shares / 1000 if diff_shares is not None else None,
                "old_weight": old_weight,
                "new_weight": new_weight,
                "weight_delta": new_weight - old_weight,
                "new_shares": new_shares,
                "old_shares": old_shares,
                "new_lots": new_shares / 1000 if new_shares is not None else None,
                "close": price,
                "holding_amount_ntd": holding_amount_ntd,
                "holding_amount_100m": holding_amount_100m,
            }
        )

    changes_df = pd.DataFrame(rows)
    if changes_df.empty:
        return changes_df
    return fill_missing_industry(changes_df)


def backfill_goalstar_etf_history(code, reference_holdings_df, *, days=30):
    normalized_code = str(code).strip().upper()
    fund_info = load_goalstar_fund_info(normalized_code)
    has_foreign_holdings = bool(fund_info.get("has_foreign"))
    if has_foreign_holdings:
        snapshot_dates = _discover_goalstar_share_dates_from_calendar(normalized_code, days=days)
    else:
        snapshot_dates = _discover_goalstar_snapshot_dates(normalized_code, reference_holdings_df, days=days)
    if not snapshot_dates:
        return {"backfilled_dates": []}

    today_text = date.today().isoformat()
    target_latest_date = snapshot_dates[-1]
    target_available_count = len(snapshot_dates)
    refresh_state = load_etf_change_refresh_state(normalized_code)
    if (
        refresh_state
        and str(refresh_state.get("last_attempt_at") or "") == today_text
        and str(refresh_state.get("latest_snapshot_date") or "") == str(target_latest_date)
        and int(refresh_state.get("available_dates_count") or 0) >= int(target_available_count)
    ):
        return {
            "backfilled_dates": [],
            "skipped": True,
            "latest_snapshot_date": target_latest_date,
            "available_dates_count": target_available_count,
        }

    shares_by_date = {}
    accessible_symbols = set()
    symbol_meta = {}
    locked_dates = []
    for snapshot_date in snapshot_dates:
        shares_payload, status_code = try_load_goalstar_fund_shares(normalized_code, snapshot_date)
        if shares_payload is None:
            locked_dates.append((snapshot_date, status_code))
            continue
        shares_items = shares_payload.get("items", []) or []
        shares_by_date[snapshot_date] = shares_items
        for item in shares_items:
            stock_symbol = str(item.get("stock_symbol") or "").strip()
            if not stock_symbol:
                continue
            accessible_symbols.add(stock_symbol)
            symbol_meta[stock_symbol] = {
                "stock_name": item.get("stock_name") or stock_symbol,
                "industry": item.get("industry"),
            }

    if locked_dates and not has_foreign_holdings:
        if not accessible_symbols and reference_holdings_df is not None and not reference_holdings_df.empty:
            for _, row in reference_holdings_df.iterrows():
                stock_symbol = str(row.get("code") or "").strip()
                if not stock_symbol:
                    continue
                accessible_symbols.add(stock_symbol)
                symbol_meta[stock_symbol] = {
                    "stock_name": row.get("name") or stock_symbol,
                    "industry": row.get("industry"),
                }

        history_days = max(int(days) + 12, 45)
        symbol_histories = {}
        for stock_symbol in sorted(accessible_symbols):
            history_payload = load_goalstar_fund_stock_history(normalized_code, stock_symbol, history_days)
            items = history_payload.get("items", []) or []
            for item in items:
                item_date = str(item.get("date") or "").strip()
                if item_date not in snapshot_dates:
                    continue
                meta = symbol_meta.get(stock_symbol, {})
                symbol_histories.setdefault(item_date, []).append(
                    {
                        "date": item_date,
                        "stock_symbol": stock_symbol,
                        "stock_name": item.get("stock_name") or meta.get("stock_name") or stock_symbol,
                        "industry": item.get("industry") or meta.get("industry"),
                        "shares": item.get("shares"),
                        "ratio": item.get("ratio"),
                        "diff": item.get("diff"),
                        "status": item.get("status"),
                        "close": item.get("close"),
                        "change": item.get("change"),
                    }
                )
        for snapshot_date, _ in locked_dates:
            reconstructed_items = symbol_histories.get(snapshot_date, [])
            if reconstructed_items:
                shares_by_date[snapshot_date] = reconstructed_items

    persisted_dates = []
    for idx, snapshot_date in enumerate(snapshot_dates):
        if snapshot_date not in shares_by_date:
            continue
        previous_date = snapshot_dates[idx - 1] if idx > 0 else None
        current_items = shares_by_date.get(snapshot_date, [])
        previous_items = shares_by_date.get(previous_date, []) if previous_date in shares_by_date else []
        changes_df = _goalstar_items_to_changes_df(current_items, previous_items)

        change_counts = {
            "新增": int((changes_df["change_label"] == "新增").sum()) if not changes_df.empty else 0,
            "加碼": int((changes_df["change_label"] == "加碼").sum()) if not changes_df.empty else 0,
            "減碼": int((changes_df["change_label"] == "減碼").sum()) if not changes_df.empty else 0,
            "刪除": int((changes_df["change_label"] == "刪除").sum()) if not changes_df.empty else 0,
        }

        summary = {
            "from_date": previous_date,
            "to_date": snapshot_date,
            "change_count": len(changes_df),
            "holdings_count": len(current_items),
            "turnover_rate": None,
            "snapshot_date": snapshot_date,
            "aum_100m": None,
            "beneficiary_10k": None,
            "issuer": fund_info.get("manager"),
            "manager": fund_info.get("manager"),
            "change_counts": change_counts,
        }
        persist_etf_change_snapshot(
            normalized_code,
            fund_info.get("name") or normalized_code,
            summary,
            changes_df,
            snapshot_date,
        )
        persisted_dates.append(snapshot_date)

    upsert_etf_change_refresh_state(
        normalized_code,
        target_days=days,
        latest_snapshot_date=target_latest_date,
        available_dates_count=target_available_count,
        last_attempt_at=today_text,
    )

    return {"backfilled_dates": persisted_dates}


def build_active_etf_overview_bundle(top_n=8):
    summary = load_active_etf_summary()
    rows = []
    for item in summary["items"]:
        basic = load_twse_etf_basic_info(item["code"])
        rows.append(
            {
                "code": item["code"],
                "name": item["name"],
                "scope": item.get("scope"),
                "issuer": basic.get("issuer") or "",
                "manager": basic.get("manager") or "",
                "benchmark": basic.get("benchmark") or "",
                "aum_100m": basic.get("aum_100m"),
                "beneficiary_10k": basic.get("beneficiary_10k"),
                "latest_snapshot_date": item.get("latestSnapshotDate"),
                "change_count": _to_int(item.get("changeCount")),
                "net_amount": _to_float(item.get("netAmount")),
                "price": _to_float(item.get("price")),
                "today_pct": _to_float(item.get("today")),
                "week_pct": _to_float(item.get("week")),
                "month_pct": _to_float(item.get("month")),
                "ytd_pct": _to_float(item.get("ytd")),
                "top_changes": item.get("topChanges") or [],
            }
        )

    overview_df = pd.DataFrame(rows)
    if overview_df.empty:
        return None

    overview_df = overview_df.sort_values(["aum_100m", "change_count", "net_amount"], ascending=[False, False, False]).reset_index(drop=True)
    top_df = overview_df.head(top_n).copy()
    top_df["規模(億)"] = top_df["aum_100m"].map(_format_amount_100m)
    top_df["受益人(萬)"] = top_df["beneficiary_10k"].map(_format_people_10k)
    top_df["最新異動筆數"] = top_df["change_count"].fillna(0).astype(int)
    top_df["最新持股日"] = top_df["latest_snapshot_date"].fillna("-")
    top_df["今日(%)"] = top_df["today_pct"].map(_format_pct)
    top_df["近一週(%)"] = top_df["week_pct"].map(_format_pct)
    top_df["近一月(%)"] = top_df["month_pct"].map(_format_pct)
    display_df = top_df.rename(
        columns={
            "code": "代碼",
            "name": "ETF名稱",
        }
    )[
        ["代碼", "ETF名稱", "規模(億)", "受益人(萬)", "最新持股日", "最新異動筆數", "今日(%)", "近一週(%)", "近一月(%)"]
    ]

    largest_row = overview_df.sort_values("aum_100m", ascending=False).iloc[0]
    busiest_row = overview_df.sort_values("change_count", ascending=False).iloc[0]
    strongest_row = overview_df.sort_values("today_pct", ascending=False).iloc[0]

    return {
        "updated_at": summary.get("updated_at"),
        "latest_market_date": summary.get("latest_market_date"),
        "raw_df": overview_df,
        "display_df": display_df,
        "top_n": top_n,
        "largest_etf": largest_row["name"],
        "largest_aum_100m": largest_row["aum_100m"],
        "busiest_etf": busiest_row["name"],
        "busiest_change_count": busiest_row["change_count"],
        "strongest_today_etf": strongest_row["name"],
        "strongest_today_pct": strongest_row["today_pct"],
    }


def build_active_etf_detail_bundle(code):
    normalized_code = str(code).strip().upper()
    detail_payload = load_active_etf_detail(normalized_code)
    basic = load_twse_etf_basic_info(normalized_code)
    active = detail_payload["active"]
    base = detail_payload["base"]
    goalstar_info = load_goalstar_fund_info(normalized_code)
    latest_diff = active.get("latestDiff") or {}
    latest_market = base.get("latestMarket") or {}
    info_payload = base.get("info") or {}
    holdings_payload = base.get("holdings") or {}
    holdings = holdings_payload.get("holdings") or holdings_payload.get("stocks") or []
    latest_aum_ntd = _to_float(latest_market.get("aum"))

    changes_df = pd.DataFrame(latest_diff.get("changes") or [])
    if not changes_df.empty:
        changes_df = fill_missing_industry(changes_df)
        changes_df["change_label"] = changes_df.apply(_classify_change_type, axis=1)
        changes_df["shares_delta"] = changes_df["sharesDelta"].map(_to_float)
        changes_df["abs_shares_delta"] = changes_df["shares_delta"].abs()
        changes_df["shares_delta_lots"] = changes_df["sharesDelta"].map(_to_float).fillna(0) / 1000
        changes_df["old_weight"] = changes_df["oldWeight"].map(_to_float)
        changes_df["new_weight"] = changes_df["newWeight"].map(_to_float)
        changes_df["weight_delta"] = changes_df["weightDelta"].map(_to_float)
        changes_df["new_shares"] = changes_df["newShares"].map(_to_float)
        changes_df["old_shares"] = changes_df["oldShares"].map(_to_float)
        changes_df["new_lots"] = changes_df["new_shares"] / 1000
        changes_df["close"] = changes_df["close"].map(_to_float) if "close" in changes_df.columns else None
        changes_df["holding_amount_ntd"] = changes_df.apply(
            lambda row: (
                row["new_shares"] * row["close"]
                if row.get("close") is not None and not pd.isna(row.get("close")) and row.get("new_shares") is not None and not pd.isna(row.get("new_shares"))
                else (latest_aum_ntd * row["new_weight"] / 100 if latest_aum_ntd is not None and row.get("new_weight") is not None and not pd.isna(row.get("new_weight")) else None)
            ),
            axis=1,
        )
        changes_df["holding_amount_100m"] = changes_df["holding_amount_ntd"] / 100000000
        changes_df["最新權重(%)"] = changes_df["new_weight"].map(lambda value: "-" if value is None or pd.isna(value) else f"{value:.2f}")
        changes_df["前日權重(%)"] = changes_df["old_weight"].map(lambda value: "-" if value is None or pd.isna(value) else f"{value:.2f}")
        changes_df["權重變化(%)"] = changes_df["weight_delta"].map(lambda value: "-" if value is None or pd.isna(value) else f"{value:+.2f}")
        changes_df["股數變化"] = changes_df["sharesDelta"].map(_format_shares)
        changes_df["張數變化"] = changes_df["sharesDelta"].map(_format_lots)
        changes_df["最新股數"] = changes_df["newShares"].map(_format_shares)
        changes_df["最新張數"] = changes_df["new_lots"].map(lambda value: "-" if value is None or pd.isna(value) else f"{value:,.1f}")
        changes_df["持有金額(估,億)"] = changes_df["holding_amount_ntd"].map(_format_amount_ntd_100m)
        changes_df["動作"] = changes_df["change_label"]
        changes_display_df = changes_df.rename(
            columns={
                "code": "代碼",
                "name": "名稱",
                "industry": "產業",
            }
        )[
            [
                "動作",
                "代碼",
                "名稱",
                "產業",
                "股數變化",
                "張數變化",
                "權重變化(%)",
                "前日權重(%)",
                "最新權重(%)",
                "持有金額(估,億)",
                "最新股數",
                "最新張數",
                "abs_shares_delta",
            ]
        ].sort_values(["動作", "abs_shares_delta"], ascending=[True, False]).drop(columns=["abs_shares_delta"]).reset_index(drop=True)
    else:
        changes_display_df = pd.DataFrame(columns=["動作", "代碼", "名稱", "產業", "股數變化", "張數變化", "權重變化(%)", "前日權重(%)", "最新權重(%)", "持有金額(估,億)", "最新股數", "最新張數"])

    holdings_df = pd.DataFrame(holdings)
    if not holdings_df.empty:
        holdings_df = fill_missing_industry(holdings_df)
        holdings_df["weight"] = holdings_df["weight"].map(_to_float)
        holdings_df["shares"] = holdings_df["shares"].map(_to_float)
        holdings_df["lots"] = holdings_df["shares"] / 1000
        holdings_df["holding_amount_ntd"] = holdings_df["weight"].map(
            lambda value: latest_aum_ntd * value / 100 if latest_aum_ntd is not None and value is not None and not pd.isna(value) else None
        )
        holdings_df["holding_amount_100m"] = holdings_df["holding_amount_ntd"] / 100000000
        holdings_df = holdings_df.sort_values(["weight", "shares"], ascending=[False, False]).reset_index(drop=True)
        holdings_df["權重(%)"] = holdings_df["weight"].map(lambda value: "-" if value is None or pd.isna(value) else f"{value:.2f}")
        holdings_df["股數"] = holdings_df["shares"].map(_format_shares)
        holdings_df["張數"] = holdings_df["lots"].map(lambda value: "-" if value is None or pd.isna(value) else f"{value:,.1f}")
        holdings_df["持有金額(估,億)"] = holdings_df["holding_amount_ntd"].map(_format_amount_ntd_100m)
        holdings_display_df = holdings_df.rename(
            columns={
                "code": "代碼",
                "name": "名稱",
                "industry": "產業",
            }
        )[["代碼", "名稱", "產業", "權重(%)", "持有金額(估,億)", "股數", "張數"]].head(20)
    else:
        holdings_display_df = pd.DataFrame(columns=["代碼", "名稱", "產業", "權重(%)", "持有金額(估,億)", "股數", "張數"])

    if not holdings_df.empty:
        industry_breakdown_df = (
            holdings_df.groupby("industry", dropna=False)
            .agg(
                industry_weight=("weight", "sum"),
                company_count=("code", "count"),
            )
            .reset_index()
            .rename(columns={"industry": "industry"})
            .sort_values(["industry_weight", "company_count"], ascending=[False, False])
            .reset_index(drop=True)
        )
    else:
        industry_breakdown_df = pd.DataFrame(columns=["industry", "industry_weight", "company_count"])

    change_summary = {
        "from_date": latest_diff.get("fromDate"),
        "to_date": latest_diff.get("toDate"),
        "change_count": len(latest_diff.get("changes") or []),
        "holdings_count": latest_diff.get("holdingsCount"),
        "turnover_rate": active.get("turnoverRate"),
        "snapshot_date": holdings_payload.get("snapshotDate"),
        "aum_100m": basic.get("aum_100m") or (_to_float(latest_market.get("aum")) / 100000000 if _to_float(latest_market.get("aum")) is not None else None),
        "beneficiary_10k": basic.get("beneficiary_10k") or (_to_float(latest_market.get("beneficiaries")) / 10000 if _to_float(latest_market.get("beneficiaries")) is not None else None),
        "issuer": info_payload.get("issuer") or basic.get("issuer"),
        "manager": info_payload.get("manager") or basic.get("manager"),
    }

    change_counts = {
        "新增": int((changes_df["change_label"] == "新增").sum()) if not changes_df.empty else 0,
        "加碼": int((changes_df["change_label"] == "加碼").sum()) if not changes_df.empty else 0,
        "減碼": int((changes_df["change_label"] == "減碼").sum()) if not changes_df.empty else 0,
        "刪除": int((changes_df["change_label"] == "刪除").sum()) if not changes_df.empty else 0,
    }
    change_summary["change_counts"] = change_counts

    persist_etf_change_snapshot(
        normalized_code,
        active.get("name") or normalized_code,
        change_summary,
        changes_df,
        active.get("updatedAt"),
    )

    has_foreign_holdings = bool(goalstar_info.get("has_foreign"))
    backfill_goalstar_etf_history(normalized_code, holdings_df, days=30)
    history_summary_df = load_etf_change_snapshot_summaries(normalized_code)

    overview = {
        "code": normalized_code,
        "name": active.get("name") or normalized_code,
        "issuer": info_payload.get("issuer") or basic.get("issuer"),
        "manager": info_payload.get("manager") or basic.get("manager") or goalstar_info.get("manager"),
        "launch_date": info_payload.get("launchDate"),
        "tracking_index": info_payload.get("trackingIndex") or basic.get("benchmark"),
        "management_style": info_payload.get("managementStyle"),
        "management_fee": _to_float(info_payload.get("managementFee")),
        "custody_fee": _to_float(info_payload.get("custodyFee")),
        "dividend_frequency": info_payload.get("dividendFrequency"),
        "dividend_policy": info_payload.get("dividendPolicy"),
        "trailing_yield": _to_float(base.get("trailingYield")),
        "aum_100m": basic.get("aum_100m") or (_to_float(latest_market.get("aum")) / 100000000 if _to_float(latest_market.get("aum")) is not None else None),
        "beneficiary_10k": basic.get("beneficiary_10k") or (_to_float(latest_market.get("beneficiaries")) / 10000 if _to_float(latest_market.get("beneficiaries")) is not None else None),
        "market_date": latest_market.get("date"),
        "price": _to_float(latest_market.get("price")),
        "nav": _to_float(latest_market.get("nav")),
        "premium": _to_float(latest_market.get("premium")),
        "market_change_pct": _to_float(latest_market.get("change")),
        "holdings_snapshot_date": holdings_payload.get("snapshotDate"),
        "holdings_count": len(holdings_df),
        "scope": "foreign" if has_foreign_holdings else "domestic",
        "return_1y": _to_float((base.get("returnStats") or {}).get("return1Y")),
        "return_3y": _to_float((base.get("returnStats") or {}).get("return3Y")),
        "return_5y": _to_float((base.get("returnStats") or {}).get("return5Y")),
    }

    return {
        "code": normalized_code,
        "name": active.get("name") or normalized_code,
        "updated_at": active.get("updatedAt"),
        "overview": overview,
        "change_summary": change_summary,
        "changes_df": changes_display_df,
        "raw_changes_df": changes_df,
        "holdings_df": holdings_display_df,
        "raw_holdings_df": holdings_df,
        "industry_breakdown_df": industry_breakdown_df,
        "history_summary_df": history_summary_df,
    }


def refresh_all_active_etf_history_snapshots(limit=None):
    summary = load_active_etf_summary()
    items = [item for item in summary.get("items", []) if item.get("code")]
    if limit is not None:
        items = items[: int(limit)]

    refreshed = []
    for item in items:
        bundle = build_active_etf_detail_bundle(item["code"])
        refreshed.append(
            {
                "code": item["code"],
                "name": bundle.get("name") or item.get("name") or item["code"],
                "snapshot_date": bundle.get("change_summary", {}).get("to_date") or bundle.get("change_summary", {}).get("snapshot_date"),
            }
        )

    return {
        "count": len(refreshed),
        "items": refreshed,
        "updated_at": summary.get("updated_at"),
    }
