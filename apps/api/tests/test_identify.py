from __future__ import annotations

import hashlib
import zlib
from pathlib import Path
from urllib.parse import unquote

import httpx
from fastapi.testclient import TestClient

from retroweb.core.config import Settings
from retroweb.library.datfile import parse_dat
from retroweb.library.romid import fingerprint
from retroweb.library.systems import GameSystem
from retroweb.models import Game
from retroweb.services.identify import GameIdentifier
from tests.conftest import make_gba_rom, wait_for_job
from tests.test_artwork import PNG, install_fetcher, thumbnail_server

GBA_DAT = "/metadat/no-intro/Nintendo - Game Boy Advance.dat"


def digests(data: bytes) -> tuple[str, str]:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08X}", hashlib.sha1(data).hexdigest().upper()  # noqa: S324


def gba_rom_with_serial(serial: bytes, seed: bytes = b"serial-rom") -> bytes:
    data = bytearray(make_gba_rom(seed))
    data[0xAC:0xB0] = serial
    return bytes(data)


def dat_entry(name: str, data: bytes | None, *, serial: str = "", region: str = "USA") -> str:
    crc, sha1 = digests(data) if data is not None else ("00000000", "0" * 40)
    serial_part = f' serial "{serial}"' if serial else ""
    digest_part = f"crc {crc} md5 {'0' * 32} sha1 {sha1}{serial_part}"
    return (
        f'game (\n\tname "{name}"\n\tregion "{region}"\n'
        + (f'\tserial "{serial}"\n' if serial else "")
        + f'\trom ( name "{name}.gba" size 4096 {digest_part} )\n)\n'
    )


def attribute_dat(attribute: str, value: str, data: bytes) -> str:
    crc, _ = digests(data)
    return f'game (\n\tcomment "x"\n\t{attribute} "{value}"\n\trom ( crc {crc} )\n)\n'


def attribute_path(attribute: str) -> str:
    return f"/metadat/{attribute}/Nintendo - Game Boy Advance.dat"


HEADER = 'clrmamepro (\n\tname "Nintendo - Game Boy Advance"\n\tversion "test"\n)\n\n'


def game_database(files: dict[str, str], hits: list[str] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = unquote(request.url.path)
        if hits is not None:
            hits.append(path)
        if path in files:
            return httpx.Response(200, text=files[path])
        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler)


def install_identifier(
    client: TestClient, settings: Settings, transport: httpx.BaseTransport
) -> GameIdentifier:
    identifier = GameIdentifier(settings, transport=transport)
    client.app.state.identifier = identifier  # type: ignore[attr-defined]
    return identifier


# -- DAT parsing --------------------------------------------------------------


def test_parse_dat_reads_names_digests_and_serials() -> None:
    text = HEADER + dat_entry('Tricky (Name) "Quoted\\" (USA, Europe)', b"abc", serial="ABCE")
    games = parse_dat(text.replace('"Quoted\\"', '\\"Quoted\\"'))
    assert len(games) == 1
    game = games[0]
    assert game.name == 'Tricky (Name) "Quoted" (USA, Europe)'
    assert game.region == "USA"
    assert game.serial == "ABCE"
    crc, sha1 = digests(b"abc")
    assert (game.roms[0].crc, game.roms[0].sha1, game.roms[0].size) == (crc, sha1, 4096)


def test_parse_dat_accepts_unquoted_values_and_attribute_blocks() -> None:
    arcade = (
        'game (\n\tname "Street Brawler (World)"\n\treleaseyear "1991"\n\tpublisher "Acme"\n'
        "\trom ( name sbrawl.zip size 123 crc 1a2b3c4d md5 00 sha1 abcdef )\n)\n"
    )
    game = parse_dat(arcade)[0]
    assert game.roms[0].name == "sbrawl.zip"
    assert game.roms[0].crc == "1A2B3C4D"
    assert game.attributes == {"releaseyear": "1991", "publisher": "Acme"}

    attribute = parse_dat(attribute_dat("developer", "Hudson Soft", b"abc"))[0]
    assert attribute.attributes == {"developer": "Hudson Soft"}
    assert attribute.roms[0].crc == digests(b"abc")[0]


# -- fingerprints ---------------------------------------------------------------


def chunked(data: bytes, size: int = 1000) -> list[bytes]:
    return [data[i : i + size] for i in range(0, len(data), size)]


