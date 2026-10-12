from datetime import date, timedelta
import sqlite3
from unittest.mock import patch

import pandas as pd

from modules.data_sources import revenue_data
from services import dashboard


def test_partial_month_is_added_when_complete_csv_lags():
    previous_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    older = (date.today().replace(day=1) - timedelta(days=32)).strftime("%Y-%m")
    def csv_snapshot(market, _url):
        return pd.DataFrame([{"report_month": older, "market": market, "code": "2330", "current_revenue": 10}])
    def partial(market, month):
        assert month == previous_month
        return pd.DataFrame([{"report_month": month, "market": market, "code": "2330", "current_revenue": 12}])
    with patch.object(revenue_data, "init_revenue_cache"), \
         patch.object(revenue_data, "_fetch_market_snapshot", side_effect=csv_snapshot), \
         patch.object(revenue_data, "_fetch_historical_revenue_month", side_effect=partial) as fetch_partial, \
         patch.object(revenue_data, "_save_snapshot"):
        result = revenue_data.refresh_monthly_revenue_snapshot()
    assert fetch_partial.call_count == 2
    assert set(result["report_month"]) == {older, previous_month}
    assert len(result[result["report_month"] == previous_month]) == 2


def test_dashboard_marks_latest_month_partial_without_zero_filling(tmp_path):
    path = tmp_path / "revenue.db"
    previous_month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    older = (date.today().replace(day=1) - timedelta(days=32)).strftime("%Y-%m")
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE monthly_revenue(report_month TEXT,market TEXT,code TEXT,current_revenue REAL,updated_at TEXT)")
        conn.executemany("INSERT INTO monthly_revenue VALUES (?,?,?,?,?)", [(older, "上市", "2330", 10, "old"), (older, "上市", "2317", 5, "old"), (previous_month, "上市", "2330", 12, "new"), (previous_month, "上櫃", "1234", None, "new")])
    with patch.object(dashboard, "REVENUE_DB", path):
        result = dashboard._recent_revenue()
    assert result["report_month"] == previous_month
    assert result["count"] == 1
    assert result["partial"] is True
