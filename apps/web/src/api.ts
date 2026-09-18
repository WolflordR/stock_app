import type {
  DashboardOverview,
  DataSourcesOverview,
  DataStatus,
  ActiveEtfChanges,
  ActiveEtfSnapshots,
  BacktestConfig,
  BacktestJobResponse,
  BrokerBranch,
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
  UsMarketCalendar
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

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

export function fetchDataStatus(): Promise<DataStatus> {
  return requestJson<DataStatus>("/api/runtime/data-status");
}

export function fetchDataSourcesOverview(): Promise<DataSourcesOverview> {
  return requestJson<DataSourcesOverview>("/api/data/sources");
}

export function fetchStockStatus(): Promise<StockStatus> {
  return requestJson<StockStatus>("/api/stocks/status");
}

export function fetchDashboardOverview(): Promise<DashboardOverview> {
  return requestJson<DashboardOverview>("/api/dashboard/overview");
}

export function fetchStockDetail(stockId: string): Promise<StockDetail> {
  return requestJson<StockDetail>(`/api/stocks/${encodeURIComponent(stockId)}`);
}

export function fetchStockOverview(stockId: string): Promise<StockOverview> {
  return requestJson<StockOverview>(`/api/stocks/${encodeURIComponent(stockId)}/overview`);
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

export function fetchRevenueMomentum(limit = 30): Promise<RevenueMomentum> {
  return requestJson<RevenueMomentum>(`/api/revenue/momentum?limit=${limit}`);
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
