import { useEffect, useMemo, useState } from "react";
import { fetchMarketMargin, fetchOwnership, type MarginHistory, type MarginRow, type OwnershipHistory, type OwnershipRow } from "../api";

type Mode = "amount" | "margin" | "short" | "ratio";
const modes: { key: Mode; label: string; unit: string }[] = [
  { key: "amount", label: "融資金額", unit: "億元" }, { key: "margin", label: "融資張數", unit: "張" }, { key: "short", label: "融券張數", unit: "張" }, { key: "ratio", label: "券資比", unit: "%" }
];
const marketRanges = { "1M": 31, "3M": 93, "6M": 186, "1Y": 366 };
const ownerRanges = { "3M": 93, "6M": 186, "1Y": 366, "2Y": 732 };
const fmt = (n: number | null | undefined, digits = 0) => n == null ? "—" : n.toLocaleString("zh-TW", { maximumFractionDigits: digits });
const signed = (n: number | null | undefined, suffix = "") => n == null ? "—" : `${n > 0 ? "+" : ""}${fmt(n, suffix === " pp" ? 2 : 0)}${suffix}`;
const signedAmount = (n: number | null | undefined) => n == null ? "—" : `${n > 0 ? "+" : ""}${fmt(n, 2)} 億元`;
const deltaTone = (n: number | null | undefined) => n == null || n === 0 ? "" : n > 0 ? "positive" : "negative";
const val = (row: MarginRow, mode: Mode) => mode === "amount" ? row.margin_balance_yi_twd ?? null : mode === "margin" ? row.margin_balance_lots : mode === "short" ? row.short_balance_lots : row.short_to_margin_pct;
function recent<T>(rows: T[], days: number, key: keyof T): T[] {
  if (days >= 10000) return rows;
  const cutoff = new Date(); cutoff.setDate(cutoff.getDate() - days);
  const iso = cutoff.toISOString().slice(0, 10);
  return rows.filter(row => String(row[key]) >= iso);
}

function RangeTabs<T extends string>({ choices, current, onChange }: { choices: T[]; current: T; onChange: (value: T) => void }) {
  return <div className="chip-tabs" role="group" aria-label="時間範圍">{choices.map(choice => <button key={choice} className={choice === current ? "active" : ""} type="button" onClick={() => onChange(choice)}>{choice}</button>)}</div>;
}
function ModeTabs({ current, onChange, showAmount = false }: { current: Mode; onChange: (mode: Mode) => void; showAmount?: boolean }) {
  return <div className="chip-tabs" role="group" aria-label="圖表模式">{modes.filter(mode => mode.key !== "amount" || showAmount).map(mode => <button key={mode.key} className={mode.key === current ? "active" : ""} type="button" onClick={() => onChange(mode.key)}>{mode.label}</button>)}</div>;
}

