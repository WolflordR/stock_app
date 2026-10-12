CREATE TABLE IF NOT EXISTS company_events (
  id TEXT PRIMARY KEY, stock_id TEXT NOT NULL, company_name TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK(event_type IN ('earnings','investor_conference')),
  title TEXT NOT NULL, event_date TEXT NOT NULL,
  start_time TEXT, end_time TEXT, fiscal_year INTEGER, fiscal_quarter INTEGER,
  status TEXT NOT NULL CHECK(status IN ('confirmed','estimated','completed','cancelled')),
  location TEXT, online_url TEXT, organizer TEXT, language TEXT, description TEXT,
  source TEXT NOT NULL, source_url TEXT NOT NULL, external_url TEXT,
  presentation_url TEXT, replay_url TEXT, ir_url TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, last_verified_at TEXT NOT NULL,
  UNIQUE(stock_id,event_type,event_date,title,source)
);
CREATE INDEX IF NOT EXISTS idx_company_events_date_type ON company_events(event_date,event_type);
CREATE INDEX IF NOT EXISTS idx_company_events_stock_date ON company_events(stock_id,event_date);
CREATE TABLE IF NOT EXISTS event_source_state (
  source TEXT PRIMARY KEY, last_attempt_at TEXT NOT NULL,
  last_success_at TEXT, last_error TEXT, rows_seen INTEGER NOT NULL DEFAULT 0
);
