from __future__ import annotations

import pandas as pd


BREAKOUT_DISTANCE = 0.10
BREAKOUT_LOOKBACK_DAYS = 252
BREAKOUT_TREND_LOOKBACK_DAYS = 20
BOWL_LOOKBACK_DAYS = 120
MIN_DRAWDOWN = 0.20
VOLUME_SHORT_WINDOW = 5
VOLUME_LONG_WINDOW = 20
BOWL_VOLUME_LOOKBACK_DAYS = 20
BOWL_VOLUME_SIGNAL_WINDOW = 3
BOWL_VOLUME_MULTIPLIER = 2.0
BOWL_TREND_LOOKBACK_DAYS = 10
BOWL_MIN_RECOVERY_FROM_BOTTOM = 0.08
BOWL_BOTTOM_ZONE_PCT = 0.12
BOWL_MIN_BOTTOM_DAYS = 3
BOWL_MIN_BOTTOM_SPAN_DAYS = 5


def _clean_ohlcv(df: pd.DataFrame, *, required_length: int) -> pd.DataFrame | None:
    if df is None or len(df) < required_length:
        return None
    required_columns = ["Open", "High", "Low", "Close", "Volume"]
    if any(column not in df.columns for column in required_columns):
        return None
    cleaned = df[required_columns].copy()
    for column in required_columns:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    cleaned = cleaned.dropna(subset=required_columns)
    if len(cleaned) < required_length:
        return None
    return cleaned.sort_index()


def _date_text(index_value) -> str:
    if hasattr(index_value, "strftime"):
        return index_value.strftime("%Y-%m-%d")
    return str(index_value)


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _find_recent_volume_signal(
    window: pd.DataFrame,
    *,
    volume_lookback_days: int,
    signal_window_days: int,
    volume_multiplier: float,
) -> dict[str, object] | None:
    volume_lookback_days = max(2, int(volume_lookback_days))
    signal_window_days = max(1, int(signal_window_days))
    volume_multiplier = max(0.1, float(volume_multiplier))
    candidates: list[dict[str, object]] = []
    start_pos = max(1, len(window) - signal_window_days)

    for pos in range(start_pos, len(window)):
        if pos < volume_lookback_days:
            continue
        avg_volume = float(window["Volume"].iloc[pos - volume_lookback_days : pos].mean())
        current_volume = float(window["Volume"].iloc[pos])
        previous_close = float(window["Close"].iloc[pos - 1])
        current_close = float(window["Close"].iloc[pos])
        volume_ratio = _safe_ratio(current_volume, avg_volume) or 0.0
        price_change_pct = ((current_close / previous_close) - 1.0) * 100 if previous_close > 0 else 0.0
        if volume_ratio >= volume_multiplier and current_close > previous_close:
            candidates.append({
                "volume_signal_date": _date_text(window.index[pos]),
                "volume_signal_pos": pos,
                "volume_signal_volume": round(current_volume),
                "volume_signal_avg_volume_20d": round(avg_volume),
                "volume_signal_ratio": round(volume_ratio, 2),
                "volume_signal_price_change_pct": round(price_change_pct, 2),
                "days_since_volume_signal": len(window) - 1 - pos,
            })

    if not candidates:
        return None
    return max(candidates, key=lambda item: float(item["volume_signal_ratio"]))


def _has_bottom_base(window: pd.DataFrame, *, low_pos: int, subsequent_low: float) -> tuple[bool, dict[str, int]]:
    right_side = window.iloc[low_pos:].copy()
    if right_side.empty or subsequent_low <= 0:
        return False, {"bottom_days": 0, "bottom_span_days": 0}

    bottom_band = subsequent_low * (1.0 + BOWL_BOTTOM_ZONE_PCT)
    bottom_positions = [low_pos + offset for offset, value in enumerate(right_side["Close"]) if float(value) <= bottom_band]
    if not bottom_positions:
        return False, {"bottom_days": 0, "bottom_span_days": 0}

    bottom_days = len(bottom_positions)
    bottom_span_days = bottom_positions[-1] - bottom_positions[0] + 1
    return (
        bottom_days >= BOWL_MIN_BOTTOM_DAYS and bottom_span_days >= BOWL_MIN_BOTTOM_SPAN_DAYS,
        {"bottom_days": bottom_days, "bottom_span_days": bottom_span_days},
    )


