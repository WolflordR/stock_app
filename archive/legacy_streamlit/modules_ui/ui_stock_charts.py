from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf

from modules.data_sources.market_watch import (
    fetch_tpex_daily_quotes,
    fetch_twse_daily_quotes,
    fetch_twse_day_trading_series,
)
from modules.data_sources.price_cache import fetch_price_history


UP_COLOR = "#DF6F7B"
DOWN_COLOR = "#63C796"
GRID_COLOR = "rgba(143, 163, 184, 0.09)"
BG_COLOR = "#0B1118"
PANEL_COLOR = "#101A26"
TEXT_COLOR = "#DBE7F3"
MUTED_TEXT_COLOR = "#8FA3B8"
MA_COLORS = {
    "MA5": "#7DD3FC",
    "MA10": "#5EA6C8",
    "MA20": "#D3A64F",
    "MA60": "#91A8BA",
    "MA120": "#7F9187",
}
VOLUME_MA_COLORS = {
    "MV5": "#7DD3FC",
    "MV20": "#D3A64F",
}
DAY_TRADE_COLOR = "#D3A64F"
INTERVAL_OPTIONS = {
    "1m": {"yf_interval": "1m", "max_days": 7, "label": "1 分"},
    "5m": {"yf_interval": "5m", "max_days": 60, "label": "5 分"},
    "1h": {"yf_interval": "60m", "max_days": 730, "label": "1 小時"},
    "1d": {"yf_interval": "1d", "max_days": None, "label": "日 K"},
}


def _normalize_date(value) -> str:
    if isinstance(value, (datetime, date)):
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    return pd.to_datetime(value).strftime("%Y-%m-%d")


@st.cache_data(show_spinner=False, ttl=1800)
def load_stock_chart_history(symbol: str, start_date, end_date, interval: str = "1d") -> pd.DataFrame:
    interval = interval if interval in INTERVAL_OPTIONS else "1d"
    if interval == "1d":
        history_df = fetch_price_history(
            symbol,
            mode="歷史回測",
            start_date=start_date,
            end_date=end_date,
            history_buffer_days=260,
            include_indicators=False,
        )
    else:
        history_df = _fetch_intraday_history(symbol, start_date, end_date, interval)
    if history_df.empty:
        return history_df

    chart_df = history_df.reset_index().copy()
    date_column = next(
        (
            column
            for column in chart_df.columns
            if str(column).lower() in {"date", "datetime", "index"}
        ),
        chart_df.columns[0],
    )
    chart_df = chart_df.rename(columns={date_column: "Date"})
    chart_df["Date"] = pd.to_datetime(chart_df["Date"])
    if getattr(chart_df["Date"].dt, "tz", None) is not None:
        chart_df["Date"] = chart_df["Date"].dt.tz_convert("Asia/Taipei").dt.tz_localize(None)
    chart_df = chart_df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    chart_df["Volume"] = pd.to_numeric(chart_df["Volume"], errors="coerce").fillna(0.0)
    for window in (5, 10, 20, 60, 120):
        chart_df[f"MA{window}"] = chart_df["Close"].rolling(window).mean()
    chart_df["MV5"] = chart_df["Volume"].rolling(5).mean() / 1000.0
    chart_df["MV20"] = chart_df["Volume"].rolling(20).mean() / 1000.0
    return chart_df


