from __future__ import annotations

import sqlite3

import pandas as pd

from apps.api import read_models
from modules.data_sources.price_cache import _normalize_history_df


def test_zero_volume_reference_bar_is_not_a_trading_quote():
    frame = pd.DataFrame(
        {"Open": [7.1, 13.2], "High": [7.2, 13.2], "Low": [7.0, 13.2],
         "Close": [7.1, 13.2], "Volume": [128173, 0]},
        index=pd.to_datetime(["2026-10-06", "2026-10-08"]),
    )
    clean = _normalize_history_df(frame)
    assert list(clean.index.strftime("%Y-%m-%d")) == ["2026-10-06"]
    assert clean.iloc[-1]["Close"] == 7.1


def test_stale_quote_does_not_claim_a_current_day_gain():
    quotes = [{"trade_date": "2026-10-02", "close": 7.0}, {"trade_date": "2026-10-06", "close": 7.1}]
    stale = read_models.build_quote_summary(quotes, "2026-10-08")
    assert stale["close"] == 7.1
    assert stale["is_current"] is False
    assert stale["change"] is None and stale["change_pct"] is None
    current = read_models.build_quote_summary(quotes, "2026-10-06")
    assert current["is_current"] is True and current["change_pct"] > 0


def test_suspended_and_stale_symbols_are_absent_from_strong_stocks(tmp_path, monkeypatch):
    monkeypatch.setattr(read_models, "db_path", lambda name: tmp_path / name)
    with sqlite3.connect(tmp_path / "price_cache.db") as conn:
        conn.execute("CREATE TABLE price_history(symbol TEXT,trade_date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(symbol,trade_date))")
        conn.executemany("INSERT INTO price_history VALUES(?,?,?,?,?,?,?)", [
            ("1111.TW", "2026-10-02", 10, 10, 10, 10, 1000),
            ("1111.TW", "2026-10-08", 11, 11, 11, 11, 1000),
            ("2222.TWO", "2026-10-02", 7, 7, 7, 7, 1000),
            ("2222.TWO", "2026-10-08", 13, 13, 13, 13, 0),
            ("3333.TWO", "2026-10-02", 5, 5, 5, 5, 1000),
            ("3333.TWO", "2026-10-07", 8, 8, 8, 8, 1000),
        ])
    with sqlite3.connect(tmp_path / "stocks.db") as conn:
        conn.execute("CREATE TABLE securities(code TEXT,name_zh TEXT,market TEXT,yfinance_symbol TEXT)")
        conn.executemany("INSERT INTO securities VALUES(?,?,?,?)", [
            ("1111", "正常", "TWSE", "1111.TW"),
            ("2222", "暫停", "TPEx", "2222.TWO"),
            ("3333", "舊報價", "TPEx", "3333.TWO"),
        ])
    assert [row["trade_date"] for row in read_models.list_stock_price_history("2222.TWO")] == ["2026-10-02"]
    result = read_models.list_strong_stocks(days=7, limit=10)
    assert result["summary"]["candidate_count"] == 1
    assert [row["code"] for row in result["rows"]] == ["1111"]
