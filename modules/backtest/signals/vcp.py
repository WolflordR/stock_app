import pandas as pd


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
