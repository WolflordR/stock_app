from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class BacktestScanRequest:
    start_num: int
    end_num: int
    selected_strategies: list[str] = field(default_factory=list)
    mode: str = "歷史回測"
    start_date: date | None = None
    end_date: date | None = None
    selected_sell_strategies: list[str] = field(default_factory=list)
    range_lookback_days: int = 60
    range_max_width_pct: float = 65.0
    range_volume_ratio: float = 1.3
    range_min_price_gain_pct: float = 0.0
    range_max_price_gain_pct: float = 18.0
    range_volume_sustain_days: int = 3
    initial_capital: int = 100000
    trading_cost_pct: float = 0.7
    initial_stop_loss_pct: float = 5.0
    w_bottom_lookback_days: int = 40
    w_bottom_tolerance_pct: float = 3.0
    w_bottom_min_rebound_pct: float = 5.0
    w_bottom_lower_shadow_ratio: float = 0.4
    w_bottom_stop_buffer_pct: float = 1.5
    gap_channel_lookback_days: int = 20
    gap_channel_max_width_pct: float = 18.0
    gap_lookback_days: int = 10
    gap_min_gap_pct: float = 0.5
    gap_hold_tolerance_pct: float = 1.0
    gap_lower_shadow_lookback_days: int = 5
    gap_lower_shadow_ratio: float = 0.4
    gap_stop_buffer_pct: float = 1.0
    trailing_stop_activation_pct: float = 8.0
    trailing_stop_drawdown_pct: float = 8.0
    request_delay_sec: float = 0.02
    benchmark_symbol: str = "0050.TW"
    rs_lookback_days: int = 60
    rs_min_outperformance_pct: float = 5.0
    vcp_lookback_days: int = 60
    vcp_min_uptrend_pct: float = 12.0
    vcp_breakout_volume_ratio: float = 1.0
    vcp_near_pivot_tolerance_pct: float = 12.0
    vcp_max_consolidation_depth_pct: float = 45.0

    @classmethod
    def from_sidebar_state(cls, state: dict[str, Any]) -> "BacktestScanRequest":
        return cls(
            start_num=int(state["start_num"]),
            end_num=int(state["end_num"]),
            selected_strategies=list(state["selected_strategies"]),
            mode=state["mode"],
            start_date=state["start_date"] if state["mode"] == "歷史回測" else None,
            end_date=state["end_date"] if state["mode"] == "歷史回測" else None,
            selected_sell_strategies=list(state["selected_sell_strategies"]),
            range_lookback_days=int(state["range_lookback_days"]),
            range_max_width_pct=float(state["range_max_width_pct"]),
            range_volume_ratio=float(state["range_volume_ratio"]),
            range_min_price_gain_pct=float(state["range_min_price_gain_pct"]),
            range_max_price_gain_pct=float(state["range_max_price_gain_pct"]),
            range_volume_sustain_days=int(state["range_volume_sustain_days"]),
            initial_capital=int(state["initial_capital"]),
            trading_cost_pct=float(state["trading_cost_pct"]),
            initial_stop_loss_pct=float(state["initial_stop_loss_pct"]),
            w_bottom_lookback_days=int(state["w_bottom_lookback_days"]),
            w_bottom_tolerance_pct=float(state["w_bottom_tolerance_pct"]),
            w_bottom_min_rebound_pct=float(state["w_bottom_min_rebound_pct"]),
            w_bottom_lower_shadow_ratio=float(state["w_bottom_lower_shadow_ratio"]),
            w_bottom_stop_buffer_pct=float(state["w_bottom_stop_buffer_pct"]),
            gap_channel_lookback_days=int(state["gap_channel_lookback_days"]),
            gap_channel_max_width_pct=float(state["gap_channel_max_width_pct"]),
            gap_lookback_days=int(state["gap_lookback_days"]),
            gap_min_gap_pct=float(state["gap_min_gap_pct"]),
            gap_hold_tolerance_pct=float(state["gap_hold_tolerance_pct"]),
            gap_lower_shadow_lookback_days=int(state["gap_lower_shadow_lookback_days"]),
            gap_lower_shadow_ratio=float(state["gap_lower_shadow_ratio"]),
            gap_stop_buffer_pct=float(state["gap_stop_buffer_pct"]),
            trailing_stop_activation_pct=float(state["trailing_stop_activation_pct"]),
            trailing_stop_drawdown_pct=float(state["trailing_stop_drawdown_pct"]),
            request_delay_sec=float(state["request_delay_sec"]),
            benchmark_symbol=state["benchmark_symbol"],
            rs_lookback_days=int(state["rs_lookback_days"]),
            rs_min_outperformance_pct=float(state["rs_min_outperformance_pct"]),
            vcp_lookback_days=int(state["vcp_lookback_days"]),
            vcp_min_uptrend_pct=float(state["vcp_min_uptrend_pct"]),
            vcp_breakout_volume_ratio=float(state["vcp_breakout_volume_ratio"]),
            vcp_near_pivot_tolerance_pct=float(state["vcp_near_pivot_tolerance_pct"]),
            vcp_max_consolidation_depth_pct=float(state["vcp_max_consolidation_depth_pct"]),
        )

    def to_engine_kwargs(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HomepageRangeScanRequest:
    start_num: int
    end_num: int
    trade_date: date | None = None
    range_lookback_days: int = 60
    range_max_width_pct: float = 65.0
    range_volume_ratio: float = 1.3
    range_min_price_gain_pct: float = 0.0
    range_max_price_gain_pct: float = 18.0
    range_volume_sustain_days: int = 3

    @classmethod
    def from_sidebar_state(cls, state: dict[str, Any]) -> "HomepageRangeScanRequest":
        return cls(
            start_num=int(state["start_num"]),
            end_num=int(state["end_num"]),
            trade_date=state.get("home_trade_date"),
            range_lookback_days=int(state["range_lookback_days"]),
            range_max_width_pct=float(state["range_max_width_pct"]),
            range_volume_ratio=float(state["range_volume_ratio"]),
            range_min_price_gain_pct=float(state["range_min_price_gain_pct"]),
            range_max_price_gain_pct=float(state["range_max_price_gain_pct"]),
            range_volume_sustain_days=int(state["range_volume_sustain_days"]),
        )

    def to_engine_kwargs(self) -> dict[str, Any]:
        return {
            "start_num": self.start_num,
            "end_num": self.end_num,
            "selected_strategies": ["區間量增啟動"],
            "mode": "即時選股",
            "start_date": None,
            "end_date": self.trade_date,
            "selected_sell_strategies": [],
            "range_lookback_days": self.range_lookback_days,
            "range_max_width_pct": self.range_max_width_pct,
            "range_volume_ratio": self.range_volume_ratio,
            "range_min_price_gain_pct": self.range_min_price_gain_pct,
            "range_max_price_gain_pct": self.range_max_price_gain_pct,
            "range_volume_sustain_days": self.range_volume_sustain_days,
        }