def analyze_near_breakout_candidate(
    df: pd.DataFrame,
    *,
    lookback_days: int = BREAKOUT_LOOKBACK_DAYS,
    max_distance: float = BREAKOUT_DISTANCE,
    trend_lookback_days: int = BREAKOUT_TREND_LOOKBACK_DAYS,
    volume_short_window: int = VOLUME_SHORT_WINDOW,
    volume_long_window: int = VOLUME_LONG_WINDOW,
) -> dict[str, object] | None:
    required_length = max(lookback_days, trend_lookback_days + 2, volume_long_window + 2, 30)
    cleaned = _clean_ohlcv(df, required_length=required_length)
    if cleaned is None:
        return None

    lookback_days = max(30, int(lookback_days))
    trend_lookback_days = max(3, int(trend_lookback_days))
    volume_short_window = max(1, int(volume_short_window))
    volume_long_window = max(volume_short_window + 1, int(volume_long_window))

    window = cleaned.tail(lookback_days).copy()
    prior_window = window.iloc[:-1].copy()
    if prior_window.empty:
        return None

    prior_high_idx = prior_window["High"].idxmax()
    high_price = float(prior_window.loc[prior_high_idx, "High"])
    latest_close = float(window["Close"].iloc[-1])
    latest_volume = float(window["Volume"].iloc[-1])
    if high_price <= 0 or latest_close <= 0:
        return None

    distance_to_high = (high_price - latest_close) / high_price
    if distance_to_high > max_distance:
        return None
    # This strategy is for "near breakout", not chasing a large post-breakout extension.
    if distance_to_high < -0.03:
        return None

    trend_reference = float(window["Close"].iloc[-(trend_lookback_days + 1)])
    recent_low = float(window["Low"].tail(trend_lookback_days).min())
    price_trend_pct = ((latest_close / trend_reference) - 1.0) * 100 if trend_reference > 0 else 0.0
    rebound_from_recent_low_pct = ((latest_close / recent_low) - 1.0) * 100 if recent_low > 0 else 0.0

    ma5 = float(window["Close"].rolling(5).mean().iloc[-1])
    ma20 = float(window["Close"].rolling(20).mean().iloc[-1])
    upward_ok = price_trend_pct > 0 and latest_close >= ma5 and ma5 >= ma20 * 0.98
    if not upward_ok:
        return None

    avg_volume_short = float(window["Volume"].tail(volume_short_window).mean())
    avg_volume_long = float(window["Volume"].tail(volume_long_window).mean())
    volume_ratio = _safe_ratio(avg_volume_short, avg_volume_long) or 0.0
    latest_volume_ratio = _safe_ratio(latest_volume, avg_volume_long) or 0.0

    distance_pct = distance_to_high * 100
    score = 0.0
    score += max(0.0, min(35.0, (max_distance - max(distance_to_high, 0.0)) / max_distance * 35.0))
    score += max(0.0, min(25.0, price_trend_pct / 12.0 * 25.0))
    score += max(0.0, min(20.0, rebound_from_recent_low_pct / 18.0 * 20.0))
    score += max(0.0, min(20.0, (volume_ratio - 0.8) / 0.8 * 20.0))
    score = round(max(0.0, min(100.0, score)), 1)

    positive_reasons = [
        f"收盤 {latest_close:.2f} 已回到前高 {high_price:.2f} 的 {100 - distance_pct:.1f}%",
        f"近 {trend_lookback_days} 日收盤上漲 {price_trend_pct:.1f}%，不是單純高檔下跌",
    ]
    if volume_ratio >= 1.0:
        positive_reasons.append(f"{volume_short_window}日均量 / {volume_long_window}日均量 = {volume_ratio:.2f}x")
    else:
        positive_reasons.append(f"量能尚未明顯放大，短長均量比 {volume_ratio:.2f}x")

    return {
        "matched": True,
        "score": score,
        "latest_close": round(latest_close, 2),
        "high_price": round(high_price, 2),
        "high_date": _date_text(prior_high_idx),
        "distance_to_high_pct": round(distance_pct, 2),
        "latest_volume": round(latest_volume),
        "avg_volume_short": round(avg_volume_short),
        "avg_volume_long": round(avg_volume_long),
        "volume_ratio": round(volume_ratio, 2),
        "latest_volume_ratio": round(latest_volume_ratio, 2),
        "price_trend_pct": round(price_trend_pct, 2),
        "rebound_from_recent_low_pct": round(rebound_from_recent_low_pct, 2),
        "positive_reasons": positive_reasons[:4],
        "caution_reasons": [],
    }


