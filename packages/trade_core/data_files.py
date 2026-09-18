from __future__ import annotations


CORE_DB_FILES = [
    "stocks.db",
    "company_links.db",
    "market_map.db",
    "active_etf_history.db",
    "broker_daily_trades.db",
]

CACHE_DB_FILES = [
    "price_cache.db",
    "revenue_cache.db",
    "chip_cache.db",
    "ui_persistent_cache.db",
    "api_jobs.db",
]

DATA_CONFIG_FILES = [
    "industry_theme_overrides.csv",
    "short_term_broker_tags.csv",
]

ALL_DB_FILES = CORE_DB_FILES + CACHE_DB_FILES
