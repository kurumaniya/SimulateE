"""Game library queries and mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from retroweb.core.errors import NotFoundError
from retroweb.core.logging import get_logger
from retroweb.library.systems import GameSystem
from retroweb.models import AUTO_STATE_SLOT, Game, GameFile, GameSave, PlaySession, SaveType, User

log = get_logger(__name__)

SortKey = Literal["title", "recently_played", "recently_added", "play_time"]


@dataclass
class GameListItem:
    game: Game
    play_time_seconds: int
    last_played_at: datetime | None
    has_auto_state: bool


def get_game(db: Session, game_id: str) -> Game:
    game = db.scalar(select(Game).options(selectinload(Game.files)).where(Game.id == game_id))
    if game is None:
        raise NotFoundError("Game not found")
    return game


def _stats_subquery(user: User):  # type: ignore[no-untyped-def]
    return (
        select(
            PlaySession.game_id.label("game_id"),
            func.coalesce(func.sum(PlaySession.duration_seconds), 0).label("play_time"),
            func.max(PlaySession.started_at).label("last_played"),
        )
        .where(PlaySession.user_id == user.id)
        .group_by(PlaySession.game_id)
        .subquery()
    )


def _auto_state_subquery(user: User):  # type: ignore[no-untyped-def]
    return (
        select(GameSave.game_id.label("game_id"))
        .where(
            GameSave.user_id == user.id,
            GameSave.save_type == SaveType.STATE.value,
            GameSave.slot == AUTO_STATE_SLOT,
        )
        .subquery()
    )


def list_games(
    db: Session,
    user: User,
    *,
    query: str | None = None,
    system: GameSystem | None = None,
    favorite: bool | None = None,
    sort: SortKey = "title",
    limit: int = 100,
    offset: int = 0,
    only_played: bool = False,
    only_with_auto_state: bool = False,
) -> tuple[list[GameListItem], int]:
    stats = _stats_subquery(user)
    auto = _auto_state_subquery(user)
    stmt = (
        select(Game, stats.c.play_time, stats.c.last_played, auto.c.game_id)
        .options(selectinload(Game.files))
        .outerjoin(stats, stats.c.game_id == Game.id)
        .outerjoin(auto, auto.c.game_id == Game.id)
    )
    if query:
        needle = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                Game.title.ilike(needle),
                Game.title_en.ilike(needle),
                Game.title_ja.ilike(needle),
                Game.title_zh.ilike(needle),
            )
        )
    if system is not None:
        stmt = stmt.where(Game.system == system.value)
    if favorite is not None:
        stmt = stmt.where(Game.favorite.is_(favorite))
    if only_played:
        stmt = stmt.where(stats.c.last_played.is_not(None))
    if only_with_auto_state:
        stmt = stmt.where(auto.c.game_id.is_not(None))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = int(db.scalar(count_stmt) or 0)

    if sort == "recently_played":
        stmt = stmt.order_by(stats.c.last_played.desc().nulls_last(), Game.title.asc())
    elif sort == "recently_added":
        stmt = stmt.order_by(Game.created_at.desc(), Game.title.asc())
    elif sort == "play_time":
        stmt = stmt.order_by(stats.c.play_time.desc().nulls_last(), Game.title.asc())
    else:
        stmt = stmt.order_by(Game.title.asc())
    stmt = stmt.limit(limit).offset(offset)

    items = [
        GameListItem(
            game=game,
            play_time_seconds=int(play_time or 0),
            last_played_at=last_played,
            has_auto_state=auto_id is not None,
        )
        for game, play_time, last_played, auto_id in db.execute(stmt).all()
    ]
    return items, total


def get_game_item(db: Session, user: User, game_id: str) -> GameListItem:
    game = get_game(db, game_id)
    stats = db.execute(
        select(
            func.coalesce(func.sum(PlaySession.duration_seconds), 0),
            func.max(PlaySession.started_at),
        ).where(PlaySession.user_id == user.id, PlaySession.game_id == game_id)
    ).one()
    has_auto = (
        db.scalar(
            select(GameSave.id).where(
                GameSave.user_id == user.id,
                GameSave.game_id == game_id,
                GameSave.save_type == SaveType.STATE.value,
                GameSave.slot == AUTO_STATE_SLOT,
            )
        )
        is not None
    )
    return GameListItem(
        game=game,
        play_time_seconds=int(stats[0] or 0),
        last_played_at=stats[1],
        has_auto_state=has_auto,
    )


def set_favorite(db: Session, game_id: str, favorite: bool) -> Game:
    game = get_game(db, game_id)
    game.favorite = favorite
    db.commit()
    return game


def update_game(db: Session, game_id: str, changes: dict[str, object]) -> Game:
    game = get_game(db, game_id)
    for key, value in changes.items():
        setattr(game, key, value)
    db.commit()
    return game


def primary_file(game: Game) -> GameFile | None:
    return game.primary_file


def platform_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(Game.system, func.count(Game.id)).group_by(Game.system)).all()
    return {system: int(count) for system, count in rows}
