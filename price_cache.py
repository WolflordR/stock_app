import sqlite3
import io
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

DB_PATH = Path(__file__).with_name("price_cache.db")
META_COLUMN_DEFINITIONS = {
    "first_cached_date": "TEXT",
    "last_cached_date": "TEXT",
    "last_trade_date": "TEXT",
    "last_checked_date": "TEXT",
    "row_count": "INTEGER NOT NULL DEFAULT 0",
    "source": "TEXT NOT NULL DEFAULT 'yfinance'",
    "fetch_status": "TEXT NOT NULL DEFAULT 'ready'",
    "last_error": "TEXT",
}


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_date(value):
    if not value:
        return None
    return pd.to_datetime(value).normalize()


def _format_date(value):
    if value is None:
        return None
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _max_date_str(*values):
    parsed = [ts for ts in (_parse_date(value) for value in values) if ts is not None]
    return _format_date(max(parsed)) if parsed else None


def init_price_cache():
    """建立歷史價格快取資料表。"""
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                symbol TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                PRIMARY KEY(symbol, trade_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_cache_meta (
                symbol TEXT PRIMARY KEY,
                last_updated_at TEXT NOT NULL,
                first_cached_date TEXT,
                last_cached_date TEXT,
                last_trade_date TEXT,
                last_checked_date TEXT,
                row_count INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'yfinance',
                fetch_status TEXT NOT NULL DEFAULT 'ready',
                last_error TEXT
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(price_cache_meta)").fetchall()
        }
        for column_name, column_definition in META_COLUMN_DEFINITIONS.items():
            if column_name not in existing_columns:
                conn.execute(
                    f"ALTER TABLE price_cache_meta ADD COLUMN {column_name} {column_definition}"
                )
        conn.commit()


def _normalize_history_df(df):
    """統一欄位與索引格式，方便寫入/讀取本地快取。"""
    if df.empty:
        return df

    df = df.copy().sort_index()
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)

    normalized = pd.DataFrame(
        {
            "Open": pd.to_numeric(df["Open"], errors="coerce"),
            "High": pd.to_numeric(df["High"], errors="coerce"),
            "Low": pd.to_numeric(df["Low"], errors="coerce"),
            "Close": pd.to_numeric(df["Close"], errors="coerce"),
            "Volume": pd.to_numeric(df["Volume"], errors="coerce"),
        },
        index=pd.to_datetime(df.index).normalize(),
    )
    normalized = normalized[~normalized.index.duplicated(keep="last")]
    return normalized.dropna(subset=["Open", "High", "Low", "Close"])


def _get_cache_bounds(symbol):
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT MIN(trade_date) AS min_date, MAX(trade_date) AS max_date, COUNT(*) AS row_count
            FROM price_history
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()

    return row["min_date"], row["max_date"], int(row["row_count"] or 0)


def _get_cache_meta(symbol):
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT symbol, last_updated_at, first_cached_date, last_cached_date,
                   last_trade_date, last_checked_date, row_count, source,
                   fetch_status, last_error
            FROM price_cache_meta
            WHERE symbol = ?
            """,
            (symbol,),
        ).fetchone()

    return dict(row) if row else None


def _ensure_symbol_meta_current(symbol):
    meta = _get_cache_meta(symbol)
    cache_min, cache_max, row_count = _get_cache_bounds(symbol)
    normalized_row_count = int(row_count or 0)
    needs_refresh = (
        meta is None
        or meta.get("first_cached_date") != cache_min
        or meta.get("last_cached_date") != cache_max
        or meta.get("last_trade_date") != cache_max
        or int(meta.get("row_count") or 0) != normalized_row_count
    )
    if not needs_refresh:
        return meta

    checked_through = None
    source = "yfinance"
    fetch_status = "ready"
    last_error = None
    if meta:
        checked_through = meta.get("last_checked_date") or cache_max
        source = meta.get("source") or source
        fetch_status = meta.get("fetch_status") or fetch_status
        last_error = meta.get("last_error")
    elif cache_max:
        checked_through = cache_max

    _update_cache_meta(
        symbol,
        checked_through=checked_through,
        source=source,
        fetch_status=fetch_status,
        last_error=last_error,
    )
    return _get_cache_meta(symbol)


def _load_cached_history(symbol, start_dt, end_dt):
    with _get_connection() as conn:
        rows = conn.execute(
            """
            SELECT trade_date, open, high, low, close, volume
            FROM price_history
            WHERE symbol = ? AND trade_date >= ? AND trade_date < ?
            ORDER BY trade_date
            """,
            (
                symbol,
                start_dt.strftime("%Y-%m-%d"),
                end_dt.strftime("%Y-%m-%d"),
            ),
        ).fetchall()

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(row) for row in rows])
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date")
    df.index.name = None
    return df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )


def _save_history(symbol, df):
    normalized = _normalize_history_df(df)
    with _get_connection() as conn:
        if not normalized.empty:
            rows = [
                (
                    symbol,
                    trade_date.strftime("%Y-%m-%d"),
                    float(row["Open"]),
                    float(row["High"]),
                    float(row["Low"]),
                    float(row["Close"]),
                    float(row["Volume"]) if pd.notna(row["Volume"]) else 0.0,
                )
                for trade_date, row in normalized.iterrows()
            ]
            conn.executemany(
                """
                INSERT INTO price_history(symbol, trade_date, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trade_date) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume
                """,
                rows,
            )
        conn.commit()


def _update_cache_meta(symbol, *, checked_through=None, source="yfinance", fetch_status="ready", last_error=None):
    cache_min, cache_max, row_count = _get_cache_bounds(symbol)
    existing_meta = _get_cache_meta(symbol) or {}
    updated_at = datetime.now().isoformat(timespec="seconds")
    first_cached_date = cache_min
    last_cached_date = cache_max
    last_trade_date = cache_max
    last_checked_date = _max_date_str(existing_meta.get("last_checked_date"), checked_through)

    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO price_cache_meta(
                symbol,
                last_updated_at,
                first_cached_date,
                last_cached_date,
                last_trade_date,
                last_checked_date,
                row_count,
                source,
                fetch_status,
                last_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                last_updated_at=excluded.last_updated_at,
                first_cached_date=excluded.first_cached_date,
                last_cached_date=excluded.last_cached_date,
                last_trade_date=excluded.last_trade_date,
                last_checked_date=excluded.last_checked_date,
                row_count=excluded.row_count,
                source=excluded.source,
                fetch_status=excluded.fetch_status,
                last_error=excluded.last_error
            """,
            (
                symbol,
                updated_at,
                first_cached_date,
                last_cached_date,
                last_trade_date,
                last_checked_date,
                row_count,
                source,
                fetch_status,
                last_error,
            ),
        )
        conn.commit()


