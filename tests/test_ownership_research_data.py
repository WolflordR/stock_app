from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd
import pytest

from modules.data_sources.market_watch import fetch_tpex_daily_quotes, fetch_twse_daily_quotes
from modules.ownership_research.backfill import backfill_tdcc_archives
from modules.ownership_research.audit import anomalous_reports
from modules.ownership_research.data import (backfill_prices, quality_report, refresh_price_day,
                                             sync_ownership_metadata)


def test_official_price_store_is_idempotent_and_empty_fetch_preserves_history() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "research.db"
        frame = pd.DataFrame([
            {"code": "1001", "open": 90, "high": 105, "low": 89, "close": 100, "volume": 1000},
            {"code": "1002", "open": 50, "high": 50, "low": 50, "close": 50, "volume": 0},
            {"code": "1003", "open": 50, "high": float("inf"), "low": 50, "close": 50, "volume": 2000},
            {"code": "0050", "open": 60, "high": 60, "low": 60, "close": 60, "volume": 2000},
        ])
        first = refresh_price_day(date(2026, 10, 8), "TWSE", path=path, fetcher=lambda _: frame)
        assert first["status"] == "ok" and first["rows"] == 2
        assert refresh_price_day(date(2026, 10, 8), "TWSE", path=path,
                                 fetcher=lambda _: (_ for _ in ()).throw(AssertionError("fetched twice")))["status"] == "cached"
        empty = refresh_price_day(date(2026, 10, 8), "TWSE", path=path, fetcher=lambda _: pd.DataFrame(), force=True)
        assert empty["status"] == "empty"
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM research_price_daily").fetchone()[0] == 2
            assert conn.execute("SELECT adjusted_close,adjustment_status FROM research_price_daily WHERE stock_id='1001'").fetchone() == (None, "unverified")
            assert conn.execute("SELECT status FROM research_source_fetches").fetchone()[0] == "empty"
        with pytest.raises(ValueError):
            backfill_prices(date(2016, 1, 1), date(2026, 1, 1), path=path)


def test_ownership_meta_marks_archived_dates_and_incomplete_tiers() -> None:
    with TemporaryDirectory() as directory:
        chip_path = Path(directory) / "chip.db"
        research_path = Path(directory) / "research.db"
        with sqlite3.connect(chip_path) as conn:
            conn.execute("""CREATE TABLE stock_ownership_distribution_weekly(
                stock_id TEXT,report_date TEXT,tier INTEGER,holder_count INTEGER,shares INTEGER,
                reported_pct REAL,source_url TEXT,updated_at TEXT)""")
            for stock_id, report_date, source, count in (
                ("1001", "2026-10-02", "https://raw.githubusercontent.com/wirelessr/tdcc-opendata-archive/main/snapshots/2026/2026-10-02.csv", 17),
                ("1001", "2026-10-08", "https://openapi.tdcc.com.tw/v1/opendata/1-5", 17),
                ("1002", "2026-10-08", "https://openapi.tdcc.com.tw/v1/opendata/1-5", 16),
                ("1003", "2026-10-08", "https://openapi.tdcc.com.tw/v1/opendata/1-5", 17),
            ):
                conn.executemany("INSERT INTO stock_ownership_distribution_weekly VALUES (?,?,?,?,?,?,?,?)", [
                    (stock_id, report_date, tier, 1, (141 if stock_id == "1003" else 140) if tier == 17 else 10, 100 if tier == 17 else 1,
                     source, "2026-10-10T12:02:14") for tier in range(1, count + 1)
                ])
        counts = sync_ownership_metadata(chip_path=chip_path, path=research_path)
        assert counts == {"reports": 4, "valid": 2, "missing_source": 0}
        sync_ownership_metadata(chip_path=chip_path, path=research_path)
        report = quality_report(path=research_path)
        assert report["ownership_reports"] == 4 and report["valid_reports"] == 2
        assert report["archive_reports_without_publication_time"] == 1
        assert report["strict_research_ready"] is False
        with sqlite3.connect(research_path) as conn:
            archive = conn.execute("SELECT published_at,publication_status,first_seen_at FROM research_ownership_weekly_meta WHERE report_date='2026-10-02'").fetchone()
            assert archive[0] is None and archive[1] == "unverified_archive" and archive[2].endswith("+08:00")
            assert conn.execute("SELECT COUNT(*) FROM research_ownership_weekly_meta").fetchone()[0] == 4
            assert "tier-16 adjustment differ" in conn.execute("SELECT quality_reason FROM research_ownership_weekly_meta WHERE stock_id='1003'").fetchone()[0]


def test_tier_16_is_subtracted_adjustment_not_holder_bucket() -> None:
    with TemporaryDirectory() as directory:
        chip_path = Path(directory) / "chip.db"
        research_path = Path(directory) / "research.db"
        with sqlite3.connect(chip_path) as conn:
            conn.execute("""CREATE TABLE stock_ownership_distribution_weekly(
                stock_id TEXT,report_date TEXT,tier INTEGER,holder_count INTEGER,shares INTEGER,
                reported_pct REAL,source_url TEXT,updated_at TEXT)""")
            conn.executemany("INSERT INTO stock_ownership_distribution_weekly VALUES (?,?,?,?,?,?,?,?)", [
                ("2409", "2026-06-05", tier, 1, 100 if tier <= 15 else (8 if tier == 16 else 1492),
                 0, "https://openapi.tdcc.com.tw/v1/opendata/1-5", "2026-06-06T10:00:00")
                for tier in range(1, 18)
            ])
        assert sync_ownership_metadata(chip_path=chip_path, path=research_path)["valid"] == 1
        with sqlite3.connect(research_path) as conn:
            assert conn.execute("SELECT valid,quality_reason FROM research_ownership_weekly_meta").fetchone() == (1, None)


