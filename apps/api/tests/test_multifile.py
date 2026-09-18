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


def _make_set(folder: Path, title: str, discs: int) -> Path:
    """A multi-disc set: one .cue/.bin per disc plus an .m3u naming the cues."""
    names = [f"{title} (Disc {n})" for n in range(1, discs + 1)]
    for name in names:
        _make_disc(folder, name)
    playlist = folder / f"{title}.m3u"
    playlist.write_text("# discs\n" + "".join(f"{name}.cue\n" for name in names))
    return playlist


def test_m3u_groups_discs_into_one_game(client: TestClient, data_dir: Path) -> None:
    playlist = _make_set(data_dir / "roms" / "ps1", "Long RPG (USA)", 2)
    result = client.post("/api/games/scan").json()
    assert result["added"] == 5, result  # m3u + 2 cue + 2 bin
    games = client.get("/api/games").json()
    assert games["total"] == 1
    detail = client.get(f"/api/games/{games['items'][0]['id']}").json()
    assert detail["title"] == "Long RPG"
    assert detail["rom_filename"] == playlist.name
    roles = {f["filename"]: f["role"] for f in detail["files"]}
    assert roles[playlist.name] == "primary"
    assert sum(role == "companion" for role in roles.values()) == 4
    again = client.post("/api/games/scan").json()
    assert again["added"] == 0 and again["skipped"] == 5


def test_m3u_adopts_existing_disc_games_and_keeps_saves(client: TestClient, data_dir: Path) -> None:
    folder = data_dir / "roms" / "ps1"
    _make_disc(folder, "Long RPG (USA) (Disc 1)")
    _make_disc(folder, "Long RPG (USA) (Disc 2)")
    client.post("/api/games/scan")
    games = client.get("/api/games").json()["items"]
    assert len(games) == 2
    disc1 = next(
        g
        for g in games
        if client.get(f"/api/games/{g['id']}").json()["rom_filename"].endswith("(Disc 1).cue")
    )
    save = client.post(
        f"/api/games/{disc1['id']}/saves",
        data={"save_type": "battery", "slot": "0", "emulator_id": "test"},
        files={"file": ("battery.sav", b"progress", "application/octet-stream")},
    )
    assert save.status_code == 201, save.text

    playlist = _make_set(folder, "Long RPG (USA)", 2)  # rewrites the same discs + adds the m3u
    result = client.post("/api/games/scan").json()
    assert result["added"] == 1, result  # only the playlist is new
    games = client.get("/api/games").json()
    assert games["total"] == 1
    merged = client.get(f"/api/games/{games['items'][0]['id']}").json()
    assert merged["id"] == disc1["id"], "disc 1's game (and its saves) must survive"
    assert merged["rom_filename"] == playlist.name
    assert len(merged["files"]) == 5
    saves = client.get(f"/api/games/{merged['id']}/saves").json()
    assert [s["save_type"] for s in saves] == ["battery"]


def test_renamed_disc_drops_stale_companions(client: TestClient, data_dir: Path) -> None:
    folder = data_dir / "roms" / "ps1"
    playlist = _make_set(folder, "Long RPG (USA)", 1)
    client.post("/api/games/scan")
    # Rename the disc and point the playlist at the new name.
    (folder / "Long RPG (USA) (Disc 1).cue").unlink()
    (folder / "Long RPG (USA) (Disc 1).bin").unlink()
    _make_disc(folder, "Long RPG (USA) (Disc A)")
    playlist.write_text("Long RPG (USA) (Disc A).cue\n")
    result = client.post("/api/games/scan").json()
    assert result["missing"] == 0, result
    game = client.get("/api/games").json()["items"][0]
    assert game["rom_missing"] is False
    detail = client.get(f"/api/games/{game['id']}").json()
    assert sorted(f["filename"] for f in detail["files"]) == [
        "Long RPG (USA) (Disc A).bin",
        "Long RPG (USA) (Disc A).cue",
        "Long RPG (USA).m3u",
    ]


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
