import logging
import time
from functools import lru_cache

from modules.backtest.performance_metrics import build_equity_curve, build_performance_summary
from modules.backtest.signals.registry import evaluate_registered_buy_strategies
from modules.backtest.signals.sell_registry import evaluate_registered_sell_strategies
from modules.core.trading_calendar import resolve_after_hours_trade_date, resolve_recent_trade_date
from modules.data_sources.market_watch import fetch_tpex_daily_quotes, fetch_twse_daily_quotes
from modules.data_sources.price_cache import fetch_price_history
from modules.data_sources.stock_db import ensure_stock_db, get_securities_in_range, get_security_share_profile, get_stock_name
from modules.industry.company_links_db import get_company_profiles_df
from modules.industry.industry_taxonomy import TECH_INDUSTRY_NAMES
from modules.backtest.strategy_signals import get_history_buffer_days


logger = logging.getLogger(__name__)


def get_chinese_name(stock_id):
    return get_stock_name(stock_id)


@lru_cache(maxsize=1)
def _load_tech_stock_symbol_set():
    profiles_df = get_company_profiles_df()
    if profiles_df.empty:
        return set()

    tech_industries = set(TECH_INDUSTRY_NAMES)
    tech_df = profiles_df[profiles_df["industry"].fillna("").astype(str).str.strip().isin(tech_industries)].copy()
    symbols = set(tech_df["yfinance_symbol"].fillna("").astype(str).str.strip())
    codes = set(tech_df["code"].fillna("").astype(str).str.zfill(4))
    return {value for value in symbols | codes if value}


def _is_tech_stock(stock_id):
    normalized = str(stock_id or "").strip().upper()
    if not normalized:
        return False
    code = normalized.split(".")[0]
    tech_lookup = _load_tech_stock_symbol_set()
    return normalized in tech_lookup or code in tech_lookup


def _resolve_scan_trade_date_text(mode="即時選股", end_date=None):
    if end_date:
        return resolve_recent_trade_date(end_date)["effective_date_text"]
    if mode == "即時選股":
        return resolve_after_hours_trade_date()["effective_date_text"]
    return resolve_recent_trade_date(None)["effective_date_text"]


@lru_cache(maxsize=16)
def _load_market_cap_leader_symbol_set(trade_date_text, rank_limit=50):
    rank_limit = max(1, int(rank_limit))
    twse_df = fetch_twse_daily_quotes(trade_date_text)
    tpex_df = fetch_tpex_daily_quotes(trade_date_text)
    quote_df = None
    if not twse_df.empty and not tpex_df.empty:
        import pandas as pd

        quote_df = pd.concat([twse_df, tpex_df], ignore_index=True)
    elif not twse_df.empty:
        quote_df = twse_df.copy()
    elif not tpex_df.empty:
        quote_df = tpex_df.copy()
    else:
        quote_df = None

    if quote_df is None or quote_df.empty:
        return frozenset()

    market_caps = []
    for row in quote_df.itertuples(index=False):
        code = str(getattr(row, "code", "") or "").strip()
        if not code:
            continue
        close_value = getattr(row, "close", None)
        try:
            close_price = float(close_value)
        except (TypeError, ValueError):
            continue
        if close_price <= 0:
            continue

        symbol = str(getattr(row, "symbol", "") or "").strip().upper()
        market = str(getattr(row, "market", "") or "").strip().upper()
        stock_input = symbol or code
        share_profile = get_security_share_profile(stock_input)
        issued_common_shares = (share_profile or {}).get("issued_common_shares")
        try:
            shares = float(issued_common_shares)
        except (TypeError, ValueError):
            continue
        if shares <= 0:
            continue
        effective_symbol = symbol or (f"{code}.TW" if market == "TWSE" else f"{code}.TWO")
        market_caps.append((close_price * shares, code, effective_symbol))

    market_caps.sort(key=lambda item: item[0], reverse=True)
    leaders = set()
    for _, code, symbol in market_caps[:rank_limit]:
        leaders.add(code)
        leaders.add(symbol.upper())
    return frozenset(leaders)


