export type RuntimePaths = {
  project_root: string;
  data_dir: string;
  raw_data_dir: string;
  processed_data_dir: string;
  db_dir: string;
  cache_dir: string;
  logs_dir: string;
  backups_dir: string;
};

export type FileStatus = {
  name: string;
  path: string;
  exists: boolean;
};

export type DataStatus = {
  paths: RuntimePaths;
  db_files: FileStatus[];
  data_files: FileStatus[];
};

export type StockStatus = {
  count: number;
  last_sync_at: string | null;
};

export type DashboardSection<T> = {
  name: string;
  ok: boolean;
  data: T | null;
  error?: string;
};

export type MarketMapStatus = {
  group_count: number;
  topic_count: number;
  company_count: number;
  assignment_count: number;
  last_sync_at: string | null;
  taxonomy_version: string | null;
  region_scope: string | null;
};

export type BrokerOverview = {
  report_count: number;
  trade_day_count: number;
  stock_count: number;
  branch_count: number;
  latest_trade_date: string;
};

export type BrokerBranch = {
  broker_name: string;
  trade_days: number;
  stock_count: number;
  last_trade_date: string;
  total_buy_shares: number;
  total_sell_shares: number;
  total_net_shares: number;
};

export type DashboardOverview = {
  summary: {
    architecture: string;
    frontend: string;
    backend: string;
    ready_file_count: number;
    total_file_count: number;
  };
  runtime: DataStatus;
  sections: {
    stocks: DashboardSection<StockStatus>;
    market_map: DashboardSection<MarketMapStatus>;
    broker: DashboardSection<BrokerOverview>;
  };
};

export type MarketMapGroup = {
  group_name: string;
  display_name: string;
  sort_order: number;
  is_tech: number;
  topic_count: number;
  company_count: number;
};

export type MarketMapTopic = {
  group_name: string;
  topic_name: string;
  display_name: string;
  parent_industry: string | null;
  topic_type: string;
  is_tech: number;
  description: string | null;
  news_query: string | null;
  company_count: number;
};

export type MarketMapMember = {
  topic_name: string;
  code: string;
  name_zh: string;
  full_name_zh: string | null;
  market: string | null;
  yfinance_symbol: string | null;
  official_industry: string | null;
  source: string;
  confidence: number;
  note: string | null;
};

export type Security = {
  code: string;
  name_zh: string;
  full_name_zh: string | null;
  market: string;
  yfinance_symbol: string;
  industry_code: string | null;
  paid_in_capital: number | null;
  issued_common_shares: number | null;
};

export type StockDetail = {
  stock_id: string;
  found: boolean;
  security: Security | null;
};

export type PriceCacheStatus = {
  symbol: string;
  last_updated_at: string | null;
  first_cached_date: string | null;
  last_cached_date: string | null;
  last_trade_date: string | null;
  last_checked_date: string | null;
  row_count: number;
  source: string;
  fetch_status: string;
  last_error: string | null;
};

export type PriceCacheOverview = {
  history: {
    symbol_count: number;
    row_count: number;
    first_trade_date: string | null;
    last_trade_date: string | null;
  };
  meta: {
    meta_count: number;
    ready_count: number | null;
    failed_count: number | null;
    last_updated_at: string | null;
  };
};

export type DataSourceStatus = {
  key: string;
  title: string;
  description: string;
  status: "ready" | "empty" | "mock" | "error" | string;
  db_file: string | null;
  latest_date: string | null;
  last_updated_at?: string | null;
  row_count: number | null;
  symbol_count: number | null;
  update_mode: string;
  action_label: string;
  action_enabled: boolean;
  note: string | null;
};

export type DataSourcesOverview = {
  sources: DataSourceStatus[];
  price_cache: PriceCacheOverview;
};

export type BrokerRankRow = {
  broker_code: string | null;
  broker_name: string;
  price: number | null;
  buy_shares: number;
  sell_shares: number;
  buy_amount: number;
  sell_amount: number;
  net_shares: number;
  avg_buy_price: number | null;
  avg_sell_price: number | null;
};

export type BrokerSummary = {
  trade_date: string;
  source: string;
  imported_at: string;
  row_count: number;
  buy_rank: BrokerRankRow[];
  sell_rank: BrokerRankRow[];
};

export type InstitutionalTradingRow = {
  trade_date: string;
  market: string;
  code: string;
  name_zh: string;
  foreign_buy: number;
  foreign_sell: number;
  foreign_net: number;
  trust_buy: number;
  trust_sell: number;
  trust_net: number;
  dealer_buy: number;
  dealer_sell: number;
  dealer_net: number;
  total_net: number;
  fetched_at: string;
};

export type PriceQuote = {
  trade_date: string;
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
};

export type QuoteSummary = PriceQuote & {
  change: number | null;
  change_pct: number | null;
};

export type StockOverview = StockDetail & {
  price_cache: PriceCacheStatus | null;
  latest_quote: QuoteSummary | null;
  quotes: PriceQuote[];
  broker_summary: BrokerSummary | null;
  institutional_trading: InstitutionalTradingRow[];
};

export type StrongStockRow = {
  symbol: string;
  code: string;
  name_zh: string;
  market: string | null;
  first_date: string;
  last_date: string;
  quote_count: number;
  start_close: number;
  latest_close: number;
  change: number;
  change_pct: number;
  sparkline: Array<{
    trade_date: string;
    close: number;
  }>;
};

