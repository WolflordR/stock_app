CREATE TABLE IF NOT EXISTS market_limit_stock_daily (
  market TEXT NOT NULL CHECK(market IN ('TWSE', 'TPEx')),
  trade_date TEXT NOT NULL,
  stock_id TEXT NOT NULL,
  name TEXT NOT NULL,
  direction TEXT NOT NULL CHECK(direction IN ('up', 'down')),
  close REAL NOT NULL,
  limit_price REAL NOT NULL,
  volume_shares INTEGER NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (market, trade_date, stock_id)
);
CREATE INDEX IF NOT EXISTS idx_market_limit_stock_date_direction
  ON market_limit_stock_daily(trade_date DESC, direction, market);

CREATE TABLE IF NOT EXISTS market_limit_detail_status (
  market TEXT NOT NULL CHECK(market IN ('TWSE', 'TPEx')),
  trade_date TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('complete', 'mismatch')),
  observed_up INTEGER NOT NULL,
  observed_down INTEGER NOT NULL,
  limit_source_url TEXT NOT NULL,
  quote_source_url TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (market, trade_date)
);
