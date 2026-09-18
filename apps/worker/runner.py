from __future__ import annotations

import json
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from modules.core.project_paths import logs_path


@dataclass(frozen=True)
class WorkerStep:
    name: str
    run: Callable[[], Any]
    enabled: bool = True


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_worker_log(run_name: str, payload: dict[str, Any]) -> None:
    log_file = logs_path(f"{run_name}.jsonl")
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def run_worker_steps(run_name: str, steps: list[WorkerStep], *, continue_on_error: bool = True) -> dict[str, Any]:
    started_at = _now_text()
    results: list[dict[str, Any]] = []
    write_worker_log(run_name, {"event": "run_started", "run_name": run_name, "started_at": started_at})

    for step in steps:
        if not step.enabled:
            result = {"name": step.name, "ok": True, "skipped": True, "duration_seconds": 0.0}
            results.append(result)
            write_worker_log(run_name, {"event": "step_skipped", "run_name": run_name, "step": result, "timestamp": _now_text()})
            continue

        step_started = time.perf_counter()
        write_worker_log(run_name, {"event": "step_started", "run_name": run_name, "step_name": step.name, "timestamp": _now_text()})
        try:
            data = step.run()
            result = {
                "name": step.name,
                "ok": True,
                "skipped": False,
                "duration_seconds": round(time.perf_counter() - step_started, 3),
                "data": data,
            }
        except Exception as exc:
            result = {
                "name": step.name,
                "ok": False,
                "skipped": False,
                "duration_seconds": round(time.perf_counter() - step_started, 3),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            results.append(result)
            write_worker_log(run_name, {"event": "step_failed", "run_name": run_name, "step": result, "timestamp": _now_text()})
            if not continue_on_error:
                break
            continue

        results.append(result)
        write_worker_log(run_name, {"event": "step_completed", "run_name": run_name, "step": result, "timestamp": _now_text()})

    summary = {
        "run_name": run_name,
        "started_at": started_at,
        "finished_at": _now_text(),
        "ok": all(item.get("ok") for item in results),
        "step_count": len(results),
        "failed_count": sum(1 for item in results if not item.get("ok")),
        "results": results,
    }
    write_worker_log(run_name, {"event": "run_finished", **summary})
    return summary
