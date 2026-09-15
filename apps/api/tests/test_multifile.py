from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

CD_SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def _make_disc(folder: Path, name: str) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    bin_path = folder / f"{name}.bin"
    bin_path.write_bytes((CD_SYNC + bytes(2352 - 12)) * 4 + name.encode())
    cue_path = folder / f"{name}.cue"
    cue_path.write_text(f'FILE "{name}.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
    return cue_path, bin_path


def test_cue_and_bin_become_one_game(client: TestClient, data_dir: Path) -> None:
    cue, binary = _make_disc(data_dir / "roms" / "ps1", "Test Disc (USA)")
    result = client.post("/api/games/scan").json()
    assert result["added"] == 2, result
    games = client.get("/api/games").json()
    assert games["total"] == 1
    detail = client.get(f"/api/games/{games['items'][0]['id']}").json()
    assert detail["system"] == "ps1"
    assert detail["rom_filename"] == cue.name
    roles = {f["filename"]: f["role"] for f in detail["files"]}
    assert roles == {cue.name: "primary", binary.name: "companion"}

    companion = next(f for f in detail["files"] if f["role"] == "companion")
    download = client.get(f"/api/games/{detail['id']}/files/{companion['id']}/{binary.name}")
    assert download.status_code == 200
    assert download.content == binary.read_bytes()
    ranged = client.get(
        f"/api/games/{detail['id']}/files/{companion['id']}/{binary.name}",
        headers={"Range": "bytes=0-11"},
    )
    assert ranged.status_code == 206
    assert ranged.content == CD_SYNC
    wrong_name = client.get(f"/api/games/{detail['id']}/files/{companion['id']}/other.bin")
    assert wrong_name.status_code == 404

    # Rescanning is stable.
    again = client.post("/api/games/scan").json()
    assert again["added"] == 0 and again["skipped"] == 2


def test_missing_companion_marks_game_missing(client: TestClient, data_dir: Path) -> None:
    _, binary = _make_disc(data_dir / "roms" / "ps1", "Broken Disc")
    client.post("/api/games/scan")
    binary.unlink()
    result = client.post("/api/games/scan").json()
    assert result["missing"] == 1
    game = client.get("/api/games").json()["items"][0]
    assert game["rom_missing"] is True


def test_raw_sector_bin_without_cue_is_ps1_by_header(client: TestClient, data_dir: Path) -> None:
    folder = data_dir / "roms" / "unsorted"
    folder.mkdir(parents=True)
    (folder / "loose.bin").write_bytes(CD_SYNC + bytes(0x200))
    client.post("/api/games/scan")
    games = client.get("/api/games").json()["items"]
    assert [g["system"] for g in games] == ["ps1"]
