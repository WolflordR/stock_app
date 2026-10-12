from __future__ import annotations

from datetime import date, timedelta

import pytest

from modules.data_sources.chip_trends import connect
from modules.data_sources.market_turnover import (
    market_turnover_ratios, parse_tpex_turnover, parse_twse_turnover, turnover_ratio,
)


def test_twse_uses_stock_total_not_all_securities_or_etf():
    day = date(2026, 10, 8)
    payload = {"stat": "OK", "date": "20261008", "tables": [{
        "fields": ["成交統計", "成交金額(元)", "成交股數(股)", "成交筆數"],
        "data": [["1.一般股票", "100", "10", "1"], ["4.ETF", "30", "3", "1"],
                 ["證券合計(1+6+14+15)", "110", "11", "2"], ["總計(1~15)", "150", "15", "4"]],
    }]}
    assert parse_twse_turnover(payload, day) == 110
    assert parse_twse_turnover({**payload, "date": "20261007"}, day) is None
    with pytest.raises(ValueError):
        parse_twse_turnover({**payload, "tables": []}, day)


def test_tpex_uses_stock_only_summary_and_converts_million_twd():
    day = date(2026, 10, 8)
    payload = {"stat": "ok", "date": "20261008", "tables": [{"title": "上櫃股票當日彙總資訊", "fields": ["上櫃家數", "本日總成交值(佰萬元)"], "data": [["893", "256,232"]]}]}
    assert parse_tpex_turnover(payload, day) == 256232000000
    assert parse_tpex_turnover({**payload, "date": "20261007"}, day) is None
    with pytest.raises(ValueError):
        parse_tpex_turnover({**payload, "tables": [{**payload["tables"][0], "data": []}]}, day)


def test_ratio_uses_five_preceding_days_and_combined_requires_matching_dates(tmp_path):
    path = str(tmp_path / "turnover.db")
    days = [(date.today() - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
    with connect(path) as conn:
        for index, day in enumerate(days):
            conn.execute("INSERT INTO market_turnover_daily VALUES (?,?,?,?,?)", ("TWSE", day, 100 if index < 6 else 200, "twse", "now"))
            if index != 6:
                conn.execute("INSERT INTO market_turnover_daily VALUES (?,?,?,?,?)", ("TPEx", day, 50, "tpex", "now"))
    result = market_turnover_ratios(path=path)
    assert result["TWSE"]["ratio"] == 2.0
    assert result["TWSE"]["average5_twd"] == 100
    assert days[6] not in result["TWSE"]["baseline_dates"]
    assert result["TPEx"]["ratio"] == 1.0
    assert result["combined"]["trade_date"] == days[5]
    assert result["combined"]["ratio"] == 1.0
    assert turnover_ratio([{"trade_date": days[6], "amount_twd": 200, "source_urls": {}}])["ratio"] is None
