from __future__ import annotations

import pandas as pd


MAX_5D_GAIN_PCT = 8.0
MAX_10D_GAIN_PCT = 15.0
MIN_TODAY_GAIN_PCT = 2.0
MAX_TODAY_GAIN_PCT = 7.0
VOLUME_MA_PERIOD = 20
MIN_VOLUME_RATIO = 1.3
QUIET_VOLUME_DAYS = 3
CONSOLIDATION_DAYS = 20
MAX_RANGE_WIDTH_PCT = 15.0
BREAKOUT_DAYS = 10
MIN_CLOSE_POSITION = 0.7


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


def _safe_pct_change(current: float, previous: float) -> float | None:
    if previous <= 0:
        return None
    return (current / previous - 1.0) * 100.0


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _volume_ratio_at(window: pd.DataFrame, pos: int, *, volume_ma_period: int) -> float | None:
    if pos < volume_ma_period:
        return None
    avg_volume = float(window["Volume"].iloc[pos - volume_ma_period : pos].mean())
    return _safe_ratio(float(window["Volume"].iloc[pos]), avg_volume)


def analyze_initial_rise_candidate(
    df: pd.DataFrame,
    *,
    max_5d_gain_pct: float = MAX_5D_GAIN_PCT,
    max_10d_gain_pct: float = MAX_10D_GAIN_PCT,
    min_today_gain_pct: float = MIN_TODAY_GAIN_PCT,
    max_today_gain_pct: float = MAX_TODAY_GAIN_PCT,
    volume_ma_period: int = VOLUME_MA_PERIOD,
    min_volume_ratio: float = MIN_VOLUME_RATIO,
    quiet_volume_days: int = QUIET_VOLUME_DAYS,
    consolidation_days: int = CONSOLIDATION_DAYS,
    max_range_width_pct: float = MAX_RANGE_WIDTH_PCT,
    breakout_days: int = BREAKOUT_DAYS,
    min_close_position: float = MIN_CLOSE_POSITION,
    stock_id: str | None = None,
    as_of_date: str | None = None,
) -> dict[str, object] | None:
    max_5d_gain_pct = float(max_5d_gain_pct)
    max_10d_gain_pct = float(max_10d_gain_pct)
    min_today_gain_pct = float(min_today_gain_pct)
    max_today_gain_pct = float(max_today_gain_pct)
    volume_ma_period = max(2, int(volume_ma_period))
    min_volume_ratio = max(0.1, float(min_volume_ratio))
    quiet_volume_days = max(1, int(quiet_volume_days))
    consolidation_days = max(5, int(consolidation_days))
    max_range_width_pct = max(0.1, float(max_range_width_pct))
    breakout_days = max(2, int(breakout_days))
    min_close_position = max(0.0, min(1.0, float(min_close_position)))
    required_length = max(
        volume_ma_period + quiet_volume_days + 1,
        consolidation_days + 1,
        breakout_days + 1,
        12,
    )
    cleaned = _clean_ohlcv(df, required_length=required_length)
    if cleaned is None:
        return None

    if as_of_date:
        cleaned = cleaned.loc[:pd.to_datetime(as_of_date)]
        if len(cleaned) < required_length:
            return None

    window = cleaned.copy()
    latest = window.iloc[-1]
    previous = window.iloc[-2]
    latest_close = float(latest["Close"])
    previous_close = float(previous["Close"])
    latest_open = float(latest["Open"])
    latest_high = float(latest["High"])
    latest_low = float(latest["Low"])
    latest_volume = float(latest["Volume"])

    today_return_pct = _safe_pct_change(latest_close, previous_close)
    if today_return_pct is None:
        return None

    pre_5d_gain_pct = _safe_pct_change(previous_close, float(window["Close"].iloc[-7])) if len(window) >= 7 else None
    pre_10d_gain_pct = _safe_pct_change(previous_close, float(window["Close"].iloc[-12])) if len(window) >= 12 else None
    avg_volume = float(window["Volume"].iloc[-(volume_ma_period + 1) : -1].mean())
    volume_ratio_today = _safe_ratio(latest_volume, avg_volume) or 0.0

    previous_volume_ratios = []
    for pos in range(len(window) - quiet_volume_days - 1, len(window) - 1):
        ratio = _volume_ratio_at(window, pos, volume_ma_period=volume_ma_period)
        if ratio is not None:
            previous_volume_ratios.append(ratio)
    max_previous_volume_ratio = max(previous_volume_ratios) if previous_volume_ratios else None

    consolidation_window = window.iloc[-(consolidation_days + 1) : -1]
    highest_high = float(consolidation_window["High"].max())
    lowest_low = float(consolidation_window["Low"].min())
    range_width_pct = _safe_pct_change(highest_high, lowest_low)

    breakout_window = window.iloc[-(breakout_days + 1) : -1]
    breakout_close = float(breakout_window["Close"].max())
    breakout_confirmed = latest_close >= breakout_close

    candle_range = latest_high - latest_low
    close_position = (latest_close - latest_low) / candle_range if candle_range > 0 else 1.0
    bullish_candle = latest_close > latest_open

    pre_gain_ok = (
        pre_5d_gain_pct is not None
        and pre_10d_gain_pct is not None
        and pre_5d_gain_pct < max_5d_gain_pct
        and pre_10d_gain_pct < max_10d_gain_pct
    )
    today_gain_ok = min_today_gain_pct <= today_return_pct <= max_today_gain_pct
    volume_expanded = volume_ratio_today >= min_volume_ratio
    quiet_before = bool(previous_volume_ratios) and all(ratio < min_volume_ratio for ratio in previous_volume_ratios)
    consolidation_ok = range_width_pct is not None and range_width_pct <= max_range_width_pct
    candle_ok = close_position >= min_close_position and bullish_candle
    matched = bool(
        pre_gain_ok
        and today_gain_ok
        and volume_expanded
        and quiet_before
        and consolidation_ok
        and candle_ok
    )

    score = 0.0
    score += 18.0 if pre_gain_ok else 0.0
    score += min(18.0, max(0.0, (today_return_pct - min_today_gain_pct) / max(max_today_gain_pct - min_today_gain_pct, 0.1) * 18.0))
    score += min(24.0, max(0.0, (volume_ratio_today - min_volume_ratio) / max(min_volume_ratio, 0.1) * 24.0 + (8.0 if volume_expanded else 0.0)))
    score += 15.0 if quiet_before else 0.0
    score += min(15.0, max(0.0, (max_range_width_pct - (range_width_pct or max_range_width_pct)) / max(max_range_width_pct, 0.1) * 15.0))
    score += 10.0 if candle_ok else 0.0
    score = round(max(0.0, min(100.0, score)), 1)

    positive_reasons = []
    caution_reasons = []
    if pre_gain_ok:
        positive_reasons.append(f"前期未大漲：前5日 {pre_5d_gain_pct:.1f}%，前10日 {pre_10d_gain_pct:.1f}%")
    else:
        caution_reasons.append("前期漲幅過大或資料不足")
    if today_gain_ok:
        positive_reasons.append(f"今日起漲 {today_return_pct:.1f}%")
    else:
        caution_reasons.append(f"今日漲幅 {today_return_pct:.1f}% 不在 {min_today_gain_pct:.1f}%~{max_today_gain_pct:.1f}%")
    if volume_expanded and quiet_before:
        positive_reasons.append(f"今日量比 {volume_ratio_today:.2f}x，且前 {quiet_volume_days} 日未放量")
    elif volume_expanded:
        caution_reasons.append(f"今日量比 {volume_ratio_today:.2f}x，但前面已有放量")
    else:
        caution_reasons.append(f"今日量比 {volume_ratio_today:.2f}x 未達 {min_volume_ratio:.2f}x")
    if consolidation_ok:
        positive_reasons.append(f"{consolidation_days}日整理寬度 {range_width_pct:.1f}%，前期走勢仍在可接受整理範圍")
    else:
        if not consolidation_ok:
            caution_reasons.append(f"{consolidation_days}日區間寬度 {(range_width_pct or 0.0):.1f}% 過大")
    if not candle_ok:
        caution_reasons.append("K棒收盤位置不足或不是紅K")

    return {
        "matched": matched,
        "symbol": stock_id,
        "as_of_date": _date_text(window.index[-1]),
        "score": score,
        "latest_close": round(latest_close, 2),
        "today_return_pct": round(today_return_pct, 2),
        "pre_5d_gain_pct": round(pre_5d_gain_pct, 2) if pre_5d_gain_pct is not None else None,
        "pre_10d_gain_pct": round(pre_10d_gain_pct, 2) if pre_10d_gain_pct is not None else None,
        "latest_volume": round(latest_volume),
        "avg_volume_20d": round(avg_volume),
        "volume_ratio_today": round(volume_ratio_today, 2),
        "max_previous_volume_ratio": round(max_previous_volume_ratio, 2) if max_previous_volume_ratio is not None else None,
        "quiet_volume_days": quiet_volume_days,
        "consolidation_days": consolidation_days,
        "range_width_pct": round(range_width_pct, 2) if range_width_pct is not None else None,
        "breakout_days": breakout_days,
        "breakout_close": round(breakout_close, 2),
        "breakout_confirmed": breakout_confirmed,
        "close_position": round(close_position, 2),
        "bullish_candle": bullish_candle,
        "pre_gain_ok": pre_gain_ok,
        "today_gain_ok": today_gain_ok,
        "volume_expanded": volume_expanded,
        "quiet_before": quiet_before,
        "consolidation_ok": consolidation_ok,
        "candle_ok": candle_ok,
        "positive_reasons": positive_reasons[:5],
        "caution_reasons": caution_reasons[:5],
    }


def strategy_initial_rise(df: pd.DataFrame, **kwargs) -> bool:
    setup = analyze_initial_rise_candidate(df, **kwargs)
    return bool(setup and setup.get("matched"))
