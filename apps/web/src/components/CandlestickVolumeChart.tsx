import {
  CandlestickSeries,
  ColorType,
  createChart,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type AutoscaleInfo,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type MouseEventParams,
  type Time
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";

import type { PriceQuote } from "../types";
import type { MarginRow } from "../api";

type ChartRow = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type OhlcDisplay = {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type ChartInterval = "daily" | "weekly" | "monthly";
const CHART_HEIGHT = 330;

const intervalLabels: Record<ChartInterval, string> = {
  daily: "日K",
  weekly: "週K",
  monthly: "月K"
};

export function CandlestickVolumeChart({ quotes, margin = [], latestQuoteIsCurrent = true }: { quotes: PriceQuote[]; margin?: MarginRow[]; latestQuoteIsCurrent?: boolean }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [hovered, setHovered] = useState<OhlcDisplay | null>(null);
  const [chartError, setChartError] = useState("");
  const [interval, setInterval] = useState<ChartInterval>("daily");
  const [visibleMA, setVisibleMA] = useState<Record<number, boolean>>({ 5: true, 10: true, 20: true });
  const [showMargin, setShowMargin] = useState(false);
  const [showShort, setShowShort] = useState(false);
  const [showMacd, setShowMacd] = useState(true);

  const rows = useMemo(() => normalizeQuotes(quotes), [quotes]);
  const chartRows = useMemo(() => aggregateRows(rows, interval), [rows, interval]);
  const alignedMargin = useMemo(() => alignMarginRows(chartRows, margin, interval), [chartRows, margin, interval]);
  const latest = hovered ?? chartRows[chartRows.length - 1] ?? null;
  const latestIndex = latest ? chartRows.findIndex(row => row.time === latest.time) : -1;
  const priorClose = latestIndex > 0 ? chartRows[latestIndex - 1].close : null;
  const changePct = latest && priorClose ? (latest.close / priorClose - 1) * 100 : null;
  const hoveredMargin = latest ? alignedMargin.find(row => row.time === latest.time) : null;
  const paneCount = Number(showMargin || showShort) + Number(showMacd);
  const height = CHART_HEIGHT + paneCount * 135;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let chart: IChartApi | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let disposed = false;
    let handleCrosshairMove: ((param: MouseEventParams<Time>) => void) | null = null;
    let hoverCloseLine: IPriceLine | null = null;

    try {
      setChartError("");
      chart = createChart(container, {
        width: Math.max(container.clientWidth, 1),
        height,
        layout: {
          background: { type: ColorType.Solid, color: "#131722" },
          textColor: "#aeb8be"
        },
        grid: {
          vertLines: { color: "rgba(174, 184, 190, 0.12)" },
          horzLines: { color: "rgba(174, 184, 190, 0.12)" }
        },
        crosshair: {
          mode: CrosshairMode.Normal
        },
        rightPriceScale: {
          borderColor: "rgba(174, 184, 190, 0.22)"
        },
        leftPriceScale: {
          visible: showMargin && showShort,
          borderColor: "rgba(174, 184, 190, 0.22)"
        },
        timeScale: {
          borderColor: "rgba(174, 184, 190, 0.22)",
          fixLeftEdge: true,
          fixRightEdge: true,
          rightBarStaysOnScroll: true,
          rightOffset: 0,
          timeVisible: true,
          secondsVisible: false
        },
        handleScroll: {
          mouseWheel: true,
          pressedMouseMove: true,
          horzTouchDrag: true,
          vertTouchDrag: false
        },
        handleScale: {
          mouseWheel: true,
          pinch: true,
          axisPressedMouseMove: true
        }
      });
      const chartApi = chart;

      const candleSeries = chartApi.addSeries(CandlestickSeries, {
        upColor: "#ff5f6d",
        downColor: "#3dd6b5",
        borderUpColor: "#ff5f6d",
        borderDownColor: "#3dd6b5",
        wickUpColor: "#ff5f6d",
        wickDownColor: "#3dd6b5",
        lastValueVisible: false,
        priceLineVisible: false,
        autoscaleInfoProvider: () => buildVisiblePriceScale(chartApi, chartRows)
      });
      const volumeSeries = chartApi.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "volume",
        lastValueVisible: false,
        priceLineVisible: false
      });
      const ma5Series = chartApi.addSeries(LineSeries, { color: "#f2c36b", lineWidth: 2, lastValueVisible: false, priceLineVisible: false, autoscaleInfoProvider: () => buildVisiblePriceScale(chartApi, chartRows) });
      const ma10Series = chartApi.addSeries(LineSeries, { color: "#64a6ff", lineWidth: 2, lastValueVisible: false, priceLineVisible: false, autoscaleInfoProvider: () => buildVisiblePriceScale(chartApi, chartRows) });
      const ma20Series = chartApi.addSeries(LineSeries, { color: "#c084fc", lineWidth: 2, lastValueVisible: false, priceLineVisible: false, autoscaleInfoProvider: () => buildVisiblePriceScale(chartApi, chartRows) });
      const maSeries = [ma5Series, ma10Series, ma20Series];
      [5, 10, 20].forEach((period, index) => maSeries[index].applyOptions({ visible: visibleMA[period] }));

      let nextPane = 1;
      if (showMargin || showShort) {
        chartApi.addPane();
        if (showMargin) {
          const marginSeries = chartApi.addSeries(LineSeries, { color: "#f2c36b", lineWidth: 2, priceScaleId: showShort ? "left" : "right", title: "融資（張）", lastValueVisible: true, priceLineVisible: false }, nextPane);
          marginSeries.setData(alignedMargin.filter(row => row.margin != null).map(row => ({ time: row.time as Time, value: row.margin! })));
        }
        if (showShort) {
          const shortSeries = chartApi.addSeries(LineSeries, { color: "#64a6ff", lineWidth: 2, priceScaleId: "right", title: "融券（張）", lastValueVisible: true, priceLineVisible: false }, nextPane);
          shortSeries.setData(alignedMargin.filter(row => row.short != null).map(row => ({ time: row.time as Time, value: row.short! })));
        }
        if (showMargin && showShort) {
          chartApi.priceScale("left", nextPane).applyOptions({ borderColor: "#f2c36b", scaleMargins: { top: 0.2, bottom: 0.15 } });
        }
        chartApi.priceScale("right", nextPane).applyOptions({ borderColor: showShort ? "#64a6ff" : "#f2c36b", scaleMargins: { top: 0.2, bottom: 0.15 } });
        nextPane += 1;
      }
      if (showMacd) {
        chartApi.addPane();
        const difSeries = chartApi.addSeries(LineSeries, { color: "#f2c36b", lineWidth: 2, title: "DIF", lastValueVisible: true, priceLineVisible: false });
        const signalSeries = chartApi.addSeries(LineSeries, { color: "#c084fc", lineWidth: 2, title: "Signal", lastValueVisible: true, priceLineVisible: false });
        const histSeries = chartApi.addSeries(HistogramSeries, { title: "MACD 柱", lastValueVisible: false, priceLineVisible: false });
        difSeries.moveToPane(nextPane);
        signalSeries.moveToPane(nextPane);
        histSeries.moveToPane(nextPane);
        const macd = buildMacd(chartRows);
        difSeries.setData(macd.map(row => ({ time: row.time as Time, value: row.dif })));
        signalSeries.setData(macd.map(row => ({ time: row.time as Time, value: row.signal })));
        histSeries.setData(macd.map(row => ({ time: row.time as Time, value: row.hist, color: row.hist > 0 ? "rgba(255,95,109,.58)" : row.hist < 0 ? "rgba(61,214,181,.58)" : "rgba(174,184,190,.45)" })));
        chartApi.priceScale("right", nextPane).applyOptions({ scaleMargins: { top: 0.15, bottom: 0.15 } });
      }
      chartApi.panes()[0]?.setStretchFactor(2.4);

      chartApi.priceScale("volume").applyOptions({
        scaleMargins: {
          top: 0.78,
          bottom: 0
        }
      });
      chartApi.priceScale("right").applyOptions({
        scaleMargins: {
          top: 0.08,
          bottom: 0.28
        }
      });

      chartRef.current = chartApi;
      candleSeriesRef.current = candleSeries;
      setSeriesData(chartRows, candleSeries, volumeSeries, ma5Series, ma10Series, ma20Series);
      fitDataRange(chartApi, chartRows.length, interval);

      handleCrosshairMove = (param) => {
        if (disposed) return;
        const candle = param.seriesData.get(candleSeries) as OhlcDisplay | undefined;
        const volume = param.seriesData.get(volumeSeries) as { value?: number } | undefined;
        if (!candle) {
          setHovered(null);
          hoverCloseLine = removeHoverCloseLine(candleSeries, hoverCloseLine);
          return;
        }
        const nextHovered = { ...candle, volume: Number(volume?.value ?? 0) };
        setHovered(nextHovered);
        hoverCloseLine = setHoverCloseLine(candleSeries, hoverCloseLine, nextHovered.close);
      };
      chartApi.subscribeCrosshairMove(handleCrosshairMove);

      if (typeof ResizeObserver !== "undefined") {
        resizeObserver = new ResizeObserver(([entry]) => {
          if (disposed || !chart) return;
          const width = Math.max(Math.floor(entry.contentRect.width), 1);
          chart.applyOptions({ width, height });
        });
        resizeObserver.observe(container);
      }
    } catch (error) {
      disposed = true;
      setChartError(error instanceof Error ? error.message : "圖表初始化失敗");
      safelyDisposeChart(chart, handleCrosshairMove);
      chartRef.current = null;
      candleSeriesRef.current = null;
    }

    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      safelyDisposeChart(chart, handleCrosshairMove);
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
  }, [chartRows, alignedMargin, height, showMargin, showShort, showMacd, visibleMA]);

  return (
    <div className="tv-chart-shell">
      <div className="tv-chart-toolbar">
        <div>
          <strong>{latest ? `開 ${formatPrice(latest.open)} 高 ${formatPrice(latest.high)} 低 ${formatPrice(latest.low)} 收 ${formatPrice(latest.close)}` : "開高低收 -"}</strong>
          <span>{latest ? <>{latest.time}｜<b className={changePct == null || changePct === 0 ? "" : changePct > 0 ? "positive" : "negative"}>{!hovered && !latestQuoteIsCurrent ? `最後成交${interval === "daily" ? "日" : interval === "weekly" ? "週" : "月"}漲跌` : `${intervalLabels[interval]}漲跌`} {changePct == null ? "—" : `${changePct > 0 ? "+" : ""}${changePct.toFixed(2)}%`}</b>｜Vol {formatVolume(latest.volume)}</> : "等待真實股價資料"}</span>
          {(showMargin || showShort) && <span>{hoveredMargin ? `官方 ${hoveredMargin.reportDate}｜${showMargin ? `融資 ${hoveredMargin.margin?.toLocaleString() ?? "—"} 張` : ""}${showMargin && showShort ? " · " : ""}${showShort ? `融券 ${hoveredMargin.short?.toLocaleString() ?? "—"} 張` : ""}` : "所選日期沒有同期間融資融券日報"}</span>}
        </div>
        <div className="ma-legend" aria-label="Moving averages">
          <span>{intervalLabels[interval]}</span>
          {visibleMA[5] && <span className="ma5">MA5</span>}
          {visibleMA[10] && <span className="ma10">MA10</span>}
          {visibleMA[20] && <span className="ma20">MA20</span>}
        </div>
      </div>
      <div className="chart-interval-controls" aria-label="Chart interval">
        {(Object.keys(intervalLabels) as ChartInterval[]).map((item) => (
          <button
            className={interval === item ? "active" : ""}
            type="button"
            key={item}
            onClick={() => {
              setHovered(null);
              setInterval(item);
            }}
          >
            {intervalLabels[item]}
          </button>
        ))}
      </div>
      <div className="chart-overlay-controls" aria-label="圖表線條切換">
        {[5, 10, 20].map(period => <label key={period}><input type="checkbox" checked={visibleMA[period]} onChange={event => setVisibleMA(current => ({ ...current, [period]: event.target.checked }))} /> MA{period}</label>)}
        <label><input type="checkbox" checked={showMargin} onChange={event => setShowMargin(event.target.checked)} disabled={!margin.length} /> 融資張數</label>
        <label><input type="checkbox" checked={showShort} onChange={event => setShowShort(event.target.checked)} disabled={!margin.length} /> 融券張數</label>
        <label><input type="checkbox" checked={showMacd} onChange={event => setShowMacd(event.target.checked)} /> MACD</label>
      </div>
      {(showMargin || showShort) && <p className="chart-unit-note">融資、融券與股價共用日期軸；{showMargin && showShort ? "融資在左軸（張），融券在右軸（張）" : `${showMargin ? "融資" : "融券"}在右軸（張）`}，位於 K 線下方的獨立圖層。缺報日期不補零。</p>}
      {showMacd && <p className="chart-unit-note">下方 MACD：DIF＝EMA12－EMA26，訊號線＝DIF 的 EMA9，柱狀＝DIF－訊號線；依目前日／週／月 K 收盤價計算。</p>}
      <div className="tv-chart" ref={containerRef} style={{ height }}>
        {chartError ? <div className="chart-fallback">圖表暫時無法載入：{chartError}</div> : null}
      </div>
      {!rows.length && <p className="chart-unit-note">尚無真實股價資料；請先更新此股票行情。</p>}
    </div>
  );
}

