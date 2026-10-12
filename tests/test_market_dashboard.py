from __future__ import annotations

from datetime import date
from datetime import timedelta
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from services.events.company_events import list_events, normalize_announcement, parse_ir_calendar, refresh_events, upsert_events
from services.dashboard import _enrich_large_holder_signals, _large_holder_strategy_signals, _liquid_home_signals, _rising_large_holder_signals
from services.dashboard_signals import refresh_signals


TWSE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"


def test_conference_and_earnings_are_distinct_and_dates_are_roc() -> None:
    conference = normalize_announcement({
        "公司代號": "6281", "公司名稱": "全國電",
        "主旨 ": "本公司受邀參加凱基證券舉行之線上法說會",
        "說明": "1.召開法人說明會之日期：115/10/12\n2.召開法人說明會之時間：14 時 00 分\n3.召開法人說明會之地點：線上法說會",
    }, "TWSE", TWSE_URL, today=date(2026, 10, 9))
    earnings = normalize_announcement({
        "公司代號": "3169", "公司名稱": "亞信",
        "主旨 ": "115年第3季財務報告董事會預計召開日期為115年10月19日",
        "說明": "1.董事會預計召開日期:115/10/19\n2.預計提報董事會或經董事會決議之財務報告或年度自結財務資訊年季:115年第3季",
    }, "TPEx", TWSE_URL, today=date(2026, 10, 9))
    assert conference and conference["event_type"] == "investor_conference"
    assert conference["event_date"] == "2026-10-12"
    assert conference["start_time"] == "14:00"
    assert conference["status"] == "confirmed"
    assert earnings and earnings["event_type"] == "earnings"
    assert earnings["event_date"] == "2026-10-19"
    assert earnings["fiscal_year"] == 2026 and earnings["fiscal_quarter"] == 3
    assert earnings["status"] == "estimated"


def test_financial_report_board_announcement_uses_speech_date_not_estimate() -> None:
    actual = normalize_announcement({
        "公司代號": "2330", "公司名稱": "台積電",
        "主旨 ": "本公司115年度第二季合併財務報告業經董事會決議通過",
        "發言日期": "1150811", "說明": "1.董事會決議日期:115/08/11",
    }, "TWSE", TWSE_URL, today=date(2026, 8, 11))
    assert actual is not None
    assert actual["event_date"] == "2026-08-11"
    assert actual["status"] == "completed"
    assert (actual["fiscal_year"], actual["fiscal_quarter"]) == (2026, 2)
    assert normalize_announcement({
        "公司代號": "2330", "公司名稱": "台積電",
        "主旨 ": "本公司115年度第二季合併財務報告業經董事會決議通過",
        "發言日期": "", "說明": "1.董事會決議日期:115/08/11",
    }, "TWSE", TWSE_URL, today=date(2026, 8, 11)) is None


def test_event_upsert_deduplicates_and_queries_dates() -> None:
    event = normalize_announcement({
        "公司代號": "6281", "公司名稱": "全國電",
        "主旨 ": "公告本公司召開法人說明會",
        "說明": "1.召開法人說明會之日期：115/10/12",
    }, "TWSE", TWSE_URL, today=date(2026, 10, 9))
    assert event
    with TemporaryDirectory() as directory:
        path = Path(directory) / "events.db"
        upsert_events([event, event], path=path)
        upsert_events([event], path=path)
        assert list_events(start_date="2026-10-09", end_date="2026-10-15", path=path)["count"] == 1
        assert list_events(start_date="2026-10-13", end_date="2026-10-20", path=path)["count"] == 0
        assert list_events(start_date="2026-10-09", end_date="2026-10-15", event_type="earnings", path=path)["count"] == 0
        filtered = list_events(start_date="2026-10-09", end_date="2026-10-15", query="全國", status="confirmed", limit=1, offset=0, path=path)
        assert filtered["count"] == 1 and filtered["totals"]["investor_conference"] == 1
        assert list_events(start_date="2026-10-09", end_date="2026-10-15", query="台積", path=path)["count"] == 0


def test_financial_report_announcement_supersedes_board_date() -> None:
    estimated = normalize_announcement({
        "公司代號": "3169", "公司名稱": "亞信",
        "主旨 ": "115年第3季財務報告董事會預計召開日期為115年10月19日",
        "說明": "1.董事會預計召開日期:115/10/19",
    }, "TPEx", TWSE_URL, today=date(2026, 10, 11))
    completed = normalize_announcement({
        "公司代號": "3169", "公司名稱": "亞信",
        "主旨 ": "本公司115年度第三季財務報告業經董事會決議通過",
        "發言日期": "1151019",
    }, "TPEx", TWSE_URL, today=date(2026, 10, 19))
    assert estimated and completed
    with TemporaryDirectory() as directory:
        path = Path(directory) / "events.db"
        upsert_events([estimated, completed], path=path)
        assert upsert_events([estimated], path=path) == 0
        rows = list_events(start_date="2026-10-01", end_date="2026-10-31", path=path)["rows"]
        assert len(rows) == 1 and rows[0]["status"] == "completed"


