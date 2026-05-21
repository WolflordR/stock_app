from datetime import datetime

import pandas as pd
import streamlit as st

from modules.backtest.backtest_models import HomepageRangeScanRequest
from modules.research.research_workbench_data import (
    TECH_INDUSTRY_NAMES,
    attach_official_industry_column as _attach_official_industry_column,
    attach_theme_column as _attach_theme_column,
    build_research_candidate_display_df as _build_research_candidate_display_df,
    build_research_institutional_signals_payload as _build_research_institutional_signals_payload,
    summarize_candidate_dashboard,
)
from modules.core.trading_calendar import resolve_recent_trade_date
from modules.ui.ui_jobs import ensure_background_data_job, get_background_data_job_manager, get_homepage_range_scan_job_manager
from modules.ui.ui_status import render_background_data_job_status, render_range_scan_job_live_status


def _build_research_candidate_cache_key(state, trade_date):
    return (
        "research_workbench_candidates_v1",
        str(trade_date),
        int(state["start_num"]),
        int(state["end_num"]),
        int(state["range_lookback_days"]),
        float(state["range_max_width_pct"]),
        float(state["range_volume_ratio"]),
        float(state["range_min_price_gain_pct"]),
        float(state["range_max_price_gain_pct"]),
        int(state["range_volume_sustain_days"]),
    )


