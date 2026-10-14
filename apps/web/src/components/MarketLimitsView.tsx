import { useEffect, useState } from "react";
import { fetchMarketLimitStocks, type MarketLimitListing } from "../api";

type Direction = "up" | "down";
type Market = "combined" | "TWSE" | "TPEx";
type Props = {
  direction: Direction;
  onDirectionChange: (direction: Direction) => void;
  onStockSelect: (code: string, codes: string[]) => void;
};
const PAGE_SIZE = 30;
const marketLabels: Record<Market, string> = { combined: "上市櫃", TWSE: "上市", TPEx: "上櫃" };
const dateText = (value: string | null | undefined) => value ? value.replaceAll("-", "/") : "—";

export function MarketLimitsView({ direction, onDirectionChange, onStockSelect }: Props) {
  const [market, setMarket] = useState<Market>("combined");
  const [listing, setListing] = useState<MarketLimitListing | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError("");
    setPage(0);
    fetchMarketLimitStocks(direction, market)
      .then((value) => { if (live) setListing(value); })
      .catch((reason) => { if (live) { setListing(null); setError(reason instanceof Error ? reason.message : "清單讀取失敗"); } })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [direction, market]);

  const rows = listing?.rows ?? [];
  const pageCount = Math.ceil(rows.length / PAGE_SIZE);
  const currentPage = Math.min(page, Math.max(pageCount - 1, 0));
  const shown = rows.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const label = direction === "up" ? "漲停" : "跌停";
  const sources = Object.entries(listing?.markets ?? {});

  return <div className="market-home market-limit-page">
    <section className="home-section">
      <div className="home-section-head"><div><h2>{label}股票</h2><p>以交易所公布的當日漲跌停價核對盤後收盤價；只有明細家數與官方統計相符才標記完成。</p></div><small>交易日 · {dateText(listing?.date)}</small></div>
      <div className="home-toolbar market-limit-toolbar">
        <div className="home-tabs" role="group" aria-label="漲跌停清單">
          <button type="button" className={direction === "up" ? "active" : ""} aria-pressed={direction === "up"} onClick={() => onDirectionChange("up")}>漲停</button>
          <button type="button" className={direction === "down" ? "active" : ""} aria-pressed={direction === "down"} onClick={() => onDirectionChange("down")}>跌停</button>
        </div>
        <div className="home-tabs" role="group" aria-label="市場範圍">
          {(["combined", "TWSE", "TPEx"] as const).map((key) => <button type="button" key={key} className={market === key ? "active" : ""} aria-pressed={market === key} onClick={() => setMarket(key)}>{marketLabels[key]}</button>)}
        </div>
      </div>
      {loading ? <p className="home-empty" aria-busy="true">正在讀取{label}清單…</p> : error ? <p className="home-empty" role="alert">{error}</p> : <>
        <div className="market-limit-summary"><strong className={direction === "up" ? "up" : "down"}>官方 {label} {listing?.official_count == null ? "—" : `${listing.official_count} 檔`}</strong><span>已核對明細 {rows.length} 檔</span><span>{listing?.complete ? `${marketLabels[market]}明細已與官方家數對齊` : "部分明細待更新；只顯示已與官方家數對齊的市場"}</span></div>
        {rows.length ? <><div className="home-table-wrap"><table className="home-table market-limit-table"><thead><tr><th>股票</th><th>市場</th><th>收盤價</th><th>{label}價</th><th>成交張數</th><th>交易日</th></tr></thead><tbody>{shown.map((row) => <tr key={`${row.market}-${row.stock_id}`}><td><button type="button" className="home-link" onClick={() => onStockSelect(row.stock_id, rows.map((item) => item.stock_id))}><strong>{row.stock_id}</strong> {row.name}</button></td><td>{marketLabels[row.market]}</td><td className={direction === "up" ? "up" : "down"}>{row.close.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}</td><td>{row.limit_price.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}</td><td>{(row.volume_shares / 1000).toLocaleString("zh-TW", { maximumFractionDigits: 1 })}</td><td>{dateText(row.trade_date)}</td></tr>)}</tbody></table></div>
          <div className="home-page-nav" aria-label={`${label}清單切換`}><span>{currentPage * PAGE_SIZE + 1}–{currentPage * PAGE_SIZE + shown.length} / {rows.length}</span><button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>上一個</button><button type="button" disabled={currentPage >= pageCount - 1} onClick={() => setPage(currentPage + 1)}>下一個</button></div>
        </> : <p className="home-empty">{listing?.complete && listing.official_count === 0 ? `當日沒有${label}股票。` : "這個市場的明細尚未完成核對，或上市與上櫃統計日期不同。可切換單一市場查看。"}</p>}
        <div className="market-limit-sources">{sources.map(([key, source]) => <span key={key}>{marketLabels[key as Market]} {dateText(source.date)} · {source.status === "complete" ? "已核對" : "待更新"}{source.summary_source_url && <> · <a href={source.summary_source_url} target="_blank" rel="noreferrer">官方家數</a></>}{source.limit_source_url && <> · <a href={source.limit_source_url} target="_blank" rel="noreferrer">漲跌停價</a></>}{source.quote_source_url && <> · <a href={source.quote_source_url} target="_blank" rel="noreferrer">收盤行情</a></>}</span>)}</div>
      </>}
    </section>
  </div>;
}