def test_monthly_ir_calendar_fills_tsmc_gap_without_duplicate() -> None:
    html = """<select id="YearSelect"><option selected value="2026">2026</option></select>
    <select id="Month"><option selected value="10">10</option></select>
    <table><thead><tr><th>日期</th><th>時間</th><th>公司</th><th>地點</th><th>訊息</th></tr></thead>
    <tbody><tr><td data-header="日期">2026/10/15</td><td data-header="時間">14:00</td>
    <td data-header="公司">2330 台積電</td><td data-header="地點">線上法說會</td>
    <td data-header="訊息">公布本公司2026年第3季財務報告及業績展望</td></tr></tbody></table>"""
    calendar = parse_ir_calendar(html, "https://example.test/calendar", today=date(2026, 10, 11))
    assert len(calendar) == 1
    assert (calendar[0]["stock_id"], calendar[0]["event_date"], calendar[0]["start_time"]) == ("2330", "2026-10-15", "14:00")
    official = normalize_announcement({
        "公司代號": "2330", "公司名稱": "台積電", "主旨 ": "公告本公司召開法人說明會",
        "說明": "1.召開法人說明會之日期：115/10/15\n2.召開法人說明會之時間：14:00",
    }, "TWSE", TWSE_URL, today=date(2026, 10, 11))
    assert official
    with TemporaryDirectory() as directory:
        path = Path(directory) / "events.db"
        upsert_events(calendar, path=path)
        upsert_events([official], path=path)
        assert upsert_events(calendar, path=path) == 0
        rows = list_events(start_date="2026-10-11", end_date="2026-10-20", path=path)["rows"]
        assert len(rows) == 1 and rows[0]["source"].startswith("TWSE")


def test_ir_calendar_empty_month_and_invalid_page() -> None:
    empty = "<table><tr><th>日期</th><th>時間</th><th>公司</th></tr></table>"
    assert parse_ir_calendar(empty, "https://example.test", today=date(2026, 10, 11)) == []
    with pytest.raises(ValueError):
        parse_ir_calendar("<html>blocked</html>", "https://example.test", today=date(2026, 10, 11))


def test_refresh_monthly_calendar_tracks_rescheduled_events() -> None:
    class FakeResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self) -> None:
            pass

        def json(self) -> list:
            return []

    class Session:
        active = True

        def get(self, url: str, **_kwargs):
            if "conferenceList" not in url:
                return FakeResponse("[]")
            if "Year=2027" in url:
                return FakeResponse("<html>future year unavailable</html>")
            month = url.split("Month=")[-1]
            rows = "" if not self.active or month != "10" else """
                <tr><td data-header="日期">2026/10/15</td><td data-header="時間">14:00</td>
                <td data-header="公司">2330 台積電</td><td data-header="地點">線上法說會</td>
                <td data-header="訊息">第三季法說會</td></tr>"""
            return FakeResponse(f"""<select id="YearSelect"><option selected value="2026">2026</option></select>
                <select id="Month"><option selected value="{month}">{month}</option></select>
                <table><tr><th>日期</th><th>時間</th><th>公司</th></tr>{rows}</table>""")

    with TemporaryDirectory() as directory:
        path = Path(directory) / "events.db"
        session = Session()
        first = refresh_events(path=path, session=session, today=date(2026, 10, 11))
        assert first["errors"] == [] and first["sources"]["IRCalendar"] == 1
        assert list_events(start_date="2026-10-11", end_date="2026-10-31", stock_id="2330", path=path)["count"] == 1
        session.active = False
        second = refresh_events(path=path, session=session, today=date(2026, 10, 11))
        assert second["errors"] == []
        assert list_events(start_date="2026-10-11", end_date="2026-10-31", stock_id="2330", path=path)["count"] == 0


def test_invalid_and_unrelated_dates_do_not_create_events() -> None:
    row = {"公司代號": "2330", "公司名稱": "台積電", "主旨 ": "公告本公司召開法人說明會", "說明": "1.召開法人說明會之日期：115/13/40"}
    assert normalize_announcement(row, "TWSE", TWSE_URL, today=date(2026, 10, 9)) is None
    row["說明"] = "事實發生日：115/10/15"
    assert normalize_announcement(row, "TWSE", TWSE_URL, today=date(2026, 10, 9)) is None


