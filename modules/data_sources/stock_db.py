import csv
import io
import sqlite3
from datetime import datetime
from pathlib import Path
from functools import lru_cache

from modules.core.http_utils import request_bytes

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "stocks.db"

LISTED_CSV_URL = "https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv"
OTC_CSV_URL = "https://dts.twse.com.tw/opendata/t187ap03_O.csv"


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_stock_db():
    """建立股票主檔資料表與簡單的更新紀錄表。"""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS securities (
                code TEXT NOT NULL,
                name_zh TEXT NOT NULL,
                full_name_zh TEXT,
                market TEXT NOT NULL,
                yfinance_symbol TEXT PRIMARY KEY,
                industry_code TEXT,
                paid_in_capital REAL,
                issued_common_shares REAL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_securities_code ON securities(code)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(securities)").fetchall()
        }
        if "paid_in_capital" not in existing_columns:
            conn.execute("ALTER TABLE securities ADD COLUMN paid_in_capital REAL")
        if "issued_common_shares" not in existing_columns:
            conn.execute("ALTER TABLE securities ADD COLUMN issued_common_shares REAL")
        conn.commit()


def _parse_numeric(value):
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "--", "---", "－"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _download_csv_rows(url):
    """下載官方股票主檔 CSV，並處理 TWSE 憑證驗證較嚴格的情況。"""
    raw = request_bytes(
        url,
        headers={"Accept": "text/csv,*/*;q=0.8"},
    )
    text = raw.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


@lru_cache(maxsize=1)
def _load_official_security_rows():
    listed_rows = _download_csv_rows(LISTED_CSV_URL)
    otc_rows = _download_csv_rows(OTC_CSV_URL)
    merged = {}
    for market, rows in (("TWSE", listed_rows), ("TPEx", otc_rows)):
        for row in rows:
            code = (row.get("公司代號") or "").strip()
            if len(code) == 4 and code.isdigit():
                merged[code] = {
                    "market": market,
                    "paid_in_capital": _parse_numeric(row.get("實收資本額")),
                    "issued_common_shares": _parse_numeric(row.get("已發行普通股數或TDR原股發行股數")),
                }
    return merged


def refresh_stock_db():
    """從官方上市/上櫃資料重新整理本地股票主檔。"""
    init_stock_db()
    listed_rows = _download_csv_rows(LISTED_CSV_URL)
    otc_rows = _download_csv_rows(OTC_CSV_URL)
    updated_at = datetime.now().isoformat(timespec="seconds")

    securities = []
    for market, suffix, rows in (
        ("TWSE", ".TW", listed_rows),
        ("TPEx", ".TWO", otc_rows),
    ):
        for row in rows:
            code = (row.get("公司代號") or "").strip()
            short_name = (row.get("公司簡稱") or row.get("公司名稱") or "").strip()
            full_name = (row.get("公司名稱") or "").strip()
            industry_code = (row.get("產業別") or "").strip()
            paid_in_capital = _parse_numeric(row.get("實收資本額"))
            issued_common_shares = _parse_numeric(row.get("已發行普通股數或TDR原股發行股數"))

            # 只保留一般常見的 4 碼股票代號，先排除權證、特別商品與雜訊資料。
            if not (len(code) == 4 and code.isdigit() and short_name):
                continue

            securities.append(
                (
                    code,
                    short_name,
                    full_name,
                    market,
                    f"{code}{suffix}",
                    industry_code,
                    paid_in_capital,
                    issued_common_shares,
                    updated_at,
                )
            )

    with _get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS securities")
        conn.execute(
            """
            CREATE TABLE securities (
                code TEXT NOT NULL,
                name_zh TEXT NOT NULL,
                full_name_zh TEXT,
                market TEXT NOT NULL,
                yfinance_symbol TEXT PRIMARY KEY,
                industry_code TEXT,
                paid_in_capital REAL,
                issued_common_shares REAL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX idx_securities_code ON securities(code)")
        conn.execute("DELETE FROM securities")
        conn.executemany(
            """
            INSERT INTO securities (
                code, name_zh, full_name_zh, market, yfinance_symbol, industry_code, paid_in_capital, issued_common_shares, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            securities,
        )
        conn.execute(
            """
            INSERT INTO metadata(key, value) VALUES ('last_sync_at', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (updated_at,),
        )
        conn.commit()

    return {
        "count": len(securities),
        "last_sync_at": updated_at,
    }


def ensure_stock_db():
    """確保股票主檔可用；若資料庫不存在或為空就自動下載。"""
    init_stock_db()
    with _get_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM securities").fetchone()
        count = row["count"]

    if count == 0:
        return refresh_stock_db()

    return get_stock_db_status()


def get_stock_db_status():
    """回傳主檔目前股票數量與最後更新時間。"""
    init_stock_db()
    with _get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS count FROM securities").fetchone()["count"]
        meta = conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_sync_at'"
        ).fetchone()

    return {
        "count": count,
        "last_sync_at": meta["value"] if meta else None,
    }


def get_stock_name(stock_id):
    """用股票代號或 yfinance symbol 找中文簡稱。"""
    init_stock_db()
    code = stock_id.split(".")[0]
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT name_zh
            FROM securities
            WHERE yfinance_symbol = ? OR code = ?
            ORDER BY CASE WHEN yfinance_symbol = ? THEN 0 ELSE 1 END, market
            LIMIT 1
            """,
            (stock_id, code, stock_id),
        ).fetchone()

    return row["name_zh"] if row else "台灣個股"


def find_security(stock_input):
    """用股票代號或 yfinance symbol 找主檔資料。"""
    init_stock_db()
    normalized = (stock_input or "").strip().upper()
    if not normalized:
        return None

    code = normalized.split(".")[0]
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT code, name_zh, full_name_zh, market, yfinance_symbol, industry_code, paid_in_capital, issued_common_shares
            FROM securities
            WHERE yfinance_symbol = ? OR code = ?
            ORDER BY
                CASE WHEN yfinance_symbol = ? THEN 0 ELSE 1 END,
                CASE market WHEN 'TWSE' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (normalized, code, normalized),
        ).fetchone()

    return dict(row) if row else None


def get_security_share_profile(stock_input):
    security = find_security(stock_input)
    if security and security.get("issued_common_shares"):
        return {
            "code": security["code"],
            "market": security.get("market"),
            "paid_in_capital": security.get("paid_in_capital"),
            "issued_common_shares": security.get("issued_common_shares"),
        }

    code = str(stock_input or "").strip().upper().split(".")[0]
    official_rows = _load_official_security_rows()
    profile = official_rows.get(code)
    if not profile:
        return None
    return {
        "code": code,
        **profile,
    }


def get_securities_in_range(start_num, end_num):
    """只抓指定區間內真正存在的上市/上櫃股票，避免大量 not found。"""
    init_stock_db()
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT code, name_zh, market, yfinance_symbol
            FROM securities
            WHERE CAST(code AS INTEGER) BETWEEN ? AND ?
            ORDER BY CAST(code AS INTEGER)
            """,
            (int(start_num), int(end_num)),
        ).fetchall()

    return [dict(row) for row in rows]
