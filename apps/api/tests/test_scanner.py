from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import make_gba_rom


def test_scan_adds_game_with_filename_metadata(client: TestClient, rom_file: Path) -> None:
    result = client.post("/api/games/scan").json()
    assert result["added"] == 1
    game = client.get("/api/games").json()["items"][0]
    assert game["title"] == "Test Game"
    assert game["system"] == "gba"
    assert game["region"] == "USA"
    detail = client.get(f"/api/games/{game['id']}").json()
    assert detail["rom_hash"] == hashlib.sha256(rom_file.read_bytes()).hexdigest()
    assert detail["rom_size"] == rom_file.stat().st_size
    assert detail["files"][0]["label"] == "Rev 1"


def test_rescan_is_idempotent(client: TestClient, rom_file: Path) -> None:
    client.post("/api/games/scan")
    result = client.post("/api/games/scan").json()
    assert result == {"added": 0, "updated": 0, "missing": 0, "skipped": 1, "errors": []}
    assert client.get("/api/games").json()["total"] == 1


def test_duplicate_content_is_skipped(client: TestClient, rom_file: Path) -> None:
    (rom_file.parent / "Copy.gba").write_bytes(rom_file.read_bytes())
    result = client.post("/api/games/scan").json()
    assert result["added"] == 1
    assert result["skipped"] == 1
    assert client.get("/api/games").json()["total"] == 1


def test_moved_file_is_relinked_by_hash(client: TestClient, rom_file: Path) -> None:
    client.post("/api/games/scan")
    game_id = client.get("/api/games").json()["items"][0]["id"]
    new_path = rom_file.parent / "Renamed.gba"
    rom_file.rename(new_path)
    result = client.post("/api/games/scan").json()
    assert result["updated"] == 1
    detail = client.get(f"/api/games/{game_id}").json()
    assert detail["rom_filename"] == "Renamed.gba"
    assert detail["rom_missing"] is False


def test_removed_file_is_flagged_missing(client: TestClient, rom_file: Path) -> None:
    client.post("/api/games/scan")
    game_id = client.get("/api/games").json()["items"][0]["id"]
    rom_file.unlink()
    result = client.post("/api/games/scan").json()
    assert result["missing"] == 1
    assert client.get(f"/api/games/{game_id}").json()["rom_missing"] is True
    rom = client.get(f"/api/games/{game_id}/rom")
    assert rom.status_code == 404
    assert rom.json()["error"]["code"] == "rom_missing"


def test_unknown_extension_is_skipped(client: TestClient, data_dir: Path) -> None:
    (data_dir / "roms" / "gba" / "notes.txt").write_text("hello")
    (data_dir / "roms" / "gba" / "other.gba").write_bytes(make_gba_rom(b"other"))
    result = client.post("/api/games/scan").json()
    assert result["added"] == 1
    assert result["skipped"] == 1
