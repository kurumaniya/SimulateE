"""Nested ROM mounts (ROM_MOUNTS) and rescans that skip unchanged files."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from retroweb.api.deps import settings_dep
from retroweb.core.config import Settings
from retroweb.library import scanner as scanner_module
from retroweb.main import create_app
from retroweb.storage import InvalidStorageKeyError, LocalStorageProvider, MountedStorage
from tests.conftest import make_gba_rom

# -- MountedStorage with nested prefixes ---------------------------------------


def test_nested_mount_routes_and_lists(tmp_path: Path) -> None:
    local = LocalStorageProvider(tmp_path / "local")
    nas = LocalStorageProvider(tmp_path / "nas-psp")
    storage = MountedStorage({"roms": local, "roms/psp": nas})

    storage.write("roms/gba/a.gba", b"gba")
    storage.write("roms/psp/Game.iso", b"psp on nas")
    # Whatever sits under the local roms/psp folder is shadowed by the mount.
    (tmp_path / "local" / "psp").mkdir()
    (tmp_path / "local" / "psp" / "stale.iso").write_bytes(b"stale")

    assert (tmp_path / "nas-psp" / "Game.iso").read_bytes() == b"psp on nas"
    assert storage.read("roms/psp/Game.iso") == b"psp on nas"
    assert storage.exists("roms/psp/stale.iso") is False
    assert sorted(o.key for o in storage.list("roms")) == ["roms/gba/a.gba", "roms/psp/Game.iso"]
    assert [o.key for o in storage.list("roms/psp")] == ["roms/psp/Game.iso"]
    assert [o.key for o in storage.list("roms/gba")] == ["roms/gba/a.gba"]
    assert storage.size("roms/psp/Game.iso") == len(b"psp on nas")
    with pytest.raises(InvalidStorageKeyError):
        storage.read("roms/psp/../gba/a.gba")


def test_rom_mounts_setting_parses_and_validates(tmp_path: Path) -> None:
    settings = Settings(
        data_path=tmp_path, rom_mounts=f"psp={tmp_path / 'nas' / 'psp'}; N64 = {tmp_path / 'n64'}"
    )
    roots = settings.rom_mount_roots()
    assert roots == {
        "psp": (tmp_path / "nas" / "psp").resolve(),
        "n64": (tmp_path / "n64").resolve(),
    }
    with pytest.raises(ValueError):
        Settings(data_path=tmp_path, rom_mounts="psp").rom_mount_roots()
    with pytest.raises(ValueError):
        Settings(data_path=tmp_path, rom_mounts="psp/x=/tmp").rom_mount_roots()


@pytest.fixture
def nas_client(tmp_path: Path, data_dir: Path) -> Iterator[tuple[TestClient, Path]]:
    nas_psp = tmp_path / "nas" / "roms" / "psp"
    nas_psp.mkdir(parents=True)
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'nas.db'}",
        data_path=data_dir,
        rom_mounts=f"psp={nas_psp}",
        log_level="WARNING",
        gamedb_base_url="https://gamedb.test",
    )
    app = create_app(settings)
    app.dependency_overrides[settings_dep] = lambda: settings
    with TestClient(app) as client:
        yield client, nas_psp


def test_scan_finds_games_on_the_nas_mount(
    nas_client: tuple[TestClient, Path], rom_file: Path
) -> None:
    client, nas_psp = nas_client
    (nas_psp / "Some Game (USA).iso").write_bytes(b"\0" * 4096)
    result = client.post("/api/games/scan").json()
    assert result["added"] == 2, result
    games = {g["system"]: g for g in client.get("/api/games").json()["items"]}
    assert set(games) == {"gba", "psp"}
    psp = client.get(f"/api/games/{games['psp']['id']}").json()
    assert psp["rom_filename"] == "Some Game (USA).iso"
    # The ROM streams from the mount like any other file.
    rom = client.get(f"/api/games/{psp['id']}/rom/Some Game (USA).iso")
    assert rom.status_code == 200 and len(rom.content) == 4096


# -- rescans skip unchanged files ---------------------------------------------------


@pytest.fixture
def hash_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    original = scanner_module.GameScanner.calculate_hash

    def counting(self: scanner_module.GameScanner, key: str) -> tuple[str, bytes]:
        calls.append(key)
        return original(self, key)

    monkeypatch.setattr(scanner_module.GameScanner, "calculate_hash", counting)
    return calls


def test_rescan_does_not_rehash_unchanged_files(
    client: TestClient, rom_file: Path, hash_calls: list[str]
) -> None:
    assert client.post("/api/games/scan").json()["added"] == 1
    assert hash_calls == ["roms/gba/Test Game (USA) (Rev 1).gba"]

    hash_calls.clear()
    result = client.post("/api/games/scan").json()
    assert result == {"added": 0, "updated": 0, "missing": 0, "skipped": 1, "errors": []}
    assert hash_calls == []
    game = client.get("/api/games").json()["items"][0]
    assert client.get(f"/api/games/{game['id']}").json()["rom_missing"] is False


def test_changed_file_is_rehashed(
    client: TestClient, rom_file: Path, hash_calls: list[str]
) -> None:
    client.post("/api/games/scan")
    hash_calls.clear()

    # Same size, new content: only the mtime changes.
    rom_file.write_bytes(make_gba_rom(b"changed-content"))
    stamp = rom_file.stat().st_mtime + 5
    os.utime(rom_file, (stamp, stamp))
    result = client.post("/api/games/scan").json()
    assert hash_calls == ["roms/gba/Test Game (USA) (Rev 1).gba"]
    assert result["updated"] == 1
    game = client.get("/api/games").json()["items"][0]
    detail = client.get(f"/api/games/{game['id']}").json()
    assert detail["rom_hash"] != ""

    # Unchanged again: nothing is read.
    hash_calls.clear()
    assert client.post("/api/games/scan").json()["skipped"] == 1
    assert hash_calls == []


def test_missing_file_that_returns_is_hashed_again(
    client: TestClient, rom_file: Path, hash_calls: list[str]
) -> None:
    client.post("/api/games/scan")
    data = rom_file.read_bytes()
    stat = rom_file.stat()
    rom_file.unlink()
    assert client.post("/api/games/scan").json()["missing"] == 1

    rom_file.write_bytes(data)
    os.utime(rom_file, (stat.st_atime, stat.st_mtime))
    hash_calls.clear()
    result = client.post("/api/games/scan").json()
    assert hash_calls == ["roms/gba/Test Game (USA) (Rev 1).gba"]
    assert result["updated"] == 1
    game = client.get("/api/games").json()["items"][0]
    assert client.get(f"/api/games/{game['id']}").json()["rom_missing"] is False
