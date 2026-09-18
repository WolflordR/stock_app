from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from modules.core.project_paths import db_path


DB_PATH = db_path("broker_daily_trades.db")

HEADER_ALIASES = {
    "trade_date": ["交易日期", "日期", "成交日期"],
    "stock_code": ["證券代號", "股票代號", "代號"],
    "stock_name": ["證券名稱", "股票名稱", "名稱"],
    "broker_code": ["券商代號", "證券商代號", "證券商代碼"],
    "broker_name": ["券商名稱", "證券商名稱", "證券商", "券商"],
    "price": ["成交單價", "單價", "成交價格", "價格"],
    "buy_shares": ["買進股數", "買進數量", "買進", "買股數"],
    "sell_shares": ["賣出股數", "賣出數量", "賣出", "賣股數"],
}


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize_market(market: str | None) -> str:
    text = str(market or "").strip().upper()
    if text in {"TWSE", "上市"}:
        return "TWSE"
    if text in {"TPEX", "TWO", "OTC", "上櫃"}:
        return "TPEX"
    return text or "TWSE"


def _normalize_market_filter(market: str | None) -> str | None:
    text = str(market or "").strip().upper()
    if text in {"", "ALL", "全部"}:
        return None
    return _normalize_market(text)


def init_official_broker_db():
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS broker_trade_reports (
                market TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT,
                source TEXT NOT NULL,
                raw_file_name TEXT,
                imported_at TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                PRIMARY KEY (market, trade_date, stock_code, source)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS broker_trade_lines (
                market TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                row_no INTEGER NOT NULL,
                broker_code TEXT,
                broker_name TEXT NOT NULL,
                price REAL,
                buy_shares REAL NOT NULL,
                sell_shares REAL NOT NULL,
                raw_json TEXT NOT NULL,
                PRIMARY KEY (market, trade_date, stock_code, row_no)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_broker_trade_lines_lookup ON broker_trade_lines(market, trade_date, stock_code)"
        )
        conn.commit()


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in {"", "-", "--", "---", "－", "None", "nan"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_header(text: str) -> str:
    return "".join(str(text or "").strip().replace("\ufeff", "").split())


def _decode_csv_bytes(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp950", "big5", "utf-8"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _clean_twse_formula_text(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith('="') and text.endswith('"'):
        return text[2:-1].strip()
    return text.strip('"').strip()


def _split_broker_code_name(value: Any) -> tuple[str, str]:
    text = _normalize_header(value)
    match = re.match(r"^([0-9A-Z]{4})(.+)$", text)
    if not match:
        return "", text
    return match.group(1), match.group(2).strip()


def _extract_stock_code_from_preamble(rows: list[list[str]], header_idx: int) -> str | None:
    for row in rows[:header_idx]:
        if len(row) >= 2 and _normalize_header(row[0]) in {"股票代碼", "證券代號"}:
            match = re.search(r"\d{4,6}", _clean_twse_formula_text(row[1]))
            if match:
                return match.group(0)
    return None


def _build_wide_twse_frame(rows: list[list[str]], header_idx: int) -> pd.DataFrame | None:
    header = [_normalize_header(cell) for cell in rows[header_idx]]
    broker_columns = [
        idx
        for idx, name in enumerate(header)
        if name in {_normalize_header(alias) for alias in HEADER_ALIASES["broker_name"]}
    ]
    if len(broker_columns) < 2:
        return None

    stock_code = _extract_stock_code_from_preamble(rows, header_idx) or ""
    records: list[dict[str, Any]] = []
    for source_row in rows[header_idx + 1 :]:
        for broker_idx in broker_columns:
            if broker_idx + 3 >= len(header):
                continue
            price_idx = broker_idx + 1
            buy_idx = broker_idx + 2
            sell_idx = broker_idx + 3
            if header[price_idx] != "價格" or header[buy_idx] != "買進股數" or header[sell_idx] != "賣出股數":
                continue
            broker_value = source_row[broker_idx] if broker_idx < len(source_row) else ""
            price_value = source_row[price_idx] if price_idx < len(source_row) else ""
            buy_value = source_row[buy_idx] if buy_idx < len(source_row) else ""
            sell_value = source_row[sell_idx] if sell_idx < len(source_row) else ""
            if not str(broker_value).strip():
                continue
            broker_code, broker_name = _split_broker_code_name(broker_value)
            records.append(
                {
                    "股票代碼": stock_code,
                    "券商代號": broker_code,
                    "券商名稱": broker_name,
                    "價格": price_value,
                    "買進股數": buy_value,
                    "賣出股數": sell_value,
                }
            )

    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records)


def _load_csv_frame(csv_path: str | Path) -> pd.DataFrame:
    raw = Path(csv_path).read_bytes()
    text = _decode_csv_bytes(raw)
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return pd.DataFrame()

    header_idx = None
    for idx, row in enumerate(rows[:20]):
        header_set = {_normalize_header(cell) for cell in row}
        if any(_normalize_header(alias) in header_set for alias in HEADER_ALIASES["broker_name"]) and any(
            _normalize_header(alias) in header_set for alias in HEADER_ALIASES["price"]
        ):
            header_idx = idx
            break

    if header_idx is None:
        raise ValueError("找不到官方 CSV 欄位列，請確認檔案內容是否為券商買賣日報表。")

    wide_frame = _build_wide_twse_frame(rows, header_idx)
    if wide_frame is not None:
        return wide_frame.reset_index(drop=True)

    header = rows[header_idx]
    data_rows = rows[header_idx + 1 :]
    frame = pd.DataFrame(data_rows, columns=header)
    frame.columns = [_normalize_header(column) for column in frame.columns]
    frame = frame.dropna(how="all")
    frame = frame[~(frame.apply(lambda row: all(str(value).strip() == "" for value in row), axis=1))]
    return frame.reset_index(drop=True)


def _resolve_column(frame: pd.DataFrame, aliases: list[str]) -> str | None:
    normalized_columns = {_normalize_header(column): column for column in frame.columns}
    for alias in aliases:
        normalized = _normalize_header(alias)
        if normalized in normalized_columns:
            return normalized_columns[normalized]
    return None


def _canonicalize_broker_frame(
    frame: pd.DataFrame,
    *,
    default_trade_date: str | None = None,
    default_stock_code: str | None = None,
    default_stock_name: str | None = None,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "trade_date",
                "stock_code",
                "stock_name",
                "broker_code",
                "broker_name",
                "price",
                "buy_shares",
                "sell_shares",
            ]
        )

    mapped = {}
    for field, aliases in HEADER_ALIASES.items():
        column = _resolve_column(frame, aliases)
        if column:
            mapped[field] = frame[column]

    result = pd.DataFrame(index=frame.index)
    result["trade_date"] = mapped.get("trade_date", default_trade_date)
    result["stock_code"] = mapped.get("stock_code", default_stock_code)
    result["stock_name"] = mapped.get("stock_name", default_stock_name)
    result["broker_code"] = mapped.get("broker_code")
    result["broker_name"] = mapped.get("broker_name")
    result["price"] = mapped.get("price")
    result["buy_shares"] = mapped.get("buy_shares", 0)
    result["sell_shares"] = mapped.get("sell_shares", 0)

    for column in ["trade_date", "stock_code", "stock_name", "broker_code", "broker_name"]:
        result[column] = result[column].fillna("").astype(str).str.strip()

    result["price"] = result["price"].map(_parse_number)
    result["buy_shares"] = result["buy_shares"].map(_parse_number).fillna(0.0)
    result["sell_shares"] = result["sell_shares"].map(_parse_number).fillna(0.0)

    result = result[result["broker_name"] != ""].copy()
    result = result[(result["buy_shares"] > 0) | (result["sell_shares"] > 0)].copy()
    return result.reset_index(drop=True)


def import_official_broker_csv(
    csv_path: str | Path,
    *,
    market: str = "TWSE",
    trade_date: str | None = None,
    stock_code: str | None = None,
    stock_name: str | None = None,
    source: str = "TWSE_CSV_MANUAL",
) -> dict[str, Any]:
    init_official_broker_db()
    frame = _load_csv_frame(csv_path)
    canonical = _canonicalize_broker_frame(
        frame,
        default_trade_date=trade_date,
        default_stock_code=stock_code,
        default_stock_name=stock_name,
    )
    if canonical.empty:
        raise ValueError("CSV 解析後沒有有效的券商成交明細。")

    report_trade_date = canonical["trade_date"].replace("", pd.NA).dropna().astype(str).iloc[0]
    report_stock_code = canonical["stock_code"].replace("", pd.NA).dropna().astype(str).iloc[0]
    report_stock_name = canonical["stock_name"].replace("", pd.NA).dropna().astype(str).iloc[0] if canonical["stock_name"].replace("", pd.NA).dropna().any() else (stock_name or "")

    imported_at = datetime.now().isoformat(timespec="seconds")
    rows_payload = []
    for idx, row in enumerate(canonical.itertuples(index=False), start=1):
        raw_row = {
            "trade_date": row.trade_date,
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "broker_code": row.broker_code,
            "broker_name": row.broker_name,
            "price": row.price,
            "buy_shares": row.buy_shares,
            "sell_shares": row.sell_shares,
        }
        rows_payload.append(
            (
                market,
                report_trade_date,
                report_stock_code,
                int(idx),
                row.broker_code or "",
                row.broker_name,
                row.price,
                float(row.buy_shares),
                float(row.sell_shares),
                json.dumps(raw_row, ensure_ascii=False),
            )
        )

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO broker_trade_reports (
                market, trade_date, stock_code, stock_name, source,
                raw_file_name, imported_at, row_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(market, trade_date, stock_code, source) DO UPDATE SET
                stock_name=excluded.stock_name,
                raw_file_name=excluded.raw_file_name,
                imported_at=excluded.imported_at,
                row_count=excluded.row_count
            """,
            (
                market,
                report_trade_date,
                report_stock_code,
                report_stock_name,
                source,
                Path(csv_path).name,
                imported_at,
                len(rows_payload),
            ),
        )
        conn.execute(
            "DELETE FROM broker_trade_lines WHERE market = ? AND trade_date = ? AND stock_code = ?",
            (market, report_trade_date, report_stock_code),
        )
        conn.executemany(
            """
            INSERT INTO broker_trade_lines (
                market, trade_date, stock_code, row_no, broker_code, broker_name,
                price, buy_shares, sell_shares, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows_payload,
        )
        conn.commit()

    return {
        "market": market,
        "trade_date": report_trade_date,
        "stock_code": report_stock_code,
        "stock_name": report_stock_name,
        "row_count": len(rows_payload),
        "source": source,
        "raw_file_name": __import__("pathlib").Path(csv_path).name,
    }


def get_official_broker_summary(
    stock_code: str,
    trade_date: str,
    *,
    market: str = "TWSE",
) -> dict[str, Any] | None:
    init_official_broker_db()
    market = _normalize_market(market)
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT broker_code, broker_name, price, buy_shares, sell_shares
            FROM broker_trade_lines
            WHERE market = ? AND trade_date = ? AND stock_code = ?
            ORDER BY row_no
            """,
            (market, trade_date, stock_code),
        ).fetchall()
        report = conn.execute(
            """
            SELECT stock_name, source, raw_file_name, imported_at, row_count
            FROM broker_trade_reports
            WHERE market = ? AND trade_date = ? AND stock_code = ?
            """,
            (market, trade_date, stock_code),
        ).fetchone()

    if not rows or not report:
        return None

    frame = pd.DataFrame([dict(row) for row in rows])
    frame["buy_amount"] = frame["price"].fillna(0.0) * frame["buy_shares"].fillna(0.0)
    frame["sell_amount"] = frame["price"].fillna(0.0) * frame["sell_shares"].fillna(0.0)
    grouped = (
        frame.groupby(["broker_code", "broker_name"], dropna=False, as_index=False)
        .agg(
            buy_shares=("buy_shares", "sum"),
            sell_shares=("sell_shares", "sum"),
            buy_amount=("buy_amount", "sum"),
            sell_amount=("sell_amount", "sum"),
        )
        .copy()
    )
    grouped["net_shares"] = grouped["buy_shares"] - grouped["sell_shares"]
    grouped["avg_buy_price"] = grouped.apply(
        lambda row: (row["buy_amount"] / row["buy_shares"]) if row["buy_shares"] else None,
        axis=1,
    )
    grouped["avg_sell_price"] = grouped.apply(
        lambda row: (row["sell_amount"] / row["sell_shares"]) if row["sell_shares"] else None,
        axis=1,
    )

    buy_rank = grouped[grouped["net_shares"] > 0].sort_values("net_shares", ascending=False).head(15)
    sell_rank = grouped[grouped["net_shares"] < 0].sort_values("net_shares", ascending=True).head(15)

    return {
        "market": market,
        "trade_date": trade_date,
        "stock_code": stock_code,
        "stock_name": report["stock_name"],
        "source": report["source"],
        "raw_file_name": report["raw_file_name"],
        "imported_at": report["imported_at"],
        "row_count": report["row_count"],
        "buy_rank": buy_rank.to_dict("records"),
        "sell_rank": sell_rank.to_dict("records"),
        "raw_rows": frame.to_dict("records"),
    }


def get_latest_official_broker_summary(
    stock_code: str,
    *,
    market: str = "TWSE",
) -> dict[str, Any] | None:
    init_official_broker_db()
    market = _normalize_market(market)
    with _get_connection() as conn:
        latest_row = conn.execute(
            """
            SELECT trade_date
            FROM broker_trade_reports
            WHERE market = ? AND stock_code = ?
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (market, stock_code),
        ).fetchone()
    if not latest_row:
        return None
    return get_official_broker_summary(stock_code, str(latest_row["trade_date"]), market=market)


def get_official_broker_db_overview(*, market: str | None = None) -> dict[str, Any]:
    init_official_broker_db()
    market_filter = _normalize_market_filter(market)
    with _get_connection() as conn:
        if market_filter:
            report_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS report_count,
                    COUNT(DISTINCT trade_date) AS trade_day_count,
                    COUNT(DISTINCT stock_code) AS stock_count,
                    MAX(trade_date) AS latest_trade_date
                FROM broker_trade_reports
                WHERE market = ?
                """,
                (market_filter,),
            ).fetchone()
            branch_row = conn.execute(
                """
                SELECT COUNT(DISTINCT broker_name) AS branch_count
                FROM broker_trade_lines
                WHERE market = ?
                """,
                (market_filter,),
            ).fetchone()
        else:
            report_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS report_count,
                    COUNT(DISTINCT trade_date) AS trade_day_count,
                    COUNT(DISTINCT stock_code) AS stock_count,
                    MAX(trade_date) AS latest_trade_date
                FROM broker_trade_reports
                """
            ).fetchone()
            branch_row = conn.execute(
                """
                SELECT COUNT(DISTINCT broker_name) AS branch_count
                FROM broker_trade_lines
                """
            ).fetchone()

    return {
        "report_count": int(report_row["report_count"] or 0),
        "trade_day_count": int(report_row["trade_day_count"] or 0),
        "stock_count": int(report_row["stock_count"] or 0),
        "branch_count": int(branch_row["branch_count"] or 0),
        "latest_trade_date": report_row["latest_trade_date"] or "",
    }


