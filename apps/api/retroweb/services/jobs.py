"""In-process background jobs with progress reporting.

Long operations (fetching cover art for a whole library) run on a thread and
expose counters the UI can poll. One job per kind at a time; finished jobs
are kept for a while so a client can read the final result.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from retroweb.core.clock import utcnow
from retroweb.core.errors import AppError
from retroweb.core.ids import new_id
from retroweb.core.logging import get_logger

log = get_logger(__name__)

MAX_ERRORS = 50
KEEP_FINISHED = 20

JobStatus = str  # "queued" | "running" | "done" | "failed"


class JobRunningError(AppError):
    """A job of this kind is already running."""

    status_code = 409
    code = "job_running"


@dataclass
class Job:
    id: str
    kind: str
    status: JobStatus = "queued"
    total: int = 0
    done: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def finished(self) -> bool:
        return self.status in ("done", "failed")

    def bump(self, key: str) -> None:
        self.counters[key] = self.counters.get(key, 0) + 1

    def error(self, message: str) -> None:
        if len(self.errors) < MAX_ERRORS:
            self.errors.append(message)


class JobRunner:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def start(self, kind: str, target: Callable[[Job], None]) -> Job:
        with self._lock:
            for existing in self._jobs.values():
                if existing.kind == kind and not existing.finished:
                    raise JobRunningError(f"A '{kind}' job is already running")
            job = Job(id=new_id(), kind=kind)
            self._jobs[job.id] = job
            self._prune()
        thread = threading.Thread(
            target=self._run, args=(job, target), name=f"job-{kind}", daemon=True
        )
        thread.start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def _run(self, job: Job, target: Callable[[Job], None]) -> None:
        job.status = "running"
        job.started_at = utcnow()
        log.info("job.started", job_id=job.id, kind=job.kind)
        try:
            target(job)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - the job reports, the process survives
            job.status = "failed"
            job.error(str(exc))
            log.exception("job.failed", job_id=job.id, kind=job.kind)
        finally:
            job.finished_at = utcnow()
        log.info("job.finished", job_id=job.id, kind=job.kind, status=job.status, **job.counters)

    def _prune(self) -> None:
        finished = [job for job in self.list() if job.finished]
        for job in finished[KEEP_FINISHED:]:
            self._jobs.pop(job.id, None)
