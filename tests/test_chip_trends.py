from __future__ import annotations

from datetime import date, timedelta

from modules.data_sources.chip_trends import (
    _write_rows, backfill_tdcc_archive, connect, market_history, ownership_history, parse_tdcc,
    parse_tpex, parse_twse, ratio, stock_margin_history,
    refresh_margin_day, _status,
)

TWSE_FIELDS = ["代號", "名稱", "買進", "賣出", "現金償還", "前日餘額", "今日餘額", "次一營業日限額", "買進", "賣出", "現券償還", "前日餘額", "今日餘額", "次一營業日限額", "資券互抵", "註記"]
TPEX_FIELDS = ["代號", "名稱", "前資餘額(張)", "資買", "資賣", "現償", "資餘額", "資屬證金", "資使用率(%)", "資限額", "前券餘額(張)", "券賣", "券買", "券償", "券餘額", "券屬證金", "券使用率(%)", "券限額", "資券相抵(張)", "備註"]


def test_twse_report_has_separate_market_and_stock_units():
    day = date(2026, 10, 8)
    payload = {"stat": "OK", "date": "20261008", "tables": [
        {"fields": ["項目"], "data": [["融資(交易單位)", "3", "1", "0", "90", "92"], ["融券(交易單位)", "2", "1", "0", "9", "10"], ["融資金額(仟元)", "30", "10", "0", "1000", "1020"]]},
        {"fields": TWSE_FIELDS, "data": [["2330", "台積電", "3", "1", "0", "90", "92", "1000", "1", "2", "0", "9", "10", "1000", "0", ""]]},
    ]}
    market, rows = parse_twse(payload, day)
    assert market["margin_balance_lots"] == 92
    assert market["margin_balance_thousand_twd"] == 1020
    assert market["margin_previous_thousand_twd"] == 1000
    assert rows[0]["short_sell_lots"] == 2
    assert rows[0]["short_buy_lots"] == 1
    assert ratio(rows[0]["short_balance_lots"], rows[0]["margin_balance_lots"]) == round(10 / 92 * 100, 4)
    assert ratio(10, 0) is None
    assert parse_twse({**payload, "date": "20261007"}, day) is None


def test_tpex_market_aggregate_includes_all_report_rows_but_stocks_are_four_digits():
    day = date(2026, 10, 8)
    first = ["3026", "禾伸堂", "100", "5", "1", "0", "104", "0", "8.0", "1300", "10", "2", "1", "0", "11", "0", "0.8", "1300", "0", ""]
    etf = ["00679B", "ETF", "20", "0", "0", "0", "20", "0", "1.0", "1000", "0", "0", "0", "0", "0", "0", "0", "1000", "0", ""]
    payload = {"stat": "ok", "date": "20261008", "tables": [{"fields": TPEX_FIELDS, "data": [first, etf]}]}
    market, rows = parse_tpex(payload, day)
    assert market["margin_balance_lots"] == 124
    assert market["margin_balance_thousand_twd"] is None
    assert len(rows) == 1 and rows[0]["market"] == "TPEx"
    assert rows[0]["margin_usage_pct"] == 8
    assert parse_tpex({**payload, "tables": [{**payload["tables"][0], "data": []}]}, day) is None


def test_tdcc_exact_official_tiers_and_missing_tier_not_zero(tmp_path):
    day = "20261002"
    raw = [{"﻿資料日期": day, "證券代號": "2330", "持股分級": str(tier), "人數": "1", "股數": str(tier * 1000), "占集保庫存數比例%": "0.1"} for tier in range(1, 18)]
    raw[-1]["股數"] = "1000000"
    report_date, parsed = parse_tdcc(raw)
    assert report_date == "2026-10-02"
    path = str(tmp_path / "chips.db")
    with connect(path) as conn:
        _write_rows(conn, "stock_ownership_distribution_weekly", parsed, "tdcc")
    result = ownership_history("2330", path=path)["latest"]
    assert result["large"]["400"]["shares"] == 12000 + 13000 + 14000 + 15000
    assert result["large"]["600"]["shares"] == 13000 + 14000 + 15000
    assert result["large"]["800"]["shares"] == 14000 + 15000
    assert result["large"]["1000"]["shares"] == 15000
    assert result["small_10"]["shares"] == 1000 + 2000 + 3000
    with connect(path) as conn:
        conn.execute("DELETE FROM stock_ownership_distribution_weekly WHERE tier=14")
    assert "800" not in ownership_history("2330", path=path)["latest"]["large"]


def test_daily_and_weekly_dates_stay_separate_and_history_is_sorted(tmp_path):
    path = str(tmp_path / "chips.db")
    today = date.today()
    old, new = (today - timedelta(days=3)).isoformat(), (today - timedelta(days=1)).isoformat()
    with connect(path) as conn:
        for market in ("TWSE", "TPEx"):
            _write_rows(conn, "market_margin_short_daily", [dict(market=market, trade_date=day, margin_balance_lots=margin, margin_previous_lots=margin - 2, margin_balance_thousand_twd=None, short_balance_lots=short, short_previous_lots=short - 1) for day, margin, short in [(new, 120, 12), (old, 100, 10)]], market)
        _write_rows(conn, "stock_margin_short_daily", [dict(market="TWSE", stock_id="2330", trade_date=day, margin_balance_lots=balance, short_balance_lots=10, margin_previous_lots=None, short_previous_lots=None) for day, balance in [(new, 120), (old, 100)]], "twse")
    combined = market_history("combined", path=path)["rows"]
    assert [r["trade_date"] for r in combined] == [old, new]
    assert combined[-1]["margin_balance_lots"] == 240
    assert combined[-1]["margin_change_lots"] == 4
    assert combined[-1]["margin_5d_change_lots"] is None
    assert stock_margin_history("2330", path=path)["rows"][0]["margin_change_lots"] is None
    assert ownership_history("2330", path=path)["rows"] == []


