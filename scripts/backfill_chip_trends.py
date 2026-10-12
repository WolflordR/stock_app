"""Backfill official daily margin reports and capture the current TDCC weekly file."""
from __future__ import annotations

import argparse
import json
from datetime import date

from modules.data_sources.chip_trends import backfill_margin, backfill_tdcc_archive, refresh_tdcc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=370, help="Calendar days of TWSE/TPEx reports to backfill")
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--skip-margin", action="store_true")
    parser.add_argument("--skip-tdcc", action="store_true")
    parser.add_argument("--tdcc-archive-year", type=int, help="Import archived original TDCC weekly CSVs for this year")
    args = parser.parse_args()
    result = {}
    if not args.skip_margin:
        result["margin"] = backfill_margin(args.days, end=args.end)
    if not args.skip_tdcc:
        result["tdcc"] = refresh_tdcc()
    if args.tdcc_archive_year:
        result["tdcc_archive"] = backfill_tdcc_archive(year=args.tdcc_archive_year)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
