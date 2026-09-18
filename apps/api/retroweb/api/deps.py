"""FastAPI dependencies: settings, db session, storage, current user."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from retroweb.core.config import Settings, get_settings
from retroweb.core.database import get_session
from retroweb.library.scanner import GameScanner
from retroweb.models import User
from retroweb.services.artwork import ArtworkFetcher
from retroweb.services.jobs import JobRunner
from retroweb.services.users import current_user
from retroweb.storage import StorageProvider


def settings_dep() -> Settings:
    return get_settings()


def db_dep() -> Iterator[Session]:
    yield from get_session()


def storage_dep(request: Request) -> StorageProvider:
    storage: StorageProvider = request.app.state.storage
    return storage


def scanner_dep(request: Request) -> GameScanner:
    scanner: GameScanner = request.app.state.scanner
    return scanner


def artwork_dep(request: Request) -> ArtworkFetcher:
    fetcher: ArtworkFetcher = request.app.state.artwork
    return fetcher


def jobs_dep(request: Request) -> JobRunner:
    runner: JobRunner = request.app.state.jobs
    return runner


def user_dep(
    db: Annotated[Session, Depends(db_dep)],
    settings: Annotated[Settings, Depends(settings_dep)],
) -> User:
    return current_user(db, settings)


SettingsDep = Annotated[Settings, Depends(settings_dep)]
DbDep = Annotated[Session, Depends(db_dep)]
StorageDep = Annotated[StorageProvider, Depends(storage_dep)]
ScannerDep = Annotated[GameScanner, Depends(scanner_dep)]
ArtworkDep = Annotated[ArtworkFetcher, Depends(artwork_dep)]
JobsDep = Annotated[JobRunner, Depends(jobs_dep)]
UserDep = Annotated[User, Depends(user_dep)]
