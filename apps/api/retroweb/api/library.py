"""Aggregated views for the home page and platform list."""

from __future__ import annotations

from fastapi import APIRouter

from retroweb.api.deps import DbDep, UserDep
from retroweb.api.serializers import game_summary
from retroweb.library.systems import ADAPTER_SUPPORTED_SYSTEMS, SYSTEMS, GameSystem
from retroweb.schemas.games import HomeResponse, PlatformSummary, SystemOut
from retroweb.services import games as game_service

router = APIRouter(tags=["library"])

HOME_SECTION_LIMIT = 12


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