def list_official_broker_branches(
    *,
    search_text: str | None = None,
    market: str | None = None,
    limit: int = 200,
) -> pd.DataFrame:
    init_official_broker_db()
    market_filter = _normalize_market_filter(market)
    search_value = f"%{str(search_text or '').strip()}%"
    query = """
        SELECT
            broker_name,
            COUNT(DISTINCT trade_date) AS trade_days,
            COUNT(DISTINCT stock_code) AS stock_count,
            MAX(trade_date) AS last_trade_date,
            SUM(buy_shares) AS total_buy_shares,
            SUM(sell_shares) AS total_sell_shares,
            SUM(buy_shares) - SUM(sell_shares) AS total_net_shares
        FROM broker_trade_lines
        WHERE broker_name != ''
          AND (? IS NULL OR market = ?)
          AND (? = '%%' OR broker_name LIKE ?)
        GROUP BY broker_name
        ORDER BY ABS(total_net_shares) DESC, last_trade_date DESC, broker_name ASC
        LIMIT ?
    """
    with _get_connection() as conn:
        frame = pd.read_sql_query(
            query,
            conn,
            params=(market_filter, market_filter, search_value, search_value, int(limit)),
        )

    if frame.empty:
        return frame

    numeric_columns = ["trade_days", "stock_count", "total_buy_shares", "total_sell_shares", "total_net_shares"]
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["trade_days"] = frame["trade_days"].astype(int)
    frame["stock_count"] = frame["stock_count"].astype(int)
    return frame


