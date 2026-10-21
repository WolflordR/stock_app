import pandas as pd

from modules.backtest import backtest_engine
from modules.backtest.signals.pullback import analyze_high_price_pullback_candidate
from modules.backtest.signals.registry import evaluate_registered_buy_strategies, get_buy_strategy_history_buffer_days
from modules.backtest.strategy_config import BUY_STRATEGY_METADATA


STRATEGY = "市值前五十大回檔超過40%"


def _price_history(close):
    dates = pd.bdate_range("2025-01-01", periods=252)
    return pd.DataFrame(
        {"High": [100.0] + [90.0] * 251, "Close": [90.0] * 251 + [close], "Volume": [10.0] * 252},
        index=dates,
    )


def test_deep_pullback_requires_top_50_and_strictly_more_than_40_percent():
    params = {
        "stock_id": "2330.TW",
        "deep_market_cap_pullback_eligible_symbol_set": {"2330.TW"},
        "high_price_pullback_lookback_days": 20,
        "high_price_pullback_market_cap_rank_limit": 100,
        "high_price_pullback_min_drop_pct": 10,
    }
    assert STRATEGY in BUY_STRATEGY_METADATA
    assert get_buy_strategy_history_buffer_days([STRATEGY]) >= 450

    matched, setup = evaluate_registered_buy_strategies(_price_history(60.0), [STRATEGY], params=params)
    assert not matched
    assert setup["high_price_pullback_depth_pct"] == 40.0

    matched, setup = evaluate_registered_buy_strategies(_price_history(59.0), [STRATEGY], params=params)
    assert matched
    assert setup["high_price_pullback_depth_pct"] == 41.0
    assert setup["high_price_pullback_lookback_days"] == 252
    assert setup["high_price_pullback_market_cap_rank_limit"] == 50
    assert setup["high_price_pullback_min_drop_pct"] == 40.0

    params["deep_market_cap_pullback_eligible_symbol_set"] = {"2317.TW"}
    matched, _ = evaluate_registered_buy_strategies(_price_history(59.0), [STRATEGY], params=params)
    assert not matched


def test_existing_pullback_uses_drop_from_high_as_denominator():
    analysis = analyze_high_price_pullback_candidate(
        _price_history(86.0), lookback_days=252, eligible_symbol_set={"2330"}, stock_id="2330.TW", min_drop_pct=15,
    )
    assert analysis["pullback_depth_pct"] == 14.0
    assert not analysis["matched"]


def test_scan_loads_top_50_for_new_strategy(monkeypatch):
    calls = []
    monkeypatch.setattr(backtest_engine, "ensure_stock_db", lambda: None)
    monkeypatch.setattr(backtest_engine, "get_securities_in_range", lambda _start, _end: [
        {"yfinance_symbol": "2330.TW"}, {"yfinance_symbol": "2317.TW"},
    ])
    monkeypatch.setattr(backtest_engine, "_resolve_scan_trade_date_text", lambda **_kwargs: "2026-10-20")
    monkeypatch.setattr(backtest_engine, "_load_market_cap_leader_symbol_set", lambda day, rank: calls.append((day, rank)) or frozenset({"2330.TW"}))
    monkeypatch.setattr(backtest_engine, "check_stock", lambda *args, **kwargs: calls.append((args, kwargs)) or {"price": 59.0})

    result = backtest_engine.scan_market(2330, 2330, [STRATEGY], request_delay_sec=0)
    assert result == {"2330.TW": {"price": 59.0}}
    assert calls[0] == ("2026-10-20", 50)
    assert calls[1][0][-1] >= 450
    assert calls[1][1]["deep_market_cap_pullback_eligible_symbol_set"] == frozenset({"2330.TW"})
    assert len(calls) == 2


def test_new_strategy_has_no_unrequested_turnover_filter(monkeypatch):
    monkeypatch.setattr(backtest_engine, "fetch_price_history", lambda *_args, **_kwargs: _price_history(59.0))
    monkeypatch.setattr(backtest_engine, "get_chinese_name", lambda _stock_id: "測試公司")

    result = backtest_engine.check_stock(
        "2330.TW", [STRATEGY], min_turnover_value=100_000_000,
        deep_market_cap_pullback_eligible_symbol_set={"2330.TW"},
    )
    assert result is not None
    assert result["high_price_pullback_depth_pct"] == 41.0


def test_nas_enables_only_the_new_live_screen(monkeypatch):
    from fastapi.testclient import TestClient
    from apps.api import main as api_main

    monkeypatch.setenv("TRADE_ENABLE_BACKTEST", "0")
    monkeypatch.setattr(api_main.backtest_jobs, "start_job", lambda _request: "test-job")
    client = TestClient(api_main.app)

    response = client.post("/api/backtest/jobs", json={"selected_strategies": [STRATEGY], "mode": "即時選股"})
    assert response.status_code == 200
    assert response.json()["job_id"] == "test-job"

    response = client.post("/api/backtest/jobs", json={"selected_strategies": ["高價股回檔"], "mode": "即時選股"})
    assert response.status_code == 503

    response = client.post("/api/backtest/jobs", json={"selected_strategies": [STRATEGY], "mode": "歷史回測"})
    assert response.status_code == 503
