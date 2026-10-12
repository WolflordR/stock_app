from fastapi.testclient import TestClient

from apps.api.main import app
from modules.data_sources import stock_db


def test_stock_search_prefix_results_and_literal_wildcards(tmp_path, monkeypatch):
    monkeypatch.setattr(stock_db, "DB_PATH", tmp_path / "stocks.db")
    stock_db.init_stock_db()
    with stock_db._get_connection() as conn:
        conn.executemany(
            "INSERT INTO securities(code,name_zh,full_name_zh,market,yfinance_symbol,updated_at) VALUES (?,?,?,?,?,?)",
            [
                ("2330", "台積電", "台灣積體電路製造", "TWSE", "2330.TW", "now"),
                ("2308", "台達電", "台達電子", "TWSE", "2308.TW", "now"),
                ("1301", "台塑", "台灣塑膠", "TWSE", "1301.TW", "now"),
                ("6589", "台康生技", "台康生物科技", "TWSE", "6589.TW", "now"),
                ("6589", "台康生技", "台康生物科技", "TPEx", "6589.TWO", "now"),
                ("1111", "新台", "新台股份有限公司", "TWSE", "1111.TW", "now"),
            ],
        )
    with TestClient(app) as client:
        rows = client.get("/api/stocks/search", params={"q": "台"}).json()["rows"]
        assert {row["code"] for row in rows[:4]} == {"2330", "2308", "1301", "6589"}
        assert rows[-1]["name_zh"] == "新台"
        assert sum(row["code"] == "6589" for row in rows) == 1
        assert client.get("/api/stocks/search", params={"q": "233"}).json()["rows"][0]["code"] == "2330"
        assert client.get("/api/stocks/search", params={"q": "%"}).json()["rows"] == []
