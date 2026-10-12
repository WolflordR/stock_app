from __future__ import annotations

import argparse
import json

from modules.industry.sector_metrics import backfill_sector_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill electronics rotation metrics from local OHLCV history")
    parser.add_argument("--trade-days", type=int, default=20)
    args = parser.parse_args()
    result = backfill_sector_metrics(trade_days=args.trade_days)
    print(json.dumps({"days": len(result), "first": result[0]["trade_date"] if result else None, "last": result[-1]["trade_date"] if result else None, "rows": sum(item["rows"] for item in result)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
