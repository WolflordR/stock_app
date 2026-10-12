from __future__ import annotations

import sqlite3

import pytest

from modules.data_sources import financial_eps


def _csv(quarter: str, eps: str, code: str = "2330") -> str:
    return f"\ufeff出表日期,年度,季別,公司代號,公司名稱,基本每股盈餘（元）\n1151010,115,{quarter},{code},測試公司,{eps}\n"


def test_eps_is_roc_year_and_year_to_date_not_single_quarter():
    row = financial_eps.parse_eps_csv(_csv("2", "49.33"), "TWSE", "ci")[0]
    assert (row["report_year"], row["report_quarter"], row["basic_eps_ytd"]) == (2026, 2, 49.33)
    assert row["output_date"] == "2026-10-10"
    assert financial_eps.parse_eps_csv(_csv("2", "—"), "TWSE", "ci") == []
    with pytest.raises(ValueError):
        financial_eps.parse_eps_csv("公司代號,數值\n2330,1", "TWSE", "ci")


def test_latest_eps_keeps_prior_report_when_new_quarter_has_no_company(tmp_path, monkeypatch):
    path = tmp_path / "financial_eps.db"
    monkeypatch.setattr(financial_eps, "REPORT_TYPES", ("bd",))
    monkeypatch.setattr(financial_eps, "MARKETS", {"TWSE": "L"})
    monkeypatch.setattr(financial_eps, "request_text", lambda *_args, **_kwargs: _csv("2", "49.33"))
    assert financial_eps.refresh_eps(path=path)["rows"] == 1
    assert financial_eps.get_latest_eps("2330", "TWSE", path=path)["basic_eps_ytd"] == 49.33
    monkeypatch.setattr(financial_eps, "request_text", lambda *_args, **_kwargs: _csv("3", "1.00", "3008"))
    financial_eps.refresh_eps(path=path)
    assert financial_eps.get_latest_eps("2330", "TWSE", path=path)["report_quarter"] == 2
    assert financial_eps.get_latest_eps("3008", "TWSE", path=path)["report_quarter"] == 3
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM stock_eps_quarterly").fetchone()[0] == 2
