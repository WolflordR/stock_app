import streamlit as st

from backtest_models import BacktestScanRequest
from backtest_service import validate_backtest_request
from ui_jobs import get_backtest_job_manager
from ui_status import render_backtest_job_page_status


def render_backtest_page(state):
    st.subheader("回測 / 選股")
    active_scan_job_id = st.session_state.get("active_scan_job_id")
    if active_scan_job_id:
        render_backtest_job_page_status()
    else:
        st.caption("請先在左側設定模式、股票區間與策略條件，再按「開始執行」。")

    if not state["submit_button"]:
        return

    request = BacktestScanRequest.from_sidebar_state(state)
    validation_error = validate_backtest_request(request)
    if validation_error:
        st.error(validation_error)
    else:
        job_id = get_backtest_job_manager().start_job(request)
        st.session_state["active_scan_job_id"] = job_id
        st.success(f"背景任務已啟動，任務編號 {job_id}。你現在可以切去其他頁面，它會繼續跑。")
        st.rerun()

