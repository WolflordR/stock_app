from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta
from typing import Any

from modules.core.project_paths import db_path
from modules.data_sources.official_broker_import import get_latest_official_broker_summary, list_official_broker_branches
from modules.data_sources.price_cache import get_price_cache_status
from modules.data_sources.stock_db import find_security
from modules.industry.classification_queries import get_company_official_industry_df
from modules.backtest.strategy_config import BUY_STRATEGY_METADATA, DEFAULT_BUY_STRATEGIES, DEFAULT_SELL_STRATEGIES, SELL_STRATEGY_METADATA


STOCK_CHART_HISTORY_LIMIT = 1260

US_MARKET_CALENDAR_EVENTS = [
    {
        "date": "2026-09-08",
        "time": "22:00",
        "country": "US",
        "event": "NFIB 小型企業信心指數",
        "category": "信心指數",
        "importance": "medium",
        "previous": "100.3",
        "forecast": "100.6",
        "actual": None,
        "unit": "index",
        "market_impact": "中小企業信心影響景氣預期與 Russell 2000 情緒。",
    },
    {
        "date": "2026-09-09",
        "time": "22:00",
        "country": "US",
        "event": "批發庫存月增率",
        "category": "庫存",
        "importance": "low",
        "previous": "0.2%",
        "forecast": "0.1%",
        "actual": None,
        "unit": "%",
        "market_impact": "通常影響較溫和，可用來觀察需求與庫存循環。",
    },
    {
        "date": "2026-09-10",
        "time": "20:30",
        "country": "US",
        "event": "CPI 年增率",
        "category": "通膨",
        "importance": "high",
        "previous": "2.7%",
        "forecast": "2.8%",
        "actual": None,
        "unit": "%",
        "market_impact": "高於預期通常推升殖利率，壓抑科技與成長股估值。",
    },
    {
        "date": "2026-09-10",
        "time": "20:30",
        "country": "US",
        "event": "核心 CPI 月增率",
        "category": "通膨",
        "importance": "high",
        "previous": "0.2%",
        "forecast": "0.3%",
        "actual": None,
        "unit": "%",
        "market_impact": "聯準會關注核心通膨，會直接牽動降息預期。",
    },
    {
        "date": "2026-09-10",
        "time": "20:30",
        "country": "US",
        "event": "初領失業救濟金人數",
        "category": "就業",
        "importance": "medium",
        "previous": "23.1萬",
        "forecast": "23.5萬",
        "actual": None,
        "unit": "人",
        "market_impact": "高於預期代表就業轉弱，可能增加降息押注。",
    },
    {
        "date": "2026-09-11",
        "time": "20:30",
        "country": "US",
        "event": "PPI 月增率",
        "category": "通膨",
        "importance": "high",
        "previous": "0.4%",
        "forecast": "0.2%",
        "actual": None,
        "unit": "%",
        "market_impact": "生產端價格若升溫，可能延長市場對通膨黏性的擔憂。",
    },
    {
        "date": "2026-09-11",
        "time": "22:00",
        "country": "US",
        "event": "密大消費者信心初值",
        "category": "信心指數",
        "importance": "medium",
        "previous": "58.2",
        "forecast": "59.0",
        "actual": None,
        "unit": "index",
        "market_impact": "消費信心會影響零售、非必需消費與景氣循環股。",
    },
    {
        "date": "2026-09-15",
        "time": "20:30",
        "country": "US",
        "event": "零售銷售月增率",
        "category": "消費",
        "importance": "high",
        "previous": "0.5%",
        "forecast": "0.2%",
        "actual": None,
        "unit": "%",
        "market_impact": "強勁零售代表需求韌性，可能支撐循環股但壓低降息預期。",
    },
    {
        "date": "2026-09-16",
        "time": "02:00",
        "country": "US",
        "event": "FOMC 利率決議",
        "category": "央行",
        "importance": "high",
        "previous": "4.25%-4.50%",
        "forecast": "4.00%-4.25%",
        "actual": None,
        "unit": "%",
        "market_impact": "利率路徑與點陣圖是科技股、美元、債券最關鍵變數。",
    },
]


def _connect_db(filename: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(filename))
    conn.row_factory = sqlite3.Row
    return conn


def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _json_safe(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def list_us_market_calendar(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    importance: str | None = None,
) -> dict[str, Any]:
    today = date.today()
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=3)
    end = date.fromisoformat(end_date) if end_date else today + timedelta(days=21)
    normalized_importance = str(importance or "all").strip().lower()

    rows = []
    for event in US_MARKET_CALENDAR_EVENTS:
        event_date = date.fromisoformat(event["date"])
        if event_date < start or event_date > end:
            continue
        if normalized_importance != "all" and event["importance"] != normalized_importance:
            continue
        rows.append(event)

    rows.sort(key=lambda row: (row["date"], row["time"], row["event"]))
    return {
        "source": "mock",
        "source_label": "本機模擬資料，欄位參考 MoneyDJ 美股數據公布行事曆",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "importance": normalized_importance,
        "event_count": len(rows),
        "rows": rows,
    }


