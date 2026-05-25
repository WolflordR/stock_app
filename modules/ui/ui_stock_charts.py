from __future__ import annotations

import json
from datetime import date, datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from modules.data_sources.market_watch import (
    fetch_tpex_daily_quotes,
    fetch_twse_daily_quotes,
    fetch_twse_day_trading_series,
)
from modules.data_sources.price_cache import fetch_price_history


UP_COLOR = "#FF4976"
DOWN_COLOR = "#41C77A"
GRID_COLOR = "rgba(148, 163, 184, 0.12)"
BG_COLOR = "#111827"
PANEL_COLOR = "#0F172A"
TEXT_COLOR = "#E5E7EB"
MUTED_TEXT_COLOR = "#94A3B8"
MA_COLORS = {
    "MA5": "#60A5FA",
    "MA10": "#8B5CF6",
    "MA20": "#FB923C",
    "MA60": "#FBBF24",
    "MA120": "#A16207",
}
VOLUME_MA_COLORS = {
    "MV5": "#60A5FA",
    "MV20": "#FB923C",
}
DAY_TRADE_COLOR = "#F6B26B"


def _normalize_date(value) -> str:
    if isinstance(value, (datetime, date)):
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    return pd.to_datetime(value).strftime("%Y-%m-%d")


@st.cache_data(show_spinner=False, ttl=1800)
def load_stock_chart_history(symbol: str, start_date, end_date) -> pd.DataFrame:
    history_df = fetch_price_history(
        symbol,
        mode="歷史回測",
        start_date=start_date,
        end_date=end_date,
        history_buffer_days=260,
        include_indicators=False,
    )
    if history_df.empty:
        return history_df

    chart_df = history_df.reset_index().rename(columns={"index": "Date"}).copy()
    chart_df["Date"] = pd.to_datetime(chart_df["Date"])
    chart_df = chart_df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    chart_df["Volume"] = pd.to_numeric(chart_df["Volume"], errors="coerce").fillna(0.0)
    for window in (5, 10, 20, 60, 120):
        chart_df[f"MA{window}"] = chart_df["Close"].rolling(window).mean()
    chart_df["MV5"] = chart_df["Volume"].rolling(5).mean() / 1000.0
    chart_df["MV20"] = chart_df["Volume"].rolling(20).mean() / 1000.0
    return chart_df


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


