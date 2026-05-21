from datetime import datetime

import streamlit as st

from modules.ui.ui_backtest_results import render_scan_results
from modules.ui.ui_jobs import get_background_data_job_manager, get_backtest_job_manager, get_homepage_range_scan_job_manager


def _param_value(params, field_name, default=None):
    if isinstance(params, dict):
        return params.get(field_name, default)
    return getattr(params, field_name, default)


def _format_duration_seconds(total_seconds):
    if total_seconds is None:
        return "-"
    total_seconds = max(int(total_seconds), 0)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小時{minutes}分"
    if minutes:
        return f"{minutes}分{seconds}秒"
    return f"{seconds}秒"


def _build_job_timing_text(job):
    created_at_text = job.get("created_at")
    if not created_at_text:
        return None
    try:
        created_at = datetime.fromisoformat(created_at_text)
    except Exception:
        return None

    elapsed_seconds = max((datetime.now() - created_at).total_seconds(), 0)
    progress = float(job.get("progress", 0.0) or 0.0)
    if progress >= 0.02 and progress < 1.0:
        estimated_total = elapsed_seconds / progress
        remaining_seconds = max(estimated_total - elapsed_seconds, 0)
        return f"已執行 {_format_duration_seconds(elapsed_seconds)}，預估還要 {_format_duration_seconds(remaining_seconds)}"
    return f"已執行 {_format_duration_seconds(elapsed_seconds)}"


@st.fragment(run_every="2s")
def render_backtest_job_sidebar_status():
    active_job_id = st.session_state.get("active_scan_job_id")
    if not active_job_id:
        return

    job = get_backtest_job_manager().get_job(active_job_id)
    if not job:
        st.session_state["active_scan_job_id"] = None
        return

    with st.expander("背景回測任務", expanded=(job["status"] in {"queued", "running"})):
        st.caption(f"任務編號：{job['job_id']}")
        st.caption(f"狀態：{job['status']}")
        st.progress(float(job.get("progress", 0.0)))
        st.caption(job.get("message") or "背景回測中")
        st.caption("你可以切去其他頁面，這個任務會繼續執行；狀態會自動更新。")
        if job["status"] == "failed":
            st.error(f"任務失敗：{job.get('error')}")
        elif job["status"] == "completed":
            st.success("背景回測已完成，回到「回測 / 選股」頁面就能看結果。")
        if st.button("清除背景任務", key="sidebar_clear_scan_job", use_container_width=True):
            st.session_state["active_scan_job_id"] = None
            st.rerun()


@st.fragment(run_every="2s")
def render_backtest_job_page_status():
    active_job_id = st.session_state.get("active_scan_job_id")
    if not active_job_id:
        return

    job = get_backtest_job_manager().get_job(active_job_id)
    if not job:
        st.session_state["active_scan_job_id"] = None
        return

    with st.expander("背景任務狀態", expanded=(job["status"] in {"queued", "running"})):
        status_cols = st.columns(4)
        status_cols[0].metric("任務編號", job["job_id"])
        status_cols[1].metric("狀態", job["status"])
        status_cols[2].metric("進度", f"{job['progress'] * 100:.1f}%")
        status_cols[3].metric("模式", _param_value(job["params"], "mode"))
        st.caption(job.get("message") or "背景任務待命中")
        st.progress(float(job.get("progress", 0.0)))
        st.caption("切去其他頁面後，這個任務會在背景繼續跑；這裡會自動更新最新進度。")

        if job["status"] == "failed":
            st.error(f"背景任務失敗：{job.get('error')}")
        elif job["status"] == "completed":
            render_scan_results(job.get("result") or {}, job["params"])
        else:
            st.info("背景任務執行中。")

        if st.button("清除任務狀態", key="clear_active_scan_job", use_container_width=True):
            st.session_state["active_scan_job_id"] = None
            st.rerun()


@st.fragment(run_every="2s")
def render_range_scan_job_live_status(session_key="active_homepage_range_scan_job_id", cache_key=None):
    active_job_id = st.session_state.get(session_key)
    if not active_job_id:
        return

    job = get_homepage_range_scan_job_manager().get_job(active_job_id)
    if not job:
        st.session_state[session_key] = None
        return

    if job["status"] == "completed":
        if cache_key:
            st.session_state[cache_key] = {
                "key": job.get("cache_key"),
                "results": job.get("result") or {},
                "scanned_at": job.get("scanned_at"),
            }
        st.session_state[session_key] = None
        st.rerun()
        return

    if job["status"] == "failed":
        st.error(f"盤整吸籌掃描失敗：{job.get('error') or '未知錯誤'}")
        return

    st.progress(float(job.get("progress", 0.0)))
    st.caption(job.get("message") or "盤整吸籌掃描中")


def render_homepage_range_scan_live_status():
    render_range_scan_job_live_status(
        session_key="active_homepage_range_scan_job_id",
        cache_key="homepage_range_scan_cache",
    )


@st.fragment(run_every="2s")
def render_background_data_job_status(session_key, title="背景資料"):
    active_job_id = st.session_state.get(session_key)
    if not active_job_id:
        return

    manager = get_background_data_job_manager()
    job = manager.get_job(active_job_id, include_result=False)
    if not job:
        st.session_state[session_key] = None
        return

    finalized_key = f"{session_key}_finalized_job_id"
    if job["status"] in {"completed", "failed"}:
        if st.session_state.get(finalized_key) != active_job_id:
            st.session_state[finalized_key] = active_job_id
            st.rerun()
        return

    with st.expander(title, expanded=True):
        st.caption(f"任務編號：{job['job_id']}")
        st.caption(f"狀態：{job['status']}")
        st.progress(float(job.get("progress", 0.0)))
        st.caption(job.get("message") or "背景整理中")
        timing_text = _build_job_timing_text(job)
        if timing_text:
            st.caption(timing_text)
        st.caption("你可以先看其他內容，完成後頁面會自動刷新。")


@st.fragment(run_every="2s")
def render_background_data_job_status_list(job_specs, title="背景資料任務"):
    manager = get_background_data_job_manager()
    rows = []
    needs_rerun = False

    for session_key, label in job_specs:
        active_job_id = st.session_state.get(session_key)
        if not active_job_id:
            continue
        job = manager.get_job(active_job_id, include_result=False)
        if not job:
            st.session_state[session_key] = None
            continue
        finalized_key = f"{session_key}_finalized_job_id"
        if job["status"] in {"completed", "failed"}:
            if st.session_state.get(finalized_key) != active_job_id:
                st.session_state[finalized_key] = active_job_id
                needs_rerun = True
            continue

        rows.append(
            {
                "項目": label,
                "狀態": job.get("status"),
                "進度": f"{float(job.get('progress', 0.0)) * 100:.0f}%",
                "訊息": job.get("message") or "背景整理中",
                "耗時 / 預估": _build_job_timing_text(job) or "-",
            }
        )

    if needs_rerun:
        st.rerun()
        return

    if not rows:
        return

    with st.expander(title, expanded=True):
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.caption("資料會在背景繼續整理，完成後頁面會自動刷新。")
