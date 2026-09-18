from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote

import httpx
from fastapi.testclient import TestClient

from retroweb.api.deps import settings_dep
from retroweb.core.config import Settings
from retroweb.library.artwork import (
    best_match,
    normalize_title,
    parse_index,
    thumbnail_name,
    thumbnail_path,
)
from retroweb.library.systems import GameSystem
from retroweb.main import create_app
from retroweb.services.artwork import ArtworkFetcher
from tests.conftest import make_gba_rom, wait_for_job

PNG = b"\x89PNG\r\n\x1a\nfake image"
GBA_DIR = "/Nintendo - Game Boy Advance/Named_Boxarts/"


# -- pure name logic --------------------------------------------------------


def test_thumbnail_name_applies_retroarch_substitutions() -> None:
    assert thumbnail_name("Pokemon - Emerald Version (USA, Europe).gba") == (
        "Pokemon - Emerald Version (USA, Europe)"
    )
    assert thumbnail_name("Ratchet & Clank: Size Matters (USA).iso") == (
        "Ratchet _ Clank_ Size Matters (USA)"
    )
    assert thumbnail_path(GameSystem.GBA, "A Game (USA)") == (
        "/Nintendo%20-%20Game%20Boy%20Advance/Named_Boxarts/A%20Game%20%28USA%29.png"
    )


def test_parse_index_skips_navigation_links() -> None:
    html = apache_index(["Alpha (USA)", "Beta & Gamma (Japan)"])
    assert parse_index(html) == ["Alpha (USA)", "Beta & Gamma (Japan)"]


def test_normalize_title_drops_tags_and_punctuation() -> None:
    assert normalize_title("Sonic The Hedgehog (USA, Europe) [!]") == "sonic the hedgehog"
    assert normalize_title("Final Fantasy VII (USA) (Disc 1)") == "final fantasy vii"


def test_best_match_prefers_region_and_avoids_betas() -> None:
    index = [
        "Monster Hunter Freedom (USA)",
        "Monster Hunter Freedom Unite (Europe) (En,Fr,De,Es,It) (v1.01)",
        "Monster Hunter Freedom Unite (Japan) (Beta)",
        "Monster Hunter Freedom Unite (USA) (En,Fr,De,Es,It)",
    ]
    assert best_match("Monster Hunter Freedom Unite (USA)", index) == (
        "Monster Hunter Freedom Unite (USA) (En,Fr,De,Es,It)"
    )
    assert best_match("Monster Hunter Freedom Unite (Europe)", index) == (
        "Monster Hunter Freedom Unite (Europe) (En,Fr,De,Es,It) (v1.01)"
    )
    # No region at all: the plainest non-beta entry wins.
    assert best_match("Monster Hunter Freedom Unite", index) == (
        "Monster Hunter Freedom Unite (USA) (En,Fr,De,Es,It)"
    )
    # A beta of the right region still beats another region's retail release...
    assert best_match("Monster Hunter Freedom Unite (Japan)", index) == (
        "Monster Hunter Freedom Unite (Japan) (Beta)"
    )
    # ...but never the retail release of the same region.
    assert best_match("Sonic (USA)", ["Sonic (USA) (Beta)", "Sonic (USA)"]) == "Sonic (USA)"
    assert best_match("Nothing Here (USA)", index) is None
    assert best_match("(USA)", index) is None


# -- fetching ---------------------------------------------------------------


def apache_index(names: list[str]) -> str:
    rows = "".join(
        f'<tr><td><a href="{quote(name + ".png", safe="")}">{name}.png</a></td></tr>'
        for name in names
    )
    return (
        "<html><body><h1>Index of /x</h1><table>"
        '<tr><th><a href="?C=N;O=D">Name</a></th></tr>'
        '<tr><td><a href="/Nintendo%20-%20Game%20Boy%20Advance/">Parent Directory</a></td></tr>'
        f"{rows}</table></body></html>"
    )


