from __future__ import annotations

import streamlit as st

from internal_nav import navigate_to_market_map
from market_map_db import ensure_market_map_db
from market_map_db import refresh_market_map_db
from market_map_queries import get_market_map_page_bundle

from .market_map_page_helpers import inject_market_map_css
from .market_map_page_helpers import render_group_sidebar
from .market_map_page_helpers import render_hero
from .market_map_page_helpers import render_kpi_strip
from .market_map_page_helpers import render_navbar
from .market_map_page_helpers import render_overview_cards
from .market_map_page_helpers import render_topic_cards_panel
from .market_map_page_helpers import render_topic_detail
from .market_map_page_helpers import render_topic_heatmap
from .market_map_page_helpers import render_topic_value_chain


def render_market_map_page(_state):
    query_params = st.query_params
    query_group = query_params.get("market_map_group")
    query_topic = query_params.get("market_map_topic")
    query_view = query_params.get("market_map_view")

    if query_group:
        st.session_state["market_map_selected_group"] = str(query_group)
    if query_topic:
        st.session_state["market_map_selected_topic"] = str(query_topic)
    if query_view in {"grid", "detail"}:
        st.session_state["market_map_view_mode"] = str(query_view)
    elif "market_map_view_mode" not in st.session_state:
        st.session_state["market_map_view_mode"] = "grid"

    inject_market_map_css()

    action_cols = st.columns([1, 1, 1, 3])
    refresh_clicked = action_cols[0].button("重建資料庫", use_container_width=True)
    force_page_refresh = action_cols[1].button("重抓頁面資料", use_container_width=True)
    show_all_groups = action_cols[2].toggle("顯示全市場熱區", value=True)

    status = refresh_market_map_db() if refresh_clicked else ensure_market_map_db()
    bundle = get_market_map_page_bundle(force_refresh=force_page_refresh)

    if bundle["topic_snapshot_df"].empty or bundle["group_summary_df"].empty:
        st.info("目前還沒有足夠的題材地圖行情資料。")
        return

    render_navbar(status, bundle)
    render_hero(status, bundle)
    render_kpi_strip(status, bundle)

    with st.container(border=True):
        st.markdown("<div class='market-map-section-title'>Global Topic Heat</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='market-map-section-note'>先把整個台股題材攤開。卡片現在只負責展示，進板塊 detail 走下面這排 app 內按鈕，不會再跳出新分頁。</div>",
            unsafe_allow_html=True,
        )
        if show_all_groups:
            top_topic_df = bundle["topic_snapshot_df"].head(15).copy()
            render_overview_cards(top_topic_df, max_items=15)
            quick_topics = top_topic_df["topic_name"].tolist()
            if quick_topics:
                st.markdown("<div class='market-map-section-note'>快速進入板塊頁</div>", unsafe_allow_html=True)
                for start_index in range(0, len(quick_topics), 3):
                    cols = st.columns(3)
                    for col, topic_name in zip(cols, quick_topics[start_index:start_index + 3]):
                        with col:
                            if st.button(
                                f"查看 {topic_name}",
                                key=f"market_map_global_open_detail_{topic_name}",
                                use_container_width=True,
                            ):
                                match_df = bundle["topic_snapshot_df"][bundle["topic_snapshot_df"]["topic_name"] == topic_name]
                                topic_group = (
                                    str(match_df.iloc[0].get("group_name"))
                                    if not match_df.empty
                                    else st.session_state.get("market_map_selected_group", "")
                                )
                                navigate_to_market_map(topic_name=topic_name, group_name=topic_group, view_mode="detail")
        else:
            st.caption("已隱藏全市場熱區。")

    left_col, center_col, right_col = st.columns([0.95, 1.45, 1.2])
    with left_col:
        selected_group = render_group_sidebar(bundle["group_summary_df"])

    group_topic_df = bundle["topic_snapshot_df"][bundle["topic_snapshot_df"]["group_name"] == selected_group].copy()
    current_topic_options = group_topic_df["topic_name"].tolist()
    previous_topic = st.session_state.get("market_map_selected_topic")
    if previous_topic not in current_topic_options and current_topic_options:
        st.session_state["market_map_selected_topic"] = current_topic_options[0]
        st.session_state["market_map_view_mode"] = "grid"

    selected_topic = st.session_state.get("market_map_selected_topic")
    view_mode = st.session_state.get("market_map_view_mode", "grid")

    with center_col:
        if view_mode == "detail" and selected_topic:
            back_clicked = st.button("回到題材總覽", key="market_map_back_to_grid", use_container_width=False)
            if back_clicked:
                navigate_to_market_map(group_name=selected_group, view_mode="grid")
        else:
            selected_topic = render_topic_cards_panel(
                group_topic_df,
                st.session_state.get("market_map_selected_topic"),
                group_name=selected_group,
            )
            if selected_topic:
                enter_cols = st.columns([1.2, 1.8])
                if enter_cols[0].button("打開聚焦題材熱力圖", key="market_map_enter_selected_topic", use_container_width=True):
                    navigate_to_market_map(topic_name=selected_topic, group_name=selected_group, view_mode="detail")

    topic_row = None
    if selected_topic and not group_topic_df.empty:
        topic_match_df = group_topic_df[group_topic_df["topic_name"] == selected_topic]
        if not topic_match_df.empty:
            topic_row = topic_match_df.iloc[0].to_dict()

    topic_members_df = bundle["component_snapshot_df"]
    if selected_topic:
        topic_members_df = topic_members_df[topic_members_df["topic_name"] == selected_topic].copy()
    topic_heatmap_df = None
    if selected_topic and not topic_members_df.empty:
        topic_heatmap_df = topic_members_df.copy()
        topic_heatmap_df["name"] = topic_heatmap_df.get("name", topic_heatmap_df.get("name_zh"))
        topic_heatmap_df["week_change_pct"] = None
        topic_heatmap_df["month_change_pct"] = None

    topic_event_summary = None
    topic_event_items_df = bundle.get("topic_event_item_df")
    topic_event_summary_df = bundle.get("topic_event_summary_df")
    if selected_topic and topic_event_summary_df is not None and not topic_event_summary_df.empty:
        match_df = topic_event_summary_df[topic_event_summary_df["topic_name"] == selected_topic]
        if not match_df.empty:
            topic_event_summary = match_df.iloc[0].to_dict()
    if selected_topic and topic_event_items_df is not None and not topic_event_items_df.empty:
        topic_event_items_df = topic_event_items_df[topic_event_items_df["topic_name"] == selected_topic].copy()

    with center_col:
        if selected_topic and st.session_state.get("market_map_view_mode", "grid") == "detail":
            render_topic_heatmap(topic_row, topic_heatmap_df)
            render_topic_value_chain(topic_row, bundle["topic_snapshot_df"])

    with right_col:
        render_topic_detail(topic_row, topic_members_df, topic_event_summary, topic_event_items_df)
