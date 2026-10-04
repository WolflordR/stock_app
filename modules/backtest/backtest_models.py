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
    pullback_strong_lookback_days: int = 20
    pullback_min_pullback_pct: float = 10.0
    pullback_base_hold_days: int = 3
    pullback_low_price_volume_price_threshold: float = 500.0
    pullback_low_price_min_volume_lots: float = 700.0
    pullback_technology_only: bool = True
    high_price_pullback_lookback_days: int = 20
    high_price_pullback_market_cap_rank_limit: int = 50
    high_price_pullback_min_drop_pct: float = 15.0
    breakout_lookback_days: int = 252
    breakout_distance_pct: float = 10.0
    breakout_trend_lookback_days: int = 20
    breakout_volume_short_window: int = 5
    breakout_volume_long_window: int = 20
    bowl_volume_lookback_days: int = 120
    bowl_volume_min_drawdown_pct: float = 20.0
    bowl_volume_volume_lookback_days: int = 20
    bowl_volume_signal_window_days: int = 3
    bowl_volume_multiplier: float = 2.0
    bowl_volume_trend_lookback_days: int = 10
    momentum_volume_ma_short: int = 5
    momentum_volume_ma_long: int = 10
    momentum_volume_momentum_lookback: int = 5
    momentum_volume_ma_slope_lookback: int = 3
    momentum_volume_volume_ma_period: int = 20
    momentum_volume_volume_multiplier: float = 2.0
    momentum_volume_volume_lookback: int = 3

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
            pullback_strong_lookback_days=int(state["pullback_strong_lookback_days"]),
            pullback_min_pullback_pct=float(state["pullback_min_pullback_pct"]),
            pullback_base_hold_days=int(state["pullback_base_hold_days"]),
            pullback_low_price_volume_price_threshold=float(state["pullback_low_price_volume_price_threshold"]),
            pullback_low_price_min_volume_lots=float(state["pullback_low_price_min_volume_lots"]),
            pullback_technology_only=bool(state["pullback_technology_only"]),
            high_price_pullback_lookback_days=int(state["high_price_pullback_lookback_days"]),
            high_price_pullback_market_cap_rank_limit=int(state["high_price_pullback_market_cap_rank_limit"]),
            high_price_pullback_min_drop_pct=float(state["high_price_pullback_min_drop_pct"]),
            breakout_lookback_days=int(state.get("breakout_lookback_days", 252)),
            breakout_distance_pct=float(state.get("breakout_distance_pct", 10.0)),
            breakout_trend_lookback_days=int(state.get("breakout_trend_lookback_days", 20)),
            breakout_volume_short_window=int(state.get("breakout_volume_short_window", 5)),
            breakout_volume_long_window=int(state.get("breakout_volume_long_window", 20)),
            bowl_volume_lookback_days=int(state.get("bowl_volume_lookback_days", 120)),
            bowl_volume_min_drawdown_pct=float(state.get("bowl_volume_min_drawdown_pct", 20.0)),
            bowl_volume_volume_lookback_days=int(state.get("bowl_volume_volume_lookback_days", 20)),
            bowl_volume_signal_window_days=int(state.get("bowl_volume_signal_window_days", 3)),
            bowl_volume_multiplier=float(state.get("bowl_volume_multiplier", 2.0)),
            bowl_volume_trend_lookback_days=int(state.get("bowl_volume_trend_lookback_days", 10)),
            momentum_volume_ma_short=int(state.get("momentum_volume_ma_short", 5)),
            momentum_volume_ma_long=int(state.get("momentum_volume_ma_long", 10)),
            momentum_volume_momentum_lookback=int(state.get("momentum_volume_momentum_lookback", 5)),
            momentum_volume_ma_slope_lookback=int(state.get("momentum_volume_ma_slope_lookback", 3)),
            momentum_volume_volume_ma_period=int(state.get("momentum_volume_volume_ma_period", 20)),
            momentum_volume_volume_multiplier=float(state.get("momentum_volume_volume_multiplier", 2.0)),
            momentum_volume_volume_lookback=int(state.get("momentum_volume_volume_lookback", 3)),
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
