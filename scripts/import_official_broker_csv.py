#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.data_sources.official_broker_import import import_official_broker_csv


def main():
    parser = argparse.ArgumentParser(description="匯入證交所 / 櫃買中心官方券商分點 CSV。")
    parser.add_argument("csv_path", help="官方下載的券商分點 CSV 路徑")
    parser.add_argument("--market", default="TWSE", help="市場別：TWSE 或 TPEX")
    parser.add_argument("--trade-date", default=None, help="交易日，格式 YYYY-MM-DD；若 CSV 本身沒有則必填")
    parser.add_argument("--stock-code", default=None, help="股票代號；若 CSV 本身沒有則必填")
    parser.add_argument("--stock-name", default=None, help="股票名稱；若 CSV 本身沒有可選填")
    parser.add_argument("--source", default="TWSE_CSV_MANUAL", help="資料來源標記")
    args = parser.parse_args()

    result = import_official_broker_csv(
        Path(args.csv_path),
        market=args.market,
        trade_date=args.trade_date,
        stock_code=args.stock_code,
        stock_name=args.stock_name,
        source=args.source,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
