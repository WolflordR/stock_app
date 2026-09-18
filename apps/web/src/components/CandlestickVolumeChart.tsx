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

const intervalLabels: Record<ChartInterval, string> = {
  daily: "日K",
  weekly: "週K",
  monthly: "月K"
};

const sampleHistory: ChartRow[] = [
  { time: "2026-08-24", open: 2410, high: 2410, low: 2375, close: 2375, volume: 10658045 },
  { time: "2026-08-25", open: 2355, high: 2400, low: 2350, close: 2400, volume: 12843032 },
  { time: "2026-08-26", open: 2375, high: 2425, low: 2375, close: 2415, volume: 17662672 },
  { time: "2026-08-27", open: 2430, high: 2435, low: 2410, close: 2410, volume: 16247745 },
  { time: "2026-08-28", open: 2440, high: 2445, low: 2410, close: 2420, volume: 13601211 },
  { time: "2026-08-31", open: 2395, high: 2405, low: 2375, close: 2405, volume: 27171787 },
  { time: "2026-09-01", open: 2395, high: 2440, low: 2390, close: 2440, volume: 17216484 },
  { time: "2026-09-02", open: 2415, high: 2420, low: 2385, close: 2385, volume: 19825721 },
  { time: "2026-09-03", open: 2385, high: 2400, low: 2380, close: 2390, volume: 12602565 }
];

export function CandlestickVolumeChart({ quotes }: { quotes: PriceQuote[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const [hovered, setHovered] = useState<OhlcDisplay | null>(null);
  const [chartError, setChartError] = useState("");
  const [interval, setInterval] = useState<ChartInterval>("daily");

  const rows = useMemo(() => normalizeQuotes(quotes), [quotes]);
  const baseRows = useMemo(() => (rows.length ? rows : sampleHistory), [rows]);
  const chartRows = useMemo(() => aggregateRows(baseRows, interval), [baseRows, interval]);
  const latest = hovered ?? chartRows[chartRows.length - 1] ?? null;
  const usingSample = rows.length === 0;

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
        width: Math.max(container.clientWidth, 320),
        height: 430,
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
        timeScale: {
          borderColor: "rgba(174, 184, 190, 0.22)",
          fixLeftEdge: true,
          fixRightEdge: true,
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
          const width = Math.max(Math.floor(entry.contentRect.width), 320);
          chart.applyOptions({ width, height: 430 });
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
  }, [chartRows]);

  return (
    <div className="tv-chart-shell">
      <div className="tv-chart-toolbar">
        <div>
          <strong>{latest ? `開 ${formatPrice(latest.open)} 高 ${formatPrice(latest.high)} 低 ${formatPrice(latest.low)} 收 ${formatPrice(latest.close)}` : "開高低收 -"}</strong>
          <span>{latest ? `${latest.time}｜Vol ${formatVolume(latest.volume)}` : "等待資料"}</span>
        </div>
        <div className="ma-legend" aria-label="Moving averages">
          <span>{intervalLabels[interval]}</span>
          <span className="ma5">MA5</span>
          <span className="ma10">MA10</span>
          <span className="ma20">MA20</span>
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
      <div className="tv-chart" ref={containerRef}>
        {chartError ? <div className="chart-fallback">圖表暫時無法載入：{chartError}</div> : null}
      </div>
      {usingSample ? (
        <details className="sample-json">
          <summary>模擬歷史股價 JSON</summary>
          <pre>{JSON.stringify(sampleHistory, null, 2)}</pre>
        </details>
      ) : null}
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
    close: row.close
  })));
  volumeSeries.setData(rows.map((row) => ({
    time: row.time as Time,
    value: row.volume,
    color: row.close >= row.open ? "rgba(255, 95, 109, 0.62)" : "rgba(61, 214, 181, 0.62)"
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
  if (rowCount <= 0) return;
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
    to: Math.max(rowCount - 1, 0)
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

function formatPrice(value: number) {
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatVolume(value: number) {
  return `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 0 })} 張`;
}
