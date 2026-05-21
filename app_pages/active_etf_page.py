from __future__ import annotations

from datetime import datetime
from textwrap import dedent
import pandas as pd
import streamlit as st

from active_etf_history_store import load_etf_change_snapshot_items
from active_etf_watch import refresh_all_active_etf_history_snapshots
from internal_nav import navigate_to_active_etf
from ui_data import load_active_etf_detail_data
from ui_data import load_active_etf_overview_data
from ui_jobs import ensure_background_data_job, get_background_data_job_manager
from ui_status import render_background_data_job_status


def _format_pct(value, digits=2):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.{digits}f}%"


def _format_100m(value, digits=1):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.{digits}f} 億"


def _format_10k(value, digits=2):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.{digits}f} 萬"


def _format_ratio(value, digits=2):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.{digits}%}"


def _html_fragment(markup):
    return dedent(markup).strip()


def _inject_active_etf_css():
    st.markdown(
        """
        <style>
        .active-etf-shell {
            border-radius: 1.5rem;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.96), rgba(2, 6, 23, 0.96));
            box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
            overflow: hidden;
            margin-bottom: 1rem;
        }
        .active-etf-hero {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 1.2rem 1.35rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.18);
        }
        .active-etf-title-wrap {
            display: flex;
            align-items: center;
            gap: 0.9rem;
        }
        .active-etf-icon {
            width: 3rem;
            height: 3rem;
            border-radius: 1rem;
            display: flex;
            align-items: center;
            justify-content: center;
            background: radial-gradient(circle at 30% 30%, rgba(124,58,237,0.38), rgba(76,29,149,0.72));
            color: #c4b5fd;
            font-size: 1.3rem;
            font-weight: 800;
        }
        .active-etf-title {
            font-size: 1.95rem;
            font-weight: 800;
            color: #f8fafc;
            letter-spacing: -0.03em;
        }
        .active-etf-subtitle {
            font-size: 0.9rem;
            color: #94a3b8;
            margin-top: 0.2rem;
        }
        .active-etf-pill {
            border-radius: 999px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: rgba(30, 41, 59, 0.92);
            color: #cbd5e1;
            padding: 0.5rem 0.9rem;
            font-size: 0.98rem;
            font-weight: 700;
        }
        .active-etf-list-header, .active-etf-list-row {
            display: grid;
            grid-template-columns: minmax(260px, 2.2fr) repeat(4, minmax(80px, 0.65fr)) 64px;
            gap: 1rem;
            align-items: center;
        }
        .active-etf-list-header {
            padding: 1rem 1.35rem 0.8rem 1.35rem;
            color: #94a3b8;
            font-weight: 700;
            font-size: 0.95rem;
        }
        .active-etf-list-row {
            padding: 1.25rem 1.35rem;
            border-top: 1px solid rgba(148, 163, 184, 0.18);
        }
        .active-etf-list-name {
            color: #f8fafc;
            font-size: 1.35rem;
            font-weight: 800;
            line-height: 1.2;
        }
        .active-etf-list-code {
            color: #e2e8f0;
            font-size: 1rem;
            font-weight: 500;
            margin-left: 0.35rem;
        }
        .active-etf-list-date {
            margin-top: 0.55rem;
            color: #94a3b8;
            font-size: 0.9rem;
        }
        .active-etf-list-value {
            font-size: 1.2rem;
            font-weight: 800;
            color: #f8fafc;
            text-align: center;
        }
        div[data-testid="stButton"] button[kind="tertiary"] {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            padding: 0 !important;
            min-height: auto !important;
            color: #f8fafc !important;
            justify-content: flex-start !important;
            font-size: 1.35rem !important;
            font-weight: 800 !important;
            line-height: 1.2 !important;
        }
        div[data-testid="stButton"] button[kind="tertiary"]:hover {
            background: transparent !important;
            color: #ffffff !important;
            text-decoration: underline;
            text-decoration-color: rgba(255,255,255,0.38);
            text-underline-offset: 0.18rem;
        }
        div[data-testid="stButton"] button[kind="tertiary"]:focus,
        div[data-testid="stButton"] button[kind="tertiary"]:focus-visible,
        div[data-testid="stButton"] button[kind="tertiary"]:active {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            color: #ffffff !important;
        }
        .active-etf-list-value.positive { color: #f43f5e; }
        .active-etf-list-value.negative { color: #22c55e; }
        .active-etf-list-value.muted { color: #94a3b8; }
        .active-etf-detail-card {
            border-radius: 1.5rem;
            border: 1px solid rgba(148, 163, 184, 0.18);
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(2, 6, 23, 0.98));
            box-shadow: 0 24px 60px rgba(0, 0, 0, 0.28);
            overflow: hidden;
            margin-top: 1rem;
        }
        .active-etf-detail-header {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: center;
            padding: 1.1rem 1.3rem;
            border-bottom: 1px solid rgba(148, 163, 184, 0.18);
        }
        .active-etf-detail-name {
            color: #f8fafc;
            font-size: 1.7rem;
            font-weight: 800;
            letter-spacing: -0.02em;
        }
        .active-etf-detail-code {
            color: #94a3b8;
            font-size: 1.05rem;
            margin-right: 0.45rem;
        }
        .active-etf-detail-meta {
            color: #94a3b8;
            font-size: 0.92rem;
            margin-top: 0.3rem;
        }
        .active-etf-stat-card {
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 1rem;
            padding: 0.95rem 1rem;
            background: rgba(30, 41, 59, 0.58);
            min-height: 7.8rem;
        }
        .active-etf-stat-label {
            color: #94a3b8;
            font-size: 0.9rem;
            margin-bottom: 0.65rem;
        }
        .active-etf-stat-value {
            color: #f8fafc;
            font-size: 1.65rem;
            font-weight: 800;
            line-height: 1.1;
            letter-spacing: -0.03em;
        }
        .active-etf-section-title {
            color: #f8fafc;
            font-size: 1.15rem;
            font-weight: 800;
            margin-bottom: 0.25rem;
        }
        .active-etf-section-note {
            color: #94a3b8;
            font-size: 0.88rem;
            line-height: 1.6;
            margin-bottom: 0.8rem;
        }
        .active-etf-industry-box {
            border-radius: 1rem;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background: rgba(30, 41, 59, 0.52);
            margin-bottom: 0.85rem;
            overflow: hidden;
        }
        .active-etf-industry-head {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.95rem 1rem;
            background: rgba(59, 130, 246, 0.14);
            color: #60a5fa;
            font-weight: 800;
        }
        .active-etf-holding-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.7rem;
            padding: 0.9rem 1rem 1rem 1rem;
        }
        .active-etf-holding-chip {
            border-left: 1px solid rgba(148, 163, 184, 0.18);
            padding-left: 0.8rem;
        }
        .active-etf-holding-code {
            color: #94a3b8;
            font-size: 0.9rem;
        }
        .active-etf-holding-name {
            color: #f8fafc;
            font-size: 1rem;
            font-weight: 700;
            margin-top: 0.05rem;
        }
        .active-etf-holding-weight {
            color: #e2e8f0;
            font-size: 0.95rem;
            font-weight: 700;
            margin-top: 0.15rem;
        }
        .active-etf-change-count-card {
            border-radius: 1rem;
            padding: 1rem 1.1rem;
            border: 1px solid rgba(148, 163, 184, 0.16);
            min-height: 7rem;
        }
        .active-etf-change-count-label {
            font-size: 0.95rem;
            font-weight: 700;
            margin-top: 0.35rem;
        }
        .active-etf-change-count-value {
            font-size: 2rem;
            font-weight: 900;
            line-height: 1;
        }
        .active-etf-action-add {
            background: rgba(245, 158, 11, 0.13);
            color: #f59e0b;
        }
        .active-etf-action-inc {
            background: rgba(244, 63, 94, 0.13);
            color: #f43f5e;
        }
        .active-etf-action-dec {
            background: rgba(34, 197, 94, 0.13);
            color: #22c55e;
        }
        .active-etf-action-rem {
            background: rgba(148, 163, 184, 0.13);
            color: #94a3b8;
        }
        .active-etf-timeline-wrap {
            border: 1px solid rgba(148, 163, 184, 0.16);
            border-radius: 1.2rem;
            background: rgba(20, 28, 46, 0.72);
            padding: 1rem 1rem 0.9rem 1rem;
            overflow: hidden;
            margin-bottom: 1rem;
        }
        .active-etf-timeline-head {
            display: flex;
            align-items: center;
            gap: 1rem;
            margin-bottom: 0.85rem;
            color: #f8fafc;
            font-weight: 800;
        }
        .active-etf-timeline-legend {
            display: flex;
            align-items: center;
            gap: 0.9rem;
            flex-wrap: wrap;
            color: #94a3b8;
            font-size: 0.88rem;
            font-weight: 700;
        }
        .active-etf-dot {
            display: inline-block;
            width: 0.75rem;
            height: 0.75rem;
            border-radius: 999px;
            margin-right: 0.32rem;
            vertical-align: middle;
        }
        .active-etf-dot.add { background: #f59e0b; }
        .active-etf-dot.inc { background: #f43f5e; }
        .active-etf-dot.dec { background: #22c55e; }
        .active-etf-dot.rem { background: #94a3b8; }
        .active-etf-timeline-scroll {
            display: flex;
            gap: 0.7rem;
            overflow-x: auto;
            padding-bottom: 0.55rem;
            scrollbar-color: rgba(100, 116, 139, 0.7) transparent;
        }
        .active-etf-timeline-scroll::-webkit-scrollbar {
            height: 10px;
        }
        .active-etf-timeline-scroll::-webkit-scrollbar-thumb {
            background: rgba(100, 116, 139, 0.65);
            border-radius: 999px;
        }
        div[data-testid="stRadio"] [role="radiogroup"] {
            display: flex;
            flex-wrap: nowrap;
            overflow-x: auto;
            gap: 0.75rem;
            padding-bottom: 0.65rem;
            scrollbar-color: rgba(100, 116, 139, 0.7) transparent;
        }
        div[data-testid="stRadio"] [role="radiogroup"]::-webkit-scrollbar {
            height: 10px;
        }
        div[data-testid="stRadio"] [role="radiogroup"]::-webkit-scrollbar-thumb {
            background: rgba(100, 116, 139, 0.65);
            border-radius: 999px;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label {
            min-width: 6.3rem;
            max-width: 6.3rem;
            min-height: 10.2rem;
            border-radius: 1rem !important;
            border: 1px solid rgba(148, 163, 184, 0.18) !important;
            background: rgba(39, 51, 74, 0.78) !important;
            padding: 0.8rem 0.55rem 0.7rem 0.55rem !important;
            color: #cbd5e1 !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center;
            flex: 0 0 auto;
            position: relative;
            cursor: pointer !important;
            transition: background 180ms ease, border-color 180ms ease, transform 180ms ease, box-shadow 180ms ease, color 180ms ease !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label:hover {
            background: rgba(49, 64, 92, 0.92) !important;
            border-color: rgba(125, 211, 252, 0.42) !important;
            box-shadow: 0 10px 24px rgba(2, 6, 23, 0.24), 0 0 0 1px rgba(125, 211, 252, 0.08) inset !important;
            transform: translateY(-1px);
        }
        div[data-testid="stRadio"] [role="radiogroup"] label:active {
            transform: translateY(0);
            background: rgba(59, 130, 246, 0.22) !important;
            border-color: rgba(125, 211, 252, 0.56) !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label[data-checked="true"],
        div[data-testid="stRadio"] [role="radiogroup"] label[aria-checked="true"],
        div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {
            background: linear-gradient(180deg, rgba(59, 130, 246, 0.88), rgba(96, 165, 250, 0.94)) !important;
            border-color: rgba(255, 255, 255, 0.74) !important;
            box-shadow: 0 0 0 2px rgba(255,255,255,0.08) inset;
            color: #ffffff !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label[data-checked="true"]:hover,
        div[data-testid="stRadio"] [role="radiogroup"] label[aria-checked="true"]:hover,
        div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked):hover {
            background: linear-gradient(180deg, rgba(76, 145, 252, 0.92), rgba(125, 179, 255, 0.98)) !important;
            border-color: rgba(255, 255, 255, 0.84) !important;
            box-shadow: 0 14px 28px rgba(30, 64, 175, 0.28), 0 0 0 2px rgba(255,255,255,0.12) inset !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label [data-baseweb="radio"],
        div[data-testid="stRadio"] [role="radiogroup"] label input[type="radio"] {
            display: none !important;
            opacity: 0 !important;
            width: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            pointer-events: none !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label > div:first-child,
        div[data-testid="stRadio"] [role="radiogroup"] label svg {
            display: none !important;
            opacity: 0 !important;
            width: 0 !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            pointer-events: none !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label [data-testid="stMarkdownContainer"] {
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            width: 100% !important;
            height: 100% !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label > div {
            width: 100% !important;
        }
        div[data-testid="stRadio"] [role="radiogroup"] label p,
        div[data-testid="stRadio"] [role="radiogroup"] label span {
            white-space: pre-line !important;
            line-height: 1.25 !important;
            text-align: center !important;
            font-weight: 800 !important;
            margin: 0 !important;
            color: inherit !important;
        }
        .active-etf-period-strip {
            display: grid;
            grid-template-columns: minmax(0, 1fr) 48px minmax(0, 1fr);
            gap: 0.8rem;
            align-items: center;
            margin: 0.85rem 0 1rem 0;
        }
        .active-etf-period-box {
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 1rem;
            background: rgba(15, 23, 42, 0.86);
            padding: 0.95rem 1rem;
            min-height: 5rem;
        }
        .active-etf-period-label {
            color: #94a3b8;
            font-size: 0.84rem;
            font-weight: 700;
            margin-bottom: 0.45rem;
        }
        .active-etf-period-value {
            color: #f8fafc;
            font-size: 1.45rem;
            font-weight: 900;
            letter-spacing: -0.03em;
        }
        .active-etf-period-arrow {
            color: #94a3b8;
            font-size: 1.4rem;
            font-weight: 900;
            text-align: center;
        }
        .active-etf-change-panel {
            border-radius: 1rem;
            border: 1px solid rgba(148, 163, 184, 0.16);
            background: rgba(30, 41, 59, 0.52);
            overflow: hidden;
            margin-top: 1rem;
        }
        .active-etf-change-panel-note {
            color: #94a3b8;
            font-size: 0.84rem;
            margin-top: 0.35rem;
        }
        .active-etf-change-panel-head {
            padding: 0.95rem 1rem;
            font-size: 1rem;
            font-weight: 800;
        }
        .active-etf-change-panel-head.up {
            color: #f43f5e;
            background: rgba(127, 29, 29, 0.22);
        }
        .active-etf-change-panel-head.down {
            color: #22c55e;
            background: rgba(20, 83, 45, 0.22);
        }
        .active-etf-change-row {
            display: grid;
            grid-template-columns: 92px minmax(0, 1fr);
            gap: 1rem;
            align-items: start;
            padding: 1rem 1rem;
            border-top: 1px solid rgba(148, 163, 184, 0.16);
        }
        .active-etf-change-body {
            display: block;
            min-width: 0;
        }
        .active-etf-change-left {
            min-width: 0;
        }
        .active-etf-change-weight {
            color: #f8fafc;
            font-size: 0.98rem;
            font-weight: 800;
        }
        .active-etf-change-name {
            color: #f8fafc;
            font-size: 1rem;
            font-weight: 800;
        }
        .active-etf-change-code {
            color: #94a3b8;
            font-size: 0.92rem;
            margin-left: 0.3rem;
        }
        .active-etf-change-industry {
            color: #94a3b8;
            font-size: 0.84rem;
            margin-top: 0.18rem;
        }
        .active-etf-change-right {
            margin-top: 0.45rem;
            min-width: 0;
            text-align: left;
        }
        .active-etf-change-shares {
            font-size: 0.86rem;
            font-weight: 900;
            line-height: 1.25;
            overflow-wrap: anywhere;
        }
        .active-etf-change-meta {
            margin-top: 0.2rem;
            font-size: 0.78rem;
            font-weight: 700;
            line-height: 1.2;
            color: #94a3b8;
            overflow-wrap: anywhere;
        }
        .active-etf-timeline-empty {
            border: 1px dashed rgba(148, 163, 184, 0.26);
            border-radius: 1rem;
            padding: 0.95rem 1rem;
            margin-top: 0.9rem;
            color: #94a3b8;
            font-size: 0.88rem;
            background: rgba(15, 23, 42, 0.5);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _change_value_style(value):
    text = str(value).strip()
    if text.startswith("+"):
        return "color: #f43f5e; font-weight: 800;"
    if text.startswith("-"):
        return "color: #22c55e; font-weight: 800;"
    return "color: #cbd5e1;"


def _render_changes_dataframe(display_df):
    styled_df = display_df.style.map(_change_value_style, subset=["股數變化", "張數變化", "權重變化(%)"])
    styled_df = styled_df.map(
        lambda value: {
            "新增": "color: #f59e0b; font-weight: 800;",
            "加碼": "color: #f43f5e; font-weight: 800;",
            "減碼": "color: #22c55e; font-weight: 800;",
            "移出": "color: #94a3b8; font-weight: 800;",
        }.get(str(value), "color: #e2e8f0;"),
        subset=["動作"],
    )
    st.dataframe(styled_df, use_container_width=True, hide_index=True)


def _weekday_label(date_text):
    try:
        date_obj = datetime.strptime(str(date_text), "%Y-%m-%d")
    except ValueError:
        return ""
    labels = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    return labels[date_obj.weekday()]


def _short_date_label(date_text):
    try:
        date_obj = datetime.strptime(str(date_text), "%Y-%m-%d")
    except ValueError:
        return str(date_text)
    return f"{date_obj.month}/{date_obj.day}"


def _render_date_timeline(etf_code, history_summary_df, selected_snapshot_date, latest_snapshot_date):
    timeline_rows = history_summary_df.sort_values("snapshot_date").to_dict("records")
    option_map = {}
    for row in timeline_rows:
        snapshot_date = str(row.get("snapshot_date") or "")
        dots = []
        if int(row.get("add_count") or 0) > 0:
            dots.append("🟠")
        if int(row.get("increase_count") or 0) > 0:
            dots.append("🔴")
        if int(row.get("decrease_count") or 0) > 0:
            dots.append("🟢")
        if int(row.get("remove_count") or 0) > 0:
            dots.append("⚪")
        option_map[snapshot_date] = (
            f"{_short_date_label(snapshot_date)}\n"
            f"{_weekday_label(snapshot_date)}\n"
            f"{' '.join(dots) if dots else '·'}\n"
            f"{int(row.get('change_count') or 0)}"
        )

    st.markdown(
        _html_fragment(
            f"""
            <div class="active-etf-timeline-wrap">
                <div class="active-etf-timeline-head">
                    <span>每日變動時間軸</span>
                    <div class="active-etf-timeline-legend">
                        <span><span class="active-etf-dot add"></span>新增</span>
                        <span><span class="active-etf-dot inc"></span>加碼</span>
                        <span><span class="active-etf-dot dec"></span>減碼</span>
                        <span><span class="active-etf-dot rem"></span>移出</span>
                    </div>
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )
    date_options = list(option_map.keys())
    if not date_options:
        return str(selected_snapshot_date or latest_snapshot_date or "")

    radio_key = f"active_etf_timeline_radio_{etf_code}"
    normalized_selected = str(selected_snapshot_date) if selected_snapshot_date is not None else ""
    if normalized_selected not in date_options:
        normalized_selected = date_options[-1]
    if radio_key not in st.session_state or str(st.session_state.get(radio_key)) not in date_options:
        st.session_state[radio_key] = normalized_selected

    picked_date = st.radio(
        "每日變動時間軸卡片",
        options=date_options,
        index=date_options.index(normalized_selected),
        format_func=lambda value: option_map.get(value, str(value)),
        horizontal=True,
        key=radio_key,
        label_visibility="collapsed",
    )

    return str(picked_date)


