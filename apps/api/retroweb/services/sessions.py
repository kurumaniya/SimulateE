"""Play session lifecycle. The server owns every timestamp."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retroweb.core.clock import utcnow
from retroweb.core.config import Settings
from retroweb.core.errors import NotFoundError, SessionStateError
from retroweb.core.logging import get_logger
from retroweb.models import Game, PlaySession, User

log = get_logger(__name__)


def _effective_end(session_row: PlaySession, now: datetime, grace: timedelta) -> datetime:
    """The latest moment we can honestly count as play time."""
    return min(now, session_row.last_heartbeat_at + grace)


def _close(session_row: PlaySession, ended_at: datetime) -> None:
    ended_at = max(ended_at, session_row.started_at)
    session_row.ended_at = ended_at
    session_row.duration_seconds = int((ended_at - session_row.started_at).total_seconds())


def close_stale_sessions(db: Session, user: User, settings: Settings) -> int:
    """Close open sessions whose heartbeat stopped; returns how many were closed."""
    now = utcnow()
    grace = timedelta(seconds=settings.session_heartbeat_grace_seconds)
    open_rows = db.scalars(
        select(PlaySession).where(PlaySession.user_id == user.id, PlaySession.ended_at.is_(None))
    ).all()
    closed = 0
    for row in open_rows:
        if now - row.last_heartbeat_at > grace:
            _close(row, row.last_heartbeat_at)
            closed += 1
    return closed


def start_session(
    db: Session,
    user: User,
    settings: Settings,
    game_id: str,
    device: str | None,
    emulator_id: str | None,
) -> PlaySession:
    game = db.get(Game, game_id)
    if game is None:
        raise NotFoundError("Game not found")
    now = utcnow()
    # One active session per user: starting a new game ends the previous sitting.
    for row in db.scalars(
        select(PlaySession).where(PlaySession.user_id == user.id, PlaySession.ended_at.is_(None))
    ):
        grace = timedelta(seconds=settings.session_heartbeat_grace_seconds)
        _close(row, _effective_end(row, now, grace))
    session_row = PlaySession(
        user_id=user.id,
        game_id=game_id,
        started_at=now,
        last_heartbeat_at=now,
        device=(device or "")[:255] or None,
        emulator_id=(emulator_id or "")[:64] or None,
    )
    db.add(session_row)
    db.commit()
    log.info("game.launch", game_id=game_id, session_id=session_row.id, emulator=emulator_id)
    return session_row


def _get_owned(db: Session, user: User, session_id: str) -> PlaySession:
    row = db.get(PlaySession, session_id)
    if row is None or row.user_id != user.id:
        raise NotFoundError("Play session not found", code="session_not_found")
    return row


def heartbeat(db: Session, user: User, session_id: str) -> PlaySession:
    row = _get_owned(db, user, session_id)
    if row.ended_at is not None:
        raise SessionStateError("Play session already ended")
    row.last_heartbeat_at = utcnow()
    db.commit()
    return row


def end_session(db: Session, user: User, settings: Settings, session_id: str) -> PlaySession:
    row = _get_owned(db, user, session_id)
    if row.ended_at is not None:
        raise SessionStateError("Play session already ended")
    grace = timedelta(seconds=settings.session_heartbeat_grace_seconds)
    _close(row, _effective_end(row, utcnow(), grace))
    db.commit()
    log.info("game.session.ended", session_id=row.id, duration=row.duration_seconds)
    return row


def recent_sessions(db: Session, user: User, limit: int = 20) -> list[PlaySession]:
    return list(
        db.scalars(
            select(PlaySession)
            .where(PlaySession.user_id == user.id)
            .order_by(PlaySession.started_at.desc())
            .limit(limit)
        )
    )


def play_stats(
    db: Session, user: User, game_ids: list[str]
) -> dict[str, tuple[int, datetime | None]]:
    """game_id → (total seconds, last played). Open sessions count up to their last heartbeat."""
    if not game_ids:
        return {}
    rows = db.execute(
        select(
            PlaySession.game_id,
            func.coalesce(func.sum(PlaySession.duration_seconds), 0),
            func.max(PlaySession.started_at),
        )
        .where(PlaySession.user_id == user.id, PlaySession.game_id.in_(game_ids))
        .group_by(PlaySession.game_id)
    ).all()
    return {game_id: (int(total), last) for game_id, total, last in rows}
