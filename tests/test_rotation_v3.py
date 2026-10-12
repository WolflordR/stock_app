from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from modules.industry.fine_classification import (
    _key, _rows, classify_business, get_fine_coverage, sync_fine_classification,
)
from modules.industry.rotation_v3 import _features, _sector_metrics, _stage


def company(market: str, stock_id: str, name: str, industry: str) -> dict:
    return {'market': market, 'stock_id': stock_id, 'name': name,
            'company_name': name + '股份有限公司', 'official_industry_code': industry}


class FineClassificationTests(unittest.TestCase):
    def test_curated_primary_official_overlap_and_theme_are_non_additive(self):
        rows = [company('TWSE','2308','台達電','28'),
                company('TWSE','2330','台積電','24'),
                company('TPEx','9998','待分類公司','28')]
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'rotation.db'
            result = sync_fine_classification(companies=rows,path=db,fetch_descriptions=False,export=False)
            self.assertEqual(result['target_total'],3)
            self.assertEqual(result['l3_mapped_total'],2)
            # The curated package itself flags 台達電 as needing product refinement.
            self.assertEqual(result['review_queue_total'],2)
            with sqlite3.connect(db) as conn:
                memberships = conn.execute("SELECT source,primary_for_flow FROM fine_memberships WHERE stock_id='2308'").fetchall()
                self.assertEqual(sum(primary for _,primary in memberships),1)
                self.assertGreater(len(memberships),1)
                self.assertEqual(next(source for source,primary in memberships if primary),'curated_product')
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM fine_themes WHERE stock_id='2308' AND theme='AI'").fetchone()[0],1)
                self.assertEqual(conn.execute("SELECT reason FROM fine_review_queue WHERE stock_id='9998'").fetchone()[0],'business_unavailable')
                # Verified manual edits stay primary after package refresh.
                conn.execute("UPDATE fine_memberships SET primary_for_flow=0 WHERE stock_id='2308'")
                conn.execute("INSERT INTO fine_memberships VALUES(?,?,?,?,?,?,?,?,?,?)",
                             ('TWSE','2308',_key('半導體','IC設計','CPU/MCU'),'manual_verified','test',1.0,1,'2026-10-01',None,'2026-10-01'))
            sync_fine_classification(companies=rows,path=db,fetch_descriptions=False,export=False)
            with sqlite3.connect(db) as conn:
                self.assertEqual(conn.execute("SELECT source FROM fine_memberships WHERE stock_id='2308' AND primary_for_flow=1").fetchone()[0],'manual_verified')
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM fine_memberships WHERE stock_id='2308' AND primary_for_flow=1").fetchone()[0],1)

    def test_business_rule_only_matches_supported_specific_products(self):
        keys={_key(r['l1'],r['l2'],r['l3']) for r in _rows('fine_taxonomy_v2.csv')}
        self.assertEqual(classify_business('主要產品：ABF載板',keys)[0],_key('PCB','IC載板','ABF Substrate'))
        self.assertIsNone(classify_business('主要產品：一般印刷電路板',keys)[0])
        self.assertEqual(classify_business('',keys)[1],'business_unavailable')
        self.assertEqual(classify_business('ABF載板、BT載板',keys)[1],'ambiguous_business')

    def test_broad_market_curated_rows_are_not_electronics_target(self):
        rows=[company('TWSE','2881','富邦金','17'),company('TPEx','9998','待分類公司','28')]
        with tempfile.TemporaryDirectory() as temp:
            result=sync_fine_classification(companies=rows,path=Path(temp)/'fine.db',fetch_descriptions=False,export=False)
            self.assertEqual(result['target_total'],1)
            self.assertEqual(result['l3_mapped_total'],0)


class RotationTests(unittest.TestCase):
    def test_suspended_stock_has_no_feature(self):
        history=[(f'2026-09-{i+1:02d}',99,101,100,100,1000) for i in range(26)]
        history[-1]=(history[-1][0],99,101,100,100,0)
        self.assertIsNone(_features(history,history[-1][0]))

    def test_median_and_concentration_control_one_outlier(self):
        stocks=[]
        for i in range(6):
            stocks.append({'market':'TWSE','return_1d':100 if i==0 else 1,
              'return_5d':100 if i==0 else 2,'return_20d':100 if i==0 else 3,
              'turnover':1000 if i==0 else 100,'turnover_expansion':2,
              'breakout':int(i==0),'pressure':0.1,'institutional_net_shares':1000 if i<5 else None})
        result=_sector_metrics(stocks,total_turnover=1500,prior_share=0.5,
                               benchmark_returns={'TWSE':2,'TWSE_5':1},constituents=7)
        self.assertEqual(result['return_1d'],1)
        self.assertTrue(result['concentrated'])
        self.assertAlmostEqual(result['institutional_coverage'],5/6)
        self.assertEqual(result['institutional_net_shares'],5000)
        self.assertEqual(result['pressure_source'],'OHLCV_ESTIMATE_CMF_MFI')
        self.assertNotIn('institutional_net_ntd',result)
        self.assertTrue(result['rank_eligible'])
        self.assertEqual(_stage(75,5,3,.7,False),'Leading')
        self.assertEqual(_stage(82,5,3,.7,True),'Crowded')

    def test_api_endpoints(self):
        from fastapi.testclient import TestClient
        from apps.api.main import app
        with TestClient(app) as client:
            coverage=client.get('/api/rotation/coverage')
            self.assertEqual(coverage.status_code,200)
            self.assertIn('review_queue_total',coverage.json())
            self.assertEqual(client.get('/api/rotation/filters').status_code,200)
            response=client.get('/api/rotation/ranking?level=3')
            self.assertEqual(response.status_code,200)
            self.assertEqual(client.get('/api/rotation/ranking?level=4').status_code,422)
            if response.json():
                from urllib.parse import quote
                key=quote(response.json()[0]['sector_key'],safe='')
                detail=client.get('/api/rotation/detail/'+key)
                self.assertEqual(detail.status_code,200)
                self.assertIn('timeline',detail.json())


if __name__ == '__main__':
    unittest.main()