def _render_selected_period_strip(selected_summary_row):
    st.markdown(
        _html_fragment(
            f"""
            <div class="active-etf-period-strip">
                <div class="active-etf-period-box">
                    <div class="active-etf-period-label">前次持股日</div>
                    <div class="active-etf-period-value">{selected_summary_row.get('from_date') or '-'}</div>
                </div>
                <div class="active-etf-period-arrow">→</div>
                <div class="active-etf-period-box">
                    <div class="active-etf-period-label">本次持股日</div>
                    <div class="active-etf-period-value">{selected_summary_row.get('to_date') or selected_summary_row.get('snapshot_date') or '-'}</div>
                </div>
            </div>
            """
        ),
        unsafe_allow_html=True,
    )


def _normalize_changes_df(raw_changes_df):
    if raw_changes_df is None or raw_changes_df.empty:
        return pd.DataFrame(
            columns=[
                "change_label", "code", "name", "industry", "shares_delta", "shares_delta_lots",
                "weight_delta", "old_weight", "new_weight", "holding_amount_100m", "new_shares", "new_lots",
            ]
        )

    working_df = raw_changes_df.copy()
    aliases = {
        "stock_code": "code",
        "stock_name": "name",
    }
    for src, dst in aliases.items():
        if dst not in working_df.columns and src in working_df.columns:
            working_df[dst] = working_df[src]

    if "shares_delta" not in working_df.columns and "sharesDelta" in working_df.columns:
        working_df["shares_delta"] = pd.to_numeric(working_df["sharesDelta"], errors="coerce")
    if "shares_delta_lots" not in working_df.columns and "shares_delta" in working_df.columns:
        working_df["shares_delta_lots"] = working_df["shares_delta"] / 1000
    if "old_weight" not in working_df.columns and "oldWeight" in working_df.columns:
        working_df["old_weight"] = pd.to_numeric(working_df["oldWeight"], errors="coerce")
    if "new_weight" not in working_df.columns and "newWeight" in working_df.columns:
        working_df["new_weight"] = pd.to_numeric(working_df["newWeight"], errors="coerce")
    if "weight_delta" not in working_df.columns and "weightDelta" in working_df.columns:
        working_df["weight_delta"] = pd.to_numeric(working_df["weightDelta"], errors="coerce")
    if "new_shares" not in working_df.columns and "newShares" in working_df.columns:
        working_df["new_shares"] = pd.to_numeric(working_df["newShares"], errors="coerce")
    if "new_lots" not in working_df.columns and "new_shares" in working_df.columns:
        working_df["new_lots"] = working_df["new_shares"] / 1000
    if "holding_amount_ntd" not in working_df.columns and "holding_amount_100m" in working_df.columns:
        working_df["holding_amount_ntd"] = pd.to_numeric(working_df["holding_amount_100m"], errors="coerce") * 100000000
    if "holding_amount_ntd" in working_df.columns:
        working_df["holding_amount_ntd"] = pd.to_numeric(working_df["holding_amount_ntd"], errors="coerce")
    if "close" in working_df.columns:
        working_df["close"] = pd.to_numeric(working_df["close"], errors="coerce")
    if "holding_amount_ntd" in working_df.columns and "close" in working_df.columns and "new_shares" in working_df.columns:
        close_based_mask = working_df["close"].notna() & working_df["new_shares"].notna()
        working_df.loc[close_based_mask, "holding_amount_ntd"] = working_df.loc[close_based_mask, "close"] * working_df.loc[close_based_mask, "new_shares"]
    if "holding_amount_100m" not in working_df.columns and "holding_amount_ntd" in working_df.columns:
        working_df["holding_amount_100m"] = pd.to_numeric(working_df["holding_amount_ntd"], errors="coerce") / 100000000

    return working_df


