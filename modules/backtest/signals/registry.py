from __future__ import annotations

from modules.backtest.bowl_scoring import analyze_bowl_bottom_candidate
from modules.backtest.signals.basic import (
    strategy_breakout_with_volume,
    strategy_golden_cross,
    strategy_ma_up,
    strategy_minervini_template,
    strategy_monthly_dip,
    strategy_relative_strength_filter,
    strategy_touch_monthly_ma,
    strategy_uptrend_filter,
    strategy_volume_surge,
)
from modules.backtest.signals.gap import strategy_gap_support_rebound
from modules.backtest.signals.pullback import (
    analyze_high_price_pullback_candidate,
    analyze_strong_pullback_rebound_candidate,
)
from modules.backtest.signals.technical_patterns import (
    analyze_bowl_bottom_volume_candidate,
    analyze_near_breakout_candidate,
)
from modules.backtest.signals.vcp import analyze_vcp_candidate
from modules.backtest.signals.w_bottom import strategy_w_bottom_rebound


def _param(params, name, default=None):
    if isinstance(params, dict):
        return params.get(name, default)
    return getattr(params, name, default)


def _evaluate_range_volume(df, _benchmark_df, params):
    analysis = analyze_bowl_bottom_candidate(
        df,
        lookback_days=_param(params, "range_lookback_days", 60),
        max_range_width_pct=_param(params, "range_max_width_pct", 35.0),
        min_volume_increase_ratio=_param(params, "range_volume_ratio", 1.3),
        min_price_gain_pct=_param(params, "range_min_price_gain_pct", 0.0),
        max_price_gain_pct=_param(params, "range_max_price_gain_pct", 18.0),
        min_sustain_days=_param(params, "range_volume_sustain_days", 3),
    )
    matched = analysis is not None and analysis["score"] >= 52
    if not analysis:
        return False, {}
    return matched, {
        "bowl_score": analysis.get("score"),
        "bowl_grade": analysis.get("grade"),
        "bowl_depth_pct": analysis.get("base_depth_pct"),
        "sustain_days": analysis.get("sustain_days"),
        "peak_distance_pct": analysis.get("peak_distance_pct"),
        "range_position_pct": analysis.get("range_position_pct"),
        "breakout_pct": analysis.get("breakout_pct"),
        "positive_reasons": analysis.get("positive_reasons") or [],
        "caution_reasons": analysis.get("caution_reasons") or [],
        "avg_volume_3": analysis.get("avg_volume_3"),
        "avg_volume_prev3": analysis.get("avg_volume_prev3"),
        "avg_volume_20": analysis.get("avg_volume_20"),
        "current_volume_ratio": analysis.get("current_volume_ratio"),
        "recent3_volume_ratio": analysis.get("recent3_volume_ratio"),
        "avg5_volume_ratio": analysis.get("avg5_volume_ratio"),
        "recovery_from_bottom_pct": analysis.get("recovery_from_bottom_pct"),
    }


def _evaluate_gap(df, _benchmark_df, params):
    setup = strategy_gap_support_rebound(
        df,
        _param(params, "gap_channel_lookback_days", 20),
        _param(params, "gap_channel_max_width_pct", 18.0),
        _param(params, "gap_lookback_days", 10),
        _param(params, "gap_min_gap_pct", 0.5),
        _param(params, "gap_hold_tolerance_pct", 1.0),
        _param(params, "gap_lower_shadow_lookback_days", 5),
        _param(params, "gap_lower_shadow_ratio", 0.4),
        _param(params, "gap_stop_buffer_pct", 1.0),
    )
    return setup is not None, setup or {}