def list_market_map_groups() -> list[dict[str, Any]]:
    with _connect_db("market_map.db") as conn:
        rows = conn.execute(
            """
            SELECT
                g.group_name,
                g.display_name,
                g.sort_order,
                g.is_tech,
                COUNT(DISTINCT t.topic_name) AS topic_count,
                COUNT(DISTINCT a.code) AS company_count
            FROM map_groups g
            LEFT JOIN map_topics t
              ON g.group_name = t.group_name
            LEFT JOIN map_topic_company_assignments a
              ON t.topic_name = a.topic_name
            GROUP BY g.group_name, g.display_name, g.sort_order, g.is_tech
            ORDER BY g.sort_order, g.group_name
            """
        ).fetchall()
    return _rows_to_dicts(rows)


def list_market_map_topics(group_name: str | None = None) -> list[dict[str, Any]]:
    params: tuple[Any, ...] = ()
    where_clause = ""
    if group_name:
        where_clause = "WHERE t.group_name = ?"
        params = (group_name,)

    with _connect_db("market_map.db") as conn:
        rows = conn.execute(
            f"""
            SELECT
                t.group_name,
                t.topic_name,
                t.display_name,
                t.parent_industry,
                t.topic_type,
                t.is_tech,
                t.description,
                t.news_query,
                COUNT(DISTINCT a.code) AS company_count
            FROM map_topics t
            LEFT JOIN map_topic_company_assignments a
              ON t.topic_name = a.topic_name
            {where_clause}
            GROUP BY
                t.group_name,
                t.topic_name,
                t.display_name,
                t.parent_industry,
                t.topic_type,
                t.is_tech,
                t.description,
                t.news_query,
                t.sort_order
            ORDER BY t.sort_order, t.topic_name
            """,
            params,
        ).fetchall()
    return _rows_to_dicts(rows)


def list_market_map_topic_members(topic_name: str, limit: int = 80) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), 300))
    with _connect_db("market_map.db") as conn:
        rows = conn.execute(
            """
            SELECT
                a.topic_name,
                c.code,
                c.name_zh,
                c.full_name_zh,
                c.market,
                c.yfinance_symbol,
                c.official_industry,
                a.source,
                a.confidence,
                a.note
            FROM map_topic_company_assignments a
            JOIN map_companies c
              ON a.code = c.code
            WHERE a.topic_name = ?
            ORDER BY a.confidence DESC, c.code
            LIMIT ?
            """,
            (topic_name, normalized_limit),
        ).fetchall()
    return _rows_to_dicts(rows)


