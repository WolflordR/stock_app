from __future__ import annotations

from modules.backtest.signals.basic import strategy_break_support, strategy_death_cross


def _param(params, name, default=None):
    if isinstance(params, dict):
        return params.get(name, default)
    return getattr(params, name, default)


def _sell_w_bottom_stop(_current_slice, current_row, position, params):
    stop_price = position.get("active_setup", {}).get("stop_price")
    if stop_price and current_row["Low"] <= stop_price:
        stop_buffer_pct = _param(params, "w_bottom_stop_buffer_pct", 1.5)
        return True, stop_price, f"W底結構停損(-{stop_buffer_pct:.1f}%)"
    return False, 0.0, ""


def _sell_gap_stop(_current_slice, current_row, position, params):
    gap_stop_price = position.get("active_setup", {}).get("gap_stop_price")
    if gap_stop_price and current_row["Low"] <= gap_stop_price:
        gap_stop_buffer_pct = _param(params, "gap_stop_buffer_pct", 1.0)
        return True, gap_stop_price, f"缺口支撐停損(-{gap_stop_buffer_pct:.1f}%)"
    return False, 0.0, ""


def _sell_w_bottom_target(_current_slice, current_row, position, _params):
    target_price = position.get("active_setup", {}).get("target_price")
    if target_price and current_row["High"] >= target_price:
        return True, target_price, "W底目標到價"
    return False, 0.0, ""


def _sell_initial_stop(_current_slice, current_row, position, params):
    buy_price = position["buy_price"]
    initial_stop_loss_pct = _param(params, "initial_stop_loss_pct", 5.0)
    initial_stop_price = buy_price * (1 - initial_stop_loss_pct / 100)
    if current_row["Low"] <= initial_stop_price:
        return True, initial_stop_price, f"初始停損(-{initial_stop_loss_pct:.1f}%)"
    return False, 0.0, ""


def _sell_trailing_stop(_current_slice, current_row, position, params):
    buy_price = position["buy_price"]
    max_high = position["max_high"]
    trailing_stop_activation_pct = _param(params, "trailing_stop_activation_pct", 8.0)
    trailing_stop_drawdown_pct = _param(params, "trailing_stop_drawdown_pct", 8.0)
    curr_profit_pct = (max_high - buy_price) / buy_price * 100
    stop_loss_price = max_high * (1 - trailing_stop_drawdown_pct / 100)
    if curr_profit_pct >= trailing_stop_activation_pct and current_row["Close"] <= stop_loss_price:
        return (
            True,
            current_row["Close"],
            f"移動停損(獲利達{trailing_stop_activation_pct:.1f}%後，收盤跌破高點回撤{trailing_stop_drawdown_pct:.1f}%)",
        )
    return False, 0.0, ""


def _sell_fixed_tp_sl(_current_slice, current_row, position, _params):
    buy_price = position["buy_price"]
    if current_row["High"] >= buy_price * 1.10:
        return True, buy_price * 1.10, "固定停利(+10%)"
    if current_row["Low"] <= buy_price * 0.95:
        return True, buy_price * 0.95, "固定停損(-5%)"
    return False, 0.0, ""


def _sell_break_ma5(current_slice, current_row, _position, _params):
    ma5 = current_slice["Close"].rolling(window=5).mean().iloc[-1]
    if current_row["Close"] < ma5:
        return True, current_row["Close"], "跌破 5MA"
    return False, 0.0, ""


def _sell_death_cross(current_slice, current_row, _position, _params):
    if strategy_death_cross(current_slice):
        return True, current_row["Close"], "死亡交叉"
    return False, 0.0, ""


def _sell_break_support(current_slice, current_row, _position, _params):
    if strategy_break_support(current_slice, lookback_days=10):
        return True, current_row["Close"], "跌破近10日支撐"
    return False, 0.0, ""


def _sell_hold_5_days(_current_slice, current_row, position, _params):
    if position["days_held"] >= 5:
        return True, current_row["Close"], "天數到期"
    return False, 0.0, ""


SELL_STRATEGY_REGISTRY = {
    "W底結構停損": _sell_w_bottom_stop,
    "缺口支撐停損": _sell_gap_stop,
    "W底目標到價": _sell_w_bottom_target,
    "初始停損": _sell_initial_stop,
    "移動式停損": _sell_trailing_stop,
    "停利 10% / 停損 5%": _sell_fixed_tp_sl,
    "跌破 5 日均線": _sell_break_ma5,
    "死亡交叉策略": _sell_death_cross,
    "跌破近10日支撐": _sell_break_support,
    "持有 5 個交易日": _sell_hold_5_days,
}


def evaluate_registered_sell_strategies(current_slice, current_row, selected_sell_strategies, *, position, params=None):
    for strategy_name in (selected_sell_strategies or []):
        handler = SELL_STRATEGY_REGISTRY.get(strategy_name)
        if handler is None:
            continue
        sold, sell_price, sell_reason = handler(current_slice, current_row, position, params)
        if sold:
            return True, float(sell_price), str(sell_reason)
    return False, 0.0, ""


def get_sell_strategy_history_buffer_days(selected_sell_strategies=None):
    selected_sell_strategies = selected_sell_strategies or []
    history_buffer_days = 120

    if {"死亡交叉策略", "跌破 5 日均線"} & set(selected_sell_strategies):
        history_buffer_days = max(history_buffer_days, 180)

    return history_buffer_days
