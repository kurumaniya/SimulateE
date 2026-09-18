"""User lookup: the implicit account in single-user mode, the login otherwise."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from retroweb.core.config import Settings
from retroweb.core.errors import UnauthorizedError
from retroweb.models import User
from retroweb.services.auth import resolve_session


def ensure_default_user(session: Session, settings: Settings) -> User:
    user = session.scalar(select(User).where(User.username == settings.default_username))
    if user is None:
        user = User(username=settings.default_username, password_hash=None)
        session.add(user)
        session.commit()
    return user


def current_user(session: Session, settings: Settings, session_token: str | None) -> User:
    """Resolve the acting user.

    Single-user mode returns the implicit account. Otherwise the request must
    carry a valid login cookie (see ``services/auth.py``).
    """
    if settings.single_user_mode:
        return ensure_default_user(session, settings)
    user = resolve_session(session, settings, session_token)
    if user is None:
        raise UnauthorizedError()
    return user
