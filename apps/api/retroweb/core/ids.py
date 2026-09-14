"""Primary-key generation. UUID4 strings are portable across SQLite/PostgreSQL."""

from __future__ import annotations

import uuid


def new_id() -> str:
    return uuid.uuid4().hex
