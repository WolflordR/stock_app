from modules.backtest.bowl_scoring import analyze_bowl_bottom_candidate, strategy_range_volume_accumulation
from modules.backtest.signals.basic import (
    calculate_relative_strength_spread,
    strategy_break_support,
    strategy_breakout_with_volume,
    strategy_death_cross,
    strategy_golden_cross,
    strategy_ma_up,
    strategy_minervini_template,
    strategy_monthly_dip,
    strategy_red_k,
    strategy_relative_strength_filter,
    strategy_touch_monthly_ma,
    strategy_uptrend_filter,
    strategy_volume_surge,
)
from modules.backtest.signals.gap import strategy_gap_support_rebound
from modules.backtest.signals.pullback import (
    analyze_high_price_pullback_candidate,
    analyze_strong_pullback_rebound_candidate,
    strategy_high_price_pullback,
    strategy_strong_pullback_rebound,
)
from modules.backtest.signals.registry import evaluate_registered_buy_strategies, get_buy_strategy_history_buffer_days
from modules.backtest.signals.sell_registry import evaluate_registered_sell_strategies, get_sell_strategy_history_buffer_days
from modules.backtest.signals.technical_patterns import (
    analyze_bowl_bottom_volume_candidate,
    analyze_near_breakout_candidate,
    strategy_bowl_bottom_volume,
    strategy_near_breakout,
)
from modules.backtest.signals.vcp import analyze_vcp_candidate, strategy_vcp_breakout
from modules.backtest.signals.w_bottom import strategy_w_bottom_rebound


def evaluate_sell_signal(current_slice, current_row, selected_sell_strategies, *, position, **params):
    return evaluate_registered_sell_strategies(
        current_slice,
        current_row,
        selected_sell_strategies,
        position=position,
        params=params,
    )


def evaluate_buy_signal(
    df,
    selected_strategies,
    benchmark_df=None,
    **params,
):
    return evaluate_registered_buy_strategies(
        df,
        selected_strategies,
        benchmark_df=benchmark_df,
        params=params,
    )


def get_history_buffer_days(selected_strategies, selected_sell_strategies=None, rs_lookback_days=60):
    buy_buffer_days = get_buy_strategy_history_buffer_days(
        selected_strategies,
        selected_sell_strategies=selected_sell_strategies,
        rs_lookback_days=rs_lookback_days,
    )
    sell_buffer_days = get_sell_strategy_history_buffer_days(selected_sell_strategies)
    return max(buy_buffer_days, sell_buffer_days)
