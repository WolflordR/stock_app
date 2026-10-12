from __future__ import annotations

from datetime import date

from modules.data_sources import financial_trends as ft


def test_mops_parser_preserves_zero_and_missing_gross_margin():
    html = """<table><tr><th>公司 代號</th><th>營業收入</th><th>營業毛利（毛損）淨額</th>
        <th>基本每股盈餘（元）</th></tr>
        <tr><td>2330</td><td>1,000</td><td>400</td><td>0</td></tr></table>
        <table><tr><th>公司 代號</th><th>收益</th><th>基本每股盈餘（元）</th></tr>
        <tr><td>2881</td><td>900</td><td>1.50</td></tr></table>"""
    rows = ft.parse_mops_income_html(html, "TWSE", 2026, 2, "source")
    assert rows[0]["basic_eps_ytd"] == 0
    assert rows[0]["gross_profit_ytd"] == 400
    assert rows[1]["gross_profit_ytd"] is None


def test_single_quarter_eps_and_gross_margin_use_same_year_difference(tmp_path):
    path = tmp_path / "financial.db"
    with ft._connect(path) as conn:
        for year, quarter, revenue, gross, eps in [
            (2025, 3, 300, 120, 6.0), (2025, 4, 500, 180, 8.0),
            (2026, 1, 150, 75, 2.0), (2026, 2, 350, 175, 5.5),
        ]:
            conn.execute("""INSERT INTO stock_income_quarterly VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         ("TWSE", "2330", year, quarter, revenue, gross, eps, "official", "first", "now"))
    result = ft.get_stock_financial_trends("2330", "TWSE", path=path, refresh_pe=False)
    rows = result["quarters"]
    assert rows[1]["period"] == "2025 Q4"
    assert rows[1]["eps_single_quarter"] == 2.0
    assert rows[1]["gross_margin_pct"] == 30.0
    assert rows[2]["eps_single_quarter"] == 2.0
    assert rows[3]["eps_single_quarter"] == 3.5
    assert rows[3]["gross_margin_pct"] == 50.0


def test_missing_preceding_quarter_is_not_filled_with_ytd(tmp_path):
    path = tmp_path / "financial.db"
    with ft._connect(path) as conn:
        conn.execute("""INSERT INTO stock_income_quarterly VALUES (?,?,?,?,?,?,?,?,?,?)""",
                     ("TPEx", "6488", 2026, 2, 350, 175, 5.5, "official", "first", "now"))
    row = ft.get_stock_financial_trends("6488", "TPEx", path=path, refresh_pe=False)["quarters"][0]
    assert row["eps_single_quarter"] is None
    assert row["gross_margin_pct"] is None


def test_tpex_pe_requires_requested_date_and_does_not_turn_missing_into_zero():
    payload = {"tables": [{"date": "115/09/30", "fields": ["股票代號", "本益比"],
                           "data": [["6488", "--"]]}]}
    row = ft._parse_tpex_pe(payload, "6488", date(2026, 9, 30), "now")
    assert row and row["pe_ratio"] is None
    assert ft._parse_tpex_pe(payload, "6488", date(2026, 9, 29), "now") is None


def test_refresh_is_resumable_and_keeps_first_observation(tmp_path, monkeypatch):
    path = tmp_path / "financial.db"
    html = """<table><tr><th>公司 代號</th><th>營業收入</th><th>營業毛利（毛損）</th>
        <th>基本每股盈餘（元）</th></tr><tr><td>2330</td><td>100</td><td>40</td><td>1</td></tr></table>"""
    calls = []
    monkeypatch.setattr(ft, "request_text", lambda url, **_kwargs: calls.append(url) or html)
    first = ft.refresh_financial_history(path=path, lookback_quarters=1, max_requests=2,
                                         recent_quarters=0, today=date(2026, 10, 11))
    assert first["requests"] == 2
    assert ft.refresh_financial_history(path=path, lookback_quarters=1, max_requests=2,
                                        recent_quarters=0, today=date(2026, 10, 11))["requests"] == 0
    assert len(calls) == 2
    with ft._connect(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM stock_income_quarterly").fetchone()[0] == 2
        assert conn.execute("SELECT first_observed_at FROM stock_income_quarterly LIMIT 1").fetchone()[0]
