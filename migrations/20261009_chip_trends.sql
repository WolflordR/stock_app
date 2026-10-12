CREATE TABLE IF NOT EXISTS market_margin_short_daily (
      market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
      trade_date TEXT NOT NULL,
      margin_balance_lots INTEGER NOT NULL,
      margin_previous_lots INTEGER,
      margin_balance_thousand_twd INTEGER,
      margin_previous_thousand_twd INTEGER,
      short_balance_lots INTEGER NOT NULL,
      short_previous_lots INTEGER,
      source_url TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (market, trade_date)
    );
    CREATE INDEX IF NOT EXISTS idx_market_margin_date ON market_margin_short_daily(trade_date DESC, market);
    CREATE TABLE IF NOT EXISTS market_limit_daily (
      market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
      trade_date TEXT NOT NULL,
      limit_up_count INTEGER NOT NULL CHECK(limit_up_count >= 0),
      limit_down_count INTEGER NOT NULL CHECK(limit_down_count >= 0),
      source_url TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (market, trade_date)
    );
    CREATE INDEX IF NOT EXISTS idx_market_limit_date ON market_limit_daily(trade_date DESC, market);
    CREATE TABLE IF NOT EXISTS market_turnover_daily (
      market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
      trade_date TEXT NOT NULL,
      amount_twd INTEGER NOT NULL CHECK(amount_twd >= 0),
      source_url TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (market, trade_date)
    );
    CREATE INDEX IF NOT EXISTS idx_market_turnover_date ON market_turnover_daily(trade_date DESC, market);
    CREATE TABLE IF NOT EXISTS stock_margin_short_daily (
      market TEXT NOT NULL CHECK(market IN ('TWSE','TPEx')),
      stock_id TEXT NOT NULL,
      trade_date TEXT NOT NULL,
      margin_previous_lots INTEGER,
      margin_buy_lots INTEGER,
      margin_sell_lots INTEGER,
      margin_cash_repayment_lots INTEGER,
      margin_balance_lots INTEGER NOT NULL,
      short_previous_lots INTEGER,
      short_sell_lots INTEGER,
      short_buy_lots INTEGER,
      short_repayment_lots INTEGER,
      short_balance_lots INTEGER NOT NULL,
      margin_limit_lots INTEGER,
      short_limit_lots INTEGER,
      margin_usage_pct REAL,
      short_usage_pct REAL,
      source_url TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (market, stock_id, trade_date)
    );
    CREATE INDEX IF NOT EXISTS idx_stock_margin_stock_date ON stock_margin_short_daily(stock_id, trade_date DESC);
    CREATE TABLE IF NOT EXISTS stock_ownership_distribution_weekly (
      stock_id TEXT NOT NULL,
      report_date TEXT NOT NULL,
      tier INTEGER NOT NULL CHECK(tier BETWEEN 1 AND 17),
      holder_count INTEGER NOT NULL,
      shares INTEGER NOT NULL,
      reported_pct REAL,
      source_url TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (stock_id, report_date, tier)
    );
    CREATE INDEX IF NOT EXISTS idx_ownership_stock_date ON stock_ownership_distribution_weekly(stock_id, report_date DESC);
    CREATE TABLE IF NOT EXISTS chip_source_status (
      source TEXT PRIMARY KEY, last_success_date TEXT, last_success_at TEXT, last_error TEXT
    );
