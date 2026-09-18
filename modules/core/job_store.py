from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from typing import Any

from modules.core.project_paths import db_path


class SQLiteJobStore:
    def __init__(self, filename: str = "api_jobs.db", *, stale_after_seconds: int = 1800):
        self.path = db_path(filename)
        self.stale_after_seconds = int(stale_after_seconds)
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_jobs (
                    job_id TEXT PRIMARY KEY,
                    job_type TEXT NOT NULL,
                    cache_key TEXT,
                    status TEXT NOT NULL,
                    progress REAL NOT NULL DEFAULT 0,
                    message TEXT,
                    params_json TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_jobs_type_cache
                ON api_jobs(job_type, cache_key, created_at DESC)
                """
            )

    def upsert_job(self, job: dict[str, Any]):
        now = datetime.now().isoformat(timespec="seconds")
        created_at = job.get("created_at") or now
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO api_jobs (
                    job_id, job_type, cache_key, status, progress, message,
                    params_json, result_json, error, created_at, updated_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    job_type=excluded.job_type,
                    cache_key=excluded.cache_key,
                    status=excluded.status,
                    progress=excluded.progress,
                    message=excluded.message,
                    params_json=excluded.params_json,
                    result_json=excluded.result_json,
                    error=excluded.error,
                    updated_at=excluded.updated_at,
                    finished_at=excluded.finished_at
                """,
                (
                    job["job_id"],
                    str(job.get("job_type") or "backtest"),
                    _to_json_text(job.get("cache_key")),
                    str(job.get("status") or "queued"),
                    float(job.get("progress") or 0),
                    job.get("message"),
                    _to_json_text(job.get("params")),
                    _to_json_text(job.get("result")),
                    job.get("error"),
                    created_at,
                    now,
                    job.get("finished_at"),
                ),
            )

    def find_active_job_id(self, job_type: str, cache_key: Any) -> str | None:
        encoded_key = _to_json_text(cache_key)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT job_id
                FROM api_jobs
                WHERE job_type = ?
                  AND cache_key = ?
                  AND status IN ('queued', 'running', 'completed')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (job_type, encoded_key),
            ).fetchone()
        if not row:
            return None
        job = self.get_job(row["job_id"])
        if job and job.get("status") in {"queued", "running", "completed"}:
            return row["job_id"]
        return None

    def find_latest_job_id(self, job_type: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT job_id
                FROM api_jobs
                WHERE job_type = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (job_type,),
            ).fetchone()
        return row["job_id"] if row else None

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM api_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()
        if not row:
            return None

        job = {
            "job_id": row["job_id"],
            "job_type": row["job_type"],
            "cache_key": _from_json_text(row["cache_key"]),
            "status": row["status"],
            "progress": row["progress"],
            "message": row["message"],
            "params": _from_json_text(row["params_json"]),
            "result": _from_json_text(row["result_json"]),
            "error": row["error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "finished_at": row["finished_at"],
        }
        if self._is_stale(job):
            job.update(
                status="failed",
                progress=1.0,
                message="背景任務逾時",
                error="Job exceeded the configured stale timeout.",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
            self.upsert_job(job)
        return job

    def _is_stale(self, job: dict[str, Any]) -> bool:
        if job.get("status") not in {"queued", "running"}:
            return False
        updated_at = _parse_datetime(job.get("updated_at") or job.get("created_at"))
        if not updated_at:
            return False
        return datetime.now() - updated_at > timedelta(seconds=self.stale_after_seconds)


def _to_json_text(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True)


def _from_json_text(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict("records"))
        except TypeError:
            return _json_safe(value.to_dict())
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