type PlotPoint = { date: string; value: number | null; second?: number | null; tip: string[] };
function LinePlot({ points, unit, secondLabel, secondUnit = "元", minSpan = 0, independentScale = false }: { points: PlotPoint[]; unit: string; secondLabel?: string; secondUnit?: string; minSpan?: number; independentScale?: boolean }) {
  const [hover, setHover] = useState<number | null>(null);
  const valid = points.map((point, index) => ({ ...point, index })).filter(point => point.value != null);
  if (!valid.length) return <p className="chip-empty">所選期間沒有可繪製的官方資料。</p>;
  const width = 760, height = 190, left = 76, right = secondLabel && (secondUnit !== unit || independentScale) ? 49 : 14, top = 14, bottom = 28;
  const sharedScale = secondLabel && secondUnit === unit && !independentScale;
  const nums = valid.map(point => point.value as number).concat(sharedScale ? points.map(point => point.second).filter((number): number is number => number != null) : []);
  let min = Math.min(...nums), max = Math.max(...nums);
  if (max - min < minSpan) { const middle = (max + min) / 2; min = middle - minSpan / 2; max = middle + minSpan / 2; }
  if (max === min) { min -= Math.max(1, min * .02); max += Math.max(1, max * .02); }
  const secondary = points.map(point => point.second).filter((number): number is number => number != null);
  let min2 = secondary.length ? Math.min(...secondary) : 0, max2 = secondary.length ? Math.max(...secondary) : 1;
  if (max2 - min2 < minSpan) { const middle = (max2 + min2) / 2; min2 = middle - minSpan / 2; max2 = middle + minSpan / 2; }
  if (max2 === min2) { min2 -= Math.max(1, min2 * .02); max2 += Math.max(1, max2 * .02); }
  const x = (i: number) => points.length === 1 ? (left + width - right) / 2 : left + i / (points.length - 1) * (width - left - right);
  const y = (n: number) => top + (max - n) / (max - min) * (height - top - bottom);
  const y2 = (n: number) => sharedScale ? y(n) : top + (max2 - n) / (max2 - min2) * (height - top - bottom);
  const segments = (get: (point: PlotPoint) => number | null | undefined, scale: (n: number) => number) => points.slice(1).flatMap((point, offset) => {
    const before = get(points[offset]), after = get(point);
    if (before == null || after == null) return [];
    return [{ d: `M${x(offset).toFixed(1)},${scale(before).toFixed(1)} L${x(offset + 1).toFixed(1)},${scale(after).toFixed(1)}`, color: after > before ? "#ff9f9f" : after < before ? "#6fe7c5" : "#64a6ff" }];
  });
  const shown = hover == null ? points.at(-1) : points[hover];
  return <div className="chip-plot-wrap">
    <svg className="chip-plot" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${points[0]?.date} 至 ${points.at(-1)?.date} 走勢圖`} onPointerLeave={() => setHover(null)}>
      {[0, .5, 1].map(f => <g key={f}><line x1={left} x2={width-right} y1={top + f*(height-top-bottom)} y2={top + f*(height-top-bottom)} stroke="rgba(236,241,244,.11)" /><text x={left-6} y={top + f*(height-top-bottom)+4} textAnchor="end" fill="#9eabb2" fontSize="10">{fmt(max - f*(max-min), unit === "%" && minSpan > 0 && minSpan < .5 ? 2 : unit === "%" || unit === "億元" ? 1 : 0)}</text>{secondLabel && !sharedScale && <text x={width-right+6} y={top + f*(height-top-bottom)+4} fill="#f2c36b" fontSize="10">{fmt(max2 - f*(max2-min2), independentScale ? 2 : 1)}</text>}</g>)}
      {segments(point => point.value, y).map((segment, i) => <path key={`main-${i}`} d={segment.d} fill="none" stroke={segment.color} strokeWidth="2.5" />)}
      {secondLabel && segments(point => point.second, y2).map((segment, i) => <path key={`second-${i}`} d={segment.d} fill="none" stroke={independentScale ? "#f2c36b" : segment.color} strokeWidth="2" strokeDasharray="5 3" />)}
      {points.length === 1 && points[0].value != null && <g><line x1={left} x2={width-right} y1={y(points[0].value)} y2={y(points[0].value)} stroke="rgba(100,166,255,.4)" strokeDasharray="4 5" /><circle cx={x(0)} cy={y(points[0].value)} r="9" fill="rgba(100,166,255,.18)" /><circle cx={x(0)} cy={y(points[0].value)} r="5" fill="#64a6ff" /></g>}
      {hover != null && points[hover]?.value != null && <g><line x1={x(hover)} x2={x(hover)} y1={top} y2={height-bottom} stroke="rgba(236,241,244,.4)" strokeDasharray="3 3" /><circle cx={x(hover)} cy={y(points[hover].value!)} r="4" fill="#64a6ff" /></g>}
      {points.map((point, index) => <rect key={`${point.date}-${index}`} x={x(index)-(width-left-right)/Math.max(1, points.length-1)/2} y={top} width={Math.max(3,(width-left-right)/Math.max(1,points.length-1))} height={height-top-bottom} fill="transparent" onPointerEnter={() => setHover(index)} />)}
      {points.length === 1 ? <text x={x(0)} y={height-5} textAnchor="middle" fill="#9eabb2" fontSize="11">{points[0].date}</text> : <><text x={left} y={height-5} fill="#9eabb2" fontSize="11">{points[0]?.date}</text><text x={width-right} y={height-5} textAnchor="end" fill="#9eabb2" fontSize="11">{points.at(-1)?.date}</text></>}
    </svg>
    <div className="chip-plot-tip" aria-live="polite"><b>{shown?.date}</b>{shown?.tip.map((line, index) => <span key={index}>{line}</span>)}</div>
    <div className="chip-plot-legend"><span>● {unit === "%" ? "比例" : "餘額"}（左軸，{unit}；紅升綠降）</span>{secondLabel && <span className="price">┄ {secondLabel}（{sharedScale ? "同軸" : "右軸"}，{secondUnit}）</span>}</div>
  </div>;
}

function marginPoints(rows: MarginRow[], mode: Mode, prices?: Map<string, number>, overlay = false): PlotPoint[] {
  return rows.map(row => ({ date: row.trade_date, value: val(row, mode), second: overlay ? prices?.get(row.trade_date) ?? null : null, tip: [
    `融資餘額 ${fmt(row.margin_balance_lots)} 張（增減 ${signed(row.margin_change_lots)} 張）`,
    ...(row.margin_balance_yi_twd != null ? [`融資金額 ${fmt(row.margin_balance_yi_twd, 2)} 億元（增減 ${signedAmount(row.margin_change_yi_twd)}）`] : []),
    `融券餘額 ${fmt(row.short_balance_lots)} 張（增減 ${signed(row.short_change_lots)} 張）`,
    `券資比 ${fmt(row.short_to_margin_pct, 2)}%`,
    ...(overlay ? [`收盤價 ${fmt(prices?.get(row.trade_date), 2)} 元（右軸）`] : [])
  ] }));
}

export function MarketMarginCard() {
  const [market, setMarket] = useState<"TWSE" | "TPEx" | "combined">("TWSE");
  const [data, setData] = useState<MarginHistory | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [range, setRange] = useState<keyof typeof marketRanges>("3M");
  const [mode, setMode] = useState<Mode>("amount");
  useEffect(() => { let live = true; setData(null); setError(""); fetchMarketMargin(market).then(value => { if (live) setData(value); }).catch(reason => { if (live) setError(String(reason)); }); return () => { live = false; }; }, [market]);
  const latest = data?.latest;
  const rows = useMemo(() => recent(data?.rows || [], marketRanges[range], "trade_date"), [data, range]);
  return <section className="home-section chip-market"><div className="home-section-head"><div><h2>大盤融資融券</h2><p>官方信用交易餘額 · 張數與金額分開呈現</p></div><small>Last updated · {latest?.trade_date || "—"}</small></div>
    <div className="chip-market-controls chip-tabs" role="group" aria-label="市場">{[["TWSE", "上市"], ["TPEx", "上櫃"], ["combined", "合計"]].map(([key, label]) => <button key={key} type="button" className={market === key ? "active" : ""} onClick={() => { setMarket(key as typeof market); setMode(key === "TWSE" ? "amount" : "margin"); }}>{label}</button>)}</div>
    {error ? <p className="chip-empty">融資融券資料暫時無法讀取；首頁其他內容仍可使用。</p> : !data ? <div className="chip-skeleton" aria-busy="true" /> : !latest ? <p className="chip-empty">尚無已保存的官方日報；執行每日資料更新後顯示。</p> : <>
      <div className="chip-summary">
        <div><small>融資餘額{latest.margin_balance_yi_twd != null ? "（金額）" : "（張數）"}</small><strong>{latest.margin_balance_yi_twd != null ? `${fmt(latest.margin_balance_yi_twd, 2)} 億元` : `${fmt(latest.margin_balance_lots)} 張`}</strong>{latest.margin_balance_yi_twd != null ? <><span>單日 <b className={deltaTone(latest.margin_change_yi_twd)}>{signedAmount(latest.margin_change_yi_twd)}</b> · 近 5 日 <b className={deltaTone(latest.margin_5d_change_yi_twd)}>{signedAmount(latest.margin_5d_change_yi_twd)}</b></span><span>融資餘額張數 {fmt(latest.margin_balance_lots)} 張</span></> : <span>單日 <b className={deltaTone(latest.margin_change_lots)}>{signed(latest.margin_change_lots, " 張")}</b> · 近 5 日 <b className={deltaTone(latest.margin_5d_change_lots)}>{signed(latest.margin_5d_change_lots, " 張")}</b></span>}</div>
        <div><small>融券餘額（張數）</small><strong>{fmt(latest.short_balance_lots)} 張</strong><span>單日 <b className={deltaTone(latest.short_change_lots)}>{signed(latest.short_change_lots, " 張")}</b> · 近 5 日 <b className={deltaTone(latest.short_5d_change_lots)}>{signed(latest.short_5d_change_lots, " 張")}</b></span></div>
        <div><small>券資比（%） <button type="button" className="chip-info" aria-label="券資比＝融券餘額張數除以融資餘額張數再乘以100%。不同單位的融資金額不能相除。" data-tip="券資比＝融券餘額張數 ÷ 融資餘額張數 × 100%。融資金額是新臺幣仟元，不能與融券張數相除。">ⓘ</button></small><strong>{fmt(latest.short_to_margin_pct, 2)}%</strong><span>近 5 日 <b className={deltaTone(latest.ratio_5d_change_pp)}>{signed(latest.ratio_5d_change_pp, " pp")}</b></span></div>
      </div>
      <button className="chip-expand" type="button" onClick={() => setExpanded(!expanded)}>{expanded ? "收合走勢" : "展開歷史走勢"}</button>
      {expanded && <><div className="chip-chart-controls"><RangeTabs choices={Object.keys(marketRanges) as (keyof typeof marketRanges)[]} current={range} onChange={setRange} /><ModeTabs current={mode} onChange={setMode} showAmount={market === "TWSE"} /></div><LinePlot points={marginPoints(rows, mode)} unit={modes.find(item => item.key === mode)!.unit} /></>}
    </>}
    <p className="chip-source">來源：<a href={market === "combined" ? data?.source_urls.TWSE : data?.source_urls[market]} target="_blank" rel="noreferrer">{market === "combined" ? "TWSE" : market}</a>{market === "combined" && <> ＋ <a href={data?.source_urls.TPEx} target="_blank" rel="noreferrer">TPEx</a></>} · 每交易日更新。上市融資金額採 TWSE 官方「融資金額（仟元）」換算，10 萬仟元＝1 億元；單日變化比較官方今日與前日餘額。今日餘額可能在次日調整，請以後續官方前日餘額為準。上櫃與合計僅顯示張數，融券無金額欄位。</p>
  </section>;
}

export function StockOwnershipTrends({ stockId }: { stockId: string }) {
  const [owner, setOwner] = useState<OwnershipHistory | null>(null);
  const [ownerError, setOwnerError] = useState(false);
  const [threshold, setThreshold] = useState("1000");
  const [ownerRange, setOwnerRange] = useState<keyof typeof ownerRanges>("1Y");
  useEffect(() => { if (!stockId) return; let live = true; setOwner(null); setOwnerError(false); fetchOwnership(stockId).then(value => { if (live) setOwner(value); }).catch(() => { if (live) setOwnerError(true); }); return () => { live = false; }; }, [stockId]);
  const ownerRows = useMemo(() => recent(owner?.rows || [], ownerRanges[ownerRange], "report_date"), [owner, ownerRange]);
  const ownerPoints = (rows: OwnershipRow[], tier: string): PlotPoint[] => rows.map(row => { const item = row.large[tier]; return { date: row.report_date, value: item?.pct ?? null, tip: [`${owner?.thresholds[tier] || tier} ${fmt(item?.pct, 2)}%`, `持股 ${fmt(item?.lots, 1)} 張`, `持股人數 ${fmt(item?.holders)} 人`] }; });
  const currentOwner = ownerRows.at(-1)?.large[threshold];
  const prior = ownerRows.at(-2)?.large[threshold];
  const four = ownerRows.at(-5)?.large[threshold];
  const twelve = ownerRows.at(-13)?.large[threshold];
  return <section className="quotes-panel stock-detail-panel chip-detail"><div className="section-title"><h2>大戶持股走勢</h2></div>
      {ownerError ? <p className="chip-empty">TDCC 資料讀取失敗；其他個股資料仍可使用。</p> : !owner ? <div className="chip-skeleton" aria-busy="true" /> : !owner.rows.length ? <p className="chip-empty">目前沒有這檔證券的 TDCC 每週股權分散資料；不以其他證券或推算值代替。</p> : <>
        <div className="chip-chart-controls"><RangeTabs choices={Object.keys(ownerRanges) as (keyof typeof ownerRanges)[]} current={ownerRange} onChange={setOwnerRange} /><div className="chip-tabs" role="group" aria-label="大戶門檻">{Object.entries(owner.thresholds).map(([key, label]) => <button key={key} type="button" title={label} className={threshold === key ? "active" : ""} onClick={() => setThreshold(key)}>逾{key}張</button>)}</div></div>
        <div className="chip-owner-summary"><span>資料日期 <b>{ownerRows.at(-1)?.report_date || "—"}</b></span><span>持股比例 <b>{fmt(currentOwner?.pct, 2)}%</b></span><span>持股張數 <b>{fmt(currentOwner?.lots, 1)} 張</b></span><span>人數 <b>{fmt(currentOwner?.holders)} 人</b></span><span>較上週 <b className={deltaTone(currentOwner?.pct != null && prior?.pct != null ? currentOwner.pct - prior.pct : null)}>{currentOwner?.pct != null && prior?.pct != null ? signed(currentOwner.pct-prior.pct, " pp") : "—"}</b></span><span>近 4 週 <b className={deltaTone(currentOwner?.pct != null && four?.pct != null ? currentOwner.pct - four.pct : null)}>{currentOwner?.pct != null && four?.pct != null ? signed(currentOwner.pct-four.pct, " pp") : "—"}</b></span><span>近 12 週 <b className={deltaTone(currentOwner?.pct != null && twelve?.pct != null ? currentOwner.pct - twelve.pct : null)}>{currentOwner?.pct != null && twelve?.pct != null ? signed(currentOwner.pct-twelve.pct, " pp") : "—"}</b></span></div>
        {ownerRows.length < 3 && <p className="chip-note">所選期間只有 {ownerRows.length} 週資料；切換到較長期間可檢視完整週走勢。</p>}
        <LinePlot points={ownerPoints(ownerRows, threshold)} unit="%" minSpan={0.2} />
        <p className="chip-note">{owner.thresholds[threshold]}，依 TDCC 原始級距加總；比例變動可能來自持有人跨越級距，不能直接解讀為主力買超。</p>
        {ownerRows.length >= 2 && ownerRows.some(row => row.small_10?.pct != null) && <div className="chip-comparison"><h3>大戶與散戶持股比例比較</h3><p>逾 1000 張（左軸）vs. 10 張以下（右軸）· 每週更新 · 兩軸刻度不同，請看各自變化</p><LinePlot points={ownerRows.map(row => ({ date: row.report_date, value: row.large["1000"]?.pct ?? null, second: row.small_10?.pct ?? null, tip: [`逾1000張 ${fmt(row.large["1000"]?.pct,2)}%`, `10張以下 ${fmt(row.small_10?.pct,2)}%`] }))} unit="%" secondLabel="10張以下比例" secondUnit="%" independentScale minSpan={0.2} /></div>}
      </>}
      <p className="chip-source">來源：<a href={owner?.source_url || "https://openapi.tdcc.com.tw/"} target="_blank" rel="noreferrer">TDCC 集保戶股權分散表</a>{owner?.archive_url && <> · 歷史週次由<a href={owner.archive_url} target="_blank" rel="noreferrer">公開原始資料歸檔</a>補入，已與現有官方週檔核對</>} · 每週更新 · 最後資料日 {owner?.latest?.report_date || "—"} · 股數以官方級距加總，換算張數除以 1,000。</p>
    </section>;
}
