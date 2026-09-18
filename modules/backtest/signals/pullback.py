import pandas as pd


def analyze_strong_pullback_rebound_candidate(
    df,
    strong_lookback_days=20,
    min_pullback_pct=10.0,
    base_hold_days=3,
    low_price_volume_price_threshold=500.0,
    low_price_min_volume_lots=700.0,
):
    required_length = max(strong_lookback_days, base_hold_days, 20)
    if len(df) < required_length:
        return None

    close_series = pd.to_numeric(df["Close"], errors="coerce")
    high_series = pd.to_numeric(df["High"], errors="coerce")
    low_series = pd.to_numeric(df["Low"], errors="coerce")
    volume_series = pd.to_numeric(df["Volume"], errors="coerce")
    if close_series.isna().any() or high_series.isna().any() or low_series.isna().any() or volume_series.isna().any():
        return None

    current_close = float(close_series.iloc[-1])
    current_volume_shares = float(volume_series.iloc[-1])
    current_volume_lots = current_volume_shares / 1000.0
    recent_window = df.tail(strong_lookback_days)
    recent_high_reference = float(recent_window["High"].max())
    pullback_depth_pct = (recent_high_reference / current_close - 1.0) * 100 if current_close > 0 else 0.0
    base_window = df.tail(base_hold_days).copy()
    first_day_low = float(base_window["Low"].iloc[0])
    latest_close = float(base_window["Close"].iloc[-1])
    prior_close = float(base_window["Close"].iloc[-2])

    condition_a = pullback_depth_pct > min_pullback_pct
    condition_b = prior_close >= first_day_low and latest_close >= first_day_low
    condition_c = current_close > low_price_volume_price_threshold or current_volume_lots >= low_price_min_volume_lots

    positive_reasons = []
    caution_reasons = []

    if condition_a:
        positive_reasons.append(f"近{strong_lookback_days}日高點 {recent_high_reference:.2f}，目前已回檔 {pullback_depth_pct:.1f}%")
    else:
        caution_reasons.append(f"回檔深度不足，目前僅回檔 {pullback_depth_pct:.1f}%")

    if condition_b:
        positive_reasons.append(f"最近{base_hold_days}天收盤守住第一天低點 {first_day_low:.2f}")
    else:
        caution_reasons.append(f"昨天或今天收盤跌破防守低點 {first_day_low:.2f}")

    if condition_c:
        if current_close <= low_price_volume_price_threshold:
            positive_reasons.append(f"收盤 {current_close:.2f} 元，成交量 {current_volume_lots:,.0f} 張，達到低價股量能門檻")
        else:
            positive_reasons.append(f"收盤 {current_close:.2f} 元，高於低價股量能檢查門檻")
    else:
        caution_reasons.append(
            f"收盤 {current_close:.2f} 元屬低價股，但成交量僅 {current_volume_lots:,.0f} 張，低於 {low_price_min_volume_lots:,.0f} 張"
        )

    score = 0.0
    score += min(max(pullback_depth_pct / max(min_pullback_pct, 1.0), 0), 2.0) * 40
    score += 30 if condition_b else 0
    score += 30 if condition_c else 0
    score = round(min(score, 100.0), 1)

    return {
        "matched": condition_a and condition_b and condition_c,
        "score": score,
        "condition_a": condition_a,
        "condition_b": condition_b,
        "condition_c": condition_c,
        "pullback_depth_pct": round(pullback_depth_pct, 2),
        "recent_high_reference": round(recent_high_reference, 2),
        "first_day_low": round(first_day_low, 2),
        "prior_close": round(prior_close, 2),
        "latest_close": round(latest_close, 2),
        "latest_volume_lots": round(current_volume_lots, 2),
        "low_price_volume_price_threshold": float(low_price_volume_price_threshold),
        "low_price_min_volume_lots": float(low_price_min_volume_lots),
        "base_hold_days": int(base_hold_days),
        "positive_reasons": positive_reasons,
        "caution_reasons": caution_reasons,
    }


