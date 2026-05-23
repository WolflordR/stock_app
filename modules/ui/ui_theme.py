import streamlit as st


BACKGROUND_OPTIONS = ("黑色背景", "白色背景")
DEFAULT_BACKGROUND = "黑色背景"


def ensure_background_theme_state():
    if st.session_state.get("app_background_theme") not in BACKGROUND_OPTIONS:
        st.session_state["app_background_theme"] = DEFAULT_BACKGROUND


def render_background_theme_control():
    ensure_background_theme_state()
    st.selectbox(
        "背景",
        BACKGROUND_OPTIONS,
        index=BACKGROUND_OPTIONS.index(st.session_state["app_background_theme"]),
        key="app_background_theme",
        help="只切換主站背景與基礎容器色，預設維持黑色背景。",
    )


def inject_app_background_css():
    ensure_background_theme_state()
    light_mode = st.session_state.get("app_background_theme") == "白色背景"
    if light_mode:
        body_background = """
            radial-gradient(circle at 12% 0%, rgba(96, 165, 250, 0.16), transparent 24%),
            radial-gradient(circle at 92% 4%, rgba(20, 184, 166, 0.12), transparent 22%),
            linear-gradient(180deg, #ffffff 0%, #f8fafc 48%, #eef2f7 100%)
        """
        sidebar_background = "rgba(255, 255, 255, 0.92)"
        text_color = "#0f172a"
        muted_color = "#64748b"
        panel_background = "rgba(255, 255, 255, 0.78)"
        border_color = "rgba(15, 23, 42, 0.12)"
        input_background = "rgba(255, 255, 255, 0.92)"
        input_text_color = "#0f172a"
        control_background = "#ffffff"
        control_hover_background = "#f1f5f9"
        selected_background = "rgba(255, 75, 75, 0.10)"
        selected_text = "#dc2626"
    else:
        body_background = """
            radial-gradient(circle at 14% 0%, rgba(124, 58, 237, 0.18), transparent 24%),
            radial-gradient(circle at 88% 6%, rgba(6, 182, 212, 0.14), transparent 20%),
            linear-gradient(180deg, #030712 0%, #020617 52%, #000000 100%)
        """
        sidebar_background = "rgba(2, 6, 23, 0.94)"
        text_color = "#f8fafc"
        muted_color = "#94a3b8"
        panel_background = "rgba(15, 23, 42, 0.72)"
        border_color = "rgba(148, 163, 184, 0.18)"
        input_background = "rgba(15, 23, 42, 0.82)"
        input_text_color = "#f8fafc"
        control_background = "rgba(15, 23, 42, 0.88)"
        control_hover_background = "rgba(30, 41, 59, 0.92)"
        selected_background = "rgba(255, 75, 75, 0.10)"
        selected_text = "#ff4b4b"

    st.markdown(
        f"""
        <style>
        :root {{
            --trade-app-text: {text_color};
            --trade-app-muted: {muted_color};
            --trade-app-panel: {panel_background};
            --trade-app-border: {border_color};
        }}
        .stApp {{
            background: {body_background} !important;
            color: {text_color} !important;
        }}
        .block-container {{
            padding-top: 1.1rem;
            padding-bottom: 2rem;
        }}
        .app-badge {{
            font-size: 0.92rem;
            font-weight: 700;
            letter-spacing: 0.02em;
            color: {text_color} !important;
            margin-bottom: 0.15rem;
        }}
        .app-subtitle {{
            font-size: 0.8rem;
            color: {muted_color} !important;
            margin-bottom: 0.9rem;
        }}
        [data-testid="stSidebar"] {{
            background: {sidebar_background} !important;
            border-right: 1px solid {border_color} !important;
        }}
        [data-testid="stSidebarContent"],
        [data-testid="stSidebarUserContent"],
        [data-testid="stSidebarHeader"] {{
            background: transparent !important;
        }}
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3,
        [data-testid="stSidebar"] strong,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
            color: {text_color} !important;
        }}
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] small {{
            color: {muted_color} !important;
        }}
        [data-testid="stSidebar"] details {{
            background: {panel_background} !important;
            border-color: {border_color} !important;
        }}
        [data-testid="stSidebar"] summary {{
            background: {control_background} !important;
            color: {text_color} !important;
            border-color: {border_color} !important;
        }}
        [data-testid="stSidebar"] summary *,
        [data-testid="stSidebar"] button *,
        [data-testid="stSidebar"] button p,
        [data-testid="stSidebar"] button [data-testid="stMarkdownContainer"] {{
            color: {text_color} !important;
        }}
        [data-testid="stSidebar"] button {{
            background: {control_background} !important;
            color: {text_color} !important;
            border-color: {border_color} !important;
        }}
        [data-testid="stSidebar"] button:hover {{
            background: {control_hover_background} !important;
            color: {text_color} !important;
            border-color: rgba(96, 165, 250, 0.42) !important;
        }}
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        textarea,
        input {{
            background-color: {input_background} !important;
            color: {input_text_color} !important;
            border-color: {border_color} !important;
        }}
        div[data-baseweb="select"] *,
        div[data-baseweb="input"] *,
        textarea::placeholder,
        input::placeholder {{
            color: {input_text_color} !important;
        }}
        div[data-baseweb="popover"] *,
        ul[role="listbox"] *,
        li[role="option"] * {{
            color: {input_text_color} !important;
        }}
        div[data-baseweb="popover"],
        ul[role="listbox"],
        li[role="option"] {{
            background: {control_background} !important;
            color: {input_text_color} !important;
        }}
        [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_control"] {{
            background: {control_background} !important;
            color: {text_color} !important;
            border-color: {border_color} !important;
            box-shadow: none !important;
        }}
        [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_control"]:hover {{
            background: {control_hover_background} !important;
            color: {text_color} !important;
            border-color: rgba(96, 165, 250, 0.42) !important;
        }}
        [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_control"][aria-checked="true"],
        [data-testid="stButtonGroup"] button[data-testid="stBaseButton-segmented_control"][aria-pressed="true"] {{
            background: {selected_background} !important;
            color: {selected_text} !important;
            border-color: {selected_text} !important;
        }}
        div[data-testid="stExpander"],
        div[data-testid="stMetric"],
        div[data-testid="stDataFrame"] {{
            border-color: {border_color} !important;
        }}
        .industry-summary-card {{
            background: {panel_background} !important;
            border-color: {border_color} !important;
        }}
        .industry-summary-label,
        .market-map-section-note,
        .active-etf-subtitle,
        .active-etf-list-header {{
            color: {muted_color} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
