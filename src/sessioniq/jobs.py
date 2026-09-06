"""Lightweight in-process background jobs.

Long tasks (voice-memo transcription, batch re-analysis) must not hold an HTTP
request hostage for minutes. Jobs run in daemon threads, report progress, and
can be cancelled between work units. In-process by design: the API is a single
process by contract, and a job's effects (notes, refreshed metadata) commit to
the library as they complete — finished job records are bookkeeping only and
are capped, so memory stays flat.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

logger = logging.getLogger(__name__)

JOB_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}
MAX_FINISHED_JOBS = 50


class JobCancelled(Exception):
    """Raised inside a runner when cancellation was requested."""


def create_job(kind: str, label: str, total: int | None = None) -> dict:
    job = {
        "id": uuid4().hex[:12],
        "kind": kind,
        "label": label,
        "status": "running",
        "progress": {"done": 0, "total": total},
        "cancel_requested": False,
        "result": None,
        "error": None,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "finished_at": None,
    }
    with JOB_LOCK:
        JOBS[job["id"]] = job
        _prune_finished()
    return job


def run_job(
    kind: str,
    label: str,
    runner: Callable[[str], object],
    total: int | None = None,
) -> dict:
    """Create a job and execute ``runner(job_id)`` in a daemon thread."""

    def wrapper(job_id: str) -> None:
        try:
            result = runner(job_id)
        except JobCancelled:
            _transition(job_id, status="cancelled")
        except Exception as exc:  # The job must never take the API down.
            logger.warning("Job %s (%s) failed.", job_id, kind, exc_info=True)
            _transition(job_id, status="error", error=f"{type(exc).__name__}: {exc}")
        else:
            _transition(job_id, status="done", result=result)

    job = create_job(kind, label, total)
    threading.Thread(target=wrapper, args=(job["id"],), daemon=True).start()
    return job


def set_progress(job_id: str, done: int, total: int | None = None) -> None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return
        resolved_total = total if total is not None else job["progress"]["total"]
        job["progress"] = {"done": done, "total": resolved_total}


def check_cancel(job_id: str) -> None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if job is not None and job["cancel_requested"]:
            raise JobCancelled(job_id)


def request_cancel(job_id: str) -> bool:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if job is None or job["status"] != "running":
            return False
        job["cancel_requested"] = True
        return True


def get_job(job_id: str) -> dict | None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def list_jobs() -> list[dict]:
    with JOB_LOCK:
        jobs = sorted(JOBS.values(), key=lambda item: item["started_at"], reverse=True)
        return [dict(job) for job in jobs]


def _transition(job_id: str, **fields) -> None:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return
        job.update(fields)
        job["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        _prune_finished()


def _prune_finished() -> None:
    finished = sorted(
        (job for job in JOBS.values() if job["status"] != "running"),
        key=lambda item: item["started_at"],
    )
    for job in finished[:-MAX_FINISHED_JOBS] if len(finished) > MAX_FINISHED_JOBS else []:
        JOBS.pop(job["id"], None)
