import { useEffect, useState, type FormEvent } from "react";
import { fetchCompanyEvents, type CompanyEventsResult, type HomeEvent } from "../api";

const PAGE_SIZE = 25;
const todayTaipei = () => new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Taipei" });
const addDays = (day: string, count: number) => {
  const date = new Date(`${day}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + count);
  return date.toISOString().slice(0, 10);
};
const eventLabel = (event: HomeEvent) => event.event_type === "investor_conference" ? "法說會" : event.status === "estimated" ? "財報預計董事會" : "財報決議公告";
const statusLabel = (event: HomeEvent) => event.status === "estimated" ? "預計" : event.status === "completed" ? "已公告" : event.status === "cancelled" ? "已取消" : "已確認";

export function CompanyCalendar({ onStockSelect }: { onStockSelect: (code: string, codes: string[]) => void }) {
  const today = todayTaipei();
  const [startDate, setStartDate] = useState(addDays(today, -7));
  const [endDate, setEndDate] = useState(addDays(today, 90));
  const [eventType, setEventType] = useState("");
  const [status, setStatus] = useState("");
  const [searchText, setSearchText] = useState("");
  const [query, setQuery] = useState("");
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [page, setPage] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<CompanyEventsResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const invalidRange = !startDate || !endDate || endDate < startDate || (startDate ? addDays(startDate, 366) < endDate : false);

  useEffect(() => {
    if (invalidRange) return;
    let live = true;
    setLoading(true);
    fetchCompanyEvents({ start_date: startDate, end_date: endDate, event_type: eventType, status, query, watchlist_only: watchlistOnly, limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then(result => { if (live) { setData(result); setError(""); } })
      .catch(reason => { if (live) setError(reason instanceof Error ? reason.message : "事件資料讀取失敗"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [startDate, endDate, eventType, status, query, watchlistOnly, page, refresh, invalidRange]);

  const changeRange = (start: string, end: string) => { setStartDate(start); setEndDate(end); setPage(0); };
  const submitSearch = (event: FormEvent) => { event.preventDefault(); setQuery(searchText.trim()); setPage(0); };
  const rows = data?.rows ?? [];
  const stockCodes = [...new Set(rows.map(row => row.stock_id))];
  const pageCount = Math.ceil((data?.count ?? 0) / PAGE_SIZE);
  const sourceDates = (data?.source_state ?? []).map(state => state.last_success_at).filter((value): value is string => !!value);
  const lastUpdated = sourceDates.sort().at(-1);

  return <section className="event-calendar-page">
    <div className="event-calendar-intro">
      <div><h2>法說會與財報日期</h2><p>整合上市、上櫃法說行事曆與官方公告。財報預計董事會日期與財報決議公告日分開列出。</p></div>
      <button type="button" onClick={() => setRefresh(value => value + 1)}>重新讀取</button>
    </div>
    <div className="event-calendar-summary">
      <div><span>區間事件</span><strong>{data?.count ?? "—"}</strong></div>
      <div><span>法說會</span><strong>{data?.totals?.investor_conference ?? 0}</strong></div>
      <div><span>財報日期</span><strong>{data?.totals?.earnings ?? 0}</strong></div>
      <div><span>最近來源更新</span><strong className="date">{lastUpdated?.replace("T", " ") ?? "尚未同步"}</strong></div>
    </div>
    <div className="event-calendar-controls">
      <div className="event-calendar-presets">
        <button type="button" onClick={() => changeRange(today, addDays(today, 30))}>未來 30 天</button>
        <button type="button" onClick={() => changeRange(today, addDays(today, 90))}>未來 90 天</button>
        <button type="button" onClick={() => changeRange(addDays(today, -30), today)}>過去 30 天</button>
      </div>
      <div className="event-calendar-filters">
        <label>開始日期<input type="date" value={startDate} onChange={event => changeRange(event.target.value, endDate)} /></label>
        <label>結束日期<input type="date" value={endDate} onChange={event => changeRange(startDate, event.target.value)} /></label>
        <label>事件<select value={eventType} onChange={event => { setEventType(event.target.value); setPage(0); }}><option value="">全部</option><option value="investor_conference">法說會</option><option value="earnings">財報</option></select></label>
        <label>狀態<select value={status} onChange={event => { setStatus(event.target.value); setPage(0); }}><option value="">全部</option><option value="estimated">預計</option><option value="confirmed">已確認法說</option><option value="completed">財報決議已公告</option></select></label>
        <label className="event-calendar-check"><input type="checkbox" checked={watchlistOnly} onChange={event => { setWatchlistOnly(event.target.checked); setPage(0); }} />只看最愛</label>
      </div>
      <form className="event-calendar-search" onSubmit={submitSearch}><input value={searchText} onChange={event => setSearchText(event.target.value)} placeholder="輸入股票代號或公司名稱" aria-label="搜尋事件公司" /><button type="submit">搜尋</button>{query && <button type="button" onClick={() => { setSearchText(""); setQuery(""); setPage(0); }}>清除</button>}</form>
    </div>
    {invalidRange && <p className="home-warning">請填寫開始與結束日期；結束日期需晚於開始日期，查詢區間最多一年。</p>}
    {error && <p className="home-warning">{error}；目前保留上次顯示的資料。</p>}
    {(data?.source_state ?? []).filter(source => source.last_error).map(source => <p className="home-warning" key={source.source}>{source.source} 官方來源更新失敗：{source.last_error}。仍可查看已保存的公告。</p>)}
    <div className="event-calendar-list" aria-busy={loading}>
      {invalidRange ? null : loading && !data ? <p className="home-empty">正在載入事件…</p> : rows.length ? rows.map(event => <EventCard key={event.id} event={event} onStockSelect={() => onStockSelect(event.stock_id, stockCodes)} />) : <p className="home-empty">此區間沒有符合條件的已取得事件。行事曆及公告會每天同步；尚未公告的日期不以推估補上。</p>}
    </div>
    <div className="home-page-nav"><span>{data?.count ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, data.count)} / ${data.count}` : "0 / 0"}</span><button type="button" disabled={page === 0} onClick={() => setPage(value => value - 1)}>上一頁</button><button type="button" disabled={page + 1 >= pageCount} onClick={() => setPage(value => value + 1)}>下一頁</button></div>
    <p className="chip-source">資料來源：臺灣指數公司 IR 議合服務平台法說會行事曆、TWSE／TPEx MOPS 重大訊息，每日自動更新。行事曆按月查詢，公告每日累積；預計董事會日期不等於財報公布日。「財報決議公告」表示公司已發布董事會通過財報的重大訊息，不代表完整財報電子書已申報。</p>
  </section>;
}

function EventCard({ event, onStockSelect }: { event: HomeEvent; onStockSelect: () => void }) {
  return <article className="event-calendar-card">
    <div className="event-calendar-date"><strong>{event.event_date}</strong>{event.start_time && <span>{event.start_time}</span>}</div>
    <div className="event-calendar-main"><div className="event-calendar-card-head"><span className={`home-badge ${event.status}`}>{statusLabel(event)}</span><b>{eventLabel(event)}</b>{event.fiscal_year && event.fiscal_quarter && <small>{event.fiscal_year} Q{event.fiscal_quarter}</small>}</div><button type="button" className="home-link" onClick={onStockSelect}>{event.stock_id} {event.company_name}</button><p>{event.title}</p><small>{event.location || event.organizer || ""}</small></div>
    <div className="event-calendar-source"><a href={event.source_url} target="_blank" rel="noreferrer">{event.source === "Taiwan Index IR calendar" ? "法說行事曆" : "官方公告資料"} ↗</a><small>驗證 {event.last_verified_at.replace("T", " ")}</small></div>
  </article>;
}
