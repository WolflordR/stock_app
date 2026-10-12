"""Small, explicit data jobs for the ownership research store."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from modules.core.project_paths import PROJECT_ROOT
from modules.ownership_research.audit import anomalous_reports, anomaly_summary, tier16_reconciliation_audit
from modules.ownership_research.backfill import backfill_tdcc_archives
from modules.ownership_research.data import backfill_prices, quality_report, sync_ownership_metadata
from modules.ownership_research.official_evidence import fetch_action_month, refresh_company_lifecycle


def main() -> None:
    parser = argparse.ArgumentParser(description="Ownership research data collection and quality checks")
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("sync-ownership", help="Index existing TDCC tiers and their provenance")
    sub.add_parser("quality", help="Report coverage and data-quality gates")
    audit = sub.add_parser("audit-anomalies", help="Export read-only TDCC reconciliation audit")
    audit.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "ownership_research" / "tdcc_anomalies.csv")
    tier16 = sub.add_parser("audit-tier16", help="Explain old tier-16 adjustment false positives without editing raw records")
    tier16.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "ownership_research" / "tier16_reconciliation_audit.csv")
    actions = sub.add_parser("fetch-actions", help="Fetch one calendar month of official action reference prices")
    actions.add_argument("--month", required=True, type=date.fromisoformat, help="Any YYYY-MM-DD in the month")
    lifecycle = sub.add_parser("refresh-lifecycle", help="Index official current companies and delisting registers")
    lifecycle.add_argument("--first-year", type=int, default=2016)
    prices = sub.add_parser("backfill-prices", help="Fetch up to 31 calendar days of official prices")
    prices.add_argument("--start", required=True, type=date.fromisoformat)
    prices.add_argument("--end", required=True, type=date.fromisoformat)
    prices.add_argument("--market", choices=("TWSE", "TPEx", "both"), default="both")
    tdcc = sub.add_parser("backfill-tdcc-archives", help="Resume a bounded import of dated TDCC mirror snapshots")
    tdcc.add_argument("--first-year", type=int, default=2020)
    tdcc.add_argument("--last-year", type=int, default=date.today().year)
    tdcc.add_argument("--max-weeks", type=int, default=20)
    args = parser.parse_args()
    if args.action == "sync-ownership":
        result = sync_ownership_metadata()
    elif args.action == "quality":
        result = quality_report()
    elif args.action == "audit-anomalies":
        frame = anomalous_reports()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False, encoding="utf-8-sig")
        result = {"output": str(args.output), **anomaly_summary(frame)}
    elif args.action == "audit-tier16":
        frame = tier16_reconciliation_audit()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False, encoding="utf-8-sig")
        result = {"output": str(args.output), "legacy_excess_reports": len(frame),
                  "corrected_reconciled": int(frame["corrected_residual_shares"].eq(0).sum()) if len(frame) else 0}
    elif args.action == "fetch-actions":
        result = fetch_action_month(args.month)
    elif args.action == "refresh-lifecycle":
        result = refresh_company_lifecycle(first_year=args.first_year)
    elif args.action == "backfill-tdcc-archives":
        result = backfill_tdcc_archives(first_year=args.first_year,
                                        last_year=args.last_year, max_weeks=args.max_weeks)
    else:
        markets = ("TWSE", "TPEx") if args.market == "both" else (args.market,)
        result = backfill_prices(args.start, args.end, markets=markets)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
