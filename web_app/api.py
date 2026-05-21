from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from modules.etf.active_etf_history_store import load_etf_change_snapshot_items
from modules.etf.active_etf_watch import build_active_etf_detail_bundle
from modules.etf.active_etf_watch import build_active_etf_overview_bundle
from modules.core.persistent_cache import load_or_compute_persistent_cache


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


app = FastAPI(title="Trade Lab Web App Beta")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _read_html(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def _records(df: pd.DataFrame):
    if df is None or getattr(df, "empty", True):
        return []
    return df.fillna("").to_dict(orient="records")


def _cache_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load_active_etf_overview_cached(top_n: int):
    cache_version = "web-beta-etf-overview-v1"
    return load_or_compute_persistent_cache(
        "web_active_etf_overview",
        (cache_version, _cache_date(), int(top_n)),
        1800,
        lambda: build_active_etf_overview_bundle(top_n=top_n),
    )


def _load_active_etf_detail_cached(code: str):
    normalized_code = str(code).strip().upper()
    cache_version = "web-beta-etf-detail-v1"
    return load_or_compute_persistent_cache(
        "web_active_etf_detail",
        (cache_version, _cache_date(), normalized_code),
        1800,
        lambda: build_active_etf_detail_bundle(normalized_code),
    )


@app.get("/api/health")
def health():
    return {"ok": True, "app": "trade-web-beta"}


@app.get("/", response_class=HTMLResponse)
def index():
    return _read_html("index.html")


@app.get("/api/active-etf/overview")
def active_etf_overview(top_n: int = 20):
    bundle = _load_active_etf_overview_cached(top_n=top_n)
    if not bundle:
        raise HTTPException(status_code=404, detail="No ETF overview data")
    return {
        "updated_at": bundle.get("updated_at"),
        "latest_market_date": bundle.get("latest_market_date"),
        "largest_etf": bundle.get("largest_etf"),
        "busiest_etf": bundle.get("busiest_etf"),
        "strongest_today_etf": bundle.get("strongest_today_etf"),
        "items": _records(bundle["raw_df"]),
    }


@app.get("/api/active-etf/{code}")
def active_etf_detail(code: str):
    bundle = _load_active_etf_detail_cached(code)
    if not bundle:
        raise HTTPException(status_code=404, detail="ETF detail not found")
    return {
        "code": bundle.get("code"),
        "name": bundle.get("name"),
        "updated_at": bundle.get("updated_at"),
        "overview": bundle.get("overview"),
        "change_summary": bundle.get("change_summary"),
        "history_summary": _records(bundle.get("history_summary_df")),
        "holdings": _records(bundle.get("raw_holdings_df")),
        "changes": _records(bundle.get("raw_changes_df")),
        "industry_breakdown": _records(bundle.get("industry_breakdown_df")),
    }


@app.get("/api/active-etf/{code}/changes/{snapshot_date}")
def active_etf_snapshot_changes(code: str, snapshot_date: str):
    items_df = load_etf_change_snapshot_items(str(code).strip().upper(), str(snapshot_date).strip())
    if items_df is None or items_df.empty:
        raise HTTPException(status_code=404, detail="Snapshot changes not found")
    return {
        "code": str(code).strip().upper(),
        "snapshot_date": str(snapshot_date).strip(),
        "items": _records(items_df),
    }
