from __future__ import annotations

from pathlib import Path

import pytest

from retroweb.storage import InvalidStorageKeyError, LocalStorageProvider, MountedStorage
from retroweb.storage.base import normalize_key


@pytest.mark.parametrize(
    "key",
    [
        "../secret",
        "/etc/passwd",
        "roms/../../etc/passwd",
        "roms\\..\\x",
        "C:/windows",
        "a\x00b",
        "",
    ],
)
def test_rejects_traversal_keys(tmp_path: Path, key: str) -> None:
    provider = LocalStorageProvider(tmp_path)
    with pytest.raises(InvalidStorageKeyError):
        provider.exists(key)


def test_symlink_escape_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("nope")
    try:
        (root / "link").symlink_to(outside)
    except OSError as exc:  # Windows needs a privilege or Developer Mode for symlinks
        pytest.skip(f"cannot create symlinks here: {exc}")
    provider = LocalStorageProvider(root)
    with pytest.raises(InvalidStorageKeyError):
        provider.read("link/secret.txt")


def test_normalize_key_collapses_dots_and_slashes() -> None:
    assert normalize_key("roms//gba/./game.gba") == "roms/gba/game.gba"


def test_write_read_stream_list(tmp_path: Path) -> None:
    provider = LocalStorageProvider(tmp_path)
    provider.write("gba/a.gba", b"0123456789")
    assert provider.read("gba/a.gba") == b"0123456789"
    assert provider.size("gba/a.gba") == 10
    assert b"".join(provider.stream("gba/a.gba", 2, 5)) == b"2345"
    assert b"".join(provider.stream("gba/a.gba", 8, 100)) == b"89"
    assert [obj.key for obj in provider.list("")] == ["gba/a.gba"]
    provider.delete("gba/a.gba")
    assert not provider.exists("gba/a.gba")


def test_mounted_storage_routes_by_prefix(tmp_path: Path) -> None:
    roms = LocalStorageProvider(tmp_path / "r")
    saves = LocalStorageProvider(tmp_path / "s")
    storage = MountedStorage({"roms": roms, "saves": saves})
    storage.write("saves/u/g/battery-0.sav", b"save")
    assert (tmp_path / "s" / "u" / "g" / "battery-0.sav").read_bytes() == b"save"
    assert [obj.key for obj in storage.list("saves")] == ["saves/u/g/battery-0.sav"]
    with pytest.raises(InvalidStorageKeyError):
        storage.read("bios/../saves/u/g/battery-0.sav")
    with pytest.raises(InvalidStorageKeyError):
        storage.read("unknown/x")