def _build_sorted_changes_table(raw_changes_df, sort_by):
    working_df = _normalize_changes_df(raw_changes_df)
    if working_df.empty:
        return pd.DataFrame(columns=["動作", "代碼", "名稱", "產業", "股數變化", "張數變化", "權重變化(%)", "前日權重(%)", "最新權重(%)", "持有金額(估,萬)", "最新股數", "最新張數"])

    if sort_by == "持有金額":
        working_df = working_df.sort_values(["holding_amount_100m", "shares_delta"], ascending=[False, False], na_position="last")
    else:
        working_df = working_df.assign(abs_shares_delta=working_df["shares_delta"].abs())
        working_df = working_df.sort_values(["abs_shares_delta", "holding_amount_100m"], ascending=[False, False], na_position="last")

    display_df = pd.DataFrame(
        {
            "動作": working_df["change_label"].replace({"刪除": "移出"}),
            "代碼": working_df["code"],
            "名稱": working_df["name"],
            "產業": working_df["industry"].fillna("-"),
            "股數變化": working_df["shares_delta"].map(lambda value: "-" if pd.isna(value) else f"{int(round(value)):+,}"),
            "張數變化": working_df["shares_delta_lots"].map(lambda value: "-" if pd.isna(value) else f"{value:+,.1f}"),
            "權重變化(%)": working_df["weight_delta"].map(lambda value: "-" if pd.isna(value) else f"{value:+.2f}"),
            "前日權重(%)": working_df["old_weight"].map(lambda value: "-" if pd.isna(value) else f"{value:.2f}"),
            "最新權重(%)": working_df["new_weight"].map(lambda value: "-" if pd.isna(value) else f"{value:.2f}"),
            "持有金額(估,萬)": working_df["holding_amount_ntd"].map(lambda value: "-" if pd.isna(value) else f"{value / 10000:,.1f}"),
            "最新股數": working_df["new_shares"].map(lambda value: "-" if pd.isna(value) else f"{int(round(value)):,}"),
            "最新張數": working_df["new_lots"].map(lambda value: "-" if pd.isna(value) else f"{value:,.1f}"),
        }
    )
    return display_df.reset_index(drop=True)


