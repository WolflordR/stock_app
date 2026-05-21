import pandas as pd

from bowl_scoring import analyze_bowl_bottom_candidate, strategy_range_volume_accumulation


def strategy_red_k(df):
    return df["Close"].iloc[-1] > df["Open"].iloc[-1]


def strategy_volume_surge(df):
    if len(df) < 6:
        return False
    avg_vol = df["Volume"].rolling(window=5).mean().iloc[-2]
    return df["Volume"].iloc[-1] > (avg_vol * 2)


def strategy_ma_up(df):
    if len(df) < 5:
        return False
    ma5 = df["Close"].rolling(window=5).mean().iloc[-1]
    return df["Close"].iloc[-1] > ma5


def strategy_monthly_dip(df):
    if len(df) < 20:
        return False
    monthly_high = df["High"].rolling(window=20).max().iloc[-1]
    return df["Close"].iloc[-1] <= (monthly_high * 0.9)


def strategy_touch_monthly_ma(df):
    if len(df) < 20:
        return False
    ma20 = df["Close"].rolling(window=20).mean().iloc[-1]
    return df["Low"].iloc[-1] <= ma20


def strategy_golden_cross(df, short_window=20, long_window=60):
    if len(df) < long_window + 1:
        return False
    short_ma = df["Close"].rolling(window=short_window).mean()
    long_ma = df["Close"].rolling(window=long_window).mean()
    return short_ma.iloc[-2] <= long_ma.iloc[-2] and short_ma.iloc[-1] > long_ma.iloc[-1]


def strategy_breakout_with_volume(df, lookback_days=20, volume_window=20, volume_multiplier=1.5):
    if len(df) < max(lookback_days + 1, volume_window + 1):
        return False
    prior_high = df["High"].iloc[-(lookback_days + 1):-1].max()
    avg_volume = df["Volume"].iloc[-(volume_window + 1):-1].mean()
    return df["Close"].iloc[-1] > prior_high and df["Volume"].iloc[-1] > (avg_volume * volume_multiplier)


