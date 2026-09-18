import pandas as pd
import streamlit as st

from modules.backtest.func import calculate_max_drawdown, calculate_profit_factor


@st.fragment(run_every="2s")
def build_portfolio_summary(results):
    all_trades = [trade for info in results.values() for trade in info["trades"]]
    total_initial_capital = sum(info["initial_capital"] for info in results.values())
    total_ending_capital = sum(info["ending_capital"] for info in results.values())
    total_net_profit = sum(info["net_profit"] for info in results.values())
    winning_trades = sum(1 for trade in all_trades if trade["return_pct"] > 0)
    overall_win_rate = (winning_trades / len(all_trades) * 100) if all_trades else 0.0
    overall_return = ((total_ending_capital / total_initial_capital) - 1) * 100 if total_initial_capital else 0.0

    curve_frames = []
    for code, info in results.items():
        curve_df = pd.DataFrame(info["equity_curve"]).copy()
        curve_df["date"] = pd.to_datetime(curve_df["date"])
        curve_df = curve_df.drop_duplicates(subset="date", keep="last")
        curve_df = curve_df.set_index("date").rename(columns={"capital": code})[[code]]
        curve_frames.append(curve_df)

    total_curve_df = pd.concat(curve_frames, axis=1).sort_index().ffill()
    total_curve_df["總資金"] = total_curve_df.sum(axis=1)
    total_curve_records = [
        {"date": idx.strftime("%Y-%m-%d"), "capital": value}
        for idx, value in total_curve_df["總資金"].items()
    ]
    rs_values = [
        trade["buy_rs_spread_pct"]
        for trade in all_trades
        if trade.get("buy_rs_spread_pct") is not None
    ]

    return {
        "total_stocks": len(results),
        "total_trades": len(all_trades),
        "winning_trades": winning_trades,
        "overall_win_rate": overall_win_rate,
        "total_initial_capital": total_initial_capital,
        "total_ending_capital": total_ending_capital,
        "total_net_profit": total_net_profit,
        "overall_return": overall_return,
        "avg_trade_return": (
            sum(trade["return_pct"] for trade in all_trades) / len(all_trades)
            if all_trades else 0.0
        ),
        "avg_buy_rs_spread": (sum(rs_values) / len(rs_values)) if rs_values else None,
        "profit_factor": calculate_profit_factor(all_trades),
        "max_drawdown": calculate_max_drawdown(total_curve_records),
        "total_curve_df": total_curve_df[["總資金"]],
    }
