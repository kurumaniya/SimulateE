"""Arcade (FBNeo ROM sets) and Sega Saturn: folder-only detection, naming, BIOS."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from retroweb.core.config import Settings
from retroweb.library.detection import detect_system
from retroweb.library.romid import fingerprint
from retroweb.library.systems import GameSystem
from tests.test_artwork import PNG, install_fetcher
from tests.test_identify import game_database, install_identifier

FBNEO_DAT = "/metadat/fbneo-split/FBNeo - Arcade Games.dat"


def rom_set(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_folder_only_systems_are_detected_by_folder_alone() -> None:
    assert detect_system("roms/arcade/sf2.zip", b"PK\x03\x04").system is GameSystem.ARCADE
    assert detect_system("roms/neogeo/mslug.zip", b"PK\x03\x04").system is GameSystem.ARCADE
    assert detect_system("roms/saturn/Game (USA).cue", b"").system is GameSystem.SATURN
    assert detect_system("roms/saturn/Game (USA).iso", b"").system is GameSystem.SATURN
    # Outside their folders those extensions keep meaning what they meant before.
    assert detect_system("roms/misc/Game (USA).cue", b"").system is GameSystem.PS1
    assert detect_system("roms/psp/Game.iso", b"").system is GameSystem.PSP
    # A zipped cartridge ROM is not an arcade set, and not a GBA game either.
    assert detect_system("roms/gba/game.zip", b"PK\x03\x04").system is None
    assert detect_system("roms/unsorted/sf2.zip", b"PK\x03\x04").system is None


def test_saturn_serial_is_read_from_the_system_id() -> None:
    sector = bytearray(2048)
    sector[0:16] = b"SEGA SEGASATURN "
    sector[16:32] = b"SEGA TP T-81    "
    sector[32:48] = b"T-8106G   V1.000"
    raw_track = b"\x00" + b"\xff" * 10 + b"\x00" + b"\x00" * 4 + bytes(sector)  # 2352-byte mode 1
    for image in (bytes(sector) * 4, raw_track * 4):
        assert fingerprint(GameSystem.SATURN, [image], len(image)).serial == "T-8106G"


def test_arcade_set_is_named_after_the_fbneo_list(
    client: TestClient, settings: Settings, data_dir: Path
) -> None:
    arcade = data_dir / "roms" / "arcade"
    arcade.mkdir(parents=True)
    (arcade / "sbrawl.zip").write_bytes(rom_set({"prog.1": b"\xf3\x18\xfe", "gfx.2": b"tiles"}))
    # The same archive dropped into a cartridge folder is ignored.
    (data_dir / "roms" / "gba" / "other.zip").write_bytes(rom_set({"x": b"y"}))
    assert client.post("/api/games/scan").status_code == 200
    games = client.get("/api/games").json()["items"]
    assert [(game["title"], game["system"]) for game in games] == [("sbrawl", "arcade")]
    game_id = games[0]["id"]

    dat = (
        'game (\n\tname "Street Brawler II: The Rematch (World 910522)"\n\treleaseyear "1991"\n'
        '\tpublisher "Acme"\n\trom ( name sbrawl.zip size 1 crc 00000001 md5 00 sha1 00 )\n)\n'
    )
    install_identifier(client, settings, game_database({FBNEO_DAT: dat}))

    def thumbnails(request: httpx.Request) -> httpx.Response:
        wanted = (
            "/FBNeo - Arcade Games/Named_Boxarts/Street Brawler II_ The Rematch (World 910522).png"
        )
        if httpx.URL(request.url).path == wanted:
            return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})
        return httpx.Response(404, text="not found", headers={"content-type": "text/html"})

    install_fetcher(client, settings, httpx.MockTransport(thumbnails))
    response = client.post(f"/api/games/{game_id}/cover/fetch")
    assert response.status_code == 200, response.text
    game = response.json()
    assert game["identified_by"] == "name"
    assert game["canonical_name"] == "Street Brawler II: The Rematch (World 910522)"
    # The set name was only a placeholder title; the file keeps its exact name.
    assert game["title"] == "Street Brawler II: The Rematch"
    assert game["rom_filename"] == "sbrawl.zip"
    assert (game["publisher"], game["release_date"]) == ("Acme", "1991-01-01")
    assert game["files"][0]["sha1"] is None  # sets are never fingerprinted
    assert game["has_cover"] is True

    rom = client.get(f"/api/games/{game_id}/rom/sbrawl.zip")
    assert rom.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(rom.content)).namelist() == ["prog.1", "gfx.2"]


def test_arcade_and_saturn_bios_files_are_accepted(client: TestClient) -> None:
    systems = {entry["system"]: entry for entry in client.get("/api/bios").json()}
    assert systems["arcade"]["optional"] is True
    assert systems["saturn"]["optional"] is True

    neogeo = rom_set({"sp-s2.sp1": b"bios"})
    response = client.post(
        "/api/bios/arcade", files={"file": ("neogeo.zip", neogeo, "application/zip")}
    )
    assert response.status_code in (200, 201), response.text
    response = client.post(
        "/api/bios/saturn",
        files={"file": ("saturn_bios.bin", b"\0" * 1024, "application/octet-stream")},
    )
    assert response.status_code in (200, 201), response.text
    installed = client.get("/api/bios/arcade").json()
    assert installed["preferred_file"] == "neogeo.zip"
