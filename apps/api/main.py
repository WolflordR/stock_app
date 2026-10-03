from __future__ import annotations

from datetime import date, timedelta
from typing import Any

try:
    from fastapi import FastAPI, Query
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - lets this skeleton compile before deps are installed.
    FastAPI = None

from apps.api.read_models import (
    build_backtest_config_payload,
    build_data_sources_overview,
    build_stock_overview,
    get_price_cache_overview,
    list_active_etf_changes,
    list_active_etf_snapshots,
    list_broker_branches,
    list_market_map_groups,
    list_market_map_topic_members,
    list_market_map_topics,
    list_research_companies,
    list_revenue_momentum,
    list_strong_stocks,
    list_stock_price_history,
    list_us_market_calendar,
)
from modules.core.project_paths import (
    BACKUPS_DIR,
    CACHE_DIR,
    DATA_DIR,
    DB_DIR,
    LOGS_DIR,
    PROCESSED_DATA_DIR,
    PROJECT_ROOT,
    RAW_DATA_DIR,
    data_path,
    db_path,
)
from modules.core.settings import SETTINGS
from modules.core.job_store import SQLiteJobStore
from modules.backtest.backtest_models import BacktestScanRequest
from modules.backtest.backtest_service import validate_backtest_request
from modules.news.news_analysis import build_news_analysis_bundle
from modules.data_sources.official_broker_import import get_official_broker_db_overview
from modules.data_sources.stock_db import find_security, get_securities_in_range, get_stock_db_status
from modules.market_map.market_map_db import get_market_map_status
from modules.core.job_managers import BackgroundDataJobManager, BacktestJobManager
from apps.worker.update_price_cache import update_stocks
from packages.trade_core.data_files import ALL_DB_FILES, DATA_CONFIG_FILES


if FastAPI is None:
    app = None
