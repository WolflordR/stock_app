import streamlit as st

from modules.etf.active_etf_watch import build_active_etf_detail_bundle
from modules.etf.active_etf_watch import build_active_etf_overview_bundle
from modules.data_sources.chip_data import build_consecutive_institutional_rankings, build_institutional_rankings
from modules.industry.company_links_db import build_theme_coverage_report
from modules.industry.industry_rotation import build_industry_rotation_bundle
from modules.industry.industry_rotation import build_homepage_industry_flow_bundle
from modules.data_sources.market_watch import build_disposition_watchlist, build_market_watchlists
from modules.news.news_analysis import build_news_analysis_bundle
from modules.data_sources.revenue_data import build_revenue_momentum_rankings
from modules.home.home_page_data import build_homepage_schedule_payload
from modules.core.persistent_cache import load_or_compute_persistent_cache


def _persistent(namespace, ttl_seconds, key_parts, builder):
    return load_or_compute_persistent_cache(namespace, key_parts, ttl_seconds, builder)


@st.cache_data(ttl=3600, show_spinner=False)
def load_homepage_revenue_momentum(
    cache_version,
    cache_date,
    top_n,
    min_yoy_pct,
    min_mom_pct,
    min_cumulative_yoy_pct,
    required_consecutive_months,
    exclude_february_from_average,
):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "homepage_revenue_momentum",
        3600,
        (cache_version, cache_date, top_n, min_yoy_pct, min_mom_pct, min_cumulative_yoy_pct, required_consecutive_months, exclude_february_from_average),
        lambda: build_revenue_momentum_rankings(
            top_n=top_n,
            min_yoy_pct=min_yoy_pct,
            min_mom_pct=min_mom_pct,
            min_cumulative_yoy_pct=min_cumulative_yoy_pct,
            required_consecutive_months=required_consecutive_months,
            exclude_february_from_average=exclude_february_from_average,
        ),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_homepage_market_watch(cache_version, cache_date, trade_date, top_n):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "homepage_market_watch",
        1800,
        (cache_version, cache_date, str(trade_date), top_n),
        lambda: build_market_watchlists(trade_date, top_n=top_n),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_homepage_disposition_watch(cache_version, cache_date, trade_date):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "homepage_disposition_watch",
        1800,
        (cache_version, cache_date, str(trade_date)),
        lambda: build_disposition_watchlist(trade_date),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_news_analysis(cache_version, cache_date, trade_date, industry_count, headlines_per_industry, us_news_items):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "news_analysis",
        1800,
        (cache_version, cache_date, str(trade_date), industry_count, headlines_per_industry, us_news_items),
        lambda: build_news_analysis_bundle(
            trade_date,
            industry_count=industry_count,
            headlines_per_industry=headlines_per_industry,
            us_news_items=us_news_items,
        ),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_homepage_institutional_data(cache_version, cache_date, trade_date, streak_options, top_n):
    _ = cache_version
    _ = cache_date

    def _builder():
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

    return _persistent(
        "homepage_institutional_data",
        1800,
        (cache_version, cache_date, str(trade_date), tuple(streak_options), top_n),
        _builder,
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_research_institutional_signals(cache_version, cache_date, trade_date):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "research_institutional_signals",
        1800,
        (cache_version, cache_date, str(trade_date)),
        lambda: {
            "trust_3d": build_consecutive_institutional_rankings(trade_date, "投信", consecutive_days=3, top_n=30),
            "trust_5d": build_consecutive_institutional_rankings(trade_date, "投信", consecutive_days=5, top_n=30),
            "foreign_3d": build_consecutive_institutional_rankings(trade_date, "外資", consecutive_days=3, top_n=30),
        },
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_industry_rotation_data(cache_version, cache_date, trade_date, history_trade_days):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "industry_rotation_data",
        1800,
        (cache_version, cache_date, str(trade_date), history_trade_days),
        lambda: build_industry_rotation_bundle(trade_date, history_trade_days=history_trade_days),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_homepage_industry_flow_data(cache_version, cache_date, trade_date, history_trade_days):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "homepage_industry_flow_data",
        1800,
        (cache_version, cache_date, str(trade_date), history_trade_days),
        lambda: build_homepage_industry_flow_bundle(trade_date, history_trade_days=history_trade_days),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_theme_coverage_report(cache_version, cache_date):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "theme_coverage_report",
        1800,
        (cache_version, cache_date),
        build_theme_coverage_report,
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_active_etf_overview_data(cache_version, cache_date, top_n):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "active_etf_overview_data",
        1800,
        (cache_version, cache_date, top_n),
        lambda: build_active_etf_overview_bundle(top_n=top_n),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_active_etf_detail_data(cache_version, cache_date, code):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "active_etf_detail_data",
        1800,
        (cache_version, cache_date, str(code).strip().upper()),
        lambda: build_active_etf_detail_bundle(code),
    )


@st.cache_data(ttl=1800, show_spinner=False)
def load_homepage_schedule_data(cache_version, cache_date):
    _ = cache_version
    _ = cache_date
    return _persistent(
        "homepage_schedule_data",
        1800,
        (cache_version, cache_date),
        build_homepage_schedule_payload,
    )
