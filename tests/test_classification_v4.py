from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from modules.industry.classification_v4 import (
    _csv, get_stock_classification, run_sanity_audit, sync_classification_v4,
)
from modules.industry.fine_classification import _key, sync_fine_classification
from modules.industry.rotation_v3 import _sector_metrics


class ClassificationV4Tests(unittest.TestCase):
    def test_all_package_audits_and_many_to_many_memberships(self):
        audits=_csv('sanity_audit_v4.csv')
        companies=[{'market':'TPEx' if row['stock_id']=='3362' else 'TWSE',
                    'stock_id':row['stock_id'],'name':row['name'],
                    'company_name':row['name']+'股份有限公司',
                    'official_industry_code':'24'} for row in audits]
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'sector.db'
            sync_fine_classification(companies=companies,path=db,fetch_descriptions=False,export=False)
            result=sync_classification_v4(path=db,export=False)
            self.assertTrue(result['sanity_audit']['all_passed'])
            self.assertEqual(result['sanity_audit']['passed'],11)
            lens=get_stock_classification('3008',path=db)
            self.assertEqual(lens['status'],'confirmed_primary')
            self.assertEqual(lens['primary']['l3'],'光學鏡頭')
            self.assertIn('光學鏡頭',{member['l3'] for member in lens['memberships']})
            capacitors=get_stock_classification('3026',path=db)
            self.assertEqual(capacitors['primary']['l3'],'MLCC')
            self.assertGreater(len(capacitors['memberships']),1)
            self.assertTrue(capacitors['levels'])
            self.assertIsNone(get_stock_classification('2881',path=db))
            with sqlite3.connect(db) as conn:
                primary=conn.execute("SELECT sector_key FROM stock_primary_sector WHERE stock_id='3026'").fetchone()[0]
                self.assertEqual(primary,_key('被動元件','電容','MLCC'))
                membership_keys={row[0] for row in conn.execute(
                    "SELECT sector_key FROM stock_sector_memberships WHERE stock_id='3026'")}
                self.assertIn(_key('被動元件','電容','MLCC'),membership_keys)
                self.assertGreater(len(membership_keys),1)
                self.assertEqual(conn.execute("SELECT sector_key FROM stock_primary_sector WHERE stock_id='3008'").fetchone()[0],
                                 _key('顯示/光學','光學元件','光學鏡頭'))
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM stock_sector_memberships WHERE sector_key LIKE '%official_only%'").fetchone()[0],0)
                conn.execute("DELETE FROM stock_sector_memberships WHERE stock_id='3008' AND sector_key=?",
                             (_key('顯示/光學','光學元件','光學鏡頭'),))
            with self.assertRaises(AssertionError):
                run_sanity_audit(db)

    def test_secondary_member_changes_breadth_without_double_counting_flow(self):
        group=_key('被動元件','電容','MLCC')
        stocks=[
            {'market':'TWSE','primary_sector_key':group,'_group_sector_key':group,
             'return_1d':2,'return_5d':3,'return_20d':4,'turnover':100,
             'turnover_expansion':2,'breakout':1,'pressure':.2,'institutional_net_shares':10},
            {'market':'TWSE','primary_sector_key':_key('被動元件','電阻','Chip Resistor'),
             '_group_sector_key':group,'return_1d':-1,'return_5d':0,'return_20d':1,
             'turnover':200,'turnover_expansion':1,'breakout':0,'pressure':-.1,
             'institutional_net_shares':20},
        ]
        result=_sector_metrics(stocks,total_turnover=300,prior_share=None,
                               benchmark_returns={'TWSE':1,'TWSE_5':0},constituents=2)
        self.assertEqual(result['observed_count'],2)
        self.assertEqual(result['breadth'],.5)
        self.assertEqual(result['turnover'],100)
        self.assertAlmostEqual(result['turnover_share'],1/3)
        self.assertEqual(result['institutional_net_shares'],10)


if __name__=='__main__':
    unittest.main()
