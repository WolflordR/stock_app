from datetime import date
from unittest.mock import patch

import pandas as pd

from modules.data_sources.chip_trends import connect
from modules.data_sources.market_limit_stocks import (
    _verified_rows,
    list_market_limit_stocks,
    parse_tpex_next_limit_prices,
    parse_twse_limit_prices,
    refresh_market_limit_details,
)


DAY = "2026-10-13"


def _quotes(market):
    return pd.DataFrame([
        {"market": market, "code": "1234", "name": "漲停股", "close": 11.0, "volume": 1000},
        {"market": market, "code": "5678", "name": "跌停股", "close": 9.0, "volume": 2000},
        {"market": market, "code": "9999", "name": "暫停交易", "close": 11.0, "volume": 0},
        {"market": market, "code": "8888", "name": "接近漲停", "close": 10.99, "volume": 3000},
    ])


def test_exact_official_limit_price_excludes_halted_and_near_limit():
    prices = {code: (11, 9) for code in ("1234", "5678", "9999", "8888")}
    rows = _verified_rows(_quotes("上市"), prices, market="TWSE", trade_date=DAY)
    assert [(row["stock_id"], row["direction"]) for row in rows] == [("1234", "up"), ("5678", "down")]


def test_official_price_report_dates_and_fields_are_checked():
    twse = {"stat": "OK", "date": "20261013", "fields": ["證券代號", "漲停價", "跌停價"], "data": [["1234", "11.00", "9.00"]]}
    assert parse_twse_limit_prices(twse, date(2026, 10, 13))["1234"][0] == 11
    assert parse_twse_limit_prices({**twse, "date": "20261012"}, date(2026, 10, 13)) is None
    tpex = {"stat": "ok", "date": "20261012", "tables": [{"fields": ["代號", "次日漲停價 ", "次日跌停價"], "data": [["1234", "11.00", "9.00"]]}]}
    assert parse_tpex_next_limit_prices(tpex, date(2026, 10, 12))["1234"][1] == 9
    assert parse_tpex_next_limit_prices({**tpex, "date": "20261013"}, date(2026, 10, 12)) is None


def test_collector_reconciles_both_markets_and_preserves_verified_rows(tmp_path):
    path = str(tmp_path / "chips.db")
    with connect(path) as conn:
        conn.executemany(
            "INSERT INTO market_limit_daily VALUES (?,?,?,?,?,?)",
            [(market, DAY, 1, 1, f"https://{market}.example/summary", "now") for market in ("TWSE", "TPEx")],
        )

    class Response:
        def __init__(self, url, payload):
            self.url = url
            self.payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self.payload

    class Session:
        def get(self, url, **kwargs):
            if "TWT84U" in url:
                return Response(url, {"stat": "OK", "date": "20261013", "fields": ["證券代號", "漲停價", "跌停價"], "data": [[code, "11.00", "9.00"] for code in ("1234", "5678", "9999", "8888")]})
            assert kwargs["params"]["d"] == "115/10/12"
            return Response(url, {"stat": "ok", "date": "20261012", "tables": [{"fields": ["代號", "次日漲停價 ", "次日跌停價"], "data": [[code, "11.00", "9.00"] for code in ("1234", "5678", "9999", "8888")]}]})

    with patch("modules.data_sources.market_limit_stocks.fetch_twse_daily_quotes", return_value=_quotes("上市")), patch("modules.data_sources.market_limit_stocks.fetch_tpex_daily_quotes", return_value=_quotes("上櫃")):
        result = refresh_market_limit_details(path=path, session=Session())
    assert not result["errors"]
    assert result["markets"]["TWSE"]["status"] == "complete"
    up = list_market_limit_stocks(direction="up", path=path)
    down = list_market_limit_stocks(direction="down", path=path)
    assert up["complete"] and up["official_count"] == 2 and len(up["rows"]) == 2
    assert down["complete"] and down["official_count"] == 2 and len(down["rows"]) == 2

    # A later partial source response must not replace a reconciled list.
    with patch("modules.data_sources.market_limit_stocks.fetch_twse_daily_quotes", return_value=_quotes("上市").iloc[:1]), patch("modules.data_sources.market_limit_stocks.fetch_tpex_daily_quotes", return_value=_quotes("上櫃")):
        failed = refresh_market_limit_details(path=path, session=Session(), force=True)
    assert "TWSE" in failed["errors"]
    assert list_market_limit_stocks(direction="down", market="TWSE", path=path)["complete"]


def test_combined_listing_requires_matching_market_dates(tmp_path):
    path = str(tmp_path / "chips.db")
    with connect(path) as conn:
        conn.executemany(
            "INSERT INTO market_limit_daily VALUES (?,?,?,?,?,?)",
            [("TWSE", "2026-10-13", 1, 0, "twse", "now"), ("TPEx", "2026-10-12", 1, 0, "tpex", "now")],
        )
    result = list_market_limit_stocks(direction="up", path=path)
    assert result["date"] is None and result["official_count"] is None and result["rows"] == []
