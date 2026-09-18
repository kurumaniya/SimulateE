"""Account administration (multi-user mode, admins only)."""

from __future__ import annotations

from fastapi import APIRouter, Response

from retroweb.api.auth import user_out
from retroweb.api.deps import AdminDep, DbDep, SettingsDep
from retroweb.core.errors import FeatureDisabledError, ValidationError
from retroweb.schemas.auth import UserCreate, UserOut, UserUpdate
from retroweb.services import auth as auth_service

router = APIRouter(prefix="/users", tags=["users"])


def _require_multi(settings: SettingsDep) -> None:
    if settings.single_user_mode:
        raise FeatureDisabledError("Accounts are off: the server runs in single-user mode")


@router.get("", response_model=list[UserOut])
def list_users(db: DbDep, settings: SettingsDep, _admin: AdminDep) -> list[UserOut]:
    _require_multi(settings)
    return [user_out(user) for user in auth_service.list_users(db)]


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: DbDep, settings: SettingsDep, _admin: AdminDep) -> UserOut:
    _require_multi(settings)
    return user_out(
        auth_service.create_user(db, payload.username, payload.password, is_admin=payload.is_admin)
    )


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str, payload: UserUpdate, db: DbDep, settings: SettingsDep, admin: AdminDep
) -> UserOut:
    _require_multi(settings)
    user = auth_service.get_user(db, user_id)
    if user.id == admin.id and payload.is_admin is False:
        raise ValidationError("You cannot remove your own admin role")
    return user_out(
        auth_service.update_user(db, user, password=payload.password, is_admin=payload.is_admin)
    )


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, db: DbDep, settings: SettingsDep, admin: AdminDep) -> Response:
    _require_multi(settings)
    user = auth_service.get_user(db, user_id)
    if user.id == admin.id:
        raise ValidationError("You cannot delete your own account")
    auth_service.delete_user(db, user)
    return Response(status_code=204)