def test_combined_requires_both_markets_same_day(tmp_path):
    path = str(tmp_path / "chips.db")
    day = date.today().isoformat()
    with connect(path) as conn:
        _write_rows(conn, "market_margin_short_daily", [dict(market="TWSE", trade_date=day, margin_balance_lots=100, margin_previous_lots=90, margin_balance_thousand_twd=1000, short_balance_lots=10, short_previous_lots=9)], "twse")
    assert market_history("TWSE", path=path)["latest"] is not None
    assert market_history("combined", path=path)["latest"] is None


def test_source_failure_does_not_discard_other_market(tmp_path):
    class Response:
        url = "https://official.example/report"
        def __init__(self, payload=None, failed=False):
            self.payload, self.failed = payload, failed
        def raise_for_status(self):
            if self.failed:
                raise RuntimeError("TWSE temporarily unavailable")
        def json(self):
            return self.payload
    class Client:
        def get(self, url, **_kwargs):
            if "twse" in url:
                return Response(failed=True)
            row = ["3026", "禾伸堂", "100", "5", "1", "0", "104", "0", "8.0", "1300", "10", "2", "1", "0", "11", "0", "0.8", "1300", "0", ""]
            return Response({"stat": "ok", "date": "20261008", "tables": [{"fields": TPEX_FIELDS, "data": [row]}]})
    path = str(tmp_path / "chips.db")
    result = refresh_margin_day(date(2026, 10, 8), session=Client(), path=path)
    assert "TWSE" in result["errors"]
    assert result["markets"]["TPEx"] == 1
    with connect(path) as conn:
        assert conn.execute("SELECT margin_balance_lots FROM market_margin_short_daily WHERE market='TPEx'").fetchone()[0] == 104


def test_five_day_change_is_missing_across_large_gap(tmp_path):
    path = str(tmp_path / "chips.db")
    today = date.today()
    days = [today - timedelta(days=n) for n in (70, 60, 50, 40, 30, 1)]
    with connect(path) as conn:
        _write_rows(conn, "market_margin_short_daily", [dict(market="TWSE", trade_date=day.isoformat(), margin_balance_lots=100 + i, margin_previous_lots=99 + i, margin_balance_thousand_twd=None, short_balance_lots=10, short_previous_lots=10) for i, day in enumerate(days)], "twse")
    assert market_history("TWSE", path=path)["latest"]["margin_5d_change_lots"] is None


def test_backfill_does_not_move_latest_source_date_backward(tmp_path):
    with connect(str(tmp_path / "chips.db")) as conn:
        _status(conn, "TWSE", "2026-10-08")
        _status(conn, "TWSE", "2025-12-01")
        assert conn.execute("SELECT last_success_date FROM chip_source_status WHERE source='TWSE'").fetchone()[0] == "2026-10-08"


def test_margin_amount_uses_official_thousand_twd_and_previous_balance(tmp_path):
    path = str(tmp_path / "chips.db")
    days = [(date.today() - timedelta(days=7-i)).isoformat() for i in range(6)]
    with connect(path) as conn:
        for i, day in enumerate(days):
            _write_rows(conn, "market_margin_short_daily", [dict(market="TWSE", trade_date=day,
                margin_balance_lots=100+i, margin_previous_lots=99+i,
                margin_balance_thousand_twd=646_000_000+i*100_000,
                margin_previous_thousand_twd=645_900_000+i*100_000,
                short_balance_lots=10, short_previous_lots=9)], "twse")
    latest = market_history("TWSE", path=path)["latest"]
    assert latest["margin_balance_yi_twd"] == 6465.0
    assert latest["margin_change_yi_twd"] == 1.0
    assert latest["margin_5d_change_yi_twd"] == 5.0
    assert latest["short_to_margin_pct"] == round(10/105*100, 4)
    assert market_history("combined", path=path)["latest"] is None


def test_tdcc_archived_original_week_is_idempotent_and_checked_against_saved_week(tmp_path):
    day = "2026-05-08"
    header = "資料日期,證券代號,持股分級,人數,股數,占集保庫存數比例%\n"
    data = "".join(f"20260508,{code},{tier},1,{100000 if tier == 17 else tier * 100},1.0\n"
                   for code in range(1000, 2001) for tier in range(1, 18))
    class Response:
        def __init__(self, content): self.content = content
        def raise_for_status(self): pass
        def json(self): return [{"name": day + ".csv", "type": "file"}]
    class Client:
        changed = False
        def get(self, url, **_kwargs):
            if url.endswith("/2026"):
                return Response(b"")
            body = header + (data.replace("20260508,1000,15,1,1500", "20260508,1000,15,1,1600") if self.changed else data)
            return Response(body.encode("utf-8-sig"))
    path = str(tmp_path / "chips.db")
    client = Client()
    first = backfill_tdcc_archive(path=path, session=client)
    assert first["weeks_imported"] == 1 and first["rows_imported"] == 1001 * 17
    assert ownership_history("1000", path=path)["archive_url"].endswith(day + ".csv")
    second = backfill_tdcc_archive(path=path, session=client)
    assert second["weeks_imported"] == 0 and second["weeks_existing"] == 1
    client.changed = True
    import pytest
    with pytest.raises(ValueError, match="does not match saved snapshot"):
        backfill_tdcc_archive(path=path, session=client)
