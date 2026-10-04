from __future__ import annotations

import pandas as pd


MA_SHORT = 5
MA_LONG = 10
MOMENTUM_LOOKBACK = 5
MA_SLOPE_LOOKBACK = 3
VOLUME_MA_PERIOD = 20
VOLUME_MULTIPLIER = 2.0
VOLUME_LOOKBACK = 3


def _clean_ohlcv(df: pd.DataFrame, *, required_length: int) -> pd.DataFrame | None:
    if df is None or len(df) < required_length:
        return None
    required_columns = ["Open", "High", "Low", "Close", "Volume"]
    if any(column not in df.columns for column in required_columns):
        return None
    cleaned = df[required_columns].copy()
    for column in required_columns:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")
    cleaned = cleaned.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
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
    return (current / previous - 1.0) * 100


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _find_recent_volume_expansion(
    window: pd.DataFrame,
    *,
    volume_ma_period: int,
    volume_lookback: int,
    volume_multiplier: float,
) -> dict[str, object] | None:
    volume_ma_period = max(2, int(volume_ma_period))
    volume_lookback = max(1, int(volume_lookback))
    volume_multiplier = max(0.1, float(volume_multiplier))
    candidates: list[dict[str, object]] = []
    start_pos = max(1, len(window) - volume_lookback)

    for pos in range(start_pos, len(window)):
        if pos < volume_ma_period:
            continue
        avg_volume = float(window["Volume"].iloc[pos - volume_ma_period : pos].mean())
        current_volume = float(window["Volume"].iloc[pos])
        previous_close = float(window["Close"].iloc[pos - 1])
        current_close = float(window["Close"].iloc[pos])
        volume_ratio = _safe_ratio(current_volume, avg_volume) or 0.0
        price_change_pct = _safe_pct_change(current_close, previous_close) or 0.0
        if volume_ratio >= volume_multiplier:
            candidates.append(
                {
                    "date": _date_text(window.index[pos]),
                    "pos": pos,
                    "volume": round(current_volume),
                    "avg_volume": round(avg_volume),
                    "volume_ratio": round(volume_ratio, 2),
                    "price_change_pct": round(price_change_pct, 2),
                    "price_up_on_signal": current_close > previous_close,
                    "days_since_signal": len(window) - 1 - pos,
                }
            )

    if not candidates:
        return None
    return max(candidates, key=lambda item: float(item["volume_ratio"]))


