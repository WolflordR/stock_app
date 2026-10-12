"""Persist official daily stock limit-up/down counts for the home dashboard."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import requests

from modules.data_sources.chip_trends import connect, integer

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_URL = "https://app.tpex.org.tw/data/15.json"


def parse_twse_limits(payload: dict[str, Any], requested: date) -> dict[str, Any] | None:
    if payload.get("stat") != "OK" or payload.get("date") != requested.strftime("%Y%m%d"):
        return None
    table = next((item for item in payload.get("tables", []) if item.get("title") == "漲跌證券數合計"), None)
    if not table or table.get("fields") != ["類型", "整體市場", "股票"]:
        raise ValueError("TWSE stock limit summary missing or changed")
    counts = {}
    for label, _all_securities, stocks in table.get("data", []):
        if label in ("上漲(漲停)", "下跌(跌停)"):
            parts = str(stocks).replace(",", "").split("(")
            if len(parts) != 2 or not parts[1].endswith(")"):
                raise ValueError("TWSE stock limit count format changed")
            counts[label] = int(parts[1][:-1])
    if set(counts) != {"上漲(漲停)", "下跌(跌停)"}:
        raise ValueError("TWSE stock limit counts missing")
    return {"market": "TWSE", "trade_date": requested.isoformat(), "limit_up_count": counts["上漲(漲停)"], "limit_down_count": counts["下跌(跌停)"]}


def parse_tpex_limits(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("stat") != "ok":
        return None
    day_text = str(payload.get("date", ""))
    if len(day_text) != 8 or not day_text.isdigit():
        raise ValueError("TPEx limit summary date missing")
    day = datetime.strptime(day_text, "%Y%m%d").date()
    table = next((item for item in payload.get("tables", []) if item.get("title") == "上櫃股票當日彙總資訊"), None)
    if not table or len(table.get("data", [])) != 1:
        raise ValueError("TPEx stock limit summary missing or changed")
    fields = table.get("fields", [])
    row = table["data"][0]
    try:
        up, down = (integer(row[fields.index(label)]) for label in ("漲停家數", "跌停家數"))
    except (ValueError, IndexError) as exc:
        raise ValueError("TPEx stock limit fields changed") from exc
    if up is None or down is None:
        raise ValueError("TPEx stock limit counts missing")
    return {"market": "TPEx", "trade_date": day.isoformat(), "limit_up_count": up, "limit_down_count": down}


def refresh_market_limits(*, session: requests.Session | None = None, path: str | None = None, end: date | None = None) -> dict[str, Any]:
    """Read TWSE's small market-summary payload and TPEx's latest stock summary.

    A failure in one exchange leaves the other exchange's saved data intact.
    """
    client = session or requests.Session()
    end = end or date.today()
    result: dict[str, Any] = {"markets": {}, "errors": {}}
    with connect(path) as conn:
        for market in ("TWSE", "TPEx"):
            try:
                if market == "TWSE":
                    parsed = None
                    source_url = None
                    for offset in range(7):
                        day = end - timedelta(days=offset)
                        if day.weekday() >= 5:
                            continue
                        response = client.get(TWSE_URL, params={"date": day.strftime("%Y%m%d"), "type": "MS", "response": "json"}, timeout=25)
                        response.raise_for_status()
                        parsed = parse_twse_limits(response.json(), day)
                        if parsed:
                            source_url = response.url
                            break
                else:
                    response = client.get(TPEX_URL, timeout=25)
                    response.raise_for_status()
                    parsed = parse_tpex_limits(response.json())
                    source_url = response.url
                    if parsed and parsed["trade_date"] > end.isoformat():
                        parsed = None
                if parsed is None:
                    result["markets"][market] = "no_report"
                    continue
                with conn:
                    conn.execute("""INSERT INTO market_limit_daily(market,trade_date,limit_up_count,limit_down_count,source_url,updated_at)
                        VALUES(?,?,?,?,?,?) ON CONFLICT(market,trade_date) DO UPDATE SET
                        limit_up_count=excluded.limit_up_count,limit_down_count=excluded.limit_down_count,
                        source_url=excluded.source_url,updated_at=excluded.updated_at""",
                        (parsed["market"], parsed["trade_date"], parsed["limit_up_count"], parsed["limit_down_count"], source_url, datetime.now().isoformat(timespec="seconds")))
                result["markets"][market] = parsed
            except Exception as exc:
                result["errors"][market] = str(exc)
    return result
