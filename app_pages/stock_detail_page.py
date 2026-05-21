from datetime import datetime, timedelta

import streamlit as st

from modules.data_sources.broker_branch_data import fetch_broker_branch_summary, fetch_broker_branch_trace
from modules.data_sources.price_cache import get_price_cache_status
from modules.data_sources.stock_db import find_security, get_stock_name
from modules.ui.ui_backtest_results import render_stock_detail_workspace


@st.cache_data(show_spinner=False, ttl=1800)
def _load_broker_branch_summary(stock_code: str):
    return fetch_broker_branch_summary(stock_code)


@st.cache_data(show_spinner=False, ttl=1800)
def _load_broker_branch_trace(detail_url: str):
    return fetch_broker_branch_trace(detail_url)


def _render_broker_branch_section(stock_code: str):
    st.markdown("---")
    st.subheader("券商分點")
    st.caption(
        "這裡先用 HiStock 公開頁做第一版分點觀察。官方 TWSE 查詢有驗證碼，FinMind 分點資料則需 sponsor 會員。"
    )

    try:
        summary_bundle = _load_broker_branch_summary(stock_code)
    except Exception as exc:
        st.warning(f"目前抓不到券商分點資料：{exc}")
        return

    buy_rows = summary_bundle.get("buy_side") or []
    sell_rows = summary_bundle.get("sell_side") or []
    if not buy_rows and not sell_rows:
        st.info("目前沒有可顯示的分點資料。")
        return

    header_cols = st.columns([1.2, 1.0, 1.0, 1.2])
    header_cols[0].metric("股票", summary_bundle.get("stock_code") or stock_code)
    header_cols[1].metric("買超分點數", len(buy_rows))
    header_cols[2].metric("賣超分點數", len(sell_rows))
    header_cols[3].link_button("查看來源頁", summary_bundle.get("source_url") or "https://histock.tw")

    table_cols = st.columns(2)
    with table_cols[0]:
        st.markdown("**買超分點排行**")
        st.dataframe(
            [row.to_display_dict() for row in buy_rows],
            use_container_width=True,
            hide_index=True,
        )
    with table_cols[1]:
        st.markdown("**賣超分點排行**")
        st.dataframe(
            [row.to_display_dict() for row in sell_rows],
            use_container_width=True,
            hide_index=True,
        )

    selection_options = []
    for side_label, rows in (("買超榜", buy_rows), ("賣超榜", sell_rows)):
        for index, row in enumerate(rows, start=1):
            selection_options.append(
                {
                    "label": f"{row.broker_branch}｜{side_label} #{index}",
                    "detail_url": row.detail_url,
                    "branch_name": row.broker_branch,
                }
            )

    if not selection_options:
        return

    selected_label = st.selectbox(
        "查看單一分點明細",
        options=[option["label"] for option in selection_options],
        key=f"broker_branch_select_{stock_code}",
    )
    selected_option = next(
        option for option in selection_options if option["label"] == selected_label
    )

    try:
        trace_bundle = _load_broker_branch_trace(selected_option["detail_url"])
    except Exception as exc:
        st.warning(f"目前抓不到 {selected_option['branch_name']} 的分點明細：{exc}")
        return

    trace_cols = st.columns(4)
    latest_net = trace_bundle.get("latest_net_shares")
    recent_5_net = trace_bundle.get("recent_5_net_shares")
    recent_20_net = trace_bundle.get("recent_20_net_shares")
    trace_cols[0].metric("選定分點", selected_option["branch_name"])
    trace_cols[1].metric("最新一日買賣超", f"{latest_net:,.1f} 張" if latest_net is not None else "-")
    trace_cols[2].metric("近5日買賣超", f"{recent_5_net:,.1f} 張")
    trace_cols[3].metric("近20日買賣超", f"{recent_20_net:,.1f} 張")

    st.caption(trace_bundle.get("title") or "券商分點個股進出")
    st.dataframe(
        trace_bundle.get("rows") or [],
        use_container_width=True,
        hide_index=True,
    )
    st.link_button("開啟這個分點來源頁", trace_bundle.get("source_url") or selected_option["detail_url"])


def render_stock_detail_page(state):
    st.subheader("個股詳頁")
    st.caption("直接查看單一股票的 K 線、均線、RSI、MACD 與布林通道，不必先跑回測。")

    default_start = st.session_state.get("stock_detail_start_date", datetime.now().date() - timedelta(days=365))
    default_end = st.session_state.get("stock_detail_end_date", datetime.now().date())

    control_cols = st.columns([1.3, 1.0, 1.0])
    stock_input = control_cols[0].text_input(
        "股票代碼 / yfinance symbol",
        value=st.session_state.get("stock_detail_input", "2330"),
        key="stock_detail_input",
        help="可輸入 2330、2330.TW 或其他已在主檔中的 symbol。",
    ).strip()
    start_date = control_cols[1].date_input(
        "開始日",
        value=default_start,
        key="stock_detail_start_date",
    )
    end_date = control_cols[2].date_input(
        "結束日",
        value=default_end,
        key="stock_detail_end_date",
    )

    if not stock_input:
        st.info("先輸入股票代碼，就會載入個股圖表。")
        return

    if start_date > end_date:
        st.error("開始日不能晚於結束日。")
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
    meta_cols = st.columns(4)
    meta_cols[0].metric("股票", stock_title)
    meta_cols[1].metric("市場", market_text)
    meta_cols[2].metric("快取筆數", f"{int(cache_status.get('row_count') or 0):,}")
    meta_cols[3].metric("快取最新日", cache_status.get("last_cached_date") or "尚未建立")

    if cache_status.get("fetch_status") == "failed":
        st.warning(f"最近一次補抓資料失敗：{cache_status.get('last_error')}")
    elif cache_status.get("last_checked_date"):
        st.caption(
            f"快取檢查到 {cache_status['last_checked_date']}，資料來源 {cache_status.get('source') or 'yfinance'}。"
        )

    render_stock_detail_workspace(
        symbol,
        stock_title,
        start_date=start_date,
        end_date=end_date,
        key_prefix="stock_detail_workspace",
    )

    stock_code = security["code"] if security else stock_input.split(".")[0]
    if stock_code:
        _render_broker_branch_section(stock_code)
