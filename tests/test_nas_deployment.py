from __future__ import annotations

import json
import sqlite3
import threading
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from apps.worker import backup_databases, daily_update, nas_scheduler


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
    assert state["attempt_count"] == 1
    assert calls == [[nas_scheduler.sys.executable, "-m", "apps.worker.daily_update", "--skip-electronic-universe"]]
    now = datetime(2026, 10, 12, 18, 46, tzinfo=ZoneInfo("Asia/Taipei"))
    assert not nas_scheduler._is_due(now, hour=18, minute=45, last_attempt=state["last_attempt"])
    assert nas_scheduler._is_due(now, hour=18, minute=45, last_attempt=None)


def test_scheduler_retries_an_interrupted_daily_run_once(tmp_path, monkeypatch):
    state_file = tmp_path / "scheduler.json"
    state_file.write_text(json.dumps({"last_attempt": "2026-10-12", "status": "running", "attempt_count": 1}))
    monkeypatch.setattr(nas_scheduler, "STATE_FILE", state_file)
    monkeypatch.setattr(nas_scheduler.subprocess, "run", lambda args, **kwargs: type("Result", (), {"returncode": 0})())
    now = datetime(2026, 10, 12, 20, 30, tzinfo=ZoneInfo("Asia/Taipei"))
    assert nas_scheduler._daily_is_due(now, nas_scheduler._read_state(), hour=18, minute=45)
    nas_scheduler._run_once(now)
    state = nas_scheduler._read_state()
    assert state["status"] == "ok"
    assert state["attempt_count"] == 2
    assert not nas_scheduler._daily_is_due(now, state, hour=18, minute=45)


def test_daily_prices_and_market_limits_run_before_long_maintenance():
    args = Namespace(
        refresh_stock_master=False, refresh_revenue=False, refresh_company_links=False,
        refresh_market_map=False, skip_electronic_universe=True, skip_sector_metrics=False,
        skip_active_etf=False, skip_chip_trends=False, price_all=False, price_stock=[],
        price_days=180, price_force=False, dry_run=False,
    )
    names = [step.name for step in daily_update.build_daily_steps(args)]
    assert names.index("refresh_official_electronics_prices") < names.index("backup")
    assert names.index("refresh_dashboard_signals") < names.index("backup")
    assert names.index("refresh_market_limits") < names.index("refresh_ownership_research_prices")
    assert names[-1] == "backup"


def test_daily_update_does_not_block_broker_import(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    imported = []
    now = datetime(2026, 10, 12, 21, 0, tzinfo=ZoneInfo("Asia/Taipei"))

    class FixedDatetime:
        @staticmethod
        def now(_zone):
            return now

    class LoopDone(Exception):
        pass

    def slow_daily(_now):
        started.set()
        release.wait(2)

    monkeypatch.setattr(nas_scheduler, "datetime", FixedDatetime)
    monkeypatch.setattr(nas_scheduler.sys, "argv", ["nas_scheduler"])
    monkeypatch.setattr(nas_scheduler, "_write_json", lambda *args: None)
    monkeypatch.setattr(nas_scheduler, "_read_state", lambda: {})
    monkeypatch.setattr(nas_scheduler, "_read_state_file", lambda _path: {"last_evening_attempt": now.date().isoformat()})
    monkeypatch.setattr(nas_scheduler, "_read_broker_state", lambda: {})
    monkeypatch.setattr(nas_scheduler, "_run_once", slow_daily)
    monkeypatch.setattr(nas_scheduler, "_run_broker_import", lambda _now, **kwargs: imported.append(kwargs["slot"]))
    monkeypatch.setattr(nas_scheduler.time, "sleep", lambda _seconds: (_ for _ in ()).throw(LoopDone()))
    try:
        with pytest.raises(LoopDone):
            nas_scheduler.main()
        assert started.wait(1)
        assert imported == ["primary"]
    finally:
        release.set()
