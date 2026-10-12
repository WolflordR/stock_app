"""Backfill official MOPS quarterly income statements; safe to rerun."""
from __future__ import annotations

import argparse
import json

from modules.data_sources.financial_trends import refresh_financial_history


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quarters", type=int, default=7)
    parser.add_argument("--max-requests", type=int, default=None)
    args = parser.parse_args()
    result = refresh_financial_history(lookback_quarters=args.quarters, max_requests=args.max_requests)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
