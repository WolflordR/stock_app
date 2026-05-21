from __future__ import annotations

from backtest_models import BacktestScanRequest, HomepageRangeScanRequest
from func import scan_market


def validate_backtest_request(request: BacktestScanRequest) -> str | None:
    if request.start_num > request.end_num:
        return "❌ 起始代碼不能大於結束代碼！"
    if not request.selected_strategies:
        return "❌ 請至少勾選一個「買入策略」！"
    if request.mode == "歷史回測":
        if request.start_date is None or request.end_date is None:
            return "❌ 回測模式需要設定開始日與結束日！"
        if request.start_date > request.end_date:
            return "❌ 回測開始日不能晚於結束日！"
        if not request.selected_sell_strategies:
            return "❌ 回測模式下，請至少勾選一個「賣出策略」！"
    return None


def run_backtest_scan(
    request: BacktestScanRequest,
    *,
    progress_callback=None,
    status_callback=None,
):
    return scan_market(
        **request.to_engine_kwargs(),
        progress_callback=progress_callback,
        status_callback=status_callback,
    )


def run_homepage_range_scan(
    request: HomepageRangeScanRequest,
    *,
    request_delay_sec: float,
    progress_callback=None,
    status_callback=None,
):
    return scan_market(
        **request.to_engine_kwargs(),
        request_delay_sec=request_delay_sec,
        progress_callback=progress_callback,
        status_callback=status_callback,
    )