function setSeriesData(
  rows: ChartRow[],
  candleSeries: ISeriesApi<"Candlestick">,
  volumeSeries: ISeriesApi<"Histogram">,
  ma5Series: ISeriesApi<"Line">,
  ma10Series: ISeriesApi<"Line">,
  ma20Series: ISeriesApi<"Line">
) {
  candleSeries.setData(rows.map((row) => ({
    time: row.time as Time,
    open: row.open,
    high: row.high,
    low: row.low,
    close: row.close,
    ...(row.close === row.open ? { color: "#aeb8be", borderColor: "#aeb8be", wickColor: "#aeb8be" } : {})
  })));
  volumeSeries.setData(rows.map((row) => ({
    time: row.time as Time,
    value: row.volume,
    color: row.close > row.open ? "rgba(255, 95, 109, 0.62)" : row.close < row.open ? "rgba(61, 214, 181, 0.62)" : "rgba(174,184,190,.45)"
  })));
  ma5Series.setData(buildMovingAverage(rows, 5));
  ma10Series.setData(buildMovingAverage(rows, 10));
  ma20Series.setData(buildMovingAverage(rows, 20));
}

function safelyDisposeChart(chart: IChartApi | null, handleCrosshairMove: ((param: MouseEventParams<Time>) => void) | null) {
  if (!chart) return;
  try {
    if (handleCrosshairMove) {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
    }
  } catch {
    // Lightweight Charts can report disposed internals during React StrictMode cleanup.
  }
  try {
    chart.remove();
  } catch {
    // Ignore double-dispose cleanup so the rest of the page stays mounted.
  }
}