def _fetch_remote_history(symbol, start_dt, end_dt):
    if start_dt >= end_dt:
        return pd.DataFrame()
    ticker = yf.Ticker(symbol)
    muted_output = io.StringIO()
    with redirect_stdout(muted_output), redirect_stderr(muted_output):
        return ticker.history(start=start_dt, end=end_dt)


def _build_missing_ranges(request_start, request_end, cache_min, cache_max, last_checked_date=None):
    missing_ranges = []
    request_last_day = (request_end - timedelta(days=1)).normalize()
    cache_min_ts = _parse_date(cache_min)
    cache_max_ts = _parse_date(cache_max)
    last_checked_ts = _parse_date(last_checked_date)
    effective_end_ts = max(
        [ts for ts in [cache_max_ts, last_checked_ts] if ts is not None],
        default=None,
    )

    if cache_min_ts is None or cache_max_ts is None:
        missing_ranges.append((request_start, request_end))
        return missing_ranges

    if request_start < cache_min_ts:
        missing_ranges.append((request_start, min(request_end, cache_min_ts)))

    if effective_end_ts is None or effective_end_ts < request_last_day:
        trailing_start = max(request_start, cache_max_ts + timedelta(days=1))
        if trailing_start < request_end:
            missing_ranges.append((trailing_start, request_end))

    return missing_ranges


def _append_indicator_columns(df):
    if df.empty:
        return df

    enriched = df.copy()
    close = enriched["Close"].astype("float64")
    for window in (5, 20, 60, 120, 240):
        enriched[f"MA{window}"] = close.rolling(window=window).mean()

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_gain = gains.rolling(window=14, min_periods=14).mean()
    avg_loss = losses.rolling(window=14, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    enriched["RSI14"] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    enriched["MACD"] = ema12 - ema26
    enriched["MACDSignal"] = enriched["MACD"].ewm(span=9, adjust=False).mean()
    enriched["MACDHist"] = enriched["MACD"] - enriched["MACDSignal"]
    return enriched


def get_price_cache_status(symbol):
    init_price_cache()
    meta = _ensure_symbol_meta_current(symbol)
    if meta:
        return meta

    cache_min, cache_max, row_count = _get_cache_bounds(symbol)
    return {
        "symbol": symbol,
        "last_updated_at": None,
        "first_cached_date": cache_min,
        "last_cached_date": cache_max,
        "last_trade_date": cache_max,
        "last_checked_date": None,
        "row_count": row_count,
        "source": "yfinance",
        "fetch_status": "missing",
        "last_error": None,
    }


def fetch_price_history(
    symbol,
    mode="即時選股",
    start_date=None,
    end_date=None,
    history_buffer_days=120,
    include_indicators=False,
):
    """先查本地快取，缺資料時再向 yfinance 抓取。"""
    init_price_cache()

    if mode == "歷史回測" and start_date and end_date:
        request_start = pd.to_datetime(start_date) - timedelta(days=history_buffer_days)
        request_end = pd.to_datetime(end_date) + timedelta(days=1)
    else:
        if end_date is not None:
            request_end = pd.to_datetime(end_date).normalize() + timedelta(days=1)
        else:
            request_end = pd.Timestamp.today().normalize() + timedelta(days=1)
        request_start = request_end - timedelta(days=max(history_buffer_days, 120))

    meta = _ensure_symbol_meta_current(symbol) or {}
    last_updated_at = _parse_date(meta.get("last_updated_at"))
    if (
        meta.get("fetch_status") == "failed"
        and int(meta.get("row_count") or 0) == 0
        and last_updated_at is not None
        and (pd.Timestamp.today().normalize() - last_updated_at).days <= 7
    ):
        return pd.DataFrame()

    cache_min, cache_max, _ = _get_cache_bounds(symbol)
    missing_ranges = _build_missing_ranges(
        request_start,
        request_end,
        cache_min,
        cache_max,
        meta.get("last_checked_date"),
    )

    for fetch_start, fetch_end in missing_ranges:
        checked_through = _format_date(fetch_end - timedelta(days=1))
        try:
            fetched_df = _fetch_remote_history(symbol, fetch_start, fetch_end)
            _save_history(symbol, fetched_df)
            _update_cache_meta(
                symbol,
                checked_through=checked_through,
                source="yfinance",
                fetch_status="ready",
                last_error=None,
            )
        except Exception as exc:
            _update_cache_meta(
                symbol,
                checked_through=checked_through,
                source="yfinance",
                fetch_status="failed",
                last_error=str(exc),
            )
            raise

    cached_df = _load_cached_history(symbol, request_start, request_end)
    normalized_df = _normalize_history_df(cached_df)
    if include_indicators:
        return _append_indicator_columns(normalized_df)
    return normalized_df
