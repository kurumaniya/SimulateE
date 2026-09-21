"""Parse clrmamepro DAT files as published by libretro-database.

Two shapes are read:

* system DATs (``metadat/no-intro``, ``metadat/redump``, ``metadat/fbneo-split``):
  one ``game ( name "…" region "…" serial "…" rom ( name … crc … sha1 … ) )``
  block per release;
* attribute DATs (``metadat/developer``, ``publisher``, ``releaseyear``,
  ``releasemonth``): one block per release carrying a single attribute, keyed
  by the CRC of its rom.

Only names and digests are read; nothing here touches game data.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

# A quoted string (with backslash escapes), a parenthesis, or a bare word.
_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([()])|([^\s()"]+)')


@dataclass(frozen=True)
class DatRom:
    name: str
    size: int | None
    crc: str | None  # upper-case hex, 8 chars
    sha1: str | None  # upper-case hex, 40 chars
    serial: str | None


@dataclass(frozen=True)
class DatGame:
    name: str
    region: str | None = None
    serial: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    roms: tuple[DatRom, ...] = ()


Node = dict[str, list["str | Node"]]


def _tokens(text: str) -> Iterator[tuple[str, str]]:
    for match in _TOKEN.finditer(text):
        quoted, paren, bare = match.groups()
        if paren:
            yield "paren", paren
        elif quoted is not None:
            yield "value", quoted.replace('\\"', '"')
        else:
            yield "value", bare


def _parse_block(tokens: Iterator[tuple[str, str]]) -> Node:
    """Key/value pairs up to the closing parenthesis; values may be nested blocks."""
    node: Node = {}
    key: str | None = None
    for kind, value in tokens:
        if kind == "paren" and value == ")":
            break
        if kind == "paren":  # "(": the value of ``key`` is a block
            child = _parse_block(tokens)
            if key is not None:
                node.setdefault(key, []).append(child)
                key = None
            continue
        if key is None:
            key = value
        else:
            node.setdefault(key, []).append(value)
            key = None
    return node


def _first(node: Node, key: str) -> str | None:
    for value in node.get(key, []):
        if isinstance(value, str):
            return value
    return None


def _hex(value: str | None, length: int) -> str | None:
    if not value:
        return None
    value = value.strip().upper()
    return value.zfill(length) if len(value) <= length else None


def _rom(node: Node) -> DatRom:
    size = _first(node, "size")
    return DatRom(
        name=_first(node, "name") or "",
        size=int(size) if size and size.isdigit() else None,
        crc=_hex(_first(node, "crc"), 8),
        sha1=_hex(_first(node, "sha1"), 40),
        serial=_first(node, "serial"),
    )


def parse_dat(text: str) -> list[DatGame]:
    """Every ``game ( … )`` block of a clrmamepro DAT, in file order."""
    games: list[DatGame] = []
    tokens = _tokens(text)
    for kind, value in tokens:
        if kind != "value":
            continue
        opener = next(tokens, None)
        if opener != ("paren", "("):
            continue
        node = _parse_block(tokens)
        if value != "game":
            continue  # the "clrmamepro ( … )" header
        roms = tuple(_rom(child) for child in node.get("rom", []) if isinstance(child, dict))
        # Attribute DATs have no name; their "comment" is the release name.
        name = _first(node, "name") or _first(node, "comment") or ""
        attributes = {
            key: text_value
            for key in node
            if key not in ("name", "comment", "region", "serial", "rom")
            and (text_value := _first(node, key)) is not None
        }
        games.append(
            DatGame(
                name=name,
                region=_first(node, "region"),
                serial=_first(node, "serial"),
                attributes=attributes,
                roms=roms,
            )
        )
    return games
