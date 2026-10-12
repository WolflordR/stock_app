from __future__ import annotations


CORE_DB_FILES = [
    "stocks.db",
    "company_links.db",
    "sector_rotation.db",
    "company_events.db",
    "market_map.db",
    "active_etf_history.db",
    "broker_daily_trades.db",
    "chip_trends.db",
    "ownership_research.db",
]

CACHE_DB_FILES = [
    "price_cache.db",
    "revenue_cache.db",
    "financial_eps.db",
    "chip_cache.db",
    "ui_persistent_cache.db",
    "api_jobs.db",
    "watchlists.db",
    "dashboard_signals.db",
]

DATA_CONFIG_FILES = [
    "industry_theme_overrides.csv",
    "short_term_broker_tags.csv",
    "sector_rotation/taxonomy.csv",
    "sector_rotation/themes.csv",
    "sector_rotation/stock_seed.csv",
]

ALL_DB_FILES = CORE_DB_FILES + CACHE_DB_FILES