def strategy_near_breakout(df: pd.DataFrame, **kwargs) -> bool:
    setup = analyze_near_breakout_candidate(df, **kwargs)
    return bool(setup and setup.get("matched"))


def analyze_bowl_bottom_volume_candidate(
    df: pd.DataFrame,
    *,
    lookback_days: int = BOWL_LOOKBACK_DAYS,
    min_drawdown: float = MIN_DRAWDOWN,
    volume_lookback_days: int = BOWL_VOLUME_LOOKBACK_DAYS,
    volume_signal_window_days: int = BOWL_VOLUME_SIGNAL_WINDOW,
    volume_multiplier: float = BOWL_VOLUME_MULTIPLIER,
    trend_lookback_days: int = BOWL_TREND_LOOKBACK_DAYS,
) -> dict[str, object] | None:
    required_length = max(lookback_days, volume_lookback_days + volume_signal_window_days + 5, trend_lookback_days + 30, 60)
    cleaned = _clean_ohlcv(df, required_length=required_length)
    if cleaned is None:
        return None

    lookback_days = max(60, int(lookback_days))
    trend_lookback_days = max(3, int(trend_lookback_days))
    volume_lookback_days = max(2, int(volume_lookback_days))
    volume_signal_window_days = max(1, int(volume_signal_window_days))
    volume_multiplier = max(0.1, float(volume_multiplier))

    window = cleaned.tail(lookback_days).copy()
    high_idx = window["High"].idxmax()
    high_pos = int(window.index.get_loc(high_idx))
    if high_pos >= len(window) - trend_lookback_days - 5:
        return None

    post_high = window.iloc[high_pos + 1 :].copy()
    if len(post_high) < trend_lookback_days + 5:
        return None

    low_idx = post_high["Low"].idxmin()
    low_pos = int(window.index.get_loc(low_idx))
    if low_pos <= high_pos or low_pos >= len(window) - trend_lookback_days:
        return None

    half_year_high = float(window.loc[high_idx, "High"])
    subsequent_low = float(window.loc[low_idx, "Low"])
    latest_close = float(window["Close"].iloc[-1])
    if half_year_high <= 0 or subsequent_low <= 0 or latest_close <= 0:
        return None

    drawdown = (half_year_high - subsequent_low) / half_year_high
    if drawdown < min_drawdown:
        return None

    bottom_ok, bottom_stats = _has_bottom_base(window, low_pos=low_pos, subsequent_low=subsequent_low)
    if not bottom_ok:
        return None

    close_series = window["Close"]
    trend_reference = float(close_series.iloc[-(trend_lookback_days + 1)])
    recent_trend_pct = ((latest_close / trend_reference) - 1.0) * 100 if trend_reference > 0 else 0.0
    recovery_from_bottom_pct = ((latest_close / subsequent_low) - 1.0) * 100
    recover_to_high_pct = ((latest_close / half_year_high) - 1.0) * 100

    if recent_trend_pct <= 0 or recovery_from_bottom_pct < BOWL_MIN_RECOVERY_FROM_BOTTOM * 100:
        return None

    ma5 = float(close_series.rolling(5).mean().iloc[-1])
    ma20_series = close_series.rolling(20).mean()
    ma20 = float(ma20_series.iloc[-1])
    ma20_prev = float(ma20_series.iloc[-6]) if len(ma20_series.dropna()) >= 6 and pd.notna(ma20_series.iloc[-6]) else ma20
    ma20_slope_pct = ((ma20 / ma20_prev) - 1.0) * 100 if ma20_prev > 0 else 0.0
    if latest_close < ma5 or latest_close < ma20 * 0.96:
        return None

    volume_signal = _find_recent_volume_signal(
        window,
        volume_lookback_days=volume_lookback_days,
        signal_window_days=volume_signal_window_days,
        volume_multiplier=volume_multiplier,
    )
    if not volume_signal:
        return None

    recent = window.tail(max(10, volume_signal_window_days + volume_lookback_days // 2)).copy()
    up_days = recent[recent["Close"] >= recent["Open"]]
    down_days = recent[recent["Close"] < recent["Open"]]
    up_volume_avg = float(up_days["Volume"].mean()) if not up_days.empty else 0.0
    down_volume_avg = float(down_days["Volume"].mean()) if not down_days.empty else 0.0
    up_down_volume_ratio = _safe_ratio(up_volume_avg, down_volume_avg) if down_volume_avg > 0 else (1.0 if up_volume_avg > 0 else 0.0)
    if up_down_volume_ratio < 0.9:
        return None

    avg_volume_short = float(window["Volume"].tail(volume_signal_window_days).mean())

    left_leg_days = low_pos - high_pos
    right_leg_days = len(window) - 1 - low_pos
    shape_balance = min(left_leg_days, right_leg_days) / max(left_leg_days, right_leg_days)
    structure_score = min(30.0, shape_balance * 30.0)
    drawdown_score = min(20.0, (drawdown - min_drawdown) / 0.25 * 20.0 + 8.0)
    recovery_score = min(25.0, recovery_from_bottom_pct / 35.0 * 25.0)
    trend_score = min(15.0, max(0.0, recent_trend_pct / 12.0 * 15.0) + (5.0 if ma20_slope_pct >= 0 else 0.0))
    volume_ratio = float(volume_signal["volume_signal_ratio"])
    volume_score = min(25.0, (volume_ratio - volume_multiplier) / max(volume_multiplier, 0.1) * 18.0 + 12.0)
    score = round(max(0.0, min(100.0, structure_score + drawdown_score + recovery_score + trend_score + volume_score)), 1)

    positive_reasons = [
        f"近 {lookback_days} 日高點後最大跌幅 {drawdown * 100:.1f}%，符合先跌出底部的條件",
        f"低檔區停留 {bottom_stats['bottom_days']} 天、橫跨 {bottom_stats['bottom_span_days']} 天，排除單日急彈",
        f"低點後反彈 {recovery_from_bottom_pct:.1f}%，近 {trend_lookback_days} 日再上漲 {recent_trend_pct:.1f}%",
        f"{volume_signal['volume_signal_date']} 放量上漲 {volume_ratio:.2f}x，漲幅 {volume_signal['volume_signal_price_change_pct']:.1f}%",
    ]
    if up_down_volume_ratio >= 1.0:
        positive_reasons.append(f"近期紅K日均量高於黑K日 {up_down_volume_ratio:.2f}x")

    caution_reasons = []
    if recover_to_high_pct > -5.0:
        caution_reasons.append("已接近半年高點，追價風險提高")
    if ma20_slope_pct < 0:
        caution_reasons.append("20MA 仍未明顯上彎")

    return {
        "matched": True,
        "score": score,
        "half_year_high": round(half_year_high, 2),
        "half_year_high_date": _date_text(high_idx),
        "subsequent_low": round(subsequent_low, 2),
        "subsequent_low_date": _date_text(low_idx),
        "drawdown_pct": round(drawdown * 100, 2),
        "latest_close": round(latest_close, 2),
        "recovery_from_bottom_pct": round(recovery_from_bottom_pct, 2),
        "recover_to_high_pct": round(recover_to_high_pct, 2),
        "avg_volume_short": round(avg_volume_short),
        "avg_volume_long": round(volume_signal["volume_signal_avg_volume_20d"]),
        "volume_ratio": round(volume_ratio, 2),
        "volume_lookback_days": int(volume_lookback_days),
        "volume_signal_window_days": int(volume_signal_window_days),
        "volume_multiplier": round(volume_multiplier, 2),
        "volume_signal_date": volume_signal["volume_signal_date"],
        "volume_signal_volume": volume_signal["volume_signal_volume"],
        "volume_signal_avg_volume_20d": volume_signal["volume_signal_avg_volume_20d"],
        "volume_signal_ratio": volume_signal["volume_signal_ratio"],
        "volume_signal_price_change_pct": volume_signal["volume_signal_price_change_pct"],
        "days_since_volume_signal": volume_signal["days_since_volume_signal"],
        "up_down_volume_ratio": round(up_down_volume_ratio, 2),
        "recent_trend_pct": round(recent_trend_pct, 2),
        "ma20_slope_pct": round(ma20_slope_pct, 2),
        "left_leg_days": int(left_leg_days),
        "right_leg_days": int(right_leg_days),
        "bottom_days": int(bottom_stats["bottom_days"]),
        "bottom_span_days": int(bottom_stats["bottom_span_days"]),
        "positive_reasons": positive_reasons[:4],
        "caution_reasons": caution_reasons[:4],
    }


def strategy_bowl_bottom_volume(df: pd.DataFrame, **kwargs) -> bool:
    setup = analyze_bowl_bottom_volume_candidate(df, **kwargs)
    return bool(setup and setup.get("matched"))
