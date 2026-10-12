from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from modules.core.http_utils import request_json, request_text


TWSE_VALUATION_URL = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
TPEX_VALUATION_URL = (
    "https://www.tpex.org.tw/web/stock/aftertrading/"
    "peratio_analysis/pera_result.php?l=zh-tw&o=csv&s=0"
)


def _number(value: object) -> float | None:
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _roc_date(value: str) -> str | None:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return None
    year = int(digits[:-4]) + 1911
    month = int(digits[-4:-2])
    day = int(digits[-2:])
    return f"{year:04d}-{month:02d}-{day:02d}"


@lru_cache(maxsize=8)
def _market_valuations(market: str, cache_day: str) -> dict[str, dict]:
    # The date is a cache key so a running API refreshes the official snapshot daily.
    if market == "TWSE":
        rows = request_json(TWSE_VALUATION_URL)
        return {
            str(row["Code"]).strip(): {
                "data_date": _roc_date(str(row.get("Date", ""))),
                "pe_ratio": _number(row.get("PEratio")),
                "dividend_yield_pct": _number(row.get("DividendYield")),
                "pb_ratio": _number(row.get("PBratio")),
            }
            for row in rows
            if str(row.get("Code", "")).strip().isdigit()
        }

    if market == "TPEx":
        text = request_text(TPEX_VALUATION_URL, encoding="cp950")
        lines = text.splitlines()
        data_date = _roc_date(lines[1]) if len(lines) > 1 else None
        return {
            str(row["股票代號"]).strip(): {
                "data_date": data_date,
                "pe_ratio": _number(row.get("本益比")),
                "dividend_yield_pct": _number(row.get("殖利率(%)")),
                "pb_ratio": _number(row.get("股價淨值比")),
            }
            for row in csv.DictReader(io.StringIO("\n".join(lines[3:])))
            if str(row.get("股票代號", "")).strip().isdigit()
        }

    return {}


def get_stock_valuation(stock_code: str, market: str) -> dict | None:
    cache_day = datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    try:
        return _market_valuations(market, cache_day).get(str(stock_code).strip())
    except (OSError, ValueError, KeyError, TypeError):
        return None
