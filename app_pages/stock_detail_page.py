from datetime import datetime, timedelta
from textwrap import dedent
from typing import Any

import pandas as pd
import streamlit as st

from modules.core.trading_calendar import resolve_recent_trade_date, resolve_trade_dates_in_range
from modules.data_sources.broker_branch_data import fetch_broker_branch_summary, fetch_broker_branch_trace
from modules.data_sources.chip_data import get_institutional_detail_for_stock, get_recent_institutional_snapshots
from modules.data_sources.broker_branch_short_term import build_short_term_broker_report, build_today_chip_quick_report, format_short_term_summary
from modules.data_sources.market_watch import (
    fetch_tpex_after_market_quotes,
    fetch_tpex_daily_quotes,
    fetch_tpex_odd_lot_quotes,
    fetch_twse_after_market_quotes,
    fetch_twse_daily_quotes,
    fetch_twse_odd_lot_quotes,
)
from modules.data_sources.price_cache import get_price_cache_status
from modules.data_sources.stock_db import find_security, get_stock_name
from modules.ui.ui_stock_charts import render_streamlit_lightweight_chart


BROKER_BRANCH_CACHE_VERSION = "broker_branch_hybrid_v4"
TODAY_CHIP_CACHE_VERSION = "today_chip_v12"


@st.cache_data(show_spinner=False, ttl=1800)
def _load_broker_branch_summary(stock_code: str, trade_date_key: str, cache_version: str):
    return fetch_broker_branch_summary(stock_code, top_n=15, trade_date=trade_date_key)


@st.cache_data(show_spinner=False, ttl=1800)
def _load_broker_branch_trace(detail_url: str):
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
def _load_short_term_broker_report(stock_code: str, trade_date_key: str, cache_version: str):
    return build_short_term_broker_report(stock_code)


@st.cache_data(show_spinner=False, ttl=1800)
def _load_short_term_broker_report_window(stock_code: str, days_window: int, trade_date_key: str, cache_version: str):
    return build_short_term_broker_report(stock_code, days_window=days_window)


def _build_deferred_today_chip_report(stock_code: str, trade_date_key: str) -> dict[str, Any]:
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


def _format_pct_text(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}%"


def _format_lots_text(value):
    if value is None:
        return "-"
    return f"{float(value):,.0f} 張"


def _format_signed_lots_text(value):
    if value is None:
        return "-"
    number = float(value)
    if abs(number) < 0.0001:
        return "0 張"
    return f"{number:+,.0f} 張"


