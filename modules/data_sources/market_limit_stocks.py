"""Verified limit-up/down stock lists from official daily prices and closes.

The daily worker collects these lists. API reads never download exchange data.
Lists are marked complete only when both directions match the saved official
stock-only market totals for the same trading date.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests

from modules.data_sources.chip_trends import connect
from modules.data_sources.market_watch import fetch_tpex_daily_quotes, fetch_twse_daily_quotes


TWSE_LIMIT_URL = "https://www.twse.com.tw/exchangeReport/TWT84U"
TWSE_QUOTE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_QUOTE_URL = "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php"


def _price(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def parse_twse_limit_prices(payload: dict[str, Any], requested: date) -> dict[str, tuple[Decimal, Decimal]] | None:
    if payload.get("stat") != "OK" or payload.get("date") != requested.strftime("%Y%m%d"):
        return None
    fields = payload.get("fields") or []
    required = ("證券代號", "漲停價", "跌停價")
    if any(field not in fields for field in required):
        raise ValueError("TWSE daily limit-price fields changed")
    code_index, up_index, down_index = (fields.index(field) for field in required)
    prices = {}
    for row in payload.get("data") or []:
        if len(row) <= max(code_index, up_index, down_index):
            continue
        code = str(row[code_index]).strip()
        up, down = _price(row[up_index]), _price(row[down_index])
        if len(code) == 4 and code.isdigit() and up is not None and down is not None:
            prices[code] = (up, down)
    if not prices:
        raise ValueError("TWSE daily limit-price report empty")
    return prices


def parse_tpex_next_limit_prices(payload: dict[str, Any], requested: date) -> dict[str, tuple[Decimal, Decimal]] | None:
    if payload.get("stat") != "ok" or payload.get("date") != requested.strftime("%Y%m%d"):
        return None
    tables = payload.get("tables") or []
    if not tables:
        raise ValueError("TPEx daily quote table missing")
    fields = [str(field).strip() for field in tables[0].get("fields") or []]
    required = ("代號", "次日漲停價", "次日跌停價")
    if any(field not in fields for field in required):
        raise ValueError("TPEx next-day limit-price fields changed")
    code_index, up_index, down_index = (fields.index(field) for field in required)
    prices = {}
    for row in tables[0].get("data") or []:
        if len(row) <= max(code_index, up_index, down_index):
            continue
        code = str(row[code_index]).strip()
        up, down = _price(row[up_index]), _price(row[down_index])
        if len(code) == 4 and code.isdigit() and up is not None and down is not None:
            prices[code] = (up, down)
    if not prices:
        raise ValueError("TPEx next-day limit-price report empty")
    return prices


def _tpex_previous_limits(client: requests.Session, trade_date: date) -> tuple[dict[str, tuple[Decimal, Decimal]], str]:
    for days_back in range(1, 11):
        previous = trade_date - timedelta(days=days_back)
        if previous.weekday() >= 5:
            continue
        response = client.get(TPEX_QUOTE_URL, params={"l": "zh-tw", "o": "json", "d": f"{previous.year - 1911:03d}/{previous.month:02d}/{previous.day:02d}", "se": "EW"}, timeout=25)
        response.raise_for_status()
        prices = parse_tpex_next_limit_prices(response.json(), previous)
        if prices is not None:
            return prices, response.url
    raise ValueError(f"TPEx previous trading-day limit prices missing for {trade_date}")


def _verified_rows(quotes: pd.DataFrame, prices: dict[str, tuple[Decimal, Decimal]], *, market: str, trade_date: str) -> list[dict[str, Any]]:
    if quotes.empty:
        raise ValueError(f"{market} daily quotes missing for {trade_date}")
    rows = []
    for quote in quotes.itertuples(index=False):
        code = str(quote.code).strip()
        limits = prices.get(code)
        close, volume = _price(quote.close), _price(quote.volume)
        if limits is None or close is None or volume is None:
            continue  # A suspended/no-trade security cannot appear on the list.
        direction = "up" if close == limits[0] else "down" if close == limits[1] else None
        if direction is None:
            continue
        rows.append({
            "market": market,
            "trade_date": trade_date,
            "stock_id": code,
            "name": str(quote.name).strip(),
            "direction": direction,
            "close": float(close),
            "limit_price": float(limits[0] if direction == "up" else limits[1]),
            "volume_shares": int(volume),
        })
    return rows


def refresh_market_limit_details(*, path: str | None = None, session: requests.Session | None = None, force: bool = False) -> dict[str, Any]:
    """Collect newest saved official summary date for each market, incrementally."""
    client = session or requests.Session()
    result: dict[str, Any] = {"markets": {}, "errors": {}}
    with connect(path) as conn:
        for market in ("TWSE", "TPEx"):
            summary = conn.execute(
                "SELECT trade_date,limit_up_count,limit_down_count FROM market_limit_daily WHERE market=? AND trade_date<=? ORDER BY trade_date DESC LIMIT 1",
                (market, date.today().isoformat()),
            ).fetchone()
            if summary is None:
                result["markets"][market] = "no_summary"
                continue
            trade_date = str(summary["trade_date"])
            previous = conn.execute(
                "SELECT status,observed_up,observed_down FROM market_limit_detail_status WHERE market=? AND trade_date=?",
                (market, trade_date),
            ).fetchone()
            if not force and previous and previous["status"] == "complete" and previous["observed_up"] == summary["limit_up_count"] and previous["observed_down"] == summary["limit_down_count"]:
                result["markets"][market] = "already_complete"
                continue
            try:
                day = date.fromisoformat(trade_date)
                if market == "TWSE":
                    response = client.get(TWSE_LIMIT_URL, params={"response": "json", "date": day.strftime("%Y%m%d")}, timeout=25)
                    response.raise_for_status()
                    prices = parse_twse_limit_prices(response.json(), day)
                    if prices is None:
                        raise ValueError(f"TWSE limit-price report not for {trade_date}")
                    limit_source_url = response.url
                    quote_source_url = f"{TWSE_QUOTE_URL}?{urlencode({'date': day.strftime('%Y%m%d'), 'type': 'ALLBUT0999', 'response': 'json'})}"
                    quotes = fetch_twse_daily_quotes(day)
                else:
                    prices, limit_source_url = _tpex_previous_limits(client, day)
                    quote_source_url = f"{TPEX_QUOTE_URL}?{urlencode({'l': 'zh-tw', 'o': 'json', 'd': f'{day.year - 1911:03d}/{day.month:02d}/{day.day:02d}', 'se': 'EW'})}"
                    quotes = fetch_tpex_daily_quotes(day)
                rows = _verified_rows(quotes, prices, market=market, trade_date=trade_date)
                observed_up = sum(row["direction"] == "up" for row in rows)
                observed_down = len(rows) - observed_up
                complete = observed_up == summary["limit_up_count"] and observed_down == summary["limit_down_count"]
                status = "complete" if complete else "mismatch"
                updated_at = datetime.now().isoformat(timespec="seconds")
                with conn:
                    # Preserve a previously verified list if a later fetch is partial.
                    if complete:
                        conn.execute("DELETE FROM market_limit_stock_daily WHERE market=? AND trade_date=?", (market, trade_date))
                        conn.executemany(
                            "INSERT INTO market_limit_stock_daily(market,trade_date,stock_id,name,direction,close,limit_price,volume_shares,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            [(row["market"], row["trade_date"], row["stock_id"], row["name"], row["direction"], row["close"], row["limit_price"], row["volume_shares"], updated_at) for row in rows],
                        )
                    if complete or not previous or previous["status"] != "complete":
                        conn.execute(
                            "INSERT INTO market_limit_detail_status(market,trade_date,status,observed_up,observed_down,limit_source_url,quote_source_url,updated_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(market,trade_date) DO UPDATE SET status=excluded.status,observed_up=excluded.observed_up,observed_down=excluded.observed_down,limit_source_url=excluded.limit_source_url,quote_source_url=excluded.quote_source_url,updated_at=excluded.updated_at",
                            (market, trade_date, status, observed_up, observed_down, limit_source_url, quote_source_url, updated_at),
                        )
                result["markets"][market] = {"status": status, "trade_date": trade_date, "observed_up": observed_up, "observed_down": observed_down}
                if not complete:
                    result["errors"][market] = f"{trade_date} official {summary['limit_up_count']}/{summary['limit_down_count']}, observed {observed_up}/{observed_down}"
            except Exception as exc:
                result["errors"][market] = str(exc)
    return result


def list_market_limit_stocks(*, direction: str, market: str = "combined", path: str | None = None) -> dict[str, Any]:
    """Return only lists reconciled with their same-day official market totals."""
    if direction not in {"up", "down"} or market not in {"TWSE", "TPEx", "combined"}:
        raise ValueError("Invalid market limit selection")
    with connect(path) as conn:
        summaries = {}
        for source in ("TWSE", "TPEx"):
            row = conn.execute(
                "SELECT market,trade_date,limit_up_count,limit_down_count,source_url FROM market_limit_daily WHERE market=? AND trade_date<=? ORDER BY trade_date DESC LIMIT 1",
                (source, date.today().isoformat()),
            ).fetchone()
            if row:
                summaries[source] = dict(row)
        selected = ("TWSE", "TPEx") if market == "combined" else (market,)
        dates = {summaries[source]["trade_date"] for source in selected if source in summaries}
        common_date = next(iter(dates)) if len(dates) == 1 and all(source in summaries for source in selected) else None
        statuses = {}
        rows = []
        for source in selected:
            summary = summaries.get(source)
            if not summary:
                statuses[source] = {"status": "no_summary", "date": None}
                continue
            status_row = conn.execute(
                "SELECT status,observed_up,observed_down,limit_source_url,quote_source_url,updated_at FROM market_limit_detail_status WHERE market=? AND trade_date=?",
                (source, summary["trade_date"]),
            ).fetchone()
            verified = bool(status_row and status_row["status"] == "complete" and status_row["observed_up"] == summary["limit_up_count"] and status_row["observed_down"] == summary["limit_down_count"])
            statuses[source] = {"status": "complete" if verified else "pending", "date": summary["trade_date"], "official_up": summary["limit_up_count"], "official_down": summary["limit_down_count"], "summary_source_url": summary["source_url"], "limit_source_url": status_row["limit_source_url"] if status_row else None, "quote_source_url": status_row["quote_source_url"] if status_row else None}
            if verified and (market != "combined" or common_date is not None):
                rows.extend(dict(row) for row in conn.execute(
                    "SELECT market,trade_date,stock_id,name,direction,close,limit_price,volume_shares FROM market_limit_stock_daily WHERE market=? AND trade_date=? AND direction=? ORDER BY volume_shares DESC,stock_id",
                    (source, summary["trade_date"], direction),
                ))
    official_count = sum(summaries[source]["limit_up_count" if direction == "up" else "limit_down_count"] for source in selected if source in summaries) if common_date else None
    rows.sort(key=lambda row: (-row["volume_shares"], row["stock_id"]))
    return {"direction": direction, "market": market, "date": common_date, "official_count": official_count, "rows": rows, "markets": statuses, "complete": common_date is not None and all(statuses.get(source, {}).get("status") == "complete" for source in selected)}
