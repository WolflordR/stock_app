import { useEffect, useState } from "react";
import { fetchBrokerBranchStocks, fetchBrokerTradeDates } from "../api";
import type { BrokerBranch, BrokerBranchStocks } from "../types";

type Side = "buy" | "sell";
type Sort = BrokerBranchStocks["sort_by"];
type Props = {
  branch: BrokerBranch;
  onStockSelect: (code: string, codes: string[]) => void;
};

const PAGE_SIZE = 50;
const SORTS: { key: Sort; label: string }[] = [
  { key: "net_shares", label: "買賣超" },
  { key: "volume", label: "股票成交量" },
  { key: "turnover_value", label: "估算成交值" },
  { key: "volume_ratio", label: "量比" },
  { key: "change_pct", label: "股票漲跌幅" }
];
const number = (value: number | null, digits = 1) => value == null ? "—" : value.toLocaleString("zh-TW", { maximumFractionDigits: digits });
const lots = (value: number | null) => value == null ? "—" : number(value / 1000, 1);
const amount = (value: number | null) => value == null ? "—" : number(value / 100000000, 2);
const signed = (value: number | null) => value == null ? "—" : `${value > 0 ? "+" : ""}${number(value, 2)}%`;

export function BrokerBranchStocksView({ branch, onStockSelect }: Props) {
  const [side, setSide] = useState<Side>("buy");
  const [sortBy, setSortBy] = useState<Sort>("net_shares");
  const [descending, setDescending] = useState(true);
  const [page, setPage] = useState(0);
  const [selectedDate, setSelectedDate] = useState(branch.last_trade_date);
  const [tradeDates, setTradeDates] = useState<string[]>([]);
  const [listing, setListing] = useState<BrokerBranchStocks | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    fetchBrokerTradeDates(branch.market)
      .then((dates) => { if (live) setTradeDates(dates); })
      .catch(() => { if (live) setTradeDates([]); });
    return () => { live = false; };
  }, [branch.market]);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    setListing(null);
    fetchBrokerBranchStocks(branch.broker_name, selectedDate, branch.market, side, sortBy, descending, page * PAGE_SIZE, PAGE_SIZE)
      .then((value) => { if (live) setListing(value); })
      .catch((reason) => { if (live) setError(reason instanceof Error ? reason.message : "分點股票清單讀取失敗"); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [branch.broker_name, branch.market, selectedDate, side, sortBy, descending, page]);

  const rows = listing?.rows ?? [];
  const total = listing?.total ?? 0;
  const pageCount = Math.ceil(total / PAGE_SIZE);
  const sideLabel = side === "buy" ? "買超" : "賣超";
  const latestDate = tradeDates[0] || branch.last_trade_date;
  const previousDate = tradeDates.find((date) => date < selectedDate);
  const nextDate = [...tradeDates].reverse().find((date) => date > selectedDate && date <= latestDate);
  function selectDate(date: string) {
    if (!date || date === selectedDate) return;
    setSelectedDate(date);
    setPage(0);
  }
  function selectSort(next: Sort) {
    if (next === sortBy) setDescending((value) => !value);
    else { setSortBy(next); setDescending(true); }
    setPage(0);
  }

  return <div className="market-home broker-activity-page">
    <section className="home-section">
      <div className="home-section-head"><div><h2>{branch.broker_name} · 買賣超股票</h2><p>依分點當日逐筆成交計算買賣超與加權成交均價；股票成交量、成交值、量比與漲跌幅均使用同一交易日的股價快取。</p></div><small>{branch.market === "TWSE" ? "上市" : "上櫃"}分點日報 · {selectedDate}</small></div>
      <div className="broker-date-controls" role="group" aria-label="分點交易日期">
        <label htmlFor="broker-trade-date">交易日期</label>
        <button type="button" disabled={!previousDate} onClick={() => previousDate && selectDate(previousDate)}>前一交易日</button>
        <input id="broker-trade-date" type="date" value={selectedDate} max={latestDate} onChange={(event) => selectDate(event.target.value)} />
        <button type="button" disabled={!nextDate} onClick={() => nextDate && selectDate(nextDate)}>後一交易日</button>
        <button type="button" disabled={selectedDate === latestDate} onClick={() => selectDate(latestDate)}>最新</button>
        <span>可查看已匯入的歷史分點日報</span>
      </div>
      <div className="home-toolbar broker-activity-toolbar">
        <div className="home-tabs" role="group" aria-label="買賣超方向">
          <button type="button" className={side === "buy" ? "active" : ""} aria-pressed={side === "buy"} onClick={() => { setSide("buy"); setPage(0); }}>買超股票</button>
          <button type="button" className={side === "sell" ? "active" : ""} aria-pressed={side === "sell"} onClick={() => { setSide("sell"); setPage(0); }}>賣超股票</button>
        </div>
        <div className="home-tabs broker-sort-tabs" role="group" aria-label="分點股票排序">
          {SORTS.map(({ key, label }) => <button type="button" key={key} className={sortBy === key ? "active" : ""} aria-pressed={sortBy === key} onClick={() => selectSort(key)}>{label}{sortBy === key ? descending ? " ↓" : " ↑" : ""}</button>)}
        </div>
      </div>
      {loading ? <p className="home-empty" aria-busy="true">正在計算{sideLabel}股票…</p> : error ? <p className="home-empty" role="alert">{error}</p> : <>
        <div className="market-limit-summary"><strong className={side === "buy" ? "up" : "down"}>{sideLabel} {total.toLocaleString()} 檔</strong><span>同日股價資料 {listing?.quoted_count.toLocaleString() ?? 0} 檔</span><span>交易日 {listing?.trade_date}</span></div>
        {rows.length ? <><p className="broker-mobile-hint">表格可左右滑動，查看成交均價與行情欄位。</p><div className="home-table-wrap"><table className="home-table broker-activity-table"><thead><tr><th>股票</th><th>買賣超<br />張</th><th>買進<br />張</th><th>賣出<br />張</th><th>買進均價</th><th>賣出均價</th><th>股票成交量<br />張</th><th>估算成交值<br />億元</th><th>量比</th><th>股票漲跌幅</th></tr></thead><tbody>{rows.map((row) => <tr key={`${row.market}-${row.stock_code}`}><td><button type="button" className="home-link" onClick={() => onStockSelect(row.stock_code, rows.map((item) => item.stock_code))}><strong>{row.stock_code}</strong> {row.stock_name}</button></td><td className={row.net_shares > 0 ? "up" : "down"}>{row.net_shares > 0 ? "+" : ""}{lots(row.net_shares)}</td><td>{lots(row.buy_shares)}</td><td>{lots(row.sell_shares)}</td><td title="買進成交金額 ÷ 買進股數；依官方分點成交明細加權">{number(row.avg_buy_price, 3)}</td><td title="賣出成交金額 ÷ 賣出股數；依官方分點成交明細加權">{number(row.avg_sell_price, 3)}</td><td>{lots(row.stock_volume_shares)}</td><td>{amount(row.estimated_trade_value)}</td><td>{row.volume_ratio == null ? "—" : `${number(row.volume_ratio, 2)}×`}</td><td className={row.change_pct == null ? "" : row.change_pct > 0 ? "up" : row.change_pct < 0 ? "down" : ""}>{signed(row.change_pct)}</td></tr>)}</tbody></table></div>
          <div className="home-page-nav" aria-label="分點股票分頁"><span>{page * PAGE_SIZE + 1}–{page * PAGE_SIZE + rows.length} / {total}</span><button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>上一個</button><button type="button" disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)}>下一個</button></div>
        </> : <p className="home-empty">這個分點在 {selectedDate} 沒有{sideLabel}股票；請確認當日有匯入分點日報。</p>}
        <p className="broker-activity-note">資料來源：{listing?.broker_source}；{listing?.price_source}。估算成交值＝同日收盤價 × 同日成交股數；量比＝同日成交股數 ÷ 前 5 個有成交交易日平均股數。缺少同日行情或五日基準時顯示「—」。買進／賣出均價為分點成交金額除以各自成交股數，並非股票收盤價。清單只涵蓋已匯入分點日報的股票。</p>
      </>}
    </section>
  </div>;
}
