"""Sign-in, first-run setup and the current account."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from retroweb.api.deps import DbDep, SettingsDep, UserDep
from retroweb.core.config import Settings
from retroweb.core.errors import FeatureDisabledError, RegistrationClosedError
from retroweb.models import User
from retroweb.schemas.auth import AuthStatus, Credentials, PasswordChange, UserOut
from retroweb.services import auth as auth_service
from retroweb.services.auth import SESSION_COOKIE

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, username=user.username, is_admin=user.is_admin, created_at=user.created_at
    )


def _start_session(
    db: DbDep, settings: Settings, request: Request, response: Response, user: User
) -> UserOut:
    token, _row = auth_service.create_session(db, settings, user, request.headers.get("user-agent"))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.session_ttl_days * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    return user_out(user)


@router.get("/status", response_model=AuthStatus)
def status(request: Request, db: DbDep, settings: SettingsDep) -> AuthStatus:
    """What the client needs before rendering: mode, setup state, who is signed in."""
    if settings.single_user_mode:
        return AuthStatus(mode="single", setup_required=False, registration_open=False, user=None)
    user = auth_service.resolve_session(db, settings, request.cookies.get(SESSION_COOKIE))
    return AuthStatus(
        mode="multi",
        setup_required=auth_service.setup_required(db),
        registration_open=settings.allow_registration,
        user=user_out(user) if user else None,
    )


@router.post("/setup", response_model=UserOut, status_code=201)
def setup(
    payload: Credentials, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> UserOut:
    """Create the first (admin) account and sign in. Only works once."""
    _require_multi(settings)
    user = auth_service.setup_first_admin(db, payload.username, payload.password)
    return _start_session(db, settings, request, response, user)


@router.post("/register", response_model=UserOut, status_code=201)
def register(
    payload: Credentials, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> UserOut:
    _require_multi(settings)
    if not settings.allow_registration:
        raise RegistrationClosedError()
    if auth_service.setup_required(db):
        # The very first account is the admin's; make that explicit.
        user = auth_service.setup_first_admin(db, payload.username, payload.password)
    else:
        user = auth_service.create_user(db, payload.username, payload.password, is_admin=False)
    return _start_session(db, settings, request, response, user)


@router.post("/login", response_model=UserOut)
def login(
    payload: Credentials, request: Request, response: Response, db: DbDep, settings: SettingsDep
) -> UserOut:
    _require_multi(settings)
    user = auth_service.authenticate(db, payload.username, payload.password)
    return _start_session(db, settings, request, response, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DbDep) -> Response:
    auth_service.revoke_session(db, request.cookies.get(SESSION_COOKIE))
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserOut)
def me(user: UserDep) -> UserOut:
    return user_out(user)


@router.patch("/password", response_model=UserOut)
def change_password(
    payload: PasswordChange, db: DbDep, user: UserDep, settings: SettingsDep
) -> UserOut:
    _require_multi(settings)
    auth_service.change_password(db, user, payload.current_password, payload.new_password)
    return user_out(user)


def _require_multi(settings: Settings) -> None:
    if settings.single_user_mode:
        raise FeatureDisabledError("Accounts are off: the server runs in single-user mode")
