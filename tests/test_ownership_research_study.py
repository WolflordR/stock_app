from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pytest

from modules.ownership_research.audit import anomalous_reports, anomaly_summary
from modules.ownership_research.data import connect, sync_ownership_metadata
from modules.ownership_research.factors import FactorConfig, load_factors
from modules.ownership_research.official_evidence import (
    _action_rows, fetch_action_month, parse_official_date, refresh_company_lifecycle,
)
from modules.ownership_research.study import (
    StudyConfig, build_event_rows, formal_readiness, summarize_events,
)


def _chip_db(path: Path, *, weeks: int = 13, gap_after: int | None = None) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("""CREATE TABLE stock_ownership_distribution_weekly(
            stock_id TEXT,report_date TEXT,tier INTEGER,holder_count INTEGER,shares INTEGER,
            reported_pct REAL,source_url TEXT,updated_at TEXT)""")
        day = date(2026, 1, 2)
        for week in range(weeks):
            if gap_after is not None and week == gap_after:
                day += timedelta(days=14)
            report_day = day.isoformat()
            delta = week * 1000
            shares = {1: 50_000 - delta, 12: 10_000, 15: 40_000 + delta, 17: 100_000}
            conn.executemany("INSERT INTO stock_ownership_distribution_weekly VALUES (?,?,?,?,?,?,?,?)", [
                ("1001", report_day, tier, 1 if shares.get(tier, 0) else 0,
                 shares.get(tier, 0), 100 if tier == 17 else shares.get(tier, 0) / 1000,
                 "https://example.test/archive", "2026-10-10T12:00:00")
                for tier in range(1, 18)
            ])
            day += timedelta(days=7)


def test_factors_use_past_tiers_once_and_reset_on_missing_week() -> None:
    with TemporaryDirectory() as tmp:
        chip, research = Path(tmp) / "chip.db", Path(tmp) / "research.db"
        _chip_db(chip, gap_after=10)
        assert sync_ownership_metadata(chip_path=chip, path=research)["valid"] == 13
        frame = load_factors(date(2026, 1, 2), date(2026, 5, 1), chip_path=chip, research_path=research)
        assert len(frame) == 13
        assert frame.loc[4, "pct_gt_400"] == pytest.approx(54.0)
        assert frame.loc[4, "pct_gt_1000"] == pytest.approx(44.0)
        assert frame.loc[4, "delta_1w_gt_1000"] == pytest.approx(1.0)
        assert frame.loc[4, "delta_4w_gt_1000"] == pytest.approx(4.0)
        assert frame.loc[8, "delta_8w_gt_1000"] == pytest.approx(8.0)
        assert frame.loc[4, "consecutive_up_weeks_gt_1000"] == 4
        assert frame.loc[4, "speed_pp_per_week_gt_1000"] == pytest.approx(1.0)
        assert frame.loc[4, "acceleration_pp_per_week_gt_1000"] == pytest.approx(0.0)
        assert frame.loc[4, "large_minus_small_delta_1w_pp"] == pytest.approx(2.0)
        assert pd.isna(frame.loc[10, "delta_1w_gt_1000"])
        assert frame.loc[10, "consecutive_up_weeks_gt_1000"] == 0
        with sqlite3.connect(chip) as conn:
            last_day = frame.loc[12, "report_date"]
            conn.execute("UPDATE stock_ownership_distribution_weekly SET shares=shares+500 WHERE report_date=? AND tier=15", (last_day,))
            conn.execute("UPDATE stock_ownership_distribution_weekly SET shares=shares-500 WHERE report_date=? AND tier=1", (last_day,))
        sync_ownership_metadata(chip_path=chip, path=research)
        changed = load_factors(date(2026, 1, 2), date(2026, 5, 1), chip_path=chip, research_path=research)
        assert changed.loc[11, "pct_gt_1000"] == frame.loc[11, "pct_gt_1000"]
        assert changed.loc[12, "pct_gt_1000"] == pytest.approx(frame.loc[12, "pct_gt_1000"] + 0.5)
        with pytest.raises(ValueError):
            FactorConfig(thresholds_lots=(350,), primary_threshold_lots=350)


