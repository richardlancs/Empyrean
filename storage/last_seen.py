"""Turn a last-seen row into the one sentence the wearer hears (SPEC.md section 4.10)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

NOT_SEEN = "I have not seen that."

_MINUTE = 60.0
_HOUR = 3600.0


def _ago(seconds: float) -> str:
    """Return "just now", "N minutes ago" or "N hours ago" for an age in seconds."""
    if seconds < _MINUTE:
        return "just now"
    if seconds < _HOUR:
        n = int(seconds // _MINUTE)
        return "1 minute ago" if n == 1 else f"{n} minutes ago"
    n = int(seconds // _HOUR)
    return "1 hour ago" if n == 1 else f"{n} hours ago"


def join_names(names: Sequence[str]) -> str:
    """Join names as "a", "a and b" or "a, b and c"."""
    items = [n for n in (s.strip() for s in names) if n]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def format_answer(row: Mapping[str, Any] | None, now: float) -> str:
    """Build the spoken answer for a last-seen row, or the no-match sentence."""
    if row is None:
        return NOT_SEEN
    label = (row.get("name") or "").strip() or (row.get("class_label") or "").strip()
    if not label:
        return NOT_SEEN
    parts = [label, _ago(now - float(row["ts"]))]
    neighbours = join_names(row.get("neighbours") or [])
    if neighbours:
        parts.append(f"next to {neighbours}")
    return ", ".join(parts) + "."
