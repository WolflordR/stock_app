"""Official stock-only daily turnover for the home market value ratio."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import requests

from modules.data_sources.chip_trends import connect, integer

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/highlight"


def parse_twse_turnover(payload: dict[str, Any], requested: date) -> int | None:
    if payload.get("stat") != "OK" or payload.get("date") != requested.strftime("%Y%m%d"):
        return None
    table = next((item for item in payload.get("tables", []) if item.get("fields") == ["成交統計", "成交金額(元)", "成交股數(股)", "成交筆數"]), None)
    if table is None:
        raise ValueError("TWSE turnover summary missing or changed")
    matches = [row for row in table.get("data", []) if str(row[0]).startswith("證券合計(")]
    if len(matches) != 1:
        raise ValueError("TWSE stock-only turnover total missing")
    amount = integer(matches[0][1])
    if amount is None or amount < 0:
        raise ValueError("TWSE stock-only turnover amount invalid")
    return amount


def parse_tpex_turnover(payload: dict[str, Any], requested: date) -> int | None:
    if payload.get("stat") != "ok" or payload.get("date") != requested.strftime("%Y%m%d"):
        return None
    table = next((item for item in payload.get("tables", []) if item.get("title") == "上櫃股票當日彙總資訊"), None)
    if table is None or len(table.get("data", [])) != 1:
        raise ValueError("TPEx stock-only turnover summary missing")
    fields = table.get("fields", [])
    if "本日總成交值(佰萬元)" not in fields:
        raise ValueError("TPEx stock turnover field changed")
    million_twd = integer(table["data"][0][fields.index("本日總成交值(佰萬元)")])
    if million_twd is None or million_twd < 0:
        raise ValueError("TPEx stock turnover amount invalid")
    return million_twd * 1_000_000


def refresh_turnover_recent(*, days: int = 18, end: date | None = None, path: str | None = None, session: requests.Session | None = None) -> dict[str, Any]:
    """Backfill recent official trading days; preserve saved values on source failure."""
    end = end or date.today()
    client = session or requests.Session()
    result: dict[str, Any] = {"saved": {"TWSE": 0, "TPEx": 0}, "errors": []}
    with connect(path) as conn:
        existing = {(row[0], row[1]) for row in conn.execute("SELECT market,trade_date FROM market_turnover_daily WHERE trade_date BETWEEN ? AND ?", ((end - timedelta(days=days-1)).isoformat(), end.isoformat()))}
        for offset in range(days - 1, -1, -1):
            day = end - timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            for market, url, params, parser in (
                ("TWSE", TWSE_URL, {"date": day.strftime("%Y%m%d"), "type": "MS", "response": "json"}, parse_twse_turnover),
                ("TPEx", TPEX_URL, {"date": f"{day.year-1911}/{day:%m/%d}"}, parse_tpex_turnover),
            ):
                if (market, day.isoformat()) in existing:
                    continue
                try:
                    response = client.get(url, params=params, timeout=25)
                    response.raise_for_status()
                    amount = parser(response.json(), day)
                    if amount is None:
                        continue
                    with conn:
                        conn.execute("INSERT OR REPLACE INTO market_turnover_daily(market,trade_date,amount_twd,source_url,updated_at) VALUES (?,?,?,?,?)",
                                     (market, day.isoformat(), amount, response.url, datetime.now().isoformat(timespec="seconds")))
                    result["saved"][market] += 1
                except Exception as exc:
                    result["errors"].append({"market": market, "date": day.isoformat(), "error": str(exc)})
    return result


def turnover_ratio(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Latest amount divided by the five *preceding* observed trading days."""
    if not rows:
        return None
    rows = sorted(rows, key=lambda row: row["trade_date"])
    latest, prior = rows[-1], rows[-6:-1]
    average = sum(row["amount_twd"] for row in prior) / 5 if len(prior) == 5 else None
    return {"trade_date": latest["trade_date"], "amount_twd": latest["amount_twd"],
            "average5_twd": round(average) if average is not None else None,
            "ratio": round(latest["amount_twd"] / average, 3) if average and average > 0 else None,
            "baseline_dates": [row["trade_date"] for row in prior] if len(prior) == 5 else [],
            "source_urls": latest["source_urls"]}


def market_turnover_ratios(*, path: str | None = None) -> dict[str, Any]:
    with connect(path) as conn:
        rows = [dict(row) for row in conn.execute("SELECT market,trade_date,amount_twd,source_url FROM market_turnover_daily WHERE trade_date<=? ORDER BY trade_date DESC LIMIT 150", (date.today().isoformat(),))]
    by_market = {market: [{**row, "source_urls": {market: row["source_url"]}} for row in rows if row["market"] == market] for market in ("TWSE", "TPEx")}
    result = {market: turnover_ratio(values) for market, values in by_market.items()}
    twse = {row["trade_date"]: row for row in by_market["TWSE"]}
    tpex = {row["trade_date"]: row for row in by_market["TPEx"]}
    paired = [{"trade_date": day, "amount_twd": twse[day]["amount_twd"] + tpex[day]["amount_twd"],
               "source_urls": {"TWSE": twse[day]["source_url"], "TPEx": tpex[day]["source_url"]}}
              for day in twse.keys() & tpex.keys()]
    result["combined"] = turnover_ratio(paired)
    return result
