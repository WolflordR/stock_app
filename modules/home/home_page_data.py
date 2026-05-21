from modules.data_sources.chip_data import build_consecutive_institutional_rankings, build_institutional_rankings
from modules.research.research_transcript_data import DEFAULT_RESEARCH_COMPANIES, build_tracking_company_schedule_payload_map
from modules.data_sources.revenue_data import build_revenue_momentum_rankings


def build_homepage_range_scan_cache_key(
    cache_version,
    cache_date,
    trade_date,
    start_num,
    end_num,
    range_lookback_days,
    range_max_width_pct,
    range_volume_ratio,
    range_min_price_gain_pct,
    range_max_price_gain_pct,
    range_volume_sustain_days,
):
    return (
        cache_version,
        cache_date,
        str(trade_date),
        int(start_num),
        int(end_num),
        int(range_lookback_days),
        float(range_max_width_pct),
        float(range_volume_ratio),
        float(range_min_price_gain_pct),
        float(range_max_price_gain_pct),
        int(range_volume_sustain_days),
    )


def build_homepage_institutional_payload(trade_date, streak_options, top_n):
    def _safe_rankings(builder, *args):
        try:
            return builder(*args)
        except Exception:
            return None

    daily_institutional = {
        "foreign": _safe_rankings(build_institutional_rankings, trade_date, "外資", top_n),
        "total": _safe_rankings(build_institutional_rankings, trade_date, "三大法人", top_n),
    }
    institutional_results = {}
    for streak_days in streak_options:
        institutional_results[streak_days] = {
            "foreign": _safe_rankings(build_consecutive_institutional_rankings, trade_date, "外資", streak_days, top_n),
            "total": _safe_rankings(build_consecutive_institutional_rankings, trade_date, "三大法人", streak_days, top_n),
        }

    return {
        "daily": daily_institutional,
        "streaks": institutional_results,
    }


def build_homepage_daily_institutional_payload(trade_date, top_n):
    def _safe_rankings(builder, *args):
        try:
            return builder(*args)
        except Exception:
            return None

    return {
        "foreign": _safe_rankings(build_institutional_rankings, trade_date, "外資", top_n),
        "total": _safe_rankings(build_institutional_rankings, trade_date, "三大法人", top_n),
    }


def build_homepage_revenue_payload(state):
    return build_revenue_momentum_rankings(
        top_n=state["revenue_top_n"],
        min_yoy_pct=state["revenue_min_yoy_pct"],
        min_mom_pct=state["revenue_min_mom_pct"],
        min_cumulative_yoy_pct=state["revenue_min_cumulative_yoy_pct"],
        required_consecutive_months=state["revenue_required_consecutive_months"],
        exclude_february_from_average=state["revenue_exclude_february"],
        technology_only=True,
    )


def safe_sync_fallback(builder, *args, **kwargs):
    try:
        return builder(*args, **kwargs)
    except Exception:
        return None


def build_homepage_schedule_payload():
    return build_tracking_company_schedule_payload_map(tuple(DEFAULT_RESEARCH_COMPANIES[:7]), window_days=30)
