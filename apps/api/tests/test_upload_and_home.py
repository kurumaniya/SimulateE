from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.conftest import make_gba_rom


def test_upload_rom_creates_game(client: TestClient, data_dir: Path) -> None:
    response = client.post(
        "/api/games/upload",
        data={"system": "gba"},
        files={
            "file": (
                "../../evil/My Game (Japan).gba",
                make_gba_rom(b"upload"),
                "application/octet-stream",
            )
        },
    )
    assert response.status_code == 201, response.text
    game = response.json()
    assert game["title"] == "My Game"
    assert game["region"] == "Japan"
    assert (data_dir / "roms" / "gba" / "My Game (Japan).gba").is_file()
    assert not (data_dir / "evil").exists()


def test_upload_rejects_wrong_extension_and_duplicates(client: TestClient, rom_file: Path) -> None:
    wrong = client.post(
        "/api/games/upload",
        data={"system": "gba"},
        files={"file": ("game.nds", make_gba_rom(), "application/octet-stream")},
    )
    assert wrong.status_code == 422
    assert wrong.json()["error"]["code"] == "unsupported_rom"

    client.post("/api/games/scan")
    dup = client.post(
        "/api/games/upload",
        data={"system": "gba"},
        files={"file": ("Another Name.gba", rom_file.read_bytes(), "application/octet-stream")},
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_rom"
    assert not (rom_file.parent / "Another Name.gba").exists()


def test_upload_size_limit(client: TestClient) -> None:
    big = client.post(
        "/api/games/upload",
        data={"system": "gba"},
        files={"file": ("big.gba", b"x" * (1024 * 1024 + 1), "application/octet-stream")},
    )
    assert big.status_code == 413


def test_home_sections_and_favorites(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    game_id = scanned_game["id"]
    home = client.get("/api/library/home").json()
    assert [g["id"] for g in home["recently_added"]] == [game_id]
    assert home["recently_played"] == []
    assert home["continue_playing"] == []
    assert home["platforms"][0]["system"] == "gba"
    assert home["platforms"][0]["supported"] is True

    fav = client.post(f"/api/games/{game_id}/favorite", json={"favorite": True})
    assert fav.json()["favorite"] is True
    assert client.get("/api/games", params={"favorite": "true"}).json()["total"] == 1
    assert client.get("/api/library/home").json()["favorites"][0]["id"] == game_id


def test_search_filter_sort(client: TestClient, data_dir: Path) -> None:
    (data_dir / "roms" / "gba" / "Alpha (USA).gba").write_bytes(make_gba_rom(b"a"))
    (data_dir / "roms" / "gba" / "Beta (Europe).gba").write_bytes(make_gba_rom(b"b"))
    client.post("/api/games/scan")
    assert client.get("/api/games", params={"q": "beta"}).json()["total"] == 1
    assert client.get("/api/games", params={"system": "nds"}).json()["total"] == 0
    titles = [
        g["title"] for g in client.get("/api/games", params={"sort": "title"}).json()["items"]
    ]
    assert titles == ["Alpha", "Beta"]


def test_cover_upload_and_fetch(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    game_id = scanned_game["id"]
    assert client.get(f"/api/games/{game_id}/cover").status_code == 404
    response = client.put(
        f"/api/games/{game_id}/cover", files={"file": ("c.png", b"\x89PNGdata", "image/png")}
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_cover"] is True
    cover = client.get(f"/api/games/{game_id}/cover")
    assert cover.status_code == 200
    assert cover.headers["content-type"] == "image/png"
    bad = client.put(
        f"/api/games/{game_id}/cover", files={"file": ("c.exe", b"x", "application/x-msdownload")}
    )
    assert bad.status_code == 422


def test_error_shape_and_health(client: TestClient) -> None:
    missing = client.get("/api/games/nope")
    assert missing.status_code == 404
    assert missing.json() == {"error": {"code": "not_found", "message": "Game not found"}}
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/systems").json()[0]["id"] == "gb"
