import pandas as pd


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