def test_reconciled_shares_with_impossible_reported_percentage_get_correct_reason() -> None:
    with TemporaryDirectory() as directory:
        chip_path = Path(directory) / "chip.db"
        research_path = Path(directory) / "research.db"
        with sqlite3.connect(chip_path) as conn:
            conn.execute("""CREATE TABLE stock_ownership_distribution_weekly(
                stock_id TEXT,report_date TEXT,tier INTEGER,holder_count INTEGER,shares INTEGER,
                reported_pct REAL,source_url TEXT,updated_at TEXT)""")
            conn.executemany("INSERT INTO stock_ownership_distribution_weekly VALUES (?,?,?,?,?,?,?,?)", [
                ("3026", "2021-07-23", tier, 1, 100 if tier <= 15 else (8 if tier == 16 else 1492),
                 101.0 if tier == 17 else 1.0, "https://example.test/archive", "2021-07-24T12:00:00")
                for tier in range(1, 18)
            ])
        assert sync_ownership_metadata(chip_path=chip_path, path=research_path)["valid"] == 0
        bad = anomalous_reports(chip_path=chip_path, research_path=research_path)
        assert len(bad) == 1 and bad.iloc[0]["error_type"] == "invalid_reported_percentage"
        assert bad.iloc[0]["share_difference"] == 0


def test_official_quote_parsers_reject_wrong_report_date() -> None:
    with patch("modules.data_sources.market_watch._request_json", return_value={"stat": "OK", "date": "20261007", "tables": []}):
        assert fetch_twse_daily_quotes(date(2026, 10, 8)).empty
    with patch("modules.data_sources.market_watch._request_json", return_value={"stat": "ok", "date": "20261007", "tables": []}):
        assert fetch_tpex_daily_quotes(date(2026, 10, 8)).empty


def test_tpex_historical_quote_schema_without_bid_ask_volume() -> None:
    fields = ["代號", "名稱", "收盤 ", "漲跌", "開盤 ", "最高 ", "最低", "成交股數  ",
              " 成交金額(元)", " 成交筆數 ", "最後買價", "最後賣價", "發行股數 ", "次日漲停價 ", "次日跌停價"]
    payload = {"stat": "ok", "date": "20161007", "tables": [{"fields": fields,
               "data": [["1258", "其祥-KY", "38.00", "- 0.60", "38.60", "38.60", "37.80",
                         "64,000", "2,447,450", "50", "38.00", "38.20", "35,969,094", "41.80", "34.20"]]}]}
    with patch("modules.data_sources.market_watch._request_json", return_value=payload):
        row = fetch_tpex_daily_quotes(date(2016, 10, 7)).iloc[0]
    assert row["code"] == "1258" and row["close"] == 38 and row["volume"] == 64000
    assert row["change_value"] == pytest.approx(-0.6)
    assert pd.isna(row["last_bid_volume"])


def test_tdcc_archive_backfill_resumes_without_overwriting_existing_rows() -> None:
    class Response:
        content = b"archived snapshot"

        def raise_for_status(self) -> None:
            pass

    class Session:
        calls = 0

        def get(self, _url: str, timeout: int) -> Response:
            self.calls += 1
            return Response()

    with TemporaryDirectory() as directory:
        chip_path = Path(directory) / "chip.db"
        research_path = Path(directory) / "research.db"
        with sqlite3.connect(chip_path) as conn:
            conn.execute("""CREATE TABLE stock_ownership_distribution_weekly(
                stock_id TEXT,report_date TEXT,tier INTEGER,holder_count INTEGER,shares INTEGER,
                reported_pct REAL,source_url TEXT,updated_at TEXT,
                PRIMARY KEY(stock_id,report_date,tier))""")
        rows = [{"stock_id": "1001", "tier": tier, "holder_count": 1, "shares": 100,
                 "reported_pct": 1.0} for tier in range(1, 18)]
        client = Session()
        with (patch("modules.ownership_research.backfill.archive_files", return_value=["2021-07-02.csv"]),
              patch("modules.ownership_research.backfill.parse_archive_content", return_value=rows)):
            first = backfill_tdcc_archives(first_year=2021, last_year=2021, max_weeks=1,
                                           chip_path=chip_path, research_path=research_path,
                                           session=client)
            second = backfill_tdcc_archives(first_year=2021, last_year=2021, max_weeks=1,
                                            chip_path=chip_path, research_path=research_path,
                                            session=client)
        assert first["imported_weeks"] == 1 and first["rows"] == 17
        assert second["cached_weeks"] == 1 and second["downloaded_weeks"] == 0
        assert client.calls == 1
        with sqlite3.connect(chip_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM stock_ownership_distribution_weekly").fetchone()[0] == 17
            conn.execute("UPDATE stock_ownership_distribution_weekly SET shares=111 WHERE tier=1")
        with sqlite3.connect(research_path) as conn:
            conn.execute("DELETE FROM research_source_fetches WHERE source_key='TDCC_ARCHIVE'")
        with (patch("modules.ownership_research.backfill.archive_files", return_value=["2021-07-02.csv"]),
              patch("modules.ownership_research.backfill.parse_archive_content", return_value=rows)):
            retry = backfill_tdcc_archives(first_year=2021, last_year=2021, max_weeks=1,
                                            chip_path=chip_path, research_path=research_path,
                                            session=client)
        assert retry["imported_weeks"] == 0 and retry["errors"]
        with sqlite3.connect(chip_path) as conn:
            assert conn.execute("SELECT shares FROM stock_ownership_distribution_weekly WHERE tier=1").fetchone()[0] == 111