def get_official_broker_branch_activity(
    broker_name: str,
    *,
    days_window: int = 5,
    market: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    init_official_broker_db()
    normalized_branch = str(broker_name or "").strip()
    if not normalized_branch:
        return {
            "broker_name": "",
            "days_window": int(days_window),
            "trade_dates": [],
            "activity_df": pd.DataFrame(),
        }

    market_filter = _normalize_market_filter(market)
    query = """
        WITH recent_dates AS (
            SELECT DISTINCT trade_date
            FROM broker_trade_reports
            WHERE (? IS NULL OR market = ?)
            ORDER BY trade_date DESC
            LIMIT ?
        ),
        stock_meta AS (
            SELECT market, trade_date, stock_code, MAX(stock_name) AS stock_name
            FROM broker_trade_reports
            GROUP BY market, trade_date, stock_code
        )
        SELECT
            l.market,
            l.stock_code,
            COALESCE(MAX(m.stock_name), '') AS stock_name,
            COUNT(DISTINCT l.trade_date) AS active_days,
            SUM(l.buy_shares) AS buy_shares,
            SUM(l.sell_shares) AS sell_shares,
            SUM(l.buy_shares) - SUM(l.sell_shares) AS net_shares,
            SUM(COALESCE(l.price, 0) * l.buy_shares) AS buy_amount,
            SUM(COALESCE(l.price, 0) * l.sell_shares) AS sell_amount
        FROM broker_trade_lines l
        JOIN recent_dates d
          ON l.trade_date = d.trade_date
        LEFT JOIN stock_meta m
          ON l.market = m.market
         AND l.trade_date = m.trade_date
         AND l.stock_code = m.stock_code
        WHERE l.broker_name = ?
          AND (? IS NULL OR l.market = ?)
        GROUP BY l.market, l.stock_code
        HAVING SUM(l.buy_shares) > 0 OR SUM(l.sell_shares) > 0
        ORDER BY ABS(net_shares) DESC, net_shares DESC, l.stock_code ASC
        LIMIT ?
    """
    with _get_connection() as conn:
        trade_dates = [
            str(row["trade_date"])
            for row in conn.execute(
                """
                SELECT DISTINCT trade_date
                FROM broker_trade_reports
                WHERE (? IS NULL OR market = ?)
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (market_filter, market_filter, int(days_window)),
            ).fetchall()
        ]
        frame = pd.read_sql_query(
            query,
            conn,
            params=(market_filter, market_filter, int(days_window), normalized_branch, market_filter, market_filter, int(limit)),
        )

    if frame.empty:
        return {
            "broker_name": normalized_branch,
            "days_window": int(days_window),
            "trade_dates": trade_dates,
            "activity_df": frame,
        }

    for column in ["active_days", "buy_shares", "sell_shares", "net_shares", "buy_amount", "sell_amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["active_days"] = frame["active_days"].astype(int)
    frame["avg_buy_price"] = frame.apply(
        lambda row: (row["buy_amount"] / row["buy_shares"]) if row["buy_shares"] else None,
        axis=1,
    )
    frame["avg_sell_price"] = frame.apply(
        lambda row: (row["sell_amount"] / row["sell_shares"]) if row["sell_shares"] else None,
        axis=1,
    )

    return {
        "broker_name": normalized_branch,
        "days_window": int(days_window),
        "trade_dates": trade_dates,
        "activity_df": frame,
    }


def get_official_stock_broker_activity(
    stock_code: str,
    *,
    days_window: int = 5,
    market: str | None = None,
    end_trade_date: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    init_official_broker_db()
    normalized_stock_code = str(stock_code or "").strip()
    if not normalized_stock_code:
        return {
            "stock_code": "",
            "stock_name": "",
            "days_window": int(days_window),
            "trade_dates": [],
            "activity_df": pd.DataFrame(),
        }

    market_filter = _normalize_market_filter(market)
    query = """
        WITH recent_dates AS (
            SELECT DISTINCT trade_date
            FROM broker_trade_reports
            WHERE stock_code = ?
              AND (? IS NULL OR market = ?)
              AND (? IS NULL OR trade_date <= ?)
            ORDER BY trade_date DESC
            LIMIT ?
        )
        SELECT
            l.broker_name,
            COUNT(DISTINCT l.trade_date) AS active_days,
            SUM(l.buy_shares) AS buy_shares,
            SUM(l.sell_shares) AS sell_shares,
            SUM(l.buy_shares) - SUM(l.sell_shares) AS net_shares,
            SUM(COALESCE(l.price, 0) * l.buy_shares) AS buy_amount,
            SUM(COALESCE(l.price, 0) * l.sell_shares) AS sell_amount,
            MAX(r.stock_name) AS stock_name
        FROM broker_trade_lines l
        JOIN recent_dates d
          ON l.trade_date = d.trade_date
        LEFT JOIN broker_trade_reports r
          ON l.market = r.market
         AND l.trade_date = r.trade_date
         AND l.stock_code = r.stock_code
        WHERE l.stock_code = ?
          AND (? IS NULL OR l.market = ?)
        GROUP BY l.broker_name
        HAVING SUM(l.buy_shares) > 0 OR SUM(l.sell_shares) > 0
        ORDER BY ABS(net_shares) DESC, net_shares DESC, l.broker_name ASC
        LIMIT ?
    """
    with _get_connection() as conn:
        trade_dates = [
            str(row["trade_date"])
            for row in conn.execute(
                """
                SELECT DISTINCT trade_date
                FROM broker_trade_reports
                WHERE stock_code = ?
                  AND (? IS NULL OR market = ?)
                  AND (? IS NULL OR trade_date <= ?)
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (
                    normalized_stock_code,
                    market_filter,
                    market_filter,
                    end_trade_date,
                    end_trade_date,
                    int(days_window),
                ),
            ).fetchall()
        ]
        frame = pd.read_sql_query(
            query,
            conn,
            params=(
                normalized_stock_code,
                market_filter,
                market_filter,
                end_trade_date,
                end_trade_date,
                int(days_window),
                normalized_stock_code,
                market_filter,
                market_filter,
                int(limit),
            ),
        )

    if frame.empty:
        return {
            "stock_code": normalized_stock_code,
            "stock_name": "",
            "days_window": int(days_window),
            "trade_dates": trade_dates,
            "activity_df": frame,
        }

    for column in ["active_days", "buy_shares", "sell_shares", "net_shares", "buy_amount", "sell_amount"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    frame["active_days"] = frame["active_days"].astype(int)
    frame["avg_buy_price"] = frame.apply(
        lambda row: (row["buy_amount"] / row["buy_shares"]) if row["buy_shares"] else None,
        axis=1,
    )
    frame["avg_sell_price"] = frame.apply(
        lambda row: (row["sell_amount"] / row["sell_shares"]) if row["sell_shares"] else None,
        axis=1,
    )
    stock_name = str(frame["stock_name"].dropna().iloc[0] if frame["stock_name"].notna().any() else "")

    return {
        "stock_code": normalized_stock_code,
        "stock_name": stock_name,
        "days_window": int(days_window),
        "trade_dates": trade_dates,
        "activity_df": frame,
    }
