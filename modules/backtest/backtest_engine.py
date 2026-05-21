import time

from modules.backtest.bowl_scoring import analyze_bowl_bottom_candidate
from modules.backtest.performance_metrics import build_equity_curve, build_performance_summary
from modules.data_sources.price_cache import fetch_price_history
from modules.data_sources.stock_db import ensure_stock_db, get_securities_in_range, get_stock_name
from modules.backtest.strategy_signals import (
    analyze_vcp_candidate,
    calculate_relative_strength_spread,
    evaluate_buy_signal,
    get_history_buffer_days,
    strategy_break_support,
    strategy_death_cross,
)


def get_chinese_name(stock_id):
    return get_stock_name(stock_id)


def check_stock(
    stock_id,
    selected_strategies,
    mode="即時選股",
    start_date=None,
    end_date=None,
    selected_sell_strategies=None,
    benchmark_df=None,
    range_lookback_days=60,
    range_max_width_pct=35.0,
    range_volume_ratio=1.3,
    range_min_price_gain_pct=0.0,
    range_max_price_gain_pct=18.0,
    range_volume_sustain_days=3,
    initial_capital=100000,
    trading_cost_pct=0.7,
    initial_stop_loss_pct=5.0,
    w_bottom_lookback_days=40,
    w_bottom_tolerance_pct=3.0,
    w_bottom_min_rebound_pct=5.0,
    w_bottom_lower_shadow_ratio=0.4,
    w_bottom_stop_buffer_pct=1.5,
    gap_channel_lookback_days=20,
    gap_channel_max_width_pct=18.0,
    gap_lookback_days=10,
    gap_min_gap_pct=0.5,
    gap_hold_tolerance_pct=1.0,
    gap_lower_shadow_lookback_days=5,
    gap_lower_shadow_ratio=0.4,
    gap_stop_buffer_pct=1.0,
    trailing_stop_activation_pct=8.0,
    trailing_stop_drawdown_pct=8.0,
    rs_lookback_days=60,
    rs_min_outperformance_pct=5.0,
    vcp_lookback_days=80,
    vcp_min_uptrend_pct=30.0,
    vcp_breakout_volume_ratio=1.5,
    vcp_near_pivot_tolerance_pct=3.0,
    vcp_max_consolidation_depth_pct=25.0,
    history_buffer_days=120,
):
    try:
        selected_sell_strategies = selected_sell_strategies or []
        df = fetch_price_history(
            stock_id,
            mode,
            start_date,
            end_date,
            history_buffer_days=history_buffer_days,
        )
        if df.empty or len(df) < 20:
            return None
        df = df.sort_index()
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)

        if mode == "歷史回測":
            trades = []
            in_position = False
            buy_price = 0
            buy_date = None
            days_held = 0
            max_high = 0
            active_setup = {}

            target_start_dt = df.index.searchsorted(start_date)
            if target_start_dt >= len(df):
                return None

            for i in range(target_start_dt, len(df)):
                current_date = df.index[i].strftime("%Y-%m-%d")
                current_slice = df.iloc[: i + 1]
                current_row = df.iloc[i]

                if not in_position:
                    matched, buy_setup = evaluate_buy_signal(
                        current_slice,
                        selected_strategies,
                        benchmark_df.loc[: current_slice.index[-1]] if benchmark_df is not None else None,
                        range_lookback_days,
                        range_max_width_pct,
                        range_volume_ratio,
                        range_min_price_gain_pct,
                        range_max_price_gain_pct,
                        range_volume_sustain_days,
                        w_bottom_lookback_days,
                        w_bottom_tolerance_pct,
                        w_bottom_min_rebound_pct,
                        w_bottom_lower_shadow_ratio,
                        w_bottom_stop_buffer_pct,
                        gap_channel_lookback_days,
                        gap_channel_max_width_pct,
                        gap_lookback_days,
                        gap_min_gap_pct,
                        gap_hold_tolerance_pct,
                        gap_lower_shadow_lookback_days,
                        gap_lower_shadow_ratio,
                        gap_stop_buffer_pct,
                        rs_lookback_days,
                        rs_min_outperformance_pct,
                        vcp_lookback_days,
                        vcp_min_uptrend_pct,
                        vcp_breakout_volume_ratio,
                        vcp_near_pivot_tolerance_pct,
                        vcp_max_consolidation_depth_pct,
                    )
                    if matched:
                        in_position = True
                        buy_price = current_row["Close"]
                        buy_date = current_date
                        days_held = 0
                        max_high = current_row["High"]
                        active_setup = buy_setup.copy()
                else:
                    days_held += 1
                    if current_row["High"] > max_high:
                        max_high = current_row["High"]

                    sell_price = 0
                    sell_reason = ""
                    sold = False

                    if not sold and "W底結構停損" in selected_sell_strategies and active_setup.get("stop_price"):
                        if current_row["Low"] <= active_setup["stop_price"]:
                            sell_price = active_setup["stop_price"]
                            sell_reason = f"W底結構停損(-{w_bottom_stop_buffer_pct:.1f}%)"
                            sold = True

                    if not sold and "缺口支撐停損" in selected_sell_strategies and active_setup.get("gap_stop_price"):
                        if current_row["Low"] <= active_setup["gap_stop_price"]:
                            sell_price = active_setup["gap_stop_price"]
                            sell_reason = f"缺口支撐停損(-{gap_stop_buffer_pct:.1f}%)"
                            sold = True

                    if not sold and "W底目標到價" in selected_sell_strategies and active_setup.get("target_price"):
                        if current_row["High"] >= active_setup["target_price"]:
                            sell_price = active_setup["target_price"]
                            sell_reason = "W底目標到價"
                            sold = True

                    if not sold and "初始停損" in selected_sell_strategies:
                        initial_stop_price = buy_price * (1 - initial_stop_loss_pct / 100)
                        if current_row["Low"] <= initial_stop_price:
                            sell_price = initial_stop_price
                            sell_reason = f"初始停損(-{initial_stop_loss_pct:.1f}%)"
                            sold = True

                    if not sold and "移動式停損" in selected_sell_strategies:
                        curr_profit_pct = (max_high - buy_price) / buy_price * 100
                        stop_loss_price = max_high * (1 - trailing_stop_drawdown_pct / 100)
                        if curr_profit_pct >= trailing_stop_activation_pct and current_row["Close"] <= stop_loss_price:
                            sell_price = current_row["Close"]
                            sell_reason = (
                                f"移動停損(獲利達{trailing_stop_activation_pct:.1f}%後，"
                                f"收盤跌破高點回撤{trailing_stop_drawdown_pct:.1f}%)"
                            )
                            sold = True

                    if not sold and "停利 10% / 停損 5%" in selected_sell_strategies:
                        if current_row["High"] >= buy_price * 1.10:
                            sell_price = buy_price * 1.10
                            sell_reason = "固定停利(+10%)"
                            sold = True
                        elif current_row["Low"] <= buy_price * 0.95:
                            sell_price = buy_price * 0.95
                            sell_reason = "固定停損(-5%)"
                            sold = True

                    if not sold and "跌破 5 日均線" in selected_sell_strategies:
                        ma5 = current_slice["Close"].rolling(window=5).mean().iloc[-1]
                        if current_row["Close"] < ma5:
                            sell_price = current_row["Close"]
                            sell_reason = "跌破 5MA"
                            sold = True

                    if not sold and "死亡交叉策略" in selected_sell_strategies and strategy_death_cross(current_slice):
                        sell_price = current_row["Close"]
                        sell_reason = "死亡交叉"
                        sold = True

                    if not sold and "跌破近10日支撐" in selected_sell_strategies and strategy_break_support(current_slice, lookback_days=10):
                        sell_price = current_row["Close"]
                        sell_reason = "跌破近10日支撐"
                        sold = True

                    if not sold and "持有 5 個交易日" in selected_sell_strategies and days_held >= 5:
                        sell_price = current_row["Close"]
                        sell_reason = "天數到期"
                        sold = True

                    if sold:
                        gross_return_pct = (sell_price - buy_price) / buy_price * 100
                        net_return_pct = gross_return_pct - trading_cost_pct
                        trades.append(
                            {
                                "buy_date": buy_date,
                                "buy_price": buy_price,
                                "sell_date": current_date,
                                "sell_price": sell_price,
                                "gross_return_pct": gross_return_pct,
                                "cost_pct": trading_cost_pct,
                                "return_pct": net_return_pct,
                                "reason": sell_reason,
                                "buy_rs_spread_pct": active_setup.get("rs_spread_pct"),
                                "w_support_price": active_setup.get("support_price"),
                                "w_stop_price": active_setup.get("stop_price"),
                                "w_target_price": active_setup.get("target_price"),
                                "gap_support_price": active_setup.get("gap_support_price"),
                                "gap_stop_price": active_setup.get("gap_stop_price"),
                                "gap_day": active_setup.get("gap_day"),
                                "gap_shadow_day": active_setup.get("shadow_confirm_day"),
                            }
                        )
                        in_position = False
                        active_setup = {}

            if in_position:
                final_row = df.iloc[-1]
                final_sell_price = final_row["Close"]
                gross_return_pct = (final_sell_price - buy_price) / buy_price * 100
                net_return_pct = gross_return_pct - trading_cost_pct
                trades.append(
                    {
                        "buy_date": buy_date,
                        "buy_price": buy_price,
                        "sell_date": df.index[-1].strftime("%Y-%m-%d"),
                        "sell_price": final_sell_price,
                        "gross_return_pct": gross_return_pct,
                        "cost_pct": trading_cost_pct,
                        "return_pct": net_return_pct,
                        "reason": "回測結束平倉",
                        "buy_rs_spread_pct": active_setup.get("rs_spread_pct"),
                        "w_support_price": active_setup.get("support_price"),
                        "w_stop_price": active_setup.get("stop_price"),
                        "w_target_price": active_setup.get("target_price"),
                        "gap_support_price": active_setup.get("gap_support_price"),
                        "gap_stop_price": active_setup.get("gap_stop_price"),
                        "gap_day": active_setup.get("gap_day"),
                        "gap_shadow_day": active_setup.get("shadow_confirm_day"),
                    }
                )

            if not trades:
                return None

            equity_curve, ending_capital = build_equity_curve(trades, initial_capital, start_date)
            performance_summary = build_performance_summary(trades, equity_curve)
            total_return = ((ending_capital / initial_capital) - 1) * 100
            win_count = len([t for t in trades if t["return_pct"] > 0])
            rs_values = [t["buy_rs_spread_pct"] for t in trades if t.get("buy_rs_spread_pct") is not None]
            return {
                "name": get_chinese_name(stock_id),
                "trades": trades,
                "equity_curve": equity_curve,
                "total_trades": len(trades),
                "win_rate": (win_count / len(trades)) * 100,
                "total_return": total_return,
                "initial_capital": round(float(initial_capital), 2),
                "ending_capital": ending_capital,
                "net_profit": round(ending_capital - float(initial_capital), 2),
                "avg_trade_return": performance_summary["avg_trade_return"],
                "avg_profit_loss": performance_summary["avg_profit_loss"],
                "profit_factor": performance_summary["profit_factor"],
                "max_drawdown": performance_summary["max_drawdown"],
                "avg_buy_rs_spread": sum(rs_values) / len(rs_values) if rs_values else None,
                "trading_cost_pct": trading_cost_pct,
                "initial_stop_loss_pct": initial_stop_loss_pct,
                "w_bottom_lookback_days": w_bottom_lookback_days,
                "w_bottom_tolerance_pct": w_bottom_tolerance_pct,
                "w_bottom_min_rebound_pct": w_bottom_min_rebound_pct,
                "w_bottom_lower_shadow_ratio": w_bottom_lower_shadow_ratio,
                "w_bottom_stop_buffer_pct": w_bottom_stop_buffer_pct,
                "trailing_stop_activation_pct": trailing_stop_activation_pct,
                "trailing_stop_drawdown_pct": trailing_stop_drawdown_pct,
                "rs_lookback_days": rs_lookback_days,
                "rs_min_outperformance_pct": rs_min_outperformance_pct,
            }

        matched, _ = evaluate_buy_signal(
            df,
            selected_strategies,
            benchmark_df,
            range_lookback_days,
            range_max_width_pct,
            range_volume_ratio,
            range_min_price_gain_pct,
            range_max_price_gain_pct,
            range_volume_sustain_days,
            w_bottom_lookback_days,
            w_bottom_tolerance_pct,
            w_bottom_min_rebound_pct,
            w_bottom_lower_shadow_ratio,
            w_bottom_stop_buffer_pct,
            gap_channel_lookback_days,
            gap_channel_max_width_pct,
            gap_lookback_days,
            gap_min_gap_pct,
            gap_hold_tolerance_pct,
            gap_lower_shadow_lookback_days,
            gap_lower_shadow_ratio,
            gap_stop_buffer_pct,
            rs_lookback_days,
            rs_min_outperformance_pct,
            vcp_lookback_days,
            vcp_min_uptrend_pct,
            vcp_breakout_volume_ratio,
            vcp_near_pivot_tolerance_pct,
            vcp_max_consolidation_depth_pct,
        )
        if matched:
            bowl_analysis = None
            vcp_analysis = None
            if "區間量增啟動" in selected_strategies:
                bowl_analysis = analyze_bowl_bottom_candidate(
                    df,
                    lookback_days=range_lookback_days,
                    max_range_width_pct=range_max_width_pct,
                    min_volume_increase_ratio=range_volume_ratio,
                    min_price_gain_pct=range_min_price_gain_pct,
                    max_price_gain_pct=range_max_price_gain_pct,
                    min_sustain_days=range_volume_sustain_days,
                )
            if "VCP 收斂突破" in selected_strategies:
                vcp_analysis = analyze_vcp_candidate(
                    df,
                    lookback_days=vcp_lookback_days,
                    min_uptrend_pct=vcp_min_uptrend_pct,
                    breakout_volume_ratio=vcp_breakout_volume_ratio,
                    near_pivot_tolerance_pct=vcp_near_pivot_tolerance_pct,
                    max_consolidation_depth_pct=vcp_max_consolidation_depth_pct,
                )
            rs_spread_pct = None
            if "相對強弱濾網" in selected_strategies:
                rs_spread_pct = calculate_relative_strength_spread(df, benchmark_df, rs_lookback_days)
            latest_volume = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0.0
            avg_volume_3 = bowl_analysis.get("avg_volume_3") if bowl_analysis else None
            avg_volume_prev3 = bowl_analysis.get("avg_volume_prev3") if bowl_analysis else None
            avg_volume_20 = bowl_analysis.get("avg_volume_20") if bowl_analysis else None
            current_volume_ratio = bowl_analysis.get("current_volume_ratio") if bowl_analysis else None
            recent3_volume_ratio = bowl_analysis.get("recent3_volume_ratio") if bowl_analysis else None
            long_term_volume_ratio = bowl_analysis.get("avg5_volume_ratio") if bowl_analysis else None
            recent_window = df.tail(range_lookback_days)
            bowl_bottom = float(recent_window["Low"].min()) if not recent_window.empty else None
            recovery_from_bottom_pct = ((float(df["Close"].iloc[-1]) / bowl_bottom) - 1) * 100 if bowl_bottom else None
            return {
                "name": get_chinese_name(stock_id),
                "price": round(float(df["Close"].iloc[-1]), 2),
                "rs_spread_pct": rs_spread_pct,
                "latest_volume": round(latest_volume),
                "avg_volume_3": round(avg_volume_3) if avg_volume_3 is not None else None,
                "avg_volume_prev3": round(avg_volume_prev3) if avg_volume_prev3 is not None else None,
                "avg_volume_20": round(avg_volume_20) if avg_volume_20 is not None else None,
                "current_volume_ratio": round(current_volume_ratio, 2) if current_volume_ratio is not None else None,
                "recent3_volume_ratio": round(recent3_volume_ratio, 2) if recent3_volume_ratio is not None else None,
                "avg5_volume_ratio": round(long_term_volume_ratio, 2) if long_term_volume_ratio is not None else None,
                "recovery_from_bottom_pct": round(recovery_from_bottom_pct, 2) if recovery_from_bottom_pct is not None else None,
                "bowl_score": bowl_analysis["score"] if bowl_analysis else None,
                "bowl_grade": bowl_analysis["grade"] if bowl_analysis else None,
                "bowl_depth_pct": bowl_analysis["base_depth_pct"] if bowl_analysis else None,
                "sustain_days": bowl_analysis["sustain_days"] if bowl_analysis else None,
                "peak_distance_pct": bowl_analysis["peak_distance_pct"] if bowl_analysis else None,
                "range_position_pct": bowl_analysis["range_position_pct"] if bowl_analysis else None,
                "breakout_pct": bowl_analysis["breakout_pct"] if bowl_analysis else None,
                "positive_reasons": bowl_analysis["positive_reasons"] if bowl_analysis else [],
                "caution_reasons": bowl_analysis["caution_reasons"] if bowl_analysis else [],
                "vcp_score": vcp_analysis["score"] if vcp_analysis else None,
                "vcp_prior_uptrend_pct": vcp_analysis["prior_uptrend_pct"] if vcp_analysis else None,
                "vcp_consolidation_depth_pct": vcp_analysis["consolidation_depth_pct"] if vcp_analysis else None,
                "vcp_near_pivot_pct": vcp_analysis["near_pivot_pct"] if vcp_analysis else None,
                "vcp_distribution_days": vcp_analysis["distribution_days"] if vcp_analysis else None,
                "vcp_breakout_confirmed": vcp_analysis["breakout_confirmed"] if vcp_analysis else None,
                "vcp_positive_reasons": vcp_analysis["positive_reasons"] if vcp_analysis else [],
                "vcp_caution_reasons": vcp_analysis["caution_reasons"] if vcp_analysis else [],
            }
        return None
    except Exception as exc:
        print(f"Error checking {stock_id}: {exc}")
        return None


