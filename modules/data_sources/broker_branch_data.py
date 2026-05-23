from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from modules.core.http_utils import request_text
from modules.data_sources.official_broker_import import (
    get_latest_official_broker_summary,
    get_official_broker_summary,
)
from modules.data_sources.stock_db import find_security, get_stock_name


YAHOO_STOCK_BASE_URL = "https://tw.stock.yahoo.com"


def _normalize_stock_code(stock_input: str) -> str:
    code = (stock_input or "").strip().upper().split(".")[0]
    return "".join(ch for ch in code if ch.isdigit())


def _clean_text(value: str) -> str:
    return (value or "").replace("\xa0", " ").strip()


def _safe_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if text in {"", "-", "--", "---", "－", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_lots(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}"


def _format_price(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _clean_stock_title(value: str) -> str:
    text = _clean_text(value)
    for token in ["籌碼相關", "券商分點績效", "獲利分析", "－", "-", "—"]:
        if token in text:
            text = text.split(token)[0].strip()
    return text


def _candidate_yahoo_symbols(stock_code: str) -> list[str]:
    security = find_security(stock_code)
    symbols: list[str] = []
    if security and security.get("yfinance_symbol"):
        symbols.append(str(security["yfinance_symbol"]).upper())

    for suffix in (".TW", ".TWO"):
        candidate = f"{stock_code}{suffix}"
        if candidate not in symbols:
            symbols.append(candidate)
    return symbols


def _normalize_market_code(market: str | None) -> str:
    text = str(market or "").strip().upper()
    if text in {"TWSE", "上市"}:
        return "TWSE"
    if text in {"TPEX", "TWO", "OTC", "上櫃"}:
        return "TPEX"
    return text or "TWSE"


def _extract_root_app_json(html: str) -> dict[str, Any]:
    matched = re.search(
        r"root\.App\.main\s*=\s*(\{.*?\})\s*;\s*}\(this\)\);",
        html,
        re.S,
    )
    if not matched:
        raise ValueError("Yahoo 頁面結構已變動，暫時抓不到籌碼資料。")

    raw = matched.group(1)
    clean = re.sub(r"\bundefined\b", "null", raw)
    clean = re.sub(r"\bNaN\b", "null", clean)
    clean = re.sub(r"\b-Infinity\b", "null", clean)
    clean = re.sub(r"\bInfinity\b", "null", clean)
    return json.loads(clean)


def _load_yahoo_broker_payload(stock_code: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for yahoo_symbol in _candidate_yahoo_symbols(stock_code):
        url = f"{YAHOO_STOCK_BASE_URL}/quote/{yahoo_symbol}/broker-trading"
        try:
            html = request_text(
                url,
                headers={
                    "Referer": f"{YAHOO_STOCK_BASE_URL}/quote/{yahoo_symbol}",
                    "User-Agent": "Mozilla/5.0",
                },
                timeout=20,
            )
            root = _extract_root_app_json(html)
            stores = root["context"]["dispatcher"]["stores"]
            broker_trades = ((stores.get("QuoteChipStore") or {}).get("brokerTrades") or {}).get("data") or {}
            if broker_trades.get("buyerRankList") or broker_trades.get("sellerRankList"):
                return {
                    "yahoo_symbol": yahoo_symbol,
                    "source_url": url,
                    "data": broker_trades,
                }
            last_error = ValueError("Yahoo 籌碼頁目前沒有回傳買賣分點榜。")
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    raise ValueError(f"目前抓不到 Yahoo 主力進出資料：{last_error}") from last_error


@dataclass
class BrokerBranchRow:
    broker_branch: str
    performance_pct: str
    total_profit_k: str
    realized_profit_k: str
    unrealized_profit_k: str
    net_shares: str
    buy_shares: str
    sell_shares: str
    avg_price: str
    avg_buy: str
    avg_sell: str
    close_price: str
    detail_url: str

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "分點": self.broker_branch,
            "績效": self.performance_pct,
            "總損益(仟)": self.total_profit_k,
            "已實現(仟)": self.realized_profit_k,
            "未實現(仟)": self.unrealized_profit_k,
            "買賣超": self.net_shares,
            "買張": self.buy_shares,
            "賣張": self.sell_shares,
            "均價": self.avg_price,
            "均買": self.avg_buy,
            "均賣": self.avg_sell,
            "現價": self.close_price,
        }


def _build_row(entry: dict[str, Any]) -> BrokerBranchRow:
    buy_lots = _safe_float(entry.get("buyVolK"))
    sell_lots = _safe_float(entry.get("sellVolK"))
    net_lots = _safe_float(entry.get("volume"))

    return BrokerBranchRow(
        broker_branch=_clean_text(entry.get("name") or "-"),
        performance_pct="-",
        total_profit_k="-",
        realized_profit_k="-",
        unrealized_profit_k="-",
        net_shares=_format_lots(net_lots),
        buy_shares=_format_lots(buy_lots),
        sell_shares=_format_lots(sell_lots),
        avg_price="-",
        avg_buy="-",
        avg_sell="-",
        close_price="-",
        detail_url="",
    )


def _build_official_row(entry: dict[str, Any], *, side: str) -> BrokerBranchRow:
    net_lots = _safe_float(entry.get("net_shares"))
    buy_lots = _safe_float(entry.get("buy_shares"))
    sell_lots = _safe_float(entry.get("sell_shares"))
    avg_price = None
    if side == "buy":
        avg_price = _safe_float(entry.get("avg_buy_price"))
    elif side == "sell":
        avg_price = _safe_float(entry.get("avg_sell_price"))
    if avg_price is None:
        avg_price = _safe_float(entry.get("avg_buy_price")) or _safe_float(entry.get("avg_sell_price"))

    return BrokerBranchRow(
        broker_branch=_clean_text(entry.get("broker_name") or "-"),
        performance_pct="-",
        total_profit_k="-",
        realized_profit_k="-",
        unrealized_profit_k="-",
        net_shares=_format_lots(net_lots),
        buy_shares=_format_lots(buy_lots),
        sell_shares=_format_lots(sell_lots),
        avg_price=_format_price(avg_price),
        avg_buy=_format_price(_safe_float(entry.get("avg_buy_price"))),
        avg_sell=_format_price(_safe_float(entry.get("avg_sell_price"))),
        close_price="-",
        detail_url="",
    )


def _build_official_summary_bundle(stock_code: str, official_summary: dict[str, Any], *, top_n: int) -> dict[str, Any]:
    stock_name = get_stock_name(stock_code)
    stock_title = _clean_stock_title(f"{stock_name} ({stock_code})")
    buy_rank = list(official_summary.get("buy_rank") or [])[:top_n]
    sell_rank = list(official_summary.get("sell_rank") or [])[:top_n]
    return {
        "stock_code": stock_code,
        "stock_title": stock_title,
        "trade_date": official_summary.get("trade_date") or "",
        "trade_volume_rate": None,
        "source_url": "",
        "source_label": "官方匯入分點日報",
        "buy_side": [_build_official_row(entry, side="buy") for entry in buy_rank],
        "sell_side": [_build_official_row(entry, side="sell") for entry in sell_rank],
    }


def fetch_broker_branch_summary(stock_input: str, *, top_n: int = 12, trade_date: str | None = None) -> dict[str, Any]:
    stock_code = _normalize_stock_code(stock_input)
    if not stock_code:
        raise ValueError("無法辨識股票代碼。")

    security = find_security(stock_code)
    market = _normalize_market_code((security or {}).get("market"))
    official_summary = (
        get_official_broker_summary(stock_code, trade_date, market=market)
        if trade_date
        else get_latest_official_broker_summary(stock_code, market=market)
    )
    if official_summary:
        return _build_official_summary_bundle(stock_code, official_summary, top_n=top_n)

    payload = _load_yahoo_broker_payload(stock_code)
    broker_data = payload["data"]
    buy_entries = list(broker_data.get("buyerRankList") or [])[:top_n]
    sell_entries = list(broker_data.get("sellerRankList") or [])[:top_n]

    stock_name = security.get("name_zh") if security else get_stock_name(stock_code)
    yahoo_symbol = payload["yahoo_symbol"]
    stock_title = _clean_stock_title(f"{stock_name} ({yahoo_symbol.split('.')[0]})")

    return {
        "stock_code": stock_code,
        "stock_title": stock_title,
        "trade_date": str(broker_data.get("date") or "").split("T")[0],
        "trade_volume_rate": _safe_float(broker_data.get("tradeVolumeRate")),
        "source_url": payload["source_url"],
        "source_label": "Yahoo 當日分點榜",
        "buy_side": [_build_row(entry) for entry in buy_entries],
        "sell_side": [_build_row(entry) for entry in sell_entries],
    }


def fetch_broker_branch_trace(detail_url: str, *, limit_rows: int = 30) -> dict[str, Any]:
    raise ValueError("Yahoo 來源目前只提供當日買賣分點榜，沒有單一分點歷史明細。")
