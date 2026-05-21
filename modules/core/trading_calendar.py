from __future__ import annotations

from functools import lru_cache

import pandas as pd

from modules.data_sources.market_watch import fetch_tpex_daily_quotes, fetch_twse_daily_quotes


@lru_cache(maxsize=256)
def _has_market_data(trade_date_text):
    try:
        twse_df = fetch_twse_daily_quotes(trade_date_text)
    except Exception:
        twse_df = pd.DataFrame()
    try:
        tpex_df = fetch_tpex_daily_quotes(trade_date_text)
    except Exception:
        tpex_df = pd.DataFrame()
    return (not twse_df.empty) or (not tpex_df.empty)


def resolve_recent_trade_date(requested_date, max_lookback_days=14):
    requested_ts = pd.to_datetime(requested_date)
    requested_text = requested_ts.strftime("%Y-%m-%d")

    for offset in range(max_lookback_days + 1):
        probe_ts = requested_ts - pd.Timedelta(days=offset)
        probe_text = probe_ts.strftime("%Y-%m-%d")
        if _has_market_data(probe_text):
            return {
                "requested_date": requested_text,
                "effective_date": probe_ts.date(),
                "effective_date_text": probe_text,
                "used_fallback": probe_text != requested_text,
            }

    fallback_ts = requested_ts
    while fallback_ts.weekday() >= 5:
        fallback_ts -= pd.Timedelta(days=1)

    return {
        "requested_date": requested_text,
        "effective_date": fallback_ts.date(),
        "effective_date_text": fallback_ts.strftime("%Y-%m-%d"),
        "used_fallback": fallback_ts.strftime("%Y-%m-%d") != requested_text,
    }


def resolve_trade_dates_in_range(start_date, end_date, max_lookback_days=14):
    start_ts = pd.to_datetime(start_date)
    end_ts = pd.to_datetime(end_date)
    if start_ts > end_ts:
        start_ts, end_ts = end_ts, start_ts

    resolved = []
    for current_ts in pd.date_range(start_ts, end_ts, freq="D"):
        current_text = current_ts.strftime("%Y-%m-%d")
        if not _has_market_data(current_text):
            continue
        resolved.append(
            {
                "requested_date": current_text,
                "effective_date": current_ts.date(),
                "effective_date_text": current_text,
                "used_fallback": False,
            }
        )
    return resolved
