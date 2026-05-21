from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import inspect
from threading import Lock
from uuid import uuid4

import streamlit as st

from app_constants import HOMEPAGE_RANGE_SCAN_DELAY_SEC
from backtest_service import run_backtest_scan, run_homepage_range_scan


class BacktestJobManager:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="trade-backtest")
        self.lock = Lock()
        self.jobs = {}

    def start_job(self, request):
        job_id = uuid4().hex[:8]
        job = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0.0,
            "message": "排隊中",
            "params": request,
            "result": None,
            "error": None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        }
        with self.lock:
            self.jobs[job_id] = job
        self.executor.submit(self._run_job, job_id, request)
        return job_id

    def _update_job(self, job_id, **updates):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(updates)

    def _run_job(self, job_id, request):
        self._update_job(job_id, status="running", message="正在準備回測")

        def progress_callback(progress, stock_code=None):
            message = f"正在處理 {stock_code}" if stock_code else "背景回測中"
            self._update_job(job_id, progress=float(progress), message=message)

        def status_callback(message):
            self._update_job(job_id, message=message)

        try:
            results = run_backtest_scan(
                request,
                progress_callback=progress_callback,
                status_callback=status_callback,
            )
            self._update_job(
                job_id,
                status="completed",
                progress=1.0,
                message="回測完成",
                result=results,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        except Exception as exc:
            self._update_job(
                job_id,
                status="failed",
                message="回測失敗",
                error=str(exc),
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )

    def get_job(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return deepcopy(job) if job else None


class HomepageRangeScanJobManager:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="trade-home-range")
        self.lock = Lock()
        self.jobs = {}
        self.jobs_by_key = {}

    def start_job(self, cache_key, request, label="首頁盤整吸籌掃描"):
        job_id = uuid4().hex[:8]
        job = {
            "job_id": job_id,
            "job_type": "homepage_range_scan",
            "cache_key": cache_key,
            "label": label,
            "status": "queued",
            "progress": 0.0,
            "message": "排隊中",
            "params": request,
            "result": None,
            "error": None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
            "scanned_at": None,
        }
        with self.lock:
            self.jobs[job_id] = job
            self.jobs_by_key[cache_key] = job_id
        self.executor.submit(self._run_job, job_id, request, label)
        return job_id

    def _update_job(self, job_id, **updates):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(updates)

    def _run_job(self, job_id, request, label):
        self._update_job(job_id, status="running", message=f"正在準備{label}")

        def progress_callback(progress, stock_code=None):
            message = f"{label}中：{stock_code}" if stock_code else f"{label}中"
            self._update_job(job_id, progress=float(progress), message=message)

        def status_callback(message):
            self._update_job(job_id, message=message)

        try:
            results = run_homepage_range_scan(
                request,
                request_delay_sec=HOMEPAGE_RANGE_SCAN_DELAY_SEC,
                progress_callback=progress_callback,
                status_callback=status_callback,
            )
            self._update_job(
                job_id,
                status="completed",
                progress=1.0,
                message=(
                    f"{label}完成，共找到 {len(results)} 檔。"
                    f" 觀察日：{request.trade_date.strftime('%Y-%m-%d') if getattr(request, 'trade_date', None) else '最新資料'}"
                ),
                result=results,
                scanned_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        except Exception as exc:
            self._update_job(
                job_id,
                status="failed",
                message=f"{label}失敗",
                error=str(exc),
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )

    def get_or_create_job(self, cache_key, request, label="首頁盤整吸籌掃描"):
        with self.lock:
            existing_job_id = self.jobs_by_key.get(cache_key)
            existing_job = self.jobs.get(existing_job_id) if existing_job_id else None
            if existing_job and existing_job.get("status") in {"queued", "running", "completed"}:
                return existing_job_id
        return self.start_job(cache_key, request, label=label)

    def get_job(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return deepcopy(job) if job else None


class BackgroundDataJobManager:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="trade-data")
        self.lock = Lock()
        self.jobs = {}
        self.jobs_by_key = {}

    def _resolve_message(self, message, *, result=None, error=None):
        if callable(message):
            try:
                return message(result=result, error=error)
            except Exception:
                return None
        return message

    def start_job(
        self,
        job_type,
        cache_key,
        target,
        *,
        args=None,
        kwargs=None,
        pending_message="排隊中",
        running_message="背景整理中",
        completed_message="背景整理完成",
        failed_message="背景整理失敗",
    ):
        args = tuple(args or ())
        kwargs = dict(kwargs or {})
        job_id = uuid4().hex[:8]
        job = {
            "job_id": job_id,
            "job_type": job_type,
            "cache_key": cache_key,
            "status": "queued",
            "progress": 0.0,
            "message": pending_message,
            "result": None,
            "error": None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": None,
        }
        with self.lock:
            self.jobs[job_id] = job
            self.jobs_by_key[(job_type, cache_key)] = job_id
        self.executor.submit(
            self._run_job,
            job_id,
            target,
            args,
            kwargs,
            running_message,
            completed_message,
            failed_message,
        )
        return job_id

    def get_or_create_job(
        self,
        job_type,
        cache_key,
        target,
        *,
        args=None,
        kwargs=None,
        pending_message="排隊中",
        running_message="背景整理中",
        completed_message="背景整理完成",
        failed_message="背景整理失敗",
    ):
        with self.lock:
            existing_job_id = self.jobs_by_key.get((job_type, cache_key))
            existing_job = self.jobs.get(existing_job_id) if existing_job_id else None
            if existing_job and existing_job.get("status") in {"queued", "running", "completed"}:
                return existing_job_id
        return self.start_job(
            job_type,
            cache_key,
            target,
            args=args,
            kwargs=kwargs,
            pending_message=pending_message,
            running_message=running_message,
            completed_message=completed_message,
            failed_message=failed_message,
        )

    def _update_job(self, job_id, **updates):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(updates)

    def _run_job(self, job_id, target, args, kwargs, running_message, completed_message, failed_message):
        self._update_job(job_id, status="running", progress=0.15, message=running_message)
        try:
            call_kwargs = dict(kwargs)
            target_signature = inspect.signature(target)

            def progress_callback(progress, message=None):
                updates = {"progress": float(progress)}
                if message:
                    updates["message"] = str(message)
                self._update_job(job_id, **updates)

            def status_callback(message):
                self._update_job(job_id, message=str(message))

            if "progress_callback" in target_signature.parameters and "progress_callback" not in call_kwargs:
                call_kwargs["progress_callback"] = progress_callback
            if "status_callback" in target_signature.parameters and "status_callback" not in call_kwargs:
                call_kwargs["status_callback"] = status_callback

            result = target(*args, **call_kwargs)
            self._update_job(
                job_id,
                status="completed",
                progress=1.0,
                message=self._resolve_message(completed_message, result=result) or "背景整理完成",
                result=result,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        except Exception as exc:
            self._update_job(
                job_id,
                status="failed",
                progress=1.0,
                message=self._resolve_message(failed_message, error=exc) or "背景整理失敗",
                error=str(exc),
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )

    def get_job(self, job_id, include_result=True):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return None
            job_copy = dict(job)
            if include_result:
                job_copy["result"] = deepcopy(job.get("result"))
            else:
                job_copy.pop("result", None)
            return job_copy


@st.cache_resource
def get_backtest_job_manager():
    return BacktestJobManager()


@st.cache_resource
def get_homepage_range_scan_job_manager():
    return HomepageRangeScanJobManager()


@st.cache_resource
def get_background_data_job_manager():
    return BackgroundDataJobManager()


def ensure_background_data_job(
    session_key,
    job_type,
    cache_key,
    target,
    *,
    args=None,
    kwargs=None,
    pending_message="排隊中",
    running_message="背景整理中",
    completed_message="背景整理完成",
    failed_message="背景整理失敗",
    autostart=True,
    force_start=False,
):
    manager = get_background_data_job_manager()
    active_job_id = st.session_state.get(session_key)
    active_job = manager.get_job(active_job_id, include_result=False) if active_job_id else None

    if (
        active_job
        and active_job.get("cache_key") == cache_key
        and active_job.get("status") in {"queued", "running", "completed"}
    ):
        return active_job_id, active_job

    if not autostart and not force_start:
        return None, None

    if (
        not active_job
        or active_job.get("cache_key") != cache_key
        or active_job.get("status") == "failed"
        or force_start
    ):
        active_job_id = manager.get_or_create_job(
            job_type,
            cache_key,
            target,
            args=args,
            kwargs=kwargs,
            pending_message=pending_message,
            running_message=running_message,
            completed_message=completed_message,
            failed_message=failed_message,
        )
        st.session_state[session_key] = active_job_id
        active_job = manager.get_job(active_job_id, include_result=False)

    return active_job_id, active_job
