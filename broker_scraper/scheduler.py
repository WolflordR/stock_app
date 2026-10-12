"""Run the TWSE broker downloader daily on the NAS at Taiwan local time."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ZONE = ZoneInfo("Asia/Taipei")
LOG_DIR = Path(os.environ.get("TRADE_LOGS_DIR", "/trade/logs")) / "broker_scraper"
STATE_FILE = LOG_DIR / "scheduler.json"
HEARTBEAT_FILE = LOG_DIR / "heartbeat.json"


def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_json(path: Path, payload: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def run_once(now: datetime) -> int:
    day = now.date().isoformat()
    log_file = LOG_DIR / f"scraper_{day}.log"
    command = [sys.executable, "-u", "-m", "broker_scraper.scraper"]
    write_json(STATE_FILE, {"last_attempt": day, "started_at": now.isoformat(), "status": "running", "log": str(log_file)})
    with log_file.open("a", encoding="utf-8") as log:
        print(f"\n===== {now:%Y-%m-%d %H:%M:%S %Z} 開始下載 =====", file=log, flush=True)
        try:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=8 * 3600, check=False)
            code = result.returncode
        except subprocess.TimeoutExpired:
            print("❌ 下載超過 8 小時，已停止。", file=log, flush=True)
            code = 124
        except OSError as exc:
            print(f"❌ 無法啟動下載程式：{exc}", file=log, flush=True)
            code = 1
        finished = datetime.now(ZONE)
        print(f"===== {finished:%Y-%m-%d %H:%M:%S %Z} 結束，狀態 {code} =====", file=log, flush=True)
    write_json(STATE_FILE, {
        "last_attempt": day,
        "started_at": now.isoformat(),
        "finished_at": finished.isoformat(),
        "status": "ok" if code == 0 else "failed",
        "exit_code": code,
        "log": str(log_file),
    })
    print(f"Broker scraper finished for {day}: exit={code}; log={log_file}", flush=True)
    return code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-once", action="store_true", help="立即執行一次，不啟動排程")
    args = parser.parse_args()
    if args.run_once:
        return run_once(datetime.now(ZONE))

    value = os.environ.get("BROKER_DAILY_TIME", "19:00")
    try:
        hour, minute = (int(part) for part in value.split(":"))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AssertionError):
        raise ValueError("BROKER_DAILY_TIME 必須是 HH:MM") from None
    print(f"Broker scraper scheduler ready: daily {hour:02d}:{minute:02d} Asia/Taipei", flush=True)
    while True:
        now = datetime.now(ZONE)
        write_json(HEARTBEAT_FILE, {"at": now.isoformat(), "epoch": time.time()})
        if (now.hour, now.minute) >= (hour, minute) and read_state().get("last_attempt") != now.date().isoformat():
            run_once(now)
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
