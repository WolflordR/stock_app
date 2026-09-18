from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from threading import Lock
from uuid import uuid4

from modules.backtest.backtest_service import run_backtest_scan


class BacktestJobManager:
    def __init__(self, job_store=None):
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="trade-backtest")
        self.lock = Lock()
        self.jobs = {}
        self.job_store = job_store

    def start_job(self, request):
        job_id = uuid4().hex[:8]
        job = {
            "job_id": job_id,
            "job_type": "backtest",
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
        self._persist_job(job)
        self.executor.submit(self._run_job, job_id, request)
        return job_id

    def _update_job(self, job_id, **updates):
        job = None
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(updates)
                job = dict(self.jobs[job_id])
        if job:
            self._persist_job(job)

    def _persist_job(self, job):
        if self.job_store:
            self.job_store.upsert_job(job)

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
            if job:
                if self.job_store:
                    stored_job = self.job_store.get_job(job_id)
                    if stored_job and stored_job.get("status") != job.get("status"):
                        self.jobs[job_id] = stored_job
                        return deepcopy(stored_job)
                return deepcopy(job)
        return self.job_store.get_job(job_id) if self.job_store else None


class BackgroundDataJobManager:
    def __init__(self, job_store=None):
        self.executor = ThreadPoolExecutor(max_workers=6, thread_name_prefix="trade-data")
        self.lock = Lock()
        self.jobs = {}
        self.jobs_by_key = {}
        self.job_store = job_store

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
        self._persist_job(job)
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
                if not self.job_store:
                    return existing_job_id
                stored_job = self.job_store.get_job(existing_job_id)
                if stored_job and stored_job.get("status") in {"queued", "running", "completed"}:
                    return existing_job_id
                if stored_job:
                    self.jobs[existing_job_id] = stored_job
        if self.job_store:
            existing_job_id = self.job_store.find_active_job_id(job_type, cache_key)
            if existing_job_id:
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
        job = None
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(updates)
                job = dict(self.jobs[job_id])
        if job:
            self._persist_job(job)

    def _persist_job(self, job):
        if self.job_store:
            self.job_store.upsert_job(job)

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
            if job:
                if self.job_store:
                    stored_job = self.job_store.get_job(job_id)
                    if stored_job and stored_job.get("status") != job.get("status"):
                        self.jobs[job_id] = stored_job
                        job = stored_job
                job_copy = dict(job)
                if include_result:
                    job_copy["result"] = deepcopy(job.get("result"))
                else:
                    job_copy.pop("result", None)
                return job_copy
        stored_job = self.job_store.get_job(job_id) if self.job_store else None
        if stored_job and not include_result:
            stored_job.pop("result", None)
        return stored_job
