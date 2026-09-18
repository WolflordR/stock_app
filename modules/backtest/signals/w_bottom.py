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