else:
    app = FastAPI(title="Trade API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(SETTINGS.api_cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api_job_store = SQLiteJobStore("api_jobs.db", stale_after_seconds=1800)
    backtest_jobs = BacktestJobManager(job_store=api_job_store)
    data_jobs = BackgroundDataJobManager(job_store=api_job_store)


def _json_safe_response(value: Any) -> Any:
    if isinstance(value, (date,)):
        return value.isoformat()
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict("records")
        except TypeError:
            return value.to_dict()
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {key: _json_safe_response(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_response(item) for item in value]
    return value


def build_runtime_paths_payload() -> dict[str, str]:
    return {
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(DATA_DIR),
        "raw_data_dir": str(RAW_DATA_DIR),
        "processed_data_dir": str(PROCESSED_DATA_DIR),
        "db_dir": str(DB_DIR),
        "cache_dir": str(CACHE_DIR),
        "logs_dir": str(LOGS_DIR),
        "backups_dir": str(BACKUPS_DIR),
    }


def build_data_status_payload() -> dict[str, object]:
    return {
        "paths": build_runtime_paths_payload(),
        "db_files": [
            {"name": name, "path": str(db_path(name)), "exists": db_path(name).exists()}
            for name in ALL_DB_FILES
        ],
        "data_files": [
            {"name": name, "path": str(data_path(name)), "exists": data_path(name).exists()}
            for name in DATA_CONFIG_FILES
        ],
    }


def _safe_section(name: str, builder) -> dict[str, object]:
    try:
        return {"name": name, "ok": True, "data": builder()}
    except Exception as exc:
        return {"name": name, "ok": False, "error": str(exc), "data": None}


def build_dashboard_overview_payload() -> dict[str, object]:
    data_status = build_data_status_payload()
    db_files = data_status["db_files"]
    data_files = data_status["data_files"]
    ready_files = sum(1 for item in [*db_files, *data_files] if item["exists"])

    return {
        "summary": {
            "architecture": "web-api-worker",
            "frontend": "Vite React",
            "backend": "FastAPI",
            "ready_file_count": ready_files,
            "total_file_count": len(db_files) + len(data_files),
        },
        "runtime": data_status,
        "sections": {
            "stocks": _safe_section("stocks", get_stock_db_status),
            "market_map": _safe_section("market_map", get_market_map_status),
            "broker": _safe_section("broker", get_official_broker_db_overview),
        },
    }


if app is not None:
    class BacktestStartRequest(BaseModel):
        start_num: int = Field(default=0, ge=0, le=9999)
        end_num: int = Field(default=9999, ge=0, le=9999)
        mode: str = "即時選股"
        selected_strategies: list[str] = Field(default_factory=lambda: ["強勢股回檔量縮止跌"])
        selected_sell_strategies: list[str] = Field(default_factory=list)
        start_date: date | None = None
        end_date: date | None = None
        request_delay_sec: float = Field(default=0.02, ge=0, le=1)
        range_lookback_days: int = Field(default=60, ge=5, le=260)
        range_max_width_pct: float = Field(default=65.0, ge=1, le=200)
        range_volume_ratio: float = Field(default=1.3, ge=0.1, le=10)
        range_min_price_gain_pct: float = Field(default=0.0, ge=-100, le=300)
        range_max_price_gain_pct: float = Field(default=18.0, ge=-100, le=500)
        range_volume_sustain_days: int = Field(default=3, ge=1, le=30)
        initial_capital: int = Field(default=100000, ge=1000, le=1000000000)
        trading_cost_pct: float = Field(default=0.7, ge=0, le=10)
        initial_stop_loss_pct: float = Field(default=5.0, ge=0.1, le=80)
        trailing_stop_activation_pct: float = Field(default=8.0, ge=0.1, le=200)
        trailing_stop_drawdown_pct: float = Field(default=8.0, ge=0.1, le=80)
        pullback_strong_lookback_days: int = Field(default=20, ge=5, le=260)
        pullback_min_pullback_pct: float = Field(default=10.0, ge=0.1, le=90)
        pullback_base_hold_days: int = Field(default=3, ge=1, le=30)
        pullback_low_price_volume_price_threshold: float = Field(default=500.0, ge=0, le=10000)
        pullback_low_price_min_volume_lots: float = Field(default=700.0, ge=0, le=1000000)
        pullback_technology_only: bool = True
        vcp_lookback_days: int = Field(default=60, ge=20, le=260)
        vcp_min_uptrend_pct: float = Field(default=12.0, ge=0.1, le=300)
        vcp_breakout_volume_ratio: float = Field(default=1.0, ge=0.1, le=20)
        vcp_near_pivot_tolerance_pct: float = Field(default=12.0, ge=0.1, le=100)
        vcp_max_consolidation_depth_pct: float = Field(default=45.0, ge=1, le=100)
        high_price_pullback_lookback_days: int = Field(default=20, ge=5, le=260)
        high_price_pullback_market_cap_rank_limit: int = Field(default=50, ge=1, le=500)
        high_price_pullback_min_drop_pct: float = Field(default=15.0, ge=0.1, le=90)
        breakout_lookback_days: int = Field(default=252, ge=30, le=1260)
        breakout_distance_pct: float = Field(default=10.0, ge=0.1, le=50)
        breakout_trend_lookback_days: int = Field(default=20, ge=3, le=120)
        breakout_volume_short_window: int = Field(default=5, ge=1, le=60)
        breakout_volume_long_window: int = Field(default=20, ge=2, le=120)
        bowl_volume_lookback_days: int = Field(default=120, ge=60, le=260)
        bowl_volume_min_drawdown_pct: float = Field(default=20.0, ge=1, le=80)
        bowl_volume_volume_lookback_days: int = Field(default=20, ge=2, le=120)
        bowl_volume_signal_window_days: int = Field(default=3, ge=1, le=10)
        bowl_volume_multiplier: float = Field(default=2.0, ge=0.1, le=20)
        bowl_volume_trend_lookback_days: int = Field(default=10, ge=3, le=120)

        def to_scan_request(self) -> BacktestScanRequest:
            today = date.today()
            mode = self.mode if self.mode in {"歷史回測", "即時選股"} else "即時選股"
            return BacktestScanRequest(
                start_num=self.start_num,
                end_num=self.end_num,
                selected_strategies=self.selected_strategies,
                mode=mode,
                start_date=self.start_date or (today - timedelta(days=90) if mode == "歷史回測" else None),
                end_date=self.end_date or (today if mode == "歷史回測" else None),
                selected_sell_strategies=self.selected_sell_strategies,
                request_delay_sec=self.request_delay_sec,
                range_lookback_days=self.range_lookback_days,
                range_max_width_pct=self.range_max_width_pct,
                range_volume_ratio=self.range_volume_ratio,
                range_min_price_gain_pct=self.range_min_price_gain_pct,
                range_max_price_gain_pct=self.range_max_price_gain_pct,
                range_volume_sustain_days=self.range_volume_sustain_days,
                initial_capital=self.initial_capital,
                trading_cost_pct=self.trading_cost_pct,
                initial_stop_loss_pct=self.initial_stop_loss_pct,
                trailing_stop_activation_pct=self.trailing_stop_activation_pct,
                trailing_stop_drawdown_pct=self.trailing_stop_drawdown_pct,
                pullback_strong_lookback_days=self.pullback_strong_lookback_days,
                pullback_min_pullback_pct=self.pullback_min_pullback_pct,
                pullback_base_hold_days=self.pullback_base_hold_days,
                pullback_low_price_volume_price_threshold=self.pullback_low_price_volume_price_threshold,
                pullback_low_price_min_volume_lots=self.pullback_low_price_min_volume_lots,
                pullback_technology_only=self.pullback_technology_only,
                vcp_lookback_days=self.vcp_lookback_days,
                vcp_min_uptrend_pct=self.vcp_min_uptrend_pct,
                vcp_breakout_volume_ratio=self.vcp_breakout_volume_ratio,
                vcp_near_pivot_tolerance_pct=self.vcp_near_pivot_tolerance_pct,
                vcp_max_consolidation_depth_pct=self.vcp_max_consolidation_depth_pct,
                high_price_pullback_lookback_days=self.high_price_pullback_lookback_days,
                high_price_pullback_market_cap_rank_limit=self.high_price_pullback_market_cap_rank_limit,
                high_price_pullback_min_drop_pct=self.high_price_pullback_min_drop_pct,
                breakout_lookback_days=self.breakout_lookback_days,
                breakout_distance_pct=self.breakout_distance_pct,
                breakout_trend_lookback_days=self.breakout_trend_lookback_days,
                breakout_volume_short_window=self.breakout_volume_short_window,
                breakout_volume_long_window=self.breakout_volume_long_window,
                bowl_volume_lookback_days=self.bowl_volume_lookback_days,
                bowl_volume_min_drawdown_pct=self.bowl_volume_min_drawdown_pct,
                bowl_volume_volume_lookback_days=self.bowl_volume_volume_lookback_days,
                bowl_volume_signal_window_days=self.bowl_volume_signal_window_days,
                bowl_volume_multiplier=self.bowl_volume_multiplier,
                bowl_volume_trend_lookback_days=self.bowl_volume_trend_lookback_days,
            )

    class NewsStartRequest(BaseModel):
        anchor_date: date | None = None
        industry_count: int = Field(default=5, ge=1, le=10)
        headlines_per_industry: int = Field(default=4, ge=1, le=8)
        us_news_items: int = Field(default=8, ge=1, le=20)

    class PriceCacheUpdateRequest(BaseModel):
        days: int = Field(default=1825, ge=30, le=2200)
        force: bool = True

    class PriceCacheJobRequest(BaseModel):
        scope: str = Field(default="all")
        start_code: int | None = Field(default=None, ge=0, le=9999)
        end_code: int | None = Field(default=None, ge=0, le=9999)
        stock_ids: list[str] = Field(default_factory=list)
        days: int = Field(default=365, ge=30, le=2200)
        force: bool = False

        def resolve_stock_ids(self) -> list[str]:
            normalized_scope = self.scope.strip().lower()
            if normalized_scope == "stocks":
                return [str(item).strip() for item in self.stock_ids if str(item).strip()]
            if normalized_scope == "range":
                start_code = self.start_code if self.start_code is not None else 1101
                end_code = self.end_code if self.end_code is not None else 9999
                return [item["yfinance_symbol"] for item in get_securities_in_range(start_code, end_code)]
            return [item["yfinance_symbol"] for item in get_securities_in_range(0, 9999)]

    def _start_web_bootstrap_price_job() -> dict[str, object]:
        if not SETTINGS.web_bootstrap_price_enabled:
            return {"ok": True, "started": False, "reason": "web bootstrap price update is disabled", "job": None}
        stock_ids = [item["yfinance_symbol"] for item in get_securities_in_range(0, 9999)]
        if not stock_ids:
            return {"ok": False, "started": False, "error": "No stocks are available in the local stock master.", "job": None}

        days = max(30, min(int(SETTINGS.web_bootstrap_price_days), 2200))
        force = bool(SETTINGS.web_bootstrap_price_force)
        cache_key = ("web_bootstrap", date.today().isoformat(), "all", len(stock_ids), days, force)
        job_id = data_jobs.get_or_create_job(
            "price_cache_update",
            cache_key,
            update_stocks,
            args=(stock_ids,),
            kwargs={"days": days, "force": force},
            pending_message=f"開啟網站後自動暖機價格資料，共 {len(stock_ids)} 檔",
            running_message=f"正在背景更新價格資料，共 {len(stock_ids)} 檔",
            completed_message=lambda result=None, error=None: (
                f"背景資料更新完成：成功 {result.get('ok_count', 0)} 檔，失敗 {result.get('failed_count', 0)} 檔"
                if isinstance(result, dict)
                else "背景資料更新完成"
            ),
            failed_message="背景資料更新失敗",
        )
        job = data_jobs.get_job(job_id, include_result=False)
        return {
            "ok": True,
            "started": job.get("status") in {"queued", "running"} if job else True,
            "job_id": job_id,
            "stock_count": len(stock_ids),
            "days": days,
            "force": force,
            "job": _json_safe_response(job),
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runtime/paths")
    def runtime_paths() -> dict[str, str]:
        return build_runtime_paths_payload()

    @app.get("/api/runtime/data-status")
    def data_status() -> dict[str, object]:
        return build_data_status_payload()

    @app.post("/api/bootstrap/jobs")
    def start_bootstrap_jobs() -> dict[str, object]:
        price_job = _start_web_bootstrap_price_job()
        return {"ok": bool(price_job.get("ok")), "price_cache": price_job}

    @app.get("/api/data/sources")
    def data_sources() -> dict[str, object]:
        return build_data_sources_overview()

    @app.get("/api/stocks/status")
    def stock_status() -> dict[str, object]:
        return get_stock_db_status()

    @app.get("/api/price-cache/status")
    def price_cache_status() -> dict[str, object]:
        return get_price_cache_overview()

    @app.get("/api/stocks/strong")
    def strong_stocks(days: int = Query(default=7, ge=2, le=365), limit: int = Query(default=10, ge=1, le=50)) -> dict[str, object]:
        return list_strong_stocks(days=days, limit=limit)

    @app.post("/api/price-cache/jobs")
    def start_price_cache_job(request_body: PriceCacheJobRequest) -> dict[str, object]:
        stock_ids = request_body.resolve_stock_ids()
        if not stock_ids:
            return {"ok": False, "error": "No stocks matched the request."}
        cache_key = (
            request_body.scope,
            request_body.start_code,
            request_body.end_code,
            len(stock_ids),
            request_body.days,
            request_body.force,
        )
        job_id = data_jobs.start_job(
            "price_cache_update",
            cache_key,
            update_stocks,
            args=(stock_ids,),
            kwargs={"days": request_body.days, "force": request_body.force},
            pending_message=f"價格更新排隊中，共 {len(stock_ids)} 檔",
            running_message=f"開始更新價格快取，共 {len(stock_ids)} 檔",
            completed_message=lambda result=None, error=None: (
                f"價格更新完成：成功 {result.get('ok_count', 0)} 檔，失敗 {result.get('failed_count', 0)} 檔"
                if isinstance(result, dict)
                else "價格更新完成"
            ),
            failed_message="價格更新失敗",
        )
        return {"ok": True, "job_id": job_id, "stock_count": len(stock_ids)}

    @app.get("/api/price-cache/jobs/latest")
    def get_latest_price_cache_job() -> dict[str, object]:
        job_id = api_job_store.find_latest_job_id("price_cache_update")
        if not job_id:
            return {"ok": True, "job": None}
        job = data_jobs.get_job(job_id, include_result=False)
        return {"ok": True, "job": _json_safe_response(job)}

    @app.get("/api/price-cache/jobs/{job_id}")
    def get_price_cache_job(job_id: str) -> dict[str, object]:
        job = data_jobs.get_job(job_id, include_result=False)
        if not job:
            return {"ok": False, "error": "Job not found"}
        return {"ok": True, "job": _json_safe_response(job)}

    @app.get("/api/stocks/{stock_id}")
    def stock_detail(stock_id: str) -> dict[str, object]:
        return build_stock_overview(stock_id)

    @app.get("/api/stocks/{stock_id}/overview")
    def stock_overview(stock_id: str) -> dict[str, object]:
        return build_stock_overview(stock_id)

    @app.get("/api/stocks/{stock_id}/quotes")
    def stock_quotes(stock_id: str, limit: int = Query(default=1260, ge=1, le=1500)) -> dict[str, object]:
        security = find_security(stock_id)
        if not security:
            return {"stock_id": stock_id, "found": False, "quotes": []}
        return {
            "stock_id": stock_id,
            "found": True,
            "symbol": security["yfinance_symbol"],
            "quotes": list_stock_price_history(security["yfinance_symbol"], limit=limit),
        }

    @app.post("/api/stocks/{stock_id}/price-cache")
    def update_stock_price_cache(stock_id: str, request_body: PriceCacheUpdateRequest) -> dict[str, object]:
        return update_stocks([stock_id], days=request_body.days, force=request_body.force)

    @app.get("/api/market-map/status")
    def market_map_status() -> dict[str, object]:
        return get_market_map_status()

    @app.get("/api/market-map/groups")
    def market_map_groups() -> list[dict[str, object]]:
        return list_market_map_groups()

    @app.get("/api/market-map/topics")
    def market_map_topics(group_name: str | None = Query(default=None)) -> list[dict[str, object]]:
        return list_market_map_topics(group_name)

    @app.get("/api/market-map/topics/{topic_name:path}/members")
    def market_map_topic_members(topic_name: str, limit: int = Query(default=80, ge=1, le=300)) -> list[dict[str, object]]:
        return list_market_map_topic_members(topic_name, limit=limit)

    @app.get("/api/broker/overview")
    def broker_overview() -> dict[str, object]:
        return get_official_broker_db_overview()

    @app.get("/api/broker/branches")
    def broker_branches(
        search_text: str | None = Query(default=None),
        limit: int = Query(default=80, ge=1, le=300),
    ) -> list[dict[str, object]]:
        return list_broker_branches(search_text=search_text, limit=limit)

    @app.get("/api/revenue/momentum")
    def revenue_momentum(limit: int = Query(default=30, ge=1, le=100)) -> dict[str, object]:
        return list_revenue_momentum(limit=limit)

    @app.get("/api/us-market/calendar")
    def us_market_calendar(
        start_date: str | None = Query(default=None),
        end_date: str | None = Query(default=None),
        importance: str | None = Query(default="all"),
    ) -> dict[str, object]:
        return list_us_market_calendar(start_date=start_date, end_date=end_date, importance=importance)

    @app.get("/api/etf/active/snapshots")
    def active_etf_snapshots(
        limit: int = Query(default=500, ge=1, le=1000),
        days: int = Query(default=30, ge=1, le=120),
    ) -> dict[str, object]:
        return list_active_etf_snapshots(limit=limit, days=days)

    @app.get("/api/etf/active/{etf_code}/changes")
    def active_etf_changes(
        etf_code: str,
        snapshot_date: str | None = Query(default=None),
        limit: int = Query(default=120, ge=1, le=500),
    ) -> dict[str, object]:
        return list_active_etf_changes(etf_code, snapshot_date=snapshot_date, limit=limit)

    @app.get("/api/backtest/config")
    def backtest_config() -> dict[str, object]:
        return build_backtest_config_payload()

    @app.post("/api/backtest/jobs")
    def start_backtest_job(request_body: BacktestStartRequest) -> dict[str, object]:
        request = request_body.to_scan_request()
        validation_error = validate_backtest_request(request)
        if validation_error:
            return {"ok": False, "error": validation_error}
        job_id = backtest_jobs.start_job(request)
        return {"ok": True, "job_id": job_id}

    @app.get("/api/backtest/jobs/{job_id}")
    def get_backtest_job(job_id: str) -> dict[str, object]:
        job = backtest_jobs.get_job(job_id)
        if not job:
            return {"ok": False, "error": "Job not found"}
        payload = _json_safe_response(job)
        result = payload.get("result")
        if isinstance(result, list):
            payload["result_count"] = len(result)
            payload["result_preview"] = result[:20]
            payload.pop("result", None)
        elif isinstance(result, dict):
            payload["result_count"] = len(result)
            payload["result_preview"] = result
            payload.pop("result", None)
        return {"ok": True, "job": payload}

    @app.post("/api/news/jobs")
    def start_news_job(request_body: NewsStartRequest) -> dict[str, object]:
        anchor_date = request_body.anchor_date or date.today()
        cache_key = (
            anchor_date.isoformat(),
            request_body.industry_count,
            request_body.headlines_per_industry,
            request_body.us_news_items,
        )
        job_id = data_jobs.get_or_create_job(
            "news_analysis",
            cache_key,
            build_news_analysis_bundle,
            args=(anchor_date,),
            kwargs={
                "industry_count": request_body.industry_count,
                "headlines_per_industry": request_body.headlines_per_industry,
                "us_news_items": request_body.us_news_items,
            },
            running_message="正在整理新聞分析",
            completed_message="新聞分析完成",
            failed_message="新聞分析失敗",
        )
        return {"ok": True, "job_id": job_id}

    @app.get("/api/news/jobs/{job_id}")
    def get_news_job(job_id: str) -> dict[str, object]:
        job = data_jobs.get_job(job_id, include_result=True)
        if not job:
            return {"ok": False, "error": "Job not found"}
        payload = _json_safe_response(job)
        result = payload.get("result")
        if isinstance(result, dict):
            payload["result_preview"] = {
                "daily_brief": result.get("daily_brief", [])[:5],
                "ai_summary_enabled": result.get("ai_summary_enabled"),
                "ai_model": result.get("ai_model"),
            }
            payload.pop("result", None)
        return {"ok": True, "job": payload}

    @app.get("/api/research/companies")
    def research_companies(
        search_text: str | None = Query(default=None),
        limit: int = Query(default=80, ge=1, le=300),
    ) -> dict[str, object]:
        return list_research_companies(search_text=search_text, limit=limit)

    @app.get("/api/dashboard/overview")
    def dashboard_overview() -> dict[str, object]:
        return build_dashboard_overview_payload()
