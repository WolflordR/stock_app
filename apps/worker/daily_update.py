from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from typing import Any

from apps.api.main import build_dashboard_overview_payload
from apps.worker.backup_databases import backup_databases
from apps.worker.runner import WorkerStep, run_worker_steps
from apps.worker.update_price_cache import update_stocks
from modules.data_sources.stock_db import get_securities_in_range
from modules.data_sources.chip_trends import refresh_margin_day, refresh_tdcc
from modules.ownership_research.data import backfill_prices, sync_ownership_metadata
from modules.ownership_research.official_evidence import fetch_action_month
from modules.data_sources.market_limits import refresh_market_limits
from modules.data_sources.market_limit_stocks import refresh_market_limit_details
from modules.data_sources.market_turnover import refresh_turnover_recent
from modules.data_sources.revenue_data import backfill_recent_monthly_revenue, refresh_monthly_revenue_snapshot
from modules.data_sources.financial_eps import refresh_eps
from modules.data_sources.financial_trends import refresh_financial_history
from modules.data_sources.stock_db import refresh_stock_db
from modules.etf.active_etf_watch import refresh_latest_active_etf_snapshots
from modules.industry.classification_refresh import refresh_company_links_db
from modules.industry.electronics_universe import sync_electronics_universe
from modules.industry.sector_metrics import refresh_official_electronics_prices, refresh_sector_metrics
from modules.industry.fine_classification import sync_fine_classification
from modules.industry.classification_v4 import refresh_mops_business, sync_classification_v4
from modules.industry.official_company_evidence import refresh_company_evidence
from modules.industry.rotation_v3 import refresh_benchmarks, refresh_institutional, refresh_rotation
from modules.market_map.market_map_db import refresh_market_map_db
from services.dashboard_signals import refresh_signals
from services.events.company_events import refresh_events


def _dry_run_payload(enabled_steps: list[str]) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "enabled_steps": enabled_steps,
        "dashboard": build_dashboard_overview_payload()["summary"],
    }


def _refresh_revenue_with_history() -> dict[str, int]:
    latest = refresh_monthly_revenue_snapshot()
    return {"rows": len(latest), "history_rows": backfill_recent_monthly_revenue()}


