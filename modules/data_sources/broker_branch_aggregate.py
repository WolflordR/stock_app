from __future__ import annotations

import time
from functools import lru_cache

import pandas as pd

from modules.data_sources.broker_branch_data import fetch_broker_branch_summary
from modules.data_sources.broker_branch_short_term import load_short_term_broker_tags
from modules.data_sources.market_watch import fetch_tpex_daily_quotes, fetch_twse_daily_quotes
from modules.data_sources.official_broker_import import list_official_broker_branches
from modules.data_sources.stock_db import get_securities_in_range


def _parse_share(value):
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "--", "---", "None"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_branch_text(value: str | None) -> str:
    text = str(value or "").strip().casefold()
    for token in [" ", "　", "-", "－", "—", "_", "/", "\\", "(", ")", "（", "）"]:
        text = text.replace(token, "")
    for suffix in ["證券股份有限公司", "證券股分有限公司", "證券有限公司", "證券公司", "股份有限公司", "有限公司", "證券", "分公司"]:
        text = text.replace(suffix.casefold(), "")
    return text.strip()


@lru_cache(maxsize=1)
def load_branch_dropdown_options() -> tuple[str, ...]:
    names: set[str] = set()

    try:
        tag_df = load_short_term_broker_tags()
        if not tag_df.empty and "branch_name" in tag_df.columns:
            for value in tag_df["branch_name"].fillna("").astype(str).str.strip():
                if value:
                    names.add(value)
    except Exception:
        pass

    try:
        official_df = list_official_broker_branches(limit=1000)
        if not official_df.empty and "broker_name" in official_df.columns:
            for value in official_df["broker_name"].fillna("").astype(str).str.strip():
                if value:
                    names.add(value)
    except Exception:
        pass

    return tuple(sorted(names))


@lru_cache(maxsize=16)
def load_quote_lookup(trade_date_text: str) -> tuple[dict[str, float], dict[str, float]]:
    try:
        twse_df = fetch_twse_daily_quotes(trade_date_text)
    except Exception:
        twse_df = pd.DataFrame()
    try:
        tpex_df = fetch_tpex_daily_quotes(trade_date_text)
    except Exception:
        tpex_df = pd.DataFrame()

    quote_df = pd.concat([twse_df, tpex_df], ignore_index=True)
    if quote_df.empty:
        return {}, {}

    quote_df = quote_df.copy()
    quote_df["code"] = quote_df["code"].astype(str).str.strip()
    quote_df["close"] = pd.to_numeric(quote_df["close"], errors="coerce")
    quote_df["volume"] = pd.to_numeric(quote_df["volume"], errors="coerce").fillna(0.0)

    close_lookup = {
        str(row["code"]): float(row["close"])
        for _, row in quote_df.iterrows()
        if str(row.get("code") or "").strip() and pd.notna(row.get("close"))
    }
    volume_lookup = {
        str(row["code"]): float(row["volume"] or 0.0)
        for _, row in quote_df.iterrows()
        if str(row.get("code") or "").strip()
    }
    return close_lookup, volume_lookup


def scan_branch_totals(
    *,
    branch_query: str,
    start_num: int,
    end_num: int,
    top_n_per_stock: int,
    request_delay_sec: float,
    trade_date_key: str,
) -> dict[str, object]:
    securities = get_securities_in_range(start_num, end_num)
    eligible_count = len(securities)

    close_lookup, volume_lookup = load_quote_lookup(trade_date_key)
    securities = sorted(
        securities,
        key=lambda item: volume_lookup.get(str(item.get("code") or ""), 0.0),
        reverse=True,
    )

    normalized_branch_query = normalize_branch_text(branch_query)
    result_rows = []
    scanned_count = 0
    matched_stocks = 0
    failed_count = 0
    failure_examples: list[str] = []
    source_dates: list[str] = []

    for security in securities:
        scanned_count += 1
        stock_code = str(security.get("code") or "")
        stock_name = str(security.get("name_zh") or "")
        market = str(security.get("market") or "")
        close_price = close_lookup.get(stock_code)
        total_volume = volume_lookup.get(stock_code) or 0.0
        stock_input = str(security.get("yfinance_symbol") or stock_code)

        try:
            summary = fetch_broker_branch_summary(stock_input, top_n=top_n_per_stock, trade_date=trade_date_key)
        except Exception as exc:  # noqa: BLE001
            failed_count += 1
            if len(failure_examples) < 8:
                failure_examples.append(f"{stock_code}: {exc}")
            if request_delay_sec > 0:
                time.sleep(request_delay_sec)
            continue

        trade_date = str(summary.get("trade_date") or "").strip()
        if trade_date:
            source_dates.append(trade_date)

        matched_buy_shares = 0.0
        matched_sell_shares = 0.0

        for side_name, rows in (("buy_side", list(summary.get("buy_side") or [])), ("sell_side", list(summary.get("sell_side") or []))):
            for row in rows:
                broker_name = str(getattr(row, "broker_branch", "") or "").strip()
                if normalized_branch_query not in normalize_branch_text(broker_name):
                    continue
                if side_name == "buy_side":
                    matched_buy_shares += _parse_share(getattr(row, "buy_shares", 0))
                else:
                    matched_sell_shares += _parse_share(getattr(row, "sell_shares", 0))

        if matched_buy_shares <= 0 and matched_sell_shares <= 0:
            if request_delay_sec > 0:
                time.sleep(request_delay_sec)
            continue

        matched_stocks += 1
        net_shares = matched_buy_shares - matched_sell_shares
        buy_amount = (matched_buy_shares * 1000.0 * close_price) if close_price is not None else 0.0
        sell_amount = (matched_sell_shares * 1000.0 * close_price) if close_price is not None else 0.0
        net_amount = (net_shares * 1000.0 * close_price) if close_price is not None else 0.0
        buy_turnover_pct = (matched_buy_shares * 1000.0 / total_volume * 100.0) if total_volume > 0 else 0.0
        sell_turnover_pct = (matched_sell_shares * 1000.0 / total_volume * 100.0) if total_volume > 0 else 0.0

        result_rows.append(
            {
                "market": market,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "close_price": close_price,
                "buy_shares": matched_buy_shares,
                "sell_shares": matched_sell_shares,
                "net_shares": net_shares,
                "buy_amount": buy_amount,
                "sell_amount": sell_amount,
                "net_amount": net_amount,
                "buy_turnover_pct": buy_turnover_pct,
                "sell_turnover_pct": sell_turnover_pct,
            }
        )

        if request_delay_sec > 0:
            time.sleep(request_delay_sec)

    result_df = pd.DataFrame(result_rows)
    return {
        "branch_query": branch_query,
        "trade_date": max(source_dates) if source_dates else trade_date_key,
        "scanned_count": scanned_count,
        "eligible_count": eligible_count,
        "matched_stocks": matched_stocks,
        "failed_count": failed_count,
        "failure_examples": failure_examples,
        "result_df": result_df,
    }
