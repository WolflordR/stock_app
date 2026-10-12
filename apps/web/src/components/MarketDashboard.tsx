import { useEffect, useMemo, useState } from "react";
import { fetchHomeDashboard, type HomeDashboard, type HomeEvent, type HomeIndustry, type HomeSignal } from "../api";
import { MarketMarginCard } from "./ChipTrends";

type Props = { onStockSelect: (code: string, sourceLabel: string, codes: string[]) => void; onIndustrySelect: (key: string) => void; refresh?: boolean };
const INDUSTRY_PAGE_SIZE = 12;
const SIGNAL_PAGE_SIZE = 20;
const EVENT_PAGE_SIZE = 4;
const WATCHLIST_PAGE_SIZE = 10;
const IMPORTANT_PAGE_SIZE = 5;
const PERFORMANCE_PAGE_SIZE = 2;
const strategyNames: Record<string, string> = { early_momentum: "剛起漲", near_breakout: "即將突破前高", bowl_bottom: "碗形底", large_holder_increase: "大戶持股增加" };
const dateText = (value: string | null | undefined) => value ? value.replaceAll("-", "/") : "—";
const pct = (value: number | null | undefined, sign = true) => value == null ? "—" : `${sign && value > 0 ? "+" : ""}${value.toFixed(1)}%`;
const num = (value: number | null | undefined, digits = 0) => value == null ? "—" : value.toLocaleString("zh-TW", { maximumFractionDigits: digits });
const tone = (value: number | null | undefined) => value == null ? "" : value > 0 ? "up" : value < 0 ? "down" : "";
const daysTo = (iso: string) => Math.round((new Date(`${iso}T00:00:00+08:00`).getTime() - new Date(new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Taipei" }) + "T00:00:00+08:00").getTime()) / 86400000);
const relative = (iso: string) => { const n = daysTo(iso); return n === 0 ? "Today" : n === 1 ? "Tomorrow" : n > 0 ? `${n} days` : `${Math.abs(n)} days ago`; };
function sorted<T>(rows: T[], field: (row: T) => string | number | null | undefined, ascending: boolean): T[] {
  return [...rows].sort((a, b) => {
    const left = field(a), right = field(b);
    if (left == null) return 1;
    if (right == null) return -1;
    const compared = typeof left === "number" && typeof right === "number" ? left - right : String(left).localeCompare(String(right), "zh-TW");
    return ascending ? compared : -compared;
  });
}
function SortHead({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return <th><button type="button" onClick={onClick}>{label} {active ? "↓" : "↕"}</button></th>;
}
function pageIndex(total: number, requested: number, pageSize: number) { return Math.min(requested, Math.max(0, Math.ceil(total / pageSize) - 1)); }
function pageRows<T>(rows: T[], requested: number, pageSize: number): T[] { const start = pageIndex(rows.length, requested, pageSize) * pageSize; return rows.slice(start, start + pageSize); }
function PageNav({ total, page, pageSize, onChange }: { total: number; page: number; pageSize: number; onChange: (page: number) => void }) {
  const current = pageIndex(total, page, pageSize);
  const pages = Math.ceil(total / pageSize);
  return <div className="home-page-nav" aria-label="列表切換">
    <span>{total ? `${current * pageSize + 1}–${Math.min((current + 1) * pageSize, total)} / ${total}` : "0 / 0"}</span>
    <button type="button" onClick={() => onChange(current - 1)} disabled={current === 0}>上一個</button>
    <button type="button" onClick={() => onChange(current + 1)} disabled={current >= pages - 1}>下一個</button>
  </div>;
}

function Section({ title, date, children, detail }: { title: string; date?: string | null; children: React.ReactNode; detail?: string }) {
  return <section className="home-section"><div className="home-section-head"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div><small>Last updated · {dateText(date)}</small></div>{children}</section>;
}
function Empty({ children }: { children: React.ReactNode }) { return <p className="home-empty">{children}</p>; }
function StockButton({ code, name, onClick }: { code: string; name?: string; onClick: () => void }) { return <button className="home-link" type="button" onClick={onClick}><strong>{code}</strong> {name}</button>; }
function LargeHolderCell({ row }: { row: HomeSignal }) {
  const change = row.large_holder_change_pp;
  if (typeof change !== "number" || !Number.isFinite(change) || typeof row.large_holder_pct !== "number" || !row.ownership_report_date || !row.ownership_previous_date) {
    return <td title="缺少可比較的完整集保週報">—</td>;
  }
  return <td title={`集保 ${dateText(row.ownership_previous_date)} → ${dateText(row.ownership_report_date)}；逾 1,000 張持股比例 ${row.large_holder_pct.toFixed(4)}%；比例變化不等於主力買超`}>
    <span className={tone(change)}>{change > 0 ? "+" : ""}{change.toFixed(4)} pp</span><small> · {dateText(row.ownership_report_date)}</small>
  </td>;
}
function EventRows({ rows, onStockSelect }: { rows: HomeEvent[]; onStockSelect: (code: string) => void }) {
  if (!rows.length) return <Empty>這段期間沒有可驗證的官方公告事件。</Empty>;
  return <div className="home-event-list">{rows.map(event => <details className="home-event" key={event.id}>
    <summary><span className="home-event-date" title={dateText(event.event_date)}>{dateText(event.event_date)}<small>{relative(event.event_date)}</small></span><span className="home-event-main"><b>{event.stock_id} {event.company_name}</b><small>{event.event_type === "earnings" ? `${event.fiscal_year || ""} Q${event.fiscal_quarter || "?"} ${event.status === "completed" ? "財報決議公告" : "財報預計董事會"}` : event.title}</small></span><span className={`home-badge ${event.status}`}>{event.status === "estimated" ? "預計" : event.status === "completed" ? "已公告" : event.status === "cancelled" ? "已取消" : "已確認"}</span>{event.is_watchlist && <span className="home-badge">★</span>}</summary>
    <div className="home-event-detail"><StockButton code={event.stock_id} name="查看個股" onClick={() => onStockSelect(event.stock_id)} /><p>{event.title}</p><p>{event.start_time || ""} {event.location || ""} {event.organizer || ""}</p><p>資料來源：<a href={event.source_url} target="_blank" rel="noreferrer">{event.source}</a> · 驗證 {event.last_verified_at.replace("T", " ")}</p>{event.status === "estimated" && <p>此為公告的董事會預定日期，財報公布時間尚未確認。</p>}{event.online_url && <a href={event.online_url} target="_blank" rel="noreferrer">線上入口</a>}{event.presentation_url && <a href={event.presentation_url} target="_blank" rel="noreferrer">簡報</a>}{event.replay_url && <a href={event.replay_url} target="_blank" rel="noreferrer">影音</a>}</div>
  </details>)}</div>;
}

export function MarketDashboard({ onStockSelect, onIndustrySelect, refresh = false }: Props) {
  const [data, setData] = useState<HomeDashboard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<"return_1d" | "return_5d" | "return_20d">("return_1d");
  const [turnoverMarket, setTurnoverMarket] = useState<"TWSE" | "TPEx" | "combined">("combined");
  const [industrySort, setIndustrySort] = useState<keyof HomeIndustry>("rotation_score");
  const [industryAsc, setIndustryAsc] = useState(false);
  const [industryPage, setIndustryPage] = useState(0);
  const [signalFilter, setSignalFilter] = useState("all");
  const [signalSort, setSignalSort] = useState<keyof HomeSignal>("is_new");
  const [signalAsc, setSignalAsc] = useState(false);
  const [signalPage, setSignalPage] = useState(0);
  const [watchSort, setWatchSort] = useState("stock_id");
  const [watchAsc, setWatchAsc] = useState(true);
  const [watchPage, setWatchPage] = useState(0);
  const [importantPage, setImportantPage] = useState(0);
  const [performanceSort, setPerformanceSort] = useState("strategy");
  const [performanceAsc, setPerformanceAsc] = useState(true);
  const [performancePage, setPerformancePage] = useState(0);
  const [eventWindow, setEventWindow] = useState("all");
  const [eventType, setEventType] = useState("all");
  const [earningsPage, setEarningsPage] = useState(0);
  const [conferencePage, setConferencePage] = useState(0);
  const [performanceWindow, setPerformanceWindow] = useState(20);
  useEffect(() => { let live = true; setLoading(true); fetchHomeDashboard(refresh).then(value => { if (live) { setData(value); setError(""); } }).catch(reason => { if (live) setError(reason instanceof Error ? reason.message : "Dashboard API 無法讀取"); }).finally(() => { if (live) setLoading(false); }); return () => { live = false; }; }, [refresh]);
  const industries = useMemo(() => sorted(data?.industries || [], row => row[industrySort] as string | number | null, industryAsc), [data, industrySort, industryAsc]);
  const signals = useMemo(() => sorted((data?.signals || []).filter(row => signalFilter === "all" || row.strategy === signalFilter), row => row[signalSort] as string | number | null, signalAsc), [data, signalFilter, signalSort, signalAsc]);
  const importantEvents = data?.important_events || [];
  const chooseIndustrySort = (key: keyof HomeIndustry) => { setIndustryAsc(current => industrySort === key ? !current : key === "l3" || key === "stage"); setIndustrySort(key); setIndustryPage(0); };
  const chooseSignalSort = (key: keyof HomeSignal) => { setSignalAsc(current => signalSort === key ? !current : ["stock_id", "strategy", "industry", "signal_date"].includes(key)); setSignalSort(key); setSignalPage(0); };
  const watchlist = useMemo(() => sorted(data?.watchlist || [], row => watchSort === "next_event" ? row.next_event?.event_date : watchSort === "signals" ? row.signals.join("、") : row[watchSort as keyof typeof row] as string | number | null, watchAsc), [data, watchSort, watchAsc]);
  const performance = useMemo(() => sorted((data?.strategy_performance || []).filter(row => row.window === performanceWindow), row => row[performanceSort as keyof typeof row], performanceAsc), [data, performanceWindow, performanceSort, performanceAsc]);
  const chooseWatchSort = (key: string) => { setWatchAsc(current => watchSort === key ? !current : ["stock_id", "industry", "signals", "next_event"].includes(key)); setWatchSort(key); setWatchPage(0); };
  const choosePerformanceSort = (key: string) => { setPerformanceAsc(current => performanceSort === key ? !current : key === "strategy"); setPerformanceSort(key); setPerformancePage(0); };
  const events = useMemo(() => (data?.events.rows || []).filter(event => {
    if (eventType !== "all" && event.event_type !== eventType && !(eventType === "watchlist" && event.is_watchlist)) return false;
    const days = daysTo(event.event_date);
    if (eventWindow === "recent") return days < 0 && days >= -7;
    if (eventWindow === "today") return days === 0;
    if (eventWindow === "week") return days >= 0 && days <= 6;
    if (eventWindow === "next") return days >= 7 && days <= 13;
    return days >= 0 && days <= 14;
  }), [data, eventType, eventWindow]);
  const selectStock = (code: string, sourceLabel: string, codes: string[]) => onStockSelect(code, sourceLabel, codes);
  if (loading) return <div className="home-skeleton" aria-busy="true">{Array.from({ length: 5 }, (_, index) => <div key={index} />)}</div>;
  if (error || !data) return <div className="alert-panel" role="alert"><strong>Market Dashboard 暫時無法載入</strong><span>{error || "No data"}</span><button type="button" onClick={() => window.location.reload()}>重新載入</button></div>;
  const market = data.market;
  const breadth = data.breadth;
  const limits = breadth.limits;
  const twseLimits = limits?.markets?.TWSE;
  const tpexLimits = limits?.markets?.TPEx;
  const benchmarks = [market.benchmarks.TWSE, market.benchmarks.TPEx].filter(Boolean);
  const turnover = market.turnover_ratios?.[turnoverMarket];
  const earnings = events.filter(event => event.event_type === "earnings");
  const conferences = events.filter(event => event.event_type === "investor_conference");
  const taipeiToday = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Taipei" });
  return <div className="market-home">
    <div className="home-meta">台股研究首頁 <span>頁面載入 {data.last_updated.replace("T", " ")} · 台北時間</span></div>
    <Section title="市場總覽" date={market.price_date} detail="上市櫃快取行情；不同來源日期分別標示">
      <div className="home-market-grid">{benchmarks.map(item => <div className="home-metric" key={item.label}><small>{item.label} · {dateText(item.date)}</small><strong>{num(item.value, 2)}</strong><span className={tone(item.change_pct)}>{item.change == null ? "—" : `${item.change > 0 ? "+" : ""}${num(item.change, 2)}`} · {pct(item.change_pct)}</span></div>)}
        <div className="home-metric"><small>追蹤股估算成交額 · {dateText(market.price_date)}</small><strong>{market.turnover_estimate == null ? "—" : `${num(market.turnover_estimate / 1e8, 1)} 億`}</strong><span>股價 × 成交股數</span></div>
        <div className="home-metric home-turnover-ratio"><small>大盤成交值量比 · {dateText(turnover?.trade_date)}</small><strong>{turnover?.ratio == null ? "—" : `${turnover.ratio.toFixed(2)}×`}</strong><div className="home-turnover-tabs" role="group" aria-label="成交值量比市場">{[["TWSE", "上市"], ["TPEx", "上櫃"], ["combined", "合計"]].map(([key, label]) => <button key={key} type="button" className={turnoverMarket === key ? "active" : ""} onClick={() => setTurnoverMarket(key as typeof turnoverMarket)}>{label}</button>)}</div><span>{turnover ? `當日 ${num(turnover.amount_twd / 1e8, 1)} 億 ÷ 前 5 日平均 ${turnover.average5_twd == null ? "—" : `${num(turnover.average5_twd / 1e8, 1)} 億`}` : "等待官方成交值更新"}</span><small>股票成交金額 · {turnoverMarket !== "TPEx" && <a href={turnover?.source_urls.TWSE || "https://www.twse.com.tw/zh/trading/historical/mi-index.html"} target="_blank" rel="noreferrer">上市來源</a>}{turnoverMarket === "combined" && " ＋ "}{turnoverMarket !== "TWSE" && <a href={turnover?.source_urls.TPEx || "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/highlight.html"} target="_blank" rel="noreferrer">上櫃來源</a>}</small></div>
        <div className="home-metric"><small>台積電 2330 · {dateText(market.tsmc?.trade_date)}</small><strong>{num(market.tsmc?.price, 2)}</strong><span className={tone(market.tsmc?.change_pct)}>{pct(market.tsmc?.change_pct)}</span></div>
        <div className="home-metric"><small>上漲 / 下跌 · {dateText(breadth.date)}</small><strong><span className="up">{num(breadth.advancing)}</span> / <span className="down">{num(breadth.declining)}</span></strong><span>上漲比例 {pct(breadth.advance_pct, false)}</span></div>
        <div className="home-metric"><small>股票漲停 / 跌停 · {dateText(limits?.date || twseLimits?.trade_date || tpexLimits?.trade_date)}</small><strong><span className="up">{num(limits?.limit_up_count)}</span> / <span className="down">{num(limits?.limit_down_count)}</span></strong><span>{twseLimits ? <a href={twseLimits.source_url} target="_blank" rel="noreferrer">上市 {num(twseLimits.limit_up_count)} / {num(twseLimits.limit_down_count)}</a> : "上市待更新"} · {tpexLimits ? <a href={tpexLimits.source_url} target="_blank" rel="noreferrer">上櫃 {num(tpexLimits.limit_up_count)} / {num(tpexLimits.limit_down_count)}</a> : "上櫃待更新"}{twseLimits && tpexLimits && !limits?.date ? "（日期不同，暫不合計）" : ""}</span></div>
      </div>
      <div className="home-breadth"><h3>Market Breadth</h3><div><span>站上 20MA <b>{pct(breadth.above_ma20_pct, false)}</b></span><span>站上 60MA <b>{pct(breadth.above_ma60_pct, false)}</b></span><span>20 日新高 <b>{num(breadth.new_high20)}</b></span><span>20 日新低 <b>{num(breadth.new_low20)}</b></span><span>觀測 <b>{num(breadth.observed)} 檔</b></span></div><small>{breadth.coverage_note}。</small></div>
    </Section>
    <MarketMarginCard />
    <Section title="細產業輪動" date={data.industry_date} detail="L3 多重產業歸屬；分數與公式沿用現有輪動引擎">
      <div className="home-toolbar"><div className="home-tabs">{(["return_1d", "return_5d", "return_20d"] as const).map((key, index) => <button className={period === key ? "active" : ""} key={key} onClick={() => { setPeriod(key); setIndustrySort(key); setIndustryAsc(false); setIndustryPage(0); }}>{["今日", "5D", "20D"][index]}</button>)}</div><span>點選欄位排序，點選產業查看成分股</span></div>
      {industries.length ? <div className="home-table-wrap"><table className="home-table"><thead><tr><SortHead label="產業" active={industrySort === "l3"} onClick={() => chooseIndustrySort("l3")} /><SortHead label={period === "return_1d" ? "今日" : period === "return_5d" ? "5D" : "20D"} active={industrySort === period} onClick={() => chooseIndustrySort(period)} /><SortHead label="5D" active={industrySort === "return_5d"} onClick={() => chooseIndustrySort("return_5d")} /><SortHead label="20D" active={industrySort === "return_20d"} onClick={() => chooseIndustrySort("return_20d")} /><SortHead label="成分平均量比" active={industrySort === "volume_ratio"} onClick={() => chooseIndustrySort("volume_ratio")} /><SortHead label="成交熱度" active={industrySort === "turnover_expansion"} onClick={() => chooseIndustrySort("turnover_expansion")} /><SortHead label="成交金額占比變化" active={industrySort === "turnover_share_delta"} onClick={() => chooseIndustrySort("turnover_share_delta")} /><SortHead label="上漲比例" active={industrySort === "breadth"} onClick={() => chooseIndustrySort("breadth")} /><SortHead label="創新高比例" active={industrySort === "breakout_participation"} onClick={() => chooseIndustrySort("breakout_participation")} /><SortHead label="產業強度" active={industrySort === "rotation_score"} onClick={() => chooseIndustrySort("rotation_score")} /><SortHead label="趨勢" active={industrySort === "stage"} onClick={() => chooseIndustrySort("stage")} /></tr></thead><tbody>{pageRows(industries, industryPage, INDUSTRY_PAGE_SIZE).map(row => <tr key={row.sector_key}><td><button className="home-link" onClick={() => onIndustrySelect(row.sector_key)}>{row.l3}</button></td><td className={tone(row[period])}>{pct(row[period])}</td><td className={tone(row.return_5d)}>{pct(row.return_5d)}</td><td className={tone(row.return_20d)}>{pct(row.return_20d)}</td><td>{row.volume_ratio == null ? "—" : `${num(row.volume_ratio, 2)}×`}</td><td>{row.turnover_expansion == null ? "—" : `${num(row.turnover_expansion, 2)}×`}</td><td>{row.turnover_share_delta == null ? "—" : `${num(row.turnover_share_delta * 100, 2)} pp`}</td><td>{pct(row.breadth == null ? null : row.breadth * 100, false)}</td><td>{pct(row.breakout_participation == null ? null : row.breakout_participation * 100, false)}</td><td><b>{num(row.rotation_score, 1)}</b></td><td>{row.stage}</td></tr>)}</tbody></table></div> : <Empty>尚無已計算的 L3 輪動資料。</Empty>}
      <PageNav total={industries.length} page={industryPage} pageSize={INDUSTRY_PAGE_SIZE} onChange={setIndustryPage} />
    </Section>
    <Section title={data.signal_date === taipeiToday ? "今日選股訊號" : "最新交易日選股訊號"} date={data.signal_date} detail="剛起漲、接近前高、碗形底與大戶持股增加是獨立選股策略；均須當日成交量 > 1,000 張或估算成交值 > 2 億元。大戶策略採集保逾 1,000 張持股比例週增">
      <div className="home-toolbar"><div className="home-tabs">{[["all", "全部"], ["early_momentum", "剛起漲"], ["near_breakout", "即將突破前高"], ["bowl_bottom", "碗形底"], ["large_holder_increase", "大戶持股增加"]].map(([key, label]) => <button key={key} className={signalFilter === key ? "active" : ""} onClick={() => { setSignalFilter(key); setSignalPage(0); }}>{label}</button>)}</div><span>{data.signal_date ? `${signals.length} 筆` : "等待每日策略快照"}</span></div>
      {signals.length ? <div className="home-table-wrap"><table className="home-table"><thead><tr><SortHead label="股票" active={signalSort === "stock_id"} onClick={() => chooseSignalSort("stock_id")} /><SortHead label="價格" active={signalSort === "price"} onClick={() => chooseSignalSort("price")} /><SortHead label="今日 %" active={signalSort === "change_pct"} onClick={() => chooseSignalSort("change_pct")} /><SortHead label="策略" active={signalSort === "strategy"} onClick={() => chooseSignalSort("strategy")} /><SortHead label="成交量 (張)" active={signalSort === "volume_lots"} onClick={() => chooseSignalSort("volume_lots")} /><SortHead label="估算成交值 (億)" active={signalSort === "estimated_turnover_twd"} onClick={() => chooseSignalSort("estimated_turnover_twd")} /><SortHead label="大戶週增 (pp)" active={signalSort === "large_holder_change_pp"} onClick={() => chooseSignalSort("large_holder_change_pp")} /><SortHead label="量比" active={signalSort === "volume_ratio"} onClick={() => chooseSignalSort("volume_ratio")} /><SortHead label="距前高" active={signalSort === "distance_to_high_pct"} onClick={() => chooseSignalSort("distance_to_high_pct")} /><SortHead label="產業" active={signalSort === "industry"} onClick={() => chooseSignalSort("industry")} /><SortHead label="強度" active={signalSort === "industry_score"} onClick={() => chooseSignalSort("industry_score")} /><SortHead label="Signal Date" active={signalSort === "signal_date"} onClick={() => chooseSignalSort("signal_date")} /><SortHead label="狀態" active={signalSort === "is_new"} onClick={() => chooseSignalSort("is_new")} /></tr></thead><tbody>{pageRows(signals, signalPage, SIGNAL_PAGE_SIZE).map(row => <tr key={`${row.stock_id}-${row.strategy}`}><td><StockButton code={row.stock_id} name={row.name} onClick={() => selectStock(row.stock_id, "首頁選股訊號", signals.map(item => item.stock_id))} /></td><td>{num(row.price, 2)}</td><td className={tone(row.change_pct)}>{pct(row.change_pct)}</td><td>{strategyNames[row.strategy] || row.strategy}</td><td>{num(row.volume_lots, 3)}</td><td>{num(row.estimated_turnover_twd / 1e8, 2)}</td><LargeHolderCell row={row} /><td>{row.volume_ratio == null ? "—" : `${num(row.volume_ratio, 2)}×`}</td><td>{pct(row.distance_to_high_pct, false)}</td><td>{row.industry || "—"}</td><td>{num(row.industry_score, 1)}</td><td>{dateText(row.signal_date)}</td><td><span className={`home-badge ${row.is_new ? "new" : ""}`}>{row.strategy === "large_holder_increase" ? "週資料" : row.is_new ? "NEW" : "Existing"}</span></td></tr>)}</tbody></table></div> : <Empty>{data.signal_date ? signalFilter === "large_holder_increase" ? "目前沒有同時符合集保大戶持股週增與成交量／估算成交值門檻的股票。" : "所選策略中，沒有符合成交量／估算成交值門檻的股票。" : "尚無每日訊號快照；執行 daily worker 後顯示。"}</Empty>}
      <PageNav total={signals.length} page={signalPage} pageSize={SIGNAL_PAGE_SIZE} onChange={setSignalPage} />
    </Section>
    <Section title="近期財報與法說" date={data.events.source_state.map(item => item.last_success_at).filter(Boolean).sort().at(-1)} detail="財報與法說是不同事件；Estimated 僅代表董事會預定日期">
      {data.recent_revenue?.report_month && <div className="home-revenue-status"><strong>{data.recent_revenue.report_month} 月營收已揭露 {num(data.recent_revenue.count)} 家</strong><span><a href={data.recent_revenue.source_urls["上市"]} target="_blank" rel="noreferrer">上市 {num(data.recent_revenue.markets["上市"] || 0)}</a> · <a href={data.recent_revenue.source_urls["上櫃"]} target="_blank" rel="noreferrer">上櫃 {num(data.recent_revenue.markets["上櫃"] || 0)}</a>{data.recent_revenue.partial ? " · 持續更新中" : ""} · 與季度財報分開統計</span><small>官方 MOPS 月營收彙整 · 本地更新 {data.recent_revenue.updated_at?.replace("T", " ") || "—"}</small></div>}
      <div className="home-toolbar"><div className="home-tabs">{[["all", "未來 14 天"], ["today", "Today"], ["week", "This Week"], ["next", "Next Week"], ["recent", "Recent 7D"]].map(([key, label]) => <button key={key} className={eventWindow === key ? "active" : ""} onClick={() => { setEventWindow(key); setEarningsPage(0); setConferencePage(0); }}>{label}</button>)}</div><select aria-label="事件篩選" value={eventType} onChange={event => { setEventType(event.target.value); setEarningsPage(0); setConferencePage(0); }}><option value="all">All</option><option value="earnings">Earnings</option><option value="investor_conference">Conference</option><option value="watchlist">Watchlist</option></select></div>
      {data.data_quality.events === "error" && <p className="home-warning">官方事件來源暫時無法更新；{data.events.count ? "目前顯示上次成功保存的公告。" : "目前沒有可顯示的事件。"}</p>}
      {data.data_quality.events === "unavailable" && <p className="home-warning">官方事件資料尚未同步；執行 daily worker 後更新。</p>}
      <div className="home-two-columns"><div><h3>近期財報 <small>{earnings.length}</small></h3><EventRows rows={pageRows(earnings, earningsPage, EVENT_PAGE_SIZE)} onStockSelect={(code) => selectStock(code, "近期財報", earnings.map(row => row.stock_id))} /><PageNav total={earnings.length} page={earningsPage} pageSize={EVENT_PAGE_SIZE} onChange={setEarningsPage} /></div><div><h3>近期法說 <small>{conferences.length}</small></h3><EventRows rows={pageRows(conferences, conferencePage, EVENT_PAGE_SIZE)} onStockSelect={(code) => selectStock(code, "近期法說", conferences.map(row => row.stock_id))} /><PageNav total={conferences.length} page={conferencePage} pageSize={EVENT_PAGE_SIZE} onChange={setConferencePage} /></div></div>
    </Section>
    <Section title="你可能需要注意" date={data.last_updated} detail="僅組合已觀測的 NEW 訊號和七天內的官方事件，不推論利多或利空">
      {importantEvents.length ? <div className="home-alert-list">{pageRows(importantEvents, importantPage, IMPORTANT_PAGE_SIZE).map(item => <div key={`${item.stock_id}-${item.event_type}`}><StockButton code={item.stock_id} name={item.name} onClick={() => selectStock(item.stock_id, "首頁重要事件", importantEvents.map(entry => entry.stock_id))} /><span>NEW {strategyNames[item.strategy]} · {item.days_until === 0 ? "今天" : `${item.days_until} 天後`} {item.event_type === "earnings" ? "預計財報董事會" : "法說會"}</span><small>{dateText(item.event_date)}</small></div>)}</div> : <Empty>目前沒有「NEW 訊號＋七天內事件」的組合。</Empty>}
      <PageNav total={importantEvents.length} page={importantPage} pageSize={IMPORTANT_PAGE_SIZE} onChange={setImportantPage} />
    </Section>
    <Section title="自選股" date={market.price_date} detail="股價、主要細產業、當前訊號及下一個重要事件">
      {data.watchlist.length ? <div className="home-table-wrap"><table className="home-table"><thead><tr><SortHead label="股票" active={watchSort === "stock_id"} onClick={() => chooseWatchSort("stock_id")} /><SortHead label="價格" active={watchSort === "price"} onClick={() => chooseWatchSort("price")} /><SortHead label="今日 %" active={watchSort === "change_pct"} onClick={() => chooseWatchSort("change_pct")} /><SortHead label="產業" active={watchSort === "industry"} onClick={() => chooseWatchSort("industry")} /><SortHead label="強度" active={watchSort === "industry_score"} onClick={() => chooseWatchSort("industry_score")} /><SortHead label="目前訊號" active={watchSort === "signals"} onClick={() => chooseWatchSort("signals")} /><SortHead label="下一個事件" active={watchSort === "next_event"} onClick={() => chooseWatchSort("next_event")} /></tr></thead><tbody>{pageRows(watchlist, watchPage, WATCHLIST_PAGE_SIZE).map(row => <tr key={row.stock_id}><td><StockButton code={row.stock_id} name={row.name} onClick={() => selectStock(row.stock_id, "首頁自選股", watchlist.map(item => item.stock_id))} /></td><td>{num(row.price, 2)}</td><td className={tone(row.change_pct)}>{pct(row.change_pct)}</td><td>{row.industry || "—"}</td><td>{num(row.industry_score, 1)}</td><td>{row.signals.map(key => strategyNames[key] || key).join("、") || "—"}</td><td>{row.next_event ? <span className={daysTo(row.next_event.event_date) <= 7 ? "home-badge soon" : ""}>{row.next_event.event_type === "earnings" ? "財報" : "法說"} · {relative(row.next_event.event_date)}</span> : "—"}</td></tr>)}</tbody></table></div> : <Empty>尚未加入自選股；從個股頁加入後，這裡會顯示下一個事件。</Empty>}
      <PageNav total={watchlist.length} page={watchPage} pageSize={WATCHLIST_PAGE_SIZE} onChange={setWatchPage} />
    </Section>
    <Section title="策略近期績效" date={data.last_updated} detail="只顯示可驗證的回測統計；目前沒有已保存的每日策略績效序列">
      <div className="home-tabs">{[20, 60, 120].map(days => <button key={days} className={performanceWindow === days ? "active" : ""} onClick={() => { setPerformanceWindow(days); setPerformancePage(0); }}>{days}D</button>)}</div>
      <div className="home-table-wrap"><table className="home-table"><thead><tr><SortHead label="策略" active={performanceSort === "strategy"} onClick={() => choosePerformanceSort("strategy")} /><SortHead label="Signals" active={performanceSort === "signals"} onClick={() => choosePerformanceSort("signals")} /><SortHead label="Win Rate" active={performanceSort === "win_rate"} onClick={() => choosePerformanceSort("win_rate")} /><SortHead label="Average Return" active={performanceSort === "average_return"} onClick={() => choosePerformanceSort("average_return")} /><SortHead label="Median Return" active={performanceSort === "median_return"} onClick={() => choosePerformanceSort("median_return")} /><SortHead label="Max Drawdown" active={performanceSort === "max_drawdown"} onClick={() => choosePerformanceSort("max_drawdown")} /></tr></thead><tbody>{pageRows(performance, performancePage, PERFORMANCE_PAGE_SIZE).map(row => <tr key={row.strategy}><td>{row.strategy}</td><td>{num(row.signals)}</td><td>{pct(row.win_rate, false)}</td><td>{pct(row.average_return)}</td><td>{pct(row.median_return)}</td><td>{pct(row.max_drawdown)}</td></tr>)}</tbody></table></div><PageNav total={performance.length} page={performancePage} pageSize={PERFORMANCE_PAGE_SIZE} onChange={setPerformancePage} /><p className="home-empty">No data · 尚未建立可比較的策略逐日績效資料。</p>
    </Section>
  </div>;
}
