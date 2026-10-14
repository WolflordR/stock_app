import type {
  DashboardOverview,
  DataSourcesOverview,
  DataStatus,
  ActiveEtfChanges,
  ActiveEtfRefreshJobResponse,
  ActiveEtfSnapshots,
  BacktestConfig,
  BacktestJobResponse,
  BootstrapJobsResponse,
  BrokerBranch,
  BrokerBranchStocks,
  MarketMapGroup,
  MarketMapMember,
  MarketMapTopic,
  NewsJobResponse,
  PriceCacheOverview,
  PriceCacheJobResponse,
  PriceCacheJobStartResponse,
  PriceCacheUpdateResponse,
  ResearchCompanies,
  RevenueMomentum,
  StockDetail,
  StockOverview,
  StockStatus,
  StrongStocks,
  UsMarketCalendar,
  WatchlistsOverview
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export type HomeEvent = {
  id: string; stock_id: string; company_name: string; event_type: "earnings" | "investor_conference";
  title: string; event_date: string; start_time: string | null; fiscal_year: number | null;
  fiscal_quarter: number | null; status: "confirmed" | "estimated" | "completed" | "cancelled";
  location: string | null; online_url: string | null; organizer: string | null; language: string | null;
  source: string; source_url: string; last_verified_at: string; presentation_url: string | null;
  replay_url: string | null; ir_url: string | null; is_watchlist?: boolean; has_signal?: boolean;
};
export type HomeIndustry = { sector_key: string; l3: string; rotation_score: number; return_1d: number | null; return_5d: number | null; return_20d: number | null; volume_ratio: number | null; turnover_expansion: number | null; turnover_share_delta: number | null; breadth: number | null; breakout_participation: number | null; stage: string; observed_count: number; trade_date: string };
export type HomeSignal = { signal_date: string; stock_id: string; name: string; strategy: string; price: number; change_pct: number | null; volume_ratio: number | null; volume_lots: number; estimated_turnover_twd: number; large_holder_pct?: number | null; large_holder_change_pp?: number | null; ownership_report_date?: string | null; ownership_previous_date?: string | null; distance_to_high_pct: number | null; is_new: number; industry: string | null; industry_score: number | null };
export type MarketTurnoverRatio = { trade_date: string; amount_twd: number; average5_twd: number | null; ratio: number | null; baseline_dates: string[]; source_urls: Record<string, string> } | null;
export type HomeDashboard = {
  last_updated: string;
  market: { benchmarks: Record<string, { label: string; value: number; date: string; change: number | null; change_pct: number | null; source_url: string }>; turnover_estimate: number | null; turnover_ratios: Record<"TWSE" | "TPEx" | "combined", MarketTurnoverRatio>; tsmc: { price: number; change_pct: number | null; trade_date: string } | null; price_date: string | null };
  breadth: { date: string | null; observed: number; advancing: number; declining: number; unchanged: number; advance_pct: number | null; above_ma20_pct: number | null; above_ma60_pct: number | null; new_high20: number; new_low20: number; coverage_note: string; limits: { date: string | null; limit_up_count: number | null; limit_down_count: number | null; markets: Record<string, { market: string; trade_date: string; limit_up_count: number; limit_down_count: number; source_url: string }> } };
  recent_revenue: { report_month: string | null; count: number; markets: Record<string, number>; updated_at: string | null; partial: boolean; source_urls: Record<string, string> };
  industry_date: string | null; industries: HomeIndustry[]; signal_date: string | null; signals: HomeSignal[];
  events: { rows: HomeEvent[]; count: number; source_state: { source: string; last_success_at: string | null; last_error: string | null }[] };
  watchlist: { stock_id: string; name: string; price?: number; change_pct?: number | null; industry: string | null; industry_score: number | null; signals: string[]; next_event: HomeEvent | null }[];
  important_events: { stock_id: string; name: string; strategy: string; event_type: string; event_date: string; days_until: number; status: string; title: string }[];
  strategy_performance: { strategy: string; window: number; signals: number | null; win_rate: number | null; average_return: number | null; median_return: number | null; max_drawdown: number | null }[];
  data_quality: Record<string, string>;
};

export function fetchHomeDashboard(refresh = false): Promise<HomeDashboard> {
  return requestJson<HomeDashboard>(refresh ? "/api/dashboard?refresh=true" : "/api/dashboard");
}

export type MarketLimitStock = {
  market: "TWSE" | "TPEx";
  trade_date: string;
  stock_id: string;
  name: string;
  direction: "up" | "down";
  close: number;
  limit_price: number;
  volume_shares: number;
};
export type MarketLimitListing = {
  direction: "up" | "down";
  market: "TWSE" | "TPEx" | "combined";
  date: string | null;
  official_count: number | null;
  rows: MarketLimitStock[];
  markets: Record<string, {
    status: "complete" | "pending" | "no_summary";
    date: string | null;
    official_up?: number;
    official_down?: number;
    summary_source_url?: string;
    limit_source_url?: string | null;
    quote_source_url?: string | null;
  }>;
  complete: boolean;
};
export function fetchMarketLimitStocks(direction: "up" | "down", market: "TWSE" | "TPEx" | "combined"): Promise<MarketLimitListing> {
  return requestJson<MarketLimitListing>(`/api/market/limits/stocks?direction=${direction}&market=${market}`);
}

export type MarginRow = { trade_date: string; market: string; margin_balance_lots: number; margin_previous_lots: number | null; margin_balance_thousand_twd?: number | null; margin_previous_thousand_twd?: number | null; margin_balance_yi_twd?: number | null; margin_change_yi_twd?: number | null; margin_5d_change_yi_twd?: number | null; margin_change_lots: number | null; margin_5d_change_lots?: number | null; margin_buy_lots?: number | null; margin_sell_lots?: number | null; short_balance_lots: number; short_previous_lots: number | null; short_change_lots: number | null; short_5d_change_lots?: number | null; short_sell_lots?: number | null; short_buy_lots?: number | null; short_to_margin_pct: number | null; ratio_5d_change_pp?: number | null; source_url: string | null };
export type MarginHistory = { market?: string; stock_id?: string; unit: string; ratio_formula?: string; rows: MarginRow[]; latest: MarginRow | null; source_urls: Record<string, string>; source_status?: { source: string; last_success_date: string | null; last_error: string | null }[] };
export type OwnershipRow = { report_date: string; total_shares: number; large: Record<string, { shares: number; lots: number; holders: number; pct: number | null }>; small_10: { shares: number; holders: number; pct: number | null } | null };
export type OwnershipHistory = { stock_id: string; frequency: string; thresholds: Record<string, string>; rows: OwnershipRow[]; latest: OwnershipRow | null; source_url: string; archive_url?: string | null };
export function fetchMarketMargin(market: "TWSE" | "TPEx" | "combined" = "TWSE"): Promise<MarginHistory> { return requestJson(`/api/chips/market/margin-short?market=${market}&days=370`); }
export function fetchStockMargin(stockId: string, all = false): Promise<MarginHistory> { return requestJson(`/api/chips/stocks/${encodeURIComponent(stockId)}/margin-short?days=${all ? 0 : 370}`); }
export function fetchOwnership(stockId: string): Promise<OwnershipHistory> { return requestJson(`/api/chips/stocks/${encodeURIComponent(stockId)}/ownership?days=750`); }

export type CompanyEventsResult = {
  rows: HomeEvent[];
  count: number;
  totals: Record<string, number>;
  source_state: { source: string; last_attempt_at: string; last_success_at: string | null; last_error: string | null; rows_seen: number }[];
};
export function fetchCompanyEvents(params: {start_date?: string; end_date?: string; event_type?: string; stock_id?: string; watchlist_only?: boolean; query?: string; status?: string; limit?: number; offset?: number}): Promise<CompanyEventsResult> {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== "") query.set(key, String(value)); });
  return requestJson(`/api/events?${query}`);
}

