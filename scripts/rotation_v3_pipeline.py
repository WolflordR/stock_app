"""Manage the live fine-sector rotation database from the project root.

Usage: stock_env/bin/python -m scripts.rotation_v3_pipeline {migrate,sync,backfill,daily}
"""
from __future__ import annotations

import argparse
import json

from modules.industry.electronics_universe import sync_electronics_universe
from modules.industry.fine_classification import get_fine_coverage, init_fine_db, sync_fine_classification
from modules.industry.classification_v4 import init_classification_v4, refresh_mops_business, sync_classification_v4
from modules.industry.official_company_evidence import refresh_company_evidence
from modules.industry.rotation_v3 import (
    backfill_rotation, init_rotation_db, refresh_benchmarks,
    refresh_institutional, refresh_rotation,
)
from modules.industry.sector_metrics import refresh_official_electronics_prices


def main() -> int:
    parser=argparse.ArgumentParser(description='TWSE/TPEx fine-sector rotation pipeline')
    parser.add_argument('action',choices=('migrate','sync','backfill','daily'))
    parser.add_argument('--trade-days',type=int,default=20)
    args=parser.parse_args()
    init_fine_db();init_classification_v4();init_rotation_db()
    result={}
    if args.action in ('sync','daily'):
        result['official_electronics']=sync_electronics_universe()
        result['fine']=sync_fine_classification()
        result['official_company_evidence']=refresh_company_evidence()
        result['mops_business']=refresh_mops_business()
        result['classification_v4']=sync_classification_v4()
    if args.action in ('backfill','daily'):
        if args.action=='daily':
            result['price']=refresh_official_electronics_prices()
        result['benchmark']=refresh_benchmarks()
        result['institutional']=refresh_institutional(trade_days=args.trade_days if args.action=='backfill' else 1)
        if args.action=='backfill':
            days=backfill_rotation(trade_days=args.trade_days)
            result['rotation']={'trade_days':len(days),'rows':sum(d['rows'] for d in days),
                                'first':days[0]['trade_date'] if days else None,
                                'last':days[-1]['trade_date'] if days else None}
        else:
            result['rotation']=refresh_rotation()
    result['coverage']=get_fine_coverage()
    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
