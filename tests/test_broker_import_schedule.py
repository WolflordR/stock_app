from __future__ import annotations

import fcntl
import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from apps.worker import nas_scheduler
from apps.worker import import_broker_csv_folder as broker_import_worker
from apps.worker.import_broker_csv_folder import import_broker_csv_folder
from broker_scraper import scheduler as broker_download_scheduler
from modules.data_sources import official_broker_import


def test_missing_only_imports_new_broker_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(official_broker_import, "DB_PATH", tmp_path / "broker.db")
    folder = tmp_path / "raw" / "2026-10-08"
    folder.mkdir(parents=True)
    (folder / "2330_bsr.csv").write_text(
        "股票代號,券商名稱,價格,買進股數,賣出股數\n"
        "2330,台灣證券,100,2000,1000\n",
        encoding="utf-8",
    )

    first = import_broker_csv_folder(root=tmp_path / "raw", missing_only=True)
    second = import_broker_csv_folder(root=tmp_path / "raw", missing_only=True)
    assert (first["imported_count"], second["imported_count"], second["skipped_count"]) == (1, 0, 1)

    (folder / "2317_bsr.csv").write_text(
        "股票代號,券商名稱,價格,買進股數,賣出股數\n"
        "2317,台灣證券,50,1000,500\n",
        encoding="utf-8",
    )
    third = import_broker_csv_folder(root=tmp_path / "raw", missing_only=True)
    assert third["imported_count"] == 1
    with sqlite3.connect(tmp_path / "broker.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM broker_trade_reports").fetchone()[0] == 2


def test_broker_import_waits_until_downloader_releases_lock(tmp_path, monkeypatch):
    lock_path = tmp_path / "raw" / ".download.lock"
    lock_path.parent.mkdir()
    monkeypatch.setattr(nas_scheduler, "BROKER_DOWNLOAD_LOCK", lock_path)
    monkeypatch.setattr(nas_scheduler, "BROKER_STATE_FILE", tmp_path / "broker_state.json")
    commands = []
    monkeypatch.setattr(nas_scheduler, "_run_with_heartbeat", lambda args, **kwargs: commands.append(args) or 0)
    now = datetime(2026, 10, 10, 21, 0, tzinfo=ZoneInfo("Asia/Taipei"))

    with lock_path.open("a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not nas_scheduler._run_broker_import(now)
        assert not commands
        fcntl.flock(lock_file, fcntl.LOCK_UN)

    assert nas_scheduler._run_broker_import(now)
    state = json.loads((tmp_path / "broker_state.json").read_text())
    assert state["status"] == "ok"
    assert state["last_attempt"] == "2026-10-10"
    assert "--missing-only" in commands[0]


def test_broker_import_log_is_readable_without_docker_access(tmp_path, monkeypatch):
    monkeypatch.setattr(nas_scheduler, "HEARTBEAT_FILE", tmp_path / "heartbeat.json")
    log_path = tmp_path / "logs" / "broker_import" / "import_2026-10-13.log"
    code = nas_scheduler._run_with_heartbeat(
        [sys.executable, "-c", "import sys; print('import summary'); print('failed csv', file=sys.stderr)"],
        timeout=10,
        log_path=log_path,
    )
    assert code == 0
    assert "import summary" in log_path.read_text(encoding="utf-8")
    assert "failed csv" in log_path.read_text(encoding="utf-8")


def test_broker_import_retries_a_temporary_sqlite_lock(tmp_path, monkeypatch):
    folder = tmp_path / "raw" / "2026-10-13"
    folder.mkdir(parents=True)
    (folder / "2330_bsr.csv").write_text("valid fixture", encoding="utf-8")
    calls = 0

    def import_report(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("database is locked")
        return {"stock_code": kwargs["stock_code"]}

    monkeypatch.setattr(broker_import_worker, "import_official_broker_csv", import_report)
    monkeypatch.setattr(broker_import_worker.time, "sleep", lambda _seconds: None)
    result = import_broker_csv_folder(root=tmp_path / "raw")
    assert calls == 2
    assert result["imported_count"] == 1
    assert result["failed_count"] == 0


def test_late_import_follows_download_retry(tmp_path, monkeypatch):
    now = datetime(2026, 10, 13, 23, 15, tzinfo=ZoneInfo("Asia/Taipei"))
    state = {"last_attempt": "2026-10-13", "status": "ok"}
    assert nas_scheduler._broker_import_slot(now, state, primary_time=(21, 0), late_time=(23, 15)) == "late"
    monkeypatch.setattr(nas_scheduler, "BROKER_DOWNLOAD_LOCK", tmp_path / ".download.lock")
    monkeypatch.setattr(nas_scheduler, "BROKER_STATE_FILE", tmp_path / "broker_state.json")
    monkeypatch.setattr(nas_scheduler, "BROKER_LOG_DIR", tmp_path / "broker_import")
    (tmp_path / "broker_state.json").write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(nas_scheduler, "_run_with_heartbeat", lambda args, **kwargs: 0)
    assert nas_scheduler._run_broker_import(now, slot="late")
    updated = json.loads((tmp_path / "broker_state.json").read_text(encoding="utf-8"))
    assert updated["last_late_attempt"] == "2026-10-13"
    assert nas_scheduler._broker_import_slot(now, updated, primary_time=(21, 0), late_time=(23, 15)) is None


def test_failed_download_gets_one_evening_retry():
    zone = ZoneInfo("Asia/Taipei")
    state = {"last_attempt": "2026-10-13", "status": "failed", "attempt_count": 1}
    due = lambda hour, minute, current: broker_download_scheduler._is_due(
        datetime(2026, 10, 13, hour, minute, tzinfo=zone),
        current,
        daily_time=(19, 0),
        retry_time=(22, 0),
    )
    assert not due(21, 59, state)
    assert due(22, 0, state)
    assert not due(22, 30, {**state, "attempt_count": 2})
    assert not due(22, 30, {**state, "status": "ok"})


def test_legacy_failed_download_state_only_retries_once(tmp_path, monkeypatch):
    state_path = tmp_path / "scheduler.json"
    state_path.write_text(json.dumps({"last_attempt": "2026-10-13", "status": "failed"}), encoding="utf-8")
    monkeypatch.setattr(broker_download_scheduler, "STATE_FILE", state_path)
    monkeypatch.setattr(broker_download_scheduler, "LOG_DIR", tmp_path)
    monkeypatch.setattr(
        broker_download_scheduler.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1),
    )
    now = datetime(2026, 10, 13, 22, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    assert broker_download_scheduler.run_once(now) == 1
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["attempt_count"] == 2
    assert not broker_download_scheduler._is_due(now, state, daily_time=(19, 0), retry_time=(22, 0))