def _format_price_text(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def _format_profit_k_text(value):
    if value is None:
        return "-"
    number = float(value)
    if abs(number) < 0.0001:
        return "0.0"
    return f"{number:+,.1f}"


def _format_close_text(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}"


def _row_value(row: dict[str, Any], *keys: str):
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _format_ratio_text(value):
    if value is None:
        return "-"
    return f"{float(value):.2f}x"


def _format_net_lots_metric(value):
    if value is None:
        return "-"
    return f"{float(value)/1000:+,.0f} 張"


def _latest_market_date_key(anchor_date=None) -> str:
    probe_date = anchor_date or datetime.now().date()
    resolved = resolve_recent_trade_date(probe_date)
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


def _load_official_volume_lots(stock_code: str, probe_date) -> float | None:
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
    else:
        # TPEx 補零股/盤後端點偏慢，先收斂成只補上市總量，
        # 上櫃暫時沿用一般盤成交量，避免拖慢個股詳頁第一屏。
        pass

    return total_volume_shares / 1000.0


@st.cache_data(show_spinner=False, ttl=1800)
def _load_official_snapshot_pair(stock_code: str, end_date_key: str, security_market: str | None) -> dict[str, Any]:
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
        else:
            # 上櫃先不補零股/盤後，避免 TPEx 盤後大表拖慢第一屏。
            pass
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
def _load_basic_quote_pair(stock_code: str, end_date_key: str, security_market: str | None) -> dict[str, Any]:
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
def _load_today_chip_snapshot(stock_code: str, symbol: str, end_date, cache_version: str):
    trade_date_key = _latest_market_date_key(end_date)
    security = find_security(stock_code) or {}
    security_market = security.get("market")

    report = _build_deferred_today_chip_report(stock_code, trade_date_key)
    report_error = None
    report_deferred = True

    # 第一屏優先快開，只吃基本日行情；零股/盤後總量改到後續再補。
    # 這樣「今日籌碼」不會因為官方補量端點變慢而整塊卡住。
    quote_warning = None
    quote_payload = _load_basic_quote_pair(stock_code, trade_date_key, security_market)

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
            report = _build_deferred_today_chip_report(stock_code, latest_row.get("trade_date") or trade_date_key)
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


def _inject_stock_detail_css():
    st.html("""
        <style>
        .stock-today-hero {
            display:grid;
            grid-template-columns: minmax(260px, 0.95fr) minmax(260px, 0.95fr);
            gap: 18px;
            margin: 0.35rem 0 1rem 0;
        }
        .stock-today-topline {
            display:grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 14px;
            margin: 0.35rem 0 1rem 0;
        }
        .stock-today-top-card {
            border:1px solid rgba(248,250,252,0.12);
            border-radius: 20px;
            background: rgba(15,23,42,0.72);
            padding: 1rem 1.15rem;
        }
        .stock-today-top-label {
            color:#94a3b8;
            font-size:0.9rem;
            font-weight:700;
        }
        .stock-today-top-value {
            color:#f8fafc;
            font-size:2.2rem;
            font-weight:900;
            margin-top:0.4rem;
            line-height:1.05;
        }
        .stock-today-top-value.is-bull { color: #fb7185; }
        .stock-today-top-value.is-bear { color: #22c55e; }
        .stock-today-top-note {
            color:#94a3b8;
            margin-top:0.3rem;
            font-size:0.88rem;
            font-weight:700;
        }
        .stock-today-main {
            border:1px solid rgba(248,250,252,0.12);
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(15,23,42,0.92), rgba(24,31,46,0.95));
            padding: 1.35rem 1.5rem;
        }
        .stock-today-kicker {
            color: #94a3b8;
            font-size: 0.95rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .stock-today-value {
            margin-top: 0.42rem;
            font-size: 3rem;
            font-weight: 900;
            line-height: 1;
            letter-spacing: -0.03em;
            color: #f8fafc;
        }
        .stock-today-value.is-bull { color: #fb7185; }
        .stock-today-value.is-bear { color: #22c55e; }
        .stock-today-value.is-neutral { color: #f8fafc; }
        .stock-today-sub {
            margin-top: 0.55rem;
            color: #cbd5e1;
            font-size: 1rem;
            line-height: 1.45;
        }
        .stock-today-grid {
            display:grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin: 0.8rem 0 1rem 0;
        }
        .stock-today-mini {
            border:1px solid rgba(248,250,252,0.12);
            border-radius: 20px;
            background: rgba(15,23,42,0.72);
            padding: 1rem 1.1rem;
        }
        .stock-today-mini-label {
            color:#94a3b8;
            font-size:0.9rem;
            font-weight:700;
        }
        .stock-today-mini-value {
            color:#f8fafc;
            font-size:1.7rem;
            font-weight:900;
            margin-top:0.35rem;
            line-height:1.05;
        }
        .stock-today-mini-note {
            color:#94a3b8;
            margin-top:0.3rem;
            font-size:0.9rem;
            font-weight:700;
        }
        .stock-today-alert-grid {
            display:grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin: 0.65rem 0 1rem 0;
        }
        .stock-today-alert {
            border-radius: 16px;
            padding: 0.95rem 1.1rem;
            border: 1px solid rgba(250, 204, 21, 0.18);
            background: linear-gradient(135deg, rgba(120,53,15,0.20), rgba(59,7,18,0.14));
            color: #fde68a;
            font-weight: 700;
        }
        .stock-today-alert.is-danger {
            border-color: rgba(251,113,133,0.22);
            background: linear-gradient(135deg, rgba(76,5,25,0.30), rgba(127,29,29,0.16));
            color: #fecdd3;
        }
        .stock-today-alert.is-good {
            border-color: rgba(34,197,94,0.22);
            background: linear-gradient(135deg, rgba(21,128,61,0.22), rgba(20,83,45,0.18));
            color: #bbf7d0;
        }
        .stock-short-term-hero {
            display:grid;
            grid-template-columns: minmax(240px, 0.95fr) minmax(320px, 1.05fr);
            gap: 18px;
            margin: 0.4rem 0 1rem 0;
        }
        .stock-short-term-main {
            border:1px solid rgba(248,250,252,0.12);
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(15,23,42,0.92), rgba(24,31,46,0.95));
            padding: 1.35rem 1.5rem;
        }
        .stock-short-term-kicker {
            color: #94a3b8;
            font-size: 0.95rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .stock-short-term-signal {
            margin-top: 0.4rem;
            font-size: 3.4rem;
            font-weight: 900;
            line-height: 1;
            letter-spacing: -0.03em;
            color: #f8fafc;
        }
        .stock-short-term-signal.is-bull { color: #fb7185; }
        .stock-short-term-signal.is-bear { color: #22c55e; }
        .stock-short-term-signal.is-neutral { color: #f8fafc; }
        .stock-short-term-reason {
            margin-top: 0.65rem;
            color: #cbd5e1;
            font-size: 1rem;
        }
        .stock-short-term-grid {
            display:grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
        }
        .stock-short-term-mini {
            border:1px solid rgba(248,250,252,0.12);
            border-radius: 20px;
            background: rgba(15,23,42,0.72);
            padding: 1rem 1.1rem;
        }
        .stock-short-term-mini-label {
            color:#94a3b8;
            font-size:0.9rem;
            font-weight:700;
        }
        .stock-short-term-mini-value {
            color:#f8fafc;
            font-size:1.85rem;
            font-weight:900;
            margin-top:0.35rem;
            line-height:1.05;
        }
        .stock-short-term-alert {
            border-radius: 18px;
            padding: 0.95rem 1.15rem;
            margin: 0.7rem 0;
            border: 1px solid rgba(250, 204, 21, 0.18);
            background: linear-gradient(135deg, rgba(120,53,15,0.22), rgba(59,7,18,0.2));
            color: #fde68a;
            font-weight: 700;
        }
        .stock-short-term-alert.is-danger {
            border-color: rgba(251,113,133,0.22);
            background: linear-gradient(135deg, rgba(76,5,25,0.32), rgba(127,29,29,0.18));
            color: #fecdd3;
        }
        .stock-short-term-rank-grid {
            display:grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 18px;
            margin-top: 1rem;
        }
        .stock-short-term-rank-panel {
            border:1px solid rgba(248,250,252,0.12);
            border-radius: 24px;
            overflow: hidden;
            background: rgba(15,23,42,0.58);
        }
        .stock-short-term-rank-head {
            padding: 1rem 1.2rem;
            font-size: 1.45rem;
            font-weight: 900;
            border-bottom: 1px solid rgba(248,250,252,0.10);
        }
        .stock-short-term-rank-head.is-buy {
            color: #fb7185;
            background: linear-gradient(135deg, rgba(88,28,46,0.82), rgba(60,18,33,0.78));
        }
        .stock-short-term-rank-head.is-sell {
            color: #4ade80;
            background: linear-gradient(135deg, rgba(18,67,52,0.82), rgba(19,52,43,0.78));
        }
        .stock-short-term-rank-row {
            display:grid;
            grid-template-columns: 120px minmax(180px, 1.2fr) minmax(180px, 0.95fr);
            gap: 16px;
            align-items:center;
            padding: 1.05rem 1.2rem;
            border-top: 1px solid rgba(248,250,252,0.08);
        }
        .stock-short-term-rank-row:first-child {
            border-top: none;
        }
        .stock-short-term-rank-left {
            display:flex;
            flex-direction:column;
            gap: 0.12rem;
        }
        .stock-short-term-rank-weight {
            color:#f8fafc;
            font-size: 1.15rem;
            font-weight: 900;
        }
        .stock-short-term-rank-net {
            color:#cbd5e1;
            font-size: 0.9rem;
            font-weight: 700;
        }
        .stock-short-term-rank-center {
            min-width: 0;
        }
        .stock-short-term-rank-branch {
            color:#f8fafc;
            font-size: 1.25rem;
            font-weight: 900;
            line-height: 1.15;
            word-break: break-word;
        }
        .stock-short-term-rank-tagline {
            color:#94a3b8;
            margin-top: 0.3rem;
            font-size: 0.96rem;
            word-break: break-word;
        }
        .stock-short-term-rank-right {
            display:flex;
            flex-direction:column;
            gap: 0.18rem;
            text-align:right;
        }
        .stock-short-term-rank-price {
            color:#f8fafc;
            font-size: 1rem;
            font-weight: 800;
        }
        .stock-short-term-rank-profit {
            font-size: 1.3rem;
            font-weight: 900;
        }
        .stock-short-term-rank-profit.is-buy { color:#fb7185; }
        .stock-short-term-rank-profit.is-sell { color:#4ade80; }
        .stock-short-term-rank-note {
            color:#94a3b8;
            font-size: 0.92rem;
            font-weight: 700;
        }
        .stock-short-term-rank-caption {
            color:#cbd5e1;
            font-size: 0.98rem;
            margin-top: 0.8rem;
        }
        @media (max-width: 900px) {
            .stock-today-topline {
                grid-template-columns: 1fr;
            }
            .stock-today-hero {
                grid-template-columns: 1fr;
            }
            .stock-today-grid {
                grid-template-columns: 1fr 1fr;
            }
            .stock-today-alert-grid {
                grid-template-columns: 1fr;
            }
            .stock-short-term-hero {
                grid-template-columns: 1fr;
            }
            .stock-short-term-grid {
                grid-template-columns: 1fr 1fr;
            }
            .stock-short-term-signal {
                font-size: 2.8rem;
            }
            .stock-short-term-rank-grid {
                grid-template-columns: 1fr;
            }
            .stock-short-term-rank-row {
                grid-template-columns: 1fr;
                gap: 0.7rem;
            }
            .stock-short-term-rank-right {
                text-align:left;
            }
        }
        </style>
        """)


def _render_today_chip_section(stock_code: str, symbol: str, end_date):
    st.markdown("### 今日籌碼")
    _inject_stock_detail_css()

    try:
        payload = _load_today_chip_snapshot(stock_code, symbol, end_date, TODAY_CHIP_CACHE_VERSION)
    except Exception as exc:
        st.warning(f"目前抓不到今日籌碼資料：{exc}")
        return

    quote_warning = payload.get("quote_warning")
    report_error = payload.get("report_error")
    report_deferred = bool(payload.get("report_deferred"))

    report = payload.get("short_term_report") or {}
    summary = report.get("summary") or {}
    summary_text = format_short_term_summary(report)
    signal_label = summary_text["主力動向"]
    signal_class = "is-neutral"
    if signal_label in {"大買", "偏多集中"}:
        signal_class = "is-bull"
    elif signal_label in {"大賣", "偏空集中"}:
        signal_class = "is-bear"

    price_state_label, price_state_reason = payload.get("price_volume_state") or ("量價中性", "目前沒有特別明顯的價量偏態。")
    state_class = "is-neutral"
    if price_state_label in {"放量上攻", "量縮墊高"}:
        state_class = "is-bull"
    elif price_state_label in {"放量下殺", "量縮回檔"}:
        state_class = "is-bear"

    history_row = payload.get("history_row") or {}
    close_text = _format_close_text(_row_value(history_row, "close", "Close"))
    change_pct_text = _format_pct_text(payload.get("change_pct"))
    display_volume_lots = payload.get("official_volume_lots")
    if display_volume_lots is None:
        fallback_volume = _row_value(history_row, "volume", "Volume")
        display_volume_lots = (fallback_volume or 0.0) / 1000.0 if fallback_volume is not None else None
    volume_text = _format_lots_text(display_volume_lots)
    summary_text["成交量"] = volume_text
    volume_growth_text = _format_ratio_text(payload.get("volume_ratio_prev_day"))
    top_close_class = "is-neutral"
    change_pct_value = payload.get("change_pct")
    if change_pct_value is not None:
        if change_pct_value > 0:
            top_close_class = "is-bull"
        elif change_pct_value < 0:
            top_close_class = "is-bear"
    top_line_html = dedent(
        f"""
        <div class="stock-today-topline">
            <div class="stock-today-top-card">
                <div class="stock-today-top-label">收盤價</div>
                <div class="stock-today-top-value {top_close_class}">{close_text}</div>
                <div class="stock-today-top-note">資料日 {history_row.get("trade_date") or report.get("trade_date") or '-'}</div>
            </div>
            <div class="stock-today-top-card">
                <div class="stock-today-top-label">漲跌幅</div>
                <div class="stock-today-top-value {top_close_class}">{change_pct_text}</div>
                <div class="stock-today-top-note">相對前一交易日</div>
            </div>
            <div class="stock-today-top-card">
                <div class="stock-today-top-label">成交量</div>
                <div class="stock-today-top-value">{volume_text}</div>
                <div class="stock-today-top-note">量增幅 {volume_growth_text}</div>
            </div>
        </div>
        """
    ).strip()
    st.html(top_line_html)
    hero_html = dedent(
        f"""
        <div class="stock-today-hero">
            <div class="stock-today-main">
                <div class="stock-today-kicker">主力動向</div>
                <div class="stock-today-value {signal_class}">{signal_label}</div>
                <div class="stock-today-sub">{summary.get("signal_reason") or "以前15大買超與賣超分點的差額，搭配籌碼集中度來判斷主力動向。"} </div>
            </div>
            <div class="stock-today-main">
                <div class="stock-today-kicker">今日價量</div>
                <div class="stock-today-value {state_class}">{price_state_label}</div>
                <div class="stock-today-sub">收盤 {close_text}｜漲跌幅 {change_pct_text}｜成交量 {volume_text}｜量增幅 {volume_growth_text}<br>{price_state_reason}</div>
            </div>
        </div>
        """
    ).strip()
    st.html(hero_html)

    today_grid_html = dedent(
        f"""
        <div class="stock-today-grid">
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">籌碼集中</div>
                <div class="stock-today-mini-value">{summary_text["籌碼集中"]}</div>
                <div class="stock-today-mini-note">前15大買超分點合計－前15大賣超分點合計</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">籌碼集中度</div>
                <div class="stock-today-mini-value">{summary_text["籌碼集中度"]}</div>
                <div class="stock-today-mini-note">籌碼集中 ÷ 區間總成交張數</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">成交量</div>
                <div class="stock-today-mini-value">{summary_text["成交量"]}</div>
                <div class="stock-today-mini-note">資料日 {history_row.get("trade_date") or report.get("trade_date") or '-'}</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">成交量增幅</div>
                <div class="stock-today-mini-value">{_format_ratio_text(payload.get("volume_ratio_prev_day"))}</div>
                <div class="stock-today-mini-note">相對前一日成交量</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">區間週轉率</div>
                <div class="stock-today-mini-value">{summary_text["區間週轉率"]}</div>
                <div class="stock-today-mini-note">區間總成交量 ÷ 公司發行總股本</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">估股本比重</div>
                <div class="stock-today-mini-value">{summary_text["估股本比重"]}</div>
                <div class="stock-today-mini-note">籌碼集中 ÷ 公司發行總股本</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">分點集中張數</div>
                <div class="stock-today-mini-value">{_format_lots_text(summary.get("concentration_lots"))}</div>
                <div class="stock-today-mini-note">與籌碼集中同步，方便對照主力吸納規模</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">分點集中度</div>
                <div class="stock-today-mini-value">{_format_pct_text(max(summary.get("buy_top5_pct") or 0.0, summary.get("sell_top5_pct") or 0.0))}</div>
                <div class="stock-today-mini-note">前五大分點相對成交量占比</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">短衝買超占比</div>
                <div class="stock-today-mini-value">{summary_text["短衝買超占比"]}</div>
                <div class="stock-today-mini-note">已知短衝 / 隔日沖分點買超占量</div>
            </div>
            <div class="stock-today-mini">
                <div class="stock-today-mini-label">短衝賣超占比</div>
                <div class="stock-today-mini-value">{summary_text["短衝賣超占比"]}</div>
                <div class="stock-today-mini-note">已知短衝 / 隔日沖分點賣超占量</div>
            </div>
        </div>
        """
    ).strip()
    st.html(today_grid_html)

    if quote_warning:
        st.info(f"今日總量補值逾時，先用一般盤日行情顯示：{quote_warning}")
    if report_deferred:
        st.caption("第一屏先顯示價量與法人摘要；分點榜與短衝分析會在後面的分頁再載入。")
    if report_error:
        st.warning(f"分點資料暫時退回簡化模式：{report_error}")

    institutional = payload.get("institutional_detail") or {}
    institution_cols = st.columns(4)
    institution_cols[0].metric("外資", _format_net_lots_metric(institutional.get("foreign_net")))
    institution_cols[1].metric("投信", _format_net_lots_metric(institutional.get("trust_net")))
    institution_cols[2].metric("自營商", _format_net_lots_metric(institutional.get("dealer_net")))
    institution_cols[3].metric("三大法人", _format_net_lots_metric(institutional.get("total_net")))

    alerts = list(report.get("alerts") or [])
    if price_state_label == "放量上攻":
        alerts.insert(0, "提醒：今天屬於放量上攻，若同時短衝買超占比高，隔日沖接力與倒貨都要留意。")
    elif price_state_label == "放量下殺":
        alerts.insert(0, "提醒：今天屬於放量下殺，若賣方短衝席次偏多，短線壓力通常不小。")
    elif price_state_label == "量縮整理":
        alerts.insert(0, "提醒：今天量縮整理，先觀察主力席次是否開始集中，通常比追價更重要。")
    if institutional.get("trust_net") and institutional["trust_net"] > 0:
        alerts.append("加分：投信當日偏買，若分點也同步集中，後續續強機率會更高。")
    if institutional.get("foreign_net") and institutional["foreign_net"] < 0 and (summary.get("short_term_sell_pct") or 0) >= 8:
        alerts.append("提醒：外資偏賣且短衝席次賣超偏高，短線隔日沖壓力提高。")

    if alerts:
        alert_boxes = []
        for alert in alerts[:4]:
            variant = "is-danger" if ("壓力" in alert or "賣超" in alert or "下殺" in alert) else "is-good" if ("加分" in alert or "上攻" in alert) else ""
            alert_boxes.append(f"<div class='stock-today-alert {variant}'>{alert}</div>")
        st.html(f"<div class='stock-today-alert-grid'>{''.join(alert_boxes)}</div>")


def _render_short_term_broker_section(stock_code: str):
    st.markdown("### 短衝主力 / 分點日報")
    _inject_stock_detail_css()
    trade_date_key = _latest_market_date_key()

    days_window = st.segmented_control(
        "統計天數",
        options=[1, 3, 5, 10, 20],
        default=1,
        key=f"short_term_days_{stock_code}",
        format_func=lambda value: f"近 {value} 日",
    )

    try:
        report = _load_short_term_broker_report_window(
            stock_code,
            int(days_window or 1),
            trade_date_key,
            BROKER_BRANCH_CACHE_VERSION,
        )
    except Exception as exc:
        st.warning(f"目前抓不到短衝主力分點資料：{exc}")
        return

    summary = report.get("summary") or {}
    summary_text = format_short_term_summary(report)
    signal_label = summary_text["主力動向"]
    signal_class = "is-neutral"
    if signal_label in {"大買", "偏多集中"}:
        signal_class = "is-bull"
    elif signal_label in {"大賣", "偏空集中"}:
        signal_class = "is-bear"

    concentration_lots = summary.get("concentration_lots") or 0.0
    concentration_pct = summary.get("concentration_pct") or 0.0
    short_term_net_lots = (summary.get("short_term_buy_lots") or 0.0) - (summary.get("short_term_sell_lots") or 0.0)
    short_term_seats = int(summary.get("short_term_buy_count") or 0) + int(summary.get("short_term_sell_count") or 0)

    reason = summary.get("signal_reason")
    hero_html = dedent(
        f"""
        <div class="stock-short-term-hero">
            <div class="stock-short-term-main">
                <div class="stock-short-term-kicker">近 {report.get('days_window') or 1} 日主力動向</div>
                <div class="stock-short-term-signal {signal_class}">{signal_label}</div>
                <div class="stock-short-term-reason">{reason or "目前買賣力道接近，先觀察分點集中度。"}</div>
            </div>
            <div class="stock-short-term-grid">
                <div class="stock-short-term-mini">
                    <div class="stock-short-term-mini-label">籌碼集中</div>
                    <div class="stock-short-term-mini-value">{_format_lots_text(concentration_lots)}</div>
                </div>
                <div class="stock-short-term-mini">
                    <div class="stock-short-term-mini-label">籌碼集中度</div>
                    <div class="stock-short-term-mini-value">{_format_pct_text(concentration_pct)}</div>
                </div>
                <div class="stock-short-term-mini">
                    <div class="stock-short-term-mini-label">估股本比重</div>
                    <div class="stock-short-term-mini-value">{summary_text["估股本比重"]}</div>
                </div>
                <div class="stock-short-term-mini">
                    <div class="stock-short-term-mini-label">區間週轉率</div>
                    <div class="stock-short-term-mini-value">{summary_text["區間週轉率"]}</div>
                </div>
            </div>
        </div>
        """
    ).strip()
    st.html(hero_html)

    quick_metrics = st.columns(3)
    quick_metrics[0].metric("成交量", summary_text["成交量"])
    quick_metrics[1].metric("短衝席次", short_term_seats)
    quick_metrics[2].metric("短衝淨差", _format_lots_text(short_term_net_lots))

    if report.get("history_mode") == "current_snapshot_only" and (report.get("days_window") or 1) > 1:
        st.info("目前分點來源改為 Yahoo 當日榜單。近 3 / 5 / 10 / 20 日先沿用當日主力榜做觀察，單一分點歷史之後再接官方快照。")

    alerts = report.get("alerts") or []
    if not alerts:
        st.html(
            "<div class='stock-short-term-alert'>提醒：目前沒有明顯短衝席次異常，但仍可持續觀察買賣榜是否由固定分點反覆進出。</div>"
        )
    else:
        for alert in alerts:
            danger = " is-danger" if ("賣超" in alert or "偏空" in (reason or "")) else ""
            st.html(f"<div class='stock-short-term-alert{danger}'>{alert}</div>")

    meta_cols = st.columns([1.2, 1.0, 1.0, 1.2])
    meta_cols[0].metric("股票", report.get("stock_title") or stock_code)
    meta_cols[1].metric("短衝買方席次", int(summary.get("short_term_buy_count") or 0))
    meta_cols[2].metric("短衝賣方席次", int(summary.get("short_term_sell_count") or 0))
    source_url = report.get("source_url") or ""
    if source_url:
        meta_cols[3].link_button("查看來源頁", source_url)
    else:
        meta_cols[3].metric("來源", report.get("source_label") or "官方匯入資料")
    source_label = report.get("source_label") or "分點榜來源"
    st.caption(f"目前分點來源：{source_label}")
    is_yahoo_fallback = "Yahoo" in source_label

    buy_rows = report.get("buy_rows") or []
    sell_rows = report.get("sell_rows") or []

    def _render_rank_panel(rows, *, title: str, variant: str, caption: str):
        panel_rows = []
        for row in rows[:15]:
            tag_labels = [tag for tag in row.get("tag_labels") or [] if tag]
            group_labels = [group for group in row.get("group_labels") or [] if group]
            tag_pieces = tag_labels + [group for group in group_labels if group not in tag_labels]
            if row.get("active_days"):
                tag_pieces.append(f"近{report.get('days_window') or 1}日活躍 {int(row['active_days'])} 天")
            tag_line = " / ".join(tag_pieces) if tag_pieces else "一般分點"
            right_lines = []
            if not is_yahoo_fallback and row.get("avg_price_value") is not None:
                right_lines.append(
                    f'<div class="stock-short-term-rank-price">均價 {_format_price_text(row.get("avg_price_value"))}</div>'
                )
            if not is_yahoo_fallback and row.get("total_profit_k_value") is not None:
                right_lines.append(
                    f'<div class="stock-short-term-rank-profit {variant}">損益 {_format_profit_k_text(row.get("total_profit_k_value"))} 萬</div>'
                )
            right_lines.append(
                f'<div class="stock-short-term-rank-note">買進 {row.get("buy_shares") or "-"} ｜ 賣出 {row.get("sell_shares") or "-"}</div>'
            )
            panel_rows.append(
                dedent(
                    f"""
                    <div class="stock-short-term-rank-row">
                        <div class="stock-short-term-rank-left">
                            <div class="stock-short-term-rank-weight">{_format_pct_text(row.get('weight_pct'))}</div>
                            <div class="stock-short-term-rank-net">{_format_signed_lots_text(row.get('net_lots_value'))}</div>
                        </div>
                        <div class="stock-short-term-rank-center">
                            <div class="stock-short-term-rank-branch">{row.get('broker_branch') or '-'}</div>
                            <div class="stock-short-term-rank-tagline">{tag_line}</div>
                        </div>
                        <div class="stock-short-term-rank-right">
                            {''.join(right_lines)}
                        </div>
                    </div>
                    """
                ).strip()
            )
        rows_html = "".join(panel_rows) or "<div class='stock-short-term-rank-row'><div class='stock-short-term-rank-center'><div class='stock-short-term-rank-branch'>目前沒有資料</div></div></div>"
        return dedent(
            f"""
            <div>
                <div class="stock-short-term-rank-panel">
                    <div class="stock-short-term-rank-head {variant}">{title}</div>
                    {rows_html}
                </div>
                <div class="stock-short-term-rank-caption">{caption}</div>
            </div>
            """
        ).strip()

    panels_html = dedent(
        f"""
        <div class="stock-short-term-rank-grid">
            {_render_rank_panel(buy_rows, title='買方 Top15', variant='is-buy', caption='先看哪些分點真的在抬轎，是否有已知短衝席次集中進場。')}
            {_render_rank_panel(sell_rows, title='賣方 Top15', variant='is-sell', caption='再看誰在倒貨，若短衝分點同時出現在賣方前排，隔日沖壓力通常更大。')}
        </div>
        """
    ).strip()
    st.html(panels_html)


def _render_broker_branch_section(stock_code: str):
    st.markdown("### 券商分點明細")
    trade_date_key = _latest_market_date_key()

    try:
        summary_bundle = _load_broker_branch_summary(stock_code, trade_date_key, BROKER_BRANCH_CACHE_VERSION)
    except Exception as exc:
        st.warning(f"目前抓不到券商分點資料：{exc}")
        return

    buy_rows = summary_bundle.get("buy_side") or []
    sell_rows = summary_bundle.get("sell_side") or []
    if not buy_rows and not sell_rows:
        st.info("目前沒有可顯示的分點資料。")
        return

    header_cols = st.columns([1.2, 1.0, 1.0, 1.2])
    header_cols[0].metric("股票", summary_bundle.get("stock_title") or summary_bundle.get("stock_code") or stock_code)
    header_cols[1].metric("買超分點數", len(buy_rows))
    header_cols[2].metric("賣超分點數", len(sell_rows))
    source_url = summary_bundle.get("source_url") or ""
    if source_url:
        header_cols[3].link_button("查看來源頁", source_url)
    else:
        header_cols[3].metric("來源", summary_bundle.get("source_label") or "官方匯入資料")
    st.caption(f"目前分點來源：{summary_bundle.get('source_label') or '分點榜來源'}")

    def _compact_branch_table(rows):
        return [
            {
                "分點": row.broker_branch,
                "買賣超(張)": row.net_shares,
                "買張": row.buy_shares,
                "賣張": row.sell_shares,
            }
            for row in rows
        ]

    table_cols = st.columns(2)
    with table_cols[0]:
        st.markdown("**買超分點排行**")
        st.dataframe(
            _compact_branch_table(buy_rows),
            use_container_width=True,
            hide_index=True,
        )
    with table_cols[1]:
        st.markdown("**賣超分點排行**")
        st.dataframe(
            _compact_branch_table(sell_rows),
            use_container_width=True,
            hide_index=True,
        )
    if "Yahoo" in str(summary_bundle.get("source_label") or ""):
        st.info("目前 Yahoo 來源只提供當日買賣分點榜，單一分點歷史明細、均價與損益暫時不提供。")
    else:
        st.info("目前顯示的是官方匯入分點日報；如果你補匯更多交易日，後面可以直接擴充成多日分點統計。")


def render_stock_detail_page(state):
    default_start = st.session_state.get("stock_detail_start_date", datetime.now().date() - timedelta(days=365))
    default_end = st.session_state.get("stock_detail_end_date", datetime.now().date())

    stock_input = st.text_input(
        "股票代碼 / yfinance symbol",
        value=st.session_state.get("stock_detail_input", "2330"),
        key="stock_detail_input",
        help="可輸入 2330、2330.TW 或其他已在主檔中的 symbol。",
    ).strip()

    if not stock_input:
        st.info("先輸入股票代碼，就會載入個股圖表。")
        return

    security = find_security(stock_input)
    if security:
        symbol = security["yfinance_symbol"]
        stock_title = f"{security['name_zh']} ({symbol})"
        market_text = security.get("market") or "-"
    else:
        normalized = stock_input.upper()
        symbol = normalized if "." in normalized else f"{normalized}.TW"
        stock_title = f"{get_stock_name(normalized)} ({symbol})"
        market_text = "未辨識"

    cache_status = get_price_cache_status(symbol)
    display_code = security["code"] if security else stock_input.split(".")[0]

    st.markdown(f"## {get_stock_name(display_code)} ({display_code})")
    meta_cols = st.columns(3)
    meta_cols[0].metric("市場", market_text)
    meta_cols[1].metric("快取筆數", f"{int(cache_status.get('row_count') or 0):,}")
    meta_cols[2].metric("快取最新日", cache_status.get("last_cached_date") or "尚未建立")

    if cache_status.get("fetch_status") == "failed":
        st.warning(f"最近一次補抓資料失敗：{cache_status.get('last_error')}")
    elif cache_status.get("last_checked_date"):
        st.caption(
            f"快取檢查到 {cache_status['last_checked_date']}，資料來源 {cache_status.get('source') or 'yfinance'}。"
        )

    stock_code = display_code
    selected_section = st.segmented_control(
        "個股詳頁分頁",
        options=["今日籌碼", "技術線圖", "短衝主力", "分點明細"],
        default="今日籌碼",
        key="stock_detail_section",
        label_visibility="collapsed",
    )

    if selected_section == "今日籌碼":
        _render_today_chip_section(stock_code, symbol, default_end)
    elif selected_section == "技術線圖":
        chart_cols = st.columns(2)
        start_date = chart_cols[0].date_input(
            "開始日",
            value=default_start,
            key="stock_detail_start_date",
        )
        end_date = chart_cols[1].date_input(
            "結束日",
            value=default_end,
            key="stock_detail_end_date",
        )
        with st.expander("圖表指標", expanded=False):
            indicator_cols = st.columns(2)
            visible_price_indicators = indicator_cols[0].multiselect(
                "價格指標",
                options=["MA5", "MA10", "MA20", "MA60", "MA120"],
                default=["MA5", "MA10", "MA20", "MA60"],
                key="stock_detail_price_indicators",
            )
            visible_volume_indicators = indicator_cols[1].multiselect(
                "量能指標",
                options=["MV5", "MV20"],
                default=["MV5", "MV20"],
                key="stock_detail_volume_indicators",
            )
        if start_date > end_date:
            st.error("開始日不能晚於結束日。")
        else:
            render_streamlit_lightweight_chart(
                symbol,
                stock_title,
                start_date=start_date,
                end_date=end_date,
                key_prefix="stock_detail_workspace",
                stock_code=stock_code,
                market_label=market_text,
                visible_price_indicators=visible_price_indicators,
                visible_volume_indicators=visible_volume_indicators,
            )
    elif stock_code and selected_section == "短衝主力":
        _render_short_term_broker_section(stock_code)
    elif stock_code and selected_section == "分點明細":
        _render_broker_branch_section(stock_code)