def test_audit_reports_source_and_type_without_rewriting_raw_db() -> None:
    with TemporaryDirectory() as tmp:
        chip, research = Path(tmp) / "chip.db", Path(tmp) / "research.db"
        _chip_db(chip, weeks=1)
        with sqlite3.connect(chip) as conn:
            conn.execute("UPDATE stock_ownership_distribution_weekly SET shares=shares+7 WHERE tier=15")
        sync_ownership_metadata(chip_path=chip, path=research)
        frame = anomalous_reports(chip_path=chip, research_path=research)
        assert len(frame) == 1 and frame.iloc[0]["share_difference"] == 7
        assert anomaly_summary(frame)["error_types"] == {"shares_do_not_reconcile": 1}
        with sqlite3.connect(chip) as conn:
            assert conn.execute("SELECT shares FROM stock_ownership_distribution_weekly WHERE tier=15").fetchone()[0] == 40007


def test_assumed_delay_enters_after_report_and_uses_exact_market_horizon() -> None:
    factor = pd.DataFrame([{"stock_id": "1001", "report_date": "2026-01-02",
                            "source_url": "archive", "publication_status": "unverified_archive",
                            "published_at": None, "delta_1w_gt_1000": 2.0}])
    days = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    prices = pd.DataFrame([{"market": "TWSE", "stock_id": "1001", "trade_date": day,
                            "open": 100.0, "high": 105.0, "low": 98.0, "close": 100.0 + i * 2,
                            "volume": 1000, "adjustment_status": "unverified"}
                           for i, day in enumerate(days)])
    config = StudyConfig(start=date(2026, 1, 2), end=date(2026, 1, 2),
                         horizons=(2,), delay_days=(2,), lead_lag_sessions=(0,),
                         quantiles=2, price_source="official_raw")
    rows = build_event_rows(factor, prices, config, 2)
    assert len(rows) == 1
    assert rows.iloc[0]["entry_date"] == "2026-01-05"
    assert rows.iloc[0]["exit_date"] == "2026-01-07"
    assert rows.iloc[0]["price_change_pct"] == pytest.approx(4.0)
    assert rows.iloc[0]["availability_basis"] == "assumed_report_plus_2_calendar_days"
    assert summarize_events(rows, config)["event_study"][0]["n"] == 1
    missing = prices.loc[prices["trade_date"].ne("2026-01-06")]
    # Another stock keeps 1/6 in the market calendar; 1001's missing quote cannot move the exit.
    market_only = prices.loc[prices["trade_date"].eq("2026-01-06")].assign(stock_id="1002")
    assert build_event_rows(factor, pd.concat([missing, market_only]), config, 2).empty


def test_event_threshold_is_applied_before_nonoverlap_selection() -> None:
    config = StudyConfig(start=date(2026, 1, 1), end=date(2026, 1, 31),
                         horizons=(5,), lead_lag_sessions=(0,), event_min=0.0)
    events = pd.DataFrame([
        {"stock_id": "1001", "horizon": 5, "lead_lag_sessions": 0, "entry_date": "2026-01-05",
         "report_date": "2026-01-02", "entry_session_index": 1, "exit_session_index": 6,
         "factor_value": -1.0, "price_change_pct": -4.0, "max_adverse_pct": -5.0},
        {"stock_id": "1001", "horizon": 5, "lead_lag_sessions": 0, "entry_date": "2026-01-09",
         "report_date": "2026-01-08", "entry_session_index": 5, "exit_session_index": 10,
         "factor_value": 2.0, "price_change_pct": 6.0, "max_adverse_pct": -2.0},
    ])
    summary = summarize_events(events, config)
    assert summary["correlations_and_lead_lag"][0]["n"] == 1
    assert summary["event_study"][0]["n"] == 1
    assert summary["event_study"][0]["mean_price_change_pct"] == 6.0


def test_formal_mode_requires_publication_adjustment_and_history() -> None:
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "research.db"
        with connect(path):
            pass
        config = StudyConfig(start=date(2026, 1, 1), end=date(2026, 1, 2), mode="formal")
        factors = pd.DataFrame([{"publication_status": "unverified_archive", "published_at": None}])
        prices = pd.DataFrame([{"adjustment_status": "unverified", "adjusted_close": None}])
        reasons = formal_readiness(config=config, factors=factors, prices=prices, research_path=path)
        assert len(reasons) == 5


