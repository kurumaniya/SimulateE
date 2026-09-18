"""Library scan as a background job (the synchronous endpoint remains for tools)."""

from __future__ import annotations

from retroweb.core.database import get_session
from retroweb.library.scanner import GameScanner
from retroweb.services.jobs import Job

LIBRARY_SCAN_JOB = "library.scan"


def scan_library_job(job: Job, scanner: GameScanner) -> None:
    def progress(done: int, total: int) -> None:
        job.done = done
        job.total = total

    for db in get_session():
        result = scanner.scan_directory(db, progress=progress)
        job.counters.update(
            added=result.added,
            updated=result.updated,
            missing=result.missing,
            skipped=result.skipped,
        )
        for error in result.errors:
            job.error(error)
