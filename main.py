import streamlit as st

from app_pages import (
    render_active_etf_page,
    render_backtest_page,
    render_home_page,
    render_industry_rotation_page,
    render_market_map_page,
    render_news_page,
    render_research_page,
    render_stock_detail_page,
)
from internal_nav import sync_selected_view_query
from ui_dialogs import render_buy_strategy_dialog, render_sell_strategy_dialog
from ui_sidebar import render_sidebar
from ui_state import ensure_strategy_state, initialize_session_state, load_secret_env


st.set_option("client.showSidebarNavigation", False)
st.set_page_config(page_title="台股量化回測系統", layout="wide")
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.1rem;
        padding-bottom: 2rem;
    }
    .app-badge {
        font-size: 0.92rem;
        font-weight: 700;
        letter-spacing: 0.02em;
        color: #0f172a;
        margin-bottom: 0.15rem;
    }
    .app-subtitle {
        font-size: 0.8rem;
        color: #64748b;
        margin-bottom: 0.9rem;
    }
    div[data-testid="stSidebar"] {
        border-right: 1px solid rgba(100, 116, 139, 0.12);
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.markdown('<div class="app-badge">Trade Lab</div>', unsafe_allow_html=True)
st.markdown('<div class="app-subtitle">台股回測、選股與籌碼觀察工作台</div>', unsafe_allow_html=True)

load_secret_env("OPENAI_API_KEY")
load_secret_env("OPENAI_NEWS_MODEL")
initialize_session_state()
ensure_strategy_state()

query_params = st.query_params
query_selected_view = query_params.get("selected_view")
query_stock_detail_input = query_params.get("stock_detail_input")
if query_stock_detail_input:
    st.session_state["stock_detail_input"] = str(query_stock_detail_input)

view_options = ["首頁", "產業輪動", "產業地圖 Beta", "研究工作台", "主動ETF", "回測 / 選股", "個股詳頁", "新聞分析"]
session_selected_view = st.session_state.get("selected_view", "首頁")
if session_selected_view not in view_options:
    session_selected_view = "首頁"
resolved_view = str(query_selected_view) if query_selected_view in view_options else str(session_selected_view)
if resolved_view not in view_options:
    resolved_view = "首頁"
st.session_state["selected_view"] = resolved_view

selected_view = st.segmented_control(
    "功能欄",
    view_options,
    default=resolved_view,
    key="selected_view_control",
    label_visibility="collapsed",
    width="stretch",
)
st.markdown("")

if selected_view != st.session_state.get("selected_view"):
    st.session_state["selected_view"] = selected_view

if st.session_state.get("_nav_last_view") != st.session_state.get("selected_view"):
    sync_selected_view_query(st.session_state["selected_view"])

selected_view = st.session_state["selected_view"]

sidebar_state = render_sidebar(selected_view)

if st.session_state.get("show_buy_strategy_dialog"):
    render_buy_strategy_dialog()

if st.session_state.get("show_sell_strategy_dialog"):
    render_sell_strategy_dialog()

if selected_view == "首頁":
    render_home_page(sidebar_state)
elif selected_view == "產業輪動":
    render_industry_rotation_page(sidebar_state)
elif selected_view == "產業地圖 Beta":
    render_market_map_page(sidebar_state)
elif selected_view == "研究工作台":
    render_research_page(sidebar_state)
elif selected_view == "主動ETF":
    render_active_etf_page(sidebar_state)
elif selected_view == "回測 / 選股":
    render_backtest_page(sidebar_state)
elif selected_view == "個股詳頁":
    render_stock_detail_page(sidebar_state)
elif selected_view == "新聞分析":
    render_news_page(sidebar_state)
