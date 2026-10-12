import { useEffect, useState } from "react";
import { BarChart3 } from "lucide-react";
import { fetchFinancialTrends, type FinancialQuarter, type FinancialTrends as FinancialTrendsData } from "../api";

type MetricKey = "gross_margin_pct" | "eps_single_quarter" | "pe_ratio_quarter_end";

function Metric({ rows, metric, label, unit, color }: {
  rows: FinancialQuarter[]; metric: MetricKey; label: string; unit: string; color: string;
}) {
  const values = rows.map(row => row[metric]);
  const valid = values.filter((value): value is number => value != null && Number.isFinite(value));
  const min = valid.length ? Math.min(...valid) : 0;
  const max = valid.length ? Math.max(...valid) : 1;
  const span = Math.max(max - min, Math.abs(max) * 0.08, 0.5);
  const coordinates = rows.map((row, index) => {
    const value = row[metric];
    if (value == null || !Number.isFinite(value)) return null;
    return { x: 26 + index * 90, y: 72 - ((value - min) / span) * 48, value, period: row.period };
  });
  const path = coordinates.map((point, index) => point ? `${index && coordinates[index - 1] ? "L" : "M"}${point.x} ${point.y}` : "").join(" ");
  const first = valid[0], last = valid.at(-1);
  const delta = valid.length >= 2 && first != null && last != null ? last - first : null;
  return <div className="financial-metric">
    <div className="financial-metric-head"><strong>{label}</strong><span>{delta == null ? "資料不足" : `近四季 ${delta >= 0 ? "+" : ""}${delta.toFixed(2)} ${unit === "%" ? "百分點" : unit}`}</span></div>
    <svg viewBox="0 0 320 88" role="img" aria-label={`${label}近四季變化`}>
      <line x1="26" y1="77" x2="296" y2="77" stroke="rgba(255,255,255,.16)" />
      <path d={path} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" />
      {coordinates.map((point, index) => point ? <circle key={index} cx={point.x} cy={point.y} r="4" fill={color}><title>{`${point.period}：${point.value.toFixed(2)}${unit}`}</title></circle> : null)}
    </svg>
    <div className="financial-values">{rows.map(row => <div key={row.period}><span>{row.period}</span><b>{row[metric] == null ? "—" : `${row[metric]?.toFixed(2)}${unit}`}</b></div>)}</div>
  </div>;
}

export function FinancialTrends({ stockId }: { stockId: string }) {
  const [data, setData] = useState<FinancialTrendsData | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setData(null);
    fetchFinancialTrends(stockId).then(value => { if (live) setData(value); })
      .catch(() => { if (live) setData(null); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [stockId]);
  return <section className="broker-panel stock-detail-panel financial-trends-panel">
    <div className="section-title"><BarChart3 size={20} /><h2>近四季財報與本益比變化</h2></div>
    {loading ? <p className="muted">載入官方財報與評價歷史…</p> : data?.quarters.length ? <>
      <div className="financial-metrics-grid">
        <Metric rows={data.quarters} metric="gross_margin_pct" label="單季毛利率" unit="%" color="#6fe7c5" />
        <Metric rows={data.quarters} metric="eps_single_quarter" label="單季 EPS" unit=" 元" color="#f6bd60" />
        <Metric rows={data.quarters} metric="pe_ratio_quarter_end" label="季末本益比" unit=" 倍" color="#e89ce1" />
      </div>
      <p className="financial-trends-note">{data.note} 來源：<a href={data.quarters.at(-1)?.source_url} target="_blank" rel="noreferrer">{data.income_source} ↗</a>、{data.pe_source}。資料截至 {data.quarters.at(-1)?.period}。{data.source_error ? `本益比更新暫時失敗：${data.source_error}` : ""}</p>
    </> : <p className="muted">尚無可確認的季度財報；更新工作完成後會顯示，未申報季度不填入估算值。</p>}
  </section>;
}
