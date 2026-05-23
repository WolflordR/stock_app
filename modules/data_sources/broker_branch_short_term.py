from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pandas as pd

from modules.core.project_paths import data_path
from modules.core.trading_calendar import resolve_recent_trade_date, resolve_trade_dates_in_range
from modules.data_sources.broker_branch_data import BrokerBranchRow, fetch_broker_branch_summary, fetch_broker_branch_trace
from modules.data_sources.market_watch import fetch_tpex_daily_quotes, fetch_twse_daily_quotes
from modules.data_sources.stock_db import get_security_share_profile

SHORT_TERM_TAGS_CSV = data_path("short_term_broker_tags.csv")


def _safe_float(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if text in {"", "-", "--", "---", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}%"


def _format_lots(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f} 張"


def _safe_ratio_percent(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _safe_float(numerator)
    denominator_value = _safe_float(denominator)
    if numerator_value is None or denominator_value is None or denominator_value == 0:
        return None
    return numerator_value / denominator_value * 100.0


def _clean_stock_title(value: str) -> str:
    text = str(value or "").strip()
    for token in ["籌碼相關", "券商分點績效", "獲利分析", "－", "-", "—"]:
        if token in text:
            text = text.split(token)[0].strip()
    return text


def load_short_term_broker_tags() -> pd.DataFrame:
    if not SHORT_TERM_TAGS_CSV.exists():
        return pd.DataFrame(columns=["branch_name", "tag", "group_name", "note"])
    tag_df = pd.read_csv(SHORT_TERM_TAGS_CSV).fillna("")
    for column in ["branch_name", "tag", "group_name", "note"]:
        if column not in tag_df.columns:
            tag_df[column] = ""
    tag_df["branch_name"] = tag_df["branch_name"].astype(str).str.strip()
    tag_df = tag_df[tag_df["branch_name"] != ""].copy()
    return tag_df


def _build_tag_lookup() -> dict[str, list[dict[str, str]]]:
    tag_df = load_short_term_broker_tags()
    lookup: dict[str, list[dict[str, str]]] = {}
    for row in tag_df.to_dict("records"):
        lookup.setdefault(row["branch_name"], []).append(row)
    return lookup


def _load_latest_quote_row(stock_code: str, requested_date: str | None = None) -> dict[str, Any]:
    resolved = resolve_recent_trade_date(requested_date or pd.Timestamp.today().strftime("%Y-%m-%d"))
    effective_date = resolved["effective_date_text"]
    twse_df = fetch_twse_daily_quotes(effective_date)
    tpex_df = fetch_tpex_daily_quotes(effective_date)
    quote_df = pd.concat([twse_df, tpex_df], ignore_index=True)
    if quote_df.empty:
        return {
            "trade_date": effective_date,
            "used_fallback": resolved["used_fallback"],
            "row": {},
        }
    matched = quote_df[quote_df["code"].astype(str) == str(stock_code)].copy()
    row = matched.iloc[0].to_dict() if not matched.empty else {}
    return {
        "trade_date": effective_date,
        "used_fallback": resolved["used_fallback"],
        "row": row,
    }


def _load_volume_window_lots(stock_code: str, trade_date: str, days_window: int) -> float | None:
    if days_window <= 1:
        quote_payload = _load_latest_quote_row(stock_code, requested_date=trade_date)
        return ((_safe_float((quote_payload.get("row") or {}).get("volume")) or 0.0) / 1000.0) or None

    end_date = pd.to_datetime(trade_date).date()
    start_date = end_date - pd.Timedelta(days=max(days_window * 3, 10))
    resolved_days = resolve_trade_dates_in_range(start_date, end_date)
    resolved_days = resolved_days[-days_window:]
    if not resolved_days:
        return None

    total_lots = 0.0
    for item in resolved_days:
        probe_date = item["effective_date_text"]
        quote_df = pd.concat(
            [fetch_twse_daily_quotes(probe_date), fetch_tpex_daily_quotes(probe_date)],
            ignore_index=True,
        )
        if quote_df.empty:
            continue
        matched = quote_df[quote_df["code"].astype(str) == str(stock_code)]
        if matched.empty:
            continue
        total_lots += (_safe_float(matched.iloc[0].get("volume")) or 0.0) / 1000.0
    return total_lots or None


def _enrich_branch_row(row: BrokerBranchRow, tag_lookup: dict[str, list[dict[str, str]]], latest_close_value: float | None = None) -> dict[str, Any]:
    raw = asdict(row)
    net_lots = _safe_float(row.net_shares)
    avg_price = _safe_float(row.avg_price)
    total_profit_k = _safe_float(row.total_profit_k)
    if total_profit_k is None and net_lots is not None and avg_price is not None and latest_close_value is not None:
        total_profit_k = (latest_close_value - avg_price) * net_lots * 0.1
    tags = tag_lookup.get(row.broker_branch, [])
    return raw | {
        "net_lots_value": net_lots,
        "avg_price_value": avg_price,
        "total_profit_k_value": total_profit_k,
        "is_short_term": bool(tags),
        "tag_labels": [tag["tag"] for tag in tags],
        "group_labels": [tag["group_name"] for tag in tags if tag.get("group_name")],
    }


def _build_display_rows(rows: list[dict[str, Any]], *, side_label: str) -> list[dict[str, Any]]:
    display_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        tag_text = " / ".join(row["tag_labels"]) if row["tag_labels"] else ""
        display_rows.append(
            {
                "排名": index,
                "券商分點": row["broker_branch"],
                "標籤": tag_text or "-",
                "買賣超(張)": row["net_shares"],
                "均價": row["avg_price"],
                "總損益(仟)": row["total_profit_k"],
                "面向": side_label,
            }
        )
    return display_rows


def _window_trace_rows(detail_url: str, days_window: int) -> list[dict[str, Any]]:
    if not detail_url:
        return []
    trace_bundle = fetch_broker_branch_trace(detail_url, limit_rows=max(days_window, 30))
    rows = trace_bundle.get("rows") or []
    return rows[:days_window]


def _aggregate_branch_window(row: dict[str, Any], days_window: int) -> dict[str, Any]:
    if days_window <= 1:
        return row

    trace_rows = _window_trace_rows(row["detail_url"], days_window)
    if not trace_rows:
        aggregated = row.copy()
        aggregated["active_days"] = None
        aggregated["trace_window_rows"] = []
        return aggregated
    net_lots_value = sum(_safe_float(trace_row.get("買賣超")) or 0.0 for trace_row in trace_rows)
    buy_lots_value = sum(_safe_float(trace_row.get("買進張數")) or 0.0 for trace_row in trace_rows)
    sell_lots_value = sum(_safe_float(trace_row.get("賣出張數")) or 0.0 for trace_row in trace_rows)
    active_days = sum(1 for trace_row in trace_rows if (_safe_float(trace_row.get("買賣超")) or 0.0) != 0.0)

    aggregated = row.copy()
    aggregated["net_lots_value"] = net_lots_value
    aggregated["net_shares"] = f"{net_lots_value:,.0f}"
    aggregated["buy_shares"] = f"{buy_lots_value:,.0f}"
    aggregated["sell_shares"] = f"{sell_lots_value:,.0f}"
    aggregated["active_days"] = active_days
    aggregated["trace_window_rows"] = trace_rows
    return aggregated


def _derive_signal(
    *,
    main_net_pct: float | None,
    concentration_pct: float | None,
    short_term_buy_pct: float | None,
    short_term_sell_pct: float | None,
    buy_top5_pct: float | None,
    sell_top5_pct: float | None,
) -> tuple[str, str]:
    main_net_pct = main_net_pct or 0.0
    concentration_pct = concentration_pct or 0.0
    short_term_buy_pct = short_term_buy_pct or 0.0
    short_term_sell_pct = short_term_sell_pct or 0.0
    buy_top5_pct = buy_top5_pct or 0.0
    sell_top5_pct = sell_top5_pct or 0.0

    if main_net_pct >= 12 or (main_net_pct >= 8 and buy_top5_pct >= 18):
        return "大買", "前15大買超分點合計明顯大於前15大賣超分點，籌碼快速集中。"
    if main_net_pct <= -12 or (main_net_pct <= -8 and sell_top5_pct >= 18):
        return "大賣", "前15大賣超分點合計明顯大於前15大買超分點，籌碼快速分散。"
    if main_net_pct >= 3 or (main_net_pct > 0 and concentration_pct >= 3):
        return "小買", "前15大買超分點略占上風，籌碼偏向小幅集中。"
    if main_net_pct <= -3 or (main_net_pct < 0 and concentration_pct <= -3):
        return "小賣", "前15大賣超分點略占上風，籌碼偏向小幅分散。"
    return "中立", "前15大買賣超分點力道接近，籌碼結構相對平穩。"


def build_short_term_broker_report(stock_code: str, *, top_n: int = 15, days_window: int = 1) -> dict[str, Any]:
    quote_payload = _load_latest_quote_row(stock_code)
    quote_row = quote_payload.get("row") or {}
    latest_close_value = _safe_float(quote_row.get("close"))
    requested_trade_date = quote_payload.get("trade_date")
    summary_bundle = fetch_broker_branch_summary(stock_code, top_n=top_n, trade_date=requested_trade_date)
    tag_lookup = _build_tag_lookup()

    base_buy_rows = [_enrich_branch_row(row, tag_lookup, latest_close_value) for row in summary_bundle.get("buy_side") or []]
    base_sell_rows = [_enrich_branch_row(row, tag_lookup, latest_close_value) for row in summary_bundle.get("sell_side") or []]

    if days_window <= 1:
        buy_rows = base_buy_rows
        sell_rows = base_sell_rows
    else:
        aggregated_rows = [_aggregate_branch_window(row, days_window) for row in (base_buy_rows + base_sell_rows)]
        buy_rows = [row for row in aggregated_rows if (row["net_lots_value"] or 0.0) > 0]
        sell_rows = [row for row in aggregated_rows if (row["net_lots_value"] or 0.0) < 0]
        buy_rows = sorted(buy_rows, key=lambda row: row["net_lots_value"] or 0.0, reverse=True)[:top_n]
        sell_rows = sorted(sell_rows, key=lambda row: row["net_lots_value"] or 0.0)[:top_n]

    trade_date = summary_bundle.get("trade_date") or quote_payload.get("trade_date")
    total_volume_lots = _load_volume_window_lots(stock_code, trade_date, days_window) if trade_date else None
    share_profile = get_security_share_profile(stock_code) or {}
    issued_common_shares = _safe_float(share_profile.get("issued_common_shares"))
    issued_common_lots = (issued_common_shares / 1000.0) if issued_common_shares is not None and issued_common_shares != 0 else None

    short_term_buy_lots = sum(row["net_lots_value"] or 0.0 for row in buy_rows if row["is_short_term"])
    short_term_sell_lots = sum(abs(row["net_lots_value"] or 0.0) for row in sell_rows if row["is_short_term"])
    main_buy_lots = sum(row["net_lots_value"] or 0.0 for row in buy_rows)
    main_sell_lots = sum(abs(row["net_lots_value"] or 0.0) for row in sell_rows)
    main_net_lots = main_buy_lots - main_sell_lots
    buy_top5_lots = sum(row["net_lots_value"] or 0.0 for row in buy_rows[:5])
    sell_top5_lots = sum(abs(row["net_lots_value"] or 0.0) for row in sell_rows[:5])
    concentration_lots = main_net_lots

    if total_volume_lots and total_volume_lots > 0:
        for row in buy_rows + sell_rows:
            row["weight_pct"] = _safe_ratio_percent(abs(row.get("net_lots_value") or 0.0), total_volume_lots)
    else:
        for row in buy_rows + sell_rows:
            row["weight_pct"] = None

    main_net_pct = _safe_ratio_percent(main_net_lots, total_volume_lots)
    concentration_pct = _safe_ratio_percent(main_net_lots, total_volume_lots)
    short_term_buy_pct = _safe_ratio_percent(short_term_buy_lots, total_volume_lots)
    short_term_sell_pct = _safe_ratio_percent(short_term_sell_lots, total_volume_lots)
    buy_top5_pct = _safe_ratio_percent(buy_top5_lots, total_volume_lots)
    sell_top5_pct = _safe_ratio_percent(sell_top5_lots, total_volume_lots)
    estimated_float_pct = _safe_ratio_percent(concentration_lots, issued_common_lots)
    interval_turnover_pct = _safe_ratio_percent(total_volume_lots, issued_common_lots)

    signal_label, signal_reason = _derive_signal(
        main_net_pct=main_net_pct,
        concentration_pct=concentration_pct,
        short_term_buy_pct=short_term_buy_pct,
        short_term_sell_pct=short_term_sell_pct,
        buy_top5_pct=buy_top5_pct,
        sell_top5_pct=sell_top5_pct,
    )

    alerts: list[str] = []
    if main_net_pct and main_net_pct >= 8:
        alerts.append(f"提醒：前15大分點主力買超占成交量 {main_net_pct:.2f}%")
    if main_net_pct and main_net_pct <= -8:
        alerts.append(f"提醒：前15大分點主力賣超占成交量 {abs(main_net_pct):.2f}%")
    if short_term_buy_pct and short_term_buy_pct >= 10:
        alerts.append(f"提醒：短衝主力買超占成交量 {short_term_buy_pct:.2f}%")
    if short_term_sell_pct and short_term_sell_pct >= 10:
        alerts.append(f"提醒：短衝主力賣超占成交量 {short_term_sell_pct:.2f}%")
    if buy_top5_pct and buy_top5_pct >= 20:
        alerts.append(f"提醒：買方前五大分點集中度 {buy_top5_pct:.2f}%")
    if sell_top5_pct and sell_top5_pct >= 20:
        alerts.append(f"提醒：賣方前五大分點集中度 {sell_top5_pct:.2f}%")

    return {
        "stock_code": stock_code,
        "stock_title": _clean_stock_title(summary_bundle.get("stock_title") or stock_code),
        "source_url": summary_bundle.get("source_url"),
        "source_label": summary_bundle.get("source_label") or "",
        "trade_date": trade_date,
        "history_mode": "current_snapshot_only" if days_window > 1 and not any(row.get("detail_url") for row in (base_buy_rows + base_sell_rows)) else "window_trace",
        "days_window": days_window,
        "quote_row": quote_row,
        "buy_rows": buy_rows,
        "sell_rows": sell_rows,
        "buy_display_rows": _build_display_rows(buy_rows, side_label="買超"),
        "sell_display_rows": _build_display_rows(sell_rows, side_label="賣超"),
        "summary": {
            "signal_label": signal_label,
            "signal_reason": signal_reason,
            "total_volume_lots": total_volume_lots,
            "main_buy_lots": main_buy_lots,
            "main_sell_lots": main_sell_lots,
            "main_net_lots": main_net_lots,
            "main_net_pct": main_net_pct,
            "concentration_pct": concentration_pct,
            "short_term_buy_lots": short_term_buy_lots,
            "short_term_sell_lots": short_term_sell_lots,
            "short_term_buy_pct": short_term_buy_pct,
            "short_term_sell_pct": short_term_sell_pct,
            "buy_top5_lots": buy_top5_lots,
            "sell_top5_lots": sell_top5_lots,
            "buy_top5_pct": buy_top5_pct,
            "sell_top5_pct": sell_top5_pct,
            "concentration_lots": concentration_lots,
            "estimated_float_pct": estimated_float_pct,
            "interval_turnover_pct": interval_turnover_pct,
            "issued_common_lots": issued_common_lots,
            "short_term_buy_count": sum(1 for row in buy_rows if row["is_short_term"]),
            "short_term_sell_count": sum(1 for row in sell_rows if row["is_short_term"]),
        },
        "alerts": alerts,
    }


def format_short_term_summary(report: dict[str, Any]) -> dict[str, str]:
    summary = report.get("summary") or {}
    return {
        "主力動向": summary.get("signal_label") or "-",
        "籌碼集中": _format_lots(summary.get("concentration_lots")),
        "主力買賣超": _format_lots(summary.get("main_net_lots")),
        "籌碼集中度": _format_pct(summary.get("concentration_pct")),
        "短衝買超占比": _format_pct(summary.get("short_term_buy_pct")),
        "短衝賣超占比": _format_pct(summary.get("short_term_sell_pct")),
        "買方前五集中": _format_pct(summary.get("buy_top5_pct")),
        "賣方前五集中": _format_pct(summary.get("sell_top5_pct")),
        "成交量": _format_lots(summary.get("total_volume_lots")),
        "估股本比重": _format_pct(summary.get("estimated_float_pct")),
        "區間週轉率": _format_pct(summary.get("interval_turnover_pct")),
    }
