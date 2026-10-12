from datetime import date
from unittest.mock import patch

from modules.data_sources.chip_trends import connect
from modules.data_sources.market_limits import parse_tpex_limits, parse_twse_limits, refresh_market_limits
from services import dashboard


def test_official_stock_counts_exclude_twse_warrants_and_preserve_zero():
    day = date(2026, 10, 8)
    twse = {"stat": "OK", "date": "20261008", "tables": [{"title": "漲跌證券數合計", "fields": ["類型", "整體市場", "股票"], "data": [["上漲(漲停)", "5,285(78)", "425(14)"], ["下跌(跌停)", "9,634(83)", "540(0)"]]}]}
    assert parse_twse_limits(twse, day) == {"market": "TWSE", "trade_date": "2026-10-08", "limit_up_count": 14, "limit_down_count": 0}
    assert parse_twse_limits({**twse, "date": "20261007"}, day) is None
    tpex = {"stat": "ok", "date": "20261008", "tables": [{"title": "上櫃股票當日彙總資訊", "fields": ["上漲家數", "漲停家數", "跌停家數"], "data": [["356", "23", "3"]]}]}
    assert parse_tpex_limits(tpex) == {"market": "TPEx", "trade_date": "2026-10-08", "limit_up_count": 23, "limit_down_count": 3}


def test_market_limits_only_combine_same_date(tmp_path):
    path = str(tmp_path / "chips.db")
    with connect(path) as conn:
        conn.execute("INSERT INTO market_limit_daily VALUES (?,?,?,?,?,?)", ("TWSE", "2026-10-08", 14, 2, "https://twse.example", "now"))
        conn.execute("INSERT INTO market_limit_daily VALUES (?,?,?,?,?,?)", ("TPEx", "2026-10-07", 23, 3, "https://tpex.example", "now"))
    with patch.object(dashboard, "CHIP_DB", tmp_path / "chips.db"):
        result = dashboard._market_limits()
        assert result["limit_up_count"] is None
        with connect(path) as conn:
            conn.execute("INSERT INTO market_limit_daily VALUES (?,?,?,?,?,?)", ("TPEx", "2026-10-08", 23, 3, "https://tpex.example", "now"))
        result = dashboard._market_limits()
    assert result["date"] == "2026-10-08"
    assert result["limit_up_count"] == 37
    assert result["limit_down_count"] == 5


def test_one_official_source_failure_keeps_other_count(tmp_path):
    class Response:
        url = "https://app.tpex.org.tw/data/15.json"
        def raise_for_status(self):
            pass
        def json(self):
            return {"stat": "ok", "date": "20261008", "tables": [{"title": "上櫃股票當日彙總資訊", "fields": ["漲停家數", "跌停家數"], "data": [["23", "3"]]}]}
    class Client:
        def get(self, url, **_kwargs):
            if "twse" in url:
                raise ConnectionError("TWSE unavailable")
            return Response()
    path = str(tmp_path / "chips.db")
    result = refresh_market_limits(session=Client(), path=path, end=date(2026, 10, 8))
    assert result["errors"]["TWSE"] == "TWSE unavailable"
    assert result["markets"]["TPEx"]["limit_up_count"] == 23
