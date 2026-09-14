"""The TypeScript GameSystem enum must match the Python one."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from retroweb.library.systems import GameSystem

TS_FILE = Path(__file__).resolve().parents[3] / "packages" / "shared" / "src" / "systems.ts"


@pytest.mark.skipif(not TS_FILE.exists(), reason="frontend package not present")
def test_enum_ids_match_frontend() -> None:
    source = TS_FILE.read_text()
    block = re.search(r"export enum GameSystem \{(.*?)\}", source, re.S)
    assert block, "GameSystem enum not found in systems.ts"
    ts_ids = set(re.findall(r'=\s*"([a-z0-9]+)"', block.group(1)))
    assert ts_ids == {system.value for system in GameSystem}
