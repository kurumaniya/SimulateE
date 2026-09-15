from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

FAKE_PS1_BIOS = b"\x00" * 1024


def test_inventory_lists_known_files(client: TestClient) -> None:
    rows = client.get("/api/bios").json()
    ps1 = next(row for row in rows if row["system"] == "ps1")
    assert ps1["optional"] is True
    assert ps1["ready"] is True  # HLE fallback
    assert ps1["preferred_file"] is None
    assert any(f["filename"] == "scph1001.bin" for f in ps1["files"])
    assert all(f["installed"] is False for f in ps1["files"])


def test_upload_known_name_is_stored_and_flagged_unverified(
    client: TestClient, data_dir: Path
) -> None:
    response = client.post(
        "/api/bios/ps1", files={"file": ("SCPH1001.BIN", FAKE_PS1_BIOS, "application/octet-stream")}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    row = next(f for f in body["files"] if f["filename"] == "scph1001.bin")
    assert row["installed"] is True
    assert row["verified"] is False  # content does not match the known image
    assert row["sha256"] == hashlib.sha256(FAKE_PS1_BIOS).hexdigest()
    assert body["preferred_file"] == "scph1001.bin"
    assert (data_dir / "bios" / "ps1" / "scph1001.bin").read_bytes() == FAKE_PS1_BIOS

    download = client.get("/api/bios/ps1/scph1001.bin")
    assert download.status_code == 200
    assert download.content == FAKE_PS1_BIOS


def test_upload_unknown_name_is_rejected(client: TestClient, data_dir: Path) -> None:
    response = client.post(
        "/api/bios/ps1",
        files={"file": ("../../evil.bin", FAKE_PS1_BIOS, "application/octet-stream")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_rom"
    assert not list((data_dir / "bios").rglob("*.bin"))


def test_upload_matching_md5_is_renamed(client: TestClient) -> None:
    # Any content whose MD5 equals a registry digest is accepted under the
    # canonical name; simulate by registering the fake's digest.
    from retroweb.library import bios as registry
    from retroweb.library.systems import GameSystem

    info = registry.BIOS_REGISTRY[GameSystem.GB]
    fake = b"boot rom"
    patched = registry.SystemBiosInfo(
        system=info.system,
        note=info.note,
        optional=info.optional,
        files=(registry.BiosSpec("gb_bios.bin", "test", hashlib.md5(fake).hexdigest()),),  # noqa: S324
    )
    registry.BIOS_REGISTRY[GameSystem.GB] = patched
    try:
        response = client.post(
            "/api/bios/gb", files={"file": ("whatever.rom", fake, "application/octet-stream")}
        )
        assert response.status_code == 201, response.text
        row = response.json()["files"][0]
        assert row["filename"] == "gb_bios.bin"
        assert row["verified"] is True
    finally:
        registry.BIOS_REGISTRY[GameSystem.GB] = info


def test_delete_and_missing(client: TestClient) -> None:
    client.post(
        "/api/bios/ps1", files={"file": ("scph5501.bin", FAKE_PS1_BIOS, "application/octet-stream")}
    )
    assert client.delete("/api/bios/ps1/scph5501.bin").status_code == 204
    assert client.delete("/api/bios/ps1/scph5501.bin").status_code == 404
    missing = client.get("/api/bios/ps1/scph5501.bin")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "bios_missing"
    assert client.get("/api/bios/ps1/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/bios/gba").status_code == 404


def test_oversized_bios_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/bios/ps1",
        files={"file": ("scph1001.bin", b"x" * (8 * 1024 * 1024 + 1), "application/octet-stream")},
    )
    assert response.status_code == 413