def strategy_strong_pullback_rebound(
    df,
    strong_lookback_days=20,
    min_pullback_pct=10.0,
    base_hold_days=3,
    low_price_volume_price_threshold=500.0,
    low_price_min_volume_lots=700.0,
):
    analysis = analyze_strong_pullback_rebound_candidate(
        df,
        strong_lookback_days=strong_lookback_days,
        min_pullback_pct=min_pullback_pct,
        base_hold_days=base_hold_days,
        low_price_volume_price_threshold=low_price_volume_price_threshold,
        low_price_min_volume_lots=low_price_min_volume_lots,
    )
    return analysis["matched"] if analysis else False


def analyze_high_price_pullback_candidate(
    df,
    lookback_days=20,
    eligible_symbol_set=None,
    stock_id=None,
    market_cap_rank_limit=50,
    min_drop_pct=15.0,
):
    required_length = max(int(lookback_days), 20)
    if len(df) < required_length:
        return None

    close_series = pd.to_numeric(df["Close"], errors="coerce")
    high_series = pd.to_numeric(df["High"], errors="coerce")
    if close_series.isna().any() or high_series.isna().any():
        return None

    current_close = float(close_series.iloc[-1])
    recent_window = df.tail(lookback_days)
    recent_high = float(recent_window["High"].max())
    if recent_high <= 0:
        return None

    pullback_depth_pct = (recent_high / current_close - 1.0) * 100 if current_close > 0 else 0.0
    normalized_stock_id = str(stock_id or "").strip().upper()
    normalized_code = normalized_stock_id.split(".")[0] if normalized_stock_id else ""
    eligible_symbol_set = {str(value).strip().upper() for value in (eligible_symbol_set or set()) if str(value).strip()}
    condition_a = bool(normalized_stock_id) and (
        normalized_stock_id in eligible_symbol_set or normalized_code in eligible_symbol_set
    )
    condition_b = pullback_depth_pct > min_drop_pct

    positive_reasons = []
    caution_reasons = []

    if condition_a:
        positive_reasons.append(f"屬於前 {int(market_cap_rank_limit)} 大市值名單")
    else:
        caution_reasons.append(f"不在前 {int(market_cap_rank_limit)} 大市值名單內")

    if condition_b:
        positive_reasons.append(f"距近{lookback_days}日高點 {recent_high:.2f} 已回檔 {pullback_depth_pct:.1f}%")
    else:
        caution_reasons.append(f"距近{lookback_days}日高點僅回檔 {pullback_depth_pct:.1f}%")

    score = 0.0
    score += 50 if condition_a else 0
    score += min(max(pullback_depth_pct / max(min_drop_pct, 1.0), 0), 2.0) * 50
    score = round(min(score, 100.0), 1)

    return {
        "matched": condition_a and condition_b,
        "score": score,
        "condition_a": condition_a,
        "condition_b": condition_b,
        "lookback_days": int(lookback_days),
        "market_cap_rank_limit": int(market_cap_rank_limit),
        "min_drop_pct": float(min_drop_pct),
        "recent_high_reference": round(recent_high, 2),
        "latest_close": round(current_close, 2),
        "pullback_depth_pct": round(pullback_depth_pct, 2),
        "positive_reasons": positive_reasons,
        "caution_reasons": caution_reasons,
    }


def strategy_high_price_pullback(
    df,
    lookback_days=20,
    eligible_symbol_set=None,
    stock_id=None,
    market_cap_rank_limit=50,
    min_drop_pct=15.0,
):
    analysis = analyze_high_price_pullback_candidate(
        df,
        lookback_days=lookback_days,
        eligible_symbol_set=eligible_symbol_set,
        stock_id=stock_id,
        market_cap_rank_limit=market_cap_rank_limit,
        min_drop_pct=min_drop_pct,
    )
    return analysis["matched"] if analysis else False