def list_broker_branches(search_text: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
    frame = list_official_broker_branches(search_text=search_text, limit=limit)
    if frame.empty:
        return []
    return _json_safe(frame.to_dict("records"))


def list_stock_price_history(symbol: str, limit: int = 30) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), 1500))
    with _connect_db("price_cache.db") as conn:
        rows = conn.execute(
            """
            SELECT trade_date, open, high, low, close, volume
            FROM price_history
            WHERE symbol = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (symbol, normalized_limit),
        ).fetchall()
    return list(reversed(_rows_to_dicts(rows)))


def get_price_cache_overview() -> dict[str, Any]:
    with _connect_db("price_cache.db") as conn:
        history = conn.execute(
            """
            SELECT
                COUNT(DISTINCT symbol) AS symbol_count,
                COUNT(*) AS row_count,
                MIN(trade_date) AS first_trade_date,
                MAX(trade_date) AS last_trade_date
            FROM price_history
            """
        ).fetchone()
        meta = conn.execute(
            """
            SELECT
                COUNT(*) AS meta_count,
                SUM(CASE WHEN fetch_status = 'ready' THEN 1 ELSE 0 END) AS ready_count,
                SUM(CASE WHEN fetch_status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                MAX(last_updated_at) AS last_updated_at
            FROM price_cache_meta
            """
        ).fetchone()
    return _json_safe({"history": dict(history), "meta": dict(meta)})


def _safe_db_summary(filename: str, query: str) -> dict[str, Any]:
    try:
        with _connect_db(filename) as conn:
            row = conn.execute(query).fetchone()
        return {"ok": True, **dict(row or {})}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def build_data_sources_overview() -> dict[str, Any]:
    price = get_price_cache_overview()
    stock_master = _safe_db_summary(
        "stocks.db",
        "SELECT COUNT(*) AS row_count, MAX(updated_at) AS last_updated_at FROM securities",
    )
    institutional = _safe_db_summary(
        "chip_cache.db",
        """
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT trade_date) AS day_count,
            COUNT(DISTINCT code) AS symbol_count,
            MAX(trade_date) AS latest_date
        FROM institutional_trading
        """,
    )
    broker = _safe_db_summary(
        "broker_daily_trades.db",
        """
        SELECT
            COUNT(*) AS report_count,
            COUNT(DISTINCT trade_date) AS day_count,
            COUNT(DISTINCT stock_code) AS symbol_count,
            MAX(trade_date) AS latest_date
        FROM broker_trade_reports
        """,
    )
    revenue = _safe_db_summary(
        "revenue_cache.db",
        """
        SELECT
            COUNT(*) AS row_count,
            COUNT(DISTINCT report_month) AS month_count,
            COUNT(DISTINCT code) AS symbol_count,
            MAX(report_month) AS latest_date,
            MAX(updated_at) AS last_updated_at
        FROM monthly_revenue
        """,
    )
    etf = _safe_db_summary(
        "active_etf_history.db",
        """
        SELECT
            COUNT(*) AS snapshot_count,
            COUNT(DISTINCT snapshot_date) AS day_count,
            COUNT(DISTINCT etf_code) AS symbol_count,
            MAX(snapshot_date) AS latest_date,
            MAX(updated_at) AS last_updated_at
        FROM etf_change_snapshots
        """,
    )
    calendar = list_us_market_calendar()

    sources = [
        {
            "key": "stock_master",
            "title": "股票主檔",
            "description": "上市櫃股票代號、名稱、市場與 yfinance symbol。",
            "status": "ready" if stock_master.get("ok") and stock_master.get("row_count") else "empty",
            "db_file": "stocks.db",
            "latest_date": stock_master.get("last_updated_at"),
            "row_count": stock_master.get("row_count", 0),
            "symbol_count": stock_master.get("row_count", 0),
            "update_mode": "worker",
            "action_label": "後端 worker",
            "action_enabled": False,
            "note": "之後會接主檔更新 job；目前先由 worker/命令更新。",
        },
        {
            "key": "price_cache",
            "title": "股價 K 線",
            "description": "日 K OHLCV 快取，個股詳頁、強勢股與回測共用。",
            "status": "ready" if (price.get("history") or {}).get("row_count") else "empty",
            "db_file": "price_cache.db",
            "latest_date": (price.get("history") or {}).get("last_trade_date"),
            "last_updated_at": (price.get("meta") or {}).get("last_updated_at"),
            "row_count": (price.get("history") or {}).get("row_count", 0),
            "symbol_count": (price.get("history") or {}).get("symbol_count", 0),
            "update_mode": "web_job",
            "action_label": "前往更新",
            "action_enabled": True,
            "note": "已支援範圍或全部股票更新，資料量大時建議用 NAS worker 排程。",
        },
        {
            "key": "institutional",
            "title": "三大法人",
            "description": "外資、投信、自營商買賣超，個股詳頁表格使用。",
            "status": "ready" if institutional.get("ok") and institutional.get("row_count") else "empty",
            "db_file": "chip_cache.db",
            "latest_date": institutional.get("latest_date"),
            "row_count": institutional.get("row_count", 0),
            "symbol_count": institutional.get("symbol_count", 0),
            "update_mode": "worker",
            "action_label": "待接更新",
            "action_enabled": False,
            "note": "目前可讀本地快取；下一步可接合法的手動查詢/匯入流程。",
        },
        {
            "key": "broker",
            "title": "券商分點",
            "description": "分點買進、賣出與買賣超排行，個股詳頁分點摘要使用。",
            "status": "ready" if broker.get("ok") and broker.get("report_count") else "empty",
            "db_file": "broker_daily_trades.db",
            "latest_date": broker.get("latest_date"),
            "row_count": broker.get("report_count", 0),
            "symbol_count": broker.get("symbol_count", 0),
            "update_mode": "manual_import",
            "action_label": "CSV 匯入待接",
            "action_enabled": False,
            "note": "已具備 CSV 匯入模組；後續補前端上傳/貼上介面。",
        },
        {
            "key": "revenue",
            "title": "月營收",
            "description": "近 6 個月營收趨勢與加速度評分。",
            "status": "ready" if revenue.get("ok") and revenue.get("row_count") else "empty",
            "db_file": "revenue_cache.db",
            "latest_date": revenue.get("latest_date"),
            "last_updated_at": revenue.get("last_updated_at"),
            "row_count": revenue.get("row_count", 0),
            "symbol_count": revenue.get("symbol_count", 0),
            "update_mode": "worker",
            "action_label": "待接更新",
            "action_enabled": False,
            "note": "後續可接收盤後或每月公告後更新。",
        },
        {
            "key": "active_etf",
            "title": "主動 ETF 快照",
            "description": "主動 ETF 成分股異動與日期快照。",
            "status": "ready" if etf.get("ok") and etf.get("snapshot_count") else "empty",
            "db_file": "active_etf_history.db",
            "latest_date": etf.get("latest_date"),
            "last_updated_at": etf.get("last_updated_at"),
            "row_count": etf.get("snapshot_count", 0),
            "symbol_count": etf.get("symbol_count", 0),
            "update_mode": "worker",
            "action_label": "待接更新",
            "action_enabled": False,
            "note": "目前讀本地快照；更新任務之後拆到 worker。",
        },
        {
            "key": "us_calendar",
            "title": "美股數據行事曆",
            "description": "美國重要經濟數據公布時間、前值、預期與影響。",
            "status": "mock",
            "db_file": None,
            "latest_date": calendar.get("end_date"),
            "row_count": calendar.get("event_count", 0),
            "symbol_count": None,
            "update_mode": "mock",
            "action_label": "待接資料源",
            "action_enabled": False,
            "note": calendar.get("source_label"),
        },
    ]
    return {"sources": sources, "price_cache": price}


def list_strong_stocks(days: int = 7, limit: int = 10) -> dict[str, Any]:
    normalized_days = max(2, min(int(days), 365))
    normalized_limit = max(1, min(int(limit), 50))
    with _connect_db("price_cache.db") as conn:
        conn.execute("ATTACH DATABASE ? AS stockdb", (str(db_path("stocks.db")),))
        latest = conn.execute("SELECT MAX(trade_date) AS trade_date FROM price_history").fetchone()
        anchor_date = latest["trade_date"] if latest else None
        if not anchor_date:
            return {"summary": {"days": normalized_days, "limit": normalized_limit, "anchor_date": None}, "rows": []}

        start_date = conn.execute(
            "SELECT date(?, '-' || ? || ' days') AS start_date",
            (anchor_date, normalized_days - 1),
        ).fetchone()["start_date"]
        candidate_summary = conn.execute(
            """
            WITH windowed AS (
                SELECT symbol, trade_date, close
                FROM price_history
                WHERE trade_date BETWEEN ? AND ?
                  AND close IS NOT NULL
            ),
            bounds AS (
                SELECT
                    symbol,
                    MIN(trade_date) AS first_date,
                    MAX(trade_date) AS last_date,
                    COUNT(*) AS quote_count
                FROM windowed
                GROUP BY symbol
                HAVING COUNT(*) >= 2
            )
            SELECT COUNT(*) AS candidate_count
            FROM bounds b
            JOIN price_history p0
              ON p0.symbol = b.symbol
             AND p0.trade_date = b.first_date
            JOIN price_history p1
              ON p1.symbol = b.symbol
             AND p1.trade_date = b.last_date
            WHERE p0.close IS NOT NULL
              AND p0.close != 0
              AND p1.close IS NOT NULL
            """,
            (start_date, anchor_date),
        ).fetchone()
        candidate_count = int(candidate_summary["candidate_count"] or 0)
        rank_rows = conn.execute(
            """
            WITH windowed AS (
                SELECT symbol, trade_date, close
                FROM price_history
                WHERE trade_date BETWEEN ? AND ?
                  AND close IS NOT NULL
            ),
            bounds AS (
                SELECT
                    symbol,
                    MIN(trade_date) AS first_date,
                    MAX(trade_date) AS last_date,
                    COUNT(*) AS quote_count
                FROM windowed
                GROUP BY symbol
                HAVING COUNT(*) >= 2
            )
            SELECT
                b.symbol,
                s.code,
                s.name_zh,
                s.market,
                b.first_date,
                b.last_date,
                b.quote_count,
                p0.close AS start_close,
                p1.close AS latest_close,
                (p1.close - p0.close) AS change,
                ((p1.close - p0.close) / p0.close * 100.0) AS change_pct
            FROM bounds b
            JOIN price_history p0
              ON p0.symbol = b.symbol
             AND p0.trade_date = b.first_date
            JOIN price_history p1
              ON p1.symbol = b.symbol
             AND p1.trade_date = b.last_date
            LEFT JOIN stockdb.securities s
              ON s.yfinance_symbol = b.symbol
            WHERE p0.close IS NOT NULL
              AND p0.close != 0
              AND p1.close IS NOT NULL
            ORDER BY change_pct DESC, quote_count DESC, b.symbol
            LIMIT ?
            """,
            (start_date, anchor_date, normalized_limit),
        ).fetchall()

        symbols = [row["symbol"] for row in rank_rows]
        sparkline_by_symbol: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
        if symbols:
            placeholders = ",".join("?" for _ in symbols)
            spark_rows = conn.execute(
                f"""
                SELECT symbol, trade_date, close
                FROM price_history
                WHERE symbol IN ({placeholders})
                  AND trade_date BETWEEN ? AND ?
                  AND close IS NOT NULL
                ORDER BY symbol, trade_date
                """,
                (*symbols, start_date, anchor_date),
            ).fetchall()
            for row in spark_rows:
                sparkline_by_symbol[row["symbol"]].append(
                    {"trade_date": row["trade_date"], "close": row["close"]}
                )

    rows = []
    for row in _rows_to_dicts(rank_rows):
        symbol = row["symbol"]
        row["code"] = row.get("code") or str(symbol).split(".")[0]
        row["name_zh"] = row.get("name_zh") or row["code"]
        row["sparkline"] = sparkline_by_symbol.get(symbol, [])
        rows.append(row)

    return _json_safe(
        {
            "summary": {
                "days": normalized_days,
                "limit": normalized_limit,
                "anchor_date": anchor_date,
                "window_start_date": start_date,
                "candidate_count": candidate_count,
                "returned_count": len(rows),
            },
            "rows": rows,
        }
    )


def list_revenue_momentum(limit: int = 30) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit), 100))
    lookback_months = 6
    with _connect_db("revenue_cache.db") as conn:
        latest = conn.execute("SELECT MAX(report_month) AS report_month FROM monthly_revenue").fetchone()
        report_month = latest["report_month"] if latest else None
        if not report_month:
            return {"report_month": None, "rows": [], "summary": {"mode": "growth_acceleration", "lookback_months": lookback_months}}
        month_rows = conn.execute(
            """
            SELECT DISTINCT report_month
            FROM monthly_revenue
            WHERE report_month IS NOT NULL
            ORDER BY report_month DESC
            LIMIT ?
            """,
            (lookback_months,),
        ).fetchall()
        used_months = sorted(row["report_month"] for row in month_rows)
        if not used_months:
            return {"report_month": report_month, "rows": [], "summary": {"mode": "growth_acceleration", "lookback_months": lookback_months}}

        placeholders = ",".join("?" for _ in used_months)
        rows = conn.execute(
            f"""
            SELECT
                report_month,
                output_date,
                market,
                code,
                name_zh,
                industry,
                current_revenue,
                mom_pct,
                yoy_pct,
                cumulative_yoy_pct,
                updated_at
            FROM monthly_revenue
            WHERE report_month IN ({placeholders})
            ORDER BY code, market, report_month
            """,
            used_months,
        ).fetchall()
    all_ranked_rows = _build_revenue_trend_rows(_rows_to_dicts(rows), used_months)
    ranked_rows = all_ranked_rows[:normalized_limit]
    return _json_safe({
        "report_month": report_month,
        "rows": ranked_rows,
        "summary": {
            "mode": "growth_acceleration",
            "lookback_months": len(used_months),
            "used_months": used_months,
            "candidate_count": len({(row["market"], row["code"]) for row in rows}),
            "qualified_count": len(all_ranked_rows),
            "returned_count": len(ranked_rows),
        },
    })


def _build_revenue_trend_rows(rows: list[dict[str, Any]], used_months: list[str]) -> list[dict[str, Any]]:
    by_stock: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        code = str(row.get("code") or "").strip()
        market = str(row.get("market") or "").strip()
        if not code or not market:
            continue
        by_stock.setdefault((market, code), []).append(row)

    ranked: list[dict[str, Any]] = []
    min_month_count = min(8, max(3, len(used_months)))
    for (_, code), stock_rows in by_stock.items():
        stock_rows = sorted(stock_rows, key=lambda item: str(item.get("report_month") or ""))
        valid_rows = [
            row for row in stock_rows
            if _to_float(row.get("current_revenue")) is not None and _to_float(row.get("current_revenue")) > 0
        ]
        if len(valid_rows) < min_month_count:
            continue
        latest_row = valid_rows[-1]
        revenues = [_to_float(row.get("current_revenue")) or 0.0 for row in valid_rows]
        latest_revenue = revenues[-1]
        first_revenue = revenues[0]
        if latest_revenue < 50000 or first_revenue < 20000:
            continue

        slope_pct = _linear_log_slope_pct(revenues)
        trend_growth_pct = (latest_revenue / first_revenue - 1.0) * 100.0
        positive_step_count = sum(1 for before, after in zip(revenues, revenues[1:]) if after > before)
        recent_average = sum(revenues[-6:]) / min(len(revenues), 6)
        latest_vs_recent_average_pct = (latest_revenue / recent_average - 1.0) * 100.0 if recent_average else 0.0
        yoy_pct = _to_float(latest_row.get("yoy_pct"))
        cumulative_yoy_pct = _to_float(latest_row.get("cumulative_yoy_pct"))
        mom_pct = _to_float(latest_row.get("mom_pct"))

        if slope_pct <= 0 or trend_growth_pct < 5:
            continue

        growth_rates = _growth_rates_pct(revenues, [str(row.get("report_month") or "") for row in valid_rows])
        growth_acceleration_pct = _linear_slope(growth_rates) if len(growth_rates) >= 2 else 0.0
        accelerating_step_count = sum(1 for before, after in zip(growth_rates, growth_rates[1:]) if after > before)
        positive_growth_rate_count = sum(1 for value in growth_rates if value > 0)
        accelerating_step_ratio = accelerating_step_count / max(len(growth_rates) - 1, 1)
        positive_growth_rate_ratio = positive_growth_rate_count / max(len(growth_rates), 1)
        growth_rate_improvement_pct = (growth_rates[-1] - growth_rates[0]) if len(growth_rates) >= 2 else 0.0
        trend_score = (
            accelerating_step_ratio * 35.0
            + positive_growth_rate_ratio * 20.0
            + _scale(growth_rate_improvement_pct, -20, 80) * 20.0
            + _scale(trend_growth_pct, 0, 120) * 10.0
            + _scale(latest_vs_recent_average_pct, -10, 40) * 8.0
            + _scale(yoy_pct or 0, -20, 80) * 7.0
        )
        ranked.append({
            **latest_row,
            "trend_score": trend_score,
            "slope_pct": slope_pct,
            "trend_growth_pct": trend_growth_pct,
            "growth_acceleration_pct": growth_acceleration_pct,
            "accelerating_step_count": accelerating_step_count,
            "positive_growth_rate_count": positive_growth_rate_count,
            "growth_rate_improvement_pct": growth_rate_improvement_pct,
            "growth_rates": growth_rates,
            "positive_step_count": positive_step_count,
            "month_count": len(valid_rows),
            "latest_vs_recent_average_pct": latest_vs_recent_average_pct,
            "revenue_history": [
                {
                    "report_month": row.get("report_month"),
                    "current_revenue": _to_float(row.get("current_revenue")),
                }
                for row in valid_rows
            ],
            "mom_pct": mom_pct,
            "yoy_pct": yoy_pct,
            "cumulative_yoy_pct": cumulative_yoy_pct,
        })

    ranked.sort(
        key=lambda row: (
            _to_float(row.get("trend_score")) or -9999,
            _to_float(row.get("growth_acceleration_pct")) or -9999,
            _to_float(row.get("slope_pct")) or -9999,
            _to_float(row.get("trend_growth_pct")) or -9999,
            _to_float(row.get("current_revenue")) or 0,
        ),
        reverse=True,
    )
    return ranked


def _linear_log_slope_pct(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    y_values = [math.log(max(value, 1.0)) for value in values]
    x_values = list(range(len(y_values)))
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return 0.0
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denominator
    return (math.exp(slope) - 1.0) * 100.0


def _growth_rates_pct(values: list[float], months: list[str]) -> list[float]:
    rates: list[float] = []
    for before, after, before_month, after_month in zip(values, values[1:], months, months[1:]):
        if before <= 0:
            continue
        month_gap = max(_month_index(after_month) - _month_index(before_month), 1)
        rates.append(((after / before) ** (1 / month_gap) - 1.0) * 100.0)
    return rates


def _month_index(month: str) -> int:
    try:
        year_text, month_text = month.split("-", 1)
        return int(year_text) * 12 + int(month_text)
    except (AttributeError, ValueError):
        return 0


def _linear_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    x_values = list(range(len(values)))
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(values) / len(values)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, values)) / denominator


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), lower), upper)


def _scale(value: float, lower: float, upper: float) -> float:
    if upper <= lower:
        return 0.0
    return (_clip(value, lower, upper) - lower) / (upper - lower)


def list_active_etf_snapshots(limit: int = 500, days: int = 30) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit), 1000))
    normalized_days = max(1, min(int(days), 120))
    with _connect_db("active_etf_history.db") as conn:
        latest = conn.execute(
            "SELECT MAX(snapshot_date) AS max_snapshot_date FROM etf_change_snapshots"
        ).fetchone()
        max_snapshot_date = latest["max_snapshot_date"] if latest else None
        start_snapshot_date = None
        if max_snapshot_date:
            start_snapshot_date = conn.execute(
                "SELECT date(?, '-' || ? || ' days') AS start_snapshot_date",
                (max_snapshot_date, normalized_days - 1),
            ).fetchone()["start_snapshot_date"]
        rows = conn.execute(
            """
            SELECT
                etf_code,
                snapshot_date,
                etf_name,
                from_date,
                to_date,
                issuer,
                holdings_count,
                turnover_rate,
                aum_100m,
                beneficiary_10k,
                change_count,
                add_count,
                increase_count,
                decrease_count,
                remove_count,
                updated_at
            FROM etf_change_snapshots
            WHERE snapshot_date BETWEEN COALESCE(?, snapshot_date) AND COALESCE(?, snapshot_date)
            ORDER BY snapshot_date DESC, etf_code
            LIMIT ?
            """,
            (start_snapshot_date, max_snapshot_date, normalized_limit),
        ).fetchall()
        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS snapshot_count,
                COUNT(DISTINCT etf_code) AS etf_count,
                MIN(snapshot_date) AS min_snapshot_date,
                MAX(snapshot_date) AS max_snapshot_date
            FROM etf_change_snapshots
            WHERE snapshot_date BETWEEN COALESCE(?, snapshot_date) AND COALESCE(?, snapshot_date)
            """
            ,
            (start_snapshot_date, max_snapshot_date),
        ).fetchone()
    return _json_safe(
        {
            "summary": {
                **dict(summary),
                "window_days": normalized_days,
                "window_start_date": start_snapshot_date,
                "window_end_date": max_snapshot_date,
            },
            "rows": _rows_to_dicts(rows),
        }
    )


