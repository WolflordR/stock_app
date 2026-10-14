"""Read one broker branch's daily net-buy/net-sell stocks from local data.

Broker execution prices and shares come from imported TWSE reports. Stock
liquidity and price momentum use the same-date local price cache; missing
same-date quotes stay null instead of silently using a newer trading day.
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from modules.core.project_paths import db_path


SortKey = Literal["net_shares", "volume", "turnover_value", "volume_ratio", "change_pct"]
Side = Literal["buy", "sell"]


def _connect_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def _quoted_metrics(history: list[dict[str, Any]], trade_date: str) -> dict[str, float | None]:
    """The ratio uses the preceding five positive-volume trading observations."""
    ordered = sorted(
        (row for row in history if row["volume"] is not None and row["close"] is not None
         and row["volume"] > 0 and row["close"] > 0 and row["trade_date"] <= trade_date),
        key=lambda row: row["trade_date"],
        reverse=True,
    )
    if not ordered or ordered[0]["trade_date"] != trade_date:
        return {"volume": None, "turnover_value": None, "volume_ratio": None, "change_pct": None}
    current = ordered[0]
    earlier = ordered[1:]
    average = sum(row["volume"] for row in earlier[:5]) / 5 if len(earlier) >= 5 else None
    previous_close = earlier[0]["close"] if earlier else None
    return {
        "volume": float(current["volume"]),
        "turnover_value": float(current["close"] * current["volume"]),
        "volume_ratio": float(current["volume"] / average) if average and average > 0 else None,
        "change_pct": float((current["close"] / previous_close - 1) * 100) if previous_close and previous_close > 0 else None,
    }


def _stock_metadata(path: Path, market: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with closing(_connect_readonly(path)) as conn:
        return {str(row["code"]): {"name": str(row["name_zh"] or ""), "symbol": str(row["yfinance_symbol"] or "")}
                for row in conn.execute("SELECT code,name_zh,yfinance_symbol FROM securities WHERE market=?", (market,))}


def _stock_quotes(path: Path, symbols: list[str], trade_date: str) -> dict[str, dict[str, float | None]]:
    if not path.exists() or not symbols:
        return {}
    earliest = (date.fromisoformat(trade_date) - timedelta(days=45)).isoformat()
    histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with closing(_connect_readonly(path)) as conn:
        for start in range(0, len(symbols), 400):
            batch = symbols[start:start + 400]
            placeholders = ",".join("?" for _ in batch)
            for row in conn.execute(
                f"SELECT symbol,trade_date,close,volume FROM price_history WHERE symbol IN ({placeholders}) AND trade_date BETWEEN ? AND ? ORDER BY symbol,trade_date DESC",
                (*batch, earliest, trade_date),
            ):
                histories[str(row["symbol"])].append(dict(row))
    return {symbol: _quoted_metrics(history, trade_date) for symbol, history in histories.items()}


def list_broker_branch_stocks(
    broker_name: str,
    trade_date: str,
    *,
    side: Side = "buy",
    sort_by: SortKey = "net_shares",
    descending: bool = True,
    limit: int = 50,
    offset: int = 0,
    market: str = "TWSE",
    broker_db: Path | None = None,
    stock_db: Path | None = None,
    price_db: Path | None = None,
) -> dict[str, Any]:
    normalized_name = broker_name.strip()
    date.fromisoformat(trade_date)
    if not normalized_name or side not in {"buy", "sell"} or sort_by not in {"net_shares", "volume", "turnover_value", "volume_ratio", "change_pct"}:
        raise ValueError("Invalid broker branch stock selection")
    if market not in {"TWSE", "TPEx"}:
        raise ValueError("Invalid market")
    stored_market = "TPEX" if market == "TPEx" else market
    if not 1 <= limit <= 100 or offset < 0:
        raise ValueError("Invalid pagination")
    broker_db = Path(broker_db or db_path("broker_daily_trades.db"))
    stock_db = Path(stock_db or db_path("stocks.db"))
    price_db = Path(price_db or db_path("price_cache.db"))
    raw_rows: list[sqlite3.Row] = []
    if broker_db.exists():
        with closing(_connect_readonly(broker_db)) as conn:
            raw_rows = conn.execute(
                """
                SELECT stock_code, SUM(buy_shares) AS buy_shares, SUM(sell_shares) AS sell_shares,
                       SUM(CASE WHEN price > 0 THEN price * buy_shares ELSE 0 END) AS buy_amount,
                       SUM(CASE WHEN price > 0 THEN price * sell_shares ELSE 0 END) AS sell_amount,
                       SUM(CASE WHEN price > 0 THEN buy_shares ELSE 0 END) AS priced_buy_shares,
                       SUM(CASE WHEN price > 0 THEN sell_shares ELSE 0 END) AS priced_sell_shares
                FROM broker_trade_lines
                WHERE market=? AND trade_date=? AND broker_name=?
                GROUP BY stock_code
                HAVING SUM(buy_shares) > 0 OR SUM(sell_shares) > 0
                """,
                (stored_market, trade_date, normalized_name),
            ).fetchall()
    metadata = _stock_metadata(stock_db, market)
    symbols = [metadata.get(str(row["stock_code"]), {}).get("symbol", "") for row in raw_rows]
    prices = _stock_quotes(price_db, [symbol for symbol in symbols if symbol], trade_date)
    rows = []
    for raw in raw_rows:
        code = str(raw["stock_code"])
        buy_shares = float(raw["buy_shares"] or 0)
        sell_shares = float(raw["sell_shares"] or 0)
        net_shares = buy_shares - sell_shares
        if (side == "buy" and net_shares <= 0) or (side == "sell" and net_shares >= 0):
            continue
        info = metadata.get(code, {})
        metrics = prices.get(info.get("symbol", ""), {})
        buy_complete = buy_shares > 0 and abs(float(raw["priced_buy_shares"] or 0) - buy_shares) < 0.001
        sell_complete = sell_shares > 0 and abs(float(raw["priced_sell_shares"] or 0) - sell_shares) < 0.001
        rows.append({
            "stock_code": code,
            "stock_name": info.get("name") or code,
            "market": market,
            "trade_date": trade_date,
            "buy_shares": buy_shares,
            "sell_shares": sell_shares,
            "net_shares": net_shares,
            "buy_amount": float(raw["buy_amount"] or 0) if buy_complete else None,
            "sell_amount": float(raw["sell_amount"] or 0) if sell_complete else None,
            "avg_buy_price": float(raw["buy_amount"] / buy_shares) if buy_complete else None,
            "avg_sell_price": float(raw["sell_amount"] / sell_shares) if sell_complete else None,
            "stock_volume_shares": metrics.get("volume"),
            "estimated_trade_value": metrics.get("turnover_value"),
            "volume_ratio": metrics.get("volume_ratio"),
            "change_pct": metrics.get("change_pct"),
        })
    field = {"net_shares": "net_shares", "volume": "stock_volume_shares", "turnover_value": "estimated_trade_value", "volume_ratio": "volume_ratio", "change_pct": "change_pct"}[sort_by]
    rows.sort(key=lambda row: row["stock_code"])
    rows.sort(
        key=lambda row: (
            row[field] is None,
            0 if row[field] is None else
            (-1 if descending else 1) * (abs(row[field]) if sort_by == "net_shares" else row[field]),
        )
    )
    return {
        "broker_name": normalized_name,
        "market": market,
        "trade_date": trade_date,
        "side": side,
        "sort_by": sort_by,
        "descending": descending,
        "total": len(rows),
        "quoted_count": sum(row["stock_volume_shares"] is not None for row in rows),
        "limit": limit,
        "offset": offset,
        "rows": rows[offset:offset + limit],
        "broker_source": "TWSE 官方分點成交日報匯入" if market == "TWSE" else "本地分點成交日報匯入",
        "price_source": "本地 yfinance 股價快取",
    }
