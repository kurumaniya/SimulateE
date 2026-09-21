"""Convert ORM/service objects into API schemas."""

from __future__ import annotations

from retroweb.core.config import Settings
from retroweb.library.systems import GameSystem
from retroweb.models import GameSave, PlaySession
from retroweb.schemas.games import GameDetail, GameFileOut, GameSummary
from retroweb.schemas.jobs import JobOut
from retroweb.schemas.saves import SaveOut
from retroweb.schemas.sessions import PlaySessionOut
from retroweb.services.games import GameListItem
from retroweb.services.jobs import Job


def game_summary(item: GameListItem) -> GameSummary:
    game = item.game
    return GameSummary(
        id=game.id,
        title=game.title,
        system=GameSystem(game.system),
        favorite=item.favorite,
        region=game.region,
        has_cover=game.cover_key is not None,
        rom_missing=game.any_file_missing,
        play_time_seconds=item.play_time_seconds,
        last_played_at=item.last_played_at,
        has_auto_state=item.has_auto_state,
        created_at=game.created_at,
    )


def game_detail(item: GameListItem) -> GameDetail:
    game = item.game
    primary = game.primary_file
    summary = game_summary(item)
    return GameDetail(
        **summary.model_dump(),
        title_en=game.title_en,
        title_ja=game.title_ja,
        title_zh=game.title_zh,
        developer=game.developer,
        publisher=game.publisher,
        release_date=game.release_date,
        description=game.description,
        canonical_name=game.canonical_name,
        identified_by=game.identified_by,
        rom_filename=primary.filename if primary else None,
        rom_hash=primary.sha256 if primary else None,
        rom_size=primary.size_bytes if primary else None,
        files=[GameFileOut.model_validate(f) for f in game.files],
        updated_at=game.updated_at,
    )


def save_out(row: GameSave) -> SaveOut:
    return SaveOut(
        id=row.id,
        game_id=row.game_id,
        save_type=row.save_type,
        slot=row.slot,
        size_bytes=row.size_bytes,
        has_screenshot=row.screenshot_key is not None,
        emulator_id=row.emulator_id,
        core_id=row.core_id,
        core_version=row.core_version,
        client_modified_at=row.client_modified_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def job_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        kind=job.kind,
        status=job.status,
        total=job.total,
        done=job.done,
        counters=dict(job.counters),
        errors=list(job.errors),
        created_at=job.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


def session_out(row: PlaySession, settings: Settings) -> PlaySessionOut:
    return PlaySessionOut(
        id=row.id,
        game_id=row.game_id,
        started_at=row.started_at,
        last_heartbeat_at=row.last_heartbeat_at,
        ended_at=row.ended_at,
        duration_seconds=row.duration_seconds,
        device=row.device,
        emulator_id=row.emulator_id,
        heartbeat_interval_seconds=settings.session_heartbeat_interval_seconds,
    )
