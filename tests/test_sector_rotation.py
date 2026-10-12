from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from modules.industry.electronics_universe import (
    get_electronics_coverage,
    import_official_companies,
    list_electronics,
    normalize_company,
)
from modules.industry.sector_metrics import aggregate_sector_metrics


def company(market: str, stock_id: str, industry_code: str) -> dict:
    return {
        "market": market, "stock_id": stock_id, "name": f"公司{stock_id}",
        "company_name": f"公司{stock_id}", "official_industry_code": industry_code,
        "website": "", "source_date": "1151006",
    }


class UniverseTests(unittest.TestCase):
    def test_normalization_and_noncompany_filter(self):
        self.assertEqual(normalize_company({"公司代號": "2330", "公司簡稱": "台積電", "產業別": "24"}, "TWSE")["official_industry_code"], "24")
        self.assertEqual(normalize_company({"SecuritiesCompanyCode": "5347", "CompanyAbbreviation": "世界", "SecuritiesIndustryCode": "24"}, "TPEx")["name"], "世界")
        self.assertIsNone(normalize_company({"公司代號": "0050", "公司簡稱": "ETF", "產業別": "24"}, "TWSE"))
        self.assertIsNone(normalize_company({"公司代號": "12345", "公司簡稱": "權證", "產業別": "24"}, "TWSE"))

    def test_complete_import_seed_and_new_listing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sector.db"
            rows = [company("TWSE", str(5000 + code), str(code)) for code in range(24, 32)]
            rows += [company("TPEx", str(6000 + code), str(code)) for code in range(24, 32)]
            rows += [company("TWSE", "2330", "24")]
            result = import_official_companies(rows, {"TWSE": "mock", "TPEx": "mock"}, path=path, stock_path=None, export=False)
            self.assertEqual(result["imported_total"], 17)
            self.assertTrue(result["coverage_ok"])
            self.assertEqual(result["taxonomy_mapped_total"], 1)
            self.assertEqual(result["official_only_total"], 16)
            self.assertEqual({r["official_industry_code"] for r in list_electronics(path=path)}, {str(code) for code in range(24, 32)})
            with sqlite3.connect(path) as conn:
                self.assertEqual(conn.execute("SELECT relation FROM stock_sector_map WHERE stock_id='2330' AND category_slug='foundry'").fetchone()[0], "primary")
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM stock_sector_map WHERE stock_id='5024'").fetchone()[0], 1)
                conn.execute("INSERT INTO stock_sector_map(market,stock_id,category_slug,relation,source,verified_at) VALUES('TWSE','5024','foundry','primary','manual_verified','2026-10-07')")
            rows.append(company("TPEx", "9998", "31"))
            updated = import_official_companies(rows, {"TWSE": "mock", "TPEx": "mock"}, path=path, stock_path=None, export=False)
            self.assertEqual(updated["imported_total"], 18)
            self.assertEqual(updated["taxonomy_mapped_total"], 2)
            self.assertTrue(any(r["stock_id"] == "9998" for r in list_electronics(path=path)))
            with sqlite3.connect(path) as conn:
                conn.execute("DELETE FROM official_electronics WHERE stock_id='9998'")
            self.assertFalse(get_electronics_coverage(path)["coverage_ok"])

    def test_rejects_partial_market_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                import_official_companies([company("TWSE", "2330", "24")], {"TWSE": "mock", "TPEx": "mock"}, path=Path(directory) / "sector.db", stock_path=None, export=False)


class MetricTests(unittest.TestCase):
    def test_one_extreme_return_does_not_dominate(self):
        anchor = date(2026, 10, 2)
        dates = [(anchor - timedelta(days=20 - i)).isoformat() for i in range(21)]
        memberships = {"test": {f"{i}.TW" for i in range(6)}}

        def histories(extreme: bool):
            result = {}
            for i in range(6):
                closes = [100.0] * 20 + [200.0 if extreme and i == 0 else 101.0]
                result[f"{i}.TW"] = [(day, close, 1000.0, close) for day, close in zip(dates, closes)]
            return result

        normal = aggregate_sector_metrics(histories(False), memberships, dates[-1], 1)[0]
        extreme = aggregate_sector_metrics(histories(True), memberships, dates[-1], 1)[0]
        self.assertEqual(normal["median_return"], extreme["median_return"])
        self.assertLess(abs(normal["rotation_score"] - extreme["rotation_score"]), 5)
        self.assertTrue(extreme["rank_eligible"])
        self.assertFalse(aggregate_sector_metrics(histories(True), {"small": {"0.TW", "1.TW"}}, dates[-1], 1)[0]["rank_eligible"])

    def test_suspended_stock_is_excluded_from_breadth(self):
        days = [(date(2026, 10, 2) - timedelta(days=20 - i)).isoformat() for i in range(21)]
        active = [(day, 100.0 if i < 20 else 101.0, 1000.0, 101.0) for i, day in enumerate(days)]
        suspended = [(day, 100.0, 0.0 if i == 20 else 1000.0, 100.0) for i, day in enumerate(days)]
        row = aggregate_sector_metrics({"a.TW": active, "b.TW": suspended}, {"test": {"a.TW", "b.TW"}}, days[-1], 1)[0]
        self.assertEqual(row["observed_count"], 1)
        self.assertEqual(row["advance_ratio"], 1.0)


class ApiTests(unittest.TestCase):
    def test_basic_sector_endpoints(self):
        from fastapi.testclient import TestClient
        from apps.api.main import app

        with TestClient(app) as client:
            for path in ("/api/sectors/coverage", "/api/sectors", "/api/sectors/ranking?window_days=1", "/api/themes"):
                self.assertEqual(client.get(path).status_code, 200, path)
            self.assertEqual(client.get("/api/sectors/ranking?window_days=2").status_code, 422)


if __name__ == "__main__":
    unittest.main()