def _build_trade_record(*, buy_date, buy_price, sell_date, sell_price, trading_cost_pct, reason, active_setup):
    gross_return_pct = (sell_price - buy_price) / buy_price * 100
    net_return_pct = gross_return_pct - trading_cost_pct
    return {
        "buy_date": buy_date,
        "buy_price": buy_price,
        "sell_date": sell_date,
        "sell_price": sell_price,
        "gross_return_pct": gross_return_pct,
        "cost_pct": trading_cost_pct,
        "return_pct": net_return_pct,
        "reason": reason,
        "buy_rs_spread_pct": active_setup.get("rs_spread_pct"),
        "w_support_price": active_setup.get("support_price"),
        "w_stop_price": active_setup.get("stop_price"),
        "w_target_price": active_setup.get("target_price"),
        "gap_support_price": active_setup.get("gap_support_price"),
        "gap_stop_price": active_setup.get("gap_stop_price"),
        "gap_day": active_setup.get("gap_day"),
        "gap_shadow_day": active_setup.get("shadow_confirm_day"),
        "pullback_score": active_setup.get("pullback_score"),
        "pullback_depth_pct": active_setup.get("pullback_depth_pct"),
        "pullback_reference_high": active_setup.get("pullback_reference_high"),
        "pullback_guard_low": active_setup.get("pullback_guard_low"),
        "pullback_prior_close": active_setup.get("pullback_prior_close"),
        "pullback_latest_close": active_setup.get("pullback_latest_close"),
        "high_price_pullback_score": active_setup.get("high_price_pullback_score"),
        "high_price_pullback_depth_pct": active_setup.get("high_price_pullback_depth_pct"),
        "high_price_pullback_reference_high": active_setup.get("high_price_pullback_reference_high"),
        "high_price_pullback_latest_close": active_setup.get("high_price_pullback_latest_close"),
        "near_breakout_score": active_setup.get("near_breakout_score"),
        "bowl_volume_score": active_setup.get("bowl_volume_score"),
    }


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
    pullback_strong_lookback_days=20,
    pullback_min_pullback_pct=10.0,
    pullback_base_hold_days=3,
    pullback_low_price_volume_price_threshold=500.0,
    pullback_low_price_min_volume_lots=700.0,
    pullback_technology_only=True,
    high_price_pullback_lookback_days=20,
    high_price_pullback_market_cap_rank_limit=50,
    high_price_pullback_min_drop_pct=15.0,
    high_price_pullback_eligible_symbol_set=None,
    breakout_lookback_days=252,
    breakout_distance_pct=10.0,
    breakout_trend_lookback_days=20,
    breakout_volume_short_window=5,
    breakout_volume_long_window=20,
    bowl_volume_lookback_days=120,
    bowl_volume_min_drawdown_pct=20.0,
    bowl_volume_short_window=5,
    bowl_volume_long_window=20,
    bowl_volume_min_volume_ratio=1.2,
    bowl_volume_trend_lookback_days=10,
    history_buffer_days=120,
):
    try:
        selected_sell_strategies = selected_sell_strategies or []
        if "強勢股回檔量縮止跌" in selected_strategies and pullback_technology_only and not _is_tech_stock(stock_id):
            return None
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

        buy_strategy_params = {
            "range_lookback_days": range_lookback_days,
            "range_max_width_pct": range_max_width_pct,
            "range_volume_ratio": range_volume_ratio,
            "range_min_price_gain_pct": range_min_price_gain_pct,
            "range_max_price_gain_pct": range_max_price_gain_pct,
            "range_volume_sustain_days": range_volume_sustain_days,
            "w_bottom_lookback_days": w_bottom_lookback_days,
            "w_bottom_tolerance_pct": w_bottom_tolerance_pct,
            "w_bottom_min_rebound_pct": w_bottom_min_rebound_pct,
            "w_bottom_lower_shadow_ratio": w_bottom_lower_shadow_ratio,
            "w_bottom_stop_buffer_pct": w_bottom_stop_buffer_pct,
            "gap_channel_lookback_days": gap_channel_lookback_days,
            "gap_channel_max_width_pct": gap_channel_max_width_pct,
            "gap_lookback_days": gap_lookback_days,
            "gap_min_gap_pct": gap_min_gap_pct,
            "gap_hold_tolerance_pct": gap_hold_tolerance_pct,
            "gap_lower_shadow_lookback_days": gap_lower_shadow_lookback_days,
            "gap_lower_shadow_ratio": gap_lower_shadow_ratio,
            "gap_stop_buffer_pct": gap_stop_buffer_pct,
            "rs_lookback_days": rs_lookback_days,
            "rs_min_outperformance_pct": rs_min_outperformance_pct,
            "vcp_lookback_days": vcp_lookback_days,
            "vcp_min_uptrend_pct": vcp_min_uptrend_pct,
            "vcp_breakout_volume_ratio": vcp_breakout_volume_ratio,
            "vcp_near_pivot_tolerance_pct": vcp_near_pivot_tolerance_pct,
            "vcp_max_consolidation_depth_pct": vcp_max_consolidation_depth_pct,
            "pullback_strong_lookback_days": pullback_strong_lookback_days,
            "pullback_min_pullback_pct": pullback_min_pullback_pct,
            "pullback_base_hold_days": pullback_base_hold_days,
            "pullback_low_price_volume_price_threshold": pullback_low_price_volume_price_threshold,
            "pullback_low_price_min_volume_lots": pullback_low_price_min_volume_lots,
            "high_price_pullback_lookback_days": high_price_pullback_lookback_days,
            "high_price_pullback_market_cap_rank_limit": high_price_pullback_market_cap_rank_limit,
            "high_price_pullback_min_drop_pct": high_price_pullback_min_drop_pct,
            "high_price_pullback_eligible_symbol_set": high_price_pullback_eligible_symbol_set or set(),
            "breakout_lookback_days": breakout_lookback_days,
            "breakout_distance_pct": breakout_distance_pct,
            "breakout_trend_lookback_days": breakout_trend_lookback_days,
            "breakout_volume_short_window": breakout_volume_short_window,
            "breakout_volume_long_window": breakout_volume_long_window,
            "bowl_volume_lookback_days": bowl_volume_lookback_days,
            "bowl_volume_min_drawdown_pct": bowl_volume_min_drawdown_pct,
            "bowl_volume_short_window": bowl_volume_short_window,
            "bowl_volume_long_window": bowl_volume_long_window,
            "bowl_volume_min_volume_ratio": bowl_volume_min_volume_ratio,
            "bowl_volume_trend_lookback_days": bowl_volume_trend_lookback_days,
            "stock_id": stock_id,
        }

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
                    matched, buy_setup = evaluate_registered_buy_strategies(
                        current_slice,
                        selected_strategies,
                        benchmark_df=benchmark_df.loc[: current_slice.index[-1]] if benchmark_df is not None else None,
                        params=buy_strategy_params,
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

                    sold, sell_price, sell_reason = evaluate_registered_sell_strategies(
                        current_slice,
                        current_row,
                        selected_sell_strategies,
                        position={
                            "buy_price": buy_price,
                            "buy_date": buy_date,
                            "days_held": days_held,
                            "max_high": max_high,
                            "active_setup": active_setup,
                        },
                        params={
                            "initial_stop_loss_pct": initial_stop_loss_pct,
                            "w_bottom_stop_buffer_pct": w_bottom_stop_buffer_pct,
                            "gap_stop_buffer_pct": gap_stop_buffer_pct,
                            "trailing_stop_activation_pct": trailing_stop_activation_pct,
                            "trailing_stop_drawdown_pct": trailing_stop_drawdown_pct,
                        },
                    )

                    if sold:
                        trades.append(
                            _build_trade_record(
                                buy_date=buy_date,
                                buy_price=buy_price,
                                sell_date=current_date,
                                sell_price=sell_price,
                                trading_cost_pct=trading_cost_pct,
                                reason=sell_reason,
                                active_setup=active_setup,
                            )
                        )
                        in_position = False
                        active_setup = {}

            if in_position:
                final_row = df.iloc[-1]
                final_sell_price = final_row["Close"]
                trades.append(
                    _build_trade_record(
                        buy_date=buy_date,
                        buy_price=buy_price,
                        sell_date=df.index[-1].strftime("%Y-%m-%d"),
                        sell_price=final_sell_price,
                        trading_cost_pct=trading_cost_pct,
                        reason="回測結束平倉",
                        active_setup=active_setup,
                    )
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

        matched, buy_setup = evaluate_registered_buy_strategies(
            df,
            selected_strategies,
            benchmark_df=benchmark_df,
            params=buy_strategy_params,
        )
        if matched:
            latest_volume = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0.0
            return {
                "name": get_chinese_name(stock_id),
                "price": round(float(df["Close"].iloc[-1]), 2),
                "rs_spread_pct": buy_setup.get("rs_spread_pct"),
                "latest_volume": round(latest_volume),
                "avg_volume_3": buy_setup.get("avg_volume_3"),
                "avg_volume_prev3": buy_setup.get("avg_volume_prev3"),
                "avg_volume_20": buy_setup.get("avg_volume_20"),
                "current_volume_ratio": buy_setup.get("current_volume_ratio"),
                "recent3_volume_ratio": buy_setup.get("recent3_volume_ratio"),
                "avg5_volume_ratio": buy_setup.get("avg5_volume_ratio"),
                "recovery_from_bottom_pct": buy_setup.get("recovery_from_bottom_pct"),
                "bowl_score": buy_setup.get("bowl_score"),
                "bowl_grade": buy_setup.get("bowl_grade"),
                "bowl_depth_pct": buy_setup.get("bowl_depth_pct"),
                "sustain_days": buy_setup.get("sustain_days"),
                "peak_distance_pct": buy_setup.get("peak_distance_pct"),
                "range_position_pct": buy_setup.get("range_position_pct"),
                "breakout_pct": buy_setup.get("breakout_pct"),
                "positive_reasons": buy_setup.get("positive_reasons") or [],
                "caution_reasons": buy_setup.get("caution_reasons") or [],
                "vcp_score": buy_setup.get("vcp_score"),
                "vcp_prior_uptrend_pct": buy_setup.get("vcp_prior_uptrend_pct"),
                "vcp_consolidation_depth_pct": buy_setup.get("vcp_consolidation_depth_pct"),
                "vcp_near_pivot_pct": buy_setup.get("vcp_near_pivot_pct"),
                "vcp_distribution_days": buy_setup.get("vcp_distribution_days"),
                "vcp_breakout_confirmed": buy_setup.get("vcp_breakout_confirmed"),
                "vcp_positive_reasons": buy_setup.get("vcp_positive_reasons") or [],
                "vcp_caution_reasons": buy_setup.get("vcp_caution_reasons") or [],
                "pullback_score": buy_setup.get("pullback_score"),
                "pullback_depth_pct": buy_setup.get("pullback_depth_pct"),
                "pullback_reference_high": buy_setup.get("pullback_reference_high"),
                "pullback_guard_low": buy_setup.get("pullback_guard_low"),
                "pullback_prior_close": buy_setup.get("pullback_prior_close"),
                "pullback_latest_close": buy_setup.get("pullback_latest_close"),
                "pullback_positive_reasons": buy_setup.get("pullback_positive_reasons") or [],
                "pullback_caution_reasons": buy_setup.get("pullback_caution_reasons") or [],
                "pullback_latest_volume_lots": buy_setup.get("pullback_latest_volume_lots"),
                "pullback_low_price_volume_price_threshold": buy_setup.get("pullback_low_price_volume_price_threshold"),
                "pullback_low_price_min_volume_lots": buy_setup.get("pullback_low_price_min_volume_lots"),
                "high_price_pullback_score": buy_setup.get("high_price_pullback_score"),
                "high_price_pullback_depth_pct": buy_setup.get("high_price_pullback_depth_pct"),
                "high_price_pullback_reference_high": buy_setup.get("high_price_pullback_reference_high"),
                "high_price_pullback_latest_close": buy_setup.get("high_price_pullback_latest_close"),
                "high_price_pullback_positive_reasons": buy_setup.get("high_price_pullback_positive_reasons") or [],
                "high_price_pullback_caution_reasons": buy_setup.get("high_price_pullback_caution_reasons") or [],
                "near_breakout_score": buy_setup.get("near_breakout_score"),
                "near_breakout_latest_close": buy_setup.get("near_breakout_latest_close"),
                "near_breakout_high_price": buy_setup.get("near_breakout_high_price"),
                "near_breakout_high_date": buy_setup.get("near_breakout_high_date"),
                "near_breakout_distance_pct": buy_setup.get("near_breakout_distance_pct"),
                "near_breakout_latest_volume": buy_setup.get("near_breakout_latest_volume"),
                "near_breakout_avg_volume_short": buy_setup.get("near_breakout_avg_volume_short"),
                "near_breakout_avg_volume_long": buy_setup.get("near_breakout_avg_volume_long"),
                "near_breakout_volume_ratio": buy_setup.get("near_breakout_volume_ratio"),
                "near_breakout_latest_volume_ratio": buy_setup.get("near_breakout_latest_volume_ratio"),
                "near_breakout_price_trend_pct": buy_setup.get("near_breakout_price_trend_pct"),
                "near_breakout_positive_reasons": buy_setup.get("near_breakout_positive_reasons") or [],
                "near_breakout_caution_reasons": buy_setup.get("near_breakout_caution_reasons") or [],
                "bowl_volume_score": buy_setup.get("bowl_volume_score"),
                "bowl_volume_half_year_high": buy_setup.get("bowl_volume_half_year_high"),
                "bowl_volume_half_year_high_date": buy_setup.get("bowl_volume_half_year_high_date"),
                "bowl_volume_subsequent_low": buy_setup.get("bowl_volume_subsequent_low"),
                "bowl_volume_subsequent_low_date": buy_setup.get("bowl_volume_subsequent_low_date"),
                "bowl_volume_drawdown_pct": buy_setup.get("bowl_volume_drawdown_pct"),
                "bowl_volume_latest_close": buy_setup.get("bowl_volume_latest_close"),
                "bowl_volume_recovery_from_bottom_pct": buy_setup.get("bowl_volume_recovery_from_bottom_pct"),
                "bowl_volume_avg_volume_short": buy_setup.get("bowl_volume_avg_volume_short"),
                "bowl_volume_avg_volume_long": buy_setup.get("bowl_volume_avg_volume_long"),
                "bowl_volume_volume_ratio": buy_setup.get("bowl_volume_volume_ratio"),
                "bowl_volume_up_down_volume_ratio": buy_setup.get("bowl_volume_up_down_volume_ratio"),
                "bowl_volume_recent_trend_pct": buy_setup.get("bowl_volume_recent_trend_pct"),
                "bowl_volume_ma20_slope_pct": buy_setup.get("bowl_volume_ma20_slope_pct"),
                "bowl_volume_positive_reasons": buy_setup.get("bowl_volume_positive_reasons") or [],
                "bowl_volume_caution_reasons": buy_setup.get("bowl_volume_caution_reasons") or [],
            }
        return None
    except Exception as exc:
        logger.exception("Error checking stock %s", stock_id)
        return None


def _sort_scan_results(results):
    def sort_score(item):
        _, payload = item
        if not isinstance(payload, dict):
            return 0.0
        for key in (
            "bowl_volume_score",
            "near_breakout_score",
            "pullback_score",
            "high_price_pullback_score",
            "vcp_score",
            "bowl_score",
            "total_return",
        ):
            value = payload.get(key)
            if value is not None:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    return dict(sorted(results.items(), key=sort_score, reverse=True))


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
    pullback_strong_lookback_days=20,
    pullback_min_pullback_pct=10.0,
    pullback_base_hold_days=3,
    pullback_low_price_volume_price_threshold=500.0,
    pullback_low_price_min_volume_lots=700.0,
    pullback_technology_only=True,
    high_price_pullback_lookback_days=20,
    high_price_pullback_market_cap_rank_limit=50,
    high_price_pullback_min_drop_pct=15.0,
    breakout_lookback_days=252,
    breakout_distance_pct=10.0,
    breakout_trend_lookback_days=20,
    breakout_volume_short_window=5,
    breakout_volume_long_window=20,
    bowl_volume_lookback_days=120,
    bowl_volume_min_drawdown_pct=20.0,
    bowl_volume_short_window=5,
    bowl_volume_long_window=20,
    bowl_volume_min_volume_ratio=1.2,
    bowl_volume_trend_lookback_days=10,
    progress_callback=None,
    status_callback=None,
):
    ensure_stock_db()
    picked_dict = {}
    securities = get_securities_in_range(start_num, end_num)
    total_stocks = len(securities)
    history_buffer_days = get_history_buffer_days(
        selected_strategies,
        selected_sell_strategies=selected_sell_strategies,
        rs_lookback_days=rs_lookback_days,
    )
    benchmark_df = None
    market_cap_leader_symbol_set = frozenset()

    if "相對強弱濾網" in selected_strategies:
        benchmark_df = fetch_price_history(
            benchmark_symbol,
            mode,
            start_date,
            end_date,
            history_buffer_days=history_buffer_days,
        )

    if "高價股回檔" in selected_strategies:
        trade_date_text = _resolve_scan_trade_date_text(mode=mode, end_date=end_date)
        market_cap_leader_symbol_set = _load_market_cap_leader_symbol_set(
            trade_date_text,
            high_price_pullback_market_cap_rank_limit,
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
            pullback_strong_lookback_days,
            pullback_min_pullback_pct,
            pullback_base_hold_days,
            pullback_low_price_volume_price_threshold,
            pullback_low_price_min_volume_lots,
            pullback_technology_only,
            high_price_pullback_lookback_days,
            high_price_pullback_market_cap_rank_limit,
            high_price_pullback_min_drop_pct,
            market_cap_leader_symbol_set,
            breakout_lookback_days,
            breakout_distance_pct,
            breakout_trend_lookback_days,
            breakout_volume_short_window,
            breakout_volume_long_window,
            bowl_volume_lookback_days,
            bowl_volume_min_drawdown_pct,
            bowl_volume_short_window,
            bowl_volume_long_window,
            bowl_volume_min_volume_ratio,
            bowl_volume_trend_lookback_days,
            history_buffer_days,
        )

        if result is not None:
            picked_dict[stock_code] = result

        if progress_bar:
            progress_bar.progress(i / total_stocks)
        if progress_callback:
            progress_callback(i / total_stocks, stock_code)
        time.sleep(request_delay_sec)

    return _sort_scan_results(picked_dict)
