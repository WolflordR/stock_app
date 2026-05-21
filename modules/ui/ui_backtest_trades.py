import pandas as pd
import streamlit as st

from modules.ui.ui_backtest_charts import build_buy_context, render_trade_reason_visuals
from modules.ui.ui_backtest_summary import build_portfolio_summary


def _param_value(params, field_name, default=None):
    if isinstance(params, dict):
        return params.get(field_name, default)
    return getattr(params, field_name, default)


def render_scan_results(results, params):
    mode = _param_value(params, "mode")
    selected_strategies = _param_value(params, "selected_strategies", [])
    selected_sell_strategies = _param_value(params, "selected_sell_strategies", [])

    if not results:
        st.warning("⚠️ 掃描結束，指定區間內沒有產生任何交易訊號。")
        return

    if mode == "歷史回測":
        portfolio_summary = build_portfolio_summary(results)
        st.success(f"回測完成！在這段期間內，共有 {len(results)} 檔股票出現過交易訊號。")
        with st.expander("本次設定摘要", expanded=False):
            st.caption("股票主檔已改成只掃官方有效代碼；歷史價格會寫入本地快取，重跑通常會更快。")
            st.write(
                f"模式：{mode}｜延遲：{_param_value(params, 'request_delay_sec', 0.0):.2f} 秒｜交易成本 + 誤差：{_param_value(params, 'trading_cost_pct', 0.0):.2f}%"
            )
            if "初始停損" in selected_sell_strategies:
                st.write(f"初始停損：{_param_value(params, 'initial_stop_loss_pct', 0.0):.1f}%")
            if "移動式停損" in selected_sell_strategies:
                st.write(
                    f"移動停損：浮盈達 {_param_value(params, 'trailing_stop_activation_pct', 0.0):.1f}% 啟動，"
                    f"高點回撤 {_param_value(params, 'trailing_stop_drawdown_pct', 0.0):.1f}% 出場"
                )
            if "W底反彈" in selected_strategies:
                st.write(
                    f"W底：回看 {_param_value(params, 'w_bottom_lookback_days', 0)} 日｜容許誤差 {_param_value(params, 'w_bottom_tolerance_pct', 0.0):.1f}%｜"
                    f"中間反彈 {_param_value(params, 'w_bottom_min_rebound_pct', 0.0):.1f}%｜下引線比例 {_param_value(params, 'w_bottom_lower_shadow_ratio', 0.0):.2f}"
                )
            if "區間量增啟動" in selected_strategies:
                st.write(
                    f"盤整吸籌：回看 {_param_value(params, 'range_lookback_days', 0)} 日｜最大盤整區間寬度 <= {_param_value(params, 'range_max_width_pct', 0.0):.1f}%｜"
                    f"今日量能 >= 前3日均量 {_param_value(params, 'range_volume_ratio', 0.0):.2f} 倍｜連續放量 {_param_value(params, 'range_volume_sustain_days', 0)} 天｜"
                    f"近5日漲幅 {_param_value(params, 'range_min_price_gain_pct', 0.0):.1f}%~{_param_value(params, 'range_max_price_gain_pct', 0.0):.1f}%"
                )
            if "上升缺口承接" in selected_strategies:
                st.write(
                    f"上升缺口承接：區間回看 {_param_value(params, 'gap_channel_lookback_days', 0)} 日｜區間寬度 <= {_param_value(params, 'gap_channel_max_width_pct', 0.0):.1f}%｜"
                    f"缺口回看 {_param_value(params, 'gap_lookback_days', 0)} 日｜最小缺口 {_param_value(params, 'gap_min_gap_pct', 0.0):.1f}%｜"
                    f"缺口容許跌破 {_param_value(params, 'gap_hold_tolerance_pct', 0.0):.1f}%｜下引線回看 {_param_value(params, 'gap_lower_shadow_lookback_days', 0)} 日"
                )
            if "相對強弱濾網" in selected_strategies:
                st.write(
                    f"相對強弱：{_param_value(params, 'benchmark_symbol', '0050.TW')}｜近 {_param_value(params, 'rs_lookback_days', 0)} 日至少優於 {_param_value(params, 'rs_min_outperformance_pct', 0.0):.1f}%"
                )
            if "VCP 收斂突破" in selected_strategies:
                st.write(
                    f"VCP：整理回看 {_param_value(params, 'vcp_lookback_days', 0)} 日｜前波至少上漲 {_param_value(params, 'vcp_min_uptrend_pct', 0.0):.1f}%｜"
                    f"突破量 >= {_param_value(params, 'vcp_breakout_volume_ratio', 0.0):.2f} 倍 20MA｜允許距離壓力位 {_param_value(params, 'vcp_near_pivot_tolerance_pct', 0.0):.1f}%"
                )

        overview_tab, detail_tab = st.tabs(["整體總覽", "逐檔明細"])

        with overview_tab:
            summary_cols = st.columns(6)
            summary_cols[0].metric("交易股票數", portfolio_summary["total_stocks"])
            summary_cols[1].metric("總交易次數", portfolio_summary["total_trades"])
            summary_cols[2].metric("整體勝率", f"{portfolio_summary['overall_win_rate']:.1f}%")
            summary_cols[3].metric("總投入資金", f"{portfolio_summary['total_initial_capital']:,.0f} 元")
            summary_cols[4].metric("整體淨損益", f"{portfolio_summary['total_net_profit']:,.0f} 元")
            summary_cols[5].metric("整體總報酬", f"{portfolio_summary['overall_return']:.2f}%")
            summary_cols_2 = st.columns(3)
            summary_cols_2[0].metric("平均單筆報酬", f"{portfolio_summary['avg_trade_return']:.2f}%")
            profit_factor_text = "∞" if portfolio_summary["profit_factor"] == float("inf") else f"{portfolio_summary['profit_factor']:.2f}"
            summary_cols_2[1].metric("Profit Factor", profit_factor_text)
            summary_cols_2[2].metric("整體最大回撤", f"{portfolio_summary['max_drawdown']:.2f}%")
            if portfolio_summary["avg_buy_rs_spread"] is not None:
                st.metric("平均買入時相對強弱", f"{portfolio_summary['avg_buy_rs_spread']:.2f}%")

            st.write("**整體資金曲線圖**")
            st.line_chart(portfolio_summary["total_curve_df"])

        with detail_tab:
            for code, info in results.items():
                title = f"{info['name']} ({code})｜交易 {info['total_trades']} 次｜勝率 {info['win_rate']:.1f}%｜總報酬 {info['total_return']:.2f}%"
                with st.expander(title, expanded=False):
                    metric_cols = st.columns(4)
                    metric_cols[0].metric("起始資金", f"{info['initial_capital']:,.0f} 元")
                    metric_cols[1].metric("期末資金", f"{info['ending_capital']:,.0f} 元")
                    metric_cols[2].metric("淨損益", f"{info['net_profit']:,.0f} 元")
                    metric_cols[3].metric("複利總報酬", f"{info['total_return']:.2f}%")
                    metric_cols_2 = st.columns(3)
                    metric_cols_2[0].metric("平均單筆報酬", f"{info['avg_trade_return']:.2f}%")
                    single_pf_text = "∞" if info["profit_factor"] == float("inf") else f"{info['profit_factor']:.2f}"
                    metric_cols_2[1].metric("Profit Factor", single_pf_text)
                    metric_cols_2[2].metric("最大回撤", f"{info['max_drawdown']:.2f}%")
                    if info.get("avg_buy_rs_spread") is not None:
                        st.metric("平均買入時相對強弱", f"{info['avg_buy_rs_spread']:.2f}%")

                    equity_df = pd.DataFrame(info["equity_curve"])
                    equity_df["date"] = pd.to_datetime(equity_df["date"])
                    equity_df = equity_df.set_index("date")

                    st.write("**資金曲線圖**")
                    st.line_chart(equity_df.rename(columns={"capital": "資金"}))

                    render_trade_reason_visuals(code, info, params, selected_strategies)

                    trade_rows = []
                    for trade in info["trades"]:
                        row = {
                            "買入日期": trade["buy_date"],
                            "買入脈絡": build_buy_context(trade, selected_strategies),
                            "投入資金": f"{trade['capital_before']:,.0f}",
                            "買入價": f"{trade['buy_price']:.2f}",
                            "賣出日期": trade["sell_date"],
                            "賣出價": f"{trade['sell_price']:.2f}",
                            "平倉原因": trade["reason"],
                            "毛報酬 (%)": f"{trade['gross_return_pct']:.2f}%",
                            "成本/誤差 (%)": f"{trade['cost_pct']:.2f}%",
                            "淨報酬 (%)": f"{trade['return_pct']:.2f}%",
                            "單筆損益": f"{trade['profit_loss']:,.0f}",
                            "交易後資金": f"{trade['capital_after']:,.0f}",
                        }
                        if trade.get("buy_rs_spread_pct") is not None:
                            row["買入時相對強弱"] = f"{trade['buy_rs_spread_pct']:.2f}%"
                        if "W底反彈" in selected_strategies:
                            row["W支撐"] = f"{trade['w_support_price']:.2f}" if trade.get("w_support_price") else "-"
                            row["W停損"] = f"{trade['w_stop_price']:.2f}" if trade.get("w_stop_price") else "-"
                            row["W目標"] = f"{trade['w_target_price']:.2f}" if trade.get("w_target_price") else "-"
                        if "上升缺口承接" in selected_strategies:
                            row["缺口日"] = trade.get("gap_day") or "-"
                            row["承接下引線日"] = trade.get("gap_shadow_day") or "-"
                            row["缺口支撐"] = f"{trade['gap_support_price']:.2f}" if trade.get("gap_support_price") else "-"
                            row["缺口停損"] = f"{trade['gap_stop_price']:.2f}" if trade.get("gap_stop_price") else "-"
                        trade_rows.append(row)

                    with st.expander(f"查看進出場歷史紀錄 ({len(trade_rows)} 筆)", expanded=False):
                        st.table(trade_rows)
    elif mode == "即時選股":
        st.success(f"掃描完成！符合條件的標的有 {len(results)} 檔。")
        st.caption("目前是依照本地股票主檔掃描有效上市/上櫃代碼。")
        st.caption(f"目前每檔請求延遲設定為 {_param_value(params, 'request_delay_sec', 0.0):.2f} 秒。")
        if "相對強弱濾網" in selected_strategies:
            st.caption(
                f"相對強弱目前用 {_param_value(params, 'benchmark_symbol', '0050.TW')} 當基準，"
                f"近 {_param_value(params, 'rs_lookback_days', 0)} 日至少優於 {_param_value(params, 'rs_min_outperformance_pct', 0.0):.1f}%。"
            )
        if "VCP 收斂突破" in selected_strategies:
            sorted_results = sorted(
                results.items(),
                key=lambda item: item[1].get("vcp_score", float("-inf")) if item[1].get("vcp_score") is not None else float("-inf"),
                reverse=True,
            )
        else:
            sorted_results = sorted(
                results.items(),
                key=lambda item: item[1].get("rs_spread_pct", float("-inf")) if item[1].get("rs_spread_pct") is not None else float("-inf"),
                reverse=True,
            )
        cols = st.columns(4)
        for index, (code, info) in enumerate(sorted_results):
            with cols[index % 4]:
                help_text = None
                if "VCP 收斂突破" in selected_strategies and info.get("vcp_score") is not None:
                    help_text = (
                        f"VCP分數 {info['vcp_score']:.1f}｜"
                        f"前波 {info.get('vcp_prior_uptrend_pct', 0):.1f}%｜"
                        f"整理深度 {info.get('vcp_consolidation_depth_pct', 0):.1f}%"
                    )
                elif info.get("rs_spread_pct") is not None:
                    help_text = f"相對強弱 {info['rs_spread_pct']:.2f}%"
                st.metric(label=f"{info['name']} ({code})", value=f"{info['price']} 元", help=help_text)
        if "VCP 收斂突破" in selected_strategies:
            vcp_rows = []
            for code, info in sorted_results:
                vcp_rows.append(
                    {
                        "代碼": code.replace(".TW", "").replace(".TWO", ""),
                        "名稱": info["name"],
                        "價格": info["price"],
                        "VCP分數": info.get("vcp_score"),
                        "前波漲幅(%)": info.get("vcp_prior_uptrend_pct"),
                        "整理深度(%)": info.get("vcp_consolidation_depth_pct"),
                        "距壓力位(%)": info.get("vcp_near_pivot_pct"),
                        "分配日數": info.get("vcp_distribution_days"),
                        "突破確認": "是" if info.get("vcp_breakout_confirmed") else "接近突破",
                        "VCP理由": "；".join((info.get("vcp_positive_reasons") or [])[:3]) or "-",
                        "觀察點": "；".join((info.get("vcp_caution_reasons") or [])[:2]) or "-",
                    }
                )
            st.write("**VCP 候選總表**")
            st.dataframe(pd.DataFrame(vcp_rows), use_container_width=True, hide_index=True)
