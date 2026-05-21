import pandas as pd


def _clip_score(value, minimum=0.0, maximum=100.0):
    return max(minimum, min(maximum, float(value)))


def _score_linear(value, low, high, max_score):
    if value <= low:
        return 0.0
    if value >= high:
        return float(max_score)
    return ((value - low) / (high - low)) * float(max_score)


def _grade_bowl_score(score, breakout_pct=0.0, range_position_pct=50.0, current_volume_ratio=1.0, sustain_days=0):
    if (
        score >= 78
        and breakout_pct <= 0.5
        and range_position_pct <= 85.0
        and current_volume_ratio >= 1.15
        and sustain_days >= 2
    ):
        return "A"
    if score >= 64 and breakout_pct <= 5.0:
        return "B"
    if score >= 50 and breakout_pct <= 8.0:
        return "C"
    return "淘汰"


def analyze_bowl_bottom_candidate(
    df,
    lookback_days=60,
    max_range_width_pct=35.0,
    recent_volume_window=3,
    base_volume_window=20,
    min_volume_increase_ratio=1.3,
    price_gain_window=5,
    min_price_gain_pct=0.0,
    max_price_gain_pct=18.0,
    min_latest_volume_lots=500,
    min_sustain_days=3,
):
    """把候選股拆成「量能抬頭 + 仍在盤整區間」的分數，避免太早刷掉潛力股。"""
    required_length = max(lookback_days, base_volume_window + min_sustain_days + 5, 45)
    if len(df) < required_length:
        return None

    window = df.tail(lookback_days).copy()
    if len(window) < 20:
        return None

    current_volume = float(window["Volume"].iloc[-1])
    if current_volume < min_latest_volume_lots * 1000:
        return None

    reference_window = window.iloc[:-3].copy() if len(window) > 12 else window.iloc[:-1].copy()
    if reference_window.empty:
        reference_window = window.copy()

    range_high = float(reference_window["High"].max())
    range_low = float(reference_window["Low"].min())
    if range_low <= 0 or range_high <= range_low:
        return None

    base_depth_pct = (range_high - range_low) / range_low * 100
    allowed_width_pct = max(max_range_width_pct, 65.0)
    if not (6.0 <= base_depth_pct <= allowed_width_pct):
        return None

    close_series = window["Close"]
    current_close = float(close_series.iloc[-1])
    recovery_from_bottom_pct = (current_close / range_low - 1) * 100
    if current_close < range_low * 1.01:
        return None
    breakout_pct = ((current_close / range_high) - 1) * 100 if range_high > 0 else 0.0
    if current_close > range_high * 1.08:
        return None
    range_position_pct = ((current_close - range_low) / (range_high - range_low)) * 100 if range_high > range_low else 0.0

    recent_gain_pct = (close_series.iloc[-1] / close_series.iloc[-(price_gain_window + 1)] - 1) * 100

    ma3_volume = window["Volume"].rolling(window=recent_volume_window).mean()
    ma20_volume = window["Volume"].rolling(window=base_volume_window).mean()
    if ma20_volume.dropna().empty:
        return None

    avg_volume_3 = float(ma3_volume.iloc[-1]) if pd.notna(ma3_volume.iloc[-1]) else current_volume
    avg_volume_20 = float(ma20_volume.iloc[-1]) if pd.notna(ma20_volume.iloc[-1]) else None
    if avg_volume_20 is None or avg_volume_20 <= 0:
        return None

    prev3_slice = window["Volume"].iloc[-4:-1] if len(window) >= 4 else window["Volume"].iloc[:-1]
    prev3_volume_avg = float(prev3_slice.mean()) if not prev3_slice.empty else None
    if prev3_volume_avg is None or pd.isna(prev3_volume_avg) or prev3_volume_avg <= 0:
        return None

    current_volume_ratio = current_volume / prev3_volume_avg
    recent3_volume_ratio = avg_volume_3 / prev3_volume_avg if prev3_volume_avg else None
    avg5_volume_ratio = avg_volume_3 / avg_volume_20 if avg_volume_20 else None
    sustain_days = 0
    for offset in range(1, min(len(window) - 1, 6) + 1):
        current_day_volume = float(window["Volume"].iloc[-offset])
        previous_day_volume = float(window["Volume"].iloc[-offset - 1])
        if previous_day_volume <= 0:
            break
        if current_day_volume >= previous_day_volume * 1.02:
            sustain_days += 1
        else:
            break

    if current_volume_ratio < 1.03 and (recent3_volume_ratio or 0.0) < 1.04 and sustain_days < 1:
        return None

    ma20_price = close_series.rolling(window=20).mean()
    if pd.isna(ma20_price.iloc[-1]):
        return None
    ma20_latest = float(ma20_price.iloc[-1])
    ma20_prev = float(ma20_price.iloc[-6]) if len(ma20_price.dropna()) >= 6 and pd.notna(ma20_price.iloc[-6]) else ma20_latest
    ma20_slope_pct = ((ma20_latest / ma20_prev) - 1) * 100 if ma20_prev else 0.0
    peak_distance_pct = ((range_high / current_close) - 1) * 100 if current_close > 0 else 0.0

    volume_trend_score = _score_linear(recent3_volume_ratio or 0.0, 1.02, max(min_volume_increase_ratio + 0.1, 1.35), 28)
    current_volume_score = _score_linear(current_volume_ratio, 1.03, max(min_volume_increase_ratio + 0.25, 1.6), 28)
    sustain_score = _score_linear(sustain_days, 1, max(min_sustain_days, 3), 16)
    long_term_reference_score = _score_linear(avg5_volume_ratio or 0.0, 1.0, 1.25, 8)

    if 18.0 <= range_position_pct <= 82.0:
        consolidation_position_score = 12.0
    elif 10.0 <= range_position_pct <= 90.0:
        consolidation_position_score = 8.0
    else:
        consolidation_position_score = 6.0

    if current_close <= range_high * 0.985:
        in_range_score = 10.0
    elif current_close <= range_high * 0.995:
        in_range_score = 7.0
    elif current_close <= range_high * 1.005:
        in_range_score = 3.0
    else:
        in_range_score = 0.0

    if 10.0 <= base_depth_pct <= allowed_width_pct:
        width_score = 8.0
    else:
        width_score = 4.0

    if current_close >= ma20_latest and ma20_slope_pct >= -1.5:
        trend_score = 8.0
    elif current_close >= ma20_latest * 0.97:
        trend_score = 5.0
    else:
        trend_score = 2.0

    if recent_gain_pct <= max(12.0, max_price_gain_pct):
        stabilization_score = 6.0
    elif recent_gain_pct <= max(18.0, max_price_gain_pct + 6.0):
        stabilization_score = 4.0
    else:
        stabilization_score = 1.0

    score = _clip_score(
        volume_trend_score
        + current_volume_score
        + consolidation_position_score
        + in_range_score
        + width_score
        + trend_score
        + stabilization_score
        + sustain_score
        + long_term_reference_score
    )
    if breakout_pct > 3.0:
        score -= 20.0
    elif breakout_pct > 1.0:
        score -= 12.0
    elif breakout_pct > 0.5:
        score -= 6.0
    elif breakout_pct > 0.0:
        score -= 3.0

    if range_position_pct > 88.0:
        score -= 14.0
    elif range_position_pct > 82.0:
        score -= 8.0

    if current_volume_ratio < 1.0:
        score -= 18.0
    elif current_volume_ratio < 1.1:
        score -= 8.0

    if (recent3_volume_ratio or 0.0) < 1.02:
        score -= 12.0
    elif (recent3_volume_ratio or 0.0) < 1.08:
        score -= 6.0

    if sustain_days < 1:
        score -= 8.0

    score = _clip_score(score)
    grade = _grade_bowl_score(score, breakout_pct, range_position_pct, current_volume_ratio, sustain_days)

    positive_reasons = []
    caution_reasons = []

    if sustain_days >= min_sustain_days:
        positive_reasons.append(f"量能已連續 {sustain_days} 天墊高")
    elif sustain_days >= 1:
        positive_reasons.append(f"量能剛抬頭，已連續 {sustain_days} 天放大")
    else:
        caution_reasons.append("量能連續性還不夠")

    if current_volume_ratio >= min_volume_increase_ratio:
        positive_reasons.append(f"今日量能較前3日均量放大到 {current_volume_ratio:.2f}x")
    elif current_volume_ratio >= 1.05:
        caution_reasons.append(f"今日量能有增加，但只比前3日多 {current_volume_ratio:.2f}x")
    else:
        caution_reasons.append("今日量能還沒有明顯放大")

    if (recent3_volume_ratio or 0.0) >= 1.08:
        positive_reasons.append(f"近3日均量高於前3日 {recent3_volume_ratio:.2f}x")
    elif (recent3_volume_ratio or 0.0) >= 1.02:
        caution_reasons.append(f"近3日均量略有抬高 {recent3_volume_ratio:.2f}x")

    if current_close <= range_high * 0.99:
        positive_reasons.append(f"現價仍在盤整區內，距區間上緣 {peak_distance_pct:.1f}%")
    elif current_close <= range_high * 1.005:
        positive_reasons.append("現價已貼近區間上緣，仍屬盤整內部")
    else:
        caution_reasons.append("價格已微幅突破區間上緣，要確認能否站穩")

    if 15.0 <= range_position_pct <= 88.0:
        positive_reasons.append(f"目前位在區間中的 {range_position_pct:.0f}% 位置")
    elif range_position_pct < 15.0:
        caution_reasons.append("位置仍偏區間下緣，價格表態還不夠")
    else:
        caution_reasons.append("位置已偏區間上緣，之後要盯突破延續")

    if ma20_slope_pct >= 0:
        positive_reasons.append("20MA 已經走平或微微上彎")
    else:
        caution_reasons.append("20MA 還沒完全走平")

    return {
        "score": round(score, 1),
        "grade": grade,
        "bowl_bottom": round(range_low, 2),
        "left_peak": round(range_high, 2),
        "base_depth_pct": round(base_depth_pct, 2),
        "range_position_pct": round(range_position_pct, 2),
        "breakout_pct": round(breakout_pct, 2),
        "recovery_from_bottom_pct": round(recovery_from_bottom_pct, 2),
        "recent_gain_pct": round(recent_gain_pct, 2),
        "avg_volume_3": round(avg_volume_3),
        "avg_volume_prev3": round(prev3_volume_avg),
        "avg_volume_20": round(avg_volume_20),
        "current_volume_ratio": round(current_volume_ratio, 2),
        "recent3_volume_ratio": round(recent3_volume_ratio, 2) if recent3_volume_ratio is not None else None,
        "avg5_volume_ratio": round(avg5_volume_ratio, 2) if avg5_volume_ratio is not None else None,
        "sustain_days": int(sustain_days),
        "ma20_slope_pct": round(ma20_slope_pct, 2),
        "peak_distance_pct": round(peak_distance_pct, 2),
        "positive_reasons": positive_reasons[:4],
        "caution_reasons": caution_reasons[:4],
    }


def strategy_range_volume_accumulation(
    df,
    lookback_days=60,
    max_range_width_pct=35.0,
    recent_volume_window=5,
    base_volume_window=20,
    min_volume_increase_ratio=1.3,
    price_gain_window=5,
    min_price_gain_pct=0.0,
    max_price_gain_pct=18.0,
    min_latest_volume_lots=500,
    min_sustain_days=3,
):
    analysis = analyze_bowl_bottom_candidate(
        df,
        lookback_days=lookback_days,
        max_range_width_pct=max_range_width_pct,
        recent_volume_window=recent_volume_window,
        base_volume_window=base_volume_window,
        min_volume_increase_ratio=min_volume_increase_ratio,
        price_gain_window=price_gain_window,
        min_price_gain_pct=min_price_gain_pct,
        max_price_gain_pct=max_price_gain_pct,
        min_latest_volume_lots=min_latest_volume_lots,
        min_sustain_days=min_sustain_days,
    )
    return analysis is not None and analysis["score"] >= 52
