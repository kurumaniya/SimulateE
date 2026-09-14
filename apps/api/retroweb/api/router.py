from __future__ import annotations

from fastapi import APIRouter

from retroweb.api import games, health, library, play_sessions, saves

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(library.router)
api_router.include_router(games.router)
api_router.include_router(saves.router)
api_router.include_router(play_sessions.router)
