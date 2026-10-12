from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apps.worker import backup_databases, nas_scheduler


def test_backup_includes_uncheckpointed_wal_data(tmp_path, monkeypatch):
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    source = db_dir / "stocks.db"
    writer = sqlite3.connect(source)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE sample(value INTEGER)")
    writer.execute("INSERT INTO sample VALUES (42)")
    writer.commit()

    monkeypatch.setattr(backup_databases, "ALL_DB_FILES", ["stocks.db"])
    monkeypatch.setattr(backup_databases, "db_path", lambda name: db_dir / name)
    monkeypatch.setattr(backup_databases, "backups_path", lambda name: tmp_path / "backups" / name)
    monkeypatch.setattr(backup_databases, "data_path", lambda name: tmp_path / "data" / name)
    result = backup_databases.backup_databases(label="test")
    snapshot = Path(result["backup_dir"]) / "stocks.db"
    with sqlite3.connect(snapshot) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == 42
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    writer.close()


def test_scheduler_records_attempt_and_does_not_repeat(tmp_path, monkeypatch):
    state_file = tmp_path / "scheduler.json"
    monkeypatch.setattr(nas_scheduler, "STATE_FILE", state_file)
    monkeypatch.setattr(nas_scheduler, "HEARTBEAT_FILE", tmp_path / "heartbeat.json")
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(nas_scheduler.subprocess, "run", run)
    nas_scheduler._run_once(datetime(2026, 10, 12, 18, 45, tzinfo=ZoneInfo("Asia/Taipei")))
    state = json.loads(state_file.read_text())
    assert state["last_attempt"] == "2026-10-12"
    assert state["status"] == "ok"
    assert calls == [[nas_scheduler.sys.executable, "-m", "apps.worker.daily_update", "--skip-electronic-universe"]]
    now = datetime(2026, 10, 12, 18, 46, tzinfo=ZoneInfo("Asia/Taipei"))
    assert not nas_scheduler._is_due(now, hour=18, minute=45, last_attempt=state["last_attempt"])
    assert nas_scheduler._is_due(now, hour=18, minute=45, last_attempt=None)
