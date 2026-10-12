import { useEffect, useMemo, useState } from "react";
import {
  fetchRotationCoverage, fetchRotationDetail, fetchRotationFilters, fetchRotationRanking,
  type RotationCoverage, type RotationDetail, type RotationRow, type RotationStock
} from "../api";

type Props = { active: boolean; onStockSelect: (code: string) => void; focusedSector?: string };
const pct = (value: number | null | undefined, digits = 1) => value == null ? "—" : `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
const share = (value: number | null | undefined) => value == null ? "—" : `${value >= 0 ? "+" : ""}${(value / 1000).toLocaleString("zh-TW", { maximumFractionDigits: 0 })} 張`;
const stageLabel: Record<string, string> = {
  Dormant: "沉寂", Improving: "改善中", "Early Rotation": "早期輪動",
  Leading: "領先", Crowded: "擁擠", Weakening: "轉弱"
};
const nameOf = (row: RotationRow) => row.l3 || row.l2 || row.l1;

function RotationMap({ rows, selected, onSelect }: { rows: RotationRow[]; selected: string; onSelect: (key: string) => void }) {
  const points = rows.filter(row => row.relative_strength != null && row.rs_momentum != null);
  const maxX = Math.max(5, ...points.map(row => Math.abs(row.relative_strength || 0)));
  const maxY = Math.max(5, ...points.map(row => Math.abs(row.rs_momentum || 0)));
  return <div className="rotation-map-wrap">
    <div className="rotation-subhead"><h3>輪動地圖</h3><span>橫軸 相對強度 RS · 縱軸 RS 動能</span></div>
    <svg viewBox="0 0 660 300" role="img" aria-label="產業輪動地圖" className="rotation-map">
      <rect x="28" y="10" width="612" height="264" rx="7" fill="rgba(255,255,255,.025)" stroke="rgba(236,241,244,.12)" />
      <line x1="334" x2="334" y1="10" y2="274" stroke="rgba(236,241,244,.2)" />
      <line x1="28" x2="640" y1="142" y2="142" stroke="rgba(236,241,244,.2)" />
      <text x="40" y="32">改善中</text><text x="575" y="32">領先</text>
      <text x="40" y="264">沉寂</text><text x="575" y="264">轉弱</text>
      {points.slice(0, 80).map(row => {
        const x = 334 + 296 * Math.max(-1, Math.min(1, (row.relative_strength || 0) / maxX));
        const y = 142 - 122 * Math.max(-1, Math.min(1, (row.rs_momentum || 0) / maxY));
        return <g key={row.sector_key} onClick={() => onSelect(row.sector_key)} className="rotation-map-dot" tabIndex={0} role="button" aria-label={`${nameOf(row)}，分數 ${row.rotation_score.toFixed(1)}`} onKeyDown={event => { if (event.key === "Enter") onSelect(row.sector_key); }}>
          <circle cx={x} cy={y} r={selected === row.sector_key ? 7 : 4.5} fill={selected === row.sector_key ? "#f2c36b" : "#6fe7c5"} fillOpacity={Math.max(.45, Math.min(1, row.rotation_score / 80))} />
          <title>{`${row.sector_key}\nRS ${pct(row.relative_strength)} / 動能 ${pct(row.rs_momentum)}`}</title>
        </g>;
      })}
    </svg>
    <p className="muted">每個點是一個細產業；輪動訊號使用全部已驗證成分股。</p>
  </div>;
}

function Timeline({ rows }: { rows: RotationRow[] }) {
  if (rows.length < 2) return <p className="muted">歷史資料不足，回補後顯示 20 日軌跡。</p>;
  const min = Math.min(...rows.map(row => row.rotation_score));
  const max = Math.max(...rows.map(row => row.rotation_score));
  const points = rows.map((row, i) => `${20 + i * 600 / (rows.length - 1)},${115 - 95 * (row.rotation_score - min) / Math.max(1, max - min)}`).join(" ");
  return <div className="rotation-timeline">
    <svg viewBox="0 0 640 135" role="img" aria-label="近 20 個交易日輪動分數走勢">
      <line x1="20" y1="115" x2="620" y2="115" stroke="rgba(236,241,244,.2)" />
      <polyline points={points} fill="none" stroke="#6fe7c5" strokeWidth="2.5" />
      {rows.map((row, i) => <circle key={row.trade_date} cx={20 + i * 600 / (rows.length - 1)} cy={115 - 95 * (row.rotation_score - min) / Math.max(1, max - min)} r="3" fill="#f2c36b"><title>{`${row.trade_date} · ${row.rotation_score.toFixed(1)} · ${stageLabel[row.stage] || row.stage}`}</title></circle>)}
    </svg>
    <div className="rotation-timeline-labels"><span>{rows[0].trade_date}</span><strong>{rows.at(-1)?.rotation_score.toFixed(1)} 分</strong><span>{rows.at(-1)?.trade_date}</span></div>
  </div>;
}

function StockGroup({ title, rows, onSelect, value }: { title: string; rows: RotationStock[]; onSelect: (code: string) => void; value: (row: RotationStock) => string }) {
  return <div className="rotation-stock-group"><h4>{title}</h4>
    {rows.length ? <div className="rotation-stock-list">{rows.map(row => <button type="button" key={`${row.market}-${row.stock_id}`} onClick={() => onSelect(row.stock_id)}>
      <span><strong>{row.name}</strong><small>{row.stock_id} · {row.market === "TWSE" ? "上市" : "上櫃"} · {row.is_primary_here ? "主要" : "跨產業"}</small></span><b>{value(row)}</b>
    </button>)}</div> : <p className="muted">當日沒有符合條件的成分股</p>}
  </div>;
}

export function SectorRotationView({ active, onStockSelect, focusedSector }: Props) {
  const [coverage, setCoverage] = useState<RotationCoverage | null>(null);
  const [filters, setFilters] = useState<{ l1: string; l2: string }[]>([]);
  const [rows, setRows] = useState<RotationRow[]>([]);
  const [detail, setDetail] = useState<RotationDetail | null>(null);
  const [level, setLevel] = useState<1 | 2 | 3>(3);
  const [l1, setL1] = useState("");
  const [l2, setL2] = useState("");
  const [includeSmall, setIncludeSmall] = useState(false);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const l1Options = useMemo(() => [...new Set(filters.map(item => item.l1))], [filters]);
  const l2Options = useMemo(() => [...new Set(filters.filter(item => item.l1 === l1).map(item => item.l2))], [filters, l1]);

  useEffect(() => {
    if (!active) return;
    let live = true;
    Promise.all([fetchRotationCoverage(), fetchRotationFilters()]).then(([nextCoverage, nextFilters]) => {
      if (live) { setCoverage(nextCoverage); setFilters(nextFilters); }
    }).catch(reason => live && setError(reason instanceof Error ? reason.message : "資料讀取失敗"));
    return () => { live = false; };
  }, [active]);

  useEffect(() => {
    if (!active) return;
    let live = true;
    fetchRotationRanking(level, l1, l2, includeSmall).then(next => {
      if (!live) return;
      setRows(next);
      setSelected(current => next.some(row => row.sector_key === focusedSector) ? focusedSector! : next.some(row => row.sector_key === current) ? current : next[0]?.sector_key || "");
    }).catch(reason => live && setError(reason instanceof Error ? reason.message : "排行讀取失敗"));
    return () => { live = false; };
  }, [active, level, l1, l2, includeSmall, focusedSector]);

  useEffect(() => {
    if (!active || !selected) { setDetail(null); return; }
    setDetail(null);
    let live = true;
    fetchRotationDetail(selected).then(next => live && setDetail(next))
      .catch(reason => live && setError(reason instanceof Error ? reason.message : "產業明細讀取失敗"));
    return () => { live = false; };
  }, [active, selected]);

  return <section className="sector-rotation-panel rotation-v3">
    <div className="section-title"><h2>細產業觀測台</h2><span className="rotation-version">Fine Sector · V4</span></div>
    <p className="muted">上市櫃完整名單 × 官方營業項目 × 細產業 × 股價與法人股數</p>
    {error ? <p className="sector-warning" role="alert">{error}</p> : null}
    {coverage ? <div className="rotation-coverage-grid">
      <div><small>上市 / 上櫃普通公司</small><strong>{coverage.twse_ordinary_total} / {coverage.tpex_ordinary_total}</strong></div>
      <div><small>電子與相鄰產業</small><strong>{coverage.target_total}</strong><span>上市 {coverage.twse_target} · 上櫃 {coverage.tpex_target}</span></div>
      <div><small>已驗證 L1 / L2 / L3</small><strong>{coverage.l1_mapped_pct}% / {coverage.l2_mapped_pct}% / {coverage.l3_mapped_pct}%</strong><span>{coverage.l1_mapped_total} / {coverage.l2_mapped_total} / {coverage.l3_mapped_total} 檔</span></div>
      <div><small>主要 L3 / 待覆核</small><strong>{coverage.primary_l3_total} / {coverage.review_queue_total}</strong><span>待覆核 {coverage.review_queue_pct}% · 成分可跨產業</span></div>
    </div> : null}
    <p className="rotation-date muted">名單更新 {coverage?.last_sync_at?.slice(0, 16) || "尚未同步"} · 輪動資料 {rows[0]?.trade_date || "尚未回補"}</p>
    <div className="rotation-controls">
      <div className="sector-window-buttons" aria-label="分類層級">{([3, 2, 1] as const).map(value => <button type="button" key={value} className={level === value ? "active" : ""} onClick={() => { setLevel(value); setSelected(""); }}>L{value}</button>)}</div>
      <label>大產業<select value={l1} onChange={event => { setL1(event.target.value); setL2(""); }}><option value="">全部</option>{l1Options.map(value => <option key={value}>{value}</option>)}</select></label>
      <label>次產業<select value={l2} onChange={event => setL2(event.target.value)} disabled={!l1 || level === 1}><option value="">全部</option>{l2Options.map(value => <option key={value}>{value}</option>)}</select></label>
      <label className="rotation-checkbox"><input type="checkbox" checked={includeSmall} onChange={event => setIncludeSmall(event.target.checked)} /> 顯示小樣本</label>
    </div>
    <div className="rotation-layout">
      <div className="rotation-ranking-wrap"><div className="rotation-subhead"><h3>輪動排行</h3><span>預設顯示有效樣本 ≥ 5 檔</span></div>
        <div className="rotation-table-scroll"><table className="rotation-table"><thead><tr>
          <th>細產業</th><th>分數</th><th>階段</th><th>1D</th><th>5D</th><th>20D</th><th>廣度</th><th>主要歸屬成交占比 Δ</th><th>主要歸屬法人買賣超</th><th>成分</th><th>廣度品質</th>
        </tr></thead><tbody>{rows.map(row => <tr key={row.sector_key} onClick={() => setSelected(row.sector_key)} className={selected === row.sector_key ? "selected" : ""} tabIndex={0} onKeyDown={event => { if (event.key === "Enter") setSelected(row.sector_key); }}>
          <td><strong>{nameOf(row)}</strong><small title={row.sector_key}>{row.level === 3 ? `${row.l1} / ${row.l2}` : row.sector_key}</small>{row.concentrated ? <em>集中</em> : null}</td>
          <td className="rotation-score">{row.rotation_score.toFixed(1)}</td><td><span className={`rotation-stage stage-${row.stage.toLowerCase().replace(/\s/g, "-")}`}>{stageLabel[row.stage] || row.stage}</span></td>
          <td className={row.return_1d == null || row.return_1d === 0 ? "" : row.return_1d > 0 ? "positive" : "negative"}>{pct(row.return_1d)}</td>
          <td className={row.return_5d == null || row.return_5d === 0 ? "" : row.return_5d > 0 ? "positive" : "negative"}>{pct(row.return_5d)}</td>
          <td className={row.return_20d == null || row.return_20d === 0 ? "" : row.return_20d > 0 ? "positive" : "negative"}>{pct(row.return_20d)}</td>
          <td>{row.breadth == null ? "—" : `${(row.breadth * 100).toFixed(0)}%`}</td>
          <td>{row.turnover_share_delta == null ? "—" : `${(row.turnover_share_delta * 100).toFixed(2)} pp`}</td>
          <td title={`法人涵蓋 ${(100 * (row.institutional_coverage || 0)).toFixed(0)}%，單位為股數`}>{share(row.institutional_net_shares)}</td>
          <td>{row.observed_count}/{row.constituent_count}</td><td>{row.breadth_quality === "good" ? "完整" : row.breadth_quality === "partial" ? "部分" : "低"}</td>
        </tr>)}</tbody></table></div>
        {!rows.length ? <p className="muted rotation-empty">這個條件目前沒有足夠樣本；可開啟「顯示小樣本」查看。</p> : null}
      </div>
      <RotationMap rows={rows} selected={selected} onSelect={setSelected} />
    </div>
    {detail ? <div className="rotation-detail">
      <div className="rotation-subhead"><div><h3>{detail.sector.l3 || detail.sector.l2 || detail.sector.l1}</h3><p className="muted">{detail.sector.sector_key} · 有效 {detail.sector.observed_count}/{detail.sector.constituent_count} 檔</p></div><span>{stageLabel[detail.sector.stage] || detail.sector.stage}</span></div>
      <div className="rotation-detail-metrics">
        <div><small>主要歸屬法人買賣超</small><strong>{share(detail.sector.institutional_net_shares)}</strong><span>涵蓋 {((detail.sector.institutional_coverage || 0) * 100).toFixed(0)}% · 股數換算</span></div>
        <div><small>估計市場承接壓力</small><strong>{detail.sector.accumulation_pressure == null ? "—" : `${(detail.sector.accumulation_pressure * 100).toFixed(0)} / 100`}</strong><span>CMF20 + MFI14 · 非法人資金</span></div>
        <div><small>成交擴張</small><strong>{detail.sector.turnover_expansion == null ? "—" : `${detail.sector.turnover_expansion.toFixed(2)}×`}</strong><span>估計成交額 / 前 5 日均值</span></div>
      </div>
      {detail.sector.concentrated ? <p className="sector-warning">Concentrated：前 1 檔占成交 {((detail.sector.top1_turnover_share || 0) * 100).toFixed(0)}%，前 3 檔 {((detail.sector.top3_turnover_share || 0) * 100).toFixed(0)}%。請搭配廣度判讀。</p> : null}
      <div className="rotation-diff-timeline"><div><h4>Rotation Diff · 前一交易日</h4>{detail.diff ? <p>分數 {detail.diff.score_delta >= 0 ? "+" : ""}{detail.diff.score_delta.toFixed(1)} · 排名 {detail.diff.rank_change == null ? "—" : `${detail.diff.rank_change >= 0 ? "+" : ""}${detail.diff.rank_change}`} · 廣度 {(detail.diff.breadth_delta * 100).toFixed(0)} pp · {stageLabel[detail.diff.stage_from]} → {stageLabel[detail.diff.stage_to]}</p> : <p className="muted">尚無前一交易日資料</p>}</div><div><h4>20 日 Rotation Timeline</h4><Timeline rows={detail.timeline} /></div></div>
      <div className="rotation-groups">
        <StockGroup title="全部已驗證成分股" rows={detail.stocks} onSelect={onStockSelect} value={row => pct(row.return_1d)} />
        <StockGroup title="領漲股" rows={detail.leaders} onSelect={onStockSelect} value={row => pct(row.return_5d)} />
        <StockGroup title="早期輪動" rows={detail.early_rotation} onSelect={onStockSelect} value={row => row.early_rise ? "初升訊號" : pct(row.return_1d)} />
        <StockGroup title="跟漲候選" rows={detail.followers} onSelect={onStockSelect} value={row => pct(row.return_1d)} />
        <StockGroup title="法人買超" rows={detail.institutional_buy} onSelect={onStockSelect} value={row => share(row.institutional_net_shares)} />
        <StockGroup title="量能放大" rows={detail.volume_surge} onSelect={onStockSelect} value={row => row.volume_ratio == null ? "—" : `${row.volume_ratio.toFixed(1)}×`} />
        <StockGroup title="突破候選" rows={detail.breakouts} onSelect={onStockSelect} value={row => pct(row.return_1d)} />
      </div>
    </div> : null}
    <p className="muted rotation-footnote">成分、廣度與輪動分數使用全部已驗證的多重產業歸屬；成交占比與法人股數只計入每股唯一主要歸屬，避免跨產業重複加總。法人股數換算張數，並非淨流入金額。CMF/MFI 為估計承接壓力。歷史軌跡採現行分類回看，不作無前視偏誤的回測。</p>
  </section>;
}
