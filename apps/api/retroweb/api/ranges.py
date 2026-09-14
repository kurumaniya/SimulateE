"""HTTP Range parsing for binary streaming endpoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int  # inclusive

    @property
    def length(self) -> int:
        return self.end - self.start + 1


class UnsatisfiableRangeError(ValueError):
    pass


def parse_range(header: str | None, total: int) -> ByteRange | None:
    """Parse a single ``bytes=start-end`` range. Returns None when absent.

    Multi-range requests are treated as "no range" (full response), which is
    a valid server behaviour and what browsers cope with fine.
    """
    if not header or total <= 0:
        return None
    unit, _, spec = header.partition("=")
    if unit.strip().lower() != "bytes" or "," in spec:
        return None
    start_text, dash, end_text = spec.strip().partition("-")
    if not dash:
        return None
    try:
        if start_text == "":
            suffix = int(end_text)
            if suffix <= 0:
                raise UnsatisfiableRangeError
            return ByteRange(max(total - suffix, 0), total - 1)
        start = int(start_text)
        end = int(end_text) if end_text else total - 1
    except ValueError as exc:
        raise UnsatisfiableRangeError from exc
    if start < 0 or start >= total or end < start:
        raise UnsatisfiableRangeError
    return ByteRange(start, min(end, total - 1))
