from __future__ import annotations

import pickle
import sqlite3
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DB_PATH = PROJECT_ROOT / "ui_persistent_cache.db"


def _get_connection():
    conn = sqlite3.connect(str(CACHE_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS persistent_cache (
            namespace TEXT NOT NULL,
            cache_key TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            payload BLOB NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (namespace, cache_key)
        )
        """
    )
    return conn


def _normalize_key(key_parts) -> str:
    return repr(tuple(key_parts))


def load_persistent_cache(namespace: str, key_parts):
    cache_key = _normalize_key(key_parts)
    now_ts = int(time.time())
    with _get_connection() as conn:
        row = conn.execute(
            """
            SELECT payload, expires_at
            FROM persistent_cache
            WHERE namespace = ? AND cache_key = ?
            """,
            (str(namespace), cache_key),
        ).fetchone()
        if not row:
            return None, False
        payload, expires_at = row
        if int(expires_at or 0) < now_ts:
            conn.execute(
                "DELETE FROM persistent_cache WHERE namespace = ? AND cache_key = ?",
                (str(namespace), cache_key),
            )
            return None, False
        try:
            return pickle.loads(payload), True
        except Exception:
            conn.execute(
                "DELETE FROM persistent_cache WHERE namespace = ? AND cache_key = ?",
                (str(namespace), cache_key),
            )
            return None, False


def save_persistent_cache(namespace: str, key_parts, value, ttl_seconds: int):
    cache_key = _normalize_key(key_parts)
    now_ts = int(time.time())
    expires_at = now_ts + int(ttl_seconds)
    payload = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    with _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO persistent_cache (namespace, cache_key, expires_at, payload, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(namespace, cache_key) DO UPDATE SET
                expires_at = excluded.expires_at,
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (str(namespace), cache_key, expires_at, payload, now_ts),
        )


def load_or_compute_persistent_cache(namespace: str, key_parts, ttl_seconds: int, builder):
    cached_value, cache_hit = load_persistent_cache(namespace, key_parts)
    if cache_hit:
        return cached_value
    value = builder()
    save_persistent_cache(namespace, key_parts, value, ttl_seconds)
    return value
