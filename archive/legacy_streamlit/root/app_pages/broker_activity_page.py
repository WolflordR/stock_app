import pandas as pd
import streamlit as st

from modules.core.trading_calendar import resolve_after_hours_trade_date
from modules.data_sources.broker_branch_aggregate import load_branch_dropdown_options, scan_branch_totals
from modules.data_sources.official_broker_import import get_official_broker_db_overview
from modules.data_sources.stock_db import get_securities_in_range


def _format_share(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.0f}"


def _format_price(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}"


def _format_amount(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.0f}"


def _format_pct(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def _build_branch_totals_table(source_df: pd.DataFrame, *, direction: str) -> pd.DataFrame:
    if source_df.empty:
        return pd.DataFrame()

    display_df = source_df.copy()
    display_df["市場"] = display_df["market"].map(lambda value: "上市" if value == "TWSE" else "上櫃")
    display_df["收盤價"] = display_df["close_price"].map(_format_price)
    display_df["買進張數"] = display_df["buy_shares"].map(_format_share)
    display_df["賣出張數"] = display_df["sell_shares"].map(_format_share)
    display_df["淨張數"] = display_df["net_shares"].map(_format_share)
    display_df["買進金額估算"] = display_df["buy_amount"].map(_format_amount)
    display_df["賣出金額估算"] = display_df["sell_amount"].map(_format_amount)
    display_df["淨金額估算"] = display_df["net_amount"].map(_format_amount)
    ratio_column = "buy_turnover_pct" if direction == "buy" else "sell_turnover_pct"
    display_df["占當天成交比"] = display_df[ratio_column].map(_format_pct)
    return display_df[
        [
            "市場",
            "stock_code",
            "stock_name",
            "收盤價",
            "買進張數",
            "賣出張數",
            "淨張數",
            "買進金額估算",
            "賣出金額估算",
            "淨金額估算",
            "占當天成交比",
        ]
    ].rename(columns={"stock_code": "代碼", "stock_name": "名稱"})


def _render_branch_result_tables(branch_query: str, result_df: pd.DataFrame):
    if result_df.empty:
        st.info("這個分點今天沒有掃到買進或賣出的股票。")
        return

    buy_df = result_df[result_df["buy_shares"] > 0].sort_values(["buy_amount", "buy_shares"], ascending=[False, False]).copy()
    sell_df = result_df[result_df["sell_shares"] > 0].sort_values(["sell_amount", "sell_shares"], ascending=[False, False]).copy()

    table_cols = st.columns(2)
    with table_cols[0]:
        st.markdown(f"**{branch_query} 總買進**")
        if buy_df.empty:
            st.info("今天沒有買進資料。")
        else:
            st.dataframe(_build_branch_totals_table(buy_df, direction="buy"), use_container_width=True, hide_index=True)
    with table_cols[1]:
        st.markdown(f"**{branch_query} 總賣出**")
        if sell_df.empty:
            st.info("今天沒有賣出資料。")
        else:
            st.dataframe(_build_branch_totals_table(sell_df, direction="sell"), use_container_width=True, hide_index=True)


def render_broker_activity_page(_state):
    st.subheader("券商分點")
    trade_date_resolution = resolve_after_hours_trade_date()
    trade_date_key = trade_date_resolution["effective_date_text"]

    branch_options = list(load_branch_dropdown_options())
    if not branch_options:
        st.warning("目前載不到可用的券商分點清單。")
        return

    with st.form("broker_branch_scan_form", clear_on_submit=False):
        previous_branch = st.session_state.get("broker_activity_branch_query", "")
        default_index = branch_options.index(previous_branch) if previous_branch in branch_options else 0
        branch_query = st.selectbox(
            "券商分點名稱",
            options=branch_options,
            index=default_index,
            key="broker_activity_branch_query",
        )
        scan_cols = st.columns(3)
        start_num = scan_cols[0].number_input("主檔起始代碼", value=1101, step=1, format="%04d", key="broker_activity_start_num")
        end_num = scan_cols[1].number_input("主檔結束代碼", value=9999, step=1, format="%04d", key="broker_activity_end_num")
        top_n_per_stock = scan_cols[2].number_input("每檔抓前幾名分點", value=15, step=1, min_value=5, max_value=15, key="broker_activity_top_n")
        request_delay_sec = st.number_input("每檔延遲（秒）", value=0.01, step=0.01, min_value=0.0, max_value=1.0, key="broker_activity_delay")
        eligible_count = len(get_securities_in_range(int(start_num), int(end_num)))
        st.caption(f"這次會逐檔掃描區間股票，目前約 {eligible_count:,} 檔。")
        submitted = st.form_submit_button("搜尋這個分點今天買賣超", use_container_width=True)

    query_signature = {
        "branch_query": str(branch_query or "").strip(),
        "start_num": int(start_num),
        "end_num": int(end_num),
        "top_n_per_stock": int(top_n_per_stock),
        "trade_date_key": trade_date_key,
    }

    if submitted:
        if int(start_num) > int(end_num):
            st.error("起始代碼不能大於結束代碼。")
        else:
            with st.spinner("正在逐檔掃描分點資料，這一段會花一些時間..."):
                snapshot = scan_branch_totals(
                    branch_query=str(branch_query).strip(),
                    start_num=int(start_num),
                    end_num=int(end_num),
                    top_n_per_stock=int(top_n_per_stock),
                    request_delay_sec=float(request_delay_sec),
                    trade_date_key=trade_date_key,
                )
                snapshot["query_signature"] = query_signature
            st.session_state["broker_activity_branch_snapshot"] = snapshot

    snapshot = st.session_state.get("broker_activity_branch_snapshot")
    if not snapshot:
        return

    if snapshot.get("query_signature") != query_signature:
        st.info("目前畫面上的條件和上次查詢結果不同，請再按一次搜尋。")
        return

    result_df = snapshot.get("result_df")
    if not isinstance(result_df, pd.DataFrame):
        result_df = pd.DataFrame()

    summary_cols = st.columns(5)
    summary_cols[0].metric("本次基準資料日", str(snapshot.get("trade_date") or trade_date_key))
    summary_cols[1].metric("掃描檔數", int(snapshot.get("scanned_count") or 0))
    summary_cols[2].metric("分點出現的股票數", int(snapshot.get("matched_stocks") or 0))
    summary_cols[3].metric("抓取失敗檔數", int(snapshot.get("failed_count") or 0))
    summary_cols[4].metric("官方已匯入報表數", int(get_official_broker_db_overview()["report_count"] or 0))

    failed_count = int(snapshot.get("failed_count") or 0)
    failure_examples = list(snapshot.get("failure_examples") or [])
    if failed_count > 0:
        st.caption(f"這次有 {failed_count} 檔在抓取分點時失敗。")
        if failure_examples:
            with st.expander("查看部分抓取失敗原因"):
                for message in failure_examples:
                    st.write(f"- {message}")

    _render_branch_result_tables(str(snapshot.get("branch_query") or branch_query), result_df)
