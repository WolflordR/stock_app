import streamlit as st

from app_pages import (
    render_active_etf_page,
    render_backtest_page,
    render_broker_activity_page,
    render_home_page,
    render_industry_rotation_page,
    render_market_map_page,
    render_news_page,
    render_research_page,
    render_stock_detail_page,
)
from modules.core.internal_nav import sync_selected_view_query
from modules.ui.ui_dialogs import render_buy_strategy_dialog, render_sell_strategy_dialog
from modules.ui.ui_sidebar import render_sidebar
from modules.ui.ui_state import ensure_strategy_state, initialize_session_state, load_secret_env


st.set_option("client.showSidebarNavigation", False)
st.set_page_config(page_title="台股量化回測系統", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --fin-bg: #0b1118;
        --fin-bg-soft: #0e1621;
        --fin-surface: #111b27;
        --fin-surface-elevated: #172333;
        --fin-surface-hover: #1d2b3d;
        --fin-border: rgba(137, 157, 179, 0.18);
        --fin-border-strong: rgba(137, 157, 179, 0.28);
        --fin-text: #dbe7f3;
        --fin-text-strong: #eef5fb;
        --fin-text-muted: #8fa3b8;
        --fin-text-faint: #64788d;
        --fin-accent: #4fb7d8;
        --fin-accent-soft: rgba(79, 183, 216, 0.14);
        --fin-success: #63c796;
        --fin-danger: #df6f7b;
        --fin-warning: #d3a64f;
        --fin-shadow: 0 18px 45px rgba(0, 0, 0, 0.30);
        --fin-shadow-soft: 0 8px 24px rgba(0, 0, 0, 0.20);
    }

    html,
    body,
    [data-testid="stAppViewContainer"] {
        background:
            linear-gradient(180deg, rgba(17, 27, 39, 0.96) 0%, rgba(11, 17, 24, 1) 42%, rgba(8, 13, 20, 1) 100%) !important;
        color: var(--fin-text) !important;
    }

    [data-testid="stAppViewContainer"]::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background:
            linear-gradient(rgba(143, 163, 184, 0.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(143, 163, 184, 0.025) 1px, transparent 1px);
        background-size: 36px 36px;
        mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.48), transparent 72%);
    }

    * {
        letter-spacing: 0 !important;
    }

    .block-container {
        padding-top: 1.1rem;
        padding-bottom: 2rem;
        max-width: min(1500px, calc(100vw - 2rem));
    }

    h1,
    h2,
    h3,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 {
        color: var(--fin-text-strong) !important;
        font-weight: 750 !important;
    }

    p,
    label,
    span,
    [data-testid="stMarkdownContainer"] {
        color: inherit;
    }

    .app-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        font-size: 0.92rem;
        font-weight: 760;
        color: var(--fin-text-strong);
        margin-bottom: 0.15rem;
    }

    .app-badge::before {
        content: "";
        width: 0.55rem;
        height: 0.55rem;
        border-radius: 999px;
        background: var(--fin-accent);
        box-shadow: 0 0 18px rgba(79, 183, 216, 0.34);
    }

    .app-subtitle {
        font-size: 0.8rem;
        color: var(--fin-text-muted);
        margin-bottom: 0.9rem;
    }

    div[data-testid="stSidebar"] {
        background:
            linear-gradient(180deg, rgba(15, 23, 34, 0.98), rgba(11, 17, 24, 0.98)) !important;
        border-right: 1px solid var(--fin-border);
        box-shadow: 12px 0 38px rgba(0, 0, 0, 0.18);
    }

    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        color: var(--fin-text-muted) !important;
    }

    .stButton > button,
    .stDownloadButton > button,
    [data-testid="stFormSubmitButton"] button {
        border: 1px solid var(--fin-border-strong) !important;
        border-radius: 8px !important;
        background: linear-gradient(180deg, rgba(29, 43, 61, 0.92), rgba(19, 30, 44, 0.96)) !important;
        color: var(--fin-text) !important;
        box-shadow: var(--fin-shadow-soft);
        font-weight: 650 !important;
    }

    .stButton > button:hover,
    .stDownloadButton > button:hover,
    [data-testid="stFormSubmitButton"] button:hover {
        border-color: rgba(79, 183, 216, 0.45) !important;
        background: linear-gradient(180deg, rgba(34, 53, 73, 0.98), rgba(22, 36, 52, 0.98)) !important;
        color: var(--fin-text-strong) !important;
    }

    .stButton > button:focus,
    .stDownloadButton > button:focus,
    [data-testid="stFormSubmitButton"] button:focus {
        box-shadow: 0 0 0 1px rgba(79, 183, 216, 0.46), 0 0 0 4px rgba(79, 183, 216, 0.12) !important;
    }

    input,
    textarea,
    [data-baseweb="select"] > div,
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div {
        border-color: var(--fin-border) !important;
        background-color: rgba(17, 27, 39, 0.96) !important;
        color: var(--fin-text) !important;
        border-radius: 8px !important;
    }

    input:focus,
    textarea:focus,
    [data-baseweb="select"] > div:focus-within,
    [data-baseweb="input"] > div:focus-within,
    [data-baseweb="textarea"] > div:focus-within {
        border-color: rgba(79, 183, 216, 0.50) !important;
        box-shadow: 0 0 0 3px rgba(79, 183, 216, 0.12) !important;
    }

    [data-baseweb="popover"],
    [data-baseweb="menu"] {
        background: var(--fin-surface-elevated) !important;
        border: 1px solid var(--fin-border) !important;
        box-shadow: var(--fin-shadow) !important;
    }

    [data-baseweb="tab-list"],
    [data-testid="stSegmentedControl"] {
        border-color: var(--fin-border) !important;
    }

    button[data-baseweb="tab"],
    [data-testid="stSegmentedControl"] button {
        color: var(--fin-text-muted) !important;
        border-radius: 8px !important;
    }

    button[data-baseweb="tab"][aria-selected="true"],
    [data-testid="stSegmentedControl"] button[aria-pressed="true"] {
        color: var(--fin-text-strong) !important;
        background: rgba(79, 183, 216, 0.14) !important;
        border-color: rgba(79, 183, 216, 0.32) !important;
    }

    [data-testid="stMetric"],
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: linear-gradient(180deg, rgba(17, 27, 39, 0.92), rgba(13, 21, 31, 0.96)) !important;
        border: 1px solid var(--fin-border) !important;
        border-radius: 8px !important;
        box-shadow: var(--fin-shadow-soft);
    }

    [data-testid="stMetricLabel"] p,
    [data-testid="stMetricDelta"] p,
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {
        color: var(--fin-text-muted) !important;
    }

    [data-testid="stMetricValue"] {
        color: var(--fin-text-strong) !important;
        font-variant-numeric: tabular-nums;
    }

    div[data-testid="stDataFrame"],
    div[data-testid="stTable"] {
        border: 1px solid var(--fin-border);
        border-radius: 8px;
        overflow: hidden;
        background: rgba(15, 24, 35, 0.86);
        box-shadow: var(--fin-shadow-soft);
    }

    div[data-testid="stExpander"] details {
        border: 1px solid var(--fin-border) !important;
        border-radius: 8px !important;
        background: linear-gradient(180deg, rgba(17, 27, 39, 0.88), rgba(13, 21, 31, 0.94)) !important;
    }

    div[data-testid="stAlert"] {
        border-radius: 8px !important;
        border: 1px solid var(--fin-border) !important;
        background: rgba(17, 27, 39, 0.90) !important;
    }

    [data-testid="stPlotlyChart"],
    [data-testid="stVegaLiteChart"] {
        border-radius: 8px;
        background: rgba(15, 24, 35, 0.68);
    }

    hr {
        border-color: var(--fin-border) !important;
    }

    ::selection {
        background: rgba(79, 183, 216, 0.28);
        color: var(--fin-text-strong);
    }

    ::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }

    ::-webkit-scrollbar-track {
        background: rgba(11, 17, 24, 0.72);
    }

    ::-webkit-scrollbar-thumb {
        background: rgba(100, 120, 141, 0.46);
        border: 2px solid rgba(11, 17, 24, 0.72);
        border-radius: 999px;
    }

    ::-webkit-scrollbar-thumb:hover {
        background: rgba(143, 163, 184, 0.58);
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

view_options = ["首頁", "產業輪動", "產業地圖 Beta", "研究工作台", "主動ETF", "回測 / 選股", "券商分點", "個股詳頁", "新聞分析"]
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
elif selected_view == "券商分點":
    render_broker_activity_page(sidebar_state)
elif selected_view == "個股詳頁":
    render_stock_detail_page(sidebar_state)
elif selected_view == "新聞分析":
    render_news_page(sidebar_state)
