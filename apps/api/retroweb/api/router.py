from __future__ import annotations

from fastapi import APIRouter

from retroweb.api import auth, bios, games, health, library, play_sessions, saves, users

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(library.router)
api_router.include_router(games.router)
api_router.include_router(saves.router)
api_router.include_router(play_sessions.router)
api_router.include_router(bios.router)