def strategy_gap_support_rebound(
    df,
    channel_lookback_days=20,
    channel_max_width_pct=18.0,
    gap_lookback_days=10,
    min_gap_pct=0.5,
    gap_hold_tolerance_pct=1.0,
    lower_shadow_lookback_days=5,
    lower_shadow_ratio=0.4,
    gap_stop_buffer_pct=1.0,
):
    required_length = max(channel_lookback_days * 2, gap_lookback_days + 5, lower_shadow_lookback_days + 5, 40)
    if len(df) < required_length:
        return None

    recent_channel = df.tail(channel_lookback_days).copy()
    prior_channel = df.iloc[-(channel_lookback_days * 2):-channel_lookback_days].copy()
    if recent_channel.empty or prior_channel.empty:
        return None

    recent_high = float(recent_channel["High"].max())
    recent_low = float(recent_channel["Low"].min())
    prior_high = float(prior_channel["High"].max())
    prior_low = float(prior_channel["Low"].min())
    if recent_low <= 0 or prior_low <= 0:
        return None

    channel_width_pct = (recent_high - recent_low) / recent_low * 100
    if channel_width_pct > channel_max_width_pct:
        return None

    close_series = df["Close"]
    ma20_series = close_series.rolling(window=20).mean()
    ma20 = ma20_series.iloc[-1]
    ma20_prev = ma20_series.iloc[-6] if len(ma20_series.dropna()) >= 6 else None
    current_close = float(close_series.iloc[-1])
    current_open = float(df["Open"].iloc[-1])
    if pd.isna(ma20) or ma20_prev is None or pd.isna(ma20_prev):
        return None

    range_mid = (recent_high + recent_low) / 2
    if not (
        recent_high > prior_high
        and recent_low > prior_low
        and current_close >= range_mid
        and current_close >= ma20
        and ma20 > ma20_prev
    ):
        return None

    gap_candidates = []
    gap_start = max(1, len(df) - gap_lookback_days)
    for pos in range(gap_start, len(df)):
        prev_high = float(df["High"].iloc[pos - 1])
        gap_day_low = float(df["Low"].iloc[pos])
        if prev_high <= 0:
            continue
        gap_pct = (gap_day_low / prev_high - 1) * 100
        if gap_pct >= min_gap_pct:
            gap_candidates.append((pos, prev_high, gap_day_low, gap_pct))

    if not gap_candidates:
        return None

    gap_pos, gap_support_price, gap_ceiling_price, gap_pct = gap_candidates[-1]
    post_gap_lows = df["Low"].iloc[gap_pos:]
    if post_gap_lows.min() < gap_support_price * (1 - gap_hold_tolerance_pct / 100):
        return None

    touch_support_pos = None
    touch_support_low = None
    touch_support_high = None
    touch_start = max(gap_pos, len(df) - lower_shadow_lookback_days)
    for pos in range(touch_start, len(df)):
        row = df.iloc[pos]
        candle_low = float(row["Low"])
        candle_high = float(row["High"])
        near_gap_support = (
            candle_low >= gap_support_price * (1 - gap_hold_tolerance_pct / 100)
            and candle_low <= gap_ceiling_price * 1.03
        )
        if near_gap_support:
            touch_support_pos = pos
            touch_support_low = candle_low
            touch_support_high = candle_high

    if touch_support_pos is None:
        return None

    ma5 = close_series.rolling(window=5).mean().iloc[-1]
    prev_day_high = float(df["High"].iloc[-2])
    entry_confirmed = (
        current_close > gap_support_price
        and current_close > ma5
        and current_close >= current_open
        and (current_close > prev_day_high or current_close > touch_support_high)
    )
    if not entry_confirmed:
        return None

    support_price = min(gap_support_price, touch_support_low)
    stop_price = support_price * (1 - gap_stop_buffer_pct / 100)

    return {
        "gap_support_price": round(gap_support_price, 2),
        "gap_ceiling_price": round(gap_ceiling_price, 2),
        "gap_stop_price": round(stop_price, 2),
        "gap_day": df.index[gap_pos].strftime("%Y-%m-%d"),
        "shadow_confirm_day": df.index[touch_support_pos].strftime("%Y-%m-%d"),
        "gap_pct": round(gap_pct, 2),
    }


def strategy_uptrend_filter(df):
    if len(df) < 70:
        return False
    ma20_series = df["Close"].rolling(window=20).mean()
    ma60_series = df["Close"].rolling(window=60).mean()
    ma20 = ma20_series.iloc[-1]
    ma60 = ma60_series.iloc[-1]
    ma60_prev = ma60_series.iloc[-11]
    close_price = df["Close"].iloc[-1]
    return ma20 > ma60 and ma60 > ma60_prev and close_price > ma60


def strategy_minervini_template(df):
    if len(df) < 260:
        return False
    close_series = df["Close"]
    ma50_series = close_series.rolling(window=50).mean()
    ma150_series = close_series.rolling(window=150).mean()
    ma200_series = close_series.rolling(window=200).mean()
    ma50 = ma50_series.iloc[-1]
    ma150 = ma150_series.iloc[-1]
    ma200 = ma200_series.iloc[-1]
    ma200_prev = ma200_series.iloc[-21]
    close_price = close_series.iloc[-1]
    yearly_low = df["Low"].iloc[-252:].min()
    yearly_high = df["High"].iloc[-252:].max()
    return (
        close_price > ma50 > ma150 > ma200
        and ma150 > ma200
        and ma200 > ma200_prev
        and close_price >= yearly_low * 1.30
        and close_price >= yearly_high * 0.75
    )


