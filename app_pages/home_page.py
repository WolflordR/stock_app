from datetime import datetime

import streamlit as st

from active_etf_watch import build_active_etf_overview_bundle
from app_constants import INSTITUTIONAL_STREAK_OPTIONS
from home_page_data import (
    build_homepage_daily_institutional_payload,
)
from home_page_sections import render_homepage_tabs
from homepage_brief import HOMEPAGE_BRIEF_STYLE, render_market_brief
from trading_calendar import resolve_recent_trade_date
from ui_data import load_active_etf_overview_data
from ui_data import load_homepage_disposition_watch
from ui_data import load_homepage_industry_flow_data
from ui_data import load_homepage_institutional_data
from ui_data import load_homepage_market_watch
from ui_data import load_homepage_revenue_momentum
from ui_data import load_homepage_schedule_data
from ui_data import load_industry_rotation_data
from ui_jobs import ensure_background_data_job, get_background_data_job_manager


@st.fragment(run_every="2s")
def _render_homepage_background_status(job_specs):
    manager = get_background_data_job_manager()
    rows = []
    completed_count = 0
    total_count = len(job_specs)
    progress_units = 0.0
    needs_rerun = False

    for session_key, label in job_specs:
        active_job_id = st.session_state.get(session_key)
        job = manager.get_job(active_job_id, include_result=False) if active_job_id else None
        if not job:
            rows.append((label, "queued"))
            continue

        status = str(job.get("status") or "queued")
        rows.append((label, status))

        if status in {"completed", "failed"}:
            completed_count += 1
            progress_units += 1.0
            finalized_key = f"{session_key}_finalized_job_id"
            if st.session_state.get(finalized_key) != active_job_id:
                st.session_state[finalized_key] = active_job_id
                needs_rerun = True
        elif status == "running":
            progress_units += 0.35
        elif status == "queued":
            progress_units += 0.08

    overall_progress = min(1.0, progress_units / total_count) if total_count else 1.0
    st.info(f"首頁背景資料整理中：已完成 {completed_count}/{total_count} 個資料源。")
    st.progress(overall_progress)

    pending_labels = [label for label, status in rows if status in {"queued", "running"}]
    if pending_labels:
        st.caption(f"背景整理中：{'、'.join(pending_labels)}")
    else:
        st.success("首頁資料已整理完成。")

    if needs_rerun:
        st.rerun()


