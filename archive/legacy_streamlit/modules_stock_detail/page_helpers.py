from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from modules.core.trading_calendar import resolve_after_hours_trade_date, resolve_recent_trade_date, resolve_trade_dates_in_range
from modules.data_sources.broker_branch_data import fetch_broker_branch_summary, fetch_broker_branch_trace
from modules.data_sources.broker_branch_short_term import build_short_term_broker_report, build_today_chip_quick_report
from modules.data_sources.chip_data import get_institutional_detail_for_stock
from modules.data_sources.market_watch import (
    fetch_tpex_after_market_quotes,
    fetch_tpex_daily_quotes,
    fetch_tpex_odd_lot_quotes,
    fetch_twse_after_market_quotes,
    fetch_twse_daily_quotes,
    fetch_twse_odd_lot_quotes,
)
from modules.data_sources.stock_db import find_security


BROKER_BRANCH_CACHE_VERSION = "broker_branch_hybrid_v4"
TODAY_CHIP_CACHE_VERSION = "today_chip_v12"


@st.cache_data(show_spinner=False, ttl=1800)
def load_broker_branch_summary(stock_code: str, trade_date_key: str, cache_version: str):
    return fetch_broker_branch_summary(stock_code, top_n=15, trade_date=trade_date_key)


@st.cache_data(show_spinner=False, ttl=1800)
def load_broker_branch_trace(detail_url: str):
    return fetch_broker_branch_trace(detail_url)


@st.cache_data(show_spinner=False, ttl=1800)
def _load_twse_daily_quotes_cached(trade_date_key: str):
    return fetch_twse_daily_quotes(trade_date_key)


@st.cache_data(show_spinner=False, ttl=1800)
def _load_tpex_daily_quotes_cached(trade_date_key: str):
    return fetch_tpex_daily_quotes(trade_date_key)


@st.cache_data(show_spinner=False, ttl=1800)
def _load_twse_odd_lot_quotes_cached():
    return fetch_twse_odd_lot_quotes()


@st.cache_data(show_spinner=False, ttl=1800)
def _load_twse_after_market_quotes_cached():
    return fetch_twse_after_market_quotes()


@st.cache_data(show_spinner=False, ttl=1800)
def _load_tpex_odd_lot_quotes_cached():
    return fetch_tpex_odd_lot_quotes()


@st.cache_data(show_spinner=False, ttl=1800)
def _load_tpex_after_market_quotes_cached():
    return fetch_tpex_after_market_quotes()


@st.cache_data(show_spinner=False, ttl=1800)
def load_short_term_broker_report(stock_code: str, trade_date_key: str, cache_version: str):
    return build_short_term_broker_report(stock_code)


@st.cache_data(show_spinner=False, ttl=1800)
def load_short_term_broker_report_window(stock_code: str, days_window: int, trade_date_key: str, cache_version: str):
    return build_short_term_broker_report(stock_code, days_window=days_window)


def build_deferred_today_chip_report(stock_code: str, trade_date_key: str) -> dict[str, Any]:
    return {
        "stock_code": stock_code,
        "stock_title": stock_code,
        "source_label": "今日籌碼快速模式",
        "trade_date": trade_date_key,
        "buy_rows": [],
        "sell_rows": [],
        "buy_display_rows": [],
        "sell_display_rows": [],
        "summary": {
            "signal_label": "分點後補",
            "signal_reason": "為了讓第一屏更快顯示，分點榜與短衝分析改到後面的分頁再載入。",
            "concentration_lots": None,
            "main_net_lots": None,
            "concentration_pct": None,
            "short_term_buy_pct": None,
            "short_term_sell_pct": None,
            "buy_top5_pct": None,
            "sell_top5_pct": None,
            "total_volume_lots": None,
            "estimated_float_pct": None,
            "interval_turnover_pct": None,
        },
        "alerts": [],
    }


