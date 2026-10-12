CREATE TABLE IF NOT EXISTS daily_signals (
  signal_date TEXT NOT NULL, stock_id TEXT NOT NULL, strategy TEXT NOT NULL,
  price REAL NOT NULL, change_pct REAL, volume_ratio REAL,
  distance_to_high_pct REAL, is_new INTEGER NOT NULL,
  calculated_at TEXT NOT NULL,
  PRIMARY KEY(signal_date,stock_id,strategy)
);
CREATE INDEX IF NOT EXISTS idx_daily_signals_date_new ON daily_signals(signal_date,is_new);
