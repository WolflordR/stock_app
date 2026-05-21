from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from modules.core.http_utils import request_text


HISTOCK_BASE_URL = "https://histock.tw"


def _normalize_stock_code(stock_input: str) -> str:
    code = (stock_input or "").strip().upper().split(".")[0]
    return "".join(ch for ch in code if ch.isdigit())


def _clean_text(value: str) -> str:
    return (value or "").replace("\xa0", " ").strip()


def _parse_float(value: str) -> float | None:
    text = _clean_text(value).replace(",", "").replace("%", "")
    if not text or text == "-":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: str) -> int | None:
    number = _parse_float(value)
    if number is None:
        return None
    return int(round(number))


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


def fetch_broker_branch_summary(stock_input: str, *, top_n: int = 12) -> dict[str, Any]:
    stock_code = _normalize_stock_code(stock_input)
    if not stock_code:
        raise ValueError("無法辨識股票代碼。")

    url = f"{HISTOCK_BASE_URL}/stock/mainprofit.aspx?no={stock_code}"
    html = request_text(url, headers={"Referer": f"{HISTOCK_BASE_URL}/stock/{stock_code}"})
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if len(tables) < 2:
        raise ValueError("目前抓不到券商分點總表。")

    def parse_table(table) -> list[BrokerBranchRow]:
        rows: list[BrokerBranchRow] = []
        for tr in table.find_all("tr")[1:]:
            cells = tr.find_all("td")
            if len(cells) < 13:
                continue
            link = tr.find("a", href=True)
            if not link:
                continue
            values = [_clean_text(td.get_text(" ", strip=True)) for td in cells]
            rows.append(
                BrokerBranchRow(
                    broker_branch=values[1],
                    performance_pct=values[2],
                    total_profit_k=values[3],
                    realized_profit_k=values[4],
                    unrealized_profit_k=values[5],
                    net_shares=values[6],
                    buy_shares=values[7],
                    sell_shares=values[8],
                    avg_price=values[9],
                    avg_buy=values[10],
                    avg_sell=values[11],
                    close_price=values[12],
                    detail_url=urljoin(HISTOCK_BASE_URL, link["href"]),
                )
            )
        return rows[:top_n]

    positive_rows = parse_table(tables[0])
    negative_rows = parse_table(tables[1])
    stock_name_node = soup.find("div", class_="ctname")
    stock_title = _clean_text(stock_name_node.get_text(" ", strip=True)) if stock_name_node else stock_code

    return {
        "stock_code": stock_code,
        "stock_title": stock_title,
        "source_url": url,
        "buy_side": positive_rows,
        "sell_side": negative_rows,
    }


def fetch_broker_branch_trace(detail_url: str, *, limit_rows: int = 30) -> dict[str, Any]:
    if not detail_url:
        raise ValueError("缺少分點明細網址。")

    html = request_text(detail_url, headers={"Referer": HISTOCK_BASE_URL})
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError("目前抓不到分點明細表。")

    title_node = soup.find("div", class_="ctname")
    title_text = _clean_text(title_node.get_text(" ", strip=True)) if title_node else "券商分點個股進出"
    rows: list[dict[str, Any]] = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if len(cells) < 10:
            continue
        values = [_clean_text(td.get_text(" ", strip=True)) for td in cells]
        rows.append(
            {
                "日期": values[0],
                "買進張數": values[1],
                "買進均價": values[2],
                "賣出張數": values[3],
                "賣出均價": values[4],
                "收盤價": values[5],
                "買賣超": values[6],
                "60日均量": values[7],
                "成交佔比": values[8],
                "大量交易提示": values[9],
                "_net_shares_value": _parse_float(values[6]),
                "_buy_shares_value": _parse_float(values[1]),
                "_sell_shares_value": _parse_float(values[3]),
            }
        )

    recent_rows = rows[:limit_rows]
    recent_5_net = sum(row.get("_net_shares_value") or 0 for row in recent_rows[:5])
    recent_20_net = sum(row.get("_net_shares_value") or 0 for row in recent_rows[:20])
    latest_net = recent_rows[0].get("_net_shares_value") if recent_rows else None

    cleaned_rows = []
    for row in recent_rows:
        cleaned_rows.append({key: value for key, value in row.items() if not key.startswith("_")})

    return {
        "title": title_text,
        "source_url": detail_url,
        "rows": cleaned_rows,
        "latest_net_shares": latest_net,
        "recent_5_net_shares": recent_5_net,
        "recent_20_net_shares": recent_20_net,
    }