def analyze_vcp_candidate(
    df,
    lookback_days=60,
    min_uptrend_pct=12.0,
    breakout_volume_ratio=1.0,
    near_pivot_tolerance_pct=12.0,
    max_consolidation_depth_pct=45.0,
):
    required_length = max(lookback_days + 90, 170)
    if len(df) < required_length:
        return None

    close_series = pd.to_numeric(df["Close"], errors="coerce")
    high_series = pd.to_numeric(df["High"], errors="coerce")
    low_series = pd.to_numeric(df["Low"], errors="coerce")
    volume_series = pd.to_numeric(df["Volume"], errors="coerce")
    if close_series.isna().any() or high_series.isna().any() or low_series.isna().any() or volume_series.isna().any():
        return None

    window = df.tail(lookback_days).copy()
    prior_trend = df.iloc[-(lookback_days + 60):-lookback_days].copy()
    if len(window) < lookback_days or prior_trend.empty:
        return None

    current_close = float(window["Close"].iloc[-1])
    current_volume = float(window["Volume"].iloc[-1])
    ma50 = float(close_series.rolling(50).mean().iloc[-1])
    ma150 = float(close_series.rolling(150).mean().iloc[-1])
    ma200 = float(close_series.rolling(200).mean().iloc[-1])
    ma200_prev = float(close_series.rolling(200).mean().iloc[-21])
    if any(pd.isna(v) for v in [ma50, ma150, ma200, ma200_prev]):
        return None

    prior_low = float(prior_trend["Low"].min())
    prior_high = float(prior_trend["High"].max())
    if prior_low <= 0:
        return None
    prior_uptrend_pct = (prior_high / prior_low - 1.0) * 100

    window_high = float(window["High"].max())
    window_low = float(window["Low"].min())
    if window_high <= 0 or window_low <= 0:
        return None
    consolidation_depth_pct = (window_high / window_low - 1.0) * 100
    drawdown_from_high_pct = (window_high / current_close - 1.0) * 100 if current_close > 0 else None

    segment_len = max(lookback_days // 3, 15)
    segment1 = window.iloc[-(segment_len * 3):-segment_len * 2]
    segment2 = window.iloc[-(segment_len * 2):-segment_len]
    segment3 = window.iloc[-segment_len:]
    if min(len(segment1), len(segment2), len(segment3)) < 10:
        return None

    def _width_pct(segment):
        low = float(segment["Low"].min())
        high = float(segment["High"].max())
        if low <= 0:
            return None
        return (high / low - 1.0) * 100

    width1 = _width_pct(segment1)
    width2 = _width_pct(segment2)
    width3 = _width_pct(segment3)
    if any(value is None for value in [width1, width2, width3]):
        return None

    vol1 = float(segment1["Volume"].mean())
    vol2 = float(segment2["Volume"].mean())
    vol3 = float(segment3["Volume"].mean())
    avg_volume_20 = float(volume_series.tail(20).mean())
    if avg_volume_20 <= 0:
        return None

    prior_pivot_high = float(window["High"].iloc[:-1].max())
    near_pivot_pct = (prior_pivot_high / current_close - 1.0) * 100 if current_close > 0 else None
    breakout_confirmed = current_close > prior_pivot_high and current_volume >= avg_volume_20 * breakout_volume_ratio
    near_pivot = near_pivot_pct is not None and near_pivot_pct <= near_pivot_tolerance_pct

    distribution_mask = (
        (window["Close"] < window["Open"])
        & (window["Volume"] > window["Volume"].rolling(20).mean())
    )
    distribution_days = int(distribution_mask.tail(15).sum())

    positive_reasons = []
    caution_reasons = []

    strong_trend_ok = (
        prior_uptrend_pct >= min_uptrend_pct
        and current_close >= ma50 * 0.97
        and ma50 >= ma150 * 0.94
        and ma200 >= ma200_prev * 0.99
    )
    if strong_trend_ok:
        positive_reasons.append(f"前波漲幅 {prior_uptrend_pct:.1f}%")
    else:
        caution_reasons.append(f"前波趨勢不足 {prior_uptrend_pct:.1f}%")

    contraction_ok = width3 <= width2 * 1.12 and width2 <= width1 * 1.15 and width3 <= width1 * 0.98
    if contraction_ok:
        positive_reasons.append(f"波動收斂 {width1:.1f}%→{width2:.1f}%→{width3:.1f}%")
    else:
        caution_reasons.append(f"收斂不夠乾淨 {width1:.1f}%→{width2:.1f}%→{width3:.1f}%")

    volume_dry_ok = vol3 <= vol2 * 1.12 and vol2 <= vol1 * 1.18 and vol3 <= vol1 * 1.0
    if volume_dry_ok:
        positive_reasons.append(f"量能收縮 {vol1/1000:,.0f}K→{vol2/1000:,.0f}K→{vol3/1000:,.0f}K")
    else:
        caution_reasons.append("整理量縮不夠明顯")

    structure_ok = (
        consolidation_depth_pct <= max_consolidation_depth_pct
        and distribution_days <= 8
        and drawdown_from_high_pct is not None
        and drawdown_from_high_pct <= max_consolidation_depth_pct + 8
    )
    if structure_ok:
        positive_reasons.append(f"整理深度 {consolidation_depth_pct:.1f}%")
    else:
        caution_reasons.append(f"整理過深或籌碼鬆動 {consolidation_depth_pct:.1f}% / 分配日{distribution_days}天")

    breakout_ok = breakout_confirmed or near_pivot
    if breakout_confirmed:
        positive_reasons.append(f"已放量突破 {current_volume/avg_volume_20:.2f}x")
    elif near_pivot:
        positive_reasons.append(f"接近壓力位 {near_pivot_pct:.2f}%")
    else:
        caution_reasons.append("離突破位仍偏遠")

    score = 0.0
    score += min(max(prior_uptrend_pct / max(min_uptrend_pct, 1.0), 0), 2.0) * 20
    score += min(max(width1 / max(width3, 0.1), 0), 3.0) * 12
    score += min(max(vol1 / max(vol3, 1.0), 0), 3.0) * 10
    score += 20 if structure_ok else 5
    score += 20 if breakout_confirmed else 10 if near_pivot else 0
    score += 10 if current_close > ma50 else 0
    score += 8 if distribution_days <= 2 else 0
    score = round(min(score, 100.0), 1)

    matched = breakout_ok and (strong_trend_ok or prior_uptrend_pct >= min_uptrend_pct * 0.8) and (structure_ok or contraction_ok) and (contraction_ok or volume_dry_ok)
    return {
        "matched": matched,
        "score": score,
        "prior_uptrend_pct": round(prior_uptrend_pct, 2),
        "consolidation_depth_pct": round(consolidation_depth_pct, 2),
        "drawdown_from_high_pct": round(drawdown_from_high_pct, 2) if drawdown_from_high_pct is not None else None,
        "widths_pct": [round(width1, 2), round(width2, 2), round(width3, 2)],
        "volume_means": [round(vol1), round(vol2), round(vol3)],
        "distribution_days": distribution_days,
        "near_pivot_pct": round(near_pivot_pct, 2) if near_pivot_pct is not None else None,
        "breakout_confirmed": breakout_confirmed,
        "positive_reasons": positive_reasons,
        "caution_reasons": caution_reasons,
        "pivot_high": round(prior_pivot_high, 2),
        "avg_volume_20": round(avg_volume_20),
    }


def strategy_vcp_breakout(
    df,
    lookback_days=60,
    min_uptrend_pct=12.0,
    breakout_volume_ratio=1.0,
    near_pivot_tolerance_pct=12.0,
    max_consolidation_depth_pct=45.0,
):
    analysis = analyze_vcp_candidate(
        df,
        lookback_days=lookback_days,
        min_uptrend_pct=min_uptrend_pct,
        breakout_volume_ratio=breakout_volume_ratio,
        near_pivot_tolerance_pct=near_pivot_tolerance_pct,
        max_consolidation_depth_pct=max_consolidation_depth_pct,
    )
    return analysis["matched"] if analysis else False


def calculate_relative_strength_spread(df, benchmark_df, lookback_days=60):
    if benchmark_df is None or df.empty or benchmark_df.empty:
        return None
    aligned = pd.DataFrame(
        {
            "stock": pd.to_numeric(df["Close"], errors="coerce"),
            "benchmark": pd.to_numeric(benchmark_df["Close"], errors="coerce"),
        }
    ).dropna()
    if len(aligned) < lookback_days + 1:
        return None
    stock_return = (aligned["stock"].iloc[-1] / aligned["stock"].iloc[-(lookback_days + 1)] - 1) * 100
    benchmark_return = (aligned["benchmark"].iloc[-1] / aligned["benchmark"].iloc[-(lookback_days + 1)] - 1) * 100
    return stock_return - benchmark_return


def strategy_relative_strength_filter(df, benchmark_df, lookback_days=60, min_outperformance_pct=5.0):
    rs_spread_pct = calculate_relative_strength_spread(df, benchmark_df, lookback_days)
    if rs_spread_pct is None:
        return False, None
    return rs_spread_pct >= min_outperformance_pct, rs_spread_pct


def strategy_death_cross(df, short_window=20, long_window=60):
    if len(df) < long_window + 1:
        return False
    short_ma = df["Close"].rolling(window=short_window).mean()
    long_ma = df["Close"].rolling(window=long_window).mean()
    return short_ma.iloc[-2] >= long_ma.iloc[-2] and short_ma.iloc[-1] < long_ma.iloc[-1]


def strategy_break_support(df, lookback_days=10):
    if len(df) < lookback_days + 1:
        return False
    support_price = df["Low"].iloc[-(lookback_days + 1):-1].min()
    return df["Close"].iloc[-1] < support_price


def strategy_w_bottom_rebound(
    df,
    lookback_days=40,
    bottom_tolerance_pct=3.0,
    min_rebound_pct=5.0,
    lower_shadow_ratio=0.4,
    stop_buffer_pct=1.5,
):
    if len(df) < max(lookback_days, 20):
        return None

    window = df.tail(lookback_days).copy()
    current_row = window.iloc[-1]
    history_before_current = window.iloc[:-1]
    if len(history_before_current) < 10:
        return None

    left_search = history_before_current.iloc[:-5]
    if left_search.empty:
        return None

    left_bottom_idx = left_search["Low"].idxmin()
    left_bottom_price = float(window.loc[left_bottom_idx, "Low"])
    left_bottom_pos = window.index.get_loc(left_bottom_idx)
    middle_section = window.iloc[left_bottom_pos + 1:-1]
    if len(middle_section) < 3:
        return None

    middle_peak_price = float(middle_section["High"].max())
    rebound_pct = ((middle_peak_price - left_bottom_price) / left_bottom_price) * 100
    if rebound_pct < min_rebound_pct:
        return None

    current_low = float(current_row["Low"])
    current_high = float(current_row["High"])
    current_open = float(current_row["Open"])
    current_close = float(current_row["Close"])
    bottom_diff_pct = abs(current_low - left_bottom_price) / left_bottom_price * 100
    if bottom_diff_pct > bottom_tolerance_pct:
        return None

    candle_range = current_high - current_low
    if candle_range <= 0:
        return None

    lower_shadow = min(current_open, current_close) - current_low
    close_position = (current_close - current_low) / candle_range
    if lower_shadow / candle_range < lower_shadow_ratio:
        return None
    if current_close <= left_bottom_price or close_position < 0.55:
        return None
    if current_close >= middle_peak_price:
        return None

    support_price = min(left_bottom_price, current_low)
    stop_price = support_price * (1 - stop_buffer_pct / 100)
    return {
        "support_price": round(support_price, 2),
        "stop_price": round(stop_price, 2),
        "target_price": round(middle_peak_price, 2),
        "left_bottom_price": round(left_bottom_price, 2),
    }


def evaluate_buy_signal(
    df,
    selected_strategies,
    benchmark_df=None,
    range_lookback_days=60,
    range_max_width_pct=35.0,
    range_volume_ratio=1.3,
    range_min_price_gain_pct=0.0,
    range_max_price_gain_pct=18.0,
    range_volume_sustain_days=3,
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
    rs_lookback_days=60,
    rs_min_outperformance_pct=5.0,
    vcp_lookback_days=80,
    vcp_min_uptrend_pct=30.0,
    vcp_breakout_volume_ratio=1.5,
    vcp_near_pivot_tolerance_pct=3.0,
    vcp_max_consolidation_depth_pct=25.0,
):
    check_results = []
    buy_setup = {}

    if "月高回檔策略" in selected_strategies:
        check_results.append(strategy_monthly_dip(df))
    if "爆量策略" in selected_strategies:
        check_results.append(strategy_volume_surge(df))
    if "均線策略" in selected_strategies:
        check_results.append(strategy_ma_up(df))
    if "跌到月線買入" in selected_strategies:
        check_results.append(strategy_touch_monthly_ma(df))
    if "黃金交叉策略" in selected_strategies:
        check_results.append(strategy_golden_cross(df))
    if "突破前高策略" in selected_strategies:
        check_results.append(strategy_breakout_with_volume(df))
    if "區間量增啟動" in selected_strategies:
        check_results.append(
            strategy_range_volume_accumulation(
                df,
                range_lookback_days,
                range_max_width_pct,
                min_volume_increase_ratio=range_volume_ratio,
                min_price_gain_pct=range_min_price_gain_pct,
                max_price_gain_pct=range_max_price_gain_pct,
                min_sustain_days=range_volume_sustain_days,
            )
        )
    if "上升缺口承接" in selected_strategies:
        gap_setup = strategy_gap_support_rebound(
            df,
            gap_channel_lookback_days,
            gap_channel_max_width_pct,
            gap_lookback_days,
            gap_min_gap_pct,
            gap_hold_tolerance_pct,
            gap_lower_shadow_lookback_days,
            gap_lower_shadow_ratio,
            gap_stop_buffer_pct,
        )
        check_results.append(gap_setup is not None)
        if gap_setup is not None:
            buy_setup.update(gap_setup)
    if "上升趨勢濾網" in selected_strategies:
        check_results.append(strategy_uptrend_filter(df))
    if "Minervini 趨勢模板" in selected_strategies:
        check_results.append(strategy_minervini_template(df))
    if "VCP 收斂突破" in selected_strategies:
        vcp_setup = analyze_vcp_candidate(
            df,
            vcp_lookback_days,
            vcp_min_uptrend_pct,
            vcp_breakout_volume_ratio,
            vcp_near_pivot_tolerance_pct,
            vcp_max_consolidation_depth_pct,
        )
        check_results.append(vcp_setup is not None and vcp_setup.get("matched", False))
        if vcp_setup is not None:
            buy_setup.update(
                {
                    "vcp_score": vcp_setup.get("score"),
                    "vcp_prior_uptrend_pct": vcp_setup.get("prior_uptrend_pct"),
                    "vcp_consolidation_depth_pct": vcp_setup.get("consolidation_depth_pct"),
                    "vcp_near_pivot_pct": vcp_setup.get("near_pivot_pct"),
                    "vcp_distribution_days": vcp_setup.get("distribution_days"),
                    "vcp_breakout_confirmed": vcp_setup.get("breakout_confirmed"),
                    "vcp_positive_reasons": vcp_setup.get("positive_reasons") or [],
                    "vcp_caution_reasons": vcp_setup.get("caution_reasons") or [],
                    "vcp_pivot_high": vcp_setup.get("pivot_high"),
                }
            )
    if "相對強弱濾網" in selected_strategies:
        rs_matched, rs_spread_pct = strategy_relative_strength_filter(
            df,
            benchmark_df,
            rs_lookback_days,
            rs_min_outperformance_pct,
        )
        check_results.append(rs_matched)
        if rs_spread_pct is not None:
            buy_setup["rs_spread_pct"] = rs_spread_pct
    if "W底反彈" in selected_strategies:
        w_bottom_setup = strategy_w_bottom_rebound(
            df,
            w_bottom_lookback_days,
            w_bottom_tolerance_pct,
            w_bottom_min_rebound_pct,
            w_bottom_lower_shadow_ratio,
            w_bottom_stop_buffer_pct,
        )
        check_results.append(w_bottom_setup is not None)
        if w_bottom_setup is not None:
            buy_setup.update(w_bottom_setup)

    return bool(check_results) and all(check_results), buy_setup


def get_history_buffer_days(selected_strategies, selected_sell_strategies=None, rs_lookback_days=60):
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
    if "相對強弱濾網" in selected_strategies:
        history_buffer_days = max(history_buffer_days, rs_lookback_days + 90)

    return history_buffer_days
