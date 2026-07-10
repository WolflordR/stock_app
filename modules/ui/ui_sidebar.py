from datetime import datetime, timedelta

import streamlit as st

from modules.data_sources.stock_db import ensure_stock_db, get_securities_in_range, refresh_stock_db
from modules.backtest.strategy_config import BUY_STRATEGY_METADATA, DEFAULT_BUY_STRATEGIES, DEFAULT_SELL_STRATEGIES, SELL_STRATEGY_METADATA
from modules.ui.ui_status import render_backtest_job_sidebar_status
from modules.ui.ui_state import seed_strategy_dialog_state
from modules.ui.ui_theme import render_background_theme_control


def render_sidebar(selected_view):
    state = {
        "start_date": None,
        "end_date": None,
        "initial_capital": 0,
        "trading_cost_pct": 0.0,
        "initial_stop_loss_pct": 5.0,
        "w_bottom_lookback_days": 40,
        "w_bottom_tolerance_pct": 3.0,
        "w_bottom_min_rebound_pct": 5.0,
        "w_bottom_lower_shadow_ratio": 0.4,
        "w_bottom_stop_buffer_pct": 1.5,
        "gap_channel_lookback_days": 20,
        "gap_channel_max_width_pct": 18.0,
        "gap_lookback_days": 10,
        "gap_min_gap_pct": 0.5,
        "gap_hold_tolerance_pct": 1.0,
        "gap_lower_shadow_lookback_days": 5,
        "gap_lower_shadow_ratio": 0.4,
        "gap_stop_buffer_pct": 1.0,
        "trailing_stop_activation_pct": 8.0,
        "trailing_stop_drawdown_pct": 8.0,
        "request_delay_sec": 0.02,
        "benchmark_symbol": "0050.TW",
        "rs_lookback_days": 60,
        "rs_min_outperformance_pct": 5.0,
        "vcp_lookback_days": 60,
        "vcp_min_uptrend_pct": 12.0,
        "vcp_breakout_volume_ratio": 1.0,
        "vcp_near_pivot_tolerance_pct": 12.0,
        "vcp_max_consolidation_depth_pct": 45.0,
        "range_lookback_days": 60,
        "range_max_width_pct": 65.0,
        "range_volume_ratio": 1.3,
        "range_min_price_gain_pct": 0.0,
        "range_max_price_gain_pct": 18.0,
        "range_volume_sustain_days": 3,
        "revenue_top_n": 10,
        "revenue_min_yoy_pct": 3.0,
        "revenue_min_mom_pct": -10.0,
        "revenue_min_cumulative_yoy_pct": -5.0,
        "revenue_required_consecutive_months": 3,
        "revenue_exclude_february": True,
        "market_watch_top_n": 30,
        "home_trade_date": datetime.now().date(),
        "news_trade_date": datetime.now().date(),
        "news_industry_count": 5,
        "news_headlines_per_industry": 4,
        "us_news_items": 8,
        "selected_sell_strategies": [],
        "mode": "歷史回測",
        "selected_strategies": ["VCP 收斂突破"],
        "submit_button": False,
        "start_num": 0,
        "end_num": 9999,
    }

    with st.sidebar:
        st.header("設定")
        render_background_theme_control()
        st.divider()

        revenue_profile_version = "tech_revenue_loose_v1"
        if st.session_state.get("revenue_profile_version") != revenue_profile_version:
            st.session_state["revenue_min_yoy_pct"] = 3.0
            st.session_state["revenue_min_mom_pct"] = -10.0
            st.session_state["revenue_min_cumulative_yoy_pct"] = -5.0
            st.session_state["revenue_required_consecutive_months"] = 3
            st.session_state["revenue_exclude_february"] = True
            st.session_state["revenue_profile_version"] = revenue_profile_version

        active_scan_job_id = st.session_state.get("active_scan_job_id")
        if active_scan_job_id:
            render_backtest_job_sidebar_status()

        try:
            stock_db_status = ensure_stock_db()
        except Exception as exc:
            stock_db_status = {"count": 0, "last_sync_at": None}
            st.warning(f"股票主檔初始化失敗：{exc}")

        if selected_view == "回測 / 選股":
            state["mode"] = st.segmented_control(
                "模式",
                ["歷史回測", "即時選股"],
                default=st.session_state["backtest_mode"],
                key="backtest_mode",
                width="stretch",
            )

            with st.expander("掃描與資料來源", expanded=True):
                st.caption("建議先測試 2330~2335，大範圍回測會比較耗時。")
                state["start_num"] = st.number_input("起始代碼", value=0, step=1, format="%04d")
                state["end_num"] = st.number_input("結束代碼", value=9999, step=1, format="%04d")
                if st.button("🔄 更新股票主檔", use_container_width=True):
                    try:
                        stock_db_status = refresh_stock_db()
                        st.success(f"股票主檔已更新，共 {stock_db_status['count']} 檔。")
                    except Exception as exc:
                        st.error(f"更新股票主檔失敗：{exc}")

                valid_range_count = len(get_securities_in_range(state["start_num"], state["end_num"]))
                if stock_db_status["last_sync_at"]:
                    st.caption(f"股票主檔：{stock_db_status['count']} 檔，最後更新 {stock_db_status['last_sync_at']}")
                else:
                    st.caption(f"股票主檔：{stock_db_status['count']} 檔")
                st.caption(f"目前區間內有效股票數：{valid_range_count} 檔")

                state["request_delay_sec"] = st.number_input(
                    "每檔請求延遲 (秒)",
                    value=0.02,
                    step=0.01,
                    min_value=0.00,
                    max_value=1.00,
                )

            with st.expander("資金與時間", expanded=(state["mode"] == "歷史回測")):
                if state["mode"] == "歷史回測":
                    state["start_date"] = st.date_input("回測開始日", value=datetime.now() - timedelta(days=90))
                    state["end_date"] = st.date_input("回測結束日", value=datetime.now())
                    state["initial_capital"] = st.number_input("每檔股票分配資金", value=100000, step=10000)
                    state["trading_cost_pct"] = st.number_input("交易成本 + 誤差 (%)", value=0.7, step=0.1, min_value=0.0)
                else:
                    st.caption("即時選股模式不需要設定回測日期與本金。")

            with st.expander("買入策略", expanded=True):
                st.session_state["selected_buy_strategies"] = DEFAULT_BUY_STRATEGIES.copy()
                state["selected_strategies"] = DEFAULT_BUY_STRATEGIES.copy()
                meta = BUY_STRATEGY_METADATA["VCP 收斂突破"]
                st.markdown(f"• {meta['title']}：{meta['summary']}")
                st.caption("回測 / 選股目前已收斂成單一 VCP 策略，先把流程簡化。")

            with st.expander("VCP 參數", expanded=True):
                state["vcp_lookback_days"] = st.number_input("VCP 整理回看天數", value=60, step=5, min_value=40)
                state["vcp_min_uptrend_pct"] = st.number_input("前波至少上漲 (%)", value=12.0, step=1.0, min_value=3.0)
                state["vcp_breakout_volume_ratio"] = st.number_input("突破量至少幾倍 20MA", value=1.0, step=0.1, min_value=0.8)
                state["vcp_near_pivot_tolerance_pct"] = st.number_input("允許距離壓力位 (%)", value=12.0, step=0.5, min_value=2.0)
                state["vcp_max_consolidation_depth_pct"] = st.number_input("整理最大回檔深度 (%)", value=45.0, step=1.0, min_value=12.0)
                st.caption("預設改成較寬鬆版本：先多抓候選，再用 VCP 分數排序，不會太早把股票刷掉。")

            if state["mode"] == "歷史回測":
                with st.expander("賣出策略", expanded=True):
                    st.caption("只要任何一個已選賣出條件成立，就會出場。")
                    if st.button("選擇賣出策略", key="open_sell_strategy_dialog", use_container_width=True):
                        seed_strategy_dialog_state(
                            "sell_strategy_dialog",
                            st.session_state["selected_sell_strategies"],
                            SELL_STRATEGY_METADATA,
                        )
                        st.session_state["show_sell_strategy_dialog"] = True

                    state["selected_sell_strategies"] = st.session_state.get("selected_sell_strategies", DEFAULT_SELL_STRATEGIES.copy())
                    if state["selected_sell_strategies"]:
                        for strategy_name in state["selected_sell_strategies"]:
                            meta = SELL_STRATEGY_METADATA[strategy_name]
                            st.markdown(f"• {meta['title']}：{meta['summary']}")
                    else:
                        st.caption("目前還沒有選任何賣出策略。")

                expanded = ("初始停損" in state["selected_sell_strategies"] or "移動式停損" in state["selected_sell_strategies"])
                with st.expander("停損參數", expanded=expanded):
                    if "初始停損" in state["selected_sell_strategies"]:
                        state["initial_stop_loss_pct"] = st.number_input("初始停損幅度 (%)", value=5.0, step=0.5, min_value=0.1)

                    if "移動式停損" in state["selected_sell_strategies"]:
                        state["trailing_stop_activation_pct"] = st.number_input("啟動移動停損的最低浮盈 (%)", value=8.0, step=0.5, min_value=0.0)
                        state["trailing_stop_drawdown_pct"] = st.number_input("高點回撤出場幅度 (%)", value=8.0, step=0.5, min_value=0.1)
            else:
                state["selected_sell_strategies"] = []
                st.caption("即時選股模式只負責找買點，不需要設定賣出策略。")

            state["submit_button"] = st.button("開始執行", use_container_width=True)

        elif selected_view == "首頁":
            with st.expander("掃描與資料來源", expanded=True):
                st.caption("首頁現在只保留市場摘要、法人訊號、資金流向、法說日程、月營收動能與處置股票。")
                state["home_trade_date"] = st.date_input("首頁資料日期", value=datetime.now(), key="home_trade_date")
                if st.button("🔄 更新股票主檔", use_container_width=True, key="range_refresh_db"):
                    try:
                        stock_db_status = refresh_stock_db()
                        st.success(f"股票主檔已更新，共 {stock_db_status['count']} 檔。")
                    except Exception as exc:
                        st.error(f"更新股票主檔失敗：{exc}")

                valid_range_count = len(get_securities_in_range(state["start_num"], state["end_num"]))
                if stock_db_status["last_sync_at"]:
                    st.caption(f"股票主檔：{stock_db_status['count']} 檔，最後更新 {stock_db_status['last_sync_at']}")
                else:
                    st.caption(f"股票主檔：{stock_db_status['count']} 檔")
                st.caption(f"目前固定掃描全市場代碼區間 0000~9999，有效股票共 {valid_range_count} 檔")

            with st.expander("月營收動能參數", expanded=True):
                state["revenue_top_n"] = st.selectbox("首頁顯示幾檔", [10, 20, 30], index=0, key="revenue_top_n")
                state["revenue_required_consecutive_months"] = st.selectbox(
                    "至少觀察幾個月的營收趨勢",
                    [2, 3, 4],
                    index=1,
                    key="revenue_required_consecutive_months",
                )
                state["revenue_min_yoy_pct"] = st.number_input("YoY 最低門檻 (%)", value=3.0, step=1.0, key="revenue_min_yoy_pct")
                state["revenue_min_mom_pct"] = st.number_input("MoM 最低門檻 (%)", value=-10.0, step=1.0, key="revenue_min_mom_pct")
                state["revenue_min_cumulative_yoy_pct"] = st.number_input("累計 YoY 最低門檻 (%)", value=-5.0, step=1.0, key="revenue_min_cumulative_yoy_pct")
                state["revenue_exclude_february"] = st.checkbox(
                    "月均值判斷時排除 2 月",
                    value=True,
                    key="revenue_exclude_february",
                )
                st.caption("這一塊現在只看科技股，優先抓最近 3 個月整體往上、最新月仍站在高檔的公司；YoY / MoM 只留作輔助門檻，不再設太硬。")

            with st.expander("市場監看參數", expanded=True):
                state["market_watch_top_n"] = st.selectbox("漲跌停 / 鎖住頁每張表顯示", [20, 30, 50], index=1, key="market_watch_top_n")

        elif selected_view == "研究工作台":
            with st.expander("候選掃描設定", expanded=True):
                st.caption("盤整吸籌候選掃描已經併到研究工作台，首頁不再跑這塊。")
                state["home_trade_date"] = st.date_input("研究預設日期", value=datetime.now(), key="research_home_trade_date")
                if st.button("🔄 更新股票主檔", use_container_width=True, key="research_refresh_db"):
                    try:
                        stock_db_status = refresh_stock_db()
                        st.success(f"股票主檔已更新，共 {stock_db_status['count']} 檔。")
                    except Exception as exc:
                        st.error(f"更新股票主檔失敗：{exc}")

                valid_range_count = len(get_securities_in_range(state["start_num"], state["end_num"]))
                if stock_db_status["last_sync_at"]:
                    st.caption(f"股票主檔：{stock_db_status['count']} 檔，最後更新 {stock_db_status['last_sync_at']}")
                else:
                    st.caption(f"股票主檔：{stock_db_status['count']} 檔")
                st.caption(f"目前掃描全市場代碼區間 0000~9999，有效股票共 {valid_range_count} 檔")

            with st.expander("盤整吸籌參數", expanded=True):
                state["range_lookback_days"] = st.number_input("區間回看天數", value=60, step=5, min_value=20, key="research_range_scan_lookback")
                state["range_max_width_pct"] = st.number_input("最大盤整區間寬度 (%)", value=65.0, step=0.5, min_value=6.0, key="research_range_scan_width")
                state["range_volume_ratio"] = st.number_input("今日量能較前3日均量至少倍數", value=1.3, step=0.05, min_value=1.0, key="research_range_scan_volume_ratio")
                state["range_volume_sustain_days"] = st.number_input("連續放量天數", value=3, step=1, min_value=1, max_value=10, key="research_range_scan_sustain_days")
                state["range_min_price_gain_pct"] = st.number_input("近5日至少漲幅 (%)", value=0.0, step=0.5, min_value=-5.0, key="research_range_scan_min_gain")
                state["range_max_price_gain_pct"] = st.number_input("近5日最多漲幅 (%)", value=18.0, step=0.5, min_value=3.0, key="research_range_scan_max_gain")
                st.caption("會優先抓價格還留在盤整區裡、而且今日量能比前3日略放大，或近幾天量能連續抬高的股票；20日均量只留作長期參考。")

        elif selected_view == "新聞分析":
            with st.expander("新聞分析設定", expanded=True):
                state["news_trade_date"] = st.date_input("新聞觀察日期", value=datetime.now(), key="news_trade_date")
                state["news_industry_count"] = st.selectbox("要追幾個熱門主題", [5, 8, 10, 12], index=1, key="news_industry_count")
                state["news_headlines_per_industry"] = st.selectbox("每個主題抓幾則新聞", [3, 4, 5], index=1, key="news_headlines_per_industry")
                state["us_news_items"] = st.selectbox("美股新聞顯示幾則", [6, 8, 10], index=1, key="us_news_items")

    return state
