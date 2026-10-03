import {
  Activity,
  BadgeCheck,
  BarChart3,
  BriefcaseBusiness,
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  Database,
  FileSearch,
  HardDrive,
  Layers3,
  Newspaper,
  PieChart,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  TrendingUp,
  Wrench
} from "lucide-react";
import type { ReactNode } from "react";
import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  fetchActiveEtfChanges,
  fetchActiveEtfSnapshots,
  fetchBacktestJob,
  fetchBacktestConfig,
  fetchBrokerBranches,
  fetchDataSourcesOverview,
  fetchDashboardOverview,
  fetchLatestPriceCacheJob,
  fetchMarketMapGroups,
  fetchMarketMapMembers,
  fetchMarketMapTopics,
  fetchNewsJob,
  fetchPriceCacheOverview,
  fetchPriceCacheJob,
  fetchResearchCompanies,
  fetchRevenueMomentum,
  fetchStrongStocks,
  fetchStockOverview,
  fetchUsMarketCalendar,
  startNewsJob,
  startBacktestJob,
  startBootstrapJobs,
  startPriceCacheJob,
  updateStockPriceCache
} from "./api";
import { CandlestickVolumeChart } from "./components/CandlestickVolumeChart";
import type {
  ActiveEtfChanges,
  ActiveEtfSnapshot,
  ActiveEtfSnapshots,
  BacktestConfig,
  BacktestJob,
  BrokerBranch,
  BrokerRankRow,
  DashboardOverview,
  DataSourcesOverview,
  DataSourceStatus,
  FileStatus,
  MarketMapGroup,
  MarketMapMember,
  MarketMapTopic,
  NewsJob,
  PriceCacheOverview,
  PriceCacheJob,
  ResearchCompanies,
  RevenueMomentum,
  StockOverview,
  StrongStocks,
  UsMarketCalendar
} from "./types";

type LoadState = "idle" | "loading" | "ready" | "error";
type ViewKey = "overview" | "stock" | "strong" | "data" | "market" | "broker" | "revenue" | "usCalendar" | "etf" | "backtest" | "news" | "research" | "system";
type StockNavigation = {
  sourceLabel: string;
  codes: string[];
};
type StockNavigationState = {
  sourceLabel: string;
  currentIndex: number;
  total: number;
  previousCode: string | null;
  nextCode: string | null;
};
type BacktestTuningParams = {
  range_lookback_days: number;
  range_max_width_pct: number;
  range_volume_ratio: number;
  range_min_price_gain_pct: number;
  range_max_price_gain_pct: number;
  range_volume_sustain_days: number;
  initial_capital: number;
  trading_cost_pct: number;
  initial_stop_loss_pct: number;
  trailing_stop_activation_pct: number;
  trailing_stop_drawdown_pct: number;
  pullback_strong_lookback_days: number;
  pullback_min_pullback_pct: number;
  pullback_base_hold_days: number;
  pullback_low_price_volume_price_threshold: number;
  pullback_low_price_min_volume_lots: number;
  pullback_technology_only: boolean;
  vcp_lookback_days: number;
  vcp_min_uptrend_pct: number;
  vcp_breakout_volume_ratio: number;
  vcp_near_pivot_tolerance_pct: number;
  vcp_max_consolidation_depth_pct: number;
  high_price_pullback_lookback_days: number;
  high_price_pullback_market_cap_rank_limit: number;
  high_price_pullback_min_drop_pct: number;
  breakout_lookback_days: number;
  breakout_distance_pct: number;
  breakout_trend_lookback_days: number;
  breakout_volume_short_window: number;
  breakout_volume_long_window: number;
  bowl_volume_lookback_days: number;
  bowl_volume_min_drawdown_pct: number;
  bowl_volume_short_window: number;
  bowl_volume_long_window: number;
  bowl_volume_min_volume_ratio: number;
  bowl_volume_trend_lookback_days: number;
};

const defaultBacktestParams: BacktestTuningParams = {
  range_lookback_days: 60,
  range_max_width_pct: 65,
  range_volume_ratio: 1.3,
  range_min_price_gain_pct: 0,
  range_max_price_gain_pct: 18,
  range_volume_sustain_days: 3,
  initial_capital: 100000,
  trading_cost_pct: 0.7,
  initial_stop_loss_pct: 5,
  trailing_stop_activation_pct: 8,
  trailing_stop_drawdown_pct: 8,
  pullback_strong_lookback_days: 20,
  pullback_min_pullback_pct: 10,
  pullback_base_hold_days: 3,
  pullback_low_price_volume_price_threshold: 500,
  pullback_low_price_min_volume_lots: 700,
  pullback_technology_only: true,
  vcp_lookback_days: 60,
  vcp_min_uptrend_pct: 12,
  vcp_breakout_volume_ratio: 1,
  vcp_near_pivot_tolerance_pct: 12,
  vcp_max_consolidation_depth_pct: 45,
  high_price_pullback_lookback_days: 20,
  high_price_pullback_market_cap_rank_limit: 50,
  high_price_pullback_min_drop_pct: 15,
  breakout_lookback_days: 252,
  breakout_distance_pct: 10,
  breakout_trend_lookback_days: 20,
  breakout_volume_short_window: 5,
  breakout_volume_long_window: 20,
  bowl_volume_lookback_days: 120,
  bowl_volume_min_drawdown_pct: 20,
  bowl_volume_short_window: 5,
  bowl_volume_long_window: 20,
  bowl_volume_min_volume_ratio: 1.2,
  bowl_volume_trend_lookback_days: 10
};

const navItems: { key: ViewKey; label: string; icon: ReactNode }[] = [
  { key: "overview", label: "總覽", icon: <Activity size={20} /> },
  { key: "stock", label: "個股", icon: <Search size={20} /> },
  { key: "strong", label: "強勢", icon: <TrendingUp size={20} /> },
  { key: "data", label: "資料", icon: <Database size={20} /> },
  { key: "market", label: "產業", icon: <Layers3 size={20} /> },
  { key: "broker", label: "分點", icon: <BriefcaseBusiness size={20} /> },
  { key: "revenue", label: "營收", icon: <TrendingUp size={20} /> },
  { key: "usCalendar", label: "美股", icon: <CalendarClock size={20} /> },
  { key: "etf", label: "ETF", icon: <PieChart size={20} /> },
  { key: "backtest", label: "回測", icon: <SlidersHorizontal size={20} /> }
];

const migrationSteps = [
  { title: "Web", body: "Vite React 已成為正式網站入口，Streamlit 不再負責新 UI。" },
  { title: "API", body: "FastAPI 聚合資料狀態，前端透過 HTTP 取得資料。" },
  { title: "Worker", body: "備份與爬蟲任務獨立跑，適合掛在 NAS 排程。" },
  { title: "NAS", body: "TRADE_DATA_DIR / TRADE_DB_DIR 可直接切到 NAS volume。" }
];

const emptyQuotes: StockOverview["quotes"] = [];
const defaultUsCalendarStart = formatInputDate(new Date());
const defaultUsCalendarEnd = formatInputDate(addDays(new Date(), 30));

