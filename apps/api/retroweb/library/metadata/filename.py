"""Derive a title and region from No-Intro / TOSEC style file names.

``Pokemon - Emerald Version (USA, Europe) (Rev 1).gba`` becomes
title ``Pokemon - Emerald Version``, region ``USA, Europe``, label ``Rev 1``.
"""

from __future__ import annotations

import re

from retroweb.library.filenames import split_extension
from retroweb.library.metadata.base import GameMetadata, MetadataProvider
from retroweb.library.systems import GameSystem

_PAREN = re.compile(r"\(([^)]*)\)")
_BRACKET = re.compile(r"\[([^\]]*)\]")
_KNOWN_REGIONS = {
    "usa",
    "europe",
    "japan",
    "world",
    "china",
    "korea",
    "taiwan",
    "asia",
    "australia",
    "germany",
    "france",
    "spain",
    "italy",
    "netherlands",
    "sweden",
    "brazil",
    "canada",
    "uk",
    "hong kong",
    "russia",
}


# Collections number their files: "2851 - 12点的钟声与灰姑娘 [简].iso". The number is
# a catalogue index, not part of the title. It is stripped only when the name
# also carries a collection tag in square brackets or a CJK title; No-Intro
# names like "007 - NightFire (USA)" keep their number.
_CATALOGUE_NUMBER = re.compile(r"^\d{4,6}\s*-\s*")
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def _strip_catalogue_number(title: str, stem: str) -> str:
    if not _CATALOGUE_NUMBER.match(title):
        return title
    if _CJK.search(title) or _BRACKET.search(stem):
        return _CATALOGUE_NUMBER.sub("", title, count=1).strip(" -_")
    return title


class FilenameMetadataProvider(MetadataProvider):
    id = "filename"

    def from_filename(self, filename: str, system: GameSystem) -> GameMetadata | None:
        stem, _ = split_extension(filename)
        if not stem.strip():
            return None
        tags = _PAREN.findall(stem) + _BRACKET.findall(stem)
        title = _BRACKET.sub("", _PAREN.sub("", stem)).strip(" -_")
        title = re.sub(r"\s+", " ", title).replace("_", " ").strip()
        title = _strip_catalogue_number(title, stem)
        if not title:
            title = stem.strip()

        region: str | None = None
        labels: list[str] = []
        for tag in tags:
            parts = [part.strip() for part in tag.split(",")]
            if parts and all(part.lower() in _KNOWN_REGIONS for part in parts):
                region = region or ", ".join(parts)
            elif tag.strip():
                labels.append(tag.strip())
        return GameMetadata(title=title, region=region, label=", ".join(labels) or None)