def render_home_page(state):
    st.subheader("每日首頁")
    st.caption("這裡會先整理每天值得優先看的訊號：法人連買賣、資金流向、法說日程、月營收動能與處置股票。")
    st.markdown(HOMEPAGE_BRIEF_STYLE, unsafe_allow_html=True)
    cache_date = datetime.now().strftime("%Y-%m-%d")
    background_manager = get_background_data_job_manager()
    trade_date_resolution = resolve_recent_trade_date(state["home_trade_date"])
    effective_trade_date = trade_date_resolution["effective_date"]
    if trade_date_resolution["used_fallback"]:
        st.caption(
            f"首頁資料日期 {trade_date_resolution['requested_date']} 非交易日或尚無完整行情，"
            f"已自動改用最近可讀交易日：{trade_date_resolution['effective_date_text']}"
        )

    institutional_job_id, institutional_job = ensure_background_data_job(
        "homepage_institutional_job_id",
        "homepage_institutional",
        ("v8", cache_date, str(effective_trade_date), tuple(INSTITUTIONAL_STREAK_OPTIONS), 30),
        load_homepage_institutional_data,
        args=("v8", cache_date, effective_trade_date, tuple(INSTITUTIONAL_STREAK_OPTIONS), 30),
        running_message="正在整理首頁法人訊號...",
        completed_message="首頁法人訊號已整理完成",
        failed_message="首頁法人訊號整理失敗",
    )
    revenue_job_id, revenue_job = ensure_background_data_job(
        "homepage_revenue_job_id",
        "homepage_revenue",
        (
            "v2",
            cache_date,
            int(state["revenue_top_n"]),
            float(state["revenue_min_yoy_pct"]),
            float(state["revenue_min_mom_pct"]),
            float(state["revenue_min_cumulative_yoy_pct"]),
            int(state["revenue_required_consecutive_months"]),
            bool(state["revenue_exclude_february"]),
        ),
        load_homepage_revenue_momentum,
        args=(
            "v2",
            cache_date,
            int(state["revenue_top_n"]),
            float(state["revenue_min_yoy_pct"]),
            float(state["revenue_min_mom_pct"]),
            float(state["revenue_min_cumulative_yoy_pct"]),
            int(state["revenue_required_consecutive_months"]),
            bool(state["revenue_exclude_february"]),
        ),
        running_message="正在整理首頁月營收動能...",
        completed_message="首頁月營收動能已整理完成",
        failed_message="首頁月營收動能整理失敗",
    )
    market_watch_job_id, market_watch_job = ensure_background_data_job(
        "homepage_market_watch_job_id",
        "homepage_market_watch",
        ("v2", cache_date, str(effective_trade_date), int(state["market_watch_top_n"])),
        load_homepage_market_watch,
        args=("v2", cache_date, effective_trade_date, int(state["market_watch_top_n"])),
        running_message="正在整理漲跌停與鎖住名單...",
        completed_message="漲跌停與鎖住名單已整理完成",
        failed_message="漲跌停與鎖住名單整理失敗",
    )
    disposition_job_id, disposition_job = ensure_background_data_job(
        "homepage_disposition_job_id",
        "homepage_disposition",
        ("v3", cache_date, str(effective_trade_date)),
        load_homepage_disposition_watch,
        args=("v3", cache_date, effective_trade_date),
        running_message="正在整理處置股票...",
        completed_message="處置股票已整理完成",
        failed_message="處置股票整理失敗",
    )
    industry_home_job_id, industry_home_job = ensure_background_data_job(
        "homepage_industry_job_id",
        "homepage_industry_rotation",
        ("v2", cache_date, str(effective_trade_date), 8),
        load_industry_rotation_data,
        args=("v2", cache_date, effective_trade_date, 8),
        running_message="正在整理首頁產業輪動摘要...",
        completed_message="首頁產業輪動摘要已整理完成",
        failed_message="首頁產業輪動摘要整理失敗",
    )
    industry_flow_job_id, industry_flow_job = ensure_background_data_job(
        "homepage_industry_flow_job_id",
        "homepage_industry_flow",
        ("v2", cache_date, str(effective_trade_date), 21),
        load_homepage_industry_flow_data,
        args=("v2", cache_date, effective_trade_date, 21),
        running_message="正在整理首頁資金流向...",
        completed_message="首頁資金流向已整理完成",
        failed_message="首頁資金流向整理失敗",
    )
    active_etf_home_job_id, active_etf_home_job = ensure_background_data_job(
        "homepage_active_etf_job_id",
        "homepage_active_etf",
        ("v2", cache_date, 8),
        load_active_etf_overview_data,
        args=("v2", cache_date, 8),
        running_message="正在整理首頁主動 ETF 摘要...",
        completed_message="首頁主動 ETF 摘要已整理完成",
        failed_message="首頁主動 ETF 摘要整理失敗",
    )
    schedule_job_id, schedule_job = ensure_background_data_job(
        "homepage_schedule_job_id",
        "homepage_schedule",
        ("v1", cache_date),
        load_homepage_schedule_data,
        args=("v1", cache_date),
        running_message="正在整理首頁法說 / 發表會日程...",
        completed_message="首頁法說 / 發表會日程已整理完成",
        failed_message="首頁法說 / 發表會日程整理失敗",
    )

    daily_institutional = {}
    institutional_results = {}
    if institutional_job and institutional_job["status"] == "completed":
        institutional_payload = background_manager.get_job(institutional_job_id, include_result=True).get("result") or {}
        daily_institutional = institutional_payload.get("daily") or {}
        institutional_results = institutional_payload.get("streaks") or {}
    elif institutional_job and institutional_job["status"] in {"queued", "running"}:
        daily_institutional = build_homepage_daily_institutional_payload(
            effective_trade_date,
            30,
        )
        institutional_results = {}
    elif institutional_job and institutional_job["status"] == "failed":
        failed_job = background_manager.get_job(institutional_job_id, include_result=False)
        st.error(f"讀取首頁法人訊號失敗：{failed_job.get('error') or '未知錯誤'}")

    reference_dates = None
    for streak_days in sorted(INSTITUTIONAL_STREAK_OPTIONS, reverse=True):
        streak_group = institutional_results.get(streak_days, {})
        if streak_group.get("foreign"):
            reference_dates = streak_group["foreign"]["trade_dates"]
            break
        if streak_group.get("total"):
            reference_dates = streak_group["total"]["trade_dates"]
            break
    if reference_dates:
        st.caption(f"連續觀察交易日：{' / '.join(reference_dates)}")
    revenue_result = None
    if revenue_job and revenue_job["status"] == "completed":
        revenue_result = background_manager.get_job(revenue_job_id, include_result=True).get("result")
    elif revenue_job and revenue_job["status"] == "failed":
        failed_job = background_manager.get_job(revenue_job_id, include_result=False)
        st.error(f"讀取首頁月營收動能失敗：{failed_job.get('error') or '未知錯誤'}")

    market_watch_result = None
    if market_watch_job and market_watch_job["status"] == "completed":
        market_watch_result = background_manager.get_job(market_watch_job_id, include_result=True).get("result")
    elif market_watch_job and market_watch_job["status"] == "failed":
        failed_job = background_manager.get_job(market_watch_job_id, include_result=False)
        st.error(f"讀取首頁漲跌停名單失敗：{failed_job.get('error') or '未知錯誤'}")

    disposition_result = None
    if disposition_job and disposition_job["status"] == "completed":
        disposition_result = background_manager.get_job(disposition_job_id, include_result=True).get("result")
    elif disposition_job and disposition_job["status"] == "failed":
        failed_job = background_manager.get_job(disposition_job_id, include_result=False)
        st.error(f"讀取首頁處置股票失敗：{failed_job.get('error') or '未知錯誤'}")

    industry_home_bundle = None
    if industry_home_job and industry_home_job["status"] == "completed":
        industry_home_bundle = background_manager.get_job(industry_home_job_id, include_result=True).get("result")

    active_etf_home_bundle = None
    if active_etf_home_job and active_etf_home_job["status"] == "completed":
        active_etf_home_bundle = background_manager.get_job(active_etf_home_job_id, include_result=True).get("result")

    industry_flow_bundle = None
    if industry_flow_job and industry_flow_job["status"] == "completed":
        industry_flow_bundle = background_manager.get_job(industry_flow_job_id, include_result=True).get("result")
        summary_df = industry_flow_bundle.get("summary_df") if industry_flow_bundle else None
        has_20d_baseline = (
            summary_df is not None
            and not summary_df.empty
            and summary_df["avg_turnover_20d"].notna().any()
        )
        if not has_20d_baseline:
            industry_flow_bundle = load_homepage_industry_flow_data("v2", cache_date, effective_trade_date, 21)

    schedule_bundle = None
    if schedule_job and schedule_job["status"] == "completed":
        schedule_bundle = background_manager.get_job(schedule_job_id, include_result=True).get("result")

    home_data_jobs = [
        institutional_job,
        revenue_job,
        market_watch_job,
        disposition_job,
        industry_home_job,
        industry_flow_job,
        active_etf_home_job,
        schedule_job,
    ]
    _render_homepage_background_status(
        [
            ("homepage_institutional_job_id", "法人訊號"),
            ("homepage_revenue_job_id", "月營收動能"),
            ("homepage_market_watch_job_id", "漲跌停與鎖住名單"),
            ("homepage_disposition_job_id", "處置股票"),
            ("homepage_industry_job_id", "產業輪動摘要"),
            ("homepage_industry_flow_job_id", "資金流向"),
            ("homepage_active_etf_job_id", "主動 ETF 摘要"),
            ("homepage_schedule_job_id", "法說 / 發表會日程"),
        ]
    )
    completed_home_jobs = sum(1 for job in home_data_jobs if job and job["status"] in {"completed", "failed"})
    total_home_jobs = len(home_data_jobs)

    if completed_home_jobs < total_home_jobs:
        pending_labels = []
        if institutional_job and institutional_job["status"] in {"queued", "running"}:
            pending_labels.append("法人訊號")
        if revenue_job and revenue_job["status"] in {"queued", "running"}:
            pending_labels.append("月營收動能")
        if market_watch_job and market_watch_job["status"] in {"queued", "running"}:
            pending_labels.append("漲跌停與鎖住名單")
        if disposition_job and disposition_job["status"] in {"queued", "running"}:
            pending_labels.append("處置股票")
        if industry_home_job and industry_home_job["status"] in {"queued", "running"}:
            pending_labels.append("產業輪動摘要")
        if industry_flow_job and industry_flow_job["status"] in {"queued", "running"}:
            pending_labels.append("資金流向")
        if active_etf_home_job and active_etf_home_job["status"] in {"queued", "running"}:
            pending_labels.append("主動 ETF 摘要")
        if schedule_job and schedule_job["status"] in {"queued", "running"}:
            pending_labels.append("法說 / 發表會日程")
        if pending_labels:
            st.caption(f"背景整理中：{'、'.join(pending_labels)}。畫面已先顯示目前抓得到的資料；如果想看最新完整結果，再手動重新整理一次即可。")

    render_market_brief(
        {},
        revenue_result,
        market_watch_result,
        daily_institutional,
        industry_bundle=industry_home_bundle,
        active_etf_bundle=active_etf_home_bundle,
    )

    scan_summary_cols = st.columns(5)
    scan_summary_cols[0].metric("月營收動能檔數", revenue_result["screened_count"] if revenue_result else 0)
    scan_summary_cols[1].metric("漲停 / 跌停", f"{market_watch_result['limit_up_count'] if market_watch_result else 0} / {market_watch_result['limit_down_count'] if market_watch_result else 0}")
    scan_summary_cols[2].metric("鎖住漲跌停", f"{market_watch_result['locked_limit_up_count'] if market_watch_result else 0} / {market_watch_result['locked_limit_down_count'] if market_watch_result else 0}")
    scan_summary_cols[3].metric("處置股票", disposition_result["count"] if disposition_result else 0)
    scan_summary_cols[4].metric("主動 ETF", len(active_etf_home_bundle["raw_df"]) if active_etf_home_bundle else 0)

    render_homepage_tabs(
        state=state,
        background_manager=background_manager,
        daily_institutional=daily_institutional,
        institutional_results=institutional_results,
        revenue_result=revenue_result,
        market_watch_result=market_watch_result,
        disposition_result=disposition_result,
        industry_flow_bundle=industry_flow_bundle,
        industry_flow_job=industry_flow_job,
        industry_flow_job_id=industry_flow_job_id,
        schedule_bundle=schedule_bundle,
    )