export function App() {
  const [activeView, setActiveView] = useState<ViewKey>("overview");
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [errorMessage, setErrorMessage] = useState("");

  const [stockInput, setStockInput] = useState("2330");
  const [stockOverview, setStockOverview] = useState<StockOverview | null>(null);
  const [stockLoading, setStockLoading] = useState(false);
  const [stockUpdating, setStockUpdating] = useState(false);
  const [stockNavigation, setStockNavigation] = useState<StockNavigation | null>(null);
  const [strongStocks, setStrongStocks] = useState<StrongStocks | null>(null);
  const [strongDays, setStrongDays] = useState(7);
  const [strongLimit, setStrongLimit] = useState(10);
  const [strongLoading, setStrongLoading] = useState(false);
  const [priceJob, setPriceJob] = useState<PriceCacheJob | null>(null);
  const [priceJobStarting, setPriceJobStarting] = useState(false);
  const [priceJobScope, setPriceJobScope] = useState<"all" | "range">("range");
  const [priceJobStartCode, setPriceJobStartCode] = useState(1101);
  const [priceJobEndCode, setPriceJobEndCode] = useState(1300);
  const [priceJobDays, setPriceJobDays] = useState(365);
  const [priceJobForce, setPriceJobForce] = useState(false);
  const [priceCacheOverview, setPriceCacheOverview] = useState<PriceCacheOverview | null>(null);
  const [dataSourcesOverview, setDataSourcesOverview] = useState<DataSourcesOverview | null>(null);

  const [marketGroups, setMarketGroups] = useState<MarketMapGroup[]>([]);
  const [selectedGroup, setSelectedGroup] = useState("");
  const [marketTopics, setMarketTopics] = useState<MarketMapTopic[]>([]);
  const [selectedTopic, setSelectedTopic] = useState("");
  const [marketMembers, setMarketMembers] = useState<MarketMapMember[]>([]);

  const [brokerSearch, setBrokerSearch] = useState("");
  const [brokerBranches, setBrokerBranches] = useState<BrokerBranch[]>([]);

  const [revenueMomentum, setRevenueMomentum] = useState<RevenueMomentum | null>(null);
  const [usCalendar, setUsCalendar] = useState<UsMarketCalendar | null>(null);
  const [usCalendarStart, setUsCalendarStart] = useState(defaultUsCalendarStart);
  const [usCalendarEnd, setUsCalendarEnd] = useState(defaultUsCalendarEnd);
  const [usCalendarImportance, setUsCalendarImportance] = useState("all");
  const [usCalendarLoading, setUsCalendarLoading] = useState(false);
  const [activeEtfSnapshots, setActiveEtfSnapshots] = useState<ActiveEtfSnapshots | null>(null);
  const [selectedEtfCode, setSelectedEtfCode] = useState("");
  const [selectedEtfSnapshotDate, setSelectedEtfSnapshotDate] = useState("");
  const [activeEtfChanges, setActiveEtfChanges] = useState<ActiveEtfChanges | null>(null);
  const [backtestConfig, setBacktestConfig] = useState<BacktestConfig | null>(null);
  const [backtestJob, setBacktestJob] = useState<BacktestJob | null>(null);
  const [backtestStarting, setBacktestStarting] = useState(false);
  const [backtestStart, setBacktestStart] = useState(0);
  const [backtestEnd, setBacktestEnd] = useState(9999);
  const [backtestMode, setBacktestMode] = useState("即時選股");
  const [backtestBuyStrategy, setBacktestBuyStrategy] = useState("強勢股回檔量縮止跌");
  const [backtestParams, setBacktestParams] = useState<BacktestTuningParams>(defaultBacktestParams);

  const [newsJob, setNewsJob] = useState<NewsJob | null>(null);
  const [newsStarting, setNewsStarting] = useState(false);

  const [researchSearch, setResearchSearch] = useState("");
  const [researchCompanies, setResearchCompanies] = useState<ResearchCompanies | null>(null);
  const [featureError, setFeatureError] = useState("");
  const [stockError, setStockError] = useState("");

  async function loadOverview() {
    setLoadState("loading");
    setErrorMessage("");
    try {
      const [nextOverview, nextMarketGroups, nextBrokerBranches] = await Promise.all([
        fetchDashboardOverview(),
        fetchMarketMapGroups(),
        fetchBrokerBranches()
      ]);
      setOverview(nextOverview);
      setMarketGroups(nextMarketGroups);
      setBrokerBranches(nextBrokerBranches);

      const defaultGroup = selectedGroup || nextMarketGroups[0]?.group_name || "";
      setSelectedGroup(defaultGroup);
      const nextTopics = await fetchMarketMapTopics(defaultGroup);
      setMarketTopics(nextTopics);

      const defaultTopic = selectedTopic || nextTopics[0]?.topic_name || "";
      setSelectedTopic(defaultTopic);
      setMarketMembers(defaultTopic ? await fetchMarketMapMembers(defaultTopic) : []);
      setLoadState("ready");
    } catch (error) {
      setLoadState("error");
      setErrorMessage(error instanceof Error ? error.message : "API connection failed");
    }
  }

  async function loadStock(nextStockId = stockInput) {
    const normalized = nextStockId.trim();
    if (!normalized) return;
    setStockLoading(true);
    setStockError("");
    try {
      const nextOverview = await fetchStockOverview(normalized);
      setStockOverview(nextOverview);
      if (!nextOverview.found) {
        setStockError(`找不到「${normalized}」的股票主檔資料`);
      }
    } catch (error) {
      setStockError(error instanceof Error ? error.message : "股票資料讀取失敗");
    } finally {
      setStockLoading(false);
    }
  }

  function openStockDetail(code: string, navigation?: StockNavigation | null) {
    const normalized = code.trim();
    if (!normalized) return;
    setStockInput(normalized);
    if (navigation !== undefined) {
      setStockNavigation(navigation);
    }
    setActiveView("stock");
    void loadStock(normalized);
  }

  async function handleStockPriceUpdate() {
    const normalized = stockInput.trim() || stockOverview?.security?.code || "";
    if (!normalized) return;
    setStockUpdating(true);
    setStockError("");
    try {
      const result = await updateStockPriceCache(normalized, 1825);
      if (result.failed_count > 0) {
        setStockError(result.results[0]?.error ?? "價格更新失敗");
      }
      await loadStock(normalized);
    } catch (error) {
      setStockError(error instanceof Error ? error.message : "價格更新失敗");
    } finally {
      setStockUpdating(false);
    }
  }

  async function loadStrongStocks(nextDays = strongDays, nextLimit = strongLimit) {
    const normalizedDays = Math.max(2, Math.min(Number(nextDays) || 7, 365));
    const normalizedLimit = Math.max(1, Math.min(Number(nextLimit) || 10, 50));
    setStrongLoading(true);
    setFeatureError("");
    try {
      setStrongDays(normalizedDays);
      setStrongLimit(normalizedLimit);
      setStrongStocks(await fetchStrongStocks(normalizedDays, normalizedLimit));
    } catch (error) {
      setFeatureError(error instanceof Error ? error.message : "強勢個股資料讀取失敗");
    } finally {
      setStrongLoading(false);
    }
  }

  async function loadPriceCacheOverview() {
    try {
      const [nextPrice, nextSources] = await Promise.all([
        fetchPriceCacheOverview(),
        fetchDataSourcesOverview()
      ]);
      setPriceCacheOverview(nextPrice);
      setDataSourcesOverview(nextSources);
    } catch (error) {
      setFeatureError(error instanceof Error ? error.message : "價格快取狀態讀取失敗");
    }
  }

  async function loadLatestPriceJob() {
    try {
      const nextJob = await fetchLatestPriceCacheJob();
      setPriceJob(nextJob.job ?? null);
    } catch {
      setPriceJob(null);
    }
  }

  async function startBootstrapDataJobs() {
    try {
      const result = await startBootstrapJobs();
      if (result.price_cache?.job) {
        setPriceJob(result.price_cache.job);
      }
    } catch {
      // Opening the app should stay fast even if the background warm-up endpoint is unavailable.
    }
  }

  async function handlePriceJobStart() {
    setPriceJobStarting(true);
    setFeatureError("");
    try {
      const started = await startPriceCacheJob({
        scope: priceJobScope,
        start_code: priceJobScope === "range" ? priceJobStartCode : undefined,
        end_code: priceJobScope === "range" ? priceJobEndCode : undefined,
        days: priceJobDays,
        force: priceJobForce
      });
      if (!started.ok || !started.job_id) {
        setFeatureError(started.error ?? "價格更新任務啟動失敗");
        return;
      }
      const nextJob = await fetchPriceCacheJob(started.job_id);
      setPriceJob(nextJob.job ?? null);
      void loadOverview();
      void loadPriceCacheOverview();
    } catch (error) {
      setFeatureError(error instanceof Error ? error.message : "價格更新任務啟動失敗");
    } finally {
      setPriceJobStarting(false);
    }
  }

  async function loadBrokerBranches(nextSearch = brokerSearch) {
    setBrokerBranches(await fetchBrokerBranches(nextSearch));
  }

  async function loadUsMarketCalendar(
    nextStart = usCalendarStart,
    nextEnd = usCalendarEnd,
    nextImportance = usCalendarImportance
  ) {
    setUsCalendarLoading(true);
    setFeatureError("");
    try {
      setUsCalendarStart(nextStart);
      setUsCalendarEnd(nextEnd);
      setUsCalendarImportance(nextImportance);
      setUsCalendar(await fetchUsMarketCalendar(nextStart, nextEnd, nextImportance));
    } catch (error) {
      setFeatureError(error instanceof Error ? error.message : "美股數據行事曆讀取失敗");
    } finally {
      setUsCalendarLoading(false);
    }
  }

  async function loadFeatureData() {
    setFeatureError("");
    try {
      const [nextRevenue, nextEtfs, nextBacktestConfig] = await Promise.all([
        fetchRevenueMomentum(30),
        fetchActiveEtfSnapshots(500, 30),
        fetchBacktestConfig(),
      ]);
      setRevenueMomentum(nextRevenue);
      setActiveEtfSnapshots(nextEtfs);
      setBacktestConfig(nextBacktestConfig);
      const nextEtfCode = selectedEtfCode || nextEtfs.rows[0]?.etf_code || "";
      const nextEtfDates = nextEtfs.rows.filter((row) => row.etf_code === nextEtfCode);
      const nextEtfSnapshotDate = selectedEtfSnapshotDate && nextEtfDates.some((row) => row.snapshot_date === selectedEtfSnapshotDate)
        ? selectedEtfSnapshotDate
        : nextEtfDates[0]?.snapshot_date || "";
      setSelectedEtfCode(nextEtfCode);
      setSelectedEtfSnapshotDate(nextEtfSnapshotDate);
      setActiveEtfChanges(nextEtfCode ? await fetchActiveEtfChanges(nextEtfCode, nextEtfSnapshotDate) : null);
    } catch (error) {
      setFeatureError(error instanceof Error ? error.message : "Feature data failed");
    }
  }

  async function handleGroupSelect(groupName: string) {
    setSelectedGroup(groupName);
    const nextTopics = await fetchMarketMapTopics(groupName);
    setMarketTopics(nextTopics);
    const nextTopic = nextTopics[0]?.topic_name || "";
    setSelectedTopic(nextTopic);
    setMarketMembers(nextTopic ? await fetchMarketMapMembers(nextTopic) : []);
  }

  async function handleTopicSelect(topicName: string) {
    setSelectedTopic(topicName);
    setMarketMembers(await fetchMarketMapMembers(topicName));
  }

  async function handleEtfSelect(etfCode: string, snapshotDate?: string) {
    const nextSnapshotDate = snapshotDate ?? activeEtfSnapshots?.rows.find((row) => row.etf_code === etfCode)?.snapshot_date ?? "";
    setSelectedEtfCode(etfCode);
    setSelectedEtfSnapshotDate(nextSnapshotDate);
    setActiveEtfChanges(await fetchActiveEtfChanges(etfCode, nextSnapshotDate));
  }

  async function handleBacktestStart() {
    setBacktestStarting(true);
    try {
      const sellStrategies = backtestMode === "歷史回測" ? backtestConfig?.default_sell_strategies ?? [] : [];
      const started = await startBacktestJob({
        start_num: backtestStart,
        end_num: backtestEnd,
        mode: backtestMode,
        selected_strategies: [backtestBuyStrategy],
        selected_sell_strategies: sellStrategies,
        request_delay_sec: 0.02,
        ...backtestParams
      });
      if (!started.ok || !started.job_id) {
        setFeatureError(started.error ?? "Backtest job failed to start");
        return;
      }
      const nextJob = await fetchBacktestJob(started.job_id);
      setBacktestJob(nextJob.job ?? null);
    } finally {
      setBacktestStarting(false);
    }
  }

  async function handleNewsStart() {
    setNewsStarting(true);
    try {
      const started = await startNewsJob();
      if (!started.ok || !started.job_id) {
        setFeatureError(started.error ?? "News job failed to start");
        return;
      }
      const nextJob = await fetchNewsJob(started.job_id);
      setNewsJob(nextJob.job ?? null);
    } finally {
      setNewsStarting(false);
    }
  }

  async function handleResearchSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResearchCompanies(await fetchResearchCompanies(researchSearch));
  }

  function handleStockSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setStockNavigation(null);
    openStockDetail(stockInput, null);
  }

  function handleBrokerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void loadBrokerBranches();
  }

  useEffect(() => {
    void startBootstrapDataJobs();
    void loadOverview();
    void loadStock("2330");
    void loadStrongStocks(7);
    void loadPriceCacheOverview();
    void loadLatestPriceJob();
    void loadUsMarketCalendar(defaultUsCalendarStart, defaultUsCalendarEnd, "all");
    void loadFeatureData();
  }, []);

  useEffect(() => {
    if (!backtestJob || !["queued", "running"].includes(backtestJob.status)) return;
    const timer = window.setInterval(async () => {
      const nextJob = await fetchBacktestJob(backtestJob.job_id);
      if (nextJob.job) {
        setBacktestJob(nextJob.job);
      } else if (!nextJob.ok) {
        setBacktestJob({ ...backtestJob, status: "failed", progress: 1, message: nextJob.error ?? "任務狀態已失效", error: nextJob.error ?? null });
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [backtestJob]);

  useEffect(() => {
    if (!newsJob || !["queued", "running"].includes(newsJob.status)) return;
    const timer = window.setInterval(async () => {
      const nextJob = await fetchNewsJob(newsJob.job_id);
      if (nextJob.job) {
        setNewsJob(nextJob.job);
      } else if (!nextJob.ok) {
        setNewsJob({ ...newsJob, status: "failed", progress: 1, message: nextJob.error ?? "任務狀態已失效", error: nextJob.error ?? null });
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [newsJob]);

  useEffect(() => {
    if (!priceJob || !["queued", "running"].includes(priceJob.status)) return;
    const timer = window.setInterval(async () => {
      const nextJob = await fetchPriceCacheJob(priceJob.job_id);
      if (nextJob.job) {
        setPriceJob(nextJob.job);
        if (nextJob.job.status === "completed") {
          void loadOverview();
          void loadPriceCacheOverview();
          void loadStrongStocks(strongDays, strongLimit);
        }
      } else if (!nextJob.ok) {
        setPriceJob({ ...priceJob, status: "failed", progress: 1, message: nextJob.error ?? "任務狀態已失效", error: nextJob.error ?? null });
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [priceJob, strongDays, strongLimit]);

  const fileSummary = useMemo(() => {
    const files = getAllFiles(overview);
    return { ready: files.filter((file) => file.exists).length, total: files.length };
  }, [overview]);

  const stockQuotes = stockOverview?.quotes ?? emptyQuotes;
  const stockNavigationState = getStockNavigationState(stockNavigation, stockOverview?.security?.code || stockInput);
  const sections = overview?.sections;
  const stockStatus = sections?.stocks.data;
  const marketMap = sections?.market_map.data;
  const broker = sections?.broker.data;

  return (
    <main className="app-shell">
      <aside className="side-nav">
        <div className="brand-mark">
          <span>TL</span>
        </div>
        <nav aria-label="Primary navigation">
          {navItems.map((item) => (
            <button
              className={`nav-item ${activeView === item.key ? "active" : ""}`}
              type="button"
              aria-label={item.label}
              title={item.label}
              key={item.key}
              onClick={() => setActiveView(item.key)}
            >
              {item.icon}
            </button>
          ))}
        </nav>
      </aside>

      <section className={`workspace ${activeView === "stock" ? "compact-workspace" : ""}`}>
        <header className="top-bar">
          <div>
            <p className="eyebrow">Trade Lab Web</p>
            <h1>{viewTitle(activeView)}</h1>
          </div>
          <button className="icon-button" type="button" onClick={() => void loadOverview()} aria-label="Reload API status">
            <RefreshCw size={18} />
          </button>
        </header>

        {loadState === "error" ? (
          <section className="alert-panel">
            <strong>API 尚未連上</strong>
            <span>{errorMessage}</span>
          </section>
        ) : null}

        {featureError ? (
          <section className="alert-panel">
            <strong>部分功能資料尚未載入</strong>
            <span>{featureError}</span>
          </section>
        ) : null}

        {activeView === "overview" ? (
          <OverviewView
            loadState={loadState}
            overview={overview}
            fileSummary={fileSummary}
            stockStatusText={stockStatus ? `${stockStatus.count.toLocaleString()} 檔` : "-"}
            stockStatusMeta={stockStatus?.last_sync_at ?? sections?.stocks.error ?? "not loaded"}
            marketMapCount={marketMap?.topic_count ?? "-"}
            brokerCount={broker?.branch_count ?? "-"}
          />
        ) : null}

        {activeView === "stock" ? (
          <StockView
            stockInput={stockInput}
            stockLoading={stockLoading}
            stockUpdating={stockUpdating}
            stockOverview={stockOverview}
            stockQuotes={stockQuotes}
            stockError={stockError}
            navigation={stockNavigationState}
            onStockInputChange={setStockInput}
            onStockSubmit={handleStockSubmit}
            onPriceUpdate={handleStockPriceUpdate}
            onNavigateStock={(code) => openStockDetail(code)}
          />
        ) : null}

        {activeView === "strong" ? (
          <StrongView
            strongStocks={strongStocks}
            strongDays={strongDays}
            strongLimit={strongLimit}
            strongLoading={strongLoading}
            onStrongParamsChange={loadStrongStocks}
            onStockSelect={(code) => {
              openStockDetail(code, {
                sourceLabel: `強勢個股 ${strongDays}日排行`,
                codes: uniqueCodes(strongStocks?.rows.map((row) => row.code) ?? [])
              });
            }}
          />
        ) : null}

        {activeView === "data" ? (
          <DataUpdateView
            overview={overview}
            dataSourcesOverview={dataSourcesOverview}
            priceCacheOverview={priceCacheOverview}
            priceJob={priceJob}
            starting={priceJobStarting}
            scope={priceJobScope}
            startCode={priceJobStartCode}
            endCode={priceJobEndCode}
            days={priceJobDays}
            force={priceJobForce}
            onScopeChange={setPriceJobScope}
            onStartCodeChange={setPriceJobStartCode}
            onEndCodeChange={setPriceJobEndCode}
            onDaysChange={setPriceJobDays}
            onForceChange={setPriceJobForce}
            onStart={handlePriceJobStart}
          />
        ) : null}

        {activeView === "market" ? (
          <MarketMapView
            marketGroups={marketGroups}
            marketTopics={marketTopics}
            marketMembers={marketMembers}
            selectedGroup={selectedGroup}
            selectedTopic={selectedTopic}
            onGroupSelect={handleGroupSelect}
            onTopicSelect={handleTopicSelect}
            onMemberSelect={(code) => {
              setStockInput(code);
              setActiveView("stock");
              void loadStock(code);
            }}
          />
        ) : null}

        {activeView === "broker" ? (
          <BrokerView
            brokerSearch={brokerSearch}
            brokerOverview={broker}
            brokerBranches={brokerBranches}
            onSearchChange={setBrokerSearch}
            onSearchSubmit={handleBrokerSubmit}
          />
        ) : null}

        {activeView === "revenue" ? (
          <RevenueView
            revenueMomentum={revenueMomentum}
            onStockSelect={(code) => {
              setStockInput(code);
              setActiveView("stock");
              void loadStock(code);
            }}
          />
        ) : null}

        {activeView === "usCalendar" ? (
          <UsMarketCalendarView
            calendar={usCalendar}
            startDate={usCalendarStart}
            endDate={usCalendarEnd}
            importance={usCalendarImportance}
            loading={usCalendarLoading}
            onChange={(nextStart, nextEnd, nextImportance) => void loadUsMarketCalendar(nextStart, nextEnd, nextImportance)}
          />
        ) : null}

        {activeView === "etf" ? (
          <ActiveEtfView
            snapshots={activeEtfSnapshots}
            changes={activeEtfChanges}
            selectedEtfCode={selectedEtfCode}
            selectedEtfSnapshotDate={selectedEtfSnapshotDate}
            onEtfSelect={handleEtfSelect}
            onStockSelect={(code) => {
              setStockInput(code);
              setActiveView("stock");
              void loadStock(code);
            }}
          />
        ) : null}

        {activeView === "backtest" ? (
          <BacktestView
            config={backtestConfig}
            job={backtestJob}
            starting={backtestStarting}
            startNum={backtestStart}
            endNum={backtestEnd}
            mode={backtestMode}
            buyStrategy={backtestBuyStrategy}
            params={backtestParams}
            onStartNumChange={setBacktestStart}
            onEndNumChange={setBacktestEnd}
            onModeChange={setBacktestMode}
            onBuyStrategyChange={setBacktestBuyStrategy}
            onParamsChange={(patch) => setBacktestParams((current) => ({ ...current, ...patch }))}
            onStart={handleBacktestStart}
            onStockSelect={(code) => {
              openStockDetail(code, {
                sourceLabel: `選股結果：${backtestBuyStrategy}`,
                codes: uniqueCodes(normalizeBacktestResults(backtestJob?.result_preview).map((row) => row.code))
              });
            }}
          />
        ) : null}
      </section>
    </main>
  );
}

function OverviewView({
  loadState,
  overview,
  fileSummary,
  stockStatusText,
  stockStatusMeta,
  marketMapCount,
  brokerCount
}: {
  loadState: LoadState;
  overview: DashboardOverview | null;
  fileSummary: { ready: number; total: number };
  stockStatusText: string;
  stockStatusMeta: string;
  marketMapCount: number | string;
  brokerCount: number | string;
}) {
  return (
    <>
      <section className="status-grid" aria-label="System status">
        <MetricCard
          icon={<ShieldCheck size={20} />}
          label="網站架構"
          value={overview?.summary.architecture ?? loadState}
          meta={overview ? `${overview.summary.frontend} + ${overview.summary.backend}` : "waiting for API"}
          tone={loadState === "ready" ? "good" : loadState === "error" ? "bad" : "neutral"}
        />
        <MetricCard icon={<Database size={20} />} label="股票主檔" value={stockStatusText} meta={stockStatusMeta} tone="good" />
        <MetricCard
          icon={<HardDrive size={20} />}
          label="資料檔案"
          value={`${fileSummary.ready}/${fileSummary.total}`}
          meta={overview?.runtime.paths.db_dir ?? "local / NAS path"}
          tone={fileSummary.ready > 0 ? "good" : "neutral"}
        />
        <MetricCard icon={<Layers3 size={20} />} label="產業題材" value={String(marketMapCount)} meta="Market Map read-only" />
        <MetricCard icon={<BriefcaseBusiness size={20} />} label="券商分點" value={String(brokerCount)} meta="本地官方匯入" />
        <MetricCard icon={<Wrench size={20} />} label="Worker" value="ready" meta="backup / price cache commands" />
      </section>

      <section className="content-grid">
        <article className="main-panel">
          <div className="section-title">
            <Layers3 size={20} />
            <h2>系統搬遷路線</h2>
          </div>
          <div className="timeline">
            {migrationSteps.map((step, index) => (
              <div className="timeline-item" key={step.title}>
                <span className="timeline-index">{index + 1}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="data-panel">
          <div className="section-title">
            <BadgeCheck size={20} />
            <h2>功能狀態</h2>
          </div>
          <div className="summary-list">
            <SummaryRow label="Dashboard API" value="已接上" ok />
            <SummaryRow label="個股 Overview" value="已接上" ok />
            <SummaryRow label="產業地圖瀏覽" value="已接上" ok />
            <SummaryRow label="券商分點列表" value="已接上" ok />
            <SummaryRow label="NAS Compose" value="已設定" ok />
          </div>
        </article>
      </section>
    </>
  );
}

function StockView({
  stockInput,
  stockLoading,
  stockUpdating,
  stockOverview,
  stockQuotes,
  stockError,
  navigation,
  onStockInputChange,
  onStockSubmit,
  onPriceUpdate,
  onNavigateStock
}: {
  stockInput: string;
  stockLoading: boolean;
  stockUpdating: boolean;
  stockOverview: StockOverview | null;
  stockQuotes: StockOverview["quotes"];
  stockError: string;
  navigation: StockNavigationState | null;
  onStockInputChange: (value: string) => void;
  onStockSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onPriceUpdate: () => Promise<void>;
  onNavigateStock: (code: string) => void;
}) {
  return (
    <>
      <section className="stock-top-grid">
        <article className="stock-panel stock-query-panel">
          <div className="section-title">
            <Search size={20} />
            <h2>股票主檔查詢</h2>
          </div>
          <form className="stock-search" onSubmit={onStockSubmit}>
            <input
              value={stockInput}
              onChange={(event) => onStockInputChange(event.target.value)}
              placeholder="輸入代號或名稱，例如 2330 / 台積電"
              aria-label="Stock code"
            />
            <button type="submit">{stockLoading ? "查詢中" : "查詢"}</button>
            <button type="button" onClick={() => void onPriceUpdate()} disabled={stockUpdating || stockLoading}>
              {stockUpdating ? "更新中" : "更新價格"}
            </button>
          </form>
          {navigation ? (
            <div className="stock-list-navigation">
              <span>{navigation.sourceLabel}</span>
              <strong>{navigation.currentIndex + 1} / {navigation.total}</strong>
              <div>
                <button type="button" onClick={() => navigation.previousCode && onNavigateStock(navigation.previousCode)} disabled={!navigation.previousCode || stockLoading}>
                  <ChevronLeft size={16} />
                  上一檔
                </button>
                <button type="button" onClick={() => navigation.nextCode && onNavigateStock(navigation.nextCode)} disabled={!navigation.nextCode || stockLoading}>
                  下一檔
                  <ChevronRight size={16} />
                </button>
              </div>
            </div>
          ) : null}
          {stockError ? <p className="inline-error">{stockError}</p> : null}
          <StockIdentity stockOverview={stockOverview} />
        </article>
      </section>

      <section className="broker-panel stock-detail-panel">
        <div className="section-title">
          <Activity size={20} />
          <h2>K 線與成交量</h2>
        </div>
        <CandlestickVolumeChart quotes={stockQuotes} />
      </section>

      <section className="broker-panel stock-detail-panel">
        <div className="section-title">
          <BriefcaseBusiness size={20} />
          <h2>券商分點摘要</h2>
        </div>
        {stockOverview?.broker_summary ? (
          <div className="broker-grid">
            <BrokerRank title="買超分點" rows={stockOverview.broker_summary.buy_rank} side="buy" />
            <BrokerRank title="賣超分點" rows={stockOverview.broker_summary.sell_rank} side="sell" />
          </div>
        ) : (
          <p className="muted">目前這檔股票沒有本地官方分點匯入資料。</p>
        )}
      </section>

      <section className="quotes-panel stock-detail-panel">
        <div className="section-title">
          <Activity size={20} />
          <h2>三大法人買賣超</h2>
        </div>
        {(stockOverview?.institutional_trading ?? []).length ? (
          <InstitutionalTradingTable rows={stockOverview?.institutional_trading ?? []} />
        ) : (
          <p className="muted">目前本地 chip_cache.db 沒有這檔股票的三大法人買賣資料。</p>
        )}
      </section>

      <section className="stock-local-strip">
        <div className="section-title">
          <BarChart3 size={18} />
          <h2>個股本地資料</h2>
        </div>
        {stockOverview?.found ? (
          <div className="stock-data-grid compact">
            <MiniDataCard label="價格列數" value={stockOverview.price_cache?.row_count ?? 0} />
            <MiniDataCard label="快取狀態" value={stockOverview.price_cache?.fetch_status ?? "-"} />
            <MiniDataCard label="最後收盤" value={formatPrice(stockOverview.latest_quote?.close)} />
            <MiniDataCard label="漲跌幅" value={formatChangePct(stockOverview.latest_quote?.change_pct)} />
            <MiniDataCard label="分點日期" value={stockOverview.broker_summary?.trade_date ?? "尚無本地匯入"} />
          </div>
        ) : (
          <p className="muted">輸入股票代號或名稱後會讀取本地 DB 狀態。</p>
        )}
      </section>
    </>
  );
}

function InstitutionalTradingTable({ rows }: { rows: StockOverview["institutional_trading"] }) {
  return (
    <div className="institutional-table">
      <div className="institutional-row institutional-header">
        <span>日期</span>
        <span>外資(張)</span>
        <span>投信(張)</span>
        <span>自營(張)</span>
        <span>合計(張)</span>
      </div>
      {rows.map((row) => (
        <div className="institutional-row" key={`${row.trade_date}-${row.market}-${row.code}`}>
          <span>{row.trade_date}</span>
          <strong className={toneClass(row.foreign_net)}>{formatLots(row.foreign_net)}</strong>
          <strong className={toneClass(row.trust_net)}>{formatLots(row.trust_net)}</strong>
          <strong className={toneClass(row.dealer_net)}>{formatLots(row.dealer_net)}</strong>
          <strong className={toneClass(row.total_net)}>{formatLots(row.total_net)}</strong>
        </div>
      ))}
    </div>
  );
}

function StrongView({
  strongStocks,
  strongDays,
  strongLimit,
  strongLoading,
  onStrongParamsChange,
  onStockSelect
}: {
  strongStocks: StrongStocks | null;
  strongDays: number;
  strongLimit: number;
  strongLoading: boolean;
  onStrongParamsChange: (days: number, limit?: number) => Promise<void>;
  onStockSelect: (code: string) => void;
}) {
  return (
    <section className="broker-panel">
      <div className="section-title with-controls">
        <div className="title-inline">
          <TrendingUp size={20} />
          <h2>強勢個股</h2>
        </div>
        <div className="range-controls" aria-label="Strong stock range">
          <button className={strongDays === 5 ? "active" : ""} type="button" onClick={() => void onStrongParamsChange(5, strongLimit)}>5日</button>
          <button className={strongDays === 7 ? "active" : ""} type="button" onClick={() => void onStrongParamsChange(7, strongLimit)}>1週</button>
          <button className={strongDays === 30 ? "active" : ""} type="button" onClick={() => void onStrongParamsChange(30, strongLimit)}>1月</button>
          <label>
            <NumericInput
              value={strongDays}
              min={2}
              max={365}
              onValueChange={(value) => void onStrongParamsChange(value, strongLimit)}
            />
            日
          </label>
          <label>
            <NumericInput
              value={strongLimit}
              min={1}
              max={50}
              onValueChange={(value) => void onStrongParamsChange(strongDays, value)}
            />
            檔
          </label>
        </div>
      </div>
      <StrongStocksList stocks={strongStocks} loading={strongLoading} onStockSelect={onStockSelect} />
    </section>
  );
}

function DataUpdateView({
  overview,
  dataSourcesOverview,
  priceCacheOverview,
  priceJob,
  starting,
  scope,
  startCode,
  endCode,
  days,
  force,
  onScopeChange,
  onStartCodeChange,
  onEndCodeChange,
  onDaysChange,
  onForceChange,
  onStart
}: {
  overview: DashboardOverview | null;
  dataSourcesOverview: DataSourcesOverview | null;
  priceCacheOverview: PriceCacheOverview | null;
  priceJob: PriceCacheJob | null;
  starting: boolean;
  scope: "all" | "range";
  startCode: number;
  endCode: number;
  days: number;
  force: boolean;
  onScopeChange: (scope: "all" | "range") => void;
  onStartCodeChange: (value: number) => void;
  onEndCodeChange: (value: number) => void;
  onDaysChange: (value: number) => void;
  onForceChange: (value: boolean) => void;
  onStart: () => Promise<void>;
}) {
  const stockStatus = overview?.sections.stocks.data;
  const history = priceCacheOverview?.history;
  const meta = priceCacheOverview?.meta;
  const jobIsRunning = priceJob ? ["queued", "running"].includes(priceJob.status) : false;
  const sources = dataSourcesOverview?.sources ?? [];
  const stockMasterSource = sources.find((source) => source.key === "stock_master");

  return (
    <>
      <section className="status-grid">
        <MetricCard icon={<Database size={20} />} label="股票主檔" value={stockStatus ? `${stockStatus.count.toLocaleString()} 檔` : "-"} meta={stockMasterSource?.latest_date ?? "本機 stocks.db"} tone="good" />
        <MetricCard icon={<BarChart3 size={20} />} label="價格快取" value={history ? `${history.symbol_count.toLocaleString()} 檔` : "-"} meta={history ? `${history.row_count.toLocaleString()} 筆` : "本機 price_cache.db"} tone="good" />
        <MetricCard icon={<CalendarClock size={20} />} label="行情區間" value={history?.last_trade_date ?? "-"} meta={history?.first_trade_date ? `${history.first_trade_date} 起` : "尚未讀取"} />
      </section>

      <section className="data-panel wide-panel">
        <div className="section-title">
          <Database size={20} />
          <h2>資料源總控台</h2>
        </div>
        {sources.length ? (
          <div className="data-source-grid">
            {sources.map((source) => (
              <DataSourceCard
                key={source.key}
                source={source}
                onAction={(key) => {
                  if (key === "price_cache") {
                    document.getElementById("price-cache-job-form")?.scrollIntoView({ behavior: "smooth", block: "center" });
                  }
                }}
              />
            ))}
          </div>
        ) : (
          <p className="muted">資料源狀態尚未載入。</p>
        )}
      </section>

      <section className="content-grid">
        <article className="main-panel">
          <div className="section-title">
            <RefreshCw size={20} />
            <h2>價格爬蟲任務</h2>
          </div>
          <form id="price-cache-job-form" className="data-job-form" onSubmit={(event) => {
            event.preventDefault();
            void onStart();
          }}>
            <label>
              <span>範圍</span>
              <select value={scope} onChange={(event) => onScopeChange(event.target.value as "all" | "range")}>
                <option value="range">代號區間</option>
                <option value="all">全部股票</option>
              </select>
            </label>
            <label>
              <span>起始</span>
              <NumericInput value={startCode} min={0} max={9999} disabled={scope === "all"} onValueChange={onStartCodeChange} />
            </label>
            <label>
              <span>結束</span>
              <NumericInput value={endCode} min={0} max={9999} disabled={scope === "all"} onValueChange={onEndCodeChange} />
            </label>
            <label>
              <span>天數</span>
              <NumericInput value={days} min={30} max={2200} onValueChange={onDaysChange} />
            </label>
            <label className="checkbox-line">
              <input type="checkbox" checked={force} onChange={(event) => onForceChange(event.target.checked)} />
              <span>強制重抓</span>
            </label>
            <button type="submit" disabled={starting || jobIsRunning}>
              {starting ? "啟動中" : jobIsRunning ? "任務執行中" : "開始更新"}
            </button>
          </form>
        </article>

        <article className="data-panel">
          <div className="section-title">
            <ShieldCheck size={20} />
            <h2>本機資料狀態</h2>
          </div>
          <div className="stock-data-grid">
            <MiniDataCard label="可用快取" value={meta?.ready_count ?? 0} />
            <MiniDataCard label="失敗快取" value={meta?.failed_count ?? 0} />
            <MiniDataCard label="最後更新" value={meta?.last_updated_at ?? "-"} />
            <MiniDataCard label="DB 位置" value={overview?.runtime.paths.db_dir ?? "data"} />
          </div>
        </article>
      </section>

      <section className="broker-panel">
        <div className="section-title">
          <Activity size={20} />
          <h2>任務進度</h2>
        </div>
        <JobProgress job={priceJob} emptyText="尚未啟動價格更新任務。" />
      </section>
    </>
  );
}

function DataSourceCard({ source, onAction }: { source: DataSourceStatus; onAction?: (key: string) => void }) {
  return (
    <article className={`data-source-card ${sourceStatusClass(source.status)}`}>
      <div className="data-source-head">
        <div>
          <span className="source-status-pill">{sourceStatusLabel(source.status)}</span>
          <h3>{source.title}</h3>
        </div>
        <Database size={18} />
      </div>
      <p>{source.description}</p>
      <div className="data-source-metrics">
        <MiniDataCard label="最新日期" value={source.latest_date ?? "-"} />
        <MiniDataCard label="資料筆數" value={source.row_count ?? 0} />
        <MiniDataCard label="標的數" value={source.symbol_count ?? "-"} />
        <MiniDataCard label="資料庫" value={source.db_file ?? source.update_mode} />
      </div>
      <div className="data-source-foot">
        <span>{source.note ?? "等待下一階段接入。"}</span>
        <button type="button" disabled={!source.action_enabled} onClick={() => onAction?.(source.key)}>{source.action_label}</button>
      </div>
    </article>
  );
}

function MarketMapView({
  marketGroups,
  marketTopics,
  marketMembers,
  selectedGroup,
  selectedTopic,
  onGroupSelect,
  onTopicSelect,
  onMemberSelect
}: {
  marketGroups: MarketMapGroup[];
  marketTopics: MarketMapTopic[];
  marketMembers: MarketMapMember[];
  selectedGroup: string;
  selectedTopic: string;
  onGroupSelect: (groupName: string) => Promise<void>;
  onTopicSelect: (topicName: string) => Promise<void>;
  onMemberSelect: (code: string) => void;
}) {
  return (
    <section className="market-map-panel">
      <div className="section-title">
        <Layers3 size={20} />
        <h2>產業地圖</h2>
      </div>
      <div className="group-grid">
        {marketGroups.map((group) => (
          <button
            className={`group-card ${selectedGroup === group.group_name ? "active" : ""}`}
            key={group.group_name}
            type="button"
            onClick={() => void onGroupSelect(group.group_name)}
          >
            <div>
              <strong>{group.display_name || group.group_name}</strong>
              <span>{group.is_tech ? "科技主線" : "一般產業"}</span>
            </div>
            <dl>
              <div>
                <dt>題材</dt>
                <dd>{group.topic_count.toLocaleString()}</dd>
              </div>
              <div>
                <dt>公司</dt>
                <dd>{group.company_count.toLocaleString()}</dd>
              </div>
            </dl>
          </button>
        ))}
      </div>
      <div className="topic-table" aria-label="Market map topics">
        {marketTopics.slice(0, 16).map((topic) => (
          <button
            className={`topic-row ${selectedTopic === topic.topic_name ? "active" : ""}`}
            key={topic.topic_name}
            type="button"
            onClick={() => void onTopicSelect(topic.topic_name)}
          >
            <div>
              <strong>{topic.display_name || topic.topic_name}</strong>
              <span>{topic.parent_industry || topic.topic_type}</span>
            </div>
            <em>{topic.company_count.toLocaleString()} 檔</em>
          </button>
        ))}
      </div>
      <div className="member-strip">
        {marketMembers.slice(0, 24).map((member) => (
          <button className="member-chip" type="button" key={`${member.topic_name}-${member.code}`} onClick={() => onMemberSelect(member.code)}>
            <strong>{member.name_zh}</strong>
            <span>{member.code}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function BrokerView({
  brokerSearch,
  brokerOverview,
  brokerBranches,
  onSearchChange,
  onSearchSubmit
}: {
  brokerSearch: string;
  brokerOverview: DashboardOverview["sections"]["broker"]["data"] | undefined;
  brokerBranches: BrokerBranch[];
  onSearchChange: (value: string) => void;
  onSearchSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <>
      <section className="status-grid">
        <MetricCard icon={<BriefcaseBusiness size={20} />} label="分點名稱" value={String(brokerOverview?.branch_count ?? "-")} />
        <MetricCard icon={<Database size={20} />} label="報告數" value={String(brokerOverview?.report_count ?? "-")} />
        <MetricCard icon={<Activity size={20} />} label="最新交易日" value={brokerOverview?.latest_trade_date || "-"} />
      </section>
      <section className="broker-panel">
        <div className="section-title">
          <Search size={20} />
          <h2>券商分點列表</h2>
        </div>
        <form className="stock-search" onSubmit={onSearchSubmit}>
          <input value={brokerSearch} onChange={(event) => onSearchChange(event.target.value)} placeholder="搜尋券商分點" aria-label="Broker search" />
          <button type="submit">搜尋</button>
        </form>
        <div className="broker-list">
          {brokerBranches.length ? (
            brokerBranches.map((branch) => (
              <div className="broker-list-row" key={branch.broker_name}>
                <strong>{branch.broker_name}</strong>
                <span>{branch.stock_count.toLocaleString()} 檔</span>
                <em>{formatShares(branch.total_net_shares)}</em>
              </div>
            ))
          ) : (
            <p className="muted">目前本地官方分點資料庫沒有可列出的分點。</p>
          )}
        </div>
      </section>
    </>
  );
}

function RevenueView({
  revenueMomentum,
  onStockSelect
}: {
  revenueMomentum: RevenueMomentum | null;
  onStockSelect: (code: string) => void;
}) {
  const rows = revenueMomentum?.rows ?? [];
  const usedMonths = revenueMomentum?.summary?.used_months ?? [];
  return (
    <>
      <section className="status-grid">
        <MetricCard icon={<TrendingUp size={20} />} label="營收月份" value={revenueMomentum?.report_month ?? "-"} />
        <MetricCard icon={<Database size={20} />} label="近 6 月排行" value={String(rows.length)} meta={usedMonths.length ? `${usedMonths[0]} 到 ${usedMonths[usedMonths.length - 1]}` : "近 6 個月"} />
        <MetricCard icon={<ShieldCheck size={20} />} label="判斷方式" value="成長加速度" meta="成長比例慢慢拉高" />
      </section>
      <section className="data-panel wide-panel">
        <div className="section-title">
          <TrendingUp size={20} />
          <h2>月營收動能排行</h2>
        </div>
        {rows.length ? (
          <div className="dense-table revenue-table">
            <div className="dense-row table-header" aria-hidden="true">
              <span>公司</span>
              <span>代號</span>
              <span>產業</span>
              <span>營收趨勢</span>
              <span>分數</span>
              <span>期間成長</span>
              <span>加速度</span>
              <span>加速段</span>
            </div>
            {rows.map((row) => (
              <button className="dense-row" type="button" key={`${row.report_month}-${row.code}`} onClick={() => onStockSelect(row.code)}>
                <strong>{row.name_zh}</strong>
                <span>{row.code}</span>
                <span>{row.industry ?? "-"}</span>
                <Sparkline values={(row.revenue_history ?? []).map((point) => Number(point.current_revenue ?? 0)).filter((value) => value > 0)} rising={(row.slope_pct ?? 0) >= 0} />
                <em>{formatScore(row.trend_score)}</em>
                <em className={toneClass(row.trend_growth_pct)}>{formatPct(row.trend_growth_pct)}</em>
                <em className={toneClass(row.growth_acceleration_pct)}>{formatPct(row.growth_acceleration_pct)}</em>
                <em>{formatStepCount(row.accelerating_step_count, row.growth_rates?.length)}</em>
              </button>
            ))}
          </div>
        ) : (
          <p className="muted">目前沒有符合趨勢條件的月營收資料。之後 worker 補更多月份後，這裡會更準。</p>
        )}
      </section>
    </>
  );
}

function UsMarketCalendarView({
  calendar,
  startDate,
  endDate,
  importance,
  loading,
  onChange
}: {
  calendar: UsMarketCalendar | null;
  startDate: string;
  endDate: string;
  importance: string;
  loading: boolean;
  onChange: (startDate: string, endDate: string, importance: string) => void;
}) {
  const rows = calendar?.rows ?? [];
  const highCount = rows.filter((row) => row.importance === "high").length;
  const nextHigh = rows.find((row) => row.importance === "high");

  function applyWindow(days: number) {
    const nextStart = formatInputDate(new Date());
    const nextEnd = formatInputDate(addDays(new Date(), days));
    onChange(nextStart, nextEnd, importance);
  }

  return (
    <>
      <section className="status-grid">
        <MetricCard icon={<CalendarClock size={20} />} label="事件數" value={String(calendar?.event_count ?? rows.length)} meta={calendar?.source_label ?? "本機行事曆"} />
        <MetricCard icon={<Activity size={20} />} label="高重要性" value={String(highCount)} meta={nextHigh ? `${nextHigh.date} ${nextHigh.event}` : "目前區間無高重要性"} />
        <MetricCard icon={<ShieldCheck size={20} />} label="資料狀態" value={calendar?.source === "mock" ? "Mock" : "Live"} meta={`${startDate} 到 ${endDate}`} />
      </section>

      <section className="data-panel wide-panel">
        <div className="section-title with-controls">
          <div>
            <CalendarClock size={20} />
            <h2>美股數據公布行事曆</h2>
          </div>
          <div className="calendar-quick-actions" aria-label="Calendar quick range">
            <button type="button" onClick={() => applyWindow(7)}>7 天</button>
            <button type="button" onClick={() => applyWindow(30)}>30 天</button>
            <button type="button" onClick={() => applyWindow(90)}>90 天</button>
          </div>
        </div>

        <div className="calendar-controls">
          <label>
            起始日期
            <input type="date" value={startDate} onChange={(event) => onChange(event.target.value, endDate, importance)} />
          </label>
          <label>
            結束日期
            <input type="date" value={endDate} onChange={(event) => onChange(startDate, event.target.value, importance)} />
          </label>
          <label>
            重要性
            <select value={importance} onChange={(event) => onChange(startDate, endDate, event.target.value)}>
              <option value="all">全部</option>
              <option value="high">高</option>
              <option value="medium">中</option>
              <option value="low">低</option>
            </select>
          </label>
        </div>

        {loading ? <p className="muted">讀取美股行事曆...</p> : null}
        {rows.length ? (
          <div className="calendar-event-list">
            {rows.map((row) => (
              <div className="calendar-event-row" key={`${row.date}-${row.time}-${row.event}`}>
                <div className="calendar-date-block">
                  <strong>{formatMonthDay(row.date)}</strong>
                  <span>{weekdayLabel(row.date)} {row.time}</span>
                </div>
                <div className="calendar-event-main">
                  <div className="calendar-event-title">
                    <span className={`importance-pill ${importanceClass(row.importance)}`}>{importanceLabel(row.importance)}</span>
                    <strong>{row.event}</strong>
                  </div>
                  <span>{row.category}｜{row.market_impact}</span>
                </div>
                <div className="calendar-event-values">
                  <MetricTiny label="前值" value={row.previous ?? "-"} />
                  <MetricTiny label="預期" value={row.forecast ?? "-"} />
                  <MetricTiny label="公布" value={row.actual ?? "待公布"} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">目前這個日期區間沒有行事曆事件。</p>
        )}
      </section>
    </>
  );
}

function ActiveEtfView({
  snapshots,
  changes,
  selectedEtfCode,
  selectedEtfSnapshotDate,
  onEtfSelect,
  onStockSelect
}: {
  snapshots: ActiveEtfSnapshots | null;
  changes: ActiveEtfChanges | null;
  selectedEtfCode: string;
  selectedEtfSnapshotDate: string;
  onEtfSelect: (etfCode: string, snapshotDate?: string) => Promise<void>;
  onStockSelect: (code: string) => void;
}) {
  const summary = snapshots?.summary;
  const rows = snapshots?.rows ?? [];
  const etfGroups = useMemo(() => groupEtfSnapshots(rows), [rows]);
  const selectedGroup = etfGroups.find((group) => group.etf_code === selectedEtfCode) ?? etfGroups[0] ?? null;
  const selectedSnapshot = selectedGroup?.snapshots.find((row) => row.snapshot_date === selectedEtfSnapshotDate) ?? selectedGroup?.snapshots[0] ?? null;
  const selectedDate = selectedSnapshot?.snapshot_date ?? selectedEtfSnapshotDate;
  return (
    <>
      <section className="status-grid">
        <MetricCard icon={<PieChart size={20} />} label="主動 ETF" value={String(summary?.etf_count ?? "-")} />
        <MetricCard icon={<CalendarClock size={20} />} label="一個月快照" value={String(summary?.snapshot_count ?? "-")} meta={`${summary?.window_start_date ?? "-"} 到 ${summary?.window_end_date ?? "-"}`} />
        <MetricCard icon={<Activity size={20} />} label="選取日期" value={selectedDate || "-"} />
      </section>
      <section className="content-grid">
        <article className="data-panel">
          <div className="section-title">
            <PieChart size={20} />
            <h2>ETF 快照</h2>
          </div>
          <div className="etf-list">
            {etfGroups.map((group) => (
              <button
                className={`etf-row ${selectedEtfCode === group.etf_code ? "active" : ""}`}
                type="button"
                key={group.etf_code}
                onClick={() => void onEtfSelect(group.etf_code, group.latest.snapshot_date)}
              >
                <div>
                  <strong>{group.etf_name || group.etf_code}</strong>
                  <span>{group.etf_code}｜{group.snapshots.length} 個日期｜最新 {group.latest.snapshot_date}</span>
                </div>
                <em>{group.latest.change_count.toLocaleString()} 筆</em>
              </button>
            ))}
          </div>
        </article>
        <article className="data-panel">
          <div className="section-title">
            <Activity size={20} />
            <h2>成分異動</h2>
          </div>
          <div className="etf-date-panel">
            <label>
              快照日期
              <select
                value={selectedDate}
                onChange={(event) => selectedGroup && void onEtfSelect(selectedGroup.etf_code, event.target.value)}
                disabled={!selectedGroup}
              >
                {(selectedGroup?.snapshots ?? []).map((row) => (
                  <option value={row.snapshot_date} key={row.snapshot_date}>
                    {row.snapshot_date}｜{row.change_count.toLocaleString()} 筆
                  </option>
                ))}
              </select>
            </label>
            {selectedSnapshot ? (
              <div className="etf-date-meta">
                <span>{selectedSnapshot.from_date ?? "-"} 到 {selectedSnapshot.to_date ?? "-"}</span>
                <span>新增 {selectedSnapshot.add_count}｜加碼 {selectedSnapshot.increase_count}｜減碼 {selectedSnapshot.decrease_count}｜刪除 {selectedSnapshot.remove_count}</span>
              </div>
            ) : null}
          </div>
          {(changes?.rows ?? []).length ? (
            <div className="dense-table etf-change-table">
              {changes?.rows.slice(0, 18).map((row) => (
                <button className="dense-row" type="button" key={`${row.stock_code}-${row.change_label}-${row.weight_delta}`} onClick={() => row.stock_code && onStockSelect(row.stock_code)}>
                  <strong>{row.stock_name || row.stock_code}</strong>
                  <span>{row.stock_code ?? "-"}</span>
                  <span>{row.change_label ?? "-"}</span>
                  <em className={toneClass(row.weight_delta)}>{formatPct(row.weight_delta)}</em>
                </button>
              ))}
            </div>
          ) : (
            <p className="muted">目前這檔 ETF 沒有可顯示的本地異動明細。</p>
          )}
        </article>
      </section>
    </>
  );
}

function groupEtfSnapshots(rows: ActiveEtfSnapshot[]) {
  const byEtf = new Map<string, ActiveEtfSnapshot[]>();
  rows.forEach((row) => {
    const current = byEtf.get(row.etf_code) ?? [];
    current.push(row);
    byEtf.set(row.etf_code, current);
  });
  return Array.from(byEtf.entries())
    .map(([etfCode, snapshots]) => {
      const sortedSnapshots = [...snapshots].sort((a, b) => b.snapshot_date.localeCompare(a.snapshot_date));
      const latest = sortedSnapshots[0];
      return {
        etf_code: etfCode,
        etf_name: latest?.etf_name ?? null,
        latest,
        snapshots: sortedSnapshots
      };
    })
    .filter((group): group is { etf_code: string; etf_name: string | null; latest: ActiveEtfSnapshot; snapshots: ActiveEtfSnapshot[] } => Boolean(group.latest))
    .sort((a, b) => {
      const dateCompare = b.latest.snapshot_date.localeCompare(a.latest.snapshot_date);
      if (dateCompare !== 0) return dateCompare;
      return a.etf_code.localeCompare(b.etf_code);
    });
}

function BacktestView({
  config,
  job,
  starting,
  startNum,
  endNum,
  mode,
  buyStrategy,
  params,
  onStartNumChange,
  onEndNumChange,
  onModeChange,
  onBuyStrategyChange,
  onParamsChange,
  onStart,
  onStockSelect
}: {
  config: BacktestConfig | null;
  job: BacktestJob | null;
  starting: boolean;
  startNum: number;
  endNum: number;
  mode: string;
  buyStrategy: string;
  params: BacktestTuningParams;
  onStartNumChange: (value: number) => void;
  onEndNumChange: (value: number) => void;
  onModeChange: (value: string) => void;
  onBuyStrategyChange: (value: string) => void;
  onParamsChange: (patch: Partial<BacktestTuningParams>) => void;
  onStart: () => Promise<void>;
  onStockSelect: (code: string) => void;
}) {
  const resultRows = normalizeBacktestResults(job?.result_preview);
  return (
    <>
      <section className="status-grid">
        <MetricCard icon={<SlidersHorizontal size={20} />} label="買入策略" value={String(config?.buy_strategies.length ?? "-")} />
        <MetricCard icon={<ShieldCheck size={20} />} label="賣出策略" value={String(config?.sell_strategies.length ?? "-")} />
        <MetricCard icon={<Wrench size={20} />} label="任務狀態" value={job?.status ?? "ready"} meta={job?.message ?? "背景 job API 已接上"} />
      </section>
      <section className="broker-panel">
        <div className="section-title">
          <Activity size={20} />
          <h2>選股任務</h2>
        </div>
        <div className="control-grid">
          <label>
            起始代碼
            <NumericInput value={startNum} min={0} max={9999} onValueChange={onStartNumChange} />
          </label>
          <label>
            結束代碼
            <NumericInput value={endNum} min={0} max={9999} onValueChange={onEndNumChange} />
          </label>
          <label>
            模式
            <select value={mode} onChange={(event) => onModeChange(event.target.value)}>
              <option value="即時選股">即時選股</option>
              <option value="歷史回測">歷史回測</option>
            </select>
          </label>
          <label>
            買入策略
            <select value={buyStrategy} onChange={(event) => onBuyStrategyChange(event.target.value)}>
              {(config?.buy_strategies ?? []).map((strategy) => (
                <option value={strategy.key} key={strategy.key}>{strategy.title}</option>
              ))}
            </select>
          </label>
        </div>
        <BacktestParamPanel strategy={buyStrategy} mode={mode} params={params} onParamsChange={onParamsChange} />
        <div className="job-runner">
          <div>
            <strong>{String(startNum).padStart(4, "0")} - {String(endNum).padStart(4, "0")}｜{mode}｜{buyStrategy}</strong>
            <span>建議先小範圍測試；大範圍掃描之後會改放 NAS worker 排程與任務佇列。</span>
          </div>
          <button type="button" onClick={() => void onStart()} disabled={starting || job?.status === "queued" || job?.status === "running"}>
            {starting ? "啟動中" : "開始"}
          </button>
        </div>
        {job ? (
          <div className="job-status">
            <span style={{ width: `${Math.max(4, Math.round((job.progress || 0) * 100))}%` }} />
            <strong>{job.message}</strong>
            <em>{job.result_count !== undefined ? `${job.result_count} 筆結果` : job.error ?? job.job_id}</em>
          </div>
        ) : null}
      </section>
      <section className="content-grid">
        <BacktestResultsPanel job={job} rows={resultRows} onStockSelect={onStockSelect} />
        <StrategyPanel title="買入策略" rows={config?.buy_strategies ?? []} defaults={config?.default_buy_strategies ?? []} />
      </section>
      <section className="content-grid">
        <StrategyPanel title="賣出策略" rows={config?.sell_strategies ?? []} defaults={config?.default_sell_strategies ?? []} />
      </section>
    </>
  );
}

type BacktestResultRow = {
  symbol: string;
  code: string;
  name: string;
  price: number | null;
  score: number | null;
  rsSpreadPct: number | null;
  volumeRatio: number | null;
  returnPct: number | null;
  totalTrades: number | null;
  positiveReasons: string[];
  cautionReasons: string[];
};

function BacktestResultsPanel({
  job,
  rows,
  onStockSelect
}: {
  job: BacktestJob | null;
  rows: BacktestResultRow[];
  onStockSelect: (code: string) => void;
}) {
  const completed = job?.status === "completed";
  return (
    <article className="data-panel backtest-results-panel">
      <div className="section-title">
        <BadgeCheck size={20} />
        <h2>選股結果</h2>
      </div>
      {!job ? (
        <p className="muted">尚未啟動選股任務。</p>
      ) : rows.length ? (
        <>
          <div className="backtest-result-summary">
            <strong>{job.result_count ?? rows.length} 筆結果</strong>
            <span>目前顯示前 {rows.length} 筆，點選股票可進個股詳頁。</span>
          </div>
          <div className="dense-table backtest-result-table">
            {rows.map((row) => (
              <button className="dense-row" type="button" key={row.symbol} onClick={() => onStockSelect(row.code)}>
                <strong>{row.name}</strong>
                <span>{row.code}</span>
                <span>{formatBacktestScore(row)}</span>
                <em>{formatPrice(row.price)}</em>
                <em className={toneClass(row.rsSpreadPct)}>{formatPct(row.rsSpreadPct)}</em>
                <em>{formatBacktestReason(row)}</em>
              </button>
            ))}
          </div>
        </>
      ) : completed ? (
        <p className="muted">這次掃描沒有符合條件的股票。</p>
      ) : (
        <p className="muted">任務完成後，符合條件的股票會顯示在這裡。</p>
      )}
    </article>
  );
}

function BacktestParamPanel({
  strategy,
  mode,
  params,
  onParamsChange
}: {
  strategy: string;
  mode: string;
  params: BacktestTuningParams;
  onParamsChange: (patch: Partial<BacktestTuningParams>) => void;
}) {
  return (
    <div className="strategy-param-panel">
      <div className="section-title compact-title">
        <SlidersHorizontal size={18} />
        <h3>策略參數</h3>
      </div>
      <div className="control-grid param-grid">
        {strategy === "強勢股回檔量縮止跌" ? (
          <>
            <ParamNumber label="觀察高點天數" value={params.pullback_strong_lookback_days} min={5} max={260} onValueChange={(value) => onParamsChange({ pullback_strong_lookback_days: value })} />
            <ParamDecimal label="最小回檔 %" value={params.pullback_min_pullback_pct} min={0.1} max={90} onValueChange={(value) => onParamsChange({ pullback_min_pullback_pct: value })} />
            <ParamNumber label="守低天數" value={params.pullback_base_hold_days} min={1} max={30} onValueChange={(value) => onParamsChange({ pullback_base_hold_days: value })} />
            <ParamDecimal label="低價股門檻" value={params.pullback_low_price_volume_price_threshold} min={0} max={10000} onValueChange={(value) => onParamsChange({ pullback_low_price_volume_price_threshold: value })} />
            <ParamDecimal label="低價股最小量" value={params.pullback_low_price_min_volume_lots} min={0} max={1000000} onValueChange={(value) => onParamsChange({ pullback_low_price_min_volume_lots: value })} />
            <label className="toggle-line">
              <input type="checkbox" checked={params.pullback_technology_only} onChange={(event) => onParamsChange({ pullback_technology_only: event.target.checked })} />
              <span>只看科技股</span>
            </label>
          </>
        ) : null}
        {strategy === "VCP 收斂突破" ? (
          <>
            <ParamNumber label="VCP 觀察天數" value={params.vcp_lookback_days} min={20} max={260} onValueChange={(value) => onParamsChange({ vcp_lookback_days: value })} />
            <ParamDecimal label="前波最小漲幅 %" value={params.vcp_min_uptrend_pct} min={0.1} max={300} onValueChange={(value) => onParamsChange({ vcp_min_uptrend_pct: value })} />
            <ParamDecimal label="突破量比" value={params.vcp_breakout_volume_ratio} min={0.1} max={20} onValueChange={(value) => onParamsChange({ vcp_breakout_volume_ratio: value })} />
            <ParamDecimal label="近壓力容忍 %" value={params.vcp_near_pivot_tolerance_pct} min={0.1} max={100} onValueChange={(value) => onParamsChange({ vcp_near_pivot_tolerance_pct: value })} />
            <ParamDecimal label="最大整理深度 %" value={params.vcp_max_consolidation_depth_pct} min={1} max={100} onValueChange={(value) => onParamsChange({ vcp_max_consolidation_depth_pct: value })} />
          </>
        ) : null}
        {strategy === "高價股回檔" ? (
          <>
            <ParamNumber label="高點觀察天數" value={params.high_price_pullback_lookback_days} min={5} max={260} onValueChange={(value) => onParamsChange({ high_price_pullback_lookback_days: value })} />
            <ParamNumber label="市值排行前 N" value={params.high_price_pullback_market_cap_rank_limit} min={1} max={500} onValueChange={(value) => onParamsChange({ high_price_pullback_market_cap_rank_limit: value })} />
            <ParamDecimal label="最小回檔 %" value={params.high_price_pullback_min_drop_pct} min={0.1} max={90} onValueChange={(value) => onParamsChange({ high_price_pullback_min_drop_pct: value })} />
          </>
        ) : null}
        {strategy === "接近前高／即將突破" ? (
          <>
            <ParamNumber label="前高觀察天數" value={params.breakout_lookback_days} min={30} max={1260} onValueChange={(value) => onParamsChange({ breakout_lookback_days: value })} />
            <ParamDecimal label="距前高內 %" value={params.breakout_distance_pct} min={0.1} max={50} onValueChange={(value) => onParamsChange({ breakout_distance_pct: value })} />
            <ParamNumber label="向上趨勢天數" value={params.breakout_trend_lookback_days} min={3} max={120} onValueChange={(value) => onParamsChange({ breakout_trend_lookback_days: value })} />
            <ParamNumber label="短均量天數" value={params.breakout_volume_short_window} min={1} max={60} onValueChange={(value) => onParamsChange({ breakout_volume_short_window: value })} />
            <ParamNumber label="長均量天數" value={params.breakout_volume_long_window} min={2} max={120} onValueChange={(value) => onParamsChange({ breakout_volume_long_window: value })} />
          </>
        ) : null}
        {strategy === "碗形底＋帶量向上" ? (
          <>
            <ParamNumber label="碗形觀察天數" value={params.bowl_volume_lookback_days} min={60} max={260} onValueChange={(value) => onParamsChange({ bowl_volume_lookback_days: value })} />
            <ParamDecimal label="最小跌幅 %" value={params.bowl_volume_min_drawdown_pct} min={1} max={80} onValueChange={(value) => onParamsChange({ bowl_volume_min_drawdown_pct: value })} />
            <ParamNumber label="短均量天數" value={params.bowl_volume_short_window} min={1} max={60} onValueChange={(value) => onParamsChange({ bowl_volume_short_window: value })} />
            <ParamNumber label="長均量天數" value={params.bowl_volume_long_window} min={2} max={120} onValueChange={(value) => onParamsChange({ bowl_volume_long_window: value })} />
            <ParamDecimal label="最小量比" value={params.bowl_volume_min_volume_ratio} min={0.1} max={10} onValueChange={(value) => onParamsChange({ bowl_volume_min_volume_ratio: value })} />
            <ParamNumber label="近期趨勢天數" value={params.bowl_volume_trend_lookback_days} min={3} max={120} onValueChange={(value) => onParamsChange({ bowl_volume_trend_lookback_days: value })} />
          </>
        ) : null}
        <ParamNumber label="盤整天數" value={params.range_lookback_days} min={5} max={260} onValueChange={(value) => onParamsChange({ range_lookback_days: value })} />
        <ParamDecimal label="盤整最大寬度 %" value={params.range_max_width_pct} min={1} max={200} onValueChange={(value) => onParamsChange({ range_max_width_pct: value })} />
        <ParamDecimal label="量增倍率" value={params.range_volume_ratio} min={0.1} max={10} onValueChange={(value) => onParamsChange({ range_volume_ratio: value })} />
        <ParamNumber label="量增連續天數" value={params.range_volume_sustain_days} min={1} max={30} onValueChange={(value) => onParamsChange({ range_volume_sustain_days: value })} />
        {mode === "歷史回測" ? (
          <>
            <ParamNumber label="初始資金" value={params.initial_capital} min={1000} max={1000000000} onValueChange={(value) => onParamsChange({ initial_capital: value })} />
            <ParamDecimal label="交易成本 %" value={params.trading_cost_pct} min={0} max={10} onValueChange={(value) => onParamsChange({ trading_cost_pct: value })} />
            <ParamDecimal label="初始停損 %" value={params.initial_stop_loss_pct} min={0.1} max={80} onValueChange={(value) => onParamsChange({ initial_stop_loss_pct: value })} />
            <ParamDecimal label="移動停損啟動 %" value={params.trailing_stop_activation_pct} min={0.1} max={200} onValueChange={(value) => onParamsChange({ trailing_stop_activation_pct: value })} />
            <ParamDecimal label="高點回撤 %" value={params.trailing_stop_drawdown_pct} min={0.1} max={80} onValueChange={(value) => onParamsChange({ trailing_stop_drawdown_pct: value })} />
          </>
        ) : null}
      </div>
    </div>
  );
}

function ParamNumber({ label, value, min, max, onValueChange }: { label: string; value: number; min: number; max: number; onValueChange: (value: number) => void }) {
  return (
    <label>
      {label}
      <NumericInput value={value} min={min} max={max} onValueChange={onValueChange} />
    </label>
  );
}

function ParamDecimal({ label, value, min, max, onValueChange }: { label: string; value: number; min: number; max: number; onValueChange: (value: number) => void }) {
  return (
    <label>
      {label}
      <DecimalInput value={value} min={min} max={max} onValueChange={onValueChange} />
    </label>
  );
}

function normalizeBacktestResults(preview: BacktestJob["result_preview"]): BacktestResultRow[] {
  if (!preview) return [];
  const entries = Array.isArray(preview)
    ? preview.map((row, index) => [`${index}`, row] as const)
    : Object.entries(preview);
  return entries.map(([symbol, raw]) => {
    const row = raw ?? {};
    const normalizedSymbol = symbol.includes(".") ? symbol : getString(row.symbol) || symbol;
    const code = getString(row.code) || normalizedSymbol.split(".")[0] || normalizedSymbol;
    return {
      symbol: normalizedSymbol,
      code,
      name: getString(row.name) || code,
      price: getNumber(row.price ?? row.ending_capital),
      score: getNumber(row.bowl_volume_score ?? row.near_breakout_score ?? row.pullback_score ?? row.high_price_pullback_score ?? row.vcp_score ?? row.bowl_score),
      rsSpreadPct: getNumber(row.rs_spread_pct ?? row.avg_buy_rs_spread),
      volumeRatio: getNumber(row.bowl_volume_volume_ratio ?? row.near_breakout_volume_ratio ?? row.current_volume_ratio ?? row.recent3_volume_ratio ?? row.avg5_volume_ratio),
      returnPct: getNumber(row.total_return),
      totalTrades: getNumber(row.total_trades),
      positiveReasons: firstStringList(row.bowl_volume_positive_reasons, row.near_breakout_positive_reasons, row.positive_reasons, row.pullback_positive_reasons, row.vcp_positive_reasons, row.high_price_pullback_positive_reasons),
      cautionReasons: firstStringList(row.bowl_volume_caution_reasons, row.near_breakout_caution_reasons, row.caution_reasons, row.pullback_caution_reasons, row.vcp_caution_reasons, row.high_price_pullback_caution_reasons)
    };
  });
}

function uniqueCodes(codes: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const rawCode of codes) {
    const code = String(rawCode || "").trim();
    if (!code || seen.has(code)) continue;
    seen.add(code);
    result.push(code);
  }
  return result;
}

function getStockNavigationState(navigation: StockNavigation | null, currentCode: string): StockNavigationState | null {
  if (!navigation?.codes.length) return null;
  const codes = uniqueCodes(navigation.codes);
  if (codes.length < 2) return null;
  const normalizedCurrent = String(currentCode || "").trim();
  const currentIndex = codes.findIndex((code) => code === normalizedCurrent);
  if (currentIndex < 0) return null;
  return {
    sourceLabel: navigation.sourceLabel,
    currentIndex,
    total: codes.length,
    previousCode: currentIndex > 0 ? codes[currentIndex - 1] : null,
    nextCode: currentIndex < codes.length - 1 ? codes[currentIndex + 1] : null
  };
}

function formatBacktestScore(row: BacktestResultRow) {
  if (row.score !== null) return `分數 ${row.score.toFixed(1)}`;
  if (row.returnPct !== null) return `報酬 ${formatPct(row.returnPct)}`;
  if (row.totalTrades !== null) return `${row.totalTrades} 筆交易`;
  return "-";
}

function formatBacktestReason(row: BacktestResultRow) {
  const reason = row.positiveReasons[0] || row.cautionReasons[0];
  if (reason) return reason;
  if (row.volumeRatio !== null) return `量比 ${row.volumeRatio.toFixed(2)}x`;
  return "符合條件";
}

function StrategyPanel({ title, rows, defaults }: { title: string; rows: BacktestConfig["buy_strategies"]; defaults: string[] }) {
  return (
    <article className="data-panel">
      <div className="section-title">
        <SlidersHorizontal size={20} />
        <h2>{title}</h2>
      </div>
      <div className="strategy-list">
        {rows.map((row) => (
          <div className="strategy-card" key={row.key}>
            <strong>{row.title}</strong>
            <span>{defaults.includes(row.key) ? "預設啟用" : "可選策略"}</span>
            <p>{row.summary}</p>
          </div>
        ))}
      </div>
    </article>
  );
}

function NewsView({
  job,
  starting,
  onStart
}: {
  job: NewsJob | null;
  starting: boolean;
  onStart: () => Promise<void>;
}) {
  return (
    <>
      <section className="broker-panel">
        <div className="section-title">
          <Newspaper size={20} />
          <h2>新聞分析任務</h2>
        </div>
        <div className="job-runner">
          <div>
            <strong>台股主題 + 美股事件 + 公司焦點</strong>
            <span>這會丟到背景任務整理，完成後顯示摘要；外部新聞來源失敗時會在狀態列回報。</span>
          </div>
          <button type="button" onClick={() => void onStart()} disabled={starting || job?.status === "queued" || job?.status === "running"}>
            {starting ? "啟動中" : "執行"}
          </button>
        </div>
        {job ? (
          <div className="job-status">
            <span style={{ width: `${Math.max(4, Math.round((job.progress || 0) * 100))}%` }} />
            <strong>{job.message}</strong>
            <em>{job.status}</em>
          </div>
        ) : null}
      </section>
      <section className="content-grid">
        <article className="main-panel">
          <div className="section-title">
            <Newspaper size={20} />
            <h2>摘要</h2>
          </div>
          {job?.result_preview?.daily_brief?.length ? (
            <div className="brief-list">
              {job.result_preview.daily_brief.map((item) => (
                <p key={item}>{item}</p>
              ))}
            </div>
          ) : (
            <p className="muted">尚未產生新聞摘要。</p>
          )}
        </article>
        <article className="data-panel">
          <div className="section-title">
            <Wrench size={20} />
            <h2>狀態</h2>
          </div>
          <div className="summary-list">
            <SummaryRow label="背景任務" value={job?.status ?? "ready"} ok={job?.status === "completed"} />
            <SummaryRow label="AI 摘要" value={job?.result_preview?.ai_summary_enabled ? "啟用" : "未啟用"} />
            <SummaryRow label="模型" value={job?.result_preview?.ai_model ?? "-"} />
          </div>
        </article>
      </section>
    </>
  );
}

function ResearchView({
  searchText,
  companies,
  onSearchChange,
  onSearchSubmit,
  onStockSelect
}: {
  searchText: string;
  companies: ResearchCompanies | null;
  onSearchChange: (value: string) => void;
  onSearchSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onStockSelect: (code: string) => void;
}) {
  const rows = companies?.rows ?? [];
  return (
    <>
      <section className="status-grid">
        <MetricCard icon={<FileSearch size={20} />} label="追蹤公司" value={String(companies?.summary.company_count ?? "-")} />
        <MetricCard icon={<Layers3 size={20} />} label="題材數" value={String(companies?.summary.theme_count ?? "-")} />
        <MetricCard icon={<Database size={20} />} label="更新時間" value={companies?.summary.last_sync_at ?? "-"} />
      </section>
      <section className="data-panel wide-panel">
        <div className="section-title">
          <FileSearch size={20} />
          <h2>公司題材研究</h2>
        </div>
        <form className="stock-search" onSubmit={onSearchSubmit}>
          <input value={searchText} onChange={(event) => onSearchChange(event.target.value)} placeholder="搜尋公司、代碼、產業或題材" aria-label="Research search" />
          <button type="submit">搜尋</button>
        </form>
        {rows.length ? (
          <div className="dense-table research-table">
            {rows.map((row) => (
              <button className="dense-row" type="button" key={row.code} onClick={() => onStockSelect(row.code)}>
                <strong>{row.name_zh}</strong>
                <span>{row.code}</span>
                <span>{row.industry ?? "-"}</span>
                <em>{row.themes.slice(0, 2).join(" / ") || "未分類"}</em>
              </button>
            ))}
          </div>
        ) : (
          <p className="muted">目前沒有符合條件的公司資料。</p>
        )}
      </section>
    </>
  );
}

function WorkflowView({ title, icon }: { title: string; icon: ReactNode }) {
  return (
    <section className="content-grid">
      <article className="main-panel">
        <div className="section-title">
          {icon}
          <h2>{title}</h2>
        </div>
        <div className="timeline">
          <div className="timeline-item">
            <span className="timeline-index">1</span>
            <div>
              <h3>前端入口已建立</h3>
              <p>這個功能已從 Streamlit 功能表搬到新網站，後續可以接專用 API 與背景任務。</p>
            </div>
          </div>
          <div className="timeline-item">
            <span className="timeline-index">2</span>
            <div>
              <h3>執行交給 Worker</h3>
              <p>需要外部新聞、AI 分析或長任務的流程，會放到 worker，避免網站請求卡住。</p>
            </div>
          </div>
        </div>
      </article>
      <article className="data-panel">
        <div className="section-title">
          <Wrench size={20} />
          <h2>搬遷狀態</h2>
        </div>
        <div className="summary-list">
          <SummaryRow label="網站入口" value="完成" ok />
          <SummaryRow label="背景任務 API" value="待接" />
          <SummaryRow label="本地快取讀取" value="下一步" />
        </div>
      </article>
    </section>
  );
}

function SystemView({ overview }: { overview: DashboardOverview | null }) {
  return (
    <>
      <section className="content-grid">
        <article className="files-panel">
          <div className="section-title">
            <Database size={20} />
            <h2>資料檔案</h2>
          </div>
          <div className="file-list">
            {getAllFiles(overview).map((file) => (
              <div className="file-row" key={file.name} title={file.path}>
                <span className={file.exists ? "dot good" : "dot bad"} />
                <span>{file.name}</span>
              </div>
            ))}
          </div>
        </article>
        <article className="main-panel">
          <div className="section-title">
            <Wrench size={20} />
            <h2>NAS Worker 指令</h2>
          </div>
          <div className="command-list">
            <code>python -m apps.worker.backup_databases --label manual</code>
            <code>python -m apps.worker.update_price_cache --stock 2330 --days 1825</code>
            <code>TRADE_NAS_ROOT=/volume1/trade docker compose -f infra/docker-compose.yml up -d --build</code>
          </div>
        </article>
      </section>
    </>
  );
}

function StockIdentity({ stockOverview }: { stockOverview: StockOverview | null }) {
  return (
    <div className="stock-result">
      {stockOverview?.found && stockOverview.security ? (
        <>
          <strong>
            {stockOverview.security.name_zh} <span>{stockOverview.security.code}</span>
          </strong>
          <p>{stockOverview.security.full_name_zh || stockOverview.security.yfinance_symbol}</p>
          <dl>
            <div>
              <dt>市場</dt>
              <dd>{stockOverview.security.market}</dd>
            </div>
            <div>
              <dt>Yahoo Symbol</dt>
              <dd>{stockOverview.security.yfinance_symbol}</dd>
            </div>
            <div>
              <dt>產業代碼</dt>
              <dd>{stockOverview.security.industry_code || "-"}</dd>
            </div>
            <div>
              <dt>價格快取</dt>
              <dd>{formatCacheRange(stockOverview.price_cache)}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="muted">尚未查到股票資料</p>
      )}
    </div>
  );
}

function viewTitle(view: ViewKey) {
  return {
    overview: "台股資料中樞",
    stock: "個股詳頁",
    strong: "強勢個股",
    data: "本機資料更新",
    market: "產業地圖",
    broker: "券商分點",
    revenue: "月營收動能",
    usCalendar: "美股數據行事曆",
    etf: "主動式 ETF",
    backtest: "回測與選股",
    news: "新聞分析",
    research: "研究工作台",
    system: "系統與 NAS"
  }[view];
}

function getAllFiles(overview: DashboardOverview | null): FileStatus[] {
  return [...(overview?.runtime.db_files ?? []), ...(overview?.runtime.data_files ?? [])];
}

function SummaryRow({ label, value, ok }: { label: string; value: number | string; ok?: boolean }) {
  return (
    <div className="summary-row">
      <span className={ok ? "dot good" : "dot bad"} />
      <span>{label}</span>
      <strong>{typeof value === "number" ? value.toLocaleString() : value}</strong>
    </div>
  );
}

function MiniDataCard({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="mini-data-card">
      <span>{label}</span>
      <strong>{typeof value === "number" ? value.toLocaleString() : value}</strong>
    </div>
  );
}

function MetricTiny({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-tiny">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StrongStocksList({
  stocks,
  loading,
  onStockSelect
}: {
  stocks: StrongStocks | null;
  loading: boolean;
  onStockSelect: (code: string) => void;
}) {
  if (loading && !stocks) {
    return <p className="muted">強勢個股讀取中...</p>;
  }
  if (!stocks?.rows.length) {
    return <p className="muted">目前 price cache 可計算的股票不足，先補行情資料後這裡會自動出現排行。</p>;
  }

  return (
    <div className="strong-stock-list">
      <div className="strong-stock-meta">
        <span>{stocks.summary.window_start_date} 到 {stocks.summary.anchor_date}</span>
        <span>{stocks.summary.candidate_count} 檔候選，顯示前 {stocks.summary.returned_count} 檔</span>
      </div>
      {stocks.rows.map((row, index) => (
        <button className="strong-stock-row" type="button" key={row.symbol} onClick={() => onStockSelect(row.code)}>
          <span className="rank-badge">{index + 1}</span>
          <span className="strong-stock-name">
            <strong>{row.name_zh}</strong>
            <em>{row.code} · {row.quote_count} 筆</em>
          </span>
          <span className="strong-stock-price">
            <strong>{formatPrice(row.latest_close)}</strong>
            <em>{formatSigned(row.change)}</em>
          </span>
          <span className={`strong-stock-change ${row.change_pct >= 0 ? "up" : "down"}`}>
            {formatChangePct(row.change_pct)}
          </span>
          <Sparkline values={row.sparkline.map((item) => item.close)} rising={row.change_pct >= 0} />
        </button>
      ))}
    </div>
  );
}

function Sparkline({ values, rising }: { values: number[]; rising: boolean }) {
  const points = buildSparklinePoints(values, 118, 38);
  return (
    <svg className="sparkline" viewBox="0 0 118 38" role="img" aria-label="Price sparkline">
      <polyline points={points.area} fill={rising ? "rgba(255, 95, 109, 0.12)" : "rgba(61, 214, 181, 0.12)"} stroke="none" />
      <polyline points={points.line} fill="none" stroke={rising ? "#ff7b85" : "#56dec3"} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function JobProgress({ job, emptyText }: { job: PriceCacheJob | null; emptyText: string }) {
  if (!job) return <p className="muted">{emptyText}</p>;
  return (
    <div className="job-status">
      <span style={{ width: `${Math.max(4, Math.round((job.progress || 0) * 100))}%` }} />
      <strong>{job.message ?? job.status}</strong>
      <em>{job.error ?? `${Math.round((job.progress || 0) * 100)}% · ${job.job_id}`}</em>
    </div>
  );
}

function NumericInput({
  value,
  min,
  max,
  disabled,
  onValueChange
}: {
  value: number;
  min: number;
  max: number;
  disabled?: boolean;
  onValueChange: (value: number) => void;
}) {
  const [text, setText] = useState(String(value));
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) setText(String(value));
  }, [editing, value]);

  function commit(nextText = text) {
    const nextValue = clampNumber(Number.parseInt(nextText, 10), min, max, value);
    setText(String(nextValue));
    onValueChange(nextValue);
  }

  return (
    <input
      type="text"
      inputMode="numeric"
      pattern="[0-9]*"
      value={text}
      disabled={disabled}
      onFocus={(event) => {
        setEditing(true);
        event.currentTarget.select();
      }}
      onChange={(event) => {
        const nextText = event.target.value.replace(/\D/g, "");
        setText(nextText);
        if (nextText !== "") {
          onValueChange(Number.parseInt(nextText, 10));
        }
      }}
      onBlur={() => {
        setEditing(false);
        commit();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        }
      }}
    />
  );
}

function DecimalInput({
  value,
  min,
  max,
  disabled,
  onValueChange
}: {
  value: number;
  min: number;
  max: number;
  disabled?: boolean;
  onValueChange: (value: number) => void;
}) {
  const [text, setText] = useState(String(value));
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) setText(String(value));
  }, [editing, value]);

  function commit(nextText = text) {
    const nextValue = clampNumber(Number.parseFloat(nextText), min, max, value);
    setText(String(nextValue));
    onValueChange(nextValue);
  }

  return (
    <input
      type="text"
      inputMode="decimal"
      value={text}
      disabled={disabled}
      onFocus={(event) => {
        setEditing(true);
        event.currentTarget.select();
      }}
      onChange={(event) => {
        const nextText = event.target.value.replace(/[^\d.]/g, "").replace(/(\..*)\./g, "$1");
        setText(nextText);
        if (nextText !== "" && nextText !== ".") {
          const nextValue = Number.parseFloat(nextText);
          if (Number.isFinite(nextValue)) onValueChange(nextValue);
        }
      }}
      onBlur={() => {
        setEditing(false);
        commit();
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        }
      }}
    />
  );
}

function clampNumber(value: number, min: number, max: number, fallback: number) {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(Math.max(value, min), max);
}

function BrokerRank({ title, rows, side }: { title: string; rows: BrokerRankRow[]; side: "buy" | "sell" }) {
  return (
    <div className="broker-rank">
      <h3>{title}</h3>
      {rows.map((row) => (
        <div className="broker-row" key={`${title}-${row.broker_name}-${row.net_shares}`}>
          <span>{row.broker_name}</span>
          <strong className={side}>{formatShares(row.net_shares)}</strong>
        </div>
      ))}
    </div>
  );
}

function formatShares(value: number) {
  return `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })} 張`;
}

function formatPrice(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatChangePct(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function formatSigned(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatScore(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
}

function formatStepCount(positiveStepCount: number | null | undefined, monthCount: number | null | undefined) {
  if (positiveStepCount === null || positiveStepCount === undefined || !monthCount) return "-";
  return `${positiveStepCount}/${Math.max(monthCount - 1, 1)}`;
}

function formatPct(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(2)}%`;
}

function formatLargeAmount(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return `${(value / 100000).toLocaleString(undefined, { maximumFractionDigits: 1 })} 億`;
}

function formatVolume(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  return `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })} 張`;
}

function formatLots(value: number | null | undefined) {
  if (value === null || value === undefined) return "-";
  const lots = value / 1000;
  const prefix = lots > 0 ? "+" : "";
  return `${prefix}${lots.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function toneClass(value: number | null | undefined) {
  if (value === null || value === undefined || value === 0) return "";
  return value > 0 ? "positive" : "negative";
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function formatInputDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatMonthDay(value: string) {
  const [, month, day] = value.split("-");
  return month && day ? `${month}/${day}` : value;
}

function weekdayLabel(value: string) {
  const date = new Date(`${value}T00:00:00`);
  return ["日", "一", "二", "三", "四", "五", "六"][date.getDay()] ?? "";
}

function importanceLabel(value: string) {
  return {
    high: "高",
    medium: "中",
    low: "低"
  }[value] ?? value;
}

function importanceClass(value: string) {
  if (value === "high") return "is-high";
  if (value === "medium") return "is-medium";
  return "is-low";
}

function sourceStatusLabel(value: string) {
  if (value === "ready") return "可用";
  if (value === "mock") return "模擬";
  if (value === "empty") return "待資料";
  if (value === "error") return "錯誤";
  return value;
}

function sourceStatusClass(value: string) {
  if (value === "ready") return "is-ready";
  if (value === "mock") return "is-mock";
  if (value === "empty") return "is-empty";
  return "is-error";
}

function getString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function getNumber(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue : null;
  }
  return null;
}

function getStringList(value: unknown) {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function firstStringList(...values: unknown[]) {
  for (const value of values) {
    const list = getStringList(value);
    if (list.length) return list;
  }
  return [];
}

function formatCacheRange(cache: StockOverview["price_cache"]) {
  if (!cache) return "-";
  if (!cache.first_cached_date && !cache.last_cached_date) return cache.fetch_status;
  return `${cache.first_cached_date ?? "-"} 到 ${cache.last_cached_date ?? "-"}`;
}

function buildSparklinePoints(values: number[], width: number, height: number) {
  if (!values.length) return { line: "", area: "" };
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const line = values.map((value, index) => {
    const x = index * step;
    const y = height - ((value - min) / range) * (height - 6) - 3;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  const area = `0,${height} ${line} ${width},${height}`;
  return { line, area };
}

function MetricCard({
  icon,
  label,
  value,
  meta,
  tone = "neutral"
}: {
  icon: ReactNode;
  label: string;
  value: string;
  meta?: string;
  tone?: "good" | "bad" | "neutral";
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
      {meta ? <small>{meta}</small> : null}
    </article>
  );
}
