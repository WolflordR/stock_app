import sqlite3
from datetime import date, timedelta

import pytest

from modules.data_sources.broker_branch_stocks import list_broker_branch_stocks


def _fixtures(tmp_path):
    broker = tmp_path / "broker.db"
    stocks = tmp_path / "stocks.db"
    prices = tmp_path / "prices.db"
    with sqlite3.connect(broker) as conn:
        conn.execute("CREATE TABLE broker_trade_lines(market TEXT,trade_date TEXT,stock_code TEXT,broker_name TEXT,price REAL,buy_shares REAL,sell_shares REAL)")
        conn.executemany("INSERT INTO broker_trade_lines VALUES(?,?,?,?,?,?,?)", [
            ("TWSE", "2026-10-08", "1101", "台北分點", 20, 1000, 0),
            ("TWSE", "2026-10-08", "1101", "台北分點", 22, 1000, 0),
            ("TWSE", "2026-10-08", "1101", "台北分點", 23, 0, 500),
            ("TWSE", "2026-10-08", "1102", "台北分點", 30, 0, 3000),
            ("TWSE", "2026-10-08", "1103", "台北分點", None, 1000, 0),
            ("TWSE", "2026-10-08", "1104", "台北分點", 9, 500, 0),
            ("TWSE", "2026-10-08", "1101", "其他分點", 20, 9000, 0),
            ("TWSE", "2026-10-07", "1101", "台北分點", 18, 8000, 0),
        ])
    with sqlite3.connect(stocks) as conn:
        conn.execute("CREATE TABLE securities(code TEXT,name_zh TEXT,market TEXT,yfinance_symbol TEXT)")
        conn.executemany("INSERT INTO securities VALUES(?,?,?,?)", [
            (code, name, "TWSE", f"{code}.TW") for code, name in
            [("1101", "台泥"), ("1102", "亞泥"), ("1103", "嘉泥"), ("1104", "環泥")]
        ])
    with sqlite3.connect(prices) as conn:
        conn.execute("CREATE TABLE price_history(symbol TEXT,trade_date TEXT,close REAL,volume REAL)")
        earlier = [(date(2026, 10, 8) - timedelta(days=days)).isoformat() for days in range(1, 6)]
        for code, close, volume in [("1101", 22, 10000), ("1102", 30, 5000), ("1103", 11, 1000)]:
            conn.executemany("INSERT INTO price_history VALUES(?,?,?,?)", [(f"{code}.TW", day, close - 2, 2000) for day in earlier])
            conn.execute("INSERT INTO price_history VALUES(?,?,?,?)", (f"{code}.TW", "2026-10-08", close, volume))
        # A newer quote must never be substituted for the selected broker date.
        conn.execute("INSERT INTO price_history VALUES(?,?,?,?)", ("1104.TW", "2026-10-09", 12, 90000))
    return broker, stocks, prices


def test_branch_stocks_use_weighted_execution_prices_and_same_day_quotes(tmp_path):
    broker, stocks, prices = _fixtures(tmp_path)
    result = list_broker_branch_stocks("台北分點", "2026-10-08", broker_db=broker, stock_db=stocks, price_db=prices)
    rows = {row["stock_code"]: row for row in result["rows"]}
    assert result["total"] == 3
    assert rows["1101"]["stock_name"] == "台泥"
    assert rows["1101"]["net_shares"] == 1500
    assert rows["1101"]["avg_buy_price"] == 21
    assert rows["1101"]["avg_sell_price"] == 23
    assert rows["1101"]["stock_volume_shares"] == 10000
    assert rows["1101"]["estimated_trade_value"] == 220000
    assert rows["1101"]["volume_ratio"] == 5
    assert rows["1101"]["change_pct"] == pytest.approx(10)
    assert rows["1103"]["avg_buy_price"] is None  # Unpriced execution is not a zero-dollar purchase.
    assert rows["1104"]["stock_volume_shares"] is None
    assert rows["1104"]["change_pct"] is None


def test_branch_stocks_filter_sort_and_paginate_without_mixing_days(tmp_path):
    broker, stocks, prices = _fixtures(tmp_path)
    common = {"broker_db": broker, "stock_db": stocks, "price_db": prices}
    sold = list_broker_branch_stocks("台北分點", "2026-10-08", side="sell", **common)
    assert sold["total"] == 1
    assert sold["rows"][0]["stock_code"] == "1102"
    assert sold["rows"][0]["avg_sell_price"] == 30
    ranked = list_broker_branch_stocks("台北分點", "2026-10-08", sort_by="volume", limit=1, offset=1, **common)
    assert ranked["total"] == 3
    assert ranked["rows"][0]["stock_code"] == "1103"
    by_value = list_broker_branch_stocks("台北分點", "2026-10-08", sort_by="turnover_value", **common)
    assert [row["stock_code"] for row in by_value["rows"]] == ["1101", "1103", "1104"]
    by_ratio = list_broker_branch_stocks("台北分點", "2026-10-08", sort_by="volume_ratio", descending=False, **common)
    assert [row["stock_code"] for row in by_ratio["rows"]] == ["1103", "1101", "1104"]
    rising = list_broker_branch_stocks("台北分點", "2026-10-08", sort_by="change_pct", descending=False, **common)
    assert [row["stock_code"] for row in rising["rows"]] == ["1101", "1103", "1104"]
    assert list_broker_branch_stocks("台北分點", "2026-10-09", **common)["total"] == 0


def test_volume_ratio_needs_five_prior_trading_observations(tmp_path):
    broker, stocks, prices = _fixtures(tmp_path)
    with sqlite3.connect(prices) as conn:
        conn.execute("DELETE FROM price_history WHERE symbol='1103.TW' AND trade_date<'2026-10-06'")
    result = list_broker_branch_stocks("台北分點", "2026-10-08", broker_db=broker, stock_db=stocks, price_db=prices)
    row = next(row for row in result["rows"] if row["stock_code"] == "1103")
    assert row["stock_volume_shares"] == 1000
    assert row["volume_ratio"] is None