def _evaluate_vcp(df, _benchmark_df, params):
    setup = analyze_vcp_candidate(
        df,
        _param(params, "vcp_lookback_days", 80),
        _param(params, "vcp_min_uptrend_pct", 30.0),
        _param(params, "vcp_breakout_volume_ratio", 1.5),
        _param(params, "vcp_near_pivot_tolerance_pct", 3.0),
        _param(params, "vcp_max_consolidation_depth_pct", 25.0),
    )
    if not setup:
        return False, {}
    return bool(setup.get("matched", False)), {
        "vcp_score": setup.get("score"),
        "vcp_prior_uptrend_pct": setup.get("prior_uptrend_pct"),
        "vcp_consolidation_depth_pct": setup.get("consolidation_depth_pct"),
        "vcp_near_pivot_pct": setup.get("near_pivot_pct"),
        "vcp_distribution_days": setup.get("distribution_days"),
        "vcp_breakout_confirmed": setup.get("breakout_confirmed"),
        "vcp_positive_reasons": setup.get("positive_reasons") or [],
        "vcp_caution_reasons": setup.get("caution_reasons") or [],
        "vcp_pivot_high": setup.get("pivot_high"),
    }


def _evaluate_pullback_guard(df, _benchmark_df, params):
    setup = analyze_strong_pullback_rebound_candidate(
        df,
        strong_lookback_days=_param(params, "pullback_strong_lookback_days", 20),
        min_pullback_pct=_param(params, "pullback_min_pullback_pct", 10.0),
        base_hold_days=_param(params, "pullback_base_hold_days", 3),
        low_price_volume_price_threshold=_param(params, "pullback_low_price_volume_price_threshold", 500.0),
        low_price_min_volume_lots=_param(params, "pullback_low_price_min_volume_lots", 700.0),
    )
    if not setup:
        return False, {}
    return bool(setup.get("matched", False)), {
        "pullback_score": setup.get("score"),
        "pullback_depth_pct": setup.get("pullback_depth_pct"),
        "pullback_reference_high": setup.get("recent_high_reference"),
        "pullback_guard_low": setup.get("first_day_low"),
        "pullback_prior_close": setup.get("prior_close"),
        "pullback_latest_close": setup.get("latest_close"),
        "pullback_base_hold_days": setup.get("base_hold_days"),
        "pullback_latest_volume_lots": setup.get("latest_volume_lots"),
        "pullback_low_price_volume_price_threshold": setup.get("low_price_volume_price_threshold"),
        "pullback_low_price_min_volume_lots": setup.get("low_price_min_volume_lots"),
        "pullback_positive_reasons": setup.get("positive_reasons") or [],
        "pullback_caution_reasons": setup.get("caution_reasons") or [],
        "pullback_condition_a": setup.get("condition_a"),
        "pullback_condition_b": setup.get("condition_b"),
        "pullback_condition_c": setup.get("condition_c"),
    }


def _evaluate_high_price_pullback(df, _benchmark_df, params):
    setup = analyze_high_price_pullback_candidate(
        df,
        lookback_days=_param(params, "high_price_pullback_lookback_days", 20),
        eligible_symbol_set=_param(params, "high_price_pullback_eligible_symbol_set", set()),
        stock_id=_param(params, "stock_id"),
        market_cap_rank_limit=_param(params, "high_price_pullback_market_cap_rank_limit", 50),
        min_drop_pct=_param(params, "high_price_pullback_min_drop_pct", 15.0),
    )
    if not setup:
        return False, {}
    return bool(setup.get("matched", False)), {
        "high_price_pullback_score": setup.get("score"),
        "high_price_pullback_depth_pct": setup.get("pullback_depth_pct"),
        "high_price_pullback_reference_high": setup.get("recent_high_reference"),
        "high_price_pullback_latest_close": setup.get("latest_close"),
        "high_price_pullback_lookback_days": setup.get("lookback_days"),
        "high_price_pullback_market_cap_rank_limit": setup.get("market_cap_rank_limit"),
        "high_price_pullback_min_drop_pct": setup.get("min_drop_pct"),
        "high_price_pullback_positive_reasons": setup.get("positive_reasons") or [],
        "high_price_pullback_caution_reasons": setup.get("caution_reasons") or [],
        "high_price_pullback_condition_a": setup.get("condition_a"),
        "high_price_pullback_condition_b": setup.get("condition_b"),
    }


