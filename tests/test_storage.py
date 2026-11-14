"""Smoke tests for storage/ (SPEC.md section 4.10)."""

from __future__ import annotations

import logging
import os
import re
import socket
import time
import uuid
from typing import Any

import psycopg
import pytest

from storage import db
from storage._deps import HazardEvent, LastSeenQuery, SpeakRequest, TouchEvent
from storage.last_seen import NOT_SEEN, UNAVAILABLE, format_answer
from storage.writer import QUEUE_MAX_ITEMS, Store

UNREACHABLE_URL = "postgresql://127.0.0.1:1/x"
NOW = 1_800_000_000.0


def _row(age: float, name: str = "Heinz ketchup", neighbours: list[str] | None = None,
         class_label: str = "bottle") -> dict[str, Any]:
    """Build a last_seen-shaped row of the given age."""
    return {"ts": NOW - age, "name": name, "class_label": class_label,
            "neighbours": neighbours or []}


def _touch(i: int = 0) -> TouchEvent:
    """Build a scripted TouchEvent."""
    return TouchEvent(ts=NOW + i, object_id=i, class_label="bottle", name="Heinz ketchup",
                      kind="touch", box=(300.0, 160.0, 340.0, 200.0), neighbours=["mug"])


def _wait_for(cond: Any, timeout: float = 3.0) -> bool:
    """Poll cond() until true or timeout."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


# 1. format_answer --------------------------------------------------------

@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (0, "just now"),
        (59.9, "just now"),
        (60, "1 minute ago"),
        (4 * 60 + 30, "4 minutes ago"),
        (3599, "59 minutes ago"),
        (3600, "1 hour ago"),
        (2 * 3600 + 59, "2 hours ago"),
        (-5, "just now"),
    ],
)
def test_format_answer_time_buckets(age: float, expected: str) -> None:
    """Each age bucket renders as SPEC 4.10 describes."""
    assert format_answer(_row(age), NOW) == f"Heinz ketchup, {expected}."


@pytest.mark.parametrize(
    ("neighbours", "suffix"),
    [
        ([], "."),
        (["mug"], ", next to mug."),
        (["mug", "cereal box"], ", next to mug and cereal box."),
        (["mug", "cereal box", "spoon"], ", next to mug, cereal box and spoon."),
    ],
)
def test_format_answer_neighbours(neighbours: list[str], suffix: str) -> None:
    """Zero to three neighbours are joined naturally."""
    assert format_answer(_row(240, neighbours=neighbours), NOW) == f"Heinz ketchup, 4 minutes ago{suffix}"


def test_format_answer_spec_example_and_fallbacks() -> None:
    """Spec example, class_label fallback, and no match."""
    assert (format_answer(_row(240, neighbours=["mug", "cereal box"]), NOW)
            == "Heinz ketchup, 4 minutes ago, next to mug and cereal box.")
    assert format_answer(_row(10, name=""), NOW) == "bottle, just now."
    assert format_answer(None, NOW) == "I have not seen that."
    assert NOT_SEEN == "I have not seen that."


# 2. unreachable database -------------------------------------------------

def _feed_100(store: Store) -> float:
    """Send 50 touch and 50 hazard events; return the slowest handler call in seconds."""
    worst = 0.0
    for i in range(100):
        ev: Any = _touch(i) if i % 2 else HazardEvent(
            ts=NOW + i, type="vehicle", source="yolo", confidence=0.9)
        t0 = time.perf_counter()
        if i % 2:
            store.on_touch_event(ev)
        else:
            store.on_hazard_event(ev)
        worst = max(worst, time.perf_counter() - t0)
    return worst


def test_unreachable_db_never_blocks_and_warns_once(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """100 events with the DB down: each call is fast, exactly one warning, nothing raised.

    The connection failure is mocked so this is deterministic on every OS. How
    long a real refused or silent connection takes is tested separately below.
    """
    attempts: list[str] = []

    def refuse(url: str) -> Any:
        attempts.append(url)
        raise psycopg.OperationalError("connection refused (mocked)")

    monkeypatch.setattr(db, "connect", refuse)
    published: list[Any] = []
    caplog.set_level(logging.WARNING, logger="storage")
    store = Store(published.append, UNREACHABLE_URL)
    try:
        worst = _feed_100(store)
        assert worst < 0.005, f"slowest call {worst * 1000:.2f} ms"
        assert _wait_for(lambda: store.dropped == 100)

        store.on_last_seen_query(LastSeenQuery(ts=NOW, text="ketchup"))
        assert _wait_for(lambda: len(published) == 1)
    finally:
        store.stop()
    # One connect attempt covers all 101 items: retries wait RETRY_INTERVAL_SECONDS.
    assert len(attempts) == 1
    assert store.written == 0
    warnings = [r for r in caplog.records if r.name == "storage" and r.levelno == logging.WARNING]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert "OperationalError" in warnings[0].getMessage()
    assert "127.0.0.1" not in caplog.text and "postgresql://" not in caplog.text
    answer = published[0]
    assert isinstance(answer, SpeakRequest)
    # Database down: say so, never "I have not seen that."
    assert (answer.text, answer.priority, answer.source) == (UNAVAILABLE, "normal", "storage")


@pytest.fixture
def silent_server() -> Any:
    """A local TCP port that accepts connections and never answers, like a hung database."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)  # the kernel completes the handshake; nothing is ever read or sent
    try:
        yield f"postgresql://u@127.0.0.1:{srv.getsockname()[1]}/x?sslmode=disable"
    finally:
        srv.close()