def test_official_action_pipeline_keeps_reference_as_evidence_not_adjusted_price() -> None:
    twse_ex = {"stat": "OK", "strDate": "20260901", "endDate": "20260930", "fields": ["資料日期", "股票代號", "除權息前收盤價", "除權息參考價", "權/息"],
               "data": [["115年09月01日", "1001", "100", "98", "息"]]}
    twse_reduction = {"stat": "OK", "strDate": "20260901", "endDate": "20260930", "fields": ["恢復買賣日期", "股票代號", "停止買賣前收盤價格", "恢復買賣參考價"],
                      "data": []}
    tpex_fields = ["除權息日期", "代號", "除權息前收盤價", "除權息參考價", "權/息", "現金股利", "每仟股無償配股"]
    tpex_ex = {"stat": "ok", "date": "20260901~20260930", "tables": [{"fields": tpex_fields,
               "data": [["115/09/02", "1002", "50", "48", "除息", "2", "0"]]}]}
    tpex_reduction = {"stat": "ok", "date": "20260901~20260930", "tables": [{"fields": [
        "恢復買賣日期", "股票代號", "最後交易日之收盤價格", "減資恢復買賣開始日參考價格"], "data": []}]}
    payloads = {"TWT49U": twse_ex, "TWTAUU": twse_reduction,
                "exDailyQ": tpex_ex, "revivt": tpex_reduction}
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "research.db"
        result = fetch_action_month(date(2026, 9, 10), path=path,
                                    getter=lambda url, _: payloads[url.rsplit("/", 1)[-1]], delay_seconds=0)
        assert result["sources"]["TWSE_EX"]["rows"] == 1
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM research_corporate_actions").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM research_corporate_action_evidence WHERE adjustment_verified=0").fetchone()[0] == 2
        fetch_action_month(date(2026, 9, 10), path=path,
                           getter=lambda *_: (_ for _ in ()).throw(RuntimeError("source offline")), delay_seconds=0)
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM research_corporate_actions").fetchone()[0] == 2
            assert conn.execute("SELECT COUNT(*) FROM research_source_fetches WHERE status='error'").fetchone()[0] == 4
            assert conn.execute("SELECT status,COUNT(*) FROM research_source_fetch_attempts GROUP BY status ORDER BY status").fetchall() == [("empty", 2), ("error", 4), ("ok", 2)]
        assert parse_official_date("1151010") == date(2026, 10, 10)
        with pytest.raises(ValueError):
            _action_rows("TPEx_EX", {**tpex_ex, "date": "20260801~20260831"}, date(2026, 9, 1), date(2026, 9, 30))
        with pytest.raises(ValueError):
            _action_rows("TWSE_EX", {**twse_ex, "strDate": "20260801"}, date(2026, 9, 1), date(2026, 9, 30))


def test_lifecycle_keeps_delisted_company_even_when_absent_from_current_snapshot() -> None:
    today_roc = f"{date.today().year-1911:03d}{date.today():%m%d}"
    csv_text = "出表日期,公司代號,公司簡稱,上市日期,已發行普通股數或TDR原股發行股數\n" + f"{today_roc},1001,甲公司,20200102,100000\n"
    twse = {"status": "ok", "fields": ["終止上市日期", "公司名稱", "上市編號"],
            "data": [["115/09/01", "乙公司", "1002"], ["108/09/01", "舊甲公司", "1001"]]}
    tpex = {"stat": "ok", "date": str(date.today().year), "tables": [{"fields": ["股票代號", "公司名稱", "終止上櫃日期"],
            "data": [["1003", "丙公司", "115-08-01"]]}]}
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "research.db"
        result = refresh_company_lifecycle(path=path, first_year=date.today().year,
                                           last_year=date.today().year,
                                           get_csv=lambda url: csv_text if url.endswith("_L.csv") else csv_text.replace("上市日期", "上櫃日期"),
                                           get_json=lambda url, _: twse if "twse.com.tw" in url else tpex)
        assert not result["errors"]
        with sqlite3.connect(path) as conn:
            assert conn.execute("SELECT listed_at FROM research_security_lifecycle WHERE market='TWSE' AND stock_id='1001'").fetchone()[0] == "2020-01-02"
            assert conn.execute("SELECT delisted_at FROM research_security_lifecycle WHERE market='TWSE' AND stock_id='1002'").fetchone()[0] == "2026-09-01"
            assert conn.execute("SELECT validation_status FROM research_security_lifecycle WHERE stock_id='1003'").fetchone()[0] == "partial_history"
            assert conn.execute("SELECT validation_status,delisted_at FROM research_security_lifecycle WHERE market='TWSE' AND stock_id='1001'").fetchone() == ("code_reuse_conflict", None)
            assert conn.execute("SELECT COUNT(*) FROM research_security_delisting_events WHERE market='TWSE'").fetchone()[0] == 2
