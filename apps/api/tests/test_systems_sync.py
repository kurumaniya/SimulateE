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


ADAPTER_FILE = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "emulator-core"
    / "src"
    / "adapters"
    / "emulatorjs"
    / "adapter.ts"
)


@pytest.mark.skipif(not ADAPTER_FILE.exists(), reason="frontend package not present")
def test_supported_systems_match_adapter_bindings() -> None:
    """`supported` reported by the API must equal what the EmulatorJS adapter claims."""
    from retroweb.library.systems import ADAPTER_SUPPORTED_SYSTEMS

    source = ADAPTER_FILE.read_text()
    block = re.search(r"const SYSTEM_BINDINGS[^{]*\{(.*?)\n\};", source, re.S)
    assert block, "SYSTEM_BINDINGS not found in adapter.ts"
    bound = set(re.findall(r"\[GameSystem\.([A-Z0-9]+)\]", block.group(1)))
    assert bound == {system.name for system in ADAPTER_SUPPORTED_SYSTEMS}