def test_real_connect_timeout_is_bounded(silent_server: str) -> None:
    """A real connect to a silent server gives up after about CONNECT_TIMEOUT_SECONDS."""
    t0 = time.monotonic()
    with pytest.raises(psycopg.OperationalError):
        db.connect(silent_server)
    elapsed = time.monotonic() - t0
    assert db.CONNECT_TIMEOUT_SECONDS - 0.5 <= elapsed < db.CONNECT_TIMEOUT_SECONDS + 3


def test_hung_db_does_not_block_handlers(
    silent_server: str, caplog: pytest.LogCaptureFixture
) -> None:
    """While the worker sits in a real connect timeout, handlers still return at once."""
    caplog.set_level(logging.WARNING, logger="storage")
    published: list[Any] = []
    store = Store(published.append, silent_server)
    try:
        worst = _feed_100(store)  # the worker is stuck connecting for most of this
        # 50 ms, not 5 ms: with the worker busy in a real connect, a handler can
        # wait one GIL switch interval (5 ms by default) just to run. Blocking on
        # the DB would cost the whole CONNECT_TIMEOUT_SECONDS, far above this.
        assert worst < 0.05, f"slowest call {worst * 1000:.2f} ms"
        store.on_last_seen_query(LastSeenQuery(ts=NOW, text="ketchup"))
        # Wait well past the connect timeout, never just up to it.
        settle = db.CONNECT_TIMEOUT_SECONDS + 5
        assert _wait_for(lambda: store.dropped == 100 and len(published) == 1, settle)
    finally:
        store.stop()
    warnings = [r for r in caplog.records if r.name == "storage" and r.levelno == logging.WARNING]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert "127.0.0.1" not in caplog.text and "postgresql://" not in caplog.text
    assert published[0].text == UNAVAILABLE


# 3. queue full -----------------------------------------------------------

def test_queue_full_drops_instead_of_raising() -> None:
    """Past QUEUE_MAX_ITEMS, events are counted and dropped, not raised."""
    store = Store(lambda _m: None, UNREACHABLE_URL, start=False)
    for i in range(QUEUE_MAX_ITEMS + 5):
        store.on_touch_event(_touch(i))
    store.on_last_seen_query(LastSeenQuery(ts=NOW, text="mug"))
    assert store.dropped == 6
    store.stop()


# 4. LIKE escaping --------------------------------------------------------

def _like_to_regex(pattern: str, escape: str = db.LIKE_ESCAPE) -> re.Pattern[str]:
    """Translate a SQL LIKE pattern with an escape char into a case-insensitive regex."""
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == escape and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "%" else "." if ch == "_" else re.escape(ch))
        i += 1
    return re.compile("".join(out), re.IGNORECASE | re.DOTALL)


def test_like_escaping() -> None:
    """User % and _ are literal; the escape char itself is escaped."""
    assert db.escape_like("50%") == "50\\%"
    assert db.escape_like("a_b") == "a\\_b"
    assert db.escape_like("c:\\x") == "c:\\\\x"
    pat = _like_to_regex(db.contains_pattern("50%"))
    assert pat.fullmatch("Juice 50% off")
    assert not pat.fullmatch("500 ml water")
    assert not pat.fullmatch("50 cents")
    under = _like_to_regex(db.contains_pattern("a_b"))
    assert under.fullmatch("x A_B y") and not under.fullmatch("axb")


# 5. live round trip ------------------------------------------------------

@pytest.mark.skipif(not os.environ.get("TIGER_DATABASE_URL"), reason="TIGER_DATABASE_URL not set")
def test_live_round_trip() -> None:
    """Insert a touch row and find it again case-insensitively."""
    url = os.environ["TIGER_DATABASE_URL"]
    tag = uuid.uuid4().hex[:8]
    session = f"pytest-{tag}"
    name = f"Pytest Ketchup {tag}"
    with db.connect(url) as conn:
        db.ensure_schema(conn)
        try:
            cx, cy = db.box_centre_fraction((300.0, 160.0, 340.0, 200.0))
            db.insert_touch(conn, {"ts": time.time(), "session_id": session, "object_id": 7,
                                   "class_label": "bottle", "name": name, "kind": "touch",
                                   "cx": cx, "cy": cy, "neighbours": ["mug", "cereal box"]})
            row = db.last_seen(conn, name.lower())
            assert row is not None and row["name"] == name
            assert list(row["neighbours"]) == ["mug", "cereal box"]
            assert format_answer(row, time.time()).startswith(f"{name}, just now")
        finally:
            conn.execute("DELETE FROM touch_events WHERE session_id = %s", (session,))