def _evaluate_near_breakout(df, _benchmark_df, params):
    setup = analyze_near_breakout_candidate(
        df,
        lookback_days=_param(params, "breakout_lookback_days", 252),
        max_distance=float(_param(params, "breakout_distance_pct", 10.0)) / 100.0,
        trend_lookback_days=_param(params, "breakout_trend_lookback_days", 20),
        volume_short_window=_param(params, "breakout_volume_short_window", 5),
        volume_long_window=_param(params, "breakout_volume_long_window", 20),
    )
    if not setup:
        return False, {}
    return bool(setup.get("matched", False)), {
        "near_breakout_score": setup.get("score"),
        "near_breakout_latest_close": setup.get("latest_close"),
        "near_breakout_high_price": setup.get("high_price"),
        "near_breakout_high_date": setup.get("high_date"),
        "near_breakout_distance_pct": setup.get("distance_to_high_pct"),
        "near_breakout_latest_volume": setup.get("latest_volume"),
        "near_breakout_avg_volume_short": setup.get("avg_volume_short"),
        "near_breakout_avg_volume_long": setup.get("avg_volume_long"),
        "near_breakout_volume_ratio": setup.get("volume_ratio"),
        "near_breakout_latest_volume_ratio": setup.get("latest_volume_ratio"),
        "near_breakout_price_trend_pct": setup.get("price_trend_pct"),
        "near_breakout_positive_reasons": setup.get("positive_reasons") or [],
        "near_breakout_caution_reasons": setup.get("caution_reasons") or [],
    }


def _evaluate_bowl_bottom_volume(df, _benchmark_df, params):
    setup = analyze_bowl_bottom_volume_candidate(
        df,
        lookback_days=_param(params, "bowl_volume_lookback_days", 120),
        min_drawdown=float(_param(params, "bowl_volume_min_drawdown_pct", 20.0)) / 100.0,
        volume_lookback_days=_param(params, "bowl_volume_volume_lookback_days", 20),
        volume_signal_window_days=_param(params, "bowl_volume_signal_window_days", 3),
        volume_multiplier=_param(params, "bowl_volume_multiplier", 2.0),
        trend_lookback_days=_param(params, "bowl_volume_trend_lookback_days", 10),
    )
    if not setup:
        return False, {}
    return bool(setup.get("matched", False)), {
        "bowl_volume_score": setup.get("score"),
        "bowl_volume_half_year_high": setup.get("half_year_high"),
        "bowl_volume_half_year_high_date": setup.get("half_year_high_date"),
        "bowl_volume_subsequent_low": setup.get("subsequent_low"),
        "bowl_volume_subsequent_low_date": setup.get("subsequent_low_date"),
        "bowl_volume_drawdown_pct": setup.get("drawdown_pct"),
        "bowl_volume_latest_close": setup.get("latest_close"),
        "bowl_volume_recovery_from_bottom_pct": setup.get("recovery_from_bottom_pct"),
        "bowl_volume_avg_volume_short": setup.get("avg_volume_short"),
        "bowl_volume_avg_volume_long": setup.get("avg_volume_long"),
        "bowl_volume_volume_ratio": setup.get("volume_ratio"),
        "bowl_volume_volume_lookback_days": setup.get("volume_lookback_days"),
        "bowl_volume_signal_window_days": setup.get("volume_signal_window_days"),
        "bowl_volume_multiplier": setup.get("volume_multiplier"),
        "bowl_volume_signal_date": setup.get("volume_signal_date"),
        "bowl_volume_signal_volume": setup.get("volume_signal_volume"),
        "bowl_volume_signal_avg_volume_20d": setup.get("volume_signal_avg_volume_20d"),
        "bowl_volume_signal_ratio": setup.get("volume_signal_ratio"),
        "bowl_volume_signal_price_change_pct": setup.get("volume_signal_price_change_pct"),
        "bowl_volume_days_since_volume_signal": setup.get("days_since_volume_signal"),
        "bowl_volume_up_down_volume_ratio": setup.get("up_down_volume_ratio"),
        "bowl_volume_recent_trend_pct": setup.get("recent_trend_pct"),
        "bowl_volume_ma20_slope_pct": setup.get("ma20_slope_pct"),
        "bowl_volume_bottom_days": setup.get("bottom_days"),
        "bowl_volume_bottom_span_days": setup.get("bottom_span_days"),
        "bowl_volume_positive_reasons": setup.get("positive_reasons") or [],
        "bowl_volume_caution_reasons": setup.get("caution_reasons") or [],
    }


