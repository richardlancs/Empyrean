"""Thin psycopg 3 helpers for the Tiger Data tables (SPEC.md section 4.10).

Every function here does blocking network I/O. Call them only from the
storage worker thread (or the --selftest CLI), never from a bus handler.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from storage._deps import PROCESS_HEIGHT, PROCESS_WIDTH

log = logging.getLogger("storage")

# Not a SPEC section 9 threshold; fixed by the storage task brief.
CONNECT_TIMEOUT_SECONDS = 3

LIKE_ESCAPE = "\\"

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

_INSERT_TOUCH = (
    "INSERT INTO touch_events "
    "(ts, session_id, object_id, class_label, name, kind, cx, cy, neighbours) "
    "VALUES (to_timestamp(%s), %s, %s, %s, %s, %s, %s, %s, %s)"
)

_INSERT_HAZARD = (
    "INSERT INTO hazard_events (ts, session_id, type, source, confidence) "
    "VALUES (to_timestamp(%s), %s, %s, %s, %s)"
)

_LAST_SEEN = (
    "SELECT extract(epoch FROM ts)::float8 AS ts, session_id, object_id, "
    "class_label, name, kind, cx, cy, neighbours "
    "FROM touch_events "
    "WHERE name ILIKE %(p)s ESCAPE '\\' OR class_label ILIKE %(p)s ESCAPE '\\' "
    "ORDER BY ts DESC LIMIT 1"
)


def connect(url: str) -> psycopg.Connection[Any]:
    """Open an autocommit connection with a short connect timeout."""
    return psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT_SECONDS, autocommit=True)


def ensure_schema(conn: psycopg.Connection[Any]) -> None:
    """Create the tables and hypertables if they do not exist yet."""
    conn.execute(_SCHEMA_PATH.read_text(encoding="utf-8"))


def box_centre_fraction(box: tuple[float, float, float, float]) -> tuple[float, float]:
    """Return the box centre as fractions of the processed frame, clamped to 0..1."""
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2.0) / PROCESS_WIDTH
    cy = ((y1 + y2) / 2.0) / PROCESS_HEIGHT
    return min(max(cx, 0.0), 1.0), min(max(cy, 0.0), 1.0)


def escape_like(text: str) -> str:
    """Escape LIKE metacharacters (escape char, % and _) so they match literally."""
    return (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", LIKE_ESCAPE + "%")
        .replace("_", LIKE_ESCAPE + "_")
    )


def contains_pattern(text: str) -> str:
    """Return an ILIKE pattern that matches values containing text literally."""
    return f"%{escape_like(text)}%"


def insert_touch(conn: psycopg.Connection[Any], row: dict[str, Any]) -> None:
    """Insert one touch_events row; row has ts (epoch s) and the table's other columns."""
    conn.execute(
        _INSERT_TOUCH,
        (
            row["ts"],
            row["session_id"],
            row["object_id"],
            row["class_label"],
            row["name"],
            row["kind"],
            row["cx"],
            row["cy"],
            list(row["neighbours"]),
        ),
    )


def insert_hazard(conn: psycopg.Connection[Any], row: dict[str, Any]) -> None:
    """Insert one hazard_events row; row has ts (epoch s) and the table's other columns."""
    conn.execute(
        _INSERT_HAZARD,
        (row["ts"], row["session_id"], row["type"], row["source"], row["confidence"]),
    )


def last_seen(conn: psycopg.Connection[Any], text: str) -> dict[str, Any] | None:
    """Return the newest touch row whose name or class_label contains text, ignoring case."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(_LAST_SEEN, {"p": contains_pattern(text)})
        return cur.fetchone()