def list_active_etf_changes(etf_code: str, snapshot_date: str | None = None, limit: int = 120) -> dict[str, Any]:
    normalized_code = str(etf_code or "").strip().upper()
    normalized_limit = max(1, min(int(limit), 500))
    with _connect_db("active_etf_history.db") as conn:
        if snapshot_date is None:
            latest = conn.execute(
                "SELECT MAX(snapshot_date) AS snapshot_date FROM etf_change_items WHERE etf_code = ?",
                (normalized_code,),
            ).fetchone()
            snapshot_date = latest["snapshot_date"] if latest else None
        if not snapshot_date:
            return {"etf_code": normalized_code, "snapshot_date": None, "rows": []}
        rows = conn.execute(
            """
            SELECT
                etf_code,
                snapshot_date,
                change_label,
                stock_code,
                stock_name,
                industry,
                shares_delta,
                shares_delta_lots,
                weight_delta,
                old_weight,
                new_weight,
                holding_amount_100m,
                new_lots
            FROM etf_change_items
            WHERE etf_code = ? AND snapshot_date = ?
            ORDER BY ABS(COALESCE(weight_delta, 0)) DESC, ABS(COALESCE(shares_delta, 0)) DESC
            LIMIT ?
            """,
            (normalized_code, snapshot_date, normalized_limit),
        ).fetchall()
    return _json_safe({"etf_code": normalized_code, "snapshot_date": snapshot_date, "rows": _rows_to_dicts(rows)})


