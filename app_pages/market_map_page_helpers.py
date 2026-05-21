from __future__ import annotations

from html import escape
import re
from textwrap import dedent

import altair as alt
import pandas as pd
import streamlit as st

from modules.core.internal_nav import navigate_to_stock_detail
from modules.market_map.market_map_value_chain import build_topic_value_chain


MARKET_MAP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+TC:wght@400;500;600;700&family=DM+Sans:wght@500;700;800&family=IBM+Plex+Mono:wght@500;600&display=swap');
.stApp {
    background:
        radial-gradient(circle at 15% 12%, rgba(124,58,237,0.18), transparent 22%),
        radial-gradient(circle at 86% 14%, rgba(6,182,212,0.16), transparent 18%),
        radial-gradient(circle at 50% 100%, rgba(59,130,246,0.08), transparent 28%),
        linear-gradient(180deg, #030712 0%, #020617 45%, #000000 100%);
    color: #E5E7EB;
}
.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background-image:
        linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px);
    background-size: 42px 42px;
    mask-image: radial-gradient(circle at center, black 28%, transparent 88%);
    opacity: 0.16;
    z-index: 0;
}
.main .block-container {
    position: relative;
    z-index: 1;
    padding-top: 1.15rem;
}
.stApp, .stMarkdown, .stDataFrame, .stSelectbox, .stRadio, .stCaption, .stMetric {
    font-family: "IBM Plex Sans TC", "PingFang TC", "Noto Sans TC", sans-serif !important;
}
.stButton > button,
.stDownloadButton > button {
    border-radius: 999px !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    background: linear-gradient(135deg, rgba(124,58,237,0.95), rgba(6,182,212,0.90)) !important;
    color: white !important;
    box-shadow: 0 10px 28px rgba(6,182,212,0.14) !important;
    transition: all 500ms ease !important;
}
.stButton > button:hover,
.stDownloadButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 0 24px rgba(124,58,237,0.20), 0 0 20px rgba(6,182,212,0.18), 0 18px 36px rgba(0,0,0,0.24) !important;
    border-color: rgba(255,255,255,0.20) !important;
}
.stTextInput input,
.stSelectbox [data-baseweb="select"] > div {
    background: rgba(15,23,42,0.74) !important;
    border: 1px solid rgba(255,255,255,0.10) !important;
    color: #E5E7EB !important;
}
div[data-baseweb="select"] * { color: #E5E7EB !important; }
.stToggle label, .stRadio label, .stSelectbox label, .stTextInput label, .stCaption {
    color: #94A3B8 !important;
}
.stDataFrame {
    background: rgba(2,6,23,0.45);
    border-radius: 1rem;
}
.market-map-navbar {
    position: sticky;
    top: 0.7rem;
    z-index: 12;
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:1rem;
    padding: 0.9rem 1rem;
    margin-bottom: 1rem;
    border-radius: 1.15rem;
    border: 1px solid rgba(255,255,255,0.10);
    background: linear-gradient(135deg, rgba(3,7,18,0.72), rgba(15,23,42,0.42));
    backdrop-filter: blur(18px);
    box-shadow: 0 18px 50px rgba(0,0,0,0.28);
}
.market-map-nav-brand { display:flex; align-items:center; gap:0.8rem; }
.market-map-nav-logo {
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 0.85rem;
    background:
        radial-gradient(circle at 30% 30%, rgba(6,182,212,0.92), transparent 42%),
        linear-gradient(135deg, rgba(124,58,237,0.95), rgba(6,182,212,0.82));
    box-shadow: 0 0 28px rgba(6,182,212,0.22);
}
.market-map-nav-title {
    font-family:"DM Sans","IBM Plex Sans TC",sans-serif;
    font-size:1rem;
    font-weight:800;
    color:#F8FAFC;
    letter-spacing:-0.03em;
}
.market-map-nav-subtitle {
    font-size:0.75rem;
    color:#94A3B8;
    margin-top:0.15rem;
}
.market-map-nav-meta {
    display:flex;
    gap:0.5rem;
    flex-wrap:wrap;
    justify-content:flex-end;
}
.market-map-nav-pill {
    border-radius:999px;
    padding:0.28rem 0.62rem;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.10);
    color:#CBD5E1;
    font-size:0.75rem;
}
.market-map-hero {
    display:grid;
    grid-template-columns: minmax(0, 1.22fr) minmax(280px, 0.92fr);
    gap: 1rem;
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 1.6rem;
    padding: 1.25rem;
    background:
        radial-gradient(circle at top left, rgba(124,58,237,0.22), transparent 28%),
        radial-gradient(circle at bottom right, rgba(6,182,212,0.18), transparent 24%),
        linear-gradient(135deg, rgba(2,6,23,0.84), rgba(15,23,42,0.58));
    backdrop-filter: blur(18px);
    box-shadow: 0 24px 60px rgba(0,0,0,0.32);
    margin-bottom: 0.95rem;
}
.market-map-eyebrow {
    display:inline-flex;
    align-items:center;
    gap:0.35rem;
    border-radius:999px;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.10);
    color:#C4B5FD;
    padding:0.28rem 0.66rem;
    font-size:0.76rem;
    font-weight:700;
    margin-bottom:0.75rem;
}
.market-map-hero-title {
    font-family:"DM Sans","IBM Plex Sans TC",sans-serif;
    font-size: clamp(2.1rem, 3.8vw, 3.4rem);
    font-weight: 800;
    line-height: 0.94;
    letter-spacing: -0.045em;
    color:#F8FAFC;
    margin-bottom:0.6rem;
}
.market-map-hero-subtitle {
    color:#CBD5E1;
    font-size:0.97rem;
    line-height:1.78;
    max-width:70ch;
}
.market-map-hero-meta {
    display:flex;
    gap:0.5rem;
    flex-wrap:wrap;
    margin-top:0.95rem;
}
.market-map-meta-chip {
    border-radius:999px;
    padding:0.28rem 0.65rem;
    background:rgba(255,255,255,0.04);
    border:1px solid rgba(255,255,255,0.10);
    color:#CBD5E1;
    font-size:0.75rem;
}
.market-map-hero-art {
    position: relative;
    overflow: hidden;
    min-height: 290px;
    border-radius: 1.35rem;
    border: 1px solid rgba(255,255,255,0.10);
    background:
        radial-gradient(circle at 30% 35%, rgba(6,182,212,0.30), transparent 26%),
        radial-gradient(circle at 70% 30%, rgba(124,58,237,0.28), transparent 28%),
        radial-gradient(circle at 50% 78%, rgba(255,255,255,0.06), transparent 30%),
        linear-gradient(180deg, rgba(2,6,23,0.72), rgba(15,23,42,0.86));
}
.market-map-orb {
    position:absolute;
    inset:50% auto auto 50%;
    transform: translate(-50%, -50%);
    width: 150px;
    height: 150px;
    border-radius:999px;
    background: radial-gradient(circle at 35% 35%, rgba(255,255,255,0.95), rgba(6,182,212,0.24) 30%, rgba(124,58,237,0.22) 60%, transparent 74%);
    box-shadow: 0 0 70px rgba(6,182,212,0.20), 0 0 90px rgba(124,58,237,0.14);
}
.market-map-ring {
    position:absolute;
    inset:50% auto auto 50%;
    transform: translate(-50%, -50%);
    border-radius:999px;
    border:1px solid rgba(255,255,255,0.11);
}
.market-map-ring.r1 { width: 210px; height: 210px; }
.market-map-ring.r2 { width: 270px; height: 270px; border-color: rgba(6,182,212,0.14); }
.market-map-ring.r3 { width: 340px; height: 340px; border-color: rgba(124,58,237,0.12); }
.market-map-art-chip {
    position:absolute;
    border-radius:999px;
    padding:0.28rem 0.58rem;
    background: rgba(255,255,255,0.05);
    border:1px solid rgba(255,255,255,0.10);
    color:#E2E8F0;
    font-size:0.74rem;
    backdrop-filter: blur(12px);
}
.market-map-art-chip.c1 { top: 1rem; left: 1rem; }
.market-map-art-chip.c2 { top: 22%; right: 1rem; }
.market-map-art-chip.c3 { bottom: 1.2rem; left: 14%; }
.market-map-art-chip.c4 { bottom: 16%; right: 12%; }
.market-map-kpi-grid {
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap:0.8rem;
    margin: 0.9rem 0 1rem 0;
}
.market-map-kpi-card {
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 1.2rem;
    padding: 0.88rem 0.92rem 0.95rem 0.92rem;
    background: linear-gradient(180deg, rgba(15,23,42,0.76), rgba(2,6,23,0.72));
    backdrop-filter: blur(16px);
    box-shadow: 0 14px 26px rgba(0,0,0,0.20);
    transition: all 500ms ease;
}
.market-map-kpi-card:hover,
.market-map-overview-card:hover,
.market-map-sidebar-item:hover,
.market-map-detail-box:hover {
    transform: translateY(-2px);
    box-shadow: 0 0 26px rgba(6,182,212,0.10), 0 0 18px rgba(124,58,237,0.10), 0 20px 40px rgba(0,0,0,0.28);
    border-color: rgba(255,255,255,0.18);
}
.market-map-card-link {
    display: block;
    text-decoration: none !important;
}
.market-map-card-link:hover {
    text-decoration: none !important;
}
.market-map-kpi-label {
    font-size:0.78rem;
    color:#94A3B8;
    margin-bottom:0.45rem;
}
.market-map-kpi-value {
    font-family:"DM Sans","IBM Plex Sans TC",sans-serif;
    font-size:1.62rem;
    font-weight:800;
    color:#F8FAFC;
    letter-spacing:-0.03em;
    line-height:1.05;
    margin-bottom:0.18rem;
}
.market-map-kpi-note {
    font-size:0.76rem;
    color:#CBD5E1;
    line-height:1.45;
}
.market-map-section-title {
    font-family:"DM Sans","IBM Plex Sans TC",sans-serif;
    font-size:1.16rem;
    font-weight:800;
    letter-spacing:-0.02em;
    color:#F8FAFC;
    margin-bottom:0.18rem;
}
.market-map-section-note {
    font-size:0.86rem;
    color:#94A3B8;
    line-height:1.6;
    margin-bottom:0.5rem;
}
.market-map-overview {
    display:grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap:0.85rem;
    margin-top:0.65rem;
}
.market-map-overview-card {
    border-radius: 1.25rem;
    padding: 0.98rem 1rem 0.95rem 1rem;
    min-height: 12.6rem;
    box-shadow: 0 18px 34px rgba(0,0,0,0.24);
    transition: all 500ms ease;
}
.market-map-card-top {
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:0.5rem;
    margin-bottom:0.4rem;
}
.market-map-card-title {
    font-size:1rem;
    font-weight:800;
    line-height:1.25;
    letter-spacing:-0.01em;
}
.market-map-card-badge {
    border-radius:999px;
    padding:0.18rem 0.5rem;
    font-size:0.72rem;
    font-weight:800;
}
.market-map-card-parent {
    font-size:0.78rem;
    opacity:0.88;
    margin-bottom:0.76rem;
}
.market-map-card-main {
    font-family:"DM Sans","IBM Plex Sans TC",sans-serif;
    font-size:clamp(1.85rem, 2.8vw, 2.45rem);
    font-weight:900;
    line-height:1;
    letter-spacing:-0.03em;
    margin-bottom:0.28rem;
}
.market-map-card-sub {
    font-size:0.86rem;
    opacity:0.95;
    margin-bottom:0.72rem;
}
.market-map-card-chips {
    display:flex;
    flex-wrap:wrap;
    gap:0.42rem;
    margin-bottom:0.75rem;
}
.market-map-chip {
    border-radius:999px;
    padding:0.22rem 0.55rem;
    font-size:0.72rem;
    font-weight:700;
    white-space:nowrap;
}
.market-map-card-footer {
    font-size:0.8rem;
    line-height:1.48;
    opacity:0.93;
}
.market-map-sidebar-item {
    border-radius:1rem;
    padding:0.7rem 0.75rem;
    background: rgba(255,255,255,0.04);
    border:1px solid rgba(255,255,255,0.08);
    transition: all 500ms ease;
    margin-top:0.55rem;
}
.market-map-sidebar-item-title {
    font-size:0.8rem;
    font-weight:700;
    color:#E2E8F0;
    margin-bottom:0.16rem;
}
.market-map-sidebar-item-note {
    font-size:0.74rem;
    color:#94A3B8;
    line-height:1.45;
}
.market-map-detail-box {
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 1.1rem;
    padding: 0.95rem;
    background: linear-gradient(180deg, rgba(2,6,23,0.74), rgba(15,23,42,0.58));
    backdrop-filter: blur(16px);
    margin-bottom: 0.8rem;
    transition: all 500ms ease;
}
.market-map-detail-title {
    font-size:1.08rem;
    font-weight:850;
    color:#F8FAFC;
    margin-bottom:0.22rem;
    letter-spacing:-0.01em;
}
.market-map-detail-sub {
    font-size:0.84rem;
    color:#94A3B8;
    margin-bottom:0.72rem;
    line-height:1.45;
}
.market-map-detail-main {
    font-family:"DM Sans","IBM Plex Sans TC",sans-serif;
    font-size:2rem;
    font-weight:900;
    line-height:1;
    letter-spacing:-0.03em;
    margin-bottom:0.25rem;
}
.market-map-legend {
    display:flex;
    align-items:center;
    gap:0.5rem;
    flex-wrap:wrap;
    color:#94A3B8;
    font-size:0.82rem;
    margin-top:0.4rem;
}
.market-map-legend-scale {
    display:flex;
    width:220px;
    height:11px;
    border-radius:999px;
    overflow:hidden;
    border:1px solid rgba(255,255,255,0.10);
}
.market-map-legend-scale span { flex:1; }
.market-map-ranking-row {
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:0.75rem;
    padding:0.68rem 0.12rem;
    border-bottom:1px solid rgba(255,255,255,0.08);
}
.market-map-ranking-row:last-child { border-bottom:none; }
.market-map-ranking-name {
    font-size:0.84rem;
    font-weight:700;
    color:#E2E8F0;
    margin-bottom:0.16rem;
}
.market-map-ranking-sub {
    font-size:0.74rem;
    color:#94A3B8;
    line-height:1.45;
}
.market-map-ranking-value {
    font-family:"IBM Plex Mono", monospace;
    font-size:0.82rem;
    font-weight:600;
    color:#E2E8F0;
    white-space:nowrap;
}
@media (max-width: 980px) {
    .market-map-navbar {
        flex-direction: column;
        align-items:flex-start;
    }
    .market-map-nav-meta {
        justify-content:flex-start;
    }
    .market-map-hero {
        grid-template-columns: 1fr;
    }
    .market-map-hero-art {
        min-height: 220px;
    }
}
</style>
"""


def _html_fragment(value):
    return dedent(value).strip()


def extract_primary_stock_code(representative_stocks):
    text = str(representative_stocks or "")
    match = re.search(r"\((\d{4})\)", text)
    return match.group(1) if match else None


def _split_treemap_items(items):
    total = sum(item["size"] for item in items)
    if len(items) <= 1 or total <= 0:
        return items, []

    running = 0.0
    split_index = 0
    for index, item in enumerate(items):
        running += item["size"]
        split_index = index + 1
        if running >= total / 2:
            break
    left = items[:split_index]
    right = items[split_index:]
    if not right:
        left = items[:-1]
        right = items[-1:]
    return left, right


def _slice_treemap(items, x, y, width, height, output_rows):
    if not items or width <= 0 or height <= 0:
        return
    if len(items) == 1:
        item = items[0]
        output_rows.append(
            {
                **item,
                "x": x,
                "y": y,
                "x2": x + width,
                "y2": y + height,
                "area": width * height,
            }
        )
        return

    total = sum(item["size"] for item in items)
    left_items, right_items = _split_treemap_items(items)
    left_total = sum(item["size"] for item in left_items)
    ratio = left_total / total if total else 0.5

    if width >= height:
        split_width = width * ratio
        _slice_treemap(left_items, x, y, split_width, height, output_rows)
        _slice_treemap(right_items, x + split_width, y, width - split_width, height, output_rows)
    else:
        split_height = height * ratio
        _slice_treemap(left_items, x, y, width, split_height, output_rows)
        _slice_treemap(right_items, x, y + split_height, width, height - split_height, output_rows)


def _build_treemap_layout_df(heatmap_df, *, size_col, value_col, max_tiles=18):
    if heatmap_df.empty:
        return pd.DataFrame()

    working_df = heatmap_df.copy()
    working_df[size_col] = pd.to_numeric(working_df[size_col], errors="coerce").fillna(0.0)
    working_df[value_col] = pd.to_numeric(working_df[value_col], errors="coerce")
    working_df = working_df.sort_values(size_col, ascending=False).reset_index(drop=True)

    main_df = working_df.head(max_tiles).copy()
    remainder_df = working_df.iloc[max_tiles:].copy()
    if not remainder_df.empty:
        value_series = remainder_df[value_col].dropna()
        remainder_row = {
            "code": "REST",
            "name": "其他成分股",
            "market": "",
            "official_industry": "",
            size_col: remainder_df[size_col].sum(),
            "change_pct": value_series.mean() if not value_series.empty else None,
            "week_change_pct": remainder_df["week_change_pct"].dropna().mean() if "week_change_pct" in remainder_df.columns and not remainder_df["week_change_pct"].dropna().empty else None,
            "month_change_pct": remainder_df["month_change_pct"].dropna().mean() if "month_change_pct" in remainder_df.columns and not remainder_df["month_change_pct"].dropna().empty else None,
            "volume": remainder_df["volume"].sum(),
        }
        main_df = pd.concat([main_df, pd.DataFrame([remainder_row])], ignore_index=True)

    positive_size_df = main_df[main_df[size_col] > 0].copy()
    if positive_size_df.empty:
        positive_size_df = main_df.copy()
        positive_size_df[size_col] = 1.0

    items = []
    total_size = float(positive_size_df[size_col].sum()) or float(len(positive_size_df))
    for _, row in positive_size_df.iterrows():
        items.append(
            {
                "code": str(row.get("code") or ""),
                "name": str(row.get("name") or ""),
                "market": str(row.get("market") or ""),
                "official_industry": str(row.get("official_industry") or ""),
                "change_pct": row.get("change_pct"),
                "week_change_pct": row.get("week_change_pct"),
                "month_change_pct": row.get("month_change_pct"),
                "volume": row.get("volume"),
                "turnover_value": row.get("turnover_value", row.get(size_col)),
                "size": float(row.get(size_col) or 1.0),
                "heat_value": row.get(value_col),
            }
        )

    output_rows = []
    _slice_treemap(items, 0.0, 0.0, 100.0, 100.0, output_rows)
    layout_df = pd.DataFrame(output_rows)
    if layout_df.empty:
        return layout_df

    layout_df["label_pct"] = layout_df["heat_value"].map(format_pct)
    layout_df["display_name"] = layout_df["name"].astype(str)
    layout_df["label"] = layout_df["display_name"] + "\n" + layout_df["label_pct"]
    layout_df["center_x"] = (layout_df["x"] + layout_df["x2"]) / 2
    layout_df["center_y"] = (layout_df["y"] + layout_df["y2"]) / 2
    layout_df["show_label"] = layout_df["area"] >= 180
    layout_df["font_size"] = layout_df["area"].apply(
        lambda area: 26 if area >= 1200 else 22 if area >= 700 else 18 if area >= 380 else 14
    )
    layout_df["tooltip_name"] = layout_df["display_name"] + " (" + layout_df["code"].astype(str) + ")"
    layout_df["size_ratio"] = layout_df["size"] / total_size
    return layout_df


def safe_float(value, default=0.0):
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_pct(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}%"


def format_ratio(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}x"


def format_billions(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) / 100000000:,.2f} 億"


def format_lots(value):
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value) / 1000:,.1f} 張"


def heat_style(change_pct):
    value = safe_float(change_pct)
    if value >= 3.0:
        return {
            "bg": "linear-gradient(135deg, rgba(127,29,29,0.92), rgba(220,38,38,0.80))",
            "border": "rgba(248, 113, 113, 0.45)",
            "text": "#fff7f7",
            "chip": "rgba(255,255,255,0.12)",
            "glow": "0 0 26px rgba(248,113,113,0.16)",
        }
    if value >= 1.0:
        return {
            "bg": "linear-gradient(135deg, rgba(124,58,237,0.86), rgba(6,182,212,0.46))",
            "border": "rgba(125, 211, 252, 0.34)",
            "text": "#f8fafc",
            "chip": "rgba(255,255,255,0.10)",
            "glow": "0 0 26px rgba(124,58,237,0.18)",
        }
    if value > -1.0:
        return {
            "bg": "linear-gradient(135deg, rgba(15,23,42,0.92), rgba(30,41,59,0.76))",
            "border": "rgba(255,255,255,0.10)",
            "text": "#f8fafc",
            "chip": "rgba(255,255,255,0.08)",
            "glow": "0 0 0 rgba(0,0,0,0)",
        }
    if value > -3.0:
        return {
            "bg": "linear-gradient(135deg, rgba(3,105,161,0.88), rgba(15,23,42,0.84))",
            "border": "rgba(125,211,252,0.34)",
            "text": "#eff6ff",
            "chip": "rgba(255,255,255,0.10)",
            "glow": "0 0 26px rgba(6,182,212,0.14)",
        }
    return {
        "bg": "linear-gradient(135deg, rgba(29,78,216,0.88), rgba(15,23,42,0.88))",
        "border": "rgba(147,197,253,0.38)",
        "text": "#eff6ff",
        "chip": "rgba(255,255,255,0.10)",
        "glow": "0 0 26px rgba(59,130,246,0.16)",
    }


def topic_badge(row):
    change_pct = safe_float(row.get("avg_change_pct"))
    volume_ratio = safe_float(row.get("volume_ratio"))
    heat_score = safe_float(row.get("heat_score"))
    if change_pct >= 2.0 and volume_ratio >= 1.15:
        return "Breakout"
    if heat_score >= 24:
        return "Momentum"
    if change_pct <= -1.5:
        return "Pullback"
    return "Watching"


def inject_market_map_css():
    st.markdown(MARKET_MAP_CSS, unsafe_allow_html=True)


def render_navbar(status, bundle):
    source_label_map = {"cache": "Cached", "fresh": "Fresh", "empty": "Empty"}
    st.markdown(
        f"""
        <div class="market-map-navbar">
            <div class="market-map-nav-brand">
                <div class="market-map-nav-logo"></div>
                <div>
                    <div class="market-map-nav-title">Trade Lab Market Map</div>
                    <div class="market-map-nav-subtitle">Premium dark mode · Taiwan topics · glass UI</div>
                </div>
            </div>
            <div class="market-map-nav-meta">
                <div class="market-map-nav-pill">Date {escape(str(bundle.get('used_date') or '-'))}</div>
                <div class="market-map-nav-pill">Topics {int(status.get('topic_count') or 0)}</div>
                <div class="market-map-nav-pill">Companies {int(status.get('company_count') or 0)}</div>
                <div class="market-map-nav-pill">{escape(source_label_map.get(bundle.get('snapshot_source'), 'Unknown'))}</div>
                <div class="market-map-nav-pill">{escape(str(status.get('region_scope') or 'TW_ONLY'))}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_hero(status, bundle):
    top_topic = bundle["topic_snapshot_df"].iloc[0] if not bundle["topic_snapshot_df"].empty else None
    top_group = (
        bundle["group_summary_df"]
        .sort_values(["heat_score", "total_turnover"], ascending=[False, False])
        .iloc[0]
        if not bundle["group_summary_df"].empty
        else None
    )
    top_topic_name = str(top_topic["topic_name"]) if top_topic is not None else "暫無資料"
    top_group_name = str(top_group["group_name"]) if top_group is not None else "暫無資料"
    hero_note = (
        f"今天最熱的題材是 {top_topic_name}，最有存在感的大類是 {top_group_name}。"
        " 我先把你最在意的版面氣質、閱讀節奏、熱區感與卡片舒適度往高級產品頁方向推進。"
    )
    st.markdown(
        f"""
        <div class="market-map-hero">
            <div>
                <div class="market-map-eyebrow">Taiwan Market Map · Beta</div>
                <div class="market-map-hero-title">One Page,<br/>Full Topic Momentum</div>
                <div class="market-map-hero-subtitle">{hero_note}</div>
                <div class="market-map-hero-meta">
                    <div class="market-map-meta-chip">資料日期：{escape(str(bundle.get('used_date') or '-'))}</div>
                    <div class="market-map-meta-chip">資料範圍：{escape(str(status.get('region_scope') or 'TW_ONLY'))}</div>
                    <div class="market-map-meta-chip">題材數：{int(status.get('topic_count') or 0)}</div>
                    <div class="market-map-meta-chip">公司數：{int(status.get('company_count') or 0)}</div>
                </div>
            </div>
            <div class="market-map-hero-art">
                <div class="market-map-orb"></div>
                <div class="market-map-ring r1"></div>
                <div class="market-map-ring r2"></div>
                <div class="market-map-ring r3"></div>
                <div class="market-map-art-chip c1">AI Server</div>
                <div class="market-map-art-chip c2">Photonics</div>
                <div class="market-map-art-chip c3">Semiconductor</div>
                <div class="market-map-art-chip c4">Power & Cooling</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpi_strip(status, bundle):
    hot_df = bundle["topic_snapshot_df"]
    top_topic_name = hot_df.iloc[0]["topic_name"] if not hot_df.empty else "-"
    heat_avg = hot_df.head(10)["heat_score"].mean() if not hot_df.empty else None
    breadth_mean = (
        (hot_df["up_count"] / hot_df["company_count"].replace(0, pd.NA)).head(10).mean() * 100.0
        if not hot_df.empty
        else None
    )
    total_turnover = hot_df.head(10)["total_turnover"].sum() if not hot_df.empty else None
    cards = [
        ("最熱題材", top_topic_name, "先看誰是今天盤面主敘事。"),
        ("前十題材平均熱度", f"{safe_float(heat_avg):.1f}", "綜合價格、量能與擴散度。"),
        ("前十題材平均上漲家數", f"{safe_float(breadth_mean):.1f}%", "看擴散，不只是少數龍頭。"),
        ("前十題材成交值", format_billions(total_turnover), "判斷資金是否真的有集中。"),
        ("最後整理", bundle.get("used_date") or "-", f"taxonomy：{status.get('taxonomy_version') or '-'}"),
    ]
    html = []
    for label, value, note in cards:
        html.append(
            (
                '<div class="market-map-kpi-card">'
                f'<div class="market-map-kpi-label">{escape(str(label))}</div>'
                f'<div class="market-map-kpi-value">{escape(str(value))}</div>'
                f'<div class="market-map-kpi-note">{escape(str(note))}</div>'
                "</div>"
            )
        )
    st.markdown("<div class='market-map-kpi-grid'>" + "".join(html) + "</div>", unsafe_allow_html=True)


def render_overview_cards(topic_snapshot_df, *, max_items=15, link_resolver=None):
    if topic_snapshot_df.empty:
        st.caption("目前沒有可顯示的題材熱區。")
        return

    card_html = []
    for _, row in topic_snapshot_df.head(max_items).iterrows():
        style = heat_style(row.get("avg_change_pct"))
        topic_name = escape(str(row.get("topic_name") or "未命名題材"))
        parent = escape(str(row.get("parent_industry") or ""))
        reps = escape(str(row.get("representative_stocks") or "-"))
        badge = topic_badge(row)
        card_markup = _html_fragment(
                f"""
                <div class="market-map-overview-card" style="background:{style['bg']};border:1px solid {style['border']};color:{style['text']};box-shadow:{style['glow']}, 0 18px 34px rgba(0,0,0,0.24);">
                    <div class="market-map-card-top">
                        <div class="market-map-card-title">{topic_name}</div>
                        <div class="market-map-card-badge" style="background:{style['chip']};">{badge}</div>
                    </div>
                    <div class="market-map-card-parent">{parent or '&nbsp;'}</div>
                    <div class="market-map-card-main">{format_pct(row.get("avg_change_pct"))}</div>
                    <div class="market-map-card-sub">5日 {format_pct(row.get("five_day_change_pct"))} ・ 量比 {format_ratio(row.get("volume_ratio"))}</div>
                    <div class="market-map-card-chips">
                        <div class="market-map-chip" style="background:{style['chip']};">成交值比 {format_ratio(row.get("turnover_ratio"))}</div>
                        <div class="market-map-chip" style="background:{style['chip']};">上漲家數 {int(safe_float(row.get('up_count')))}/{int(safe_float(row.get('company_count')))}</div>
                        <div class="market-map-chip" style="background:{style['chip']};">分數 {safe_float(row.get("heat_score")):.1f}</div>
                    </div>
                    <div class="market-map-card-footer">{reps}</div>
                </div>
                """
            )
        card_html.append(card_markup)

    st.markdown(
        """
        <div class="market-map-legend">
            <span>Weak</span>
            <div class="market-map-legend-scale">
                <span style="background:#1d4ed8;"></span>
                <span style="background:#334155;"></span>
                <span style="background:#06b6d4;"></span>
                <span style="background:#7c3aed;"></span>
            </div>
            <span>Strong</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div class='market-map-overview'>" + "".join(card_html) + "</div>", unsafe_allow_html=True)


def render_group_sidebar(group_summary_df):
    st.markdown("<div class='market-map-section-title'>Topic Groups</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='market-map-section-note'>先挑一個大類，縮小閱讀範圍，再往下看具體題材。</div>",
        unsafe_allow_html=True,
    )
    group_options = group_summary_df["group_name"].tolist()
    with st.container(border=True):
        selected_group = st.radio(
            "大類",
            group_options,
            index=0,
            key="market_map_selected_group",
            label_visibility="collapsed",
        )
        top_groups_df = group_summary_df.sort_values(
            ["heat_score", "avg_change_pct"],
            ascending=[False, False],
        ).head(4)
        rows = []
        for _, row in top_groups_df.iterrows():
            rows.append(
                _html_fragment(
                    f"""
                    <div class="market-map-sidebar-item">
                        <div class="market-map-sidebar-item-title">{escape(str(row['group_name']))}</div>
                        <div class="market-map-sidebar-item-note">
                            單日 {format_pct(row.get('avg_change_pct'))} ・ 5日 {format_pct(row.get('five_day_change_pct'))}<br/>
                            題材 {int(safe_float(row.get('topic_count')))} 個 ・ 熱度 {safe_float(row.get('heat_score')):.1f}
                        </div>
                    </div>
                    """
                )
            )
        st.markdown("".join(rows), unsafe_allow_html=True)
    return selected_group


def render_topic_cards_panel(group_topic_df, selected_topic, *, group_name=None):
    if group_topic_df.empty:
        st.info("這個大類目前沒有可顯示的題材。")
        return None

    st.markdown("<div class='market-map-section-title'>Bento Topic Grid</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='market-map-section-note'>這裡是你現在最需要的主戰場：同大類內的題材，一眼看出誰最熱、誰開始走弱。</div>",
        unsafe_allow_html=True,
    )
    filter_cols = st.columns([1.05, 1.0, 1.2])
    sort_label = filter_cols[0].selectbox(
        "題材排序",
        ["綜合熱度", "單日漲跌", "5日漲跌", "量比", "成交值比"],
        index=0,
        key="market_map_topic_sort",
    )
    min_company_count = filter_cols[1].selectbox(
        "成分股門檻",
        [0, 3, 5, 8],
        index=0,
        key="market_map_min_company_count",
    )
    topic_keyword = filter_cols[2].text_input(
        "搜尋題材",
        value="",
        key="market_map_topic_keyword",
        placeholder="例如：記憶體、CPO、散熱",
    ).strip()

    sort_map = {
        "綜合熱度": ["heat_score", "total_turnover", "avg_change_pct"],
        "單日漲跌": ["avg_change_pct", "heat_score", "total_turnover"],
        "5日漲跌": ["five_day_change_pct", "heat_score", "total_turnover"],
        "量比": ["volume_ratio", "heat_score", "total_turnover"],
        "成交值比": ["turnover_ratio", "heat_score", "total_turnover"],
    }
    filtered_df = group_topic_df[group_topic_df["company_count"] >= min_company_count].copy()
    if topic_keyword:
        mask = (
            filtered_df["topic_name"].astype(str).str.contains(topic_keyword, case=False, na=False)
            | filtered_df["representative_stocks"].astype(str).str.contains(topic_keyword, case=False, na=False)
            | filtered_df["description"].astype(str).str.contains(topic_keyword, case=False, na=False)
        )
        filtered_df = filtered_df[mask]
    sorted_df = filtered_df.sort_values(sort_map[sort_label], ascending=[False, False, False]).reset_index(drop=True)
    st.caption(f"目前顯示 {len(sorted_df)} 個題材。")

    with st.container(border=True):
        render_overview_cards(sorted_df, max_items=min(12, len(sorted_df)))

    st.caption("如果卡片本身沒有切換，直接用下面這排按鈕進入熱力圖。")

    quick_topics = sorted_df["topic_name"].head(min(9, len(sorted_df))).tolist()
    if quick_topics:
        st.markdown("<div class='market-map-section-note'>快速進入熱力圖</div>", unsafe_allow_html=True)
        for start_index in range(0, len(quick_topics), 3):
            cols = st.columns(3)
            for col, topic_name in zip(cols, quick_topics[start_index:start_index + 3]):
                with col:
                    if st.button(
                        f"查看 {topic_name}",
                        key=f"market_map_open_detail_{group_name}_{topic_name}",
                        use_container_width=True,
                    ):
                        from internal_nav import navigate_to_market_map
                        navigate_to_market_map(topic_name=topic_name, group_name=group_name, view_mode="detail")

    topic_options = sorted_df["topic_name"].tolist()
    if not topic_options:
        st.info("這個篩選條件下沒有可顯示的題材。")
        return None
    default_index = topic_options.index(selected_topic) if selected_topic in topic_options else 0
    return st.selectbox("聚焦題材", topic_options, index=default_index, key="market_map_selected_topic")


def render_topic_ranking(topic_members_df):
    if topic_members_df.empty:
        return
    st.markdown("<div class='market-map-section-title'>Leading Stocks</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='market-map-section-note'>先看成交值與漲跌幅排序，快速知道是哪幾檔在真正驅動題材。</div>",
        unsafe_allow_html=True,
    )
    top_rows = topic_members_df.sort_values(["turnover_value", "change_pct"], ascending=[False, False]).head(6).copy()
    html = []
    for _, row in top_rows.iterrows():
        html.append(
            _html_fragment(
                f"""
                <div class="market-map-ranking-row">
                    <div>
                        <div class="market-map-ranking-name">{escape(str(row['name']))} ({escape(str(row['code']))})</div>
                        <div class="market-map-ranking-sub">{escape(str(row.get('official_industry') or '-'))}</div>
                    </div>
                    <div class="market-map-ranking-value">{format_pct(row.get('change_pct'))}<br/>{format_billions(row.get('turnover_value'))}</div>
                </div>
                """
            )
        )
    st.markdown(f"<div class='market-map-detail-box'>{''.join(html)}</div>", unsafe_allow_html=True)


def render_topic_detail(topic_row, topic_members_df, topic_event_summary=None, topic_event_items_df=None):
    st.markdown("<div class='market-map-section-title'>Detail Panel</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='market-map-section-note'>右邊這層負責把你選的題材講清楚，不用再跳別頁才知道自己在看什麼。</div>",
        unsafe_allow_html=True,
    )
    if topic_row is None:
        st.caption("先在中間選一個題材。")
        return

    style = heat_style(topic_row.get("avg_change_pct"))
    st.markdown(
        f"""
        <div class="market-map-detail-box" style="background:{style['bg']};color:{style['text']};border:1px solid {style['border']};box-shadow:{style['glow']}, 0 18px 34px rgba(0,0,0,0.26);">
            <div class="market-map-detail-title">{escape(str(topic_row.get('topic_name') or '未命名題材'))}</div>
            <div class="market-map-detail-sub">{escape(str(topic_row.get('parent_industry') or ''))}</div>
            <div class="market-map-detail-main">{format_pct(topic_row.get('avg_change_pct'))}</div>
            <div style="font-size:0.88rem;opacity:0.94;margin-bottom:0.65rem;">
                5日 {format_pct(topic_row.get('five_day_change_pct'))} ・ 量比 {format_ratio(topic_row.get('volume_ratio'))} ・ 成交值比 {format_ratio(topic_row.get('turnover_ratio'))}
            </div>
            <div style="font-size:0.82rem;line-height:1.5;">
                代表股：{escape(str(topic_row.get('representative_stocks') or '-'))}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_cols = st.columns(3)
    metric_cols[0].metric("成分股數", int(safe_float(topic_row.get("company_count"))))
    metric_cols[1].metric(
        "上漲家數",
        f"{int(safe_float(topic_row.get('up_count')))}/{int(safe_float(topic_row.get('company_count')))}",
    )
    metric_cols[2].metric("題材分數", f"{safe_float(topic_row.get('heat_score')):.1f}")

    if topic_event_summary:
        event_cols = st.columns(3)
        event_cols[0].metric("重訊筆數", int(safe_float(topic_event_summary.get("event_count"))))
        event_cols[1].metric("涉及公司", int(safe_float(topic_event_summary.get("company_count"))))
        event_cols[2].metric("風險事件", int(safe_float(topic_event_summary.get("risk_event_count"))))

    st.markdown(
        f"""
        <div class="market-map-detail-box">
            <div class="market-map-detail-title">Topic Memo</div>
            <div class="market-map-detail-sub">{escape(str(topic_row.get('description') or '目前先用關鍵字摘要，之後可以再補成正式題材敘述。'))}</div>
            <div style="font-size:0.84rem;line-height:1.7;color:#CBD5E1;">
                強勢股：{escape(str(topic_row.get('top_leaders') or '-'))}<br/>
                轉弱股：{escape(str(topic_row.get('top_laggards') or '-'))}<br/>
                題材搜尋語句：{escape(str(topic_row.get('news_query') or '-'))}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    render_topic_ranking(topic_members_df)

    if topic_event_items_df is not None and not topic_event_items_df.empty:
        st.markdown("<div class='market-map-section-title'>Recent Official Events</div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='market-map-section-note'>先接官方重大訊息，讓題材頁先看得到今天有哪些公司事件，不做 AI 摘要也能直接用。</div>",
            unsafe_allow_html=True,
        )
        rows = []
        for _, row in topic_event_items_df.head(6).iterrows():
            company_label = f"{row.get('company_name') or '-'} ({row.get('company_code') or '-'})"
            event_at = row.get("event_at") or row.get("event_date") or "-"
            title = escape(str(row.get("title") or "-"))
            url = str(row.get("url") or "").strip()
            title_html = f"<a href='{escape(url)}' target='_blank' style='color:#F8FAFC;text-decoration:none;'>{title}</a>" if url else title
            rows.append(
                _html_fragment(
                    f"""
                    <div class="market-map-ranking-row">
                        <div>
                            <div class="market-map-ranking-name">{escape(company_label)}</div>
                            <div class="market-map-ranking-sub">{escape(str(row.get('event_type') or '-'))} ・ {escape(str(event_at))}</div>
                            <div class="market-map-ranking-sub" style="color:#CBD5E1;margin-top:0.28rem;">{title_html}</div>
                        </div>
                        <div class="market-map-ranking-value">{safe_float(row.get('severity_score')):.1f}</div>
                    </div>
                    """
                )
            )
        st.markdown(f"<div class='market-map-detail-box'>{''.join(rows)}</div>", unsafe_allow_html=True)

    if topic_members_df.empty:
        st.caption("目前沒有這個題材的成分股快照。")
        return

    display_df = topic_members_df.copy()
    display_df["漲跌幅"] = display_df["change_pct"].map(format_pct)
    display_df["成交值"] = display_df["turnover_value"].map(format_billions)
    display_df["成交量"] = display_df["volume"].map(format_lots)
    display_df["分類"] = display_df["source"].fillna("").astype(str)
    st.dataframe(
        display_df.rename(
            columns={
                "code": "代碼",
                "name": "名稱",
                "market": "市場",
                "official_industry": "官方產業",
            }
        )[["代碼", "名稱", "市場", "官方產業", "漲跌幅", "成交量", "成交值", "分類"]],
        use_container_width=True,
        hide_index=True,
    )


def render_topic_heatmap(topic_row, heatmap_df):
    st.markdown("<div class='market-map-section-title'>Industry Heat Map</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='market-map-section-note'>點進題材後先看成分股熱力圖。面積代表成交值，顏色代表漲跌幅，先把盤面主力股一次看清楚。</div>",
        unsafe_allow_html=True,
    )
    if topic_row is None or heatmap_df is None or heatmap_df.empty:
        st.caption("目前沒有足夠的成分股資料可以畫熱力圖。")
        return

    period_options = {
        "單日": "change_pct",
        "單週": "week_change_pct",
        "單月": "month_change_pct",
    }
    selected_period = st.segmented_control(
        "熱力區間",
        list(period_options.keys()),
        default="單日",
        key=f"market_map_heatmap_period_{topic_row.get('topic_name', 'default')}",
        label_visibility="collapsed",
        width="content",
    )
    value_col = period_options[selected_period]
    if value_col not in heatmap_df.columns or heatmap_df[value_col].dropna().empty:
        fallback_period = "單週" if selected_period == "單月" else "單日"
        st.caption(f"{selected_period} 資料目前不足，先顯示 {fallback_period} 熱力圖。")
        value_col = period_options[fallback_period]

    layout_df = _build_treemap_layout_df(heatmap_df, size_col="turnover_value", value_col=value_col)
    if layout_df.empty:
        st.caption("目前沒有可顯示的熱力圖資料。")
        return

    color_domain = [-10, -5, -2, 0, 2, 5, 10]
    color_range = ["#22c55e", "#86efac", "#d1fae5", "#cbd5e1", "#fecaca", "#f87171", "#dc2626"]
    base = alt.Chart(layout_df)

    rect_chart = base.mark_rect(stroke="#0F172A", strokeWidth=2, cornerRadius=8).encode(
        x=alt.X("x:Q", axis=None, scale=alt.Scale(domain=[0, 100])),
        x2="x2:Q",
        y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[100, 0])),
        y2="y2:Q",
        color=alt.Color(
            "heat_value:Q",
            scale=alt.Scale(domain=color_domain, range=color_range),
            legend=alt.Legend(title=None, orient="bottom", direction="horizontal"),
        ),
        tooltip=[
            alt.Tooltip("tooltip_name:N", title="公司"),
            alt.Tooltip("change_pct:Q", title="單日", format=".2f"),
            alt.Tooltip("week_change_pct:Q", title="單週", format=".2f"),
            alt.Tooltip("month_change_pct:Q", title="單月", format=".2f"),
            alt.Tooltip("turnover_value:Q", title="成交值", format=",.0f"),
            alt.Tooltip("volume:Q", title="成交量", format=",.0f"),
        ],
    )

    label_df = layout_df[layout_df["show_label"]].copy()
    name_chart = alt.Chart(label_df).mark_text(
        align="center",
        baseline="middle",
        font="IBM Plex Sans TC",
        fontWeight="bold",
        lineBreak="\n",
        dy=-10,
        color="#111827",
    ).encode(
        x=alt.X("center_x:Q", axis=None, scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("center_y:Q", axis=None, scale=alt.Scale(domain=[100, 0])),
        text=alt.Text("display_name:N"),
        size=alt.Size("font_size:Q", legend=None),
    )
    pct_chart = alt.Chart(label_df).mark_text(
        align="center",
        baseline="middle",
        font="IBM Plex Sans TC",
        fontWeight="normal",
        dy=16,
        color="#111827",
    ).encode(
        x=alt.X("center_x:Q", axis=None, scale=alt.Scale(domain=[0, 100])),
        y=alt.Y("center_y:Q", axis=None, scale=alt.Scale(domain=[100, 0])),
        text=alt.Text("label_pct:N"),
        size=alt.Size("font_size:Q", legend=None),
    )

    chart = (
        alt.layer(rect_chart, name_chart, pct_chart)
        .properties(height=520)
        .configure_view(stroke=None)
        .configure(background="transparent")
    )
    st.altair_chart(chart, use_container_width=True)

    summary_cols = st.columns(4)
    summary_cols[0].metric("題材", str(topic_row.get("topic_name") or "-"))
    summary_cols[1].metric("成分股數", len(heatmap_df))
    summary_cols[2].metric("熱力區間", selected_period)
    summary_cols[3].metric("上漲家數", f"{int(safe_float(topic_row.get('up_count')))}/{int(safe_float(topic_row.get('company_count')))}")
    st.caption(f"代表股：{topic_row.get('representative_stocks') or '-'}")

    st.markdown("<div class='market-map-section-note'>從這裡直接進個股詳頁。</div>", unsafe_allow_html=True)
    jump_df = (
        heatmap_df.sort_values(["turnover_value", "change_pct"], ascending=[False, False])
        .head(9)
        .copy()
    )
    if not jump_df.empty:
        for start_index in range(0, len(jump_df), 3):
            cols = st.columns(3)
            for col, (_, row) in zip(cols, jump_df.iloc[start_index:start_index + 3].iterrows()):
                company_name = str(row.get("name") or row.get("name_zh") or row.get("code") or "-")
                company_code = str(row.get("code") or "").strip()
                if not company_code:
                    continue
                button_label = f"開啟 {company_name} {company_code}"
                with col:
                    if st.button(
                        button_label,
                        key=f"market_map_heatmap_stock_{topic_row.get('topic_name', 'topic')}_{company_code}",
                        use_container_width=True,
                    ):
                        navigate_to_stock_detail(company_code)


def render_topic_value_chain(topic_row, topic_snapshot_df):
    st.markdown("<div class='market-map-section-title'>產業價值鏈結構</div>", unsafe_allow_html=True)
    st.markdown(
        "<div class='market-map-section-note'>先用題材關聯做第一版價值鏈，幫你快速看這個主題上游材料、中游製程、下游應用分布。</div>",
        unsafe_allow_html=True,
    )
    sections = build_topic_value_chain(topic_row, topic_snapshot_df)
    if not sections:
        st.caption("目前還沒有這個題材的價值鏈資料。")
        return

    columns = st.columns(3)
    for column, section in zip(columns, sections):
        with column:
            st.markdown(
                f"<div class='market-map-detail-box'><div class='market-map-detail-title'>{section['title']}</div><div class='market-map-detail-sub'>相關題材與代表股</div></div>",
                unsafe_allow_html=True,
            )
            if not section["items"]:
                st.caption("暫無對應題材。")
                continue
            for item in section["items"]:
                style = heat_style(item.get("avg_change_pct"))
                st.markdown(
                    _html_fragment(
                        f"""
                        <div class="market-map-detail-box" style="background:{style['bg']};color:{style['text']};border:1px solid {style['border']};box-shadow:{style['glow']}, 0 10px 24px rgba(0,0,0,0.18);">
                            <div class="market-map-ranking-name">{escape(str(item.get('topic_name') or '-'))}</div>
                            <div class="market-map-ranking-sub" style="color:{style['text']};opacity:0.82;">{escape(str(item.get('parent_industry') or '-'))}</div>
                            <div style="font-size:1.1rem;font-weight:800;margin:0.4rem 0 0.25rem 0;">{format_pct(item.get('avg_change_pct'))}</div>
                            <div class="market-map-ranking-sub" style="color:{style['text']};opacity:0.92;">{escape(str(item.get('representative_stocks') or '-'))}</div>
                        </div>
                        """
                    ),
                    unsafe_allow_html=True,
                )