async function requestJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, payload: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function deleteJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchDataStatus(): Promise<DataStatus> {
  return requestJson<DataStatus>("/api/runtime/data-status");
}

export function startBootstrapJobs(): Promise<BootstrapJobsResponse> {
  return postJson<BootstrapJobsResponse>("/api/bootstrap/jobs", {});
}

export function fetchDataSourcesOverview(): Promise<DataSourcesOverview> {
  return requestJson<DataSourcesOverview>("/api/data/sources");
}

export function fetchStockStatus(): Promise<StockStatus> {
  return requestJson<StockStatus>("/api/stocks/status");
}

export function fetchSectorCoverage(): Promise<SectorCoverage> {
  return requestJson<SectorCoverage>("/api/sectors/coverage");
}

export function fetchSectorRanking(windowDays: 1 | 3 | 5): Promise<SectorRankingRow[]> {
  return requestJson<SectorRankingRow[]>(`/api/sectors/ranking?window_days=${windowDays}`);
}

export function fetchSectorStocks(slug: string): Promise<SectorStock[]> {
  return requestJson<SectorStock[]>(`/api/sectors/${encodeURIComponent(slug)}/stocks`);
}

export type RotationCoverage = {
  twse_ordinary_total: number; tpex_ordinary_total: number;
  twse_target: number; tpex_target: number; target_total: number;
  l1_mapped_total: number; l1_mapped_pct: number;
  l2_mapped_total: number; l2_mapped_pct: number;
  l3_mapped_total: number; l3_mapped_pct: number;
  primary_l3_total: number; classification_version?: string;
  review_queue_total: number; review_queue_pct: number;
  unresolved_membership_total: number; last_sync_at: string | null;
};

