from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from retroweb.core.database import get_session
from retroweb.models import PlaySession


def _rewind(session_id: str, seconds: int) -> None:
    """Pretend the session started ``seconds`` ago (tests cannot wait)."""
    for db in get_session():
        row = db.scalar(select(PlaySession).where(PlaySession.id == session_id))
        assert row is not None
        row.started_at -= timedelta(seconds=seconds)
        row.last_heartbeat_at -= timedelta(seconds=seconds)
        db.commit()


def test_session_lifecycle(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    game_id = scanned_game["id"]
    started = client.post(
        "/api/play-sessions",
        json={"game_id": game_id, "emulator_id": "emulatorjs", "device": "test"},
    )
    assert started.status_code == 201, started.text
    session = started.json()
    assert session["ended_at"] is None
    assert session["heartbeat_interval_seconds"] > 0

    _rewind(session["id"], 300)
    beat = client.patch(f"/api/play-sessions/{session['id']}", json={"action": "heartbeat"})
    assert beat.status_code == 200

    ended = client.patch(f"/api/play-sessions/{session['id']}", json={"action": "end"})
    assert ended.status_code == 200
    body = ended.json()
    assert body["ended_at"] is not None
    assert 295 <= body["duration_seconds"] <= 305

    again = client.patch(f"/api/play-sessions/{session['id']}", json={"action": "end"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "session_already_ended"

    detail = client.get(f"/api/games/{game_id}").json()
    assert 295 <= detail["play_time_seconds"] <= 305
    assert detail["last_played_at"] is not None

    recent = client.get("/api/play-sessions/recent").json()
    assert recent[0]["game"]["id"] == game_id


def test_client_cannot_inflate_play_time(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    """A session abandoned without heartbeats is capped at heartbeat + grace."""
    session = client.post("/api/play-sessions", json={"game_id": scanned_game["id"]}).json()
    _rewind(session["id"], 3600)  # started an hour ago, last heartbeat an hour ago
    ended = client.patch(f"/api/play-sessions/{session['id']}", json={"action": "end"}).json()
    # grace is 60 s in the test settings
    assert ended["duration_seconds"] <= 61


def test_starting_new_session_closes_previous(client: TestClient, scanned_game: dict) -> None:  # type: ignore[type-arg]
    first = client.post("/api/play-sessions", json={"game_id": scanned_game["id"]}).json()
    client.post("/api/play-sessions", json={"game_id": scanned_game["id"]})
    beat = client.patch(f"/api/play-sessions/{first['id']}", json={"action": "heartbeat"})
    assert beat.status_code == 409


def test_unknown_game_or_session(client: TestClient) -> None:
    assert client.post("/api/play-sessions", json={"game_id": "nope"}).status_code == 404
    assert client.patch("/api/play-sessions/nope", json={"action": "end"}).status_code == 404