def _build_chart_payload(chart_df: pd.DataFrame, day_trade_df: pd.DataFrame | None = None) -> dict:
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
        date_text = row["Date"].strftime("%Y-%m-%d")
        open_price = float(row["Open"])
        high_price = float(row["High"])
        low_price = float(row["Low"])
        close_price = float(row["Close"])
        volume_lots = float(row["Volume"]) / 1000.0
        is_up = close_price >= open_price

        candles.append(
            {
                "time": date_text,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": close_price,
            }
        )
        volumes.append(
            {
                "time": date_text,
                "value": volume_lots,
                "color": UP_COLOR if is_up else DOWN_COLOR,
            }
        )
        day_trade_row = day_trade_map.get(date_text) or {}
        if day_trade_row.get("day_trade_ratio") is not None:
            day_trade_series.append(
                {
                    "time": date_text,
                    "value": float(day_trade_row["day_trade_ratio"]),
                    "color": DAY_TRADE_COLOR,
                }
            )

        for ma_name in MA_COLORS:
            ma_value = row.get(ma_name)
            if pd.notna(ma_value):
                ma_series[ma_name].append({"time": date_text, "value": float(ma_value)})

        for mv_name in volume_ma_series:
            mv_value = row.get(mv_name)
            if pd.notna(mv_value):
                volume_ma_series[mv_name].append({"time": date_text, "value": float(mv_value)})

        legend_rows.append(
            {
                "time": date_text,
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
):
    try:
        chart_df = load_stock_chart_history(symbol, start_date, end_date)
    except Exception as exc:  # noqa: BLE001
        st.error(f"讀取 {title} 的 K 線資料失敗：{exc}")
        return

    if chart_df.empty:
        st.warning("目前抓不到這檔股票的歷史價格資料。")
        return

    normalized_market = str(market_label or "").strip().upper()
    effective_code = str(stock_code or symbol.split(".")[0]).strip()
    day_trade_df = pd.DataFrame()
    if effective_code.isdigit() and normalized_market in {"TWSE", "上市"}:
        try:
            day_trade_df = load_twse_day_trade_history(effective_code)
        except Exception:
            day_trade_df = pd.DataFrame()

    latest_quote = None
    if effective_code.isdigit():
        try:
            latest_quote = load_latest_official_quote(effective_code, market_label, end_date)
        except Exception:
            latest_quote = None

    chart_df = _merge_latest_quote_into_chart(chart_df, latest_quote)

    payload = _build_chart_payload(chart_df, day_trade_df=day_trade_df)
    component_id = f"{key_prefix}_{symbol}_{_normalize_date(start_date)}_{_normalize_date(end_date)}".replace(".", "_")
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

    html = f"""
    <div id="{component_id}-wrapper" style="background:{PANEL_COLOR};border:1px solid rgba(148,163,184,0.16);border-radius:20px;padding:14px 14px 10px 14px;">
      <div id="{component_id}-legend" style="display:flex;flex-direction:column;gap:8px;margin-bottom:12px;color:{TEXT_COLOR};font-family:ui-sans-serif,system-ui,sans-serif;">
        <div style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;">
          <div style="font-size:18px;font-weight:700;">{title}</div>
          <div id="{component_id}-date" style="color:{MUTED_TEXT_COLOR};font-size:14px;"></div>
        </div>
        <div id="{component_id}-ohlc" style="font-size:15px;font-weight:700;"></div>
        <div id="{component_id}-ma" style="font-size:14px;color:{MUTED_TEXT_COLOR};"></div>
        <div id="{component_id}-volume-meta" style="font-size:14px;color:{TEXT_COLOR};font-weight:600;"></div>
        <div id="{component_id}-daytrade-meta" style="font-size:14px;color:{TEXT_COLOR};font-weight:600;"></div>
      </div>
      <div id="{component_id}" style="width:100%;height:700px;"></div>
      <div id="{component_id}-error" style="display:none;margin-top:10px;color:#FCA5A5;font-size:13px;font-family:ui-sans-serif,system-ui,sans-serif;"></div>
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
        if (!container || !window.LightweightCharts) return;

        function showError(message) {{
          if (!errorEl) return;
          errorEl.style.display = 'block';
          errorEl.textContent = message;
        }}

        try {{
        const chart = LightweightCharts.createChart(container, {{
          width: container.clientWidth,
          height: 700,
          layout: {{
            background: {{ type: 'solid', color: '{BG_COLOR}' }},
            textColor: '{TEXT_COLOR}',
            fontSize: 13,
          }},
          grid: {{
            vertLines: {{ color: '{GRID_COLOR}' }},
            horzLines: {{ color: '{GRID_COLOR}' }},
          }},
          crosshair: {{
            mode: LightweightCharts.CrosshairMode.Normal,
            vertLine: {{ labelBackgroundColor: '#374151', color: 'rgba(226,232,240,0.35)' }},
            horzLine: {{ labelBackgroundColor: '#374151', color: 'rgba(226,232,240,0.35)' }},
          }},
          rightPriceScale: {{
            borderColor: 'rgba(148, 163, 184, 0.20)',
            scaleMargins: {{ top: 0.06, bottom: 0.42 }},
          }},
          timeScale: {{
            borderColor: 'rgba(148, 163, 184, 0.20)',
            timeVisible: true,
            secondsVisible: false,
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
        }});
        candleSeries.setData(payload.candles);

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

        const byTime = new Map((payload.legend_rows || []).map(row => [row.time, row]));
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
          dateEl.textContent = row.time;
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
            daytradeMetaEl.textContent = dayTradeParts.length ? dayTradeParts.join(' ｜ ') : '當沖比例：目前僅支援上市股';
          }}
        }}

        renderLegend(latest);

        chart.subscribeCrosshairMove(param => {{
          if (!param || !param.time || !param.point || param.point.x < 0 || param.point.y < 0) {{
            renderLegend(latest);
            return;
          }}
          const time = typeof param.time === 'string' ? param.time : (
            param.time && param.time.year
              ? `${{param.time.year}}-${{String(param.time.month).padStart(2,'0')}}-${{String(param.time.day).padStart(2,'0')}}`
              : null
          );
          renderLegend(byTime.get(time) || latest);
        }});

        const ro = new ResizeObserver(() => {{
          chart.applyOptions({{ width: container.clientWidth }});
        }});
        ro.observe(container);
        }} catch (err) {{
          showError(`K 線圖初始化失敗：${{err && err.message ? err.message : err}}`);
        }}
      }})();
    </script>
    """

    components.html(html, height=850)
    st.caption("滑鼠移到哪根 K 棒，就會同步更新當天的 OHLC、成交量、均線與當沖比例資料。")
