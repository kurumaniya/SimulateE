"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from alembic import command
from retroweb import __version__
from retroweb.api.router import api_router
from retroweb.core.config import Settings, get_settings
from retroweb.core.database import get_session, init_engine
from retroweb.core.errors import AppError
from retroweb.core.logging import configure_logging, get_logger
from retroweb.library.scanner import GameScanner
from retroweb.services.artwork import ArtworkFetcher
from retroweb.services.identify import GameIdentifier
from retroweb.services.jobs import JobRunner
from retroweb.services.users import ensure_default_user
from retroweb.storage import InvalidStorageKeyError, build_storage

log = get_logger(__name__)

ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def run_migrations(settings: Settings) -> None:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_INI.parent / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    command.upgrade(config, "head")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_engine(settings)
        run_migrations(settings)
        app.state.storage = build_storage(settings)
        app.state.scanner = GameScanner(app.state.storage)
        app.state.artwork = ArtworkFetcher(settings)
        app.state.identifier = GameIdentifier(settings)
        app.state.jobs = JobRunner()
        for session in get_session():
            ensure_default_user(session, settings)
        log.info("app.started", app=settings.app_name, version=__version__)
        yield
        app.state.artwork.close()
        app.state.identifier.close()

    app = FastAPI(title=f"{settings.app_name} API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Accept-Ranges", "ETag", "X-Save-Updated-At"],
    )

    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(InvalidStorageKeyError)
    async def _storage_key_error(_request: Request, exc: InvalidStorageKeyError) -> JSONResponse:
        log.warning("storage.invalid_key", error=str(exc))
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_storage_key", "message": "Invalid file reference"}},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": exc.errors(),
                }
            },
        )

    app.include_router(api_router)
    return app


app = create_app()