export type StrongStocks = {
  summary: {
    days: number;
    limit: number;
    anchor_date: string | null;
    window_start_date: string | null;
    candidate_count: number;
    returned_count: number;
  };
  rows: StrongStockRow[];
};

export type PriceCacheUpdateResponse = {
  requested_count: number;
  ok_count: number;
  failed_count: number;
  results: Array<{
    stock_id: string;
    symbol?: string;
    ok: boolean;
    loaded_rows?: number;
    error?: string;
    status?: PriceCacheStatus;
  }>;
};

export type PriceCacheJob = {
  job_id: string;
  job_type: string;
  cache_key: unknown;
  status: "queued" | "running" | "completed" | "failed" | string;
  progress: number;
  message: string | null;
  params: unknown;
  error: string | null;
  created_at: string;
  updated_at: string;
  finished_at: string | null;
};

export type PriceCacheJobStartResponse = {
  ok: boolean;
  job_id?: string;
  stock_count?: number;
  error?: string;
};

export type PriceCacheJobResponse = {
  ok: boolean;
  job?: PriceCacheJob;
  error?: string;
};

export type RevenueMomentumRow = {
  report_month: string;
  output_date: string | null;
  market: string;
  code: string;
  name_zh: string;
  industry: string | null;
  current_revenue: number | null;
  mom_pct: number | null;
  yoy_pct: number | null;
  cumulative_yoy_pct: number | null;
  trend_score?: number | null;
  slope_pct?: number | null;
  trend_growth_pct?: number | null;
  growth_acceleration_pct?: number | null;
  accelerating_step_count?: number | null;
  positive_growth_rate_count?: number | null;
  growth_rate_improvement_pct?: number | null;
  growth_rates?: number[];
  positive_step_count?: number | null;
  month_count?: number | null;
  latest_vs_recent_average_pct?: number | null;
  revenue_history?: Array<{
    report_month: string;
    current_revenue: number | null;
  }>;
  updated_at: string;
};

export type RevenueMomentum = {
  report_month: string | null;
  summary?: {
    mode: string;
    lookback_months: number;
    used_months?: string[];
    candidate_count?: number;
    qualified_count?: number;
    returned_count?: number;
  };
  rows: RevenueMomentumRow[];
};

export type UsMarketCalendarEvent = {
  date: string;
  time: string;
  country: string;
  event: string;
  category: string;
  importance: "high" | "medium" | "low" | string;
  previous: string | null;
  forecast: string | null;
  actual: string | null;
  unit: string | null;
  market_impact: string;
};

export type UsMarketCalendar = {
  source: string;
  source_label: string;
  start_date: string;
  end_date: string;
  importance: string;
  event_count: number;
  rows: UsMarketCalendarEvent[];
};

export type ActiveEtfSnapshot = {
  etf_code: string;
  snapshot_date: string;
  etf_name: string | null;
  from_date: string | null;
  to_date: string | null;
  issuer: string | null;
  holdings_count: number | null;
  turnover_rate: number | null;
  aum_100m: number | null;
  beneficiary_10k: number | null;
  change_count: number;
  add_count: number;
  increase_count: number;
  decrease_count: number;
  remove_count: number;
  updated_at: string | null;
};

export type ActiveEtfSnapshots = {
  summary: {
    snapshot_count: number;
    etf_count: number;
    min_snapshot_date: string | null;
    max_snapshot_date: string | null;
    window_days: number;
    window_start_date: string | null;
    window_end_date: string | null;
  };
  rows: ActiveEtfSnapshot[];
};

export type ActiveEtfChange = {
  etf_code: string;
  snapshot_date: string;
  change_label: string | null;
  stock_code: string | null;
  stock_name: string | null;
  industry: string | null;
  shares_delta: number | null;
  shares_delta_lots: number | null;
  weight_delta: number | null;
  old_weight: number | null;
  new_weight: number | null;
  holding_amount_100m: number | null;
  new_lots: number | null;
};

export type ActiveEtfChanges = {
  etf_code: string;
  snapshot_date: string | null;
  rows: ActiveEtfChange[];
};

export type StrategyMetadata = {
  key: string;
  title: string;
  summary: string;
  description: string;
};

export type BacktestConfig = {
  default_buy_strategies: string[];
  default_sell_strategies: string[];
  buy_strategies: StrategyMetadata[];
  sell_strategies: StrategyMetadata[];
};

export type BacktestJob = {
  job_id: string;
  status: string;
  progress: number;
  message: string;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  result_count?: number;
  result_preview?: Record<string, unknown>[] | Record<string, Record<string, unknown>>;
};

export type BacktestJobResponse = {
  ok: boolean;
  job?: BacktestJob;
  job_id?: string;
  error?: string;
};

export type NewsJob = {
  job_id: string;
  status: string;
  progress: number;
  message: string;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  result_preview?: {
    daily_brief?: string[];
    ai_summary_enabled?: boolean;
    ai_model?: string;
  };
};

export type NewsJobResponse = {
  ok: boolean;
  job?: NewsJob;
  job_id?: string;
  error?: string;
};

export type ResearchCompany = {
  code: string;
  name_zh: string;
  full_name_zh: string | null;
  market: string | null;
  yfinance_symbol: string | null;
  industry: string | null;
  themes: string[];
  confidence: number | null;
  updated_at: string | null;
};

export type ResearchCompanies = {
  summary: {
    company_count: number;
    theme_count: number;
    last_sync_at: string | null;
  };
  rows: ResearchCompany[];
};