function setHoverCloseLine(series: ISeriesApi<"Candlestick">, currentLine: IPriceLine | null, close: number) {
  if (currentLine) {
    currentLine.applyOptions({ price: close, title: formatPrice(close) });
    return currentLine;
  }
  return series.createPriceLine({
    price: close,
    color: "rgba(236, 241, 244, 0.76)",
    lineWidth: 1,
    lineStyle: LineStyle.Dashed,
    axisLabelVisible: true,
    title: formatPrice(close)
  });
}

function removeHoverCloseLine(series: ISeriesApi<"Candlestick">, currentLine: IPriceLine | null) {
  if (!currentLine) return null;
  try {
    series.removePriceLine(currentLine);
  } catch {
    // Ignore stale hover line cleanup during chart teardown.
  }
  return null;
}

function fitDataRange(chart: IChartApi, rowCount: number, interval: ChartInterval) {
  if (rowCount < 2) return;
  if (interval === "daily") {
    const visibleRows = Math.min(rowCount, 84);
    chart.timeScale().setVisibleLogicalRange({
      from: rowCount - visibleRows,
      to: rowCount - 1
    });
    return;
  }
  chart.timeScale().setVisibleLogicalRange({
    from: 0,
    to: rowCount - 1
  });
}

function buildVisiblePriceScale(chart: IChartApi, rows: ChartRow[]): AutoscaleInfo | null {
  const range = chart.timeScale().getVisibleLogicalRange();
  if (!range || rows.length === 0) return null;

  const from = Math.max(0, Math.floor(Number(range.from)));
  const to = Math.min(rows.length - 1, Math.ceil(Number(range.to)));
  if (from > to) return null;

  const ma5 = buildMovingAverage(rows, 5);
  const ma10 = buildMovingAverage(rows, 10);
  const ma20 = buildMovingAverage(rows, 20);
  const values: number[] = [];

  rows.slice(from, to + 1).forEach((row) => {
    values.push(row.high, row.low);
  });
  [ma5, ma10, ma20].forEach((line) => {
    line.slice(from, to + 1).forEach((point) => values.push(point.value));
  });

  const finiteValues = values.filter(Number.isFinite);
  if (!finiteValues.length) return null;
  const min = Math.min(...finiteValues);
  const max = Math.max(...finiteValues);
  const padding = Math.max((max - min) * 0.08, max * 0.01, 1);
  return {
    priceRange: {
      minValue: min - padding,
      maxValue: max + padding
    }
  };
}