def test_fingerprint_removes_nes_and_copier_headers() -> None:
    body = bytes(range(256)) * 64
    nes = b"NES\x1a" + b"\0" * 12 + body
    print_ = fingerprint(GameSystem.NES, chunked(nes, 7), len(nes))
    assert (print_.crc32, print_.sha1) == digests(body)
    assert print_.size == len(body)

    smc = b"\0" * 512 + body
    print_ = fingerprint(GameSystem.SNES, chunked(smc, 100), len(smc))
    assert (print_.crc32, print_.sha1) == digests(body)
    # A headerless .sfc is hashed as it is.
    assert fingerprint(GameSystem.SNES, [body], len(body)).sha1 == digests(body)[1]


def test_fingerprint_normalises_n64_byte_order() -> None:
    z64 = bytearray(b"\x80\x37\x12\x40" + bytes(range(60)) * 17)
    z64[0x3B:0x3F] = b"NSME"
    z64 = bytes(z64[: len(z64) - len(z64) % 4])
    v64 = b"".join(bytes((z64[i + 1], z64[i])) for i in range(0, len(z64), 2))
    n64 = b"".join(z64[i : i + 4][::-1] for i in range(0, len(z64), 4))
    expected = digests(z64)
    for image in (z64, v64, n64):
        print_ = fingerprint(GameSystem.N64, chunked(image, 333), len(image))
        assert (print_.crc32, print_.sha1) == expected
        assert print_.serial == "NSME"


def test_fingerprint_reads_cartridge_and_disc_serials() -> None:
    gba = gba_rom_with_serial(b"ABSE")
    assert fingerprint(GameSystem.GBA, chunked(gba), len(gba)).serial == "ABSE"
    # Garbage where the game code should be is not a serial.
    assert fingerprint(GameSystem.GBA, [make_gba_rom(b"\x01\x02")], 4096).serial is None

    ps1 = b"\0" * 5000 + b"BOOT = cdrom:\\SLUS_012.34;1\r\nTCB = 4\r\n" + b"\0" * 100
    assert fingerprint(GameSystem.PS1, chunked(ps1), len(ps1)).serial == "SLUS-01234"
    ps2_style = b"\0" * 10 + b"BOOT2 = cdrom0:\\SCES_987.65;1" + b"\0" * 10
    assert fingerprint(GameSystem.PS1, [ps2_style], len(ps2_style)).serial == "SCES-98765"

    psp = b"\0" * 9000 + b"ULUS-10041|0123456789ABCDEF|0001|G" + b"\0" * 50
    assert fingerprint(GameSystem.PSP, chunked(psp), len(psp)).serial == "ULUS-10041"


# -- identification ---------------------------------------------------------------


