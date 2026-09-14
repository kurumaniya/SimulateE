"""Central application configuration.

Everything configurable lives here and is read from environment variables or a
``.env`` file. Other modules import ``get_settings()`` instead of reading
``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path | None:
    """Walk up from the working directory looking for a ``.env`` file.

    The API is normally started from ``apps/api`` while ``.env`` lives at the
    repository root, so a plain relative lookup would miss it.
    """
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        env = candidate / ".env"
        if env.is_file():
            return env
    return None


def _base_dir() -> Path:
    """Directory relative paths are resolved against: the ``.env`` location or cwd."""
    env = _find_env_file()
    return env.parent if env else Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_find_env_file(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RetroWeb"
    database_url: str = "sqlite:///./data/retroweb.db"

    data_path: Path = Path("./data")
    rom_path: Path | None = None
    save_path: Path | None = None
    state_path: Path | None = None
    bios_path: Path | None = None
    cover_path: Path | None = None
    screenshot_path: Path | None = None

    secret_key: str = "change-me"
    single_user_mode: bool = True
    default_username: str = "player"

    max_rom_upload_bytes: int = 2 * 1024 * 1024 * 1024
    max_save_upload_bytes: int = 64 * 1024 * 1024
    max_cover_upload_bytes: int = 5 * 1024 * 1024

    # A session without heartbeat for longer than this is considered ended at
    # its last heartbeat, so an abandoned tab cannot inflate play time.
    session_heartbeat_grace_seconds: int = 120
    # How often the client is expected to send heartbeats.
    session_heartbeat_interval_seconds: int = 30

    log_format: Literal["console", "json"] = "console"
    log_level: str = "INFO"

    # Comma separated; kept as a string because dotenv sources JSON-decode list fields.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @field_validator(
        "rom_path",
        "save_path",
        "state_path",
        "bios_path",
        "cover_path",
        "screenshot_path",
        mode="before",
    )
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("data_path", mode="after")
    @classmethod
    def _absolute_data_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (_base_dir() / value).resolve()

    @field_validator("database_url", mode="after")
    @classmethod
    def _absolute_sqlite_url(cls, value: str) -> str:
        """Anchor relative SQLite files to the project root, not the process cwd."""
        prefix = "sqlite:///"
        if value.startswith(prefix):
            location = value[len(prefix) :]
            if location and location != ":memory:" and not Path(location).is_absolute():
                return prefix + str((_base_dir() / location).resolve())
        return value

    def resolved_data_path(self) -> Path:
        return self.data_path.resolve()

    def storage_roots(self) -> dict[str, Path]:
        """Mount name → directory. Each mount is a top-level storage key prefix."""
        base = self.resolved_data_path()
        overrides = {
            "roms": self.rom_path,
            "saves": self.save_path,
            "states": self.state_path,
            "bios": self.bios_path,
            "covers": self.cover_path,
            "screenshots": self.screenshot_path,
        }
        return {
            name: (override.resolve() if override else base / name)
            for name, override in overrides.items()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