def format_pct_text(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def format_lots_text(value):
    if value is None:
        return "-"
    return f"{float(value):,.0f} 張"


def format_signed_lots_text(value):
    if value is None:
        return "-"
    number = float(value)
    if abs(number) < 0.0001:
        return "0 張"
    return f"{number:+,.0f} 張"


def format_price_text(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def format_profit_k_text(value):
    if value is None:
        return "-"
    number = float(value)
    if abs(number) < 0.0001:
        return "0.0"
    return f"{number:+,.1f}"


def format_close_text(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def row_value(row: dict[str, Any], *keys: str):
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def format_ratio_text(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}x"


def format_net_lots_metric(value):
    if value is None:
        return "-"
    return f"{float(value)/1000:+,.0f} 張"


def latest_market_date_key(anchor_date=None) -> str:
    if anchor_date is None:
        resolved = resolve_after_hours_trade_date()
    else:
        resolved = resolve_recent_trade_date(anchor_date)
    return resolved["effective_date_text"]


def _lookup_component_volume(component_df: pd.DataFrame, stock_code: str, probe_date, value_column: str) -> float:
    if component_df.empty:
        return 0.0

    matched = component_df[component_df["code"].astype(str) == str(stock_code)].copy()
    if matched.empty:
        return 0.0

    probe_date_text = probe_date.strftime("%Y-%m-%d") if hasattr(probe_date, "strftime") else str(probe_date)
    if "date" in matched.columns:
        dated = matched[matched["date"].astype(str) == probe_date_text]
        if not dated.empty:
            matched = dated
        elif matched["date"].astype(str).str.len().gt(0).any():
            return 0.0

    value = matched.iloc[0].get(value_column)
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def load_official_volume_lots(stock_code: str, probe_date) -> float | None:
    twse_df = fetch_twse_daily_quotes(probe_date)
    tpex_df = fetch_tpex_daily_quotes(probe_date)
    quote_df = pd.concat([twse_df, tpex_df], ignore_index=True)
    if quote_df.empty:
        return None

    matched = quote_df[quote_df["code"].astype(str) == str(stock_code)]
    if matched.empty:
        return None

    matched_row = matched.iloc[0]
    regular_volume_shares = matched_row.get("volume")
    if regular_volume_shares is None or pd.isna(regular_volume_shares):
        return None

    market_name = str(matched_row.get("market") or "")
    total_volume_shares = float(regular_volume_shares)

    if market_name == "上市":
        total_volume_shares += _lookup_component_volume(fetch_twse_odd_lot_quotes(), stock_code, probe_date, "odd_volume")
        total_volume_shares += _lookup_component_volume(
            fetch_twse_after_market_quotes(),
            stock_code,
            probe_date,
            "after_market_volume",
        )

    return total_volume_shares / 1000.0


@st.cache_data(show_spinner=False, ttl=1800)
def load_official_snapshot_pair(stock_code: str, end_date_key: str, security_market: str | None) -> dict[str, Any]:
    end_date = datetime.strptime(end_date_key, "%Y-%m-%d").date()
    resolved_days = resolve_trade_dates_in_range(end_date - timedelta(days=10), end_date)
    if not resolved_days:
        return {
            "current_row": None,
            "prev_row": None,
            "current_volume_lots": None,
            "prev_volume_lots": None,
        }

    trade_dates = [item["effective_date_text"] for item in resolved_days]
    current_trade_date = trade_dates[-1]
    prev_trade_date = trade_dates[-2] if len(trade_dates) >= 2 else None
    quote_cache: dict[str, pd.DataFrame] = {}
    normalized_market = str(security_market or "").strip().upper()

    def _quote_df_for(trade_date_text: str | None) -> pd.DataFrame:
        if not trade_date_text:
            return pd.DataFrame()
        if trade_date_text not in quote_cache:
            if normalized_market == "TWSE":
                quote_cache[trade_date_text] = _load_twse_daily_quotes_cached(trade_date_text)
            elif normalized_market == "TPEX":
                quote_cache[trade_date_text] = _load_tpex_daily_quotes_cached(trade_date_text)
            else:
                quote_cache[trade_date_text] = pd.concat(
                    [_load_twse_daily_quotes_cached(trade_date_text), _load_tpex_daily_quotes_cached(trade_date_text)],
                    ignore_index=True,
                )
        return quote_cache[trade_date_text]

    def _lookup_quote_row(trade_date_text: str | None) -> dict[str, Any] | None:
        quote_df = _quote_df_for(trade_date_text)
        if quote_df.empty:
            return None
        matched = quote_df[quote_df["code"].astype(str) == str(stock_code)]
        if matched.empty:
            return None
        row = matched.iloc[0].to_dict()
        row["trade_date"] = trade_date_text
        return row

    twse_odd_df = _load_twse_odd_lot_quotes_cached() if normalized_market in {"", "TWSE"} else pd.DataFrame()
    twse_after_df = _load_twse_after_market_quotes_cached() if normalized_market in {"", "TWSE"} else pd.DataFrame()

    def _total_volume_lots(row: dict[str, Any] | None, trade_date_text: str | None) -> float | None:
        if not row or not trade_date_text:
            return None
        regular_volume = row.get("volume")
        if regular_volume is None or pd.isna(regular_volume):
            return None

        market_name = str(row.get("market") or "")
        total_volume_shares = float(regular_volume)
        probe_date = datetime.strptime(trade_date_text, "%Y-%m-%d").date()
        if market_name == "上市":
            total_volume_shares += _lookup_component_volume(twse_odd_df, stock_code, probe_date, "odd_volume")
            total_volume_shares += _lookup_component_volume(twse_after_df, stock_code, probe_date, "after_market_volume")
        return total_volume_shares / 1000.0

    current_row = _lookup_quote_row(current_trade_date)
    prev_row = _lookup_quote_row(prev_trade_date)
    return {
        "current_row": current_row,
        "prev_row": prev_row,
        "current_volume_lots": _total_volume_lots(current_row, current_trade_date),
        "prev_volume_lots": _total_volume_lots(prev_row, prev_trade_date),
    }


@st.cache_data(show_spinner=False, ttl=1800)
def load_basic_quote_pair(stock_code: str, end_date_key: str, security_market: str | None) -> dict[str, Any]:
    def _to_float(value: Any) -> float | None:
        try:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    end_date = datetime.strptime(end_date_key, "%Y-%m-%d").date()
    resolved_days = resolve_trade_dates_in_range(end_date - timedelta(days=10), end_date)
    if not resolved_days:
        return {
            "current_row": None,
            "prev_row": None,
            "current_volume_lots": None,
            "prev_volume_lots": None,
        }

    trade_dates = [item["effective_date_text"] for item in resolved_days]
    normalized_market = str(security_market or "").strip().upper()

    def _quote_df_for(trade_date_text: str | None) -> pd.DataFrame:
        if not trade_date_text:
            return pd.DataFrame()
        if normalized_market == "TWSE":
            return _load_twse_daily_quotes_cached(trade_date_text)
        if normalized_market == "TPEX":
            return _load_tpex_daily_quotes_cached(trade_date_text)
        return pd.concat(
            [_load_twse_daily_quotes_cached(trade_date_text), _load_tpex_daily_quotes_cached(trade_date_text)],
            ignore_index=True,
        )

    def _lookup_quote_row(trade_date_text: str | None) -> dict[str, Any] | None:
        quote_df = _quote_df_for(trade_date_text)
        if quote_df.empty:
            return None
        matched = quote_df[quote_df["code"].astype(str) == str(stock_code)]
        if matched.empty:
            return None
        row = matched.iloc[0].to_dict()
        row["trade_date"] = trade_date_text
        return row

    resolved_rows = []
    for trade_date_text in reversed(trade_dates):
        row = _lookup_quote_row(trade_date_text)
        if row is not None:
            resolved_rows.append(row)
        if len(resolved_rows) >= 2:
            break

    current_row = resolved_rows[0] if len(resolved_rows) >= 1 else None
    prev_row = resolved_rows[1] if len(resolved_rows) >= 2 else None
    return {
        "current_row": current_row,
        "prev_row": prev_row,
        "current_volume_lots": ((_to_float((current_row or {}).get("volume")) or 0.0) / 1000.0) if current_row else None,
        "prev_volume_lots": ((_to_float((prev_row or {}).get("volume")) or 0.0) / 1000.0) if prev_row else None,
    }


@st.cache_data(show_spinner=False, ttl=1800)
def load_today_chip_snapshot(stock_code: str, symbol: str, end_date, cache_version: str):
    trade_date_key = latest_market_date_key(end_date)
    security = find_security(stock_code) or {}
    security_market = security.get("market")

    report = build_deferred_today_chip_report(stock_code, trade_date_key)
    report_error = None
    report_deferred = True
    quote_warning = None
    quote_payload = load_basic_quote_pair(stock_code, trade_date_key, security_market)

    latest_row = quote_payload.get("current_row")
    prev_row = quote_payload.get("prev_row")
    if latest_row is None:
        return {
            "short_term_report": report,
            "history_row": None,
            "institutional_detail": None,
            "price_volume_state": None,
            "volume_ratio_prev_day": None,
            "change_pct": None,
            "official_volume_lots": None,
            "official_prev_volume_lots": None,
            "quote_warning": quote_warning,
            "report_error": report_error,
            "report_deferred": report_deferred,
        }

    official_volume_lots = quote_payload.get("current_volume_lots")
    official_prev_volume_lots = quote_payload.get("prev_volume_lots")
    latest_volume = (official_volume_lots or 0.0) * 1000.0 if official_volume_lots is not None else float(latest_row.get("volume") or 0.0)
    prev_day_volume = (official_prev_volume_lots or 0.0) * 1000.0 if official_prev_volume_lots is not None else (
        float(prev_row.get("volume")) if prev_row and prev_row.get("volume") is not None else None
    )
    volume_ratio_prev_day = (latest_volume / prev_day_volume) if prev_day_volume and prev_day_volume > 0 else None

    close_value = float(latest_row.get("close") or 0.0) if latest_row.get("close") is not None else None
    prev_close = float(latest_row.get("prev_close") or 0.0) if latest_row.get("prev_close") is not None else None
    change_pct = float(latest_row.get("change_pct")) if latest_row.get("change_pct") is not None else (
        ((close_value - prev_close) / prev_close * 100.0) if close_value and prev_close else None
    )

    if (change_pct or 0.0) >= 2.0 and (volume_ratio_prev_day or 0.0) >= 1.5:
        price_volume_state = ("放量上攻", "量價同步擴張，短線追價力道偏強。")
    elif (change_pct or 0.0) <= -2.0 and (volume_ratio_prev_day or 0.0) >= 1.5:
        price_volume_state = ("放量下殺", "帶量回落，短線賣壓較重。")
    elif abs(change_pct or 0.0) <= 1.2 and (volume_ratio_prev_day or 0.0) < 0.85:
        price_volume_state = ("量縮整理", "價格波動收斂，籌碼暫時觀望。")
    elif (change_pct or 0.0) > 0 and (volume_ratio_prev_day or 0.0) < 1.0:
        price_volume_state = ("量縮墊高", "價格偏強，但量能未明顯放大。")
    elif (change_pct or 0.0) < 0 and (volume_ratio_prev_day or 0.0) < 1.0:
        price_volume_state = ("量縮回檔", "拉回過程量能不大，先看支撐。")
    else:
        price_volume_state = ("量價中性", "價格與量能沒有特別偏離常態。")

    institutional_detail = None
    try:
        institutional_detail = get_institutional_detail_for_stock(
            stock_code,
            latest_row["trade_date"],
            market=security_market or "TWSE",
        )
        if institutional_detail is None:
            institutional_detail = get_institutional_detail_for_stock(
                stock_code,
                latest_row["trade_date"],
                market="TWSE",
            )
    except Exception:
        institutional_detail = None

    try:
        report = build_today_chip_quick_report(
            stock_code,
            trade_date=latest_row.get("trade_date") or trade_date_key,
            total_volume_lots=official_volume_lots,
            latest_close_value=close_value,
        )
        report_deferred = False
        report_error = None
    except Exception as exc:
        try:
            report = build_short_term_broker_report(stock_code, days_window=1)
            report_deferred = False
            report_error = None
        except Exception:
            report = build_deferred_today_chip_report(stock_code, latest_row.get("trade_date") or trade_date_key)
            report_error = str(exc)
            report_deferred = True

    report_summary = report.get("summary") or {}
    if official_volume_lots is not None:
        report_summary["total_volume_lots"] = official_volume_lots
        main_net_lots = report_summary.get("main_net_lots")
        concentration_lots = report_summary.get("concentration_lots")
        if main_net_lots is not None and official_volume_lots > 0:
            report_summary["main_net_pct"] = float(main_net_lots) / float(official_volume_lots) * 100.0
            report_summary["concentration_pct"] = float(main_net_lots) / float(official_volume_lots) * 100.0
        if concentration_lots is not None and official_volume_lots > 0:
            report_summary["concentration_pct"] = float(concentration_lots) / float(official_volume_lots) * 100.0
        if report_summary.get("short_term_buy_lots") is not None and official_volume_lots > 0:
            report_summary["short_term_buy_pct"] = float(report_summary["short_term_buy_lots"]) / float(official_volume_lots) * 100.0
        if report_summary.get("short_term_sell_lots") is not None and official_volume_lots > 0:
            report_summary["short_term_sell_pct"] = float(report_summary["short_term_sell_lots"]) / float(official_volume_lots) * 100.0
        if report_summary.get("buy_top5_lots") is not None and official_volume_lots > 0:
            report_summary["buy_top5_pct"] = float(report_summary["buy_top5_lots"]) / float(official_volume_lots) * 100.0
        if report_summary.get("sell_top5_lots") is not None and official_volume_lots > 0:
            report_summary["sell_top5_pct"] = float(report_summary["sell_top5_lots"]) / float(official_volume_lots) * 100.0

    return {
        "short_term_report": report,
        "history_row": latest_row,
        "institutional_detail": institutional_detail,
        "price_volume_state": price_volume_state,
        "volume_ratio_prev_day": volume_ratio_prev_day,
        "change_pct": change_pct,
        "official_volume_lots": official_volume_lots,
        "official_prev_volume_lots": official_prev_volume_lots,
        "quote_warning": quote_warning,
        "report_error": report_error,
        "report_deferred": report_deferred,
    }
