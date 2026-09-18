from __future__ import annotations

import argparse
import json
from typing import Any

from apps.api.main import build_dashboard_overview_payload
from apps.worker.backup_databases import backup_databases
from apps.worker.runner import WorkerStep, run_worker_steps
from apps.worker.update_price_cache import update_stocks
from modules.data_sources.stock_db import get_securities_in_range
from modules.data_sources.revenue_data import refresh_monthly_revenue_snapshot
from modules.data_sources.stock_db import refresh_stock_db
from modules.industry.classification_refresh import refresh_company_links_db
from modules.market_map.market_map_db import refresh_market_map_db


def _dry_run_payload(enabled_steps: list[str]) -> dict[str, Any]:
    return {
        "mode": "dry-run",
        "enabled_steps": enabled_steps,
        "dashboard": build_dashboard_overview_payload()["summary"],
    }


def build_daily_steps(args: argparse.Namespace) -> list[WorkerStep]:
    enabled_steps = ["backup", "dashboard_status"]
    if args.refresh_stock_master:
        enabled_steps.append("refresh_stock_master")
    if args.refresh_revenue:
        enabled_steps.append("refresh_revenue")
    if args.refresh_company_links:
        enabled_steps.append("refresh_company_links")
    if args.refresh_market_map:
        enabled_steps.append("refresh_market_map")
    price_stock_ids = _resolve_price_stock_ids(args)
    if price_stock_ids:
        enabled_steps.append("update_price_cache")

    if args.dry_run:
        return [
            WorkerStep(
                "dry_run",
                lambda: _dry_run_payload(enabled_steps),
            )
        ]

    return [
        WorkerStep("backup", lambda: backup_databases(label="daily")),
        WorkerStep("dashboard_status", build_dashboard_overview_payload),
        WorkerStep("refresh_stock_master", refresh_stock_db, enabled=args.refresh_stock_master),
        WorkerStep("refresh_revenue", lambda: {"rows": len(refresh_monthly_revenue_snapshot())}, enabled=args.refresh_revenue),
        WorkerStep("refresh_company_links", refresh_company_links_db, enabled=args.refresh_company_links),
        WorkerStep("refresh_market_map", refresh_market_map_db, enabled=args.refresh_market_map),
        WorkerStep(
            "update_price_cache",
            lambda: update_stocks(price_stock_ids, days=args.price_days, force=args.price_force),
            enabled=bool(price_stock_ids),
        ),
    ]


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
