from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from modules.core.project_paths import data_path


DB_PATH = data_path("broker_daily_trades.db")

HEADER_ALIASES = {
    "trade_date": ["交易日期", "日期", "成交日期"],
    "stock_code": ["證券代號", "股票代號", "代號"],
    "stock_name": ["證券名稱", "股票名稱", "名稱"],
    "broker_code": ["券商代號", "證券商代號", "證券商代碼"],
    "broker_name": ["券商名稱", "證券商名稱", "證券商"],
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
    for idx, row in canonical.iterrows():
        rows_payload.append(
            (
                market,
                report_trade_date,
                report_stock_code,
                int(idx + 1),
                row["broker_code"] or "",
                row["broker_name"],
                row["price"],
                float(row["buy_shares"]),
                float(row["sell_shares"]),
                json.dumps(row.to_dict(), ensure_ascii=False),
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
