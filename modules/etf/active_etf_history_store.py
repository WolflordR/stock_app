from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "active_etf_history.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_active_etf_history_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS etf_change_snapshots (
                etf_code TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                etf_name TEXT,
                from_date TEXT,
                to_date TEXT,
                updated_at TEXT,
                issuer TEXT,
                holdings_count INTEGER,
                turnover_rate REAL,
                aum_100m REAL,
                beneficiary_10k REAL,
                change_count INTEGER,
                add_count INTEGER,
                increase_count INTEGER,
                decrease_count INTEGER,
                remove_count INTEGER,
                PRIMARY KEY (etf_code, snapshot_date)
            );

            CREATE TABLE IF NOT EXISTS etf_change_items (
                etf_code TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                change_label TEXT,
                stock_code TEXT,
                stock_name TEXT,
                industry TEXT,
                shares_delta REAL,
                shares_delta_lots REAL,
                weight_delta REAL,
                old_weight REAL,
                new_weight REAL,
                holding_amount_100m REAL,
                new_shares REAL,
                new_lots REAL
            );

            CREATE TABLE IF NOT EXISTS etf_change_refresh_state (
                etf_code TEXT NOT NULL PRIMARY KEY,
                target_days INTEGER,
                latest_snapshot_date TEXT,
                available_dates_count INTEGER,
                last_attempt_at TEXT
            );
            """
        )


def persist_etf_change_snapshot(etf_code, etf_name, summary, changes_df, updated_at):
    snapshot_date = str(summary.get("to_date") or summary.get("snapshot_date") or "").strip()
    if not snapshot_date:
        return

    ensure_active_etf_history_db()
    counts = summary.get("change_counts") or {}
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO etf_change_snapshots (
                etf_code, snapshot_date, etf_name, from_date, to_date, updated_at, issuer,
                holdings_count, turnover_rate, aum_100m, beneficiary_10k, change_count,
                add_count, increase_count, decrease_count, remove_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(etf_code, snapshot_date) DO UPDATE SET
                etf_name = excluded.etf_name,
                from_date = excluded.from_date,
                to_date = excluded.to_date,
                updated_at = excluded.updated_at,
                issuer = excluded.issuer,
                holdings_count = excluded.holdings_count,
                turnover_rate = excluded.turnover_rate,
                aum_100m = excluded.aum_100m,
                beneficiary_10k = excluded.beneficiary_10k,
                change_count = excluded.change_count,
                add_count = excluded.add_count,
                increase_count = excluded.increase_count,
                decrease_count = excluded.decrease_count,
                remove_count = excluded.remove_count
            """,
            (
                etf_code,
                snapshot_date,
                etf_name,
                summary.get("from_date"),
                summary.get("to_date"),
                updated_at,
                summary.get("issuer"),
                int(summary.get("holdings_count") or 0),
                summary.get("turnover_rate"),
                summary.get("aum_100m"),
                summary.get("beneficiary_10k"),
                int(summary.get("change_count") or 0),
                int(counts.get("新增") or 0),
                int(counts.get("加碼") or 0),
                int(counts.get("減碼") or 0),
                int(counts.get("刪除") or 0),
            ),
        )
        conn.execute(
            "DELETE FROM etf_change_items WHERE etf_code = ? AND snapshot_date = ?",
            (etf_code, snapshot_date),
        )
        if changes_df is not None and not changes_df.empty:
            rows = []
            for _, row in changes_df.iterrows():
                rows.append(
                    (
                        etf_code,
                        snapshot_date,
                        row.get("change_label"),
                        row.get("code"),
                        row.get("name"),
                        row.get("industry"),
                        row.get("shares_delta"),
                        row.get("shares_delta_lots"),
                        row.get("weight_delta"),
                        row.get("old_weight"),
                        row.get("new_weight"),
                        row.get("holding_amount_100m"),
                        row.get("new_shares"),
                        row.get("new_lots"),
                    )
                )
            conn.executemany(
                """
                INSERT INTO etf_change_items (
                    etf_code, snapshot_date, change_label, stock_code, stock_name, industry,
                    shares_delta, shares_delta_lots, weight_delta, old_weight, new_weight,
                    holding_amount_100m, new_shares, new_lots
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )


def load_etf_change_snapshot_summaries(etf_code):
    ensure_active_etf_history_db()
    with _connect() as conn:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM etf_change_snapshots
            WHERE etf_code = ?
            ORDER BY snapshot_date DESC
            """,
            conn,
            params=(etf_code,),
        )
    return df


def load_etf_change_snapshot_items(etf_code, snapshot_date):
    ensure_active_etf_history_db()
    with _connect() as conn:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM etf_change_items
            WHERE etf_code = ? AND snapshot_date = ?
            """,
            conn,
            params=(etf_code, snapshot_date),
        )
    return df


def load_etf_change_refresh_state(etf_code):
    ensure_active_etf_history_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM etf_change_refresh_state
            WHERE etf_code = ?
            """,
            (etf_code,),
        ).fetchone()
    return dict(row) if row else None


def upsert_etf_change_refresh_state(etf_code, target_days, latest_snapshot_date, available_dates_count, last_attempt_at):
    ensure_active_etf_history_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO etf_change_refresh_state (
                etf_code, target_days, latest_snapshot_date, available_dates_count, last_attempt_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(etf_code) DO UPDATE SET
                target_days = excluded.target_days,
                latest_snapshot_date = excluded.latest_snapshot_date,
                available_dates_count = excluded.available_dates_count,
                last_attempt_at = excluded.last_attempt_at
            """,
            (
                etf_code,
                int(target_days or 0),
                latest_snapshot_date,
                int(available_dates_count or 0),
                last_attempt_at,
            ),
        )