def render_research_candidate_tab(state):
    st.write("**起漲候選濾網**")
    st.caption("這裡先保留每天當下的起漲候選清單，搭配投信連買訊號一起看。")

    control_cols = st.columns([1.0, 1.0])
    trade_date = control_cols[0].date_input(
        "研究日期",
        value=st.session_state.get("research_workbench_trade_date", state["home_trade_date"]),
        key="research_workbench_trade_date",
    )
    trade_date_resolution = resolve_recent_trade_date(trade_date)
    effective_trade_date = trade_date_resolution["effective_date"]
    if trade_date_resolution["used_fallback"]:
        st.caption(
            f"研究日期 {trade_date_resolution['requested_date']} 非交易日或尚無完整行情，"
            f"已自動改用最近可讀交易日：{trade_date_resolution['effective_date_text']}"
        )
    candidate_top_n = control_cols[1].selectbox(
        "候選顯示筆數",
        [10, 15, 20, 30],
        index=1,
        key="research_workbench_top_n",
    )
    action_cols = st.columns([0.9, 0.9, 0.9, 2.3])
    rerun_scan = action_cols[0].button("執行", use_container_width=True, key="run_research_candidates")
    rerun_candidate_scan = action_cols[1].button("重新整理", use_container_width=True, key="rerun_research_candidates")
    clear_candidate_scan = action_cols[2].button("清除結果", use_container_width=True, key="clear_research_candidates")
    action_cols[3].caption("候選與投信重疊都改成手動執行，先把流程維持簡單。")
    if clear_candidate_scan:
        st.session_state["research_candidate_scan_job_id"] = None
        st.session_state["research_institutional_job_id"] = None
        st.rerun()

    candidate_cache_key = _build_research_candidate_cache_key(state, effective_trade_date)
    if rerun_scan or rerun_candidate_scan:
        st.session_state["research_candidate_refresh_token"] = datetime.now().isoformat(timespec="seconds")
    candidate_refresh_token = st.session_state.get("research_candidate_refresh_token", datetime.now().strftime("%Y-%m-%d"))
    candidate_cache_key = (*candidate_cache_key, candidate_refresh_token)

    request_state = dict(state)
    request_state["home_trade_date"] = effective_trade_date
    request = HomepageRangeScanRequest.from_sidebar_state(request_state)
    candidate_job_id = st.session_state.get("research_candidate_scan_job_id")
    candidate_job = get_homepage_range_scan_job_manager().get_job(candidate_job_id) if candidate_job_id else None
    if candidate_job and candidate_job.get("cache_key") != candidate_cache_key:
        candidate_job = None
    if rerun_scan or rerun_candidate_scan:
        candidate_job_id = get_homepage_range_scan_job_manager().get_or_create_job(
            candidate_cache_key,
            request,
            label="研究工作台盤整吸籌掃描",
        )
        st.session_state["research_candidate_scan_job_id"] = candidate_job_id
        candidate_job = get_homepage_range_scan_job_manager().get_job(candidate_job_id)

    institutional_cache_key = ("v3", datetime.now().strftime("%Y-%m-%d"), str(effective_trade_date))
    institutional_job_id, institutional_job = ensure_background_data_job(
        "research_institutional_job_id",
        "research_institutional_signals",
        institutional_cache_key,
        _build_research_institutional_signals_payload,
        args=(effective_trade_date,),
        running_message="正在整理投信 / 外資連買訊號...",
        completed_message="投信 / 外資連買訊號已整理完成",
        failed_message="投信 / 外資連買訊號整理失敗",
        autostart=False,
        force_start=(rerun_scan or rerun_candidate_scan),
    )

    candidate_results = {}
    if candidate_job and candidate_job["status"] == "completed":
        candidate_results = candidate_job.get("result") or {}
    elif candidate_job and candidate_job["status"] == "failed":
        st.warning(f"盤整吸籌候選掃描失敗：{candidate_job.get('error') or '未知錯誤'}")

    institutional_signals = {}
    if institutional_job and institutional_job["status"] == "completed":
        institutional_signals = get_background_data_job_manager().get_job(institutional_job_id, include_result=True).get("result") or {}
    elif institutional_job and institutional_job["status"] == "failed":
        failed_job = get_background_data_job_manager().get_job(institutional_job_id, include_result=False)
        st.warning(f"讀取投信 / 外資連買訊號失敗：{failed_job.get('error') or '未知錯誤'}")

    if not candidate_job and not institutional_job:
        st.info("目前是手動模式。按上面的 `執行候選掃描` 後，才會整理候選與法人重疊訊號。")
    if candidate_job and candidate_job["status"] in {"queued", "running"}:
        st.info("盤整吸籌候選背景掃描中，完成後會自動刷新。")
        render_range_scan_job_live_status("research_candidate_scan_job_id")
    if institutional_job and institutional_job["status"] in {"queued", "running"}:
        st.info("投信 / 外資連買訊號背景整理中，完成後會自動刷新。")
        render_background_data_job_status("research_institutional_job_id", "研究訊號背景任務")

    trust_3d = institutional_signals.get("trust_3d")
    trust_5d = institutional_signals.get("trust_5d")

    candidate_df = _build_research_candidate_display_df(
        candidate_results or {},
        effective_trade_date,
        trust_3d,
        top_n=candidate_top_n,
    )
    candidate_df = _attach_theme_column(candidate_df)
    candidate_df = _attach_official_industry_column(candidate_df)
    candidate_stats = summarize_candidate_dashboard(candidate_df)

    summary_cols = st.columns(4)
    summary_cols[0].metric("盤整吸籌候選", len(candidate_results or {}))
    summary_cols[1].metric("A / B / C", f"{candidate_stats['grade_counts']['A']} / {candidate_stats['grade_counts']['B']} / {candidate_stats['grade_counts']['C']}")
    summary_cols[2].metric("投信連3日重疊", candidate_stats["trust_overlap"])
    summary_cols[3].metric("觀察日期", effective_trade_date.strftime("%Y-%m-%d"))

    insight_cols = st.columns(2)
    insight_cols[0].caption(f"候選最集中主題：{candidate_stats['top_theme']}")
    avg_volume_ratio = candidate_stats["avg_volume_ratio"]
    insight_cols[1].caption(
        "平均當日量增倍數："
        + (f"{avg_volume_ratio:.2f}x" if avg_volume_ratio is not None else "-")
    )

    filter_cols = st.columns([0.9, 1.0, 1.0])
    grade_filter = filter_cols[0].segmented_control(
        "候選分級",
        ["全部", "A", "B", "C"],
        default="全部",
        key="research_candidate_grade_filter",
    )
    sort_choice = filter_cols[1].selectbox(
        "排序方式",
        ["產業排序（科技股優先）", "盤整吸籌分數", "當日量增倍數", "近3日量增倍數", "投信連3日優先"],
        index=0,
        key="research_candidate_sort_choice",
    )
    only_trust_overlap = filter_cols[2].toggle(
        "只看投信重疊",
        value=False,
        key="research_candidate_only_trust_overlap",
    )

    candidate_display_df = candidate_df.copy()
    if grade_filter != "全部" and not candidate_display_df.empty:
        candidate_display_df = candidate_display_df[candidate_display_df["級別"] == grade_filter].copy()
    if only_trust_overlap and not candidate_display_df.empty and "投信連3日" in candidate_display_df.columns:
        candidate_display_df = candidate_display_df[candidate_display_df["投信連3日"] == "是"].copy()

    if not candidate_display_df.empty:
        if sort_choice == "產業排序（科技股優先）":
            candidate_display_df["__industry_sort"] = candidate_display_df["官方產業"].fillna("未分類").astype(str)
            candidate_display_df["__theme_sort"] = candidate_display_df["細分產業"].fillna("未分類").astype(str)
            candidate_display_df["__tech_priority"] = candidate_display_df["官方產業"].map(
                lambda value: 0 if str(value).strip() in TECH_INDUSTRY_NAMES else 1
            )
            candidate_display_df["__score_sort"] = pd.to_numeric(
                candidate_display_df["盤整吸籌分數"],
                errors="coerce",
            ).fillna(0)
            candidate_display_df = (
                candidate_display_df.sort_values(
                    ["__tech_priority", "__industry_sort", "__theme_sort", "__score_sort"],
                    ascending=[True, True, True, False],
                    na_position="last",
                )
                .drop(columns=["__industry_sort", "__theme_sort", "__tech_priority", "__score_sort"])
            )
        elif sort_choice == "當日量增倍數":
            candidate_display_df["__sort_key"] = pd.to_numeric(
                candidate_display_df["當日量增倍數"].astype(str).str.replace("x", "", regex=False),
                errors="coerce",
            )
        elif sort_choice == "近3日量增倍數":
            candidate_display_df["__sort_key"] = pd.to_numeric(
                candidate_display_df["近3日量增倍數"].astype(str).str.replace("x", "", regex=False),
                errors="coerce",
            )
        elif sort_choice == "投信連3日優先":
            candidate_display_df["__sort_key"] = (
                (candidate_display_df["投信連3日"] == "是").astype(int) * 1000
                + pd.to_numeric(candidate_display_df["盤整吸籌分數"], errors="coerce").fillna(0)
            )
        else:
            candidate_display_df["__sort_key"] = pd.to_numeric(candidate_display_df["盤整吸籌分數"], errors="coerce")
        if "__sort_key" in candidate_display_df.columns:
            candidate_display_df = candidate_display_df.sort_values("__sort_key", ascending=False, na_position="last").drop(columns="__sort_key")

    left_col, right_col = st.columns([1.3, 1.0])
    with left_col:
        st.write("**優先候選清單**")
        st.caption("先看盤整吸籌分數高、量能抬頭、而且還留在盤整區內的股票。")
        if not candidate_display_df.empty:
            st.dataframe(candidate_display_df, use_container_width=True, hide_index=True)
        else:
            st.caption("目前這個篩選條件下沒有可用的候選。")

    with right_col:
        st.write("**投信初見客**")
        st.caption("投信過去不太碰，但最近開始連續買超，通常更值得追蹤。")
        if trust_3d and not trust_3d["buy_rank_df"].empty:
            trust_3d_df = _attach_theme_column(trust_3d["buy_rank_df"])
            trust_3d_df = _attach_official_industry_column(trust_3d_df)
            st.dataframe(trust_3d_df, use_container_width=True, hide_index=True)
        else:
            st.caption("目前抓不到投信連3日的連買名單。")

    if trust_5d and not trust_5d["buy_rank_df"].empty:
        st.write("**投信連5日名單**")
        st.caption("如果你想看更偏中期建倉的訊號，這份名單會更乾淨。")
        trust_5d_df = _attach_theme_column(trust_5d["buy_rank_df"])
        trust_5d_df = _attach_official_industry_column(trust_5d_df)
        st.dataframe(trust_5d_df, use_container_width=True, hide_index=True)