def analyze_momentum_volume_candidate(
    df: pd.DataFrame,
    *,
    ma_short: int = MA_SHORT,
    ma_long: int = MA_LONG,
    momentum_lookback: int = MOMENTUM_LOOKBACK,
    ma_slope_lookback: int = MA_SLOPE_LOOKBACK,
    volume_ma_period: int = VOLUME_MA_PERIOD,
    volume_multiplier: float = VOLUME_MULTIPLIER,
    volume_lookback: int = VOLUME_LOOKBACK,
    stock_id: str | None = None,
    as_of_date: str | None = None,
) -> dict[str, object] | None:
    ma_short = max(1, int(ma_short))
    ma_long = max(ma_short + 1, int(ma_long))
    momentum_lookback = max(1, int(momentum_lookback))
    ma_slope_lookback = max(1, int(ma_slope_lookback))
    volume_ma_period = max(2, int(volume_ma_period))
    volume_multiplier = max(0.1, float(volume_multiplier))
    volume_lookback = max(1, int(volume_lookback))
    required_length = max(ma_long + ma_slope_lookback + 1, momentum_lookback + 1, volume_ma_period + volume_lookback + 1)
    cleaned = _clean_ohlcv(df, required_length=required_length)
    if cleaned is None:
        return None

    if as_of_date:
        cleaned = cleaned.loc[:pd.to_datetime(as_of_date)]
        if len(cleaned) < required_length:
            return None

    window = cleaned.copy()
    close = window["Close"]
    volume = window["Volume"]
    ma_short_series = close.rolling(ma_short).mean()
    ma_long_series = close.rolling(ma_long).mean()

    latest_close = float(close.iloc[-1])
    previous_close = float(close.iloc[-2])
    latest_volume = float(volume.iloc[-1])
    ma_short_value = float(ma_short_series.iloc[-1])
    ma_long_value = float(ma_long_series.iloc[-1])
    ma_short_prior = float(ma_short_series.iloc[-(ma_slope_lookback + 1)])
    close_lookback = float(close.iloc[-(momentum_lookback + 1)])
    volume_ma_today = float(volume.iloc[-(volume_ma_period + 1) : -1].mean())

    if any(pd.isna(value) for value in [ma_short_value, ma_long_value, ma_short_prior, volume_ma_today]):
        return None

    momentum_return_pct = _safe_pct_change(latest_close, close_lookback) or 0.0
    price_change_pct = _safe_pct_change(latest_close, previous_close) or 0.0
    ma_short_slope_pct = _safe_pct_change(ma_short_value, ma_short_prior) or 0.0
    volume_ratio_today = _safe_ratio(latest_volume, volume_ma_today) or 0.0
    recent_volume_ratios = []
    for pos in range(max(volume_ma_period, len(window) - volume_lookback), len(window)):
        avg_volume = float(volume.iloc[pos - volume_ma_period : pos].mean())
        recent_volume_ratios.append(_safe_ratio(float(volume.iloc[pos]), avg_volume) or 0.0)

    volume_signal = _find_recent_volume_expansion(
        window,
        volume_ma_period=volume_ma_period,
        volume_lookback=volume_lookback,
        volume_multiplier=volume_multiplier,
    )
    volume_confirmed = bool(volume_signal and volume_signal.get("price_up_on_signal"))
    momentum_up = (
        latest_close > ma_short_value
        and ma_short_value > ma_long_value
        and ma_short_value > ma_short_prior
        and momentum_return_pct > 0
    )
    price_up = latest_close > previous_close
    matched = bool(momentum_up and volume_confirmed and price_up)

    distance_from_ma_short = _safe_pct_change(latest_close, ma_short_value) or 0.0
    distance_from_ma_long = _safe_pct_change(latest_close, ma_long_value) or 0.0
    return_3d = _safe_pct_change(latest_close, float(close.iloc[-4])) if len(close) >= 4 else None
    return_10d = _safe_pct_change(latest_close, float(close.iloc[-11])) if len(close) >= 11 else None
    volume_ratio_max = max(recent_volume_ratios) if recent_volume_ratios else 0.0
    volume_ratio_avg = sum(recent_volume_ratios) / len(recent_volume_ratios) if recent_volume_ratios else 0.0

    score = 0.0
    score += min(30.0, max(0.0, momentum_return_pct / 8.0 * 30.0))
    score += min(20.0, max(0.0, ma_short_slope_pct / 5.0 * 20.0))
    score += min(30.0, max(0.0, (volume_ratio_max - volume_multiplier) / max(volume_multiplier, 0.1) * 30.0 + (10.0 if volume_confirmed else 0.0)))
    score += min(20.0, max(0.0, price_change_pct / 5.0 * 20.0))
    score = round(max(0.0, min(100.0, score)), 1)

    positive_reasons = []
    caution_reasons = []
    if momentum_up:
        positive_reasons.append(f"收盤站上 MA{ma_short}，且 MA{ma_short} > MA{ma_long}、{momentum_lookback}日報酬 {momentum_return_pct:.1f}%")
    else:
        caution_reasons.append("短線動能條件尚未全部成立")
    if volume_signal:
        signal_text = f"{volume_signal['date']} 量比 {float(volume_signal['volume_ratio']):.2f}x"
        if volume_signal.get("price_up_on_signal"):
            positive_reasons.append(f"{signal_text} 且爆量日收盤上漲 {float(volume_signal['price_change_pct']):.1f}%")
        else:
            caution_reasons.append(f"{signal_text} 但爆量日不是上漲日")
    else:
        caution_reasons.append(f"最近 {volume_lookback} 日沒有達到 {volume_multiplier:.1f} 倍量")
    if price_up:
        positive_reasons.append(f"判斷日收盤上漲 {price_change_pct:.1f}%")
    else:
        caution_reasons.append("判斷日收盤未高於前一日")

    signal_date = volume_signal.get("date") if volume_signal else None
    return {
        "matched": matched,
        "symbol": stock_id,
        "as_of_date": _date_text(window.index[-1]),
        "score": score,
        "latest_close": round(latest_close, 2),
        "price_change_pct": round(price_change_pct, 2),
        "ma_short": round(ma_short_value, 2),
        "ma_long": round(ma_long_value, 2),
        "ma_short_period": int(ma_short),
        "ma_long_period": int(ma_long),
        "momentum_return_pct": round(momentum_return_pct, 2),
        "latest_volume": round(latest_volume),
        "avg_volume": round(volume_ma_today),
        "volume_ratio_today": round(volume_ratio_today, 2),
        "volume_ratio_max": round(volume_ratio_max, 2),
        "volume_ratio_avg": round(volume_ratio_avg, 2),
        "volume_signal_date": signal_date,
        "volume_signal_volume": volume_signal.get("volume") if volume_signal else None,
        "volume_signal_avg_volume": volume_signal.get("avg_volume") if volume_signal else None,
        "volume_signal_ratio": volume_signal.get("volume_ratio") if volume_signal else None,
        "volume_signal_price_change_pct": volume_signal.get("price_change_pct") if volume_signal else None,
        "days_since_volume_signal": volume_signal.get("days_since_signal") if volume_signal else None,
        "momentum_up": momentum_up,
        "volume_confirmed": volume_confirmed,
        "price_up": price_up,
        "distance_from_ma_short_pct": round(distance_from_ma_short, 2),
        "distance_from_ma_long_pct": round(distance_from_ma_long, 2),
        "ma_short_slope_pct": round(ma_short_slope_pct, 2),
        "return_3d_pct": round(return_3d, 2) if return_3d is not None else None,
        "return_5d_pct": round(momentum_return_pct, 2),
        "return_10d_pct": round(return_10d, 2) if return_10d is not None else None,
        "positive_reasons": positive_reasons[:4],
        "caution_reasons": caution_reasons[:4],
    }


def strategy_momentum_volume(df: pd.DataFrame, **kwargs) -> bool:
    setup = analyze_momentum_volume_candidate(df, **kwargs)
    return bool(setup and setup.get("matched"))