export type RotationRow = {
  trade_date: string; level: number; sector_key: string; l1: string; l2: string | null; l3: string | null;
  constituent_count: number; observed_count: number; coverage_ratio: number;
  rotation_score: number; stage: string; return_1d: number | null; return_5d: number | null;
  return_20d: number | null; breadth: number | null; turnover_share: number | null;
  turnover_share_delta: number | null; turnover_expansion: number | null;
  accumulation_pressure: number | null;
  relative_strength: number | null; rs_momentum: number | null;
  institutional_net_shares: number | null; institutional_coverage: number | null;
  breadth_quality: string; concentrated: number; top1_turnover_share: number;
  top3_turnover_share: number; pressure_source: string;
};

export type RotationStock = {
  market: string; stock_id: string; name: string; classification_source: string; is_primary_here: number;
  return_1d: number | null; return_5d: number | null; return_20d: number | null;
  turnover: number | null; volume_ratio: number | null; breakout: number | null; early_rise: number | null;
  institutional_net_shares: number | null;
};

export type RotationDetail = {
  sector: RotationRow; stocks: RotationStock[]; timeline: RotationRow[];
  diff: { score_delta: number; rank_change: number | null; stage_from: string; stage_to: string; breadth_delta: number } | null;
  leaders: RotationStock[]; early_rotation: RotationStock[]; followers: RotationStock[];
  institutional_buy: RotationStock[]; volume_surge: RotationStock[]; breakouts: RotationStock[];
};

export function fetchRotationCoverage(): Promise<RotationCoverage> {
  return requestJson<RotationCoverage>('/api/rotation/coverage');
}

export function fetchRotationFilters(): Promise<{l1: string; l2: string}[]> {
  return requestJson<{l1: string; l2: string}[]>('/api/rotation/filters');
}

export function fetchRotationRanking(level: 1 | 2 | 3, l1: string, l2: string, includeSmall: boolean): Promise<RotationRow[]> {
  const query = new URLSearchParams({level: String(level), include_small: String(includeSmall)});
  if (l1) query.set('l1', l1);
  if (l2) query.set('l2', l2);
  return requestJson<RotationRow[]>(`/api/rotation/ranking?${query}`);
}

export function fetchRotationDetail(key: string): Promise<RotationDetail> {
  return requestJson<RotationDetail>(`/api/rotation/detail/${encodeURIComponent(key)}`);
}