function normalizeQuotes(quotes: PriceQuote[]): ChartRow[] {
  return quotes
    .filter((quote) => quote.open !== null && quote.high !== null && quote.low !== null && quote.close !== null)
    .map((quote) => ({
      time: quote.trade_date,
      open: Number(quote.open),
      high: Number(quote.high),
      low: Number(quote.low),
      close: Number(quote.close),
      volume: Number(quote.volume ?? 0)
    }));
}

function aggregateRows(rows: ChartRow[], interval: ChartInterval) {
  if (interval === "daily") return rows;
  const grouped = new Map<string, ChartRow[]>();
  rows.forEach((row) => {
    const key = interval === "weekly" ? getWeekKey(row.time) : row.time.slice(0, 7);
    grouped.set(key, [...(grouped.get(key) ?? []), row]);
  });

  return [...grouped.values()].map((groupRows) => {
    const first = groupRows[0];
    const last = groupRows[groupRows.length - 1];
    return {
      time: last.time,
      open: first.open,
      high: Math.max(...groupRows.map((row) => row.high)),
      low: Math.min(...groupRows.map((row) => row.low)),
      close: last.close,
      volume: groupRows.reduce((sum, row) => sum + row.volume, 0)
    };
  });
}

function getWeekKey(dateText: string) {
  const date = new Date(`${dateText}T00:00:00`);
  const day = date.getDay() || 7;
  date.setDate(date.getDate() - day + 1);
  return date.toISOString().slice(0, 10);
}