def _build_change_panel_rows(raw_changes_df, sort_by, actions):
    working_df = _normalize_changes_df(raw_changes_df)
    if working_df.empty:
        return working_df
    if actions:
        working_df = working_df[working_df["change_label"].replace({"刪除": "移出"}).isin(actions)].copy()
    if working_df.empty:
        return working_df
    if sort_by == "持有金額":
        return working_df.sort_values(["holding_amount_100m", "shares_delta"], ascending=[False, False], na_position="last")
    return working_df.assign(abs_shares_delta=working_df["shares_delta"].abs()).sort_values(
        ["abs_shares_delta", "holding_amount_100m"], ascending=[False, False], na_position="last"
    )


def _build_sorted_holdings_table(raw_holdings_df, sort_by):
    if raw_holdings_df is None or raw_holdings_df.empty:
        return pd.DataFrame(columns=["代碼", "名稱", "產業", "權重(%)", "持有金額(估,億)", "股數", "張數"])

    working_df = raw_holdings_df.copy()
    if sort_by == "張數":
        working_df = working_df.sort_values(["lots", "holding_amount_100m", "weight"], ascending=[False, False, False], na_position="last")
    else:
        working_df = working_df.sort_values(["weight", "holding_amount_100m", "lots"], ascending=[False, False, False], na_position="last")

    return pd.DataFrame(
        {
            "代碼": working_df["code"],
            "名稱": working_df["name"],
            "產業": working_df["industry"].fillna("-"),
            "權重(%)": working_df["weight"].map(lambda value: "-" if pd.isna(value) else f"{value:.2f}"),
            "持有金額(估,億)": working_df["holding_amount_100m"].map(lambda value: "-" if pd.isna(value) else f"{value:,.2f}"),
            "股數": working_df["shares"].map(lambda value: "-" if pd.isna(value) else f"{int(round(value)):,}"),
            "張數": working_df["lots"].map(lambda value: "-" if pd.isna(value) else f"{value:,.1f}"),
        }
    ).reset_index(drop=True)


