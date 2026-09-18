import pandas as pd


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