export type SectorCoverage = {
  twse_official_total: number;
  tpex_official_total: number;
  imported_total: number;
  taxonomy_mapped_total: number;
  taxonomy_mapped_pct: number;
  official_only_total: number;
  official_only_pct: number;
  verified_theme_total: number;
  last_sync_at: string | null;
  coverage_ok: boolean;
};

export type SectorRankingRow = {
  trade_date: string;
  window_days: number;
  category_slug: string;
  name_zh: string;
  type: string;
  constituent_count: number;
  observed_count: number;
  rotation_score: number;
  advance_ratio: number;
  median_return: number;
  volume_expansion_ratio: number;
  breakout_ratio: number;
  relative_strength: number;
  turnover_momentum: number;
};

export type SectorStock = {
  market: string;
  stock_id: string;
  name: string;
  official_industry_code: string;
  classification_state: string;
  category_slugs: string | null;
};

export function fetchDashboardOverview(): Promise<DashboardOverview> {
  return requestJson<DashboardOverview>("/api/dashboard/overview");
}

export function fetchStockDetail(stockId: string): Promise<StockDetail> {
  return requestJson<StockDetail>(`/api/stocks/${encodeURIComponent(stockId)}`);
}

export function fetchStockOverview(stockId: string): Promise<StockOverview> {
  return requestJson<StockOverview>(`/api/stocks/${encodeURIComponent(stockId)}/overview`);
}

export type FinancialQuarter = {
  period: string;
  report_year: number;
  report_quarter: number;
  eps_single_quarter: number | null;
  gross_margin_pct: number | null;
  pe_ratio_quarter_end: number | null;
  pe_data_date: string | null;
  source_url: string;
};

export type FinancialTrends = {
  quarters: FinancialQuarter[];
  pe_history: { data_date: string; pe_ratio: number | null; source_url: string }[];
  income_source: string;
  pe_source: string;
  source_error: string | null;
  note: string;
};

export function fetchFinancialTrends(stockId: string): Promise<FinancialTrends> {
  return requestJson<FinancialTrends>(`/api/stocks/${encodeURIComponent(stockId)}/financial-trends`);
}

export type StockSuggestion = { code: string; name_zh: string; market: "TWSE" | "TPEx" };
export function fetchStockSuggestions(query: string): Promise<{ query: string; rows: StockSuggestion[] }> {
  return requestJson(`/api/stocks/search?q=${encodeURIComponent(query)}&limit=50`);
}

export function fetchWatchlists(groupId?: number | null): Promise<WatchlistsOverview> {
  const query = groupId ? `?group_id=${groupId}` : "";
  return requestJson<WatchlistsOverview>(`/api/watchlists${query}`);
}

export function createWatchlistGroup(name: string): Promise<WatchlistsOverview> {
  return postJson<WatchlistsOverview>("/api/watchlists/groups", { name });
}

export function addWatchlistItem(stockCode: string, groupId?: number | null): Promise<WatchlistsOverview> {
  return postJson<WatchlistsOverview>("/api/watchlists/items", {
    stock_code: stockCode,
    group_id: groupId ?? undefined
  });
}

export function removeWatchlistItem(groupId: number, stockCode: string): Promise<WatchlistsOverview> {
  return deleteJson<WatchlistsOverview>(`/api/watchlists/groups/${groupId}/items/${encodeURIComponent(stockCode)}`);
}

export function updateStockPriceCache(stockId: string, days = 1825): Promise<PriceCacheUpdateResponse> {
  return postJson<PriceCacheUpdateResponse>(`/api/stocks/${encodeURIComponent(stockId)}/price-cache`, {
    days,
    force: true
  });
}

export function fetchStrongStocks(days = 7, limit = 10): Promise<StrongStocks> {
  return requestJson<StrongStocks>(`/api/stocks/strong?days=${days}&limit=${limit}`);
}

export function fetchPriceCacheOverview(): Promise<PriceCacheOverview> {
  return requestJson<PriceCacheOverview>("/api/price-cache/status");
}

