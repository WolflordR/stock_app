from __future__ import annotations

import streamlit as st


APP_QUERY_KEYS = {
    "selected_view",
    "stock_detail_input",
    "active_etf_code",
    "active_etf_date",
    "market_map_topic",
    "market_map_view",
    "market_map_group",
}


def _set_query_params(param_map):
    active_keys = set(param_map.keys())
    for key in list(APP_QUERY_KEYS):
        if key not in active_keys and key in st.query_params:
            del st.query_params[key]
    for key, value in param_map.items():
        if value is None or value == "":
            if key in st.query_params:
                del st.query_params[key]
        else:
            st.query_params[key] = str(value)


def navigate_to_view(view_name, *, session_updates=None, query_updates=None, rerun=True):
    st.session_state["selected_view"] = str(view_name)
    st.session_state["_nav_last_view"] = str(view_name)
    for key, value in (session_updates or {}).items():
        st.session_state[key] = value

    merged_query = {"selected_view": str(view_name)}
    for key, value in (query_updates or {}).items():
        if value is not None and value != "":
            merged_query[key] = value
    _set_query_params(merged_query)

    if rerun:
        st.rerun()


def sync_selected_view_query(view_name):
    normalized_view = str(view_name)
    st.session_state["_nav_last_view"] = normalized_view
    _set_query_params({"selected_view": normalized_view})


def navigate_to_stock_detail(stock_code):
    normalized_code = str(stock_code or "").strip()
    navigate_to_view(
        "個股詳頁",
        session_updates={"stock_detail_input": normalized_code},
        query_updates={"stock_detail_input": normalized_code},
    )


def navigate_to_active_etf(etf_code=None, snapshot_date=None):
    normalized_code = str(etf_code or "").strip().upper()
    session_updates = {"active_etf_view_mode": "detail" if normalized_code else "list"}
    query_updates = {}
    if normalized_code:
        session_updates["active_etf_selected_code"] = normalized_code
        query_updates["active_etf_code"] = normalized_code
    if snapshot_date:
        snapshot_text = str(snapshot_date).strip()
        session_updates[f"active_etf_selected_snapshot_{normalized_code}"] = snapshot_text
        query_updates["active_etf_date"] = snapshot_text
    navigate_to_view("主動ETF", session_updates=session_updates, query_updates=query_updates)


def navigate_to_market_map(*, topic_name=None, group_name=None, view_mode="grid"):
    session_updates = {"market_map_view_mode": str(view_mode)}
    query_updates = {
        "market_map_view": str(view_mode),
    }
    if group_name:
        session_updates["market_map_selected_group"] = str(group_name)
        query_updates["market_map_group"] = str(group_name)
    if topic_name:
        session_updates["market_map_selected_topic"] = str(topic_name)
        query_updates["market_map_topic"] = str(topic_name)
    navigate_to_view("產業地圖 Beta", session_updates=session_updates, query_updates=query_updates)
