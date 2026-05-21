from datetime import datetime

import pandas as pd
import streamlit as st

from modules.industry.industry_rotation import build_industry_rotation_bundle, build_theme_member_display_df
from modules.industry.industry_page_helpers import (
    build_combined_rotation_display_df,
    build_combined_rotation_series_df,
    build_combined_rotation_summary_df,
    build_market_tone_summary,
    render_summary_metric_card,
)
from modules.industry.industry_page_sections import (
    render_battle_room_tab,
    render_official_indices_tab,
    render_theme_members_tab,
)
from modules.core.trading_calendar import resolve_recent_trade_date
from modules.ui.ui_jobs import ensure_background_data_job, get_background_data_job_manager
from modules.ui.ui_status import render_background_data_job_status


def render_industry_rotation_page(state):
    st.subheader("產業輪動")
    st.caption("這一頁主畫面只看細分主題，讓記憶體、CPO、光通訊、散熱、ABF、AI 伺服器這些題材可以直接放在一起比。細分主題的「報價」採 100 基期等權主題指數，方便觀察資金輪動，並不是交易所官方指數。")
    st.markdown(
        """
        <style>
        .industry-summary-card {
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-radius: 0.9rem;
            padding: 0.9rem 1rem 1rem 1rem;
            background: rgba(15, 23, 42, 0.04);
            min-height: 7.5rem;
        }
        .industry-summary-label {
            font-size: 0.92rem;
            color: #94a3b8;
            margin-bottom: 0.55rem;
            line-height: 1.25;
        }
        .industry-summary-value {
            font-size: clamp(1.45rem, 2.2vw, 3rem);
            font-weight: 700;
            line-height: 1.05;
            letter-spacing: -0.02em;
            word-break: break-word;
            overflow-wrap: anywhere;
        }
        .industry-tone-box {
            border: 1px solid rgba(96, 165, 250, 0.22);
            border-radius: 1rem;
            padding: 1.05rem 1.15rem 1.05rem 1.15rem;
            background:
                radial-gradient(circle at top right, rgba(37, 99, 235, 0.28), transparent 34%),
                radial-gradient(circle at bottom left, rgba(220, 38, 38, 0.18), transparent 30%),
                linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(17, 24, 39, 0.90));
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
            margin-bottom: 1rem;
        }
        .industry-tone-title {
            font-size: 1.15rem;
            font-weight: 800;
            margin-bottom: 0.45rem;
            color: #f8fafc;
            letter-spacing: -0.01em;
        }
        .industry-tone-summary {
            font-size: 0.96rem;
            color: #dbeafe;
            line-height: 1.7;
            margin-bottom: 0.85rem;
        }
        .industry-tone-signal {
            font-size: 0.92rem;
            color: #e2e8f0;
            margin-bottom: 0.32rem;
            line-height: 1.5;
            text-shadow: 0 1px 0 rgba(15, 23, 42, 0.45);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    control_cols = st.columns([1.15, 0.9, 1.0, 1.0])
    trade_date = control_cols[0].date_input(
        "觀察日期",
        value=st.session_state.get("industry_rotation_trade_date", state["home_trade_date"]),
        key="industry_rotation_trade_date",
    )
    trade_date_resolution = resolve_recent_trade_date(trade_date)
    effective_trade_date = trade_date_resolution["effective_date"]
    if trade_date_resolution["used_fallback"]:
        st.caption(
            f"產業觀察日期 {trade_date_resolution['requested_date']} 非交易日或尚無完整行情，"
            f"已自動改用最近可讀交易日：{trade_date_resolution['effective_date_text']}"
        )
    history_trade_days = control_cols[1].selectbox(
        "回看交易日",
        [6, 8, 10, 12],
        index=1,
        key="industry_rotation_history_trade_days",
    )
    theme_top_n = control_cols[2].selectbox(
        "主題成分股顯示筆數",
        [12, 15, 20, 30],
        index=2,
        key="industry_rotation_theme_top_n",
    )
    industry_top_n = control_cols[3].selectbox(
        "官方產業顯示筆數",
        [8, 10, 12, 15],
        index=2,
        key="industry_rotation_industry_top_n",
    )
    action_cols = st.columns([0.9, 0.9, 0.9, 2.3])
    run_rotation = action_cols[0].button("執行", use_container_width=True, key="run_industry_rotation")
    rerun_rotation = action_cols[1].button("重新整理", use_container_width=True, key="rerun_industry_rotation")
    clear_rotation = action_cols[2].button("清除結果", use_container_width=True, key="clear_industry_rotation")
    action_cols[3].caption("只有按下按鈕時才整理產業輪動。")
    if clear_rotation:
        st.session_state["industry_rotation_job_id"] = None
        st.rerun()

    cache_key = (
        "v2",
        datetime.now().strftime("%Y-%m-%d"),
        str(effective_trade_date),
        int(history_trade_days),
    )
    job_id, job = ensure_background_data_job(
        "industry_rotation_job_id",
        "industry_rotation",
        cache_key,
        build_industry_rotation_bundle,
        args=(effective_trade_date,),
        kwargs={"history_trade_days": history_trade_days},
        running_message="正在整理科技股產業輪動...",
        completed_message="產業輪動資料已整理完成",
        failed_message="產業輪動資料整理失敗",
        autostart=False,
        force_start=(run_rotation or rerun_rotation),
    )

    if job and job["status"] == "failed":
        failed_job = get_background_data_job_manager().get_job(job_id, include_result=False)
        st.error(f"讀取產業輪動資料失敗：{failed_job.get('error') or '未知錯誤'}")
        return

    if not job:
        st.info("目前是手動模式。按上面的 `執行產業輪動整理` 後，才會丟進背景 queue。")
        return

    if job["status"] != "completed":
        st.info("產業輪動資料背景整理中，完成後會自動刷新。")
        render_background_data_job_status("industry_rotation_job_id", "產業輪動背景任務")
        return

    rotation_bundle = get_background_data_job_manager().get_job(job_id, include_result=True).get("result")

    if not rotation_bundle:
        st.caption("目前抓不到足夠的產業輪動資料，可能是最近行情來源暫時不可用。")
        return

    summary = rotation_bundle["summary"]
    theme_report = rotation_bundle["theme_report"]
    industry_report = rotation_bundle["industry_report"]
    twse_index_snapshot = rotation_bundle.get("twse_index_snapshot")
    theme_summary_df = theme_report["summary_df"].copy()
    industry_summary_df = industry_report["summary_df"].copy()
    theme_series_df = theme_report["series_df"].copy()
    focus_summary_df = build_combined_rotation_summary_df(theme_summary_df, pd.DataFrame())
    focus_display_df = build_combined_rotation_display_df(theme_summary_df, pd.DataFrame())
    focus_series_df = build_combined_rotation_series_df(theme_series_df, pd.DataFrame())
    tone_summary = build_market_tone_summary(focus_summary_df)

    metric_cols = st.columns(5)
    with metric_cols[0]:
        render_summary_metric_card("行情資料日", summary["used_date"])
    with metric_cols[1]:
        render_summary_metric_card("追蹤主題數", summary["theme_count"])
    with metric_cols[2]:
        render_summary_metric_card("分數加速主題", focus_summary_df.sort_values(["score_delta_1d", "score_delta_3d"], ascending=[False, False]).iloc[0]["group_name"] if not focus_summary_df.empty else "-")
    with metric_cols[3]:
        render_summary_metric_card("量能最強主題", summary["top_theme"] or "-")
    with metric_cols[4]:
        render_summary_metric_card(
            "最強主題量比",
            f"{summary['top_theme_volume_ratio']:.2f}x" if summary.get("top_theme_volume_ratio") is not None else "-",
        )

    tone_html = "".join(
        f"<div class='industry-tone-signal'>• {signal}</div>"
        for signal in tone_summary["signals"]
    )
    st.markdown(
        f"""
        <div class="industry-tone-box">
            <div class="industry-tone-title">今日市場定調｜{tone_summary['title']}</div>
            <div class="industry-tone-summary">{tone_summary['summary']}</div>
            {tone_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    page_tabs = st.tabs(["輪動戰情室", "主題成分股", "類股指數 / 補充"])

    with page_tabs[0]:
        render_battle_room_tab(
            focus_summary_df=focus_summary_df,
            focus_series_df=focus_series_df,
        )

    with page_tabs[1]:
        render_theme_members_tab(theme_summary_df, theme_report)

    with page_tabs[2]:
        render_official_indices_tab(industry_report, twse_index_snapshot, industry_top_n)