export type PriceCacheJobPayload = {
  scope: "all" | "range" | "stocks";
  start_code?: number;
  end_code?: number;
  stock_ids?: string[];
  days: number;
  force: boolean;
};

export function startPriceCacheJob(payload: PriceCacheJobPayload): Promise<PriceCacheJobStartResponse> {
  return postJson<PriceCacheJobStartResponse>("/api/price-cache/jobs", payload);
}

export function fetchPriceCacheJob(jobId: string): Promise<PriceCacheJobResponse> {
  return requestJson<PriceCacheJobResponse>(`/api/price-cache/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchLatestPriceCacheJob(): Promise<PriceCacheJobResponse> {
  return requestJson<PriceCacheJobResponse>("/api/price-cache/jobs/latest");
}

export function fetchMarketMapGroups(): Promise<MarketMapGroup[]> {
  return requestJson<MarketMapGroup[]>("/api/market-map/groups");
}

export function fetchMarketMapTopics(groupName?: string): Promise<MarketMapTopic[]> {
  const params = new URLSearchParams();
  if (groupName) params.set("group_name", groupName);
  const query = params.toString();
  return requestJson<MarketMapTopic[]>(`/api/market-map/topics${query ? `?${query}` : ""}`);
}

export function fetchMarketMapMembers(topicName: string): Promise<MarketMapMember[]> {
  return requestJson<MarketMapMember[]>(`/api/market-map/topics/${encodeURIComponent(topicName)}/members`);
}

export function fetchBrokerBranches(searchText = ""): Promise<BrokerBranch[]> {
  const params = new URLSearchParams();
  if (searchText.trim()) params.set("search_text", searchText.trim());
  params.set("limit", "80");
  return requestJson<BrokerBranch[]>(`/api/broker/branches?${params.toString()}`);
}

export function fetchBrokerBranchStocks(
  brokerName: string,
  tradeDate: string,
  side: "buy" | "sell",
  sortBy: BrokerBranchStocks["sort_by"],
  descending: boolean,
  offset: number,
  limit = 50
): Promise<BrokerBranchStocks> {
  const params = new URLSearchParams({
    broker_name: brokerName,
    trade_date: tradeDate,
    side,
    sort_by: sortBy,
    descending: String(descending),
    offset: String(offset),
    limit: String(limit)
  });
  return requestJson<BrokerBranchStocks>(`/api/broker/branch-stocks?${params.toString()}`);
}

export function fetchRevenueMomentum(limit = 30, offset = 0): Promise<RevenueMomentum> {
  return requestJson<RevenueMomentum>(`/api/revenue/momentum?limit=${limit}&offset=${offset}`);
}

export function fetchUsMarketCalendar(startDate: string, endDate: string, importance = "all"): Promise<UsMarketCalendar> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  params.set("importance", importance);
  return requestJson<UsMarketCalendar>(`/api/us-market/calendar?${params.toString()}`);
}

export function fetchActiveEtfSnapshots(limit = 500, days = 30): Promise<ActiveEtfSnapshots> {
  return requestJson<ActiveEtfSnapshots>(`/api/etf/active/snapshots?limit=${limit}&days=${days}`);
}

export function fetchActiveEtfChanges(etfCode: string, snapshotDate?: string): Promise<ActiveEtfChanges> {
  const params = new URLSearchParams();
  params.set("limit", "120");
  if (snapshotDate) params.set("snapshot_date", snapshotDate);
  return requestJson<ActiveEtfChanges>(`/api/etf/active/${encodeURIComponent(etfCode)}/changes?${params.toString()}`);
}

export function startActiveEtfRefresh(): Promise<ActiveEtfRefreshJobResponse> {
  return postJson<ActiveEtfRefreshJobResponse>("/api/etf/active/refresh", {});
}

export function fetchActiveEtfRefreshJob(jobId: string): Promise<ActiveEtfRefreshJobResponse> {
  return requestJson<ActiveEtfRefreshJobResponse>(`/api/etf/active/refresh/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchBacktestConfig(): Promise<BacktestConfig> {
  return requestJson<BacktestConfig>("/api/backtest/config");
}

export type BacktestStartPayload = {
  start_num: number;
  end_num: number;
  mode: string;
  selected_strategies: string[];
  selected_sell_strategies: string[];
  request_delay_sec: number;
  range_lookback_days?: number;
  range_max_width_pct?: number;
  range_volume_ratio?: number;
  range_min_price_gain_pct?: number;
  range_max_price_gain_pct?: number;
  range_volume_sustain_days?: number;
  initial_capital?: number;
  trading_cost_pct?: number;
  initial_stop_loss_pct?: number;
  min_turnover_value?: number;
  trailing_stop_activation_pct?: number;
  trailing_stop_drawdown_pct?: number;
  pullback_strong_lookback_days?: number;
  pullback_min_pullback_pct?: number;
  pullback_base_hold_days?: number;
  pullback_low_price_volume_price_threshold?: number;
  pullback_low_price_min_volume_lots?: number;
  pullback_technology_only?: boolean;
  vcp_lookback_days?: number;
  vcp_min_uptrend_pct?: number;
  vcp_breakout_volume_ratio?: number;
  vcp_near_pivot_tolerance_pct?: number;
  vcp_max_consolidation_depth_pct?: number;
  high_price_pullback_lookback_days?: number;
  high_price_pullback_market_cap_rank_limit?: number;
  high_price_pullback_min_drop_pct?: number;
  breakout_lookback_days?: number;
  breakout_distance_pct?: number;
  breakout_trend_lookback_days?: number;
  breakout_volume_short_window?: number;
  breakout_volume_long_window?: number;
  bowl_volume_lookback_days?: number;
  bowl_volume_min_drawdown_pct?: number;
  bowl_volume_volume_lookback_days?: number;
  bowl_volume_signal_window_days?: number;
  bowl_volume_multiplier?: number;
  bowl_volume_trend_lookback_days?: number;
  momentum_volume_ma_short?: number;
  momentum_volume_ma_long?: number;
  momentum_volume_momentum_lookback?: number;
  momentum_volume_ma_slope_lookback?: number;
  momentum_volume_volume_ma_period?: number;
  momentum_volume_volume_multiplier?: number;
  momentum_volume_volume_lookback?: number;
  initial_rise_max_5d_gain_pct?: number;
  initial_rise_max_10d_gain_pct?: number;
  initial_rise_min_today_gain_pct?: number;
  initial_rise_max_today_gain_pct?: number;
  initial_rise_volume_ma_period?: number;
  initial_rise_min_volume_ratio?: number;
  initial_rise_quiet_volume_days?: number;
  initial_rise_consolidation_days?: number;
  initial_rise_max_range_width_pct?: number;
  initial_rise_breakout_days?: number;
  initial_rise_min_close_position?: number;
};

export function startBacktestJob(payload: BacktestStartPayload): Promise<BacktestJobResponse> {
  return postJson<BacktestJobResponse>("/api/backtest/jobs", {
    ...payload
  });
}

export function fetchBacktestJob(jobId: string): Promise<BacktestJobResponse> {
  return requestJson<BacktestJobResponse>(`/api/backtest/jobs/${encodeURIComponent(jobId)}`);
}

export function startNewsJob(): Promise<NewsJobResponse> {
  return postJson<NewsJobResponse>("/api/news/jobs", {
    industry_count: 5,
    headlines_per_industry: 4,
    us_news_items: 8
  });
}

export function fetchNewsJob(jobId: string): Promise<NewsJobResponse> {
  return requestJson<NewsJobResponse>(`/api/news/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchResearchCompanies(searchText = ""): Promise<ResearchCompanies> {
  const params = new URLSearchParams();
  if (searchText.trim()) params.set("search_text", searchText.trim());
  params.set("limit", "80");
  return requestJson<ResearchCompanies>(`/api/research/companies?${params.toString()}`);
}
