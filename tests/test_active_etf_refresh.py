from __future__ import annotations

import unittest
from unittest.mock import patch

from modules.etf.active_etf_watch import _is_target_active_etf, refresh_latest_active_etf_snapshots


class ActiveEtfRefreshTests(unittest.TestCase):
    def test_active_bond_etfs_are_included(self):
        self.assertTrue(_is_target_active_etf({'code': '00985D', 'name': '主動貝萊德優投等'}))
        self.assertFalse(_is_target_active_etf({'code': '0050', 'name': '元大台灣50'}))

    def test_latest_changes_are_persisted_with_snapshot_date(self):
        summary = {'updated_at': '2026-10-08', 'items': [
            {'code': '00981A', 'name': '主動統一台股增長', 'issuer': '統一'}]}
        detail = {'active': {'name': '主動統一台股增長', 'updatedAt': '2026-10-08',
                             'latestDiff': {'fromDate': '2026-10-07', 'toDate': '2026-10-08',
                                            'holdingsCount': 50, 'changes': [
                                                {'code': '2330', 'name': '台積電', 'industry': '半導體業',
                                                 'oldShares': 0, 'newShares': 2000, 'sharesDelta': 2000,
                                                 'oldWeight': 0, 'newWeight': 1.5, 'weightDelta': 1.5}]}},
                  'base': {'latestMarket': {'aum': 1000000000}}}
        with patch('modules.etf.active_etf_watch.load_active_etf_summary', return_value=summary), \
             patch('modules.etf.active_etf_watch.load_active_etf_detail', return_value=detail), \
             patch('modules.etf.active_etf_watch.fill_missing_industry', side_effect=lambda rows: rows), \
             patch('modules.etf.active_etf_watch.persist_etf_change_snapshot') as persist:
            result = refresh_latest_active_etf_snapshots()
        self.assertEqual(result['latest_snapshot_date'], '2026-10-08')
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['failed_count'], 0)
        args = persist.call_args.args
        self.assertEqual(args[0], '00981A')
        self.assertEqual(args[2]['to_date'], '2026-10-08')
        self.assertEqual(args[2]['change_counts']['新增'], 1)
        self.assertEqual(args[3].iloc[0]['shares_delta_lots'], 2)


if __name__ == '__main__':
    unittest.main()