def scan_market(
    start_num,
    end_num,
    selected_strategies,
    mode="即時選股",
    start_date=None,
    end_date=None,
    selected_sell_strategies=None,
    progress_bar=None,
    status_text=None,
    range_lookback_days=60,
    range_max_width_pct=35.0,
    range_volume_ratio=1.3,
    range_min_price_gain_pct=0.0,
    range_max_price_gain_pct=18.0,
    range_volume_sustain_days=3,
    initial_capital=100000,
    trading_cost_pct=0.7,
    initial_stop_loss_pct=5.0,
    w_bottom_lookback_days=40,
    w_bottom_tolerance_pct=3.0,
    w_bottom_min_rebound_pct=5.0,
    w_bottom_lower_shadow_ratio=0.4,
    w_bottom_stop_buffer_pct=1.5,
    gap_channel_lookback_days=20,
    gap_channel_max_width_pct=18.0,
    gap_lookback_days=10,
    gap_min_gap_pct=0.5,
    gap_hold_tolerance_pct=1.0,
    gap_lower_shadow_lookback_days=5,
    gap_lower_shadow_ratio=0.4,
    gap_stop_buffer_pct=1.0,
    trailing_stop_activation_pct=8.0,
    trailing_stop_drawdown_pct=8.0,
    request_delay_sec=0.02,
    benchmark_symbol="0050.TW",
    rs_lookback_days=60,
    rs_min_outperformance_pct=5.0,
    vcp_lookback_days=80,
    vcp_min_uptrend_pct=30.0,
    vcp_breakout_volume_ratio=1.5,
    vcp_near_pivot_tolerance_pct=3.0,
    vcp_max_consolidation_depth_pct=25.0,
    progress_callback=None,
    status_callback=None,
):
    ensure_stock_db()
    picked_dict = {}
    securities = get_securities_in_range(start_num, end_num)
    total_stocks = len(securities)
    history_buffer_days = get_history_buffer_days(
        selected_strategies,
        selected_sell_strategies,
        rs_lookback_days,
    )
    benchmark_df = None

    if "相對強弱濾網" in selected_strategies:
        benchmark_df = fetch_price_history(
            benchmark_symbol,
            mode,
            start_date,
            end_date,
            history_buffer_days=history_buffer_days,
        )

    if total_stocks == 0:
        return picked_dict

    for i, security in enumerate(securities, start=1):
        stock_code = security["yfinance_symbol"]
        if status_text:
            status_text.caption(f"🔄 正在回測模擬: {stock_code} ...")
        if status_callback:
            status_callback(f"正在處理 {stock_code}")

        result = check_stock(
            stock_code,
            selected_strategies,
            mode,
            start_date,
            end_date,
            selected_sell_strategies,
            benchmark_df,
            range_lookback_days,
            range_max_width_pct,
            range_volume_ratio,
            range_min_price_gain_pct,
            range_max_price_gain_pct,
            range_volume_sustain_days,
            initial_capital,
            trading_cost_pct,
            initial_stop_loss_pct,
            w_bottom_lookback_days,
            w_bottom_tolerance_pct,
            w_bottom_min_rebound_pct,
            w_bottom_lower_shadow_ratio,
            w_bottom_stop_buffer_pct,
            gap_channel_lookback_days,
            gap_channel_max_width_pct,
            gap_lookback_days,
            gap_min_gap_pct,
            gap_hold_tolerance_pct,
            gap_lower_shadow_lookback_days,
            gap_lower_shadow_ratio,
            gap_stop_buffer_pct,
            trailing_stop_activation_pct,
            trailing_stop_drawdown_pct,
            rs_lookback_days,
            rs_min_outperformance_pct,
            vcp_lookback_days,
            vcp_min_uptrend_pct,
            vcp_breakout_volume_ratio,
            vcp_near_pivot_tolerance_pct,
            vcp_max_consolidation_depth_pct,
            history_buffer_days,
        )

        if result is not None:
            picked_dict[stock_code] = result

        if progress_bar:
            progress_bar.progress(i / total_stocks)
        if progress_callback:
            progress_callback(i / total_stocks, stock_code)
        time.sleep(request_delay_sec)

    return picked_dict