def build_backtest_config_payload() -> dict[str, Any]:
    return {
        "default_buy_strategies": DEFAULT_BUY_STRATEGIES,
        "default_sell_strategies": DEFAULT_SELL_STRATEGIES,
        "buy_strategies": [
            {"key": key, **value}
            for key, value in BUY_STRATEGY_METADATA.items()
        ],
        "sell_strategies": [
            {"key": key, **value}
            for key, value in SELL_STRATEGY_METADATA.items()
        ],
    }


def list_research_companies(search_text: str | None = None, limit: int = 80) -> dict[str, Any]:
    normalized_limit = max(1, min(int(limit), 300))
    normalized_search = str(search_text or "").strip()
    params: list[Any] = []
    where_clause = ""
    if normalized_search:
        where_clause = """
        WHERE p.code LIKE ?
           OR p.name_zh LIKE ?
           OR p.full_name_zh LIKE ?
           OR p.industry LIKE ?
           OR a.theme LIKE ?
        """
        like_text = f"%{normalized_search}%"
        params.extend([like_text, like_text, like_text, like_text, like_text])

    with _connect_db("company_links.db") as conn:
        summary = conn.execute(
            """
            SELECT
                COUNT(*) AS company_count,
                (SELECT COUNT(DISTINCT theme) FROM company_theme_assignments) AS theme_count,
                MAX(updated_at) AS last_sync_at
            FROM company_profiles
            """
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT
                p.code,
                p.name_zh,
                p.full_name_zh,
                p.market,
                p.yfinance_symbol,
                p.industry,
                GROUP_CONCAT(DISTINCT a.theme) AS themes,
                MAX(COALESCE(a.confidence, 0)) AS confidence,
                MAX(COALESCE(a.updated_at, p.updated_at)) AS updated_at
            FROM company_profiles p
            LEFT JOIN company_theme_assignments a
              ON p.code = a.code
            {where_clause}
            GROUP BY
                p.code,
                p.name_zh,
                p.full_name_zh,
                p.market,
                p.yfinance_symbol,
                p.industry
            ORDER BY confidence DESC, p.code
            LIMIT ?
            """,
            (*params, normalized_limit),
        ).fetchall()
    payload_rows = []
    for row in _rows_to_dicts(rows):
        row["themes"] = [item for item in str(row.get("themes") or "").split(",") if item]
        payload_rows.append(row)
    return _json_safe({"summary": dict(summary), "rows": payload_rows})


def build_quote_summary(quotes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not quotes:
        return None

    latest = quotes[-1]
    previous = quotes[-2] if len(quotes) >= 2 else None
    close = latest.get("close")
    previous_close = previous.get("close") if previous else None
    change = None
    change_pct = None
    if close is not None and previous_close not in (None, 0):
        change = float(close) - float(previous_close)
        change_pct = change / float(previous_close) * 100

    return {
        "trade_date": latest.get("trade_date"),
        "open": latest.get("open"),
        "high": latest.get("high"),
        "low": latest.get("low"),
        "close": close,
        "volume": latest.get("volume"),
        "change": change,
        "change_pct": change_pct,
    }


def list_stock_institutional_history(stock_code: str, market: str = "TWSE", limit: int = 20) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), 60))
    normalized_code = str(stock_code or "").strip().zfill(4)
    with _connect_db("chip_cache.db") as conn:
        rows = conn.execute(
            """
            SELECT
                trade_date,
                market,
                code,
                name_zh,
                foreign_buy,
                foreign_sell,
                foreign_net,
                trust_buy,
                trust_sell,
                trust_net,
                dealer_buy,
                dealer_sell,
                dealer_net,
                total_net,
                fetched_at
            FROM institutional_trading
            WHERE code = ? AND market = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (normalized_code, market, normalized_limit),
        ).fetchall()
    return _rows_to_dicts(rows)


