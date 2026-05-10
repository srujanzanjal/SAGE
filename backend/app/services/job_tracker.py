from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Optional
from uuid import uuid4


@dataclass
class IngestionJob:
    job_id: str
    operation: str
    source_type: str
    status: str = "queued"
    current_step: str = "Queued"
    progress_percentage: int = 0
    message: str = "Queued"
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_JOBS: dict[str, IngestionJob] = {}
_LOCK = Lock()


def create_job(*, operation: str, source_type: str, message: str = "Queued") -> IngestionJob:
    job = IngestionJob(
        job_id=str(uuid4()),
        operation=operation,
        source_type=source_type,
        message=message,
    )
    with _LOCK:
        _JOBS[job.job_id] = job
    return job


def update_job(
    job_id: str,
    *,
    status: Optional[str] = None,
    current_step: Optional[str] = None,
    progress_percentage: Optional[int] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    result: Optional[dict[str, Any]] = None,
) -> IngestionJob:
    with _LOCK:
        job = _JOBS[job_id]
        if status is not None:
            job.status = status
        if current_step is not None:
            job.current_step = current_step
        if progress_percentage is not None:
            job.progress_percentage = max(0, min(100, int(progress_percentage)))
        if message is not None:
            job.message = message
        if error is not None:
            job.error = error
        if result is not None:
            job.result = result
        job.updated_at = datetime.now(timezone.utc).isoformat()
        return job


def get_job(job_id: str) -> Optional[IngestionJob]:
    with _LOCK:
        return _JOBS.get(job_id)


def job_to_dict(job: IngestionJob) -> dict[str, Any]:
    return asdict(job)


def require_job(job_id: str) -> IngestionJob:
    job = get_job(job_id)
    if not job:
        raise KeyError(job_id)
    return job
