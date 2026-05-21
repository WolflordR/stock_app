import pandas as pd


def build_equity_curve(trades, initial_capital, start_date):
    current_capital = float(initial_capital)
    curve = [{
        "date": pd.to_datetime(start_date).strftime("%Y-%m-%d"),
        "capital": round(current_capital, 2),
    }]

    for trade in trades:
        capital_before = current_capital
        profit_loss = capital_before * (trade["return_pct"] / 100)
        current_capital = capital_before + profit_loss
        trade["capital_before"] = round(capital_before, 2)
        trade["profit_loss"] = round(profit_loss, 2)
        trade["capital_after"] = round(current_capital, 2)
        curve.append({
            "date": trade["sell_date"],
            "capital": round(current_capital, 2),
        })

    return curve, round(current_capital, 2)


def calculate_max_drawdown(curve):
    if not curve:
        return 0.0
    capital_series = pd.Series([point["capital"] for point in curve], dtype="float64")
    running_peak = capital_series.cummax()
    drawdown = (capital_series / running_peak) - 1
    return abs(float(drawdown.min())) * 100


def calculate_profit_factor(trades):
    gross_profit = sum(max(trade["profit_loss"], 0) for trade in trades)
    gross_loss = abs(sum(min(trade["profit_loss"], 0) for trade in trades))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def build_performance_summary(trades, equity_curve):
    if not trades:
        return {
            "avg_trade_return": 0.0,
            "avg_profit_loss": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
        }

    avg_trade_return = sum(trade["return_pct"] for trade in trades) / len(trades)
    avg_profit_loss = sum(trade["profit_loss"] for trade in trades) / len(trades)
    profit_factor = calculate_profit_factor(trades)
    return {
        "avg_trade_return": avg_trade_return,
        "avg_profit_loss": avg_profit_loss,
        "profit_factor": profit_factor,
        "max_drawdown": calculate_max_drawdown(equity_curve),
    }