def test_identify_by_digest_fills_metadata(
    client: TestClient,
    settings: Settings,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    rom = make_gba_rom()
    database = {
        GBA_DAT: HEADER
        + dat_entry("Some Other Game (Japan)", b"other", region="Japan")
        + dat_entry("Test Game Deluxe (USA, Europe) (Rev 1)", rom),
        attribute_path("developer"): attribute_dat("developer", "Dev", rom),
        attribute_path("publisher"): attribute_dat("publisher", "Pub", rom),
        attribute_path("releaseyear"): attribute_dat("releaseyear", "2003", rom),
        attribute_path("releasemonth"): attribute_dat("releasemonth", "11", rom),
    }
    install_identifier(client, settings, game_database(database))

    response = client.post(f"/api/games/{scanned_game['id']}/identify")
    assert response.status_code == 200, response.text
    game = response.json()
    assert game["canonical_name"] == "Test Game Deluxe (USA, Europe) (Rev 1)"
    assert game["identified_by"] == "hash"
    assert game["title"] == "Test Game"  # the user's own title is kept
    assert game["title_en"] == "Test Game Deluxe"
    assert (game["developer"], game["publisher"]) == ("Dev", "Pub")
    assert game["release_date"] == "2003-11-01"
    crc, sha1 = digests(rom)
    assert (game["files"][0]["crc32"], game["files"][0]["sha1"]) == (crc, sha1)


def test_identify_keeps_fields_the_user_filled_in(
    client: TestClient,
    settings: Settings,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    rom = make_gba_rom()
    install_identifier(
        client,
        settings,
        game_database(
            {
                GBA_DAT: HEADER + dat_entry("Test Game (USA)", rom),
                attribute_path("developer"): attribute_dat("developer", "Database Dev", rom),
            }
        ),
    )
    client.patch(f"/api/games/{scanned_game['id']}", json={"developer": "My Dev"})
    game = client.post(f"/api/games/{scanned_game['id']}/identify").json()
    assert game["developer"] == "My Dev"


def test_translated_rom_is_identified_by_serial_and_gets_its_cover(
    client: TestClient, settings: Settings, data_dir: Path
) -> None:
    translated = gba_rom_with_serial(b"ABSE", seed=b"patched")
    name = "炸弹人锦标赛[group](AI)(64Mb).gba"
    (data_dir / "roms" / "gba" / name).write_bytes(translated)
    assert client.post("/api/games/scan").status_code == 200
    game_id = client.get("/api/games").json()["items"][0]["id"]

    original = b"the untouched dump"
    database = {
        GBA_DAT: HEADER
        + dat_entry("Bomberman Tournament (USA, Europe) (Beta)", b"beta", serial="ABSE")
        + dat_entry("Bomberman Tournament (USA, Europe)", original, serial="ABSE")
        + dat_entry("Bookworm (USA)", b"book", serial="BKWE"),
    }
    install_identifier(client, settings, game_database(database))
    install_fetcher(client, settings, thumbnail_server({"Bomberman Tournament (USA, Europe)": PNG}))

    job = wait_for_job(client, client.post("/api/library/covers/fetch").json()["id"])
    assert job["status"] == "done", job
    assert job["counters"] == {"fetched": 1}

    game = client.get(f"/api/games/{game_id}").json()
    assert game["canonical_name"] == "Bomberman Tournament (USA, Europe)"
    assert game["identified_by"] == "serial"
    assert game["title_en"] == "Bomberman Tournament"
    assert game["title_zh"] == game["title"]
    assert game["region"] == "USA, Europe"
    assert game["files"][0]["serial"] == "ABSE"
    assert game["has_cover"] is True
    assert (data_dir / "covers" / f"{game_id}.png").read_bytes() == PNG


def test_identify_by_name_when_content_is_unknown(
    client: TestClient,
    settings: Settings,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    database = {
        GBA_DAT: HEADER
        + dat_entry("Test Game (Japan)", b"jp", region="Japan")
        + dat_entry("Test Game (USA) (Rev 1)", b"us"),
    }
    install_identifier(client, settings, game_database(database))
    game = client.post(f"/api/games/{scanned_game['id']}/identify").json()
    assert game["canonical_name"] == "Test Game (USA) (Rev 1)"
    assert game["identified_by"] == "name"


def test_unknown_game_reports_not_identified_and_keeps_digests(
    client: TestClient,
    settings: Settings,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    install_identifier(
        client, settings, game_database({GBA_DAT: HEADER + dat_entry("Else (USA)", b"e")})
    )
    response = client.post(f"/api/games/{scanned_game['id']}/identify")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "game_not_identified"
    game = client.get(f"/api/games/{scanned_game['id']}").json()
    assert game["canonical_name"] is None
    assert game["files"][0]["sha1"] == digests(make_gba_rom())[1]


def test_identify_library_job_counts_outcomes(
    client: TestClient, settings: Settings, data_dir: Path, rom_file: Path
) -> None:
    (data_dir / "roms" / "gba" / "Mystery.gba").write_bytes(make_gba_rom(b"mystery"))
    assert client.post("/api/games/scan").status_code == 200
    install_identifier(
        client,
        settings,
        game_database({GBA_DAT: HEADER + dat_entry("Test Game (USA)", make_gba_rom())}),
    )
    job = wait_for_job(client, client.post("/api/library/identify").json()["id"])
    assert job["status"] == "done", job
    assert job["counters"] == {"hash": 1, "not_found": 1}
    # Identified games are skipped next time; the unknown one is tried again.
    job = wait_for_job(client, client.post("/api/library/identify").json()["id"])
    assert (job["total"], job["counters"]) == (1, {"not_found": 1})
    job = wait_for_job(client, client.post("/api/library/identify?force=true").json()["id"])
    assert job["total"] == 2


def test_database_is_cached_on_disk_and_survives_an_outage(
    client: TestClient,
    settings: Settings,
    data_dir: Path,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    hits: list[str] = []
    database = {GBA_DAT: HEADER + dat_entry("Test Game (USA)", make_gba_rom())}
    install_identifier(client, settings, game_database(database, hits))
    assert client.post(f"/api/games/{scanned_game['id']}/identify").status_code == 200
    assert hits.count(GBA_DAT) == 1
    assert list((data_dir / "cache" / "gamedb").glob("no-intro__*.dat"))

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    # A new process (empty memory cache) with the network gone: the disk copy serves.
    install_identifier(client, settings, httpx.MockTransport(down))
    response = client.post(f"/api/games/{scanned_game['id']}/identify")
    assert response.status_code == 200, response.text


def test_database_unreachable_without_a_cache(
    client: TestClient,
    settings: Settings,
    scanned_game: dict,  # type: ignore[type-arg]
) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    install_identifier(client, settings, httpx.MockTransport(down))
    response = client.post(f"/api/games/{scanned_game['id']}/identify")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "metadata_unavailable"
    # The cover lookup still works from the file name alone.
    install_fetcher(client, settings, thumbnail_server({"Test Game (USA) (Rev 1)": PNG}))
    assert client.post(f"/api/games/{scanned_game['id']}/cover/fetch").status_code == 200


def test_identification_respects_the_online_switch(
    settings: Settings,
    rom_file: Path,
) -> None:
    from retroweb.api.deps import settings_dep
    from retroweb.main import create_app

    offline = settings.model_copy(update={"online_metadata": False})
    app = create_app(offline)
    app.dependency_overrides[settings_dep] = lambda: offline
    with TestClient(app) as offline_client:
        assert offline_client.post("/api/games/scan").status_code == 200
        game_id = offline_client.get("/api/games").json()["items"][0]["id"]
        for path in (f"/api/games/{game_id}/identify", "/api/library/identify"):
            response = offline_client.post(path)
            assert response.json()["error"]["code"] == "feature_disabled", response.text


def test_bare_catalogue_code_title_is_replaced_by_the_release_name(
    client: TestClient, settings: Settings, data_dir: Path
) -> None:
    rom = make_gba_rom(b"code-named")
    (data_dir / "roms" / "gba" / "2728.gba").write_bytes(rom)
    assert client.post("/api/games/scan").status_code == 200
    game_id = client.get("/api/games").json()["items"][0]["id"]
    install_identifier(
        client, settings, game_database({GBA_DAT: HEADER + dat_entry("Real Name (USA)", rom)})
    )
    game = client.post(f"/api/games/{game_id}/identify").json()
    assert game["title"] == "Real Name"
    assert game["title_en"] == "Real Name"


def test_probe_only_fingerprint_reads_the_head_and_skips_digests() -> None:
    consumed: list[int] = []

    def chunks():  # type: ignore[no-untyped-def]
        payload = b"\0" * 9000 + b"ULUS-10041|0123456789ABCDEF|0001|G" + b"\0" * 50
        for i in range(0, 64 * 1024 * 1024, 1024 * 1024):
            consumed.append(i)
            yield payload if i == 0 else b"\0" * (1024 * 1024)

    print_ = fingerprint(GameSystem.PSP, chunks(), 64 * 1024 * 1024, probe_only=True)
    assert print_.serial == "ULUS-10041"
    assert print_.sha1 is None and print_.crc32 is None
    assert len(consumed) <= 9  # stopped after the 8 MB probe, not the whole image


def make_cso(image: bytes, block_size: int = 2048) -> bytes:
    """A minimal CSO container: zlib raw-deflate blocks, one index entry per block."""
    import struct
    import zlib as _zlib

    blocks = [image[i : i + block_size] for i in range(0, len(image), block_size)]
    header = struct.pack("<4sIQIBBH", b"CISO", 24, len(image), block_size, 1, 0, 0)
    index_size = 4 * (len(blocks) + 1)
    data = b""
    entries: list[int] = []
    for block in blocks:
        compressed = _zlib.compress(block, 9)[2:-4]  # raw deflate
        entries.append(24 + index_size + len(data))
        data += compressed
    entries.append(24 + index_size + len(data))
    return header + struct.pack(f"<{len(entries)}I", *entries) + data


def test_cso_images_are_probed_after_decompression() -> None:
    image = b"\0" * 4000 + b"UCUS-98737|0123456789ABCDEF|0001|G" + b"\0" * 3000
    cso = make_cso(image)
    assert cso[:4] == b"CISO"
    print_ = fingerprint(GameSystem.PSP, [cso], len(cso), probe_only=True)
    assert print_.serial == "UCUS-98737"


def test_extra_name_lists_are_merged_into_the_index(
    client: TestClient, settings: Settings, data_dir: Path
) -> None:
    image = b"\0" * 4000 + b"NPJH-50654|0123456789ABCDEF|0001|G" + b"\0" * 3000
    (data_dir / "roms" / "psp").mkdir()
    (data_dir / "roms" / "psp" / "Some PSN Game.iso").write_bytes(image)
    assert client.post("/api/games/scan").status_code == 200
    game_id = client.get("/api/games?system=psp").json()["items"][0]["id"]
    psn = (
        'game (\n\tname "PSN Game (Japan)"\n\tregion "Japan"\n\tserial "NPJH-50654"\n'
        '\trom ( name "PSN Game (Japan).iso" size 1 crc 00000001 md5 00 sha1 00'
        ' serial "NPJH-50654" )\n)\n'
    )
    hits: list[str] = []
    install_identifier(
        client,
        settings,
        game_database({"/metadat/no-intro/Sony - PlayStation Portable (PSN).dat": psn}, hits),
    )
    game = client.post(f"/api/games/{game_id}/identify").json()
    assert game["canonical_name"] == "PSN Game (Japan)"
    assert game["identified_by"] == "serial"
    assert "/metadat/redump/Sony - PlayStation Portable.dat" in hits


def make_sfo(entries: dict[bytes, bytes]) -> bytes:
    import struct as _struct

    keys = b"".join(k + b"\0" for k in entries)
    key_table = 20 + 16 * len(entries)
    data_table = key_table + len(keys)
    data_table += (-data_table) % 4
    index = b""
    data = b""
    key_offset = 0
    for key, value in entries.items():
        value = value + b"\0"
        index += _struct.pack("<HHIII", key_offset, 0x0204, len(value), len(value), len(data))
        key_offset += len(key) + 1
        data += value
    header = _struct.pack("<IIIII", 0x46535000, 0x0101, key_table, data_table, len(entries))
    return header + index + keys.ljust(data_table - key_table, b"\0") + data


def test_psp_serial_falls_back_to_param_sfo_disc_id() -> None:
    sfo = make_sfo({b"CATEGORY": b"UG", b"DISC_ID": b"UCJS10041", b"TITLE": b"Miku"})
    iso = b"\0" * 3000 + b"PARAM.SFO" + b"\0" * 5000 + sfo + b"\0" * 2000
    print_ = fingerprint(GameSystem.PSP, [iso], len(iso), probe_only=True)
    assert print_.serial == "UCJS-10041"
    # A PBP package: the SFO is what the header points at.
    pbp = b"\0PBP" + b"\0" * 36 + sfo
    assert fingerprint(GameSystem.PSP, [pbp], len(pbp), probe_only=True).serial == "UCJS-10041"


def test_cso_with_zero_header_size_field_is_decoded() -> None:
    import struct as _struct

    image = b"\0" * 4000 + b"NPUX-80431|0123456789ABCDEF|0001|G" + b"\0" * 3000
    cso = bytearray(make_cso(image))
    _struct.pack_into("<I", cso, 4, 0)  # header_size = 0, as several tools write it
    assert (
        fingerprint(GameSystem.PSP, [bytes(cso)], len(cso), probe_only=True).serial == "NPUX-80431"
    )


def test_attribute_lists_supply_names_for_releases_missing_from_the_main_lists(
    client: TestClient, settings: Settings, data_dir: Path
) -> None:
    image = b"\0" * 4000 + b"NPUX-80431|0123456789ABCDEF|0001|G" + b"\0" * 3000
    (data_dir / "roms" / "psp").mkdir()
    (data_dir / "roms" / "psp" / "SRHT.iso").write_bytes(image)
    assert client.post("/api/games/scan").status_code == 200
    game_id = client.get("/api/games?system=psp").json()["items"][0]["id"]
    developer = (
        'game (\n\tname "One Two Boat Racing (USA)"\n\tserial "NPUX-80431"\n\tdeveloper "Zallag"\n'
        '\trom ( serial "NPUX-80431" name "One Two Boat Racing (USA).cue" )\n)\n'
    )
    install_identifier(
        client,
        settings,
        game_database({"/metadat/developer/Sony - PlayStation Portable.dat": developer}),
    )
    game = client.post(f"/api/games/{game_id}/identify").json()
    assert game["canonical_name"] == "One Two Boat Racing (USA)"
    assert game["title"] == "One Two Boat Racing"  # a bare code title is replaced
    assert game["developer"] == "Zallag"


def test_known_digests_without_a_serial_get_the_head_probed_again(
    client: TestClient, settings: Settings, data_dir: Path
) -> None:
    image = b"\0" * 4000 + b"NPUX-80431|0123456789ABCDEF|0001|G" + b"\0" * 3000
    (data_dir / "roms" / "psp").mkdir()
    (data_dir / "roms" / "psp" / "boat.iso").write_bytes(image)
    assert client.post("/api/games/scan").status_code == 200
    game_id = client.get("/api/games?system=psp").json()["items"][0]["id"]
    # First pass with an empty database: digests are stored, nothing matches.
    install_identifier(client, settings, game_database({}))
    assert client.post(f"/api/games/{game_id}/identify").status_code == 404
    # Simulate an older probe that stored digests but no serial.
    from sqlalchemy import update

    from retroweb.core.database import get_session
    from retroweb.models import GameFile

    for db in get_session():
        db.execute(update(GameFile).where(GameFile.game_id == game_id).values(serial=None))
        db.commit()
    assert client.get(f"/api/games/{game_id}").json()["files"][0]["sha1"] is not None
    # A list appears later (the earlier 404s are cached, so drop that cache):
    # a plain (non-force) pass must still find the serial.
    import shutil

    shutil.rmtree(data_dir / "cache", ignore_errors=True)
    dat = 'game (\n\tname "Boat (USA)"\n\tserial "NPUX-80431"\n\trom ( serial "NPUX-80431" )\n)\n'
    install_identifier(
        client, settings, game_database({"/metadat/developer/Sony - PlayStation Portable.dat": dat})
    )
    from retroweb.services.identify import identify_game as _identify

    for db in get_session():
        game = db.get(Game, game_id)
        assert (
            _identify(db, client.app.state.storage, client.app.state.identifier, game) == "serial"
        )  # type: ignore[attr-defined]
        assert game.canonical_name == "Boat (USA)"


def test_attributes_are_found_by_release_name_for_serial_matches(
    client: TestClient, settings: Settings, data_dir: Path
) -> None:
    image = b"\0" * (300 * 1024 * 1024)  # above FULL_HASH_LIMIT: only the head is probed
    image = image[:4000] + b"ULJS-00480|0123456789ABCDEF|0001|G" + image[4000 + 34 :]
    (data_dir / "roms" / "psp").mkdir()
    (data_dir / "roms" / "psp" / "big.iso").write_bytes(image)
    assert client.post("/api/games/scan").status_code == 200
    game_id = client.get("/api/games?system=psp").json()["items"][0]["id"]

    def entry(extra: str, rom: str, name: str = "Big Game (Japan)") -> str:
        head = 'game (\n\tname "' + name + '"\n\tserial "ULJS-00480"\n'
        return head + extra + "\trom ( " + rom + " )\n)\n"

    main = entry("", 'name "Big Game (Japan).iso" size 1 crc 0000AAAA serial "ULJS-00480"')
    # The year list spells the name differently: it is matched by serial.
    year = entry('\treleaseyear "2011"\n', 'serial "ULJS-00480"', "Big Game (Japan) (v1.01)")
    dev = entry('\tdeveloper "Bandai"\n', 'serial "ULJS-00480"')
    install_identifier(
        client,
        settings,
        game_database(
            {
                "/metadat/redump/Sony - PlayStation Portable.dat": main,
                "/metadat/releaseyear/Sony - PlayStation Portable.dat": year,
                "/metadat/developer/Sony - PlayStation Portable.dat": dev,
            }
        ),
    )
    game = client.post(f"/api/games/{game_id}/identify").json()
    assert game["identified_by"] == "serial"
    assert game["files"][0]["sha1"] is None  # not hashed in full
    assert game["release_date"] == "2011-01-01"
    assert game["developer"] == "Bandai"