def test_dashboard_empty_data_and_event_api_validation() -> None:
    from services import dashboard
    with patch.object(dashboard, "_price_snapshot", return_value=(None, {}, {})), \
         patch.object(dashboard, "_benchmarks", return_value={}), \
         patch.object(dashboard, "_industries", return_value=(None, [], {})), \
         patch.object(dashboard, "_signals", return_value=(None, [])), \
         patch.object(dashboard, "_watchlist_codes", return_value=[]), \
         patch.object(dashboard, "list_events", return_value={"rows": [], "count": 0, "source_state": []}):
        result = dashboard.build_dashboard()
    assert result["data_quality"]["price"] == "unavailable"
    assert result["events"]["rows"] == []
    from apps.api.main import app
    client = TestClient(app)
    assert client.get("/api/events?start_date=2026-10-20&end_date=2026-10-09").status_code == 422
    assert client.get("/api/events?event_type=not_a_type").status_code == 422


def test_home_signal_liquidity_uses_same_day_shares_and_strict_or_boundary() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "prices.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE price_history(symbol TEXT,trade_date TEXT,close REAL,volume REAL)")
            conn.executemany("INSERT INTO price_history VALUES (?,?,?,?)", [
                ("1001.TW", "2026-10-08", 1, 1_000_001),       # volume only
                ("1002.TW", "2026-10-08", 250, 900_000),       # value only
                ("1003.TW", "2026-10-08", 200, 1_000_000),     # equal on both: excluded
                ("1004.TW", "2026-10-08", 100, None),          # missing is not zero
                ("1005.TW", "2026-10-07", 300, 1_500_000),     # wrong date
                ("1006.TWO", "2026-10-08", 201, 1_000_000),    # value only, OTC
            ])
        signals = [{"stock_id": code, "strategy": "early_momentum"} for code in ("1001", "1002", "1003", "1004", "1005", "1006")]
        filtered = _liquid_home_signals(signals, "2026-10-08", price_path=path)
        assert [row["stock_id"] for row in filtered] == ["1001", "1002", "1006"]
        assert filtered[0]["volume_lots"] == 1000.001
        assert filtered[1]["estimated_turnover_twd"] == 225_000_000


def test_home_signals_require_complete_rising_weekly_large_holder_percentage() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "chip.db"
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE stock_ownership_distribution_weekly(stock_id TEXT,report_date TEXT,tier INTEGER,shares INTEGER)")
            def week(stock_id: str, report_date: str, large: int, *, missing_tier: int | None = None) -> None:
                conn.executemany("INSERT INTO stock_ownership_distribution_weekly VALUES (?,?,?,?)", [
                    (stock_id, report_date, tier, 1000 if tier == 17 else large if tier == 15 else 0)
                    for tier in range(1, 18) if tier != missing_tier
                ])
            for stock_id, previous, current in (("1001", 100, 200), ("1002", 200, 100), ("1005", 100, 100)):
                week(stock_id, "2026-10-02", previous)
                week(stock_id, "2026-10-08", current)
            week("1003", "2026-10-08", 200)  # Missing prior week.
            week("1004", "2026-10-02", 100)
            week("1004", "2026-10-08", 200, missing_tier=4)  # Incomplete current report.
            week("1006", "2026-10-02", 100)
            week("1006", "2026-10-15", 300)  # Future report cannot enter Oct 8 selection.
        signals = [{"stock_id": code} for code in ("1001", "1002", "1003", "1004", "1005", "1006")]
        enriched = _enrich_large_holder_signals(signals, "2026-10-08", chip_path=path)
        assert [row["stock_id"] for row in enriched] == [row["stock_id"] for row in signals]
        assert [row["large_holder_change_pp"] for row in enriched] == [10, -10, None, None, 0, None]
        assert enriched[2]["large_holder_pct"] == 20
        filtered = _rising_large_holder_signals(signals, "2026-10-08", chip_path=path)
        assert [row["stock_id"] for row in filtered] == ["1001"]
        assert filtered[0]["large_holder_pct"] == 20
        assert filtered[0]["large_holder_change_pp"] == 10
        assert (filtered[0]["ownership_previous_date"], filtered[0]["ownership_report_date"]) == ("2026-10-02", "2026-10-08")
        assert _rising_large_holder_signals(signals, "2026-11-01", chip_path=path) == []
        assert len(_enrich_large_holder_signals(signals, "2026-11-01", chip_path=path)) == len(signals)


