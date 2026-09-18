from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from retroweb.api.deps import settings_dep
from retroweb.core.config import Settings
from retroweb.main import create_app
from retroweb.services.auth import hash_password, verify_password
from tests.conftest import make_gba_rom

ADMIN = {"username": "koy", "password": "correct horse battery"}
BOB = {"username": "bob", "password": "bobs-password-1"}


@pytest.fixture
def multi_app(settings: Settings) -> FastAPI:
    multi = settings.model_copy(update={"single_user_mode": False})
    app = create_app(multi)
    app.dependency_overrides[settings_dep] = lambda: multi
    return app


@pytest.fixture
def anon(multi_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(multi_app) as client:
        yield client


@pytest.fixture
def admin(multi_app: FastAPI, anon: TestClient) -> TestClient:
    """A signed-in admin: the first account, created through /auth/setup."""
    client = TestClient(multi_app)
    response = client.post("/api/auth/setup", json=ADMIN)
    assert response.status_code == 201, response.text
    return client


@pytest.fixture
def bob(multi_app: FastAPI, admin: TestClient) -> TestClient:
    """A signed-in regular user created by the admin."""
    created = admin.post("/api/users", json=BOB)
    assert created.status_code == 201, created.text
    client = TestClient(multi_app)
    assert client.post("/api/auth/login", json=BOB).status_code == 200
    return client


def test_password_hashing_roundtrip() -> None:
    stored = hash_password("hunter22")
    assert stored.startswith("scrypt$")
    assert verify_password("hunter22", stored)
    assert not verify_password("hunter23", stored)
    assert not verify_password("hunter22", None)
    assert not verify_password("hunter22", "garbage")


def test_single_user_mode_needs_no_login(client: TestClient) -> None:
    status = client.get("/api/auth/status").json()
    assert status == {
        "mode": "single",
        "setup_required": False,
        "registration_open": False,
        "user": None,
    }
    assert client.get("/api/games").status_code == 200
    assert client.post("/api/auth/login", json=ADMIN).status_code == 409


def test_setup_then_login_claims_the_implicit_account(anon: TestClient) -> None:
    status = anon.get("/api/auth/status").json()
    assert status["mode"] == "multi" and status["setup_required"] is True
    locked = anon.get("/api/games")
    assert locked.status_code == 401
    assert locked.json()["error"]["code"] == "unauthorized"

    created = anon.post("/api/auth/setup", json=ADMIN)
    assert created.status_code == 201, created.text
    me = anon.get("/api/auth/me").json()
    assert me["username"] == "koy" and me["is_admin"] is True
    assert anon.get("/api/auth/status").json()["setup_required"] is False
    assert anon.get("/api/games").status_code == 200

    # The implicit "player" row was claimed, not duplicated.
    users = anon.get("/api/users").json()
    assert [u["username"] for u in users] == ["koy"]

    again = anon.post("/api/auth/setup", json=BOB)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "setup_complete"


def test_login_logout_and_wrong_password(multi_app: FastAPI, admin: TestClient) -> None:
    fresh = TestClient(multi_app)
    bad = fresh.post("/api/auth/login", json={**ADMIN, "password": "nope-nope-nope"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"
    assert fresh.get("/api/auth/me").status_code == 401

    ok = fresh.post("/api/auth/login", json=ADMIN)
    assert ok.status_code == 200
    assert "retroweb_session" in fresh.cookies
    assert fresh.get("/api/auth/me").json()["username"] == "koy"

    assert fresh.post("/api/auth/logout").status_code == 204
    assert fresh.get("/api/auth/me").status_code == 401


def test_registration_is_closed_unless_enabled(
    multi_app: FastAPI, admin: TestClient, settings: Settings
) -> None:
    closed = TestClient(multi_app).post("/api/auth/register", json=BOB)
    assert closed.status_code == 403
    assert closed.json()["error"]["code"] == "registration_closed"

    open_settings = settings.model_copy(
        update={"single_user_mode": False, "allow_registration": True}
    )
    multi_app.dependency_overrides[settings_dep] = lambda: open_settings
    with TestClient(multi_app) as client:
        assert client.get("/api/auth/status").json()["registration_open"] is True
        joined = client.post("/api/auth/register", json=BOB)
        assert joined.status_code == 201, joined.text
        assert joined.json()["is_admin"] is False
        dup = client.post("/api/auth/register", json=BOB)
        assert dup.status_code == 409
        assert dup.json()["error"]["code"] == "username_taken"


def test_regular_users_cannot_manage_the_library(bob: TestClient, data_dir: Path) -> None:
    for call in (
        lambda: bob.post("/api/games/scan"),
        lambda: bob.post("/api/library/scan"),
        lambda: bob.post("/api/library/covers/fetch"),
        lambda: bob.get("/api/users"),
        lambda: bob.post("/api/users", json={"username": "eve", "password": "eve-password-1"}),
        lambda: bob.post(
            "/api/bios/ps1", files={"file": ("scph1001.bin", b"x" * 16, "application/octet-stream")}
        ),
    ):
        response = call()
        assert response.status_code == 403, response.text
        assert response.json()["error"]["code"] == "forbidden"
    # Reading and playing are open to everyone signed in.
    assert bob.get("/api/games").status_code == 200
    assert bob.get("/api/bios").status_code == 200


def test_favorites_and_saves_are_per_user(
    admin: TestClient, bob: TestClient, data_dir: Path
) -> None:
    (data_dir / "roms" / "gba" / "Shared Game (USA).gba").write_bytes(make_gba_rom(b"shared"))
    assert admin.post("/api/games/scan").status_code == 200
    game_id = admin.get("/api/games").json()["items"][0]["id"]

    assert admin.post(f"/api/games/{game_id}/favorite", json={"favorite": True}).json()["favorite"]
    assert bob.get(f"/api/games/{game_id}").json()["favorite"] is False
    assert bob.get("/api/games", params={"favorite": "true"}).json()["total"] == 0
    assert admin.get("/api/library/home").json()["favorites"][0]["id"] == game_id
    assert bob.get("/api/library/home").json()["favorites"] == []

    upload = bob.post(
        f"/api/games/{game_id}/saves",
        data={"save_type": "battery", "slot": "0", "emulator_id": "test"},
        files={"file": ("battery.sav", b"bobs progress", "application/octet-stream")},
    )
    assert upload.status_code == 201, upload.text
    assert admin.get(f"/api/games/{game_id}/saves").json() == []
    assert len(bob.get(f"/api/games/{game_id}/saves").json()) == 1
    save_id = upload.json()["id"]
    assert admin.get(f"/api/saves/{save_id}").status_code == 404


def test_admin_manages_users(multi_app: FastAPI, admin: TestClient, bob: TestClient) -> None:
    users = admin.get("/api/users").json()
    assert [(u["username"], u["is_admin"]) for u in users] == [("koy", True), ("bob", False)]
    bob_id = next(u["id"] for u in users if u["username"] == "bob")
    me_id = next(u["id"] for u in users if u["username"] == "koy")

    # Password reset by the admin signs bob in with the new password only.
    reset = admin.patch(f"/api/users/{bob_id}", json={"password": "new-bob-password"})
    assert reset.status_code == 200, reset.text
    assert TestClient(multi_app).post("/api/auth/login", json=BOB).status_code == 401
    assert (
        TestClient(multi_app)
        .post("/api/auth/login", json={**BOB, "password": "new-bob-password"})
        .status_code
        == 200
    )

    assert admin.patch(f"/api/users/{me_id}", json={"is_admin": False}).status_code == 422
    assert admin.delete(f"/api/users/{me_id}").status_code == 422
    assert admin.delete(f"/api/users/{bob_id}").status_code == 204
    assert bob.get("/api/auth/me").status_code == 401  # session gone with the account
    assert [u["username"] for u in admin.get("/api/users").json()] == ["koy"]


def test_change_own_password(multi_app: FastAPI, admin: TestClient) -> None:
    wrong = admin.patch(
        "/api/auth/password", json={"current_password": "x", "new_password": "another-pass-1"}
    )
    assert wrong.status_code == 401
    short = admin.patch(
        "/api/auth/password",
        json={"current_password": ADMIN["password"], "new_password": "short"},
    )
    assert short.status_code == 422
    ok = admin.patch(
        "/api/auth/password",
        json={"current_password": ADMIN["password"], "new_password": "another-pass-1"},
    )
    assert ok.status_code == 200, ok.text
    fresh = TestClient(multi_app)
    assert fresh.post("/api/auth/login", json=ADMIN).status_code == 401
    assert (
        fresh.post("/api/auth/login", json={**ADMIN, "password": "another-pass-1"}).status_code
        == 200
    )


def test_username_rules(admin: TestClient) -> None:
    bad = admin.post("/api/users", json={"username": "no spaces", "password": "long-enough-1"})
    assert bad.status_code == 422
    taken = admin.post("/api/users", json={"username": "KOY", "password": "long-enough-1"})
    assert taken.status_code == 409
