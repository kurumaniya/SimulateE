from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retroweb.api.deps import settings_dep
from retroweb.core.config import Settings
from retroweb.main import create_app

GBA_HEADER_FIXED_BYTE = 0xB2


def make_gba_rom(seed: bytes = b"retroweb-test", size: int = 4096) -> bytes:
    """A byte blob with the fixed GBA header byte set (not a runnable game)."""
    data = bytearray((seed * (size // len(seed) + 1))[:size])
    data[GBA_HEADER_FIXED_BYTE] = 0x96
    return bytes(data)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "roms" / "gba").mkdir(parents=True)
    return root


@pytest.fixture
def settings(data_dir: Path, tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_path=data_dir,
        max_save_upload_bytes=1024 * 1024,
        max_cover_upload_bytes=64 * 1024,
        max_rom_upload_bytes=1024 * 1024,
        session_heartbeat_grace_seconds=60,
        log_level="WARNING",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[settings_dep] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def rom_file(data_dir: Path) -> Path:
    path = data_dir / "roms" / "gba" / "Test Game (USA) (Rev 1).gba"
    path.write_bytes(make_gba_rom())
    return path


@pytest.fixture
def scanned_game(client: TestClient, rom_file: Path) -> dict:  # type: ignore[type-arg]
    response = client.post("/api/games/scan")
    assert response.status_code == 200, response.text
    games = client.get("/api/games").json()["items"]
    assert len(games) == 1
    return client.get(f"/api/games/{games[0]['id']}").json()
