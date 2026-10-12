"""Daily snapshots of the site's existing three buy strategies."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from modules.backtest.signals.initial_rise import analyze_initial_rise_candidate
from modules.backtest.signals.technical_patterns import analyze_bowl_bottom_volume_candidate, analyze_near_breakout_candidate
from modules.core.project_paths import PROJECT_ROOT, db_path

DB_PATH = db_path("dashboard_signals.db")
PRICE_DB = db_path("price_cache.db")
STRATEGIES = {
    "early_momentum": analyze_initial_rise_candidate,
    "near_breakout": analyze_near_breakout_candidate,
    "bowl_bottom": analyze_bowl_bottom_volume_candidate,
}


def migrate(path: Path = DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript((PROJECT_ROOT / "migrations" / "20261009_dashboard_signals.sql").read_text())


def _matched(frame: pd.DataFrame, analyzer) -> dict | None:
    try:
        result = analyzer(frame)
        return result if result and result.get("matched") else None
    except (ValueError, IndexError, KeyError, TypeError, ZeroDivisionError):
        return None


def refresh_signals(*, path: Path = DB_PATH, price_path: Path = PRICE_DB, anchor: str | None = None) -> dict:
    migrate(path)
    with sqlite3.connect(price_path) as conn:
        anchor = anchor or conn.execute("SELECT MAX(trade_date) FROM price_history WHERE trade_date<=?", (date.today().isoformat(),)).fetchone()[0]
        if not anchor:
            return {"date": None, "observed": 0, "signals": 0}
        cutoff = (date.fromisoformat(anchor) - timedelta(days=420)).isoformat()
        # Bounded, date-indexed read of cached OHLCV. No live per-symbol calls.
        conn.execute("CREATE INDEX IF NOT EXISTS idx_price_history_trade_date ON price_history(trade_date,symbol)")
        rows = conn.execute("SELECT symbol,trade_date,open,high,low,close,volume FROM price_history WHERE trade_date BETWEEN ? AND ? ORDER BY symbol,trade_date", (cutoff, anchor))
        by_symbol = defaultdict(list)
        for row in rows:
            if row[0].endswith((".TW", ".TWO")):
                by_symbol[row[0]].append(row)
    now = datetime.now().isoformat(timespec="seconds")
    output = []
    observed = 0
    for symbol, rows in by_symbol.items():
        if len(rows) < 22 or rows[-1][1] != anchor:
            continue
        observed += 1
        frame = pd.DataFrame(rows[-290:], columns=["symbol", "Date", "Open", "High", "Low", "Close", "Volume"])
        frame.index = pd.to_datetime(frame.pop("Date"))
        frame = frame.drop(columns="symbol")
        if not frame["Close"].iloc[-2]:
            continue
        change_pct = round((frame["Close"].iloc[-1] / frame["Close"].iloc[-2] - 1) * 100, 2)
        stock_id = symbol.split(".")[0]
        for key, analyzer in STRATEGIES.items():
            current = _matched(frame, analyzer)
            if not current:
                continue
            previous = _matched(frame.iloc[:-1], analyzer)
            output.append((anchor, stock_id, key, float(frame["Close"].iloc[-1]), change_pct,
                           current.get("volume_ratio_today") or current.get("latest_volume_ratio") or current.get("volume_ratio"),
                           current.get("distance_to_high_pct"), int(previous is None), now))
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM daily_signals WHERE signal_date=?", (anchor,))
        conn.executemany("INSERT INTO daily_signals VALUES (?,?,?,?,?,?,?,?,?)", output)
    return {"date": anchor, "observed": observed, "signals": len(output), "new": sum(row[7] for row in output)}