def _evaluate_relative_strength(df, benchmark_df, params):
    matched, rs_spread_pct = strategy_relative_strength_filter(
        df,
        benchmark_df,
        _param(params, "rs_lookback_days", 60),
        _param(params, "rs_min_outperformance_pct", 5.0),
    )
    return matched, {"rs_spread_pct": rs_spread_pct} if rs_spread_pct is not None else {}


def _evaluate_w_bottom(df, _benchmark_df, params):
    setup = strategy_w_bottom_rebound(
        df,
        _param(params, "w_bottom_lookback_days", 40),
        _param(params, "w_bottom_tolerance_pct", 3.0),
        _param(params, "w_bottom_min_rebound_pct", 5.0),
        _param(params, "w_bottom_lower_shadow_ratio", 0.4),
        _param(params, "w_bottom_stop_buffer_pct", 1.5),
    )
    return setup is not None, setup or {}


BUY_STRATEGY_REGISTRY = {
    "月高回檔策略": lambda df, benchmark_df, params: (strategy_monthly_dip(df), {}),
    "爆量策略": lambda df, benchmark_df, params: (strategy_volume_surge(df), {}),
    "均線策略": lambda df, benchmark_df, params: (strategy_ma_up(df), {}),
    "跌到月線買入": lambda df, benchmark_df, params: (strategy_touch_monthly_ma(df), {}),
    "黃金交叉策略": lambda df, benchmark_df, params: (strategy_golden_cross(df), {}),
    "突破前高策略": lambda df, benchmark_df, params: (strategy_breakout_with_volume(df), {}),
    "區間量增啟動": _evaluate_range_volume,
    "上升缺口承接": _evaluate_gap,
    "上升趨勢濾網": lambda df, benchmark_df, params: (strategy_uptrend_filter(df), {}),
    "Minervini 趨勢模板": lambda df, benchmark_df, params: (strategy_minervini_template(df), {}),
    "VCP 收斂突破": _evaluate_vcp,
    "強勢股回檔量縮止跌": _evaluate_pullback_guard,
    "高價股回檔": _evaluate_high_price_pullback,
    "接近前高／即將突破": _evaluate_near_breakout,
    "碗形底＋帶量向上": _evaluate_bowl_bottom_volume,
    "相對強弱濾網": _evaluate_relative_strength,
    "W底反彈": _evaluate_w_bottom,
}


def evaluate_registered_buy_strategies(df, selected_strategies, *, benchmark_df=None, params=None):
    check_results = []
    buy_setup = {}

    for strategy_name in selected_strategies:
        handler = BUY_STRATEGY_REGISTRY.get(strategy_name)
        if handler is None:
            continue
        matched, setup = handler(df, benchmark_df, params)
        check_results.append(bool(matched))
        if setup:
            buy_setup.update(setup)

    return bool(check_results) and all(check_results), buy_setup


def get_buy_strategy_history_buffer_days(selected_strategies, selected_sell_strategies=None, rs_lookback_days=60):
    selected_sell_strategies = selected_sell_strategies or []
    history_buffer_days = 120

    if "W底反彈" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 180)
    if "區間量增啟動" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 120)
    if "上升缺口承接" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 160)
    if {"黃金交叉策略", "死亡交叉策略", "上升趨勢濾網"} & set(selected_strategies + selected_sell_strategies):
        history_buffer_days = max(history_buffer_days, 180)
    if "Minervini 趨勢模板" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 450)
    if "VCP 收斂突破" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 320)
    if "強勢股回檔量縮止跌" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 140)
    if "高價股回檔" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 140)
    if "接近前高／即將突破" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 320)
    if "碗形底＋帶量向上" in selected_strategies:
        history_buffer_days = max(history_buffer_days, 220)
    if "相對強弱濾網" in selected_strategies:
        history_buffer_days = max(history_buffer_days, rs_lookback_days + 90)

    return history_buffer_days
