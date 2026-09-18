"""Accounts and logins: password hashing, sessions, the first-run setup.

Passwords are hashed with scrypt from the standard library (no extra
dependency); a login is a random token in an HttpOnly cookie whose SHA-256 is
stored in ``user_sessions`` so it can be revoked server-side.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from retroweb.core.clock import utcnow
from retroweb.core.config import Settings
from retroweb.core.errors import (
    InvalidCredentialsError,
    NotFoundError,
    SetupCompleteError,
    UsernameTakenError,
    ValidationError,
)
from retroweb.core.logging import get_logger
from retroweb.models import User, UserSession

log = get_logger(__name__)

SESSION_COOKIE = "retroweb_session"
USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$")
MIN_PASSWORD_LENGTH = 8

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


# -- passwords ---------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_hex, digest_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode(),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(digest_hex) // 2,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


def validate_username(username: str) -> str:
    username = username.strip()
    if not USERNAME_RE.match(username):
        raise ValidationError("Username must be 2-32 characters: letters, digits, '.', '_' or '-'")
    return username


def validate_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return password


# -- accounts ----------------------------------------------------------------


def setup_required(db: Session) -> bool:
    """True until someone has a password, i.e. before the first real account."""
    count = db.scalar(select(func.count(User.id)).where(User.password_hash.is_not(None)))
    return not count


def create_user(db: Session, username: str, password: str, *, is_admin: bool) -> User:
    username = validate_username(username)
    validate_password(password)
    if db.scalar(select(User).where(func.lower(User.username) == username.lower())):
        raise UsernameTakenError()
    user = User(username=username, password_hash=hash_password(password), is_admin=is_admin)
    db.add(user)
    db.commit()
    log.info("user.created", user_id=user.id, username=username, admin=is_admin)
    return user


def setup_first_admin(db: Session, username: str, password: str) -> User:
    """Create the first account. If the implicit single-user account exists,
    it is claimed instead so its saves and play history carry over."""
    if not setup_required(db):
        raise SetupCompleteError()
    username = validate_username(username)
    validate_password(password)
    implicit = db.scalar(select(User).where(User.password_hash.is_(None)).order_by(User.created_at))
    other = db.scalar(select(User).where(func.lower(User.username) == username.lower()))
    if other is not None and other is not implicit:
        raise UsernameTakenError()
    if implicit is None:
        return create_user(db, username, password, is_admin=True)
    implicit.username = username
    implicit.password_hash = hash_password(password)
    implicit.is_admin = True
    db.commit()
    log.info("user.setup", user_id=implicit.id, username=username, claimed=True)
    return implicit


def authenticate(db: Session, username: str, password: str) -> User:
    user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        # Same work and same answer whether the user exists or not.
        verify_password(password, hash_password("x" * MIN_PASSWORD_LENGTH))
        raise InvalidCredentialsError()
    return user


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise InvalidCredentialsError("Current password is wrong")
    validate_password(new)
    user.password_hash = hash_password(new)
    db.commit()
    log.info("user.password_changed", user_id=user.id)


def update_user(
    db: Session, user: User, *, password: str | None = None, is_admin: bool | None = None
) -> User:
    if password is not None:
        validate_password(password)
        user.password_hash = hash_password(password)
    if is_admin is not None:
        user.is_admin = is_admin
    db.commit()
    return user


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.created_at)))


def get_user(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)  # saves, sessions, favorites cascade
    db.commit()
    log.info("user.deleted", user_id=user.id, username=user.username)


# -- logins ------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(
    db: Session, settings: Settings, user: User, user_agent: str | None
) -> tuple[str, UserSession]:
    """Returns ``(cookie token, row)``; only the row's hash is persisted."""
    token = secrets.token_urlsafe(32)
    now = utcnow()
    row = UserSession(
        user_id=user.id,
        token_hash=_token_hash(token),
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=settings.session_ttl_days),
        user_agent=(user_agent or "")[:255] or None,
    )
    db.add(row)
    db.commit()
    log.info("user.login", user_id=user.id)
    return token, row


def resolve_session(db: Session, settings: Settings, token: str | None) -> User | None:
    """The user a cookie token belongs to, refreshing the sliding expiry."""
    if not token:
        return None
    row = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    now = utcnow()
    if row is None or row.expires_at <= now:
        return None
    user = db.get(User, row.user_id)
    if user is None:
        return None
    if now - row.last_seen_at > timedelta(minutes=5):
        row.last_seen_at = now
        row.expires_at = now + timedelta(days=settings.session_ttl_days)
        db.commit()
    return user


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    row = db.scalar(select(UserSession).where(UserSession.token_hash == _token_hash(token)))
    if row is not None:
        db.delete(row)
        db.commit()