def test_home_signals_fail_closed_when_ownership_table_missing() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "chip.db"
        sqlite3.connect(path).close()
        assert _rising_large_holder_signals([{"stock_id": "1001"}], "2026-10-08", chip_path=path) == []
        assert _enrich_large_holder_signals([{"stock_id": "1001"}], "2026-10-08", chip_path=path)[0]["large_holder_change_pp"] is None


def test_large_holder_is_standalone_strategy_with_liquidity_and_stock_universe() -> None:
    with TemporaryDirectory() as directory:
        price_path = Path(directory) / "prices.db"
        chip_path = Path(directory) / "chip.db"
        with sqlite3.connect(price_path) as conn:
            conn.execute("CREATE TABLE price_history(symbol TEXT,trade_date TEXT,close REAL,volume REAL)")
            conn.executemany("INSERT INTO price_history VALUES (?,?,?,?)", [
                ("1001.TW", "2026-10-08", 100, 1_000_001),
                ("1002.TW", "2026-10-08", 100, 1_000_001),
                ("1003.TWO", "2026-10-08", 100, 500_000),
                ("0050.TW", "2026-10-08", 100, 2_000_000),
            ])
        with sqlite3.connect(chip_path) as conn:
            conn.execute("CREATE TABLE stock_ownership_distribution_weekly(stock_id TEXT,report_date TEXT,tier INTEGER,shares INTEGER)")
            for stock_id, prior, current in (("1001", 100, 200), ("1002", 200, 100), ("1003", 100, 200), ("0050", 100, 200)):
                conn.executemany("INSERT INTO stock_ownership_distribution_weekly VALUES (?,?,?,?)", [
                    (stock_id, report_date, tier, 1000 if tier == 17 else large if tier == 15 else 0)
                    for report_date, large in (("2026-10-02", prior), ("2026-10-08", current))
                    for tier in range(1, 18)
                ])
        prices = {code: {"price": 100, "change_pct": 2, "trade_date": "2026-10-08"} for code in ("1001", "1002", "1003", "0050")}
        rows = _large_holder_strategy_signals(prices, "2026-10-08", {"1001", "1002", "1003"}, price_path=price_path, chip_path=chip_path)
        assert [(row["stock_id"], row["strategy"], row["large_holder_change_pp"]) for row in rows] == [("1001", "large_holder_increase", 10)]
        assert rows[0]["is_new"] == 0  # Weekly TDCC comparison is not a daily NEW signal.


def test_official_source_failure_keeps_stored_events() -> None:
    class FailingSession:
        def get(self, *_args, **_kwargs):
            raise ConnectionError("source unavailable")

    event = normalize_announcement({
        "公司代號": "6281", "公司名稱": "全國電",
        "主旨 ": "公告本公司召開法人說明會",
        "說明": "1.召開法人說明會之日期：115/10/12",
    }, "TWSE", TWSE_URL, today=date(2026, 10, 9))
    assert event
    with TemporaryDirectory() as directory:
        path = Path(directory) / "events.db"
        upsert_events([event], path=path)
        result = refresh_events(path=path, session=FailingSession(), today=date(2026, 10, 9))
        assert len(result["errors"]) == 3
        stored = list_events(start_date="2026-10-09", end_date="2026-10-15", path=path)
        assert stored["count"] == 1
        assert all(state["last_error"] for state in stored["source_state"])


def test_new_signal_requires_previous_session_to_be_unmatched() -> None:
    def analyzer(frame):
        return {"matched": float(frame["Close"].iloc[-1]) > 100, "volume_ratio_today": 1.5}

    with TemporaryDirectory() as directory:
        price_path = Path(directory) / "prices.db"
        signal_path = Path(directory) / "signals.db"
        with sqlite3.connect(price_path) as conn:
            conn.execute("CREATE TABLE price_history(symbol TEXT,trade_date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(symbol,trade_date))")
            for index in range(30):
                day = (date(2026, 9, 1) + timedelta(days=index)).isoformat()
                close = 102 if index == 29 else 99
                conn.execute("INSERT INTO price_history VALUES (?,?,?,?,?,?,?)", ("2330.TW", day, close, close, close, close, 1000))
        with patch("services.dashboard_signals.STRATEGIES", {"early_momentum": analyzer}):
            first = refresh_signals(path=signal_path, price_path=price_path, anchor="2026-09-30")
            assert first["signals"] == 1 and first["new"] == 1
            with sqlite3.connect(price_path) as conn:
                conn.execute("UPDATE price_history SET close=102 WHERE trade_date='2026-09-29'")
            second = refresh_signals(path=signal_path, price_path=price_path, anchor="2026-09-30")
            assert second["signals"] == 1 and second["new"] == 0
        with sqlite3.connect(signal_path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM daily_signals").fetchone()[0] == 1