def list_stock_monthly_revenue(stock_code: str, limit: int = 12) -> list[dict[str, Any]]:
    normalized_limit = max(1, min(int(limit), 36))
    normalized_code = str(stock_code or "").strip().zfill(4)
    with _connect_db("revenue_cache.db") as conn:
        rows = conn.execute(
            """
            SELECT
                report_month,
                output_date,
                market,
                code,
                name_zh,
                industry,
                current_revenue,
                mom_pct,
                yoy_pct,
                cumulative_revenue,
                cumulative_yoy_pct,
                updated_at
            FROM monthly_revenue
            WHERE code = ?
            ORDER BY report_month DESC
            LIMIT ?
            """,
            (normalized_code, normalized_limit),
        ).fetchall()
    return _rows_to_dicts(rows)


def build_stock_overview(stock_id: str) -> dict[str, Any]:
    security = find_security(stock_id)
    if not security:
        return {
            "stock_id": stock_id,
            "found": False,
            "security": None,
            "price_cache": None,
            "latest_quote": None,
            "quotes": [],
            "broker_summary": None,
            "institutional_trading": [],
            "monthly_revenue": [],
        }

    symbol = security["yfinance_symbol"]
    market = security.get("market") or "TWSE"
    stock_code = security["code"]
    industry_lookup_df = get_company_official_industry_df()
    industry_lookup = dict(zip(industry_lookup_df["code"], industry_lookup_df["industry"])) if not industry_lookup_df.empty else {}
    security = {
        **security,
        "industry": industry_lookup.get(str(stock_code).zfill(4)) or security.get("industry_code"),
    }
    price_cache = get_price_cache_status(symbol)
    quotes = list_stock_price_history(symbol, limit=STOCK_CHART_HISTORY_LIMIT)
    broker_summary = get_latest_official_broker_summary(stock_code, market=market)

    broker_payload = None
    if broker_summary:
        broker_payload = {
            "trade_date": broker_summary.get("trade_date"),
            "source": broker_summary.get("source"),
            "imported_at": broker_summary.get("imported_at"),
            "row_count": broker_summary.get("row_count"),
            "buy_rank": broker_summary.get("buy_rank", [])[:5],
            "sell_rank": broker_summary.get("sell_rank", [])[:5],
        }

    return _json_safe(
        {
            "stock_id": stock_id,
            "found": True,
            "security": security,
            "price_cache": price_cache,
            "latest_quote": build_quote_summary(quotes),
            "quotes": quotes,
            "broker_summary": broker_payload,
            "institutional_trading": list_stock_institutional_history(stock_code, market=market, limit=20),
            "monthly_revenue": list_stock_monthly_revenue(stock_code, limit=12),
        }
    )