def _fetch_intraday_history(symbol: str, start_date, end_date, interval: str) -> pd.DataFrame:
    config = INTERVAL_OPTIONS.get(interval, INTERVAL_OPTIONS["1d"])
    end_ts = pd.to_datetime(end_date).normalize() + timedelta(days=1)
    requested_start = pd.to_datetime(start_date)
    max_days = config.get("max_days")
    start_ts = max(requested_start, end_ts - timedelta(days=int(max_days))) if max_days else requested_start

    ticker = yf.Ticker(symbol)
    history_df = ticker.history(
        start=start_ts,
        end=end_ts,
        interval=config["yf_interval"],
        auto_adjust=False,
        prepost=False,
    )
    if history_df.empty:
        return pd.DataFrame()
    if isinstance(history_df.columns, pd.MultiIndex):
        history_df.columns = history_df.columns.get_level_values(0)
    return history_df.rename(
        columns={
            "Open": "Open",
            "High": "High",
            "Low": "Low",
            "Close": "Close",
            "Volume": "Volume",
        }
    )[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Open", "High", "Low", "Close"])


@st.cache_data(show_spinner=False, ttl=1800)
def load_twse_day_trade_history(stock_code: str) -> pd.DataFrame:
    return fetch_twse_day_trading_series(stock_code)


@st.cache_data(show_spinner=False, ttl=1800)
def load_latest_official_quote(stock_code: str, market_label: str | None, probe_date) -> dict | None:
    normalized_market = str(market_label or "").strip().upper()
    probe_date_text = pd.to_datetime(probe_date).strftime("%Y-%m-%d")
    if normalized_market in {"TWSE", "上市"}:
        quote_df = fetch_twse_daily_quotes(probe_date_text)
    elif normalized_market in {"TPEX", "上櫃"}:
        quote_df = fetch_tpex_daily_quotes(probe_date_text)
    else:
        quote_df = pd.concat(
            [fetch_twse_daily_quotes(probe_date_text), fetch_tpex_daily_quotes(probe_date_text)],
            ignore_index=True,
        )
    if quote_df.empty or "code" not in quote_df.columns:
        return None
    matched = quote_df[quote_df["code"].astype(str) == str(stock_code).strip()]
    if matched.empty:
        return None
    row = matched.iloc[0].to_dict()
    row["trade_date"] = probe_date_text
    return row


def _merge_latest_quote_into_chart(chart_df: pd.DataFrame, latest_quote: dict | None) -> pd.DataFrame:
    if chart_df.empty or not latest_quote:
        return chart_df

    trade_date = latest_quote.get("trade_date")
    close_value = latest_quote.get("close")
    open_value = latest_quote.get("open")
    high_value = latest_quote.get("high")
    low_value = latest_quote.get("low")
    volume_value = latest_quote.get("volume")
    if not trade_date or close_value is None or open_value is None or high_value is None or low_value is None:
        return chart_df

    trade_ts = pd.to_datetime(trade_date)
    working_df = chart_df.copy()
    last_ts = pd.to_datetime(working_df["Date"]).max()

    if trade_ts <= last_ts:
        same_day_mask = pd.to_datetime(working_df["Date"]) == trade_ts
        if same_day_mask.any():
            working_df.loc[same_day_mask, ["Open", "High", "Low", "Close", "Volume"]] = [
                float(open_value),
                float(high_value),
                float(low_value),
                float(close_value),
                float(volume_value or 0.0),
            ]
        else:
            return working_df
    else:
        appended_row = {
            "Date": trade_ts,
            "Open": float(open_value),
            "High": float(high_value),
            "Low": float(low_value),
            "Close": float(close_value),
            "Volume": float(volume_value or 0.0),
        }
        working_df = pd.concat([working_df, pd.DataFrame([appended_row])], ignore_index=True)

    working_df = working_df.sort_values("Date").reset_index(drop=True)
    for window in (5, 10, 20, 60, 120):
        working_df[f"MA{window}"] = working_df["Close"].rolling(window).mean()
    working_df["MV5"] = working_df["Volume"].rolling(5).mean() / 1000.0
    working_df["MV20"] = working_df["Volume"].rolling(20).mean() / 1000.0
    return working_df


def _build_chart_payload(chart_df: pd.DataFrame, day_trade_df: pd.DataFrame | None = None, interval: str = "1d") -> dict:
    candles: list[dict] = []
    volumes: list[dict] = []
    day_trade_series: list[dict] = []
    ma_series: dict[str, list[dict]] = {name: [] for name in MA_COLORS}
    volume_ma_series: dict[str, list[dict]] = {name: [] for name in VOLUME_MA_COLORS}
    legend_rows: list[dict] = []
    day_trade_map: dict[str, dict] = {}
    latest_day_trade: dict | None = None

    if day_trade_df is not None and not day_trade_df.empty:
        source_df = day_trade_df.copy()
        source_df["date"] = pd.to_datetime(source_df["date"]).dt.strftime("%Y-%m-%d")
        for _, row in source_df.iterrows():
            normalized_row = {
                "day_trade_volume": float(row["day_trade_volume"]) / 1000.0 if pd.notna(row.get("day_trade_volume")) else None,
                "day_trade_ratio": float(row["day_trade_ratio"]) if pd.notna(row.get("day_trade_ratio")) else None,
                "avg_day_trade_volume": float(row["avg_day_trade_volume"]) / 1000.0 if pd.notna(row.get("avg_day_trade_volume")) else None,
                "date": row["date"],
            }
            day_trade_map[row["date"]] = normalized_row
            latest_day_trade = normalized_row

    previous_close: float | None = None
    previous_volume_lots: float | None = None

    for _, row in chart_df.iterrows():
        row_ts = pd.to_datetime(row["Date"])
        date_text = row_ts.strftime("%Y-%m-%d")
        display_time = row_ts.strftime("%Y-%m-%d") if interval == "1d" else row_ts.strftime("%Y-%m-%d %H:%M")
        chart_time = date_text if interval == "1d" else int(row_ts.timestamp())
        time_key = str(chart_time)
        open_price = float(row["Open"])
        high_price = float(row["High"])
        low_price = float(row["Low"])
        close_price = float(row["Close"])
        volume_lots = float(row["Volume"]) / 1000.0
        is_up = close_price >= open_price

        candles.append(
            {
                "time": chart_time,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
            }
        )
        volumes.append(
            {
                "time": chart_time,
                "value": volume_lots,
                "color": UP_COLOR if is_up else DOWN_COLOR,
            }
        )
        day_trade_row = day_trade_map.get(date_text) or {}
        if day_trade_row.get("day_trade_ratio") is not None:
            day_trade_series.append(
                {
                    "time": chart_time,
                    "value": float(day_trade_row["day_trade_ratio"]),
                    "color": DAY_TRADE_COLOR,
                }
            )

        for ma_name in MA_COLORS:
            ma_value = row.get(ma_name)
            if pd.notna(ma_value):
                ma_series[ma_name].append({"time": chart_time, "value": float(ma_value)})

        for mv_name in volume_ma_series:
            mv_value = row.get(mv_name)
            if pd.notna(mv_value):
                volume_ma_series[mv_name].append({"time": chart_time, "value": float(mv_value)})

        legend_rows.append(
            {
                "time": time_key,
                "display_time": display_time,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
                "prev_close": previous_close,
                "volume_lots": volume_lots,
                "ma5": float(row["MA5"]) if pd.notna(row.get("MA5")) else None,
                "ma10": float(row["MA10"]) if pd.notna(row.get("MA10")) else None,
                "ma20": float(row["MA20"]) if pd.notna(row.get("MA20")) else None,
                "ma60": float(row["MA60"]) if pd.notna(row.get("MA60")) else None,
                "ma120": float(row["MA120"]) if pd.notna(row.get("MA120")) else None,
                "mv5": float(row["MV5"]) if pd.notna(row.get("MV5")) else None,
                "mv20": float(row["MV20"]) if pd.notna(row.get("MV20")) else None,
                "day_trade_volume": day_trade_row.get("day_trade_volume"),
                "day_trade_ratio": day_trade_row.get("day_trade_ratio"),
                "avg_day_trade_volume": day_trade_row.get("avg_day_trade_volume"),
                "volume_ratio_prev_day": (volume_lots / previous_volume_lots) if previous_volume_lots and previous_volume_lots > 0 else None,
            }
        )
        previous_close = close_price
        previous_volume_lots = volume_lots

    return {
        "candles": candles,
        "volumes": volumes,
        "day_trade_series": day_trade_series,
        "ma_series": ma_series,
        "volume_ma_series": volume_ma_series,
        "legend_rows": legend_rows,
        "latest_day_trade": latest_day_trade,
    }


def render_streamlit_lightweight_chart(
    symbol: str,
    title: str,
    *,
    start_date,
    end_date,
    key_prefix: str,
    stock_code: str | None = None,
    market_label: str | None = None,
    visible_price_indicators: list[str] | None = None,
    visible_volume_indicators: list[str] | None = None,
    interval: str = "1d",
):
    interval = interval if interval in INTERVAL_OPTIONS else "1d"
    try:
        chart_df = load_stock_chart_history(symbol, start_date, end_date, interval=interval)
    except Exception as exc:  # noqa: BLE001
        st.error(f"讀取 {title} 的 K 線資料失敗：{exc}")
        return

    if chart_df.empty:
        st.warning("目前抓不到這檔股票的歷史價格資料。")
        return

    normalized_market = str(market_label or "").strip().upper()
    effective_code = str(stock_code or symbol.split(".")[0]).strip()
    day_trade_df = pd.DataFrame()
    if interval == "1d" and effective_code.isdigit() and normalized_market in {"TWSE", "上市"}:
        try:
            day_trade_df = load_twse_day_trade_history(effective_code)
        except Exception:
            day_trade_df = pd.DataFrame()

    latest_quote = None
    if interval == "1d" and effective_code.isdigit():
        try:
            latest_quote = load_latest_official_quote(effective_code, market_label, end_date)
        except Exception:
            latest_quote = None

    if interval == "1d":
        chart_df = _merge_latest_quote_into_chart(chart_df, latest_quote)

    payload = _build_chart_payload(chart_df, day_trade_df=day_trade_df, interval=interval)
    component_id = f"{key_prefix}_{symbol}_{interval}_{_normalize_date(start_date)}_{_normalize_date(end_date)}".replace(".", "_")
    payload_json = json.dumps(payload, ensure_ascii=False)
    visible_price_indicators = [
        indicator for indicator in (visible_price_indicators or list(MA_COLORS)) if indicator in MA_COLORS
    ]
    visible_volume_indicators = [
        indicator
        for indicator in (visible_volume_indicators or list(VOLUME_MA_COLORS))
        if indicator in VOLUME_MA_COLORS
    ]
    visible_price_json = json.dumps(visible_price_indicators, ensure_ascii=False)
    visible_volume_json = json.dumps(visible_volume_indicators, ensure_ascii=False)
    price_color_json = json.dumps(MA_COLORS, ensure_ascii=False)
    volume_color_json = json.dumps(VOLUME_MA_COLORS, ensure_ascii=False)
    interval_label = INTERVAL_OPTIONS[interval]["label"]

    html = f"""
    <div id="{component_id}-wrapper" style="position:relative;background:linear-gradient(180deg,{PANEL_COLOR},#0d1722);border:1px solid rgba(137,157,179,0.18);border-radius:8px;padding:12px 12px 10px 12px;box-shadow:0 22px 54px rgba(0,0,0,0.30);">
      <div id="{component_id}-legend" style="display:flex;flex-direction:column;gap:8px;margin-bottom:12px;color:{TEXT_COLOR};font-family:ui-sans-serif,system-ui,sans-serif;">
        <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;">
          <div style="font-size:18px;font-weight:700;">{title}</div>
          <div style="font-size:12px;color:{MUTED_TEXT_COLOR};border:1px solid rgba(137,157,179,0.22);border-radius:999px;padding:3px 9px;background:rgba(79,183,216,0.08);">{interval_label}</div>
          <div id="{component_id}-date" style="color:{MUTED_TEXT_COLOR};font-size:14px;"></div>
          <button id="{component_id}-reset" type="button" style="margin-left:auto;background:#172333;border:1px solid rgba(137,157,179,0.28);color:{TEXT_COLOR};border-radius:8px;padding:6px 10px;font-size:12px;cursor:pointer;">Reset</button>
        </div>
        <div id="{component_id}-ohlc" style="font-size:15px;font-weight:700;"></div>
        <div id="{component_id}-ma" style="font-size:14px;color:{MUTED_TEXT_COLOR};"></div>
        <div id="{component_id}-volume-meta" style="font-size:14px;color:{TEXT_COLOR};font-weight:600;"></div>
        <div id="{component_id}-daytrade-meta" style="font-size:14px;color:{TEXT_COLOR};font-weight:600;"></div>
      </div>
      <div id="{component_id}" style="position:relative;width:100%;height:720px;"></div>
      <div id="{component_id}-tooltip" style="display:none;position:absolute;z-index:20;pointer-events:none;min-width:178px;background:rgba(12,18,27,0.96);border:1px solid rgba(137,157,179,0.26);border-radius:8px;padding:9px 10px;color:{TEXT_COLOR};font-family:ui-sans-serif,system-ui,sans-serif;font-size:12px;line-height:1.55;box-shadow:0 14px 34px rgba(0,0,0,0.38);backdrop-filter:blur(8px);"></div>
      <div id="{component_id}-error" style="display:none;margin-top:10px;color:#F2A2A9;font-size:13px;font-family:ui-sans-serif,system-ui,sans-serif;"></div>
    </div>
    <script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
    <script>
      (() => {{
        const payload = {payload_json};
        const visiblePriceIndicators = {visible_price_json};
        const visibleVolumeIndicators = {visible_volume_json};
        const container = document.getElementById("{component_id}");
        const errorEl = document.getElementById("{component_id}-error");
        const dateEl = document.getElementById("{component_id}-date");
        const ohlcEl = document.getElementById("{component_id}-ohlc");
        const volumeMetaEl = document.getElementById("{component_id}-volume-meta");
        const daytradeMetaEl = document.getElementById("{component_id}-daytrade-meta");
        const maEl = document.getElementById("{component_id}-ma");
        const tooltipEl = document.getElementById("{component_id}-tooltip");
        const resetBtn = document.getElementById("{component_id}-reset");
        if (!container || !window.LightweightCharts) return;

        function showError(message) {{
          if (!errorEl) return;
          errorEl.style.display = 'block';
          errorEl.textContent = message;
        }}

        try {{
        const chart = LightweightCharts.createChart(container, {{
          width: container.clientWidth,
          height: 720,
          layout: {{
            background: {{ type: 'solid', color: '{BG_COLOR}' }},
            textColor: '{TEXT_COLOR}',
            fontSize: 13,
            fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
          }},
          grid: {{
            vertLines: {{ color: '{GRID_COLOR}' }},
            horzLines: {{ color: '{GRID_COLOR}' }},
          }},
          crosshair: {{
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: {{ labelBackgroundColor: '#172333', color: 'rgba(219,231,243,0.28)' }},
            horzLine: {{ labelBackgroundColor: '#172333', color: 'rgba(219,231,243,0.28)' }},
          }},
          rightPriceScale: {{
            borderColor: 'rgba(137, 157, 179, 0.20)',
            scaleMargins: {{ top: 0.06, bottom: 0.42 }},
          }},
          timeScale: {{
            borderColor: 'rgba(137, 157, 179, 0.20)',
            timeVisible: true,
            secondsVisible: false,
            rightOffset: 8,
            barSpacing: 8,
            minBarSpacing: 3,
            fixLeftEdge: false,
            fixRightEdge: false,
          }},
          handleScroll: {{ mouseWheel: true, pressedMouseMove: true }},
          handleScale: {{ axisPressedMouseMove: true, mouseWheel: true, pinch: true }},
          localization: {{
            locale: 'zh-TW',
            dateFormat: 'yyyy/MM/dd',
          }},
        }});

        const candleSeries = chart.addCandlestickSeries({{
          upColor: '{UP_COLOR}',
          downColor: '{DOWN_COLOR}',
          borderUpColor: '{UP_COLOR}',
          borderDownColor: '{DOWN_COLOR}',
          wickUpColor: '{UP_COLOR}',
          wickDownColor: '{DOWN_COLOR}',
          priceLineVisible: true,
          lastValueVisible: true,
        }});
        candleSeries.setData(payload.candles);
        const latestCandle = payload.candles[payload.candles.length - 1];
        if (latestCandle) {{
          candleSeries.createPriceLine({{
            price: latestCandle.close,
            color: latestCandle.close >= latestCandle.open ? '{UP_COLOR}' : '{DOWN_COLOR}',
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'Last',
          }});
        }}

        Object.entries({price_color_json}).forEach(([name, color]) => {{
          if (!visiblePriceIndicators.includes(name)) return;
          const series = chart.addLineSeries({{
            color,
            lineWidth: name === 'MA5' ? 2 : 1.5,
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          }});
          series.setData(payload.ma_series[name] || []);
        }});

        const volumeSeries = chart.addHistogramSeries({{
          priceFormat: {{ type: 'volume' }},
          priceScaleId: 'volume',
          lastValueVisible: true,
          priceLineVisible: false,
        }});
        chart.priceScale('volume').applyOptions({{
          scaleMargins: {{ top: 0.72, bottom: 0.16 }},
          borderVisible: false,
        }});
        const dayTradeSeries = chart.addHistogramSeries({{
          priceFormat: {{ type: 'volume' }},
          priceScaleId: 'daytrade',
          lastValueVisible: true,
          priceLineVisible: false,
        }});
        chart.priceScale('daytrade').applyOptions({{
          scaleMargins: {{ top: 0.88, bottom: 0.02 }},
          borderVisible: false,
        }});
        volumeSeries.setData(payload.volumes);
        dayTradeSeries.setData(payload.day_trade_series || []);

        Object.entries({volume_color_json}).forEach(([name, color]) => {{
          if (!visibleVolumeIndicators.includes(name)) return;
          const series = chart.addLineSeries({{
            color,
            lineWidth: 1.5,
            lineStyle: LightweightCharts.LineStyle.Solid,
            priceScaleId: 'volume',
            priceLineVisible: false,
            lastValueVisible: false,
            crosshairMarkerVisible: false,
          }});
          series.setData(payload.volume_ma_series[name] || []);
        }});

        chart.timeScale().fitContent();

        const byTime = new Map((payload.legend_rows || []).map(row => [String(row.time), row]));
        const latest = payload.legend_rows[payload.legend_rows.length - 1];

        function formatNum(value, digits = 2) {{
          if (value === null || value === undefined || Number.isNaN(value)) return '-';
          return Number(value).toLocaleString('zh-TW', {{
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
          }});
        }}

        function formatLots(value) {{
          if (value === null || value === undefined || Number.isNaN(value)) return '-';
          return `${{Number(value).toLocaleString('zh-TW', {{ maximumFractionDigits: 0 }})}} 張`;
        }}

        function renderLegend(row) {{
          if (!row) return;
          const prev = row.prev_close;
          const diff = prev !== null && prev !== undefined ? row.close - prev : null;
          const diffPct = diff !== null && prev ? (diff / prev) * 100 : null;
          const diffText = diff === null
            ? ''
            : ` ｜ 漲跌 ${{diff >= 0 ? '+' : ''}}${{formatNum(diff)}} (${{diffPct >= 0 ? '+' : ''}}${{formatNum(diffPct)}}%)`;
          dateEl.textContent = row.display_time || row.time;
          ohlcEl.textContent = `開 ${{formatNum(row.open)}} ｜ 高 ${{formatNum(row.high)}} ｜ 低 ${{formatNum(row.low)}} ｜ 收 ${{formatNum(row.close)}}${{diffText}}`;
          const metricParts = [];
          visiblePriceIndicators.forEach(name => {{
            const key = name.toLowerCase();
            metricParts.push(`${{name}} ${{formatNum(row[key])}}`);
          }});
          maEl.textContent = metricParts.join(' ｜ ');

          const volumeParts = [`成交量 ${{formatLots(row.volume_lots)}}`];
          if (row.volume_ratio_prev_day !== null && row.volume_ratio_prev_day !== undefined) {{
            volumeParts.push(`量增幅 ${{formatNum(row.volume_ratio_prev_day, 2)}}x`);
          }}
          visibleVolumeIndicators.forEach(name => {{
            const key = name.toLowerCase();
            volumeParts.push(`${{name}} ${{formatNum(row[key], 0)}}`);
          }});
          volumeMetaEl.textContent = volumeParts.join(' ｜ ');

          const dayTradeParts = [];
          if (row.day_trade_volume !== null && row.day_trade_volume !== undefined) {{
            dayTradeParts.push(`當沖量 ${{formatLots(row.day_trade_volume)}}`);
          }}
          if (row.day_trade_ratio !== null && row.day_trade_ratio !== undefined) {{
            dayTradeParts.push(`當沖比例 ${{formatNum(row.day_trade_ratio)}}%`);
          }}
          if (row.avg_day_trade_volume !== null && row.avg_day_trade_volume !== undefined) {{
            dayTradeParts.push(`近期待沖均量 ${{formatLots(row.avg_day_trade_volume)}}`);
          }}
          if (!dayTradeParts.length && payload.latest_day_trade) {{
            const latestDayTrade = payload.latest_day_trade;
            const fallbackParts = [`當沖資料最新 ${{latestDayTrade.date || '-'}}`];
            if (latestDayTrade.day_trade_volume !== null && latestDayTrade.day_trade_volume !== undefined) {{
              fallbackParts.push(`當沖量 ${{formatLots(latestDayTrade.day_trade_volume)}}`);
            }}
            if (latestDayTrade.day_trade_ratio !== null && latestDayTrade.day_trade_ratio !== undefined) {{
              fallbackParts.push(`當沖比例 ${{formatNum(latestDayTrade.day_trade_ratio)}}%`);
            }}
            if (latestDayTrade.avg_day_trade_volume !== null && latestDayTrade.avg_day_trade_volume !== undefined) {{
              fallbackParts.push(`近期待沖均量 ${{formatLots(latestDayTrade.avg_day_trade_volume)}}`);
            }}
            daytradeMetaEl.textContent = fallbackParts.join(' ｜ ');
          }} else {{
            daytradeMetaEl.textContent = dayTradeParts.length ? dayTradeParts.join(' ｜ ') : '當沖比例：日 K 上市股支援';
          }}
        }}

        function renderTooltip(row, point) {{
          if (!tooltipEl || !row || !point) return;
          tooltipEl.innerHTML = `
            <div style="font-weight:800;margin-bottom:5px;color:#eef5fb;">${{row.display_time || row.time}}</div>
            <div>Open <b>${{formatNum(row.open)}}</b></div>
            <div>High <b>${{formatNum(row.high)}}</b></div>
            <div>Low <b>${{formatNum(row.low)}}</b></div>
            <div>Close <b>${{formatNum(row.close)}}</b></div>
            <div>Volume <b>${{formatLots(row.volume_lots)}}</b></div>
          `;
          const wrapper = document.getElementById("{component_id}-wrapper");
          const chartRect = container.getBoundingClientRect();
          const wrapperRect = wrapper.getBoundingClientRect();
          const tooltipWidth = 190;
          const tooltipHeight = 150;
          let left = chartRect.left - wrapperRect.left + point.x + 18;
          let top = chartRect.top - wrapperRect.top + point.y + 18;
          if (left + tooltipWidth > wrapperRect.width - 8) left = chartRect.left - wrapperRect.left + point.x - tooltipWidth - 18;
          if (top + tooltipHeight > wrapperRect.height - 8) top = chartRect.top - wrapperRect.top + point.y - tooltipHeight - 18;
          tooltipEl.style.left = `${{Math.max(8, left)}}px`;
          tooltipEl.style.top = `${{Math.max(8, top)}}px`;
          tooltipEl.style.display = 'block';
        }}

        function hideTooltip() {{
          if (tooltipEl) tooltipEl.style.display = 'none';
        }}

        function normalizeTime(time) {{
          if (typeof time === 'number') return String(time);
          if (typeof time === 'string') return time;
          if (time && time.year) {{
            return `${{time.year}}-${{String(time.month).padStart(2,'0')}}-${{String(time.day).padStart(2,'0')}}`;
          }}
          return null;
        }}

        renderLegend(latest);

        chart.subscribeCrosshairMove(param => {{
          if (!param || !param.time || !param.point || param.point.x < 0 || param.point.y < 0) {{
            renderLegend(latest);
            hideTooltip();
            return;
          }}
          const time = normalizeTime(param.time);
          const row = byTime.get(time) || latest;
          renderLegend(row);
          renderTooltip(row, param.point);
        }});

        const ro = new ResizeObserver(() => {{
          const height = Math.max(520, Math.min(760, Math.round(window.innerHeight * 0.68)));
          container.style.height = `${{height}}px`;
          chart.applyOptions({{ width: container.clientWidth, height }});
        }});
        ro.observe(container);
        resetBtn?.addEventListener('click', () => chart.timeScale().fitContent());
        container.addEventListener('dblclick', () => chart.timeScale().fitContent());
        }} catch (err) {{
          showError(`K 線圖初始化失敗：${{err && err.message ? err.message : err}}`);
        }}
      }})();
    </script>
    """

    components.html(html, height=910)
    st.caption("滑鼠滾輪縮放、拖曳平移、雙擊或按 Reset 回到完整範圍；十字線與 tooltip 由前端即時處理，不會觸發頁面重跑。")
