from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from modules.core.project_paths import db_path
from modules.data_sources.stock_db import find_security


DB_PATH = db_path("watchlists.db")
DEFAULT_GROUP_NAME = "想多看"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normalize_code(stock_code: str) -> str:
    return str(stock_code or "").strip().upper().split(".")[0].zfill(4)


def init_watchlist_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist_items (
                group_id INTEGER NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT,
                symbol TEXT,
                note TEXT,
                added_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(group_id, stock_code),
                FOREIGN KEY(group_id) REFERENCES watchlist_groups(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_watchlist_items_stock ON watchlist_items(stock_code)"
        )
        existing = conn.execute("SELECT id FROM watchlist_groups WHERE name = ?", (DEFAULT_GROUP_NAME,)).fetchone()
        if existing is None:
            now = _now_text()
            conn.execute(
                """
                INSERT INTO watchlist_groups(name, sort_order, created_at, updated_at)
                VALUES (?, 0, ?, ?)
                """,
                (DEFAULT_GROUP_NAME, now, now),
            )
        conn.commit()


def _resolve_group_id(conn: sqlite3.Connection, group_id: int | None, group_name: str | None = None) -> int:
    if group_id:
        row = conn.execute("SELECT id FROM watchlist_groups WHERE id = ?", (int(group_id),)).fetchone()
        if row:
            return int(row["id"])
    normalized_name = str(group_name or DEFAULT_GROUP_NAME).strip() or DEFAULT_GROUP_NAME
    row = conn.execute("SELECT id FROM watchlist_groups WHERE name = ?", (normalized_name,)).fetchone()
    if row:
        return int(row["id"])
    now = _now_text()
    max_sort = conn.execute("SELECT COALESCE(MAX(sort_order), 0) AS max_sort FROM watchlist_groups").fetchone()
    cursor = conn.execute(
        """
        INSERT INTO watchlist_groups(name, sort_order, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        (normalized_name, int(max_sort["max_sort"] or 0) + 1, now, now),
    )
    return int(cursor.lastrowid)


def create_watchlist_group(name: str) -> dict[str, Any]:
    init_watchlist_db()
    normalized_name = str(name or "").strip()
    if not normalized_name:
        normalized_name = DEFAULT_GROUP_NAME
    with _connect() as conn:
        group_id = _resolve_group_id(conn, None, normalized_name)
        conn.commit()
    return get_watchlists(group_id=group_id)


def add_watchlist_item(stock_code: str, *, group_id: int | None = None, group_name: str | None = None, note: str | None = None) -> dict[str, Any]:
    init_watchlist_db()
    normalized_code = _normalize_code(stock_code)
    security = find_security(normalized_code) or {}
    stock_name = security.get("name_zh") or security.get("full_name_zh") or ""
    symbol = security.get("yfinance_symbol") or normalized_code
    now = _now_text()
    with _connect() as conn:
        target_group_id = _resolve_group_id(conn, group_id, group_name)
        conn.execute(
            """
            INSERT INTO watchlist_items(group_id, stock_code, stock_name, symbol, note, added_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(group_id, stock_code) DO UPDATE SET
                stock_name=excluded.stock_name,
                symbol=excluded.symbol,
                note=COALESCE(excluded.note, watchlist_items.note),
                updated_at=excluded.updated_at
            """,
            (target_group_id, normalized_code, stock_name, symbol, note, now, now),
        )
        conn.execute("UPDATE watchlist_groups SET updated_at = ? WHERE id = ?", (now, target_group_id))
        conn.commit()
    return get_watchlists(group_id=target_group_id)


def remove_watchlist_item(group_id: int, stock_code: str) -> dict[str, Any]:
    init_watchlist_db()
    normalized_code = _normalize_code(stock_code)
    with _connect() as conn:
        conn.execute(
            "DELETE FROM watchlist_items WHERE group_id = ? AND stock_code = ?",
            (int(group_id), normalized_code),
        )
        conn.execute("UPDATE watchlist_groups SET updated_at = ? WHERE id = ?", (_now_text(), int(group_id)))
        conn.commit()
    return get_watchlists(group_id=group_id)


def get_watchlists(*, group_id: int | None = None) -> dict[str, Any]:
    init_watchlist_db()
    with _connect() as conn:
        group_rows = conn.execute(
            """
            SELECT
                g.id,
                g.name,
                g.sort_order,
                g.created_at,
                g.updated_at,
                COUNT(i.stock_code) AS item_count
            FROM watchlist_groups g
            LEFT JOIN watchlist_items i ON i.group_id = g.id
            GROUP BY g.id, g.name, g.sort_order, g.created_at, g.updated_at
            ORDER BY g.sort_order, g.id
            """
        ).fetchall()
        selected_group_id = group_id or (int(group_rows[0]["id"]) if group_rows else None)
        item_rows = conn.execute(
            """
            SELECT group_id, stock_code, stock_name, symbol, note, added_at, updated_at
            FROM watchlist_items
            WHERE group_id = ?
            ORDER BY added_at DESC, stock_code
            """,
            (selected_group_id,),
        ).fetchall() if selected_group_id else []

    return {
        "groups": [dict(row) for row in group_rows],
        "selected_group_id": selected_group_id,
        "items": [dict(row) for row in item_rows],
    }