def thumbnail_server(available: dict[str, bytes]) -> httpx.MockTransport:
    """Behaves like thumbnails.libretro.com for the GBA box art directory."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)
        if path == GBA_DIR:
            return httpx.Response(
                200, text=apache_index(sorted(available)), headers={"content-type": "text/html"}
            )
        if path.startswith(GBA_DIR) and path.endswith(".png"):
            name = path[len(GBA_DIR) : -len(".png")]
            if name in available:
                return httpx.Response(
                    200, content=available[name], headers={"content-type": "image/png"}
                )
        return httpx.Response(404, text="not found", headers={"content-type": "text/html"})

    return httpx.MockTransport(handler)


def install_fetcher(
    client: TestClient, settings: Settings, transport: httpx.BaseTransport
) -> ArtworkFetcher:
    fetcher = ArtworkFetcher(settings, transport=transport)
    client.app.state.artwork = fetcher  # type: ignore[attr-defined]
    return fetcher


def test_fetch_cover_exact_name(
    client: TestClient,
    settings: Settings,
    data_dir: Path,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    install_fetcher(client, settings, thumbnail_server({"Test Game (USA) (Rev 1)": PNG}))
    response = client.post(f"/api/games/{scanned_game['id']}/cover/fetch")
    assert response.status_code == 200, response.text
    assert response.json()["has_cover"] is True
    assert (data_dir / "covers" / f"{scanned_game['id']}.png").read_bytes() == PNG
    cover = client.get(f"/api/games/{scanned_game['id']}/cover")
    assert cover.status_code == 200
    assert cover.headers["content-type"] == "image/png"


def test_fetch_cover_falls_back_to_the_index(
    client: TestClient,
    settings: Settings,
    data_dir: Path,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    server = {"Test Game (Japan)": b"japan", "Test Game (USA)": PNG, "Other (USA)": b"x"}
    install_fetcher(client, settings, thumbnail_server(server))
    response = client.post(f"/api/games/{scanned_game['id']}/cover/fetch")
    assert response.status_code == 200, response.text
    assert (data_dir / "covers" / f"{scanned_game['id']}.png").read_bytes() == PNG


def test_fetch_cover_not_found(
    client: TestClient,
    settings: Settings,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    install_fetcher(client, settings, thumbnail_server({"Other (USA)": b"x"}))
    response = client.post(f"/api/games/{scanned_game['id']}/cover/fetch")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "cover_not_found"
    assert client.get(f"/api/games/{scanned_game['id']}").json()["has_cover"] is False


def test_fetch_cover_source_unreachable(
    client: TestClient,
    settings: Settings,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    install_fetcher(client, settings, httpx.MockTransport(down))
    response = client.post(f"/api/games/{scanned_game['id']}/cover/fetch")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "metadata_unavailable"


def test_fetch_missing_covers_job(
    client: TestClient, settings: Settings, data_dir: Path, rom_file: Path
) -> None:
    (data_dir / "roms" / "gba" / "Unknown Thing (Europe).gba").write_bytes(make_gba_rom(b"u"))
    assert client.post("/api/games/scan").status_code == 200
    install_fetcher(client, settings, thumbnail_server({"Test Game (USA)": PNG}))

    started = client.post("/api/library/covers/fetch")
    assert started.status_code == 202, started.text
    job_id = started.json()["id"]
    job = wait_for_job(client, job_id)
    assert job["status"] == "done", job
    assert job["total"] == 2
    assert job["done"] == 2
    assert job["counters"] == {"fetched": 1, "not_found": 1}
    assert job["errors"] == []

    games = client.get("/api/games").json()["items"]
    by_title = {game["title"]: game["has_cover"] for game in games}
    assert by_title == {"Test Game": True, "Unknown Thing": False}
    assert client.get("/api/library/jobs").json()[0]["id"] == job_id

    # A second run only looks at games still without a cover.
    again = wait_for_job(client, client.post("/api/library/covers/fetch").json()["id"])
    assert again["total"] == 1
    assert again["counters"] == {"not_found": 1}


def test_online_metadata_can_be_disabled(settings: Settings) -> None:
    offline = settings.model_copy(update={"online_metadata": False})
    app = create_app(offline)
    app.dependency_overrides[settings_dep] = lambda: offline
    with TestClient(app) as client:
        response = client.post("/api/library/covers/fetch")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "feature_disabled"
        assert client.get("/api/library/jobs/nope").status_code == 404
