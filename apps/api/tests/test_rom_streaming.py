from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_full_download(client: TestClient, scanned_game: dict, rom_file: Path) -> None:  # type: ignore[type-arg]
    response = client.get(f"/api/games/{scanned_game['id']}/rom")
    assert response.status_code == 200
    assert response.content == rom_file.read_bytes()
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-length"] == str(rom_file.stat().st_size)
    assert response.headers["etag"] == f'"{scanned_game["rom_hash"]}"'
    assert "filename*=UTF-8''Test%20Game" in response.headers["content-disposition"]


def test_range_request(client: TestClient, scanned_game: dict, rom_file: Path) -> None:  # type: ignore[type-arg]
    data = rom_file.read_bytes()
    response = client.get(f"/api/games/{scanned_game['id']}/rom", headers={"Range": "bytes=10-19"})
    assert response.status_code == 206
    assert response.content == data[10:20]
    assert response.headers["content-range"] == f"bytes 10-19/{len(data)}"
    assert response.headers["content-length"] == "10"

    suffix = client.get(f"/api/games/{scanned_game['id']}/rom", headers={"Range": "bytes=-5"})
    assert suffix.status_code == 206
    assert suffix.content == data[-5:]

    open_ended = client.get(
        f"/api/games/{scanned_game['id']}/rom", headers={"Range": f"bytes={len(data) - 3}-"}
    )
    assert open_ended.content == data[-3:]


def test_unsatisfiable_range(client: TestClient, scanned_game: dict, rom_file: Path) -> None:  # type: ignore[type-arg]
    response = client.get(
        f"/api/games/{scanned_game['id']}/rom", headers={"Range": "bytes=999999-"}
    )
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{rom_file.stat().st_size}"


def test_head_and_etag(client: TestClient, scanned_game: dict, rom_file: Path) -> None:  # type: ignore[type-arg]
    head = client.head(f"/api/games/{scanned_game['id']}/rom")
    assert head.status_code == 200
    assert head.headers["content-length"] == str(rom_file.stat().st_size)
    assert head.content == b""
    cached = client.get(
        f"/api/games/{scanned_game['id']}/rom",
        headers={"If-None-Match": f'"{scanned_game["rom_hash"]}"'},
    )
    assert cached.status_code == 304


def test_named_rom_url_requires_exact_filename(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    ok = client.get(f"/api/games/{scanned_game['id']}/rom/{scanned_game['rom_filename']}")
    assert ok.status_code == 200
    bad = client.get(f"/api/games/{scanned_game['id']}/rom/..%2F..%2Fetc%2Fpasswd")
    assert bad.status_code == 404
    other = client.get(f"/api/games/{scanned_game['id']}/rom/other.gba")
    assert other.status_code == 404


def test_unknown_game_ids_never_touch_the_filesystem(client: TestClient) -> None:
    for game_id in ["../../etc/passwd", "..", "%2e%2e%2f", "does-not-exist"]:
        response = client.get(f"/api/games/{game_id}/rom")
        assert response.status_code == 404, game_id
