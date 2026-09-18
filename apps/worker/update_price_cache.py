from __future__ import annotations

import argparse
import json
from typing import Any

from modules.data_sources.price_cache import (
    clear_price_cache_status,
    fetch_price_history,
    get_price_cache_status,
)
from modules.data_sources.stock_db import find_security, get_securities_in_range


def _resolve_symbol(stock_id: str) -> str | None:
    security = find_security(stock_id)
    if security:
        return security["yfinance_symbol"]
    normalized = str(stock_id or "").strip().upper()
    if "." in normalized:
        return normalized
    if normalized.isdigit() and len(normalized) == 4:
        return f"{normalized}.TW"
    return None


def update_symbol_price_cache(symbol: str, *, days: int = 180, force: bool = False) -> dict[str, Any]:
    cleared_meta_rows = clear_price_cache_status(symbol) if force else 0
    frame = fetch_price_history(symbol, history_buffer_days=days)
    status = get_price_cache_status(symbol)
    fetch_status = status.get("fetch_status")
    row_count = int(status.get("row_count") or 0)
    loaded_rows = int(len(frame))
    ok = fetch_status != "failed" and (loaded_rows > 0 or row_count > 0)
    error = None
    if fetch_status == "failed":
        error = status.get("last_error") or "Price cache fetch failed."
    elif loaded_rows == 0 and row_count == 0:
        error = "No price rows are available after update."

    return {
        "symbol": symbol,
        "ok": ok,
        "loaded_rows": loaded_rows,
        "cleared_meta_rows": cleared_meta_rows,
        "status": status,
        **({"error": error} if error else {}),
    }


def update_stocks(
    stock_ids: list[str],
    *,
    days: int = 180,
    force: bool = False,
    progress_callback=None,
    status_callback=None,
) -> dict[str, Any]:
    results = []
    total = len(stock_ids)
    for index, stock_id in enumerate(stock_ids, start=1):
        if status_callback:
            status_callback(f"正在更新 {stock_id} ({index}/{total})")
        symbol = _resolve_symbol(stock_id)
        if not symbol:
            results.append({"stock_id": stock_id, "ok": False, "error": "Unknown stock id"})
            if progress_callback:
                progress_callback(index / total if total else 1, f"略過未知股票 {stock_id}")
            continue
        try:
            results.append({"stock_id": stock_id, **update_symbol_price_cache(symbol, days=days, force=force)})
        except Exception as exc:
            results.append({"stock_id": stock_id, "symbol": symbol, "ok": False, "error": str(exc)})
        if progress_callback:
            latest = results[-1]
            label = "完成" if latest.get("ok") else "失敗"
            progress_callback(index / total if total else 1, f"{label} {stock_id} ({index}/{total})")

    return {
        "requested_count": len(stock_ids),
        "ok_count": sum(1 for item in results if item.get("ok")),
        "failed_count": sum(1 for item in results if not item.get("ok")),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Update local yfinance price cache for selected stocks.")
    parser.add_argument("--stock", action="append", default=[], help="Stock code or yfinance symbol. Repeatable.")
    parser.add_argument("--range", nargs=2, metavar=("START", "END"), help="Inclusive numeric stock code range.")
    parser.add_argument("--days", type=int, default=180, help="History window to keep fresh.")
    parser.add_argument("--force", action="store_true", help="Clear cache metadata before fetching so failed symbols can retry immediately.")
    args = parser.parse_args()

    stock_ids = list(args.stock)
    if args.range:
        start, end = args.range
        stock_ids.extend(item["yfinance_symbol"] for item in get_securities_in_range(start, end))

    if not stock_ids:
        parser.error("Provide at least one --stock or --range START END.")

    result = update_stocks(stock_ids, days=args.days, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
