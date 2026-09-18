from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from retroweb.schemas.common import ApiModel


class UserOut(ApiModel):
    id: str
    username: str
    is_admin: bool
    created_at: datetime


class AuthStatus(BaseModel):
    mode: Literal["single", "multi"]
    # Multi-user mode before the first account exists.
    setup_required: bool
    registration_open: bool
    user: UserOut | None


class Credentials(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserCreate(Credentials):
    is_admin: bool = False


class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=1, max_length=256)
    is_admin: bool | None = None