def build_daily_steps(args: argparse.Namespace) -> list[WorkerStep]:
    price_stock_ids = _resolve_price_stock_ids(args)
    steps = [
        WorkerStep("dashboard_status", build_dashboard_overview_payload),
        WorkerStep("refresh_stock_master", refresh_stock_db, enabled=args.refresh_stock_master),
        WorkerStep("sync_electronic_universe", sync_electronics_universe, enabled=not args.skip_electronic_universe),
        WorkerStep("sync_fine_classification", sync_fine_classification, enabled=not args.skip_electronic_universe),
        WorkerStep("refresh_official_company_evidence", refresh_company_evidence, enabled=not args.skip_electronic_universe),
        WorkerStep("refresh_mops_business", refresh_mops_business, enabled=not args.skip_electronic_universe),
        WorkerStep("sync_classification_v4", sync_classification_v4, enabled=not args.skip_electronic_universe),
        WorkerStep("refresh_revenue", _refresh_revenue_with_history, enabled=args.refresh_revenue),
        WorkerStep("refresh_company_links", refresh_company_links_db, enabled=args.refresh_company_links),
        WorkerStep("refresh_market_map", refresh_market_map_db, enabled=args.refresh_market_map),
        WorkerStep(
            "update_price_cache",
            lambda: update_stocks(price_stock_ids, days=args.price_days, force=args.price_force),
            enabled=bool(price_stock_ids),
        ),
        WorkerStep("refresh_official_electronics_prices", refresh_official_electronics_prices, enabled=not args.skip_sector_metrics),
        WorkerStep("refresh_sector_metrics", refresh_sector_metrics, enabled=not args.skip_sector_metrics),
        WorkerStep("refresh_rotation_benchmarks", refresh_benchmarks, enabled=not args.skip_sector_metrics),
        # Cached dates are cheap; retry a rolling window so a missed trading day
        # (for example, immediately after deployment or a source outage) is recovered.
        WorkerStep("refresh_rotation_institutional", lambda: refresh_institutional(trade_days=10), enabled=not args.skip_sector_metrics),
        WorkerStep("refresh_rotation_v3", refresh_rotation, enabled=not args.skip_sector_metrics),
        WorkerStep("refresh_active_etf", refresh_latest_active_etf_snapshots, enabled=not args.skip_active_etf),
        WorkerStep("refresh_company_events", refresh_events),
        WorkerStep("refresh_dashboard_signals", refresh_signals),
        WorkerStep("refresh_eps", refresh_eps),
        WorkerStep("refresh_financial_history", lambda: refresh_financial_history(max_requests=4)),
        WorkerStep("refresh_margin_short", lambda: [refresh_margin_day(date.today() - timedelta(days=offset)) for offset in range(6, -1, -1) if (date.today() - timedelta(days=offset)).weekday() < 5], enabled=not args.skip_chip_trends),
        WorkerStep("refresh_tdcc_ownership", refresh_tdcc, enabled=not args.skip_chip_trends),
        WorkerStep("sync_ownership_research_metadata", sync_ownership_metadata, enabled=not args.skip_chip_trends),
        WorkerStep("refresh_market_limits", refresh_market_limits, enabled=not args.skip_chip_trends),
        WorkerStep("refresh_market_limit_details", refresh_market_limit_details, enabled=not args.skip_chip_trends),
        WorkerStep("refresh_market_turnover", refresh_turnover_recent, enabled=not args.skip_chip_trends),
        WorkerStep("refresh_ownership_research_prices", lambda: backfill_prices(date.today() - timedelta(days=7), date.today(), max_days=8, delay_seconds=0.25), enabled=not args.skip_chip_trends),
        WorkerStep("refresh_ownership_research_actions", lambda: fetch_action_month(date.today()), enabled=not args.skip_chip_trends),
        WorkerStep("backup", lambda: backup_databases(label="daily")),
    ]
    if args.dry_run:
        return [WorkerStep("dry_run", lambda: _dry_run_payload([step.name for step in steps if step.enabled]))]
    return steps


def _resolve_price_stock_ids(args: argparse.Namespace) -> list[str]:
    if args.price_all:
        return [item["yfinance_symbol"] for item in get_securities_in_range("0000", "9999")]
    return list(args.price_stock)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the NAS-friendly Trade daily data workflow.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without changing data.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop after the first failed step.")
    parser.add_argument("--refresh-stock-master", action="store_true", help="Refresh TWSE/TPEx stock master data.")
    parser.add_argument("--refresh-revenue", action="store_true", help="Refresh monthly revenue snapshot.")
    parser.add_argument("--refresh-company-links", action="store_true", help="Refresh company links taxonomy DB.")
    parser.add_argument("--refresh-market-map", action="store_true", help="Refresh market map DB.")
    parser.add_argument("--skip-electronic-universe", action="store_true", help="Skip official TWSE/TPEx electronics sync.")
    parser.add_argument("--skip-sector-metrics", action="store_true", help="Skip rotation metrics from local price cache.")
    parser.add_argument("--skip-active-etf", action="store_true", help="Skip latest active ETF snapshots.")
    parser.add_argument("--skip-chip-trends", action="store_true", help="Skip official TWSE/TPEx margin and TDCC ownership snapshots.")
    parser.add_argument("--price-stock", action="append", default=[], help="Update price cache for a stock code or symbol. Repeatable.")
    parser.add_argument("--price-all", action="store_true", help="Update price cache for all stocks in the local stock master.")
    parser.add_argument("--price-days", type=int, default=180, help="History window for price cache updates.")
    parser.add_argument("--price-force", action="store_true", help="Clear price cache metadata before fetching selected stocks.")
    args = parser.parse_args()

    result = run_worker_steps(
        "daily_update",
        build_daily_steps(args),
        continue_on_error=not args.stop_on_error,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
