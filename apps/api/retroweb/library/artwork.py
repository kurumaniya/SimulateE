"""Cover art naming for the libretro-thumbnails collection.

The collection (https://thumbnails.libretro.com, mirrored on GitHub under
``libretro-thumbnails/``) stores one PNG per game under
``<System>/Named_Boxarts/<No-Intro name>.png``. RetroWeb's scanner already
keeps the No-Intro style file name, so most games resolve with one request.
When the exact name misses, the directory index of the system is fetched and
the closest entry with the same title is chosen.

Only name logic lives here; the HTTP side is ``services/artwork.py``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from html import unescape
from urllib.parse import quote, unquote

from retroweb.library.filenames import split_extension
from retroweb.library.systems import GameSystem

# Directory names used by the thumbnail server (spaces, not the underscores of
# the GitHub repository names).
THUMBNAIL_SYSTEM_DIRS: dict[GameSystem, str] = {
    GameSystem.GB: "Nintendo - Game Boy",
    GameSystem.GBC: "Nintendo - Game Boy Color",
    GameSystem.GBA: "Nintendo - Game Boy Advance",
    GameSystem.NES: "Nintendo - Nintendo Entertainment System",
    GameSystem.SNES: "Nintendo - Super Nintendo Entertainment System",
    GameSystem.GENESIS: "Sega - Mega Drive - Genesis",
    GameSystem.N64: "Nintendo - Nintendo 64",
    GameSystem.PS1: "Sony - PlayStation",
    GameSystem.PSP: "Sony - PlayStation Portable",
    GameSystem.NDS: "Nintendo - Nintendo DS",
    GameSystem.SATURN: "Sega - Saturn",
    GameSystem.ARCADE: "FBNeo - Arcade Games",
}

BOXART_DIR = "Named_Boxarts"

# RetroArch replaces these characters with "_" when it builds thumbnail names.
_FORBIDDEN = re.compile(r"[&*/:`<>?\\|]")
_TAG = re.compile(r"\s*[(\[][^)\]]*[)\]]")
_PAREN = re.compile(r"\(([^)]*)\)")
_HREF = re.compile(r'href="([^"]+\.png)"', re.IGNORECASE)

# Tags that mark a dump the user most likely does not have when their own
# file name lacks the tag.
_UNWANTED_TAGS = ("beta", "proto", "demo", "sample", "kiosk", "unl", "pirate", "hack", "virtual")
# Costs less than a matching region (10): a beta of the right region still
# beats the retail release of another region.
_UNWANTED_PENALTY = 8


def thumbnail_name(rom_filename: str) -> str:
    """The thumbnail file name (without ``.png``) RetroArch would look up."""
    stem, _ = split_extension(rom_filename)
    return _FORBIDDEN.sub("_", stem).strip()


def _system_dir(system: GameSystem) -> str:
    return quote(THUMBNAIL_SYSTEM_DIRS[system], safe="")


def thumbnail_path(system: GameSystem, name: str) -> str:
    """URL path of one box art image on the thumbnail server."""
    return f"/{_system_dir(system)}/{BOXART_DIR}/{quote(name + '.png', safe='')}"


def index_path(system: GameSystem) -> str:
    """URL path of the directory listing for a system's box art."""
    return f"/{_system_dir(system)}/{BOXART_DIR}/"


def parse_index(html: str) -> list[str]:
    """Thumbnail names (without ``.png``) from an Apache directory listing."""
    names: list[str] = []
    for href in _HREF.findall(html):
        name = unquote(unescape(href))
        if "/" in name or "?" in name:
            continue  # parent directory, sort links, anything that is not an entry
        names.append(name[: -len(".png")])
    return names


def normalize_title(name: str) -> str:
    """Lower-case title with every ``(tag)`` / ``[tag]`` and punctuation removed."""
    bare = _TAG.sub("", name)
    return re.sub(r"[^a-z0-9]+", " ", bare.lower()).strip()


def tags_of(name: str) -> list[str]:
    """Lower-case contents of the parenthesised tags, in order."""
    return [tag.strip().lower() for tag in _PAREN.findall(name) if tag.strip()]


def _tokens(tags: Iterable[str]) -> set[str]:
    return {part.strip() for tag in tags for part in tag.split(",") if part.strip()}


def _score(name: str, wanted_tags: list[str], wanted_tokens: set[str]) -> int:
    tags = tags_of(name)
    score = 10 * len(_tokens(tags) & wanted_tokens)
    if tags and wanted_tags and tags[0] == wanted_tags[0]:
        score += 5
    for tag in tags:
        if tag in wanted_tags:
            score += 2
            continue
        score -= 1
        if tag.startswith(_UNWANTED_TAGS):
            score -= _UNWANTED_PENALTY
    return score


def closest_release(wanted: str, candidates: Iterable[str]) -> str | None:
    """The candidate whose tags fit the file name ``wanted`` best.

    Shared region / language tokens score highest, tags the wanted name lacks
    cost a little, and beta/proto/demo style tags cost a lot unless the wanted
    name carries them too. Ties resolve alphabetically so the choice is stable.
    The candidates are assumed to be releases of the same game.
    """
    wanted_tags = tags_of(wanted)
    wanted_tokens = _tokens(wanted_tags)
    best: tuple[int, str] | None = None
    for name in candidates:
        score = _score(name, wanted_tags, wanted_tokens)
        if best is None or score > best[0] or (score == best[0] and name < best[1]):
            best = (score, name)
    return best[1] if best else None


def best_match(wanted: str, available: Iterable[str]) -> str | None:
    """Closest entry of ``available`` for the file name ``wanted``.

    Only entries with the same normalised title qualify; among those
    :func:`closest_release` decides.
    """
    title = normalize_title(wanted)
    if not title:
        return None
    return closest_release(wanted, (name for name in available if normalize_title(name) == title))