def _render_stat_cards(cards):
    cols = st.columns(len(cards))
    for col, (label, value) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="active-etf-stat-card">
                    <div class="active-etf-stat-label">{label}</div>
                    <div class="active-etf-stat-value">{value}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_etf_overview_list(raw_df):
    st.markdown(
        """
        <div class="active-etf-shell">
            <div class="active-etf-hero">
                <div class="active-etf-title-wrap">
                    <div class="active-etf-icon">⚡</div>
                    <div>
                        <div class="active-etf-title">主動式 ETF 追蹤</div>
                        <div class="active-etf-subtitle">先看最近誰在換股，再點進單一 ETF 拆細節。</div>
                    </div>
                </div>
                <div class="active-etf-pill">每日持股變動</div>
            </div>
            <div class="active-etf-list-header">
                <div>ETF 名稱</div>
                <div style="text-align:center;">最新異動</div>
                <div style="text-align:center;">今日</div>
                <div style="text-align:center;">近一週</div>
                <div style="text-align:center;">近一月</div>
                <div></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for _, row in raw_df.iterrows():
        row_cols = st.columns([3.2, 0.9, 0.8, 0.8, 0.8, 0.5])
        with row_cols[0]:
            if st.button(f"{row['name']}  {row['code']}", key=f"open_active_etf_name_{row['code']}", type="tertiary"):
                navigate_to_active_etf(row["code"])
            st.markdown(f"<div class='active-etf-list-date'>{row.get('latest_snapshot_date') or '-'}</div>", unsafe_allow_html=True)
        with row_cols[1]:
            st.markdown(f"<div class='active-etf-list-value'>{int(row.get('change_count') or 0)}</div>", unsafe_allow_html=True)
        for col, value in zip(row_cols[2:5], [row.get("today_pct"), row.get("week_pct"), row.get("month_pct")]):
            tone = "positive" if value is not None and value >= 0 else "negative"
            with col:
                st.markdown(
                    f"<div class='active-etf-list-value {tone}'>{_format_pct(value)}</div>",
                    unsafe_allow_html=True,
                )
        with row_cols[5]:
            if st.button("查看", key=f"open_active_etf_{row['code']}", use_container_width=True):
                navigate_to_active_etf(row["code"])


def _sort_active_etf_overview(raw_df, sort_by, sort_order):
    if raw_df is None or raw_df.empty:
        return raw_df

    ascending = sort_order == "升冪"
    working_df = raw_df.copy()
    if sort_by == "ETF編號":
        return working_df.sort_values(["code", "aum_100m"], ascending=[ascending, False], na_position="last").reset_index(drop=True)
    return working_df.sort_values(["aum_100m", "code"], ascending=[ascending, True], na_position="last").reset_index(drop=True)


def _render_overview_tab(detail_bundle):
    overview = detail_bundle["overview"]
    st.markdown("<div class='active-etf-section-title'>概覽</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='active-etf-section-note'>先把這檔 ETF 的核心輪廓看完：發行資訊、費用、最新規模、報酬與前十大持股。</div>",
        unsafe_allow_html=True,
    )
    _render_stat_cards(
        [
            ("追蹤指數", overview.get("tracking_index") or "無（經理人主動管理）"),
            ("管理費用", "-" if overview.get("management_fee") is None else f"{overview['management_fee']:.2f}%"),
            ("發行公司", overview.get("issuer") or "-"),
            ("基金規模", _format_100m(overview.get("aum_100m"), digits=2)),
            ("成立日期", overview.get("launch_date") or "-"),
        ]
    )
    st.markdown("")
    _render_stat_cards(
        [
            ("最新市價", "-" if overview.get("price") is None else f"{overview['price']:.2f}"),
            ("折溢價", _format_pct(overview.get("premium"))),
        ]
    )
    st.markdown("")
    st.markdown("<div class='active-etf-section-title'>前十大成分股</div>", unsafe_allow_html=True)
    top10_df = _build_sorted_holdings_table(detail_bundle["raw_holdings_df"], "持有金額").head(10)
    st.dataframe(top10_df, use_container_width=True, hide_index=True)


def _render_holdings_tab(detail_bundle):
    st.markdown("<div class='active-etf-section-title'>成分股</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='active-etf-section-note'>先看產業分布，再往下拆每個產業裡的主要持股，最後再看完整成分股列表。</div>",
        unsafe_allow_html=True,
    )
    raw_holdings_df = detail_bundle["raw_holdings_df"]
    industry_breakdown_df = detail_bundle["industry_breakdown_df"]

    if not raw_holdings_df.empty and not industry_breakdown_df.empty:
        for _, industry_row in industry_breakdown_df.iterrows():
            industry_name = industry_row.get("industry") or "未分類"
            industry_df = raw_holdings_df[raw_holdings_df["industry"].fillna("未分類") == industry_name].copy()
            industry_df = industry_df.sort_values(["weight", "shares"], ascending=[False, False]).head(10)
            chips = []
            for _, holding_row in industry_df.iterrows():
                chips.append(
                    _html_fragment(
                        f"""
                    <div class="active-etf-holding-chip">
                        <div class="active-etf-holding-code">{holding_row['code']}</div>
                        <div class="active-etf-holding-name">{holding_row['name']}</div>
                        <div class="active-etf-holding-weight">{holding_row['weight']:.2f}%</div>
                    </div>
                        """
                    )
                )
            st.markdown(
                _html_fragment(
                    f"""
                <div class="active-etf-industry-box">
                    <div class="active-etf-industry-head">
                        <span>{industry_name}　{int(industry_row['company_count'])} 檔</span>
                        <span>{industry_row['industry_weight']:.1f}%</span>
                    </div>
                    <div class="active-etf-holding-grid">
                        {''.join(chips)}
                    </div>
                </div>
                    """
                ),
                unsafe_allow_html=True,
            )

    st.markdown("")
    sort_by = st.segmented_control(
        "成分股排序",
        ["持有金額", "張數"],
        default="持有金額",
        key=f"active_etf_holding_sort_{detail_bundle['code']}",
    )
    holdings_df = _build_sorted_holdings_table(raw_holdings_df, sort_by)
    show_mode = st.segmented_control(
        "顯示範圍",
        ["前十大", "全部"],
        default="前十大",
        key=f"active_etf_holding_show_mode_{detail_bundle['code']}",
    )
    if show_mode == "前十大":
        holdings_df = holdings_df.head(10)
    st.dataframe(holdings_df, use_container_width=True, hide_index=True)


def _render_change_count_cards(counts):
    cards = [
        ("新增入榜", int(counts.get("新增") or 0), "active-etf-action-add"),
        ("加碼持股", int(counts.get("加碼") or 0), "active-etf-action-inc"),
        ("減碼持股", int(counts.get("減碼") or 0), "active-etf-action-dec"),
        ("移出榜單", int(counts.get("刪除") or 0), "active-etf-action-rem"),
    ]
    cols = st.columns(4)
    for col, (label, value, css_class) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="active-etf-change-count-card {css_class}">
                    <div class="active-etf-change-count-value">{value}</div>
                    <div class="active-etf-change-count-label">{label}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_change_panel(title, tone, raw_changes_df, sort_by, actions):
    panel_df = _build_change_panel_rows(raw_changes_df, sort_by, actions)
    if panel_df.empty:
        st.caption(f"{title} 目前沒有資料。")
        return

    rows = []
    for _, row in panel_df.iterrows():
        latest_weight = "-" if pd.isna(row.get("new_weight")) else f"{row.get('new_weight'):.2f}%"
        shares_delta = row.get("shares_delta")
        shares_text = "-" if pd.isna(shares_delta) else f"{int(round(shares_delta)):+,} 股"
        lots_delta = row.get("shares_delta_lots")
        lots_text = "-" if pd.isna(lots_delta) else f"{lots_delta:+,.1f} 張"
        weight_delta = row.get("weight_delta")
        weight_text = "-" if pd.isna(weight_delta) else f"{weight_delta:+.2f}%"
        holding_amount_ntd = row.get("holding_amount_ntd")
        amount_text = "-" if pd.isna(holding_amount_ntd) else _format_10k(holding_amount_ntd / 10000, digits=1)
        shares_style = "color:#f43f5e;" if shares_text.startswith("+") else "color:#22c55e;" if shares_text.startswith("-") else "color:#cbd5e1;"
        weight_style = "color:#f43f5e;" if weight_text.startswith("+") else "color:#22c55e;" if weight_text.startswith("-") else "color:#cbd5e1;"
        rows.append(
            _html_fragment(
                f"""
                <div class="active-etf-change-row">
                    <div class="active-etf-change-weight">{latest_weight}</div>
                    <div class="active-etf-change-body">
                        <div class="active-etf-change-left">
                            <div class="active-etf-change-name">{row.get('name') or '-'}<span class="active-etf-change-code">{row.get('code') or '-'}</span></div>
                            <div class="active-etf-change-industry">{row.get('industry') or '-'}</div>
                        </div>
                        <div class="active-etf-change-right">
                            <div class="active-etf-change-shares" style="{shares_style}">{shares_text} ／ {lots_text}</div>
                            <div class="active-etf-change-meta"><span style="{weight_style}">{weight_text}</span> ｜ 持有金額 {amount_text}</div>
                        </div>
                    </div>
                </div>
                """
            )
        )

    st.markdown(
        _html_fragment(
            f"""
            <div class="active-etf-change-panel">
                <div class="active-etf-change-panel-head {tone}">{title}（{len(panel_df)}）</div>
                {''.join(rows)}
            </div>
            """
        ),
        unsafe_allow_html=True,
    )
    action_hint = "看今天新進榜與加碼最明顯的持股。" if tone == "up" else "看今天被調節或退出榜單的持股。"
    st.markdown(f"<div class='active-etf-change-panel-note'>{action_hint}</div>", unsafe_allow_html=True)


def _render_changes_tab(detail_bundle):
    st.markdown("<div class='active-etf-section-title'>持股變動</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='active-etf-section-note'>這裡會先回補近 30 個交易日的公開歷史，再接上你本地每天整理的快照，所以時間軸不需要等一個月才會長出來。</div>",
        unsafe_allow_html=True,
    )

    history_summary_df = detail_bundle.get("history_summary_df")
    latest_snapshot_date = detail_bundle["change_summary"].get("to_date") or detail_bundle["change_summary"].get("snapshot_date")
    if history_summary_df is None or history_summary_df.empty:
        history_summary_df = pd.DataFrame([{
            "snapshot_date": latest_snapshot_date,
            "from_date": detail_bundle["change_summary"].get("from_date"),
            "to_date": detail_bundle["change_summary"].get("to_date"),
            "change_count": detail_bundle["change_summary"].get("change_count"),
            "add_count": detail_bundle["change_summary"]["change_counts"].get("新增", 0),
            "increase_count": detail_bundle["change_summary"]["change_counts"].get("加碼", 0),
            "decrease_count": detail_bundle["change_summary"]["change_counts"].get("減碼", 0),
            "remove_count": detail_bundle["change_summary"]["change_counts"].get("刪除", 0),
        }])

    date_options = history_summary_df["snapshot_date"].astype(str).tolist()
    default_date = latest_snapshot_date if latest_snapshot_date in date_options else date_options[0]
    selected_snapshot_date = st.session_state.get(f"active_etf_selected_snapshot_{detail_bundle['code']}", default_date)
    if selected_snapshot_date not in date_options:
        selected_snapshot_date = default_date
        st.session_state[f"active_etf_selected_snapshot_{detail_bundle['code']}"] = selected_snapshot_date

    picked_snapshot_date = _render_date_timeline(
        detail_bundle["code"],
        history_summary_df,
        selected_snapshot_date,
        latest_snapshot_date,
    )
    if str(picked_snapshot_date) != str(selected_snapshot_date):
        st.session_state[f"active_etf_selected_snapshot_{detail_bundle['code']}"] = str(picked_snapshot_date)
        st.rerun()

    _render_selected_period_strip(
        history_summary_df[history_summary_df["snapshot_date"].astype(str) == str(picked_snapshot_date)].iloc[0]
    )

    if len(date_options) == 1:
        st.markdown(
            "<div class='active-etf-timeline-empty'>這檔 ETF 目前只回補到 1 個可用日期，所以時間軸先只有一張日期卡。通常代表外部歷史來源暫時不足，之後再整理時會繼續補齊。</div>",
            unsafe_allow_html=True,
        )

    selected_summary_row = history_summary_df[history_summary_df["snapshot_date"].astype(str) == str(picked_snapshot_date)].iloc[0]
    selected_changes_raw_df = load_etf_change_snapshot_items(detail_bundle["code"], str(picked_snapshot_date))
    if selected_changes_raw_df.empty and str(picked_snapshot_date) == str(latest_snapshot_date):
        selected_changes_raw_df = detail_bundle["raw_changes_df"].copy()

    selected_changes_df = _build_sorted_changes_table(selected_changes_raw_df, "增減量")
    counts = {
        "新增": int(selected_summary_row.get("add_count") or 0),
        "加碼": int(selected_summary_row.get("increase_count") or 0),
        "減碼": int(selected_summary_row.get("decrease_count") or 0),
        "刪除": int(selected_summary_row.get("remove_count") or 0),
    }

    _render_change_count_cards(counts)
    st.markdown("")

    sort_by = st.segmented_control(
        "持股變動排序",
        ["增減量", "持有金額"],
        default="增減量",
        key=f"active_etf_change_sort_{detail_bundle['code']}_{picked_snapshot_date}",
    )
    selected_changes_df = _build_sorted_changes_table(selected_changes_raw_df, sort_by)
    if selected_changes_df.empty:
        st.caption("這個日期目前沒有可用的持股變動資料。")
        return

    panel_cols = st.columns(2)
    with panel_cols[0]:
        _render_change_panel("新增 / 加碼", "up", selected_changes_raw_df, sort_by, ["新增", "加碼"])
    with panel_cols[1]:
        _render_change_panel("減碼 / 移出", "down", selected_changes_raw_df, sort_by, ["減碼", "移出"])
    st.markdown("")
    st.markdown("**完整明細**")
    _render_changes_dataframe(selected_changes_df)


def render_active_etf_page(state):
    _ = state
    _inject_active_etf_css()

    query_code = st.query_params.get("active_etf_code")
    query_date = st.query_params.get("active_etf_date")
    previous_query_code = st.session_state.get("_active_etf_query_code")
    if query_code:
        normalized_query_code = str(query_code)
        st.session_state["active_etf_selected_code"] = normalized_query_code
        st.session_state["active_etf_view_mode"] = "detail"
        if query_date:
            st.session_state[f"active_etf_selected_snapshot_{normalized_query_code}"] = str(query_date)
        elif previous_query_code != normalized_query_code:
            st.session_state.pop(f"active_etf_selected_snapshot_{normalized_query_code}", None)
        st.session_state["_active_etf_query_code"] = normalized_query_code
    elif "active_etf_view_mode" not in st.session_state:
        st.session_state["active_etf_view_mode"] = "list"

    st.subheader("主動 ETF 動向")

    top_n = 999
    control_cols = st.columns([0.9, 0.9, 4.2])
    with control_cols[0]:
        st.caption("排序依據")
        sort_by = st.selectbox(
            "排序依據",
            ["資金大小", "ETF編號"],
            index=0,
            key="active_etf_sort_by",
            label_visibility="collapsed",
        )
    with control_cols[1]:
        st.caption("升降冪")
        sort_order = st.selectbox(
            "升降冪",
            ["降冪", "升冪"],
            index=0,
            key="active_etf_sort_order",
            label_visibility="collapsed",
        )
    rerun_active_etf = False
    refresh_all_history = False

    history_job_id, history_job = ensure_background_data_job(
        "active_etf_history_job_id",
        "active_etf_history_refresh",
        ("v1", datetime.now().strftime("%Y-%m-%d")),
        refresh_all_active_etf_history_snapshots,
        running_message="正在整理全部主動 ETF 當日快照...",
        completed_message=lambda result=None, **_: f"已整理 {int((result or {}).get('count') or 0)} 檔主動 ETF 的當日快照",
        failed_message="整理全部主動 ETF 快照失敗",
        force_start=refresh_all_history,
    )

    overview_cache_key = ("v3", datetime.now().strftime("%Y-%m-%d"), int(top_n))
    overview_job_id, overview_job = ensure_background_data_job(
        "active_etf_overview_job_id",
        "active_etf_overview",
        overview_cache_key,
        load_active_etf_overview_data,
        args=("v3", datetime.now().strftime("%Y-%m-%d"), int(top_n)),
        running_message="正在整理主動式 ETF 最新動向...",
        completed_message="主動式 ETF 總覽已整理完成",
        failed_message="主動式 ETF 總覽整理失敗",
        force_start=rerun_active_etf,
    )

    if overview_job and overview_job["status"] == "failed":
        failed_job = get_background_data_job_manager().get_job(overview_job_id, include_result=False)
        st.error(f"讀取主動式 ETF 總覽失敗：{failed_job.get('error') or '未知錯誤'}")
        return
    if overview_job["status"] != "completed":
        st.info("主動式 ETF 資料背景整理中，完成後會自動刷新。")
        render_background_data_job_status("active_etf_overview_job_id", "主動 ETF 總覽背景任務")
        return

    overview_bundle = get_background_data_job_manager().get_job(overview_job_id, include_result=True).get("result")
    if not overview_bundle:
        st.caption("目前抓不到可用的主動式 ETF 資料。")
        return

    raw_df = _sort_active_etf_overview(overview_bundle["raw_df"].copy(), sort_by, sort_order)
    selector_label_map = {f"{row['code']}｜{row['name']}": row["code"] for _, row in raw_df.iterrows()}
    view_mode = st.session_state.get("active_etf_view_mode")
    selected_code = st.session_state.get("active_etf_selected_code")

    if view_mode != "detail":
        _render_etf_overview_list(raw_df)
        return

    if not selected_code:
        fallback_code = raw_df.iloc[0]["code"] if not raw_df.empty else None
        if fallback_code:
            navigate_to_active_etf(fallback_code)
        else:
            st.caption("目前沒有可用的 ETF 詳情資料。")
        return

    detail_cache_key = ("v5", datetime.now().strftime("%Y-%m-%d"), selected_code)
    detail_job_id, detail_job = ensure_background_data_job(
        "active_etf_detail_job_id",
        "active_etf_detail",
        detail_cache_key,
        load_active_etf_detail_data,
        args=("v5", datetime.now().strftime("%Y-%m-%d"), selected_code),
        running_message=f"正在整理 {selected_code} 主動 ETF 明細...",
        completed_message=f"{selected_code} 主動 ETF 明細已整理完成",
        failed_message=f"{selected_code} 主動 ETF 明細整理失敗",
        force_start=rerun_active_etf,
    )

    if detail_job and detail_job["status"] == "failed":
        failed_job = get_background_data_job_manager().get_job(detail_job_id, include_result=False)
        st.error(f"讀取這檔 ETF 明細失敗：{failed_job.get('error') or '未知錯誤'}")
        return
    if detail_job["status"] != "completed":
        st.info("這檔 ETF 的明細背景整理中，完成後會自動刷新。")
        render_background_data_job_status("active_etf_detail_job_id", "主動 ETF 明細背景任務")
        return

    detail_bundle = get_background_data_job_manager().get_job(detail_job_id, include_result=True).get("result")
    if not detail_bundle:
        st.caption("目前抓不到這檔 ETF 的明細。")
        return

    st.markdown("<div class='active-etf-detail-card'>", unsafe_allow_html=True)
    header_cols = st.columns([0.85, 0.15])
    with header_cols[0]:
        st.markdown(
            f"""
            <div class="active-etf-detail-header">
                <div>
                    <div class="active-etf-detail-name"><span class="active-etf-detail-code">{detail_bundle['code']}</span>{detail_bundle['name']}</div>
                    <div class="active-etf-detail-meta">
                        持股日：{detail_bundle['overview'].get('holdings_snapshot_date') or '-'} ｜ 持股範圍：{'全球 / 海外' if detail_bundle['overview'].get('scope') == 'foreign' else '台灣'} ｜ 發行公司：{detail_bundle['overview'].get('issuer') or '-'} ｜ 經理人：{detail_bundle['overview'].get('manager') or '-'}
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        if st.button("返回清單", key="active_etf_back_to_list", use_container_width=True):
            navigate_to_active_etf()
    st.markdown("</div>", unsafe_allow_html=True)

    tabs = st.tabs(["概覽", "成分股", "持股變動"])
    with tabs[0]:
        _render_overview_tab(detail_bundle)
    with tabs[1]:
        _render_holdings_tab(detail_bundle)
    with tabs[2]:
        _render_changes_tab(detail_bundle)
