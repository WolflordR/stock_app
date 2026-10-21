"""Single-process, once-per-trading-day NAS scheduler."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from modules.core.project_paths import LOGS_DIR, RAW_DATA_DIR


ZONE = ZoneInfo("Asia/Taipei")
STATE_FILE = LOGS_DIR / "nas_scheduler.json"
HEARTBEAT_FILE = LOGS_DIR / "nas_scheduler_heartbeat.json"
BROKER_STATE_FILE = LOGS_DIR / "nas_broker_import.json"
BROKER_LOG_DIR = LOGS_DIR / "broker_import"
EVENT_STATE_FILE = LOGS_DIR / "nas_company_events.json"
BROKER_DOWNLOAD_LOCK = RAW_DATA_DIR / "broker" / "twse" / ".download.lock"


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_broker_state() -> dict:
    try:
        return json.loads(BROKER_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _read_state_file(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _run_with_heartbeat(args: list[str], *, timeout: int, log_path: Path | None = None, write_heartbeat: bool = True) -> int:
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.is_set():
            now = datetime.now(ZONE)
            _write_json(HEARTBEAT_FILE, {"epoch": time.time(), "at": now.isoformat()})
            stop.wait(30)

    thread = threading.Thread(target=heartbeat, daemon=True) if write_heartbeat else None
    if thread is not None:
        thread.start()
    try:
        if log_path is None:
            return subprocess.run(args, check=False, timeout=timeout).returncode
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            return subprocess.run(args, check=False, timeout=timeout, stdout=log, stderr=subprocess.STDOUT).returncode
    except subprocess.TimeoutExpired:
        return 124
    finally:
        stop.set()
        if thread is not None:
            thread.join()


def _run_once(now: datetime) -> None:
    today = now.date().isoformat()
    previous = _read_state()
    attempt_count = int(previous.get("attempt_count", 1)) + 1 if previous.get("last_attempt") == today else 1
    _write_json(STATE_FILE, {"last_attempt": today, "attempt_count": attempt_count, "started_at": now.isoformat(), "status": "running"})
    args = [sys.executable, "-m", "apps.worker.daily_update", "--skip-electronic-universe"]
    print(f"NAS daily update started: {today}", flush=True)
    exit_code = _run_with_heartbeat(args, timeout=4 * 3600, write_heartbeat=False)
    status = "ok" if exit_code == 0 else "timeout" if exit_code == 124 else "failed"
    _write_json(STATE_FILE, {
        "last_attempt": today,
        "attempt_count": attempt_count,
        "finished_at": datetime.now(ZONE).isoformat(),
        "status": status,
        "exit_code": exit_code,
        "command": args,
    })
    print(f"NAS daily update finished: {today} {status} exit={exit_code}", flush=True)


def _run_broker_import(now: datetime, *, slot: str = "primary") -> bool:
    """Import downloaded reports after the scraper releases its file lock."""
    BROKER_DOWNLOAD_LOCK.parent.mkdir(parents=True, exist_ok=True)
    with BROKER_DOWNLOAD_LOCK.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        try:
            today = now.date().isoformat()
            previous = _read_broker_state()
            log_path = BROKER_LOG_DIR / f"import_{today}_{slot}.log"
            state = {**previous, "last_attempt": today, "started_at": now.isoformat(), "status": "running", "log": str(log_path)}
            if slot == "late":
                state["last_late_attempt"] = today
            _write_json(BROKER_STATE_FILE, state)
            args = [sys.executable, "-m", "apps.worker.import_broker_csv_folder", "--missing-only", "--progress-every", "100"]
            print(f"NAS broker CSV import started: {today} {slot}", flush=True)
            exit_code = _run_with_heartbeat(args, timeout=4 * 3600, log_path=log_path)
            status = "ok" if exit_code == 0 else "timeout" if exit_code == 124 else "failed"
            _write_json(BROKER_STATE_FILE, {
                **state,
                "finished_at": datetime.now(ZONE).isoformat(),
                "status": status,
                "exit_code": exit_code,
                "command": args,
                "log": str(log_path),
            })
            print(f"NAS broker CSV import finished: {today} {slot} {status} exit={exit_code}", flush=True)
            return True
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _run_event_refresh(now: datetime, slot: str) -> None:
    today = now.date().isoformat()
    previous = _read_state_file(EVENT_STATE_FILE)
    _write_json(EVENT_STATE_FILE, {**previous, f"last_{slot}_attempt": today, "started_at": now.isoformat(), "status": "running"})
    args = [sys.executable, "-m", "apps.worker.refresh_company_events"]
    exit_code = _run_with_heartbeat(args, timeout=180)
    _write_json(EVENT_STATE_FILE, {
        **previous,
        f"last_{slot}_attempt": today,
        "finished_at": datetime.now(ZONE).isoformat(),
        "status": "ok" if exit_code == 0 else "failed",
        "exit_code": exit_code,
    })
    print(f"NAS company events refresh: {today} {slot} exit={exit_code}", flush=True)


def _is_due(now: datetime, *, hour: int, minute: int, last_attempt: str | None) -> bool:
    return (
        now.weekday() < 5
        and (now.hour, now.minute) >= (hour, minute)
        and last_attempt != now.date().isoformat()
    )


def _daily_is_due(now: datetime, state: dict, *, hour: int, minute: int) -> bool:
    if _is_due(now, hour=hour, minute=minute, last_attempt=state.get("last_attempt")):
        return True
    return (
        now.weekday() < 5
        and (now.hour, now.minute) >= (hour, minute)
        and state.get("last_attempt") == now.date().isoformat()
        and state.get("status") == "running"
        and int(state.get("attempt_count", 1)) < 2
    )


def _broker_import_slot(
    now: datetime,
    state: dict,
    *,
    primary_time: tuple[int, int],
    late_time: tuple[int, int],
) -> str | None:
    today = now.date().isoformat()
    if (now.hour, now.minute) >= primary_time and state.get("last_attempt") != today:
        return "primary"
    if state.get("last_attempt") == today and (now.hour, now.minute) >= late_time and state.get("last_late_attempt") != today:
        return "late"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()
    if args.health:
        try:
            heartbeat = json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8"))
            return 0 if time.time() - heartbeat["epoch"] < 180 else 1
        except (OSError, ValueError, KeyError, TypeError):
            return 1

    hour, minute = map(int, os.getenv("TRADE_DAILY_TIME", "18:45").split(":"))
    event_hour, event_minute = map(int, os.getenv("TRADE_EVENTS_TIME", "08:30").split(":"))
    evening_hour, evening_minute = map(int, os.getenv("TRADE_EVENTS_EVENING_TIME", "20:30").split(":"))
    broker_hour, broker_minute = map(int, os.getenv("TRADE_BROKER_IMPORT_TIME", "21:00").split(":"))
    late_hour, late_minute = map(int, os.getenv("TRADE_BROKER_IMPORT_LATE_TIME", "23:15").split(":"))
    if not all(0 <= h <= 23 and 0 <= m <= 59 for h, m in ((hour, minute), (event_hour, event_minute), (evening_hour, evening_minute), (broker_hour, broker_minute), (late_hour, late_minute))):
        raise ValueError("Scheduler times must be HH:MM")
    print(f"NAS scheduler ready; daily data weekdays {hour:02d}:{minute:02d}, company events daily {event_hour:02d}:{event_minute:02d} and {evening_hour:02d}:{evening_minute:02d}, broker import daily {broker_hour:02d}:{broker_minute:02d} and {late_hour:02d}:{late_minute:02d} Asia/Taipei", flush=True)
    daily_thread: threading.Thread | None = None
    while True:
        now = datetime.now(ZONE)
        _write_json(HEARTBEAT_FILE, {"epoch": time.time(), "at": now.isoformat()})
        if (daily_thread is None or not daily_thread.is_alive()) and _daily_is_due(now, _read_state(), hour=hour, minute=minute):
            daily_thread = threading.Thread(target=_run_once, args=(now,), daemon=True)
            daily_thread.start()
        event_state = _read_state_file(EVENT_STATE_FILE)
        if (now.hour, now.minute) >= (evening_hour, evening_minute):
            if event_state.get("last_evening_attempt") != now.date().isoformat():
                _run_event_refresh(now, "evening")
        elif (now.hour, now.minute) >= (event_hour, event_minute) and event_state.get("last_morning_attempt") != now.date().isoformat():
            _run_event_refresh(now, "morning")
        broker_slot = _broker_import_slot(
            now,
            _read_broker_state(),
            primary_time=(broker_hour, broker_minute),
            late_time=(late_hour, late_minute),
        )
        if broker_slot:
            _run_broker_import(now, slot=broker_slot)
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
