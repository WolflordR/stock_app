"""Bounded descriptive experiment; outputs carry provenance and limitations."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from modules.core.project_paths import PROJECT_ROOT
from modules.ownership_research.factors import FactorConfig
from modules.ownership_research.study import StudyConfig, run_study
from modules.ownership_research.data import now_iso


def _ints(text: str) -> tuple[int, ...]:
    return tuple(int(value.strip()) for value in text.split(",") if value.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Descriptive TDCC factor/price study, with formal-data gate")
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--factor", default="delta_1w_gt_1000")
    parser.add_argument("--thresholds", type=_ints, default=(400, 1000))
    parser.add_argument("--lookbacks", type=_ints, default=(1, 4, 8))
    parser.add_argument("--primary-threshold", type=int, default=1000)
    parser.add_argument("--small-holder-last-tier", type=int, default=3)
    parser.add_argument("--zscore-weeks", type=int, default=12)
    parser.add_argument("--min-gap-days", type=int, default=4)
    parser.add_argument("--max-gap-days", type=int, default=10)
    parser.add_argument("--horizons", type=_ints, default=(5, 10, 20, 40, 60))
    parser.add_argument("--delays", type=_ints, default=(3, 7, 14))
    parser.add_argument("--lead-lags", type=_ints, default=(0, 5, 10))
    parser.add_argument("--event-min", type=float, default=0.01)
    parser.add_argument("--quantiles", type=int, default=5)
    parser.add_argument("--max-entry-delay-sessions", type=int, default=2)
    parser.add_argument("--allow-overlap", action="store_true", help="Descriptive comparison only; repeated stock paths are dependent")
    parser.add_argument("--price-source", choices=("official_raw", "yahoo_cache"), default="yahoo_cache")
    parser.add_argument("--mode", choices=("exploratory", "formal"), default="exploratory")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "ownership_research" / "first_exploratory_study.json")
    args = parser.parse_args()
    factors = FactorConfig(thresholds_lots=args.thresholds, change_weeks=args.lookbacks,
                           primary_threshold_lots=args.primary_threshold,
                           small_holder_last_tier=args.small_holder_last_tier,
                           zscore_weeks=args.zscore_weeks, min_gap_days=args.min_gap_days,
                           max_gap_days=args.max_gap_days)
    study = StudyConfig(start=args.start, end=args.end, factor=args.factor, horizons=args.horizons,
                        delay_days=args.delays, lead_lag_sessions=args.lead_lags,
                        event_min=args.event_min, quantiles=args.quantiles,
                        price_source=args.price_source, mode=args.mode,
                        max_entry_delay_sessions=args.max_entry_delay_sessions,
                        nonoverlap=not args.allow_overlap)
    result = run_study(study, factor_config=factors)
    result["generated_at"] = now_iso()
    result["config"] = {"factor": args.factor, "thresholds_lots": args.thresholds,
                        "lookbacks_weeks": args.lookbacks, "primary_threshold_lots": args.primary_threshold,
                        "horizons_trading_days": args.horizons, "assumed_delay_calendar_days": args.delays,
                        "lead_lag_trading_days": args.lead_lags, "event_min_pp": args.event_min,
                        "price_source": args.price_source, "mode": args.mode}
    result["config"].update({"min_gap_days": args.min_gap_days, "max_gap_days": args.max_gap_days,
                             "max_entry_delay_sessions": args.max_entry_delay_sessions,
                             "nonoverlap_per_stock_horizon": not args.allow_overlap})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "mode": result["mode"], "status": result["status"],
                      "factor_rows": result.get("factor_rows", 0),
                      "sensitivity_event_rows": [item["event_rows"] for item in result.get("sensitivity", [])],
                      "reasons": result.get("reasons", [])}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
