CREATE TABLE IF NOT EXISTS research_source_fetches (
    source_key TEXT NOT NULL,
    market TEXT,
    requested_date TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ok','empty','error')),
    row_count INTEGER NOT NULL DEFAULT 0 CHECK(row_count >= 0),
    content_sha256 TEXT,
    error TEXT,
    PRIMARY KEY (source_key, market, requested_date)
);

CREATE TABLE IF NOT EXISTS research_source_fetch_attempts (
    attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT NOT NULL,
    market TEXT,
    requested_date TEXT NOT NULL,
    source_url TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ok','empty','error')),
    row_count INTEGER NOT NULL DEFAULT 0,
    content_sha256 TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_fetch_attempts_key
    ON research_source_fetch_attempts(source_key, market, requested_date, fetched_at);

CREATE TABLE IF NOT EXISTS research_price_daily (
    market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
    stock_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open REAL NOT NULL CHECK(open > 0),
    high REAL NOT NULL CHECK(high > 0),
    low REAL NOT NULL CHECK(low > 0),
    close REAL NOT NULL CHECK(close > 0),
    volume_shares INTEGER NOT NULL CHECK(volume_shares > 0),
    adjusted_close REAL,
    adjustment_status TEXT NOT NULL DEFAULT 'unverified',
    source_url TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (market, stock_id, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_research_price_date ON research_price_daily(trade_date, market);

CREATE TABLE IF NOT EXISTS research_ownership_weekly_meta (
    stock_id TEXT NOT NULL,
    report_date TEXT NOT NULL,
    source_url TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    published_at TEXT,
    publication_status TEXT NOT NULL CHECK(publication_status IN ('first_observed','verified','unverified_archive')),
    tier_count INTEGER NOT NULL,
    total_shares INTEGER,
    valid INTEGER NOT NULL CHECK(valid IN (0,1)),
    quality_reason TEXT,
    PRIMARY KEY (stock_id, report_date)
);
CREATE INDEX IF NOT EXISTS idx_research_ownership_date ON research_ownership_weekly_meta(report_date, valid);

CREATE TABLE IF NOT EXISTS research_security_status (
    market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
    stock_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    name_zh TEXT,
    security_type TEXT,
    listing_status TEXT,
    industry_code TEXT,
    issued_common_shares INTEGER,
    source_url TEXT NOT NULL,
    published_at TEXT,
    PRIMARY KEY (market, stock_id, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_research_security_lookup ON research_security_status(market, stock_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS research_corporate_actions (
    market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
    stock_id TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    action_type TEXT NOT NULL,
    cash_dividend REAL,
    stock_dividend_ratio REAL,
    reference_price REAL,
    source_url TEXT NOT NULL,
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (market, stock_id, ex_date, action_type)
);
CREATE INDEX IF NOT EXISTS idx_research_actions_ex_date ON research_corporate_actions(ex_date, market);

CREATE TABLE IF NOT EXISTS research_corporate_action_evidence (
    market TEXT NOT NULL,
    stock_id TEXT NOT NULL,
    ex_date TEXT NOT NULL,
    action_type TEXT NOT NULL,
    previous_reference_close REAL,
    raw_json TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    adjustment_verified INTEGER NOT NULL DEFAULT 0 CHECK(adjustment_verified IN (0,1)),
    PRIMARY KEY (market, stock_id, ex_date, action_type),
    FOREIGN KEY (market, stock_id, ex_date, action_type)
      REFERENCES research_corporate_actions(market, stock_id, ex_date, action_type)
);

CREATE TABLE IF NOT EXISTS research_security_lifecycle (
    market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
    stock_id TEXT NOT NULL,
    listed_at TEXT,
    delisted_at TEXT,
    name_zh TEXT,
    security_type TEXT NOT NULL DEFAULT 'ordinary_company_candidate',
    issued_common_shares INTEGER,
    listing_source_url TEXT,
    delisting_source_url TEXT,
    first_seen_at TEXT NOT NULL,
    validation_status TEXT NOT NULL DEFAULT 'partial_history',
    PRIMARY KEY (market, stock_id)
);
CREATE INDEX IF NOT EXISTS idx_research_lifecycle_dates ON research_security_lifecycle(market, listed_at, delisted_at);

CREATE TABLE IF NOT EXISTS research_security_delisting_events (
    market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
    stock_id TEXT NOT NULL,
    delisted_at TEXT NOT NULL,
    name_zh TEXT,
    source_url TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (market, stock_id, delisted_at)
);

-- Deliberately empty until the complete event chain and open/close factors are audited.
-- A TWSE/TPEx reference price or Yahoo cached bar alone cannot fill this table.
CREATE TABLE IF NOT EXISTS research_verified_adjusted_prices (
    market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
    stock_id TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    adjusted_open REAL NOT NULL CHECK(adjusted_open > 0),
    adjusted_close REAL NOT NULL CHECK(adjusted_close > 0),
    adjustment_method TEXT NOT NULL,
    verification_evidence_url TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    PRIMARY KEY (market, stock_id, trade_date)
);

CREATE TABLE IF NOT EXISTS research_quality_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    checked_at TEXT NOT NULL,
    first_week TEXT,
    last_week TEXT,
    report_count INTEGER NOT NULL,
    valid_report_count INTEGER NOT NULL,
    archived_report_count INTEGER NOT NULL,
    first_observed_count INTEGER NOT NULL,
    price_rows INTEGER NOT NULL,
    adjusted_price_rows INTEGER NOT NULL,
    notes TEXT NOT NULL
);
