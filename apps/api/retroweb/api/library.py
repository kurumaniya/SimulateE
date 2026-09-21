"""Aggregated views for the home page and platform list."""

from __future__ import annotations

from fastapi import APIRouter

from retroweb.api.deps import (
    AdminDep,
    ArtworkDep,
    DbDep,
    IdentifierDep,
    JobsDep,
    ScannerDep,
    StorageDep,
    UserDep,
)
from retroweb.api.serializers import game_summary, job_out
from retroweb.core.errors import FeatureDisabledError, NotFoundError
from retroweb.library.systems import ADAPTER_SUPPORTED_SYSTEMS, SYSTEMS, GameSystem
from retroweb.schemas.games import HomeResponse, PlatformSummary, SystemOut
from retroweb.schemas.jobs import JobOut
from retroweb.services import artwork as artwork_service
from retroweb.services import games as game_service
from retroweb.services import identify as identify_service
from retroweb.services import scan as scan_service

router = APIRouter(tags=["library"])

HOME_SECTION_LIMIT = 12


@router.post("/library/scan", response_model=JobOut, status_code=202)
def scan_library_async(scanner: ScannerDep, jobs: JobsDep, _admin: AdminDep) -> JobOut:
    """Scan the ROM directory in the background; poll the job for progress and counts."""
    job = jobs.start(
        scan_service.LIBRARY_SCAN_JOB, lambda job: scan_service.scan_library_job(job, scanner)
    )
    return job_out(job)


@router.post("/library/covers/fetch", response_model=JobOut, status_code=202)
def fetch_missing_covers(
    storage: StorageDep,
    artwork: ArtworkDep,
    identifier: IdentifierDep,
    jobs: JobsDep,
    _admin: AdminDep,
) -> JobOut:
    """Start a background job that fetches a cover for every game without one."""
    if not artwork.enabled:
        raise FeatureDisabledError("Online cover art is disabled (ONLINE_METADATA=false)")
    job = jobs.start(
        artwork_service.COVER_FETCH_JOB,
        lambda job: artwork_service.fetch_missing_covers(job, storage, artwork, identifier),
    )
    return job_out(job)


@router.post("/library/identify", response_model=JobOut, status_code=202)
def identify_library(
    storage: StorageDep,
    identifier: IdentifierDep,
    jobs: JobsDep,
    _admin: AdminDep,
    force: bool = False,
) -> JobOut:
    """Match every unidentified game against the No-Intro / Redump lists in the background.

    ``force`` looks every game up again, including the ones already identified.
    """
    if not identifier.enabled:
        raise FeatureDisabledError("Game identification is disabled (ONLINE_METADATA=false)")
    job = jobs.start(
        identify_service.IDENTIFY_JOB,
        lambda job: identify_service.identify_library(job, storage, identifier, force=force),
    )
    return job_out(job)


@router.get("/library/jobs", response_model=list[JobOut])
def list_jobs(jobs: JobsDep, _user: UserDep) -> list[JobOut]:
    return [job_out(job) for job in jobs.list()]


@router.get("/library/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, jobs: JobsDep, _user: UserDep) -> JobOut:
    job = jobs.get(job_id)
    if job is None:
        raise NotFoundError("Job not found")
    return job_out(job)


@router.get("/library/home", response_model=HomeResponse)
def home(db: DbDep, user: UserDep) -> HomeResponse:
    continue_playing, _ = game_service.list_games(
        db, user, sort="recently_played", limit=HOME_SECTION_LIMIT, only_with_auto_state=True
    )
    recently_played, _ = game_service.list_games(
        db, user, sort="recently_played", limit=HOME_SECTION_LIMIT, only_played=True
    )
    recently_added, _ = game_service.list_games(
        db, user, sort="recently_added", limit=HOME_SECTION_LIMIT
    )
    favorites, _ = game_service.list_games(
        db, user, favorite=True, sort="recently_played", limit=HOME_SECTION_LIMIT
    )
    counts = game_service.platform_counts(db)
    platforms = [
        PlatformSummary(
            system=info.id,
            name=info.name,
            short_name=info.short_name,
            count=counts.get(info.id.value, 0),
            supported=info.id in ADAPTER_SUPPORTED_SYSTEMS,
        )
        for info in SYSTEMS.values()
        if counts.get(info.id.value, 0) > 0
    ]
    return HomeResponse(
        continue_playing=[game_summary(i) for i in continue_playing],
        recently_played=[game_summary(i) for i in recently_played],
        recently_added=[game_summary(i) for i in recently_added],
        favorites=[game_summary(i) for i in favorites],
        platforms=platforms,
    )


@router.get("/systems", response_model=list[SystemOut])
def systems() -> list[SystemOut]:
    return [
        SystemOut(
            id=info.id,
            name=info.name,
            short_name=info.short_name,
            manufacturer=info.manufacturer,
            extensions=list(info.extensions),
            supported=info.id in ADAPTER_SUPPORTED_SYSTEMS,
        )
        for info in SYSTEMS.values()
    ]


@router.get("/systems/{system}", response_model=SystemOut)
def system_detail(system: GameSystem) -> SystemOut:
    info = SYSTEMS[system]
    return SystemOut(
        id=info.id,
        name=info.name,
        short_name=info.short_name,
        manufacturer=info.manufacturer,
        extensions=list(info.extensions),
        supported=info.id in ADAPTER_SUPPORTED_SYSTEMS,
    )