function buildMovingAverage(rows: ChartRow[], windowSize: number) {
  return rows
    .map((row, index) => {
      if (index + 1 < windowSize) return null;
      const windowRows = rows.slice(index + 1 - windowSize, index + 1);
      const value = windowRows.reduce((sum, item) => sum + item.close, 0) / windowSize;
      return { time: row.time as Time, value };
    })
    .filter((item): item is { time: Time; value: number } => item !== null);
}

function alignMarginRows(rows: ChartRow[], reports: MarginRow[], interval: ChartInterval) {
  const byPeriod = new Map<string, MarginRow[]>();
  for (const report of reports) {
    const key = interval === "daily" ? report.trade_date : interval === "weekly" ? getWeekKey(report.trade_date) : report.trade_date.slice(0, 7);
    byPeriod.set(key, [...(byPeriod.get(key) || []), report]);
  }
  return rows.flatMap(row => {
    const key = interval === "daily" ? row.time : interval === "weekly" ? getWeekKey(row.time) : row.time.slice(0, 7);
    const report = (byPeriod.get(key) || []).filter(item => item.trade_date <= row.time).sort((a, b) => b.trade_date.localeCompare(a.trade_date))[0];
    return report ? [{ time: row.time, reportDate: report.trade_date, margin: report.margin_balance_lots, short: report.short_balance_lots }] : [];
  });
}

function buildMacd(rows: ChartRow[]) {
  let ema12: number | null = null;
  let ema26: number | null = null;
  let signal: number | null = null;
  return rows.map(row => {
    ema12 = ema12 == null ? row.close : ema12 + (2 / 13) * (row.close - ema12);
    ema26 = ema26 == null ? row.close : ema26 + (2 / 27) * (row.close - ema26);
    const dif = ema12 - ema26;
    signal = signal == null ? dif : signal + (2 / 10) * (dif - signal);
    return { time: row.time, dif, signal, hist: dif - signal };
  });
}

function formatPrice(value: number) {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(value: number) {
  return `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })} 張`;
}
