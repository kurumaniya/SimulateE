"""User lookup. Single-user mode returns the implicit default account."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from retroweb.core.config import Settings
from retroweb.models import User


def ensure_default_user(session: Session, settings: Settings) -> User:
    user = session.scalar(select(User).where(User.username == settings.default_username))
    if user is None:
        user = User(username=settings.default_username, password_hash=None)
        session.add(user)
        session.commit()
    return user


def current_user(session: Session, settings: Settings) -> User:
    """Resolve the acting user.

    Phase 1: single-user mode only. When authentication lands this is where a
    session cookie is validated; callers never need to change.
    """
    if not settings.single_user_mode:
        raise NotImplementedError("multi-user authentication is not implemented yet")
    return ensure_default_user(session, settings)
