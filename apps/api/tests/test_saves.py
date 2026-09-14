from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient


def _upload(client: TestClient, game_id: str, **overrides: object) -> object:
    fields = {
        "save_type": "battery",
        "slot": "0",
        "emulator_id": "emulatorjs",
        "core_id": "mgba",
        "core_version": "4.2.3",
    }
    fields.update({k: str(v) for k, v in overrides.items() if k != "data"})
    data = overrides.get("data", b"\x01\x02\x03SAVE")
    return client.post(
        f"/api/games/{game_id}/saves",
        data=fields,
        files={"file": ("battery.sav", data, "application/octet-stream")},
    )


def test_upload_list_download_battery(
    client: TestClient, scanned_game: dict, data_dir: Path
) -> None:  # type: ignore[type-arg]
    game_id = scanned_game["id"]
    created = _upload(client, game_id, data=b"SAVE-1")
    assert created.status_code == 201, created.text
    save = created.json()
    assert save["save_type"] == "battery"
    assert save["slot"] == 0
    assert save["size_bytes"] == 6
    assert save["core_id"] == "mgba"

    listed = client.get(f"/api/games/{game_id}/saves", params={"save_type": "battery"}).json()
    assert [row["id"] for row in listed] == [save["id"]]

    download = client.get(f"/api/saves/{save['id']}/download")
    assert download.status_code == 200
    assert download.content == b"SAVE-1"
    assert "x-save-updated-at" in download.headers

    # Files live under saves/<user>/<game>/, never under a client-chosen path.
    stored = list((data_dir / "saves").rglob("battery-0.sav"))
    assert len(stored) == 1
    assert game_id in str(stored[0])


def test_upload_replaces_same_slot(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    game_id = scanned_game["id"]
    first = _upload(client, game_id, data=b"OLD").json()
    second = _upload(
        client, game_id, data=b"NEWER", client_modified_at=datetime(2026, 1, 1).isoformat()
    ).json()
    assert second["id"] == first["id"]
    assert client.get(f"/api/saves/{first['id']}/download").content == b"NEWER"
    assert second["client_modified_at"].startswith("2026-01-01")
    assert len(client.get(f"/api/games/{game_id}/saves").json()) == 1


def test_state_slots_and_screenshot(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    game_id = scanned_game["id"]
    response = client.post(
        f"/api/games/{game_id}/saves",
        data={"save_type": "state", "slot": "-1", "emulator_id": "emulatorjs", "core_id": "mgba"},
        files={
            "file": ("auto.state", b"STATE", "application/octet-stream"),
            "screenshot": ("shot.png", b"\x89PNG fake", "image/png"),
        },
    )
    assert response.status_code == 201, response.text
    save = response.json()
    assert save["has_screenshot"] is True
    assert client.get(f"/api/saves/{save['id']}/screenshot").content == b"\x89PNG fake"
    assert client.get(f"/api/games/{game_id}").json()["has_auto_state"] is True

    bad_slot = _upload(client, game_id, save_type="state", slot=42)
    assert bad_slot.status_code == 422
    bad_battery_slot = _upload(client, game_id, save_type="battery", slot=1)
    assert bad_battery_slot.status_code == 422


def test_oversized_and_empty_uploads_rejected(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    game_id = scanned_game["id"]
    too_big = _upload(client, game_id, data=b"x" * (1024 * 1024 + 1))
    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "file_too_large"
    empty = _upload(client, game_id, data=b"")
    assert empty.status_code == 422


def test_delete_save(client: TestClient, scanned_game: dict, data_dir: Path) -> None:  # type: ignore[type-arg]
    game_id = scanned_game["id"]
    save = _upload(client, game_id).json()
    assert client.delete(f"/api/saves/{save['id']}").status_code == 204
    assert client.get(f"/api/saves/{save['id']}").status_code == 404
    assert not list((data_dir / "saves").rglob("*.sav"))


def test_save_for_unknown_game(client: TestClient) -> None:
    response = _upload(client, "nope")
    assert response.status_code == 404
