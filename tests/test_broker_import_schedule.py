from __future__ import annotations

import fcntl
import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from apps.worker import nas_scheduler
from apps.worker.import_broker_csv_folder import import_broker_csv_folder
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
