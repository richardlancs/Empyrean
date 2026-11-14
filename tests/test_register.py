"""register(bus) tests for storage/, namer/ and their fakes, through a small test bus.

No credentials needed: every storage.db call is replaced with an in-memory stand-in.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import pytest

import storage
from contracts import (
    FrameResult,
    HazardEvent,
    LastSeenQuery,
    NameRequest,
    NameResult,
    SceneQuestion,
    SpeakRequest,
    TouchEvent,
)
from fakes.namer import fake_namer
from fakes.storage import fake_store
from namer import Namer
from namer import register as namer_register
from storage import db
from storage.last_seen import UNAVAILABLE, format_answer
from storage.writer import Store

FAKE_URL = "postgresql://user@fake-host/fake-db"
NOW = 1_800_000_000.0


class TestBus:
    """Minimal in-process bus: subscribe(MessageType, handler) and publish(message)."""

    __test__ = False  # not a pytest test class

    def __init__(self) -> None:
        """Start with no subscribers and an empty publish log."""
        self.subscribers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.published: list[tuple[Any, str]] = []
        self._lock = threading.Lock()

    def subscribe(self, msg_type: type, handler: Callable[[Any], None]) -> None:
        """Register handler for messages of exactly msg_type."""
        self.subscribers[msg_type].append(handler)

    def publish(self, msg: Any) -> None:
        """Record msg with the publishing thread's name, then deliver it synchronously."""
        with self._lock:
            self.published.append((msg, threading.current_thread().name))
        for handler in list(self.subscribers.get(type(msg), [])):
            handler(msg)

    def of_type(self, msg_type: type) -> list[Any]:
        """Return published messages of msg_type."""
        with self._lock:
            return [m for m, _ in self.published if isinstance(m, msg_type)]


class FakeConn:
    """Stands in for a psycopg connection: open and healthy until closed."""

    def __init__(self) -> None:
        """Create an open connection."""
        self.closed = False
        self.broken = False

    def close(self) -> None:
        """Mark the connection closed."""
        self.closed = True


class FakeDb:
    """Records every storage.db call made by the worker."""

    def __init__(self, last_seen_row: dict[str, Any] | None = None) -> None:
        """Set the row that last_seen() returns."""
        self.connect_urls: list[str] = []
        self.touches: list[dict[str, Any]] = []
        self.hazards: list[dict[str, Any]] = []
        self.queries: list[str] = []
        self.last_seen_row = last_seen_row
        self.connect_gate = threading.Event()
        self.connect_gate.set()

    def connect(self, url: str) -> FakeConn:
        """Wait on connect_gate (to simulate a slow DB), then return a connection."""
        self.connect_gate.wait(timeout=5.0)
        self.connect_urls.append(url)
        return FakeConn()

    def ensure_schema(self, conn: FakeConn) -> None:
        """Do nothing."""

    def insert_touch(self, conn: FakeConn, row: dict[str, Any]) -> None:
        """Record a touch row."""
        self.touches.append(row)

    def insert_hazard(self, conn: FakeConn, row: dict[str, Any]) -> None:
        """Record a hazard row."""
        self.hazards.append(row)

    def last_seen(self, conn: FakeConn, text: str) -> dict[str, Any] | None:
        """Record the query and return the configured row."""
        self.queries.append(text)
        return self.last_seen_row


@pytest.fixture
def fake_db(monkeypatch: pytest.MonkeyPatch) -> FakeDb:
    """Replace storage.db's network functions and point TIGER_DATABASE_URL at a fake."""
    fake = FakeDb(
        last_seen_row={
            "ts": time.time() - 240,
            "name": "Heinz ketchup",
            "class_label": "bottle",
            "neighbours": ["mug", "cereal box"],
        }
    )
    for name in (
        "connect",
        "ensure_schema",
        "insert_touch",
        "insert_hazard",
        "last_seen",
    ):
        monkeypatch.setattr(db, name, getattr(fake, name))
    monkeypatch.setenv("TIGER_DATABASE_URL", FAKE_URL)
    return fake


def _wait_for(cond: Callable[[], bool], timeout: float = 5.0) -> bool:
    """Poll cond() until true or timeout."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.01)
    return cond()


def _touch() -> TouchEvent:
    """Build a scripted TouchEvent."""
    return TouchEvent(
        ts=NOW,
        object_id=7,
        class_label="bottle",
        name="Heinz ketchup",
        kind="touch",
        box=(300.0, 160.0, 340.0, 200.0),
        neighbours=["mug"],
    )


def _hazard() -> HazardEvent:
    """Build a scripted HazardEvent."""
    return HazardEvent(ts=NOW, type="stairs_down", source="yolo", confidence=0.9)


# storage.register -----------------------------------------------------------


def test_storage_register_subscribes_three_handlers(fake_db: FakeDb) -> None:
    """register returns a Store whose three handlers are subscribed to the contract classes."""
    bus = TestBus()
    store = storage.register(bus)
    try:
        assert isinstance(store, Store)
        assert dict(bus.subscribers) == {
            TouchEvent: [store.on_touch_event],
            HazardEvent: [store.on_hazard_event],
            LastSeenQuery: [store.on_last_seen_query],
        }
    finally:
        store.stop()


def test_storage_register_writes_touch_and_hazard(fake_db: FakeDb) -> None:
    """TouchEvent and HazardEvent published on the bus reach the database writer."""
    bus = TestBus()
    store = storage.register(bus)
    try:
        bus.publish(_touch())
        bus.publish(_hazard())
        assert _wait_for(lambda: store.written == 2)
        assert fake_db.touches[0]["object_id"] == 7
        assert fake_db.touches[0]["name"] == "Heinz ketchup"
        assert fake_db.hazards[0]["type"] == "stairs_down"
        assert fake_db.connect_urls == [FAKE_URL]
    finally:
        store.stop()


def test_storage_register_query_publishes_speak_request(fake_db: FakeDb) -> None:
    """A LastSeenQuery on the bus produces one SpeakRequest, published from the worker."""
    bus = TestBus()
    store = storage.register(bus)
    try:
        bus.publish(LastSeenQuery(ts=NOW, text="ketchup"))
        assert _wait_for(lambda: len(bus.of_type(SpeakRequest)) == 1)
        answer = bus.of_type(SpeakRequest)[0]
        assert type(answer) is SpeakRequest
        assert answer.text == format_answer(fake_db.last_seen_row, time.time())
        assert answer.text.startswith(
            "Heinz ketchup, 4 minutes ago, next to mug and cereal box"
        )
        assert answer.priority == "normal"
        assert answer.source == "storage"
        assert fake_db.queries == ["ketchup"]
        thread = next(t for m, t in bus.published if m is answer)
        assert thread == "storage-writer"
    finally:
        store.stop()


def test_storage_handlers_do_not_wait_on_database(fake_db: FakeDb) -> None:
    """Publishing returns at once even while the database connection hangs."""
    fake_db.connect_gate.clear()
    bus = TestBus()
    start = time.monotonic()
    store = storage.register(bus)
    try:
        for _ in range(20):
            bus.publish(_touch())
            bus.publish(_hazard())
            bus.publish(LastSeenQuery(ts=NOW, text="ketchup"))
        elapsed = time.monotonic() - start
        assert elapsed < 0.5
        assert store.written == 0
        fake_db.connect_gate.set()
        assert _wait_for(lambda: store.written == 40)
        assert _wait_for(lambda: len(bus.of_type(SpeakRequest)) == 20)
    finally:
        fake_db.connect_gate.set()
        store.stop()


def test_storage_register_reads_url_once_at_registration(
    fake_db: FakeDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The URL is captured when register() runs; setting it afterwards has no effect."""
    monkeypatch.delenv("TIGER_DATABASE_URL")
    bus = TestBus()
    store = storage.register(bus)
    try:
        monkeypatch.setenv("TIGER_DATABASE_URL", FAKE_URL)  # too late
        bus.publish(_touch())
        bus.publish(LastSeenQuery(ts=NOW, text="ketchup"))
        assert _wait_for(lambda: len(bus.of_type(SpeakRequest)) == 1)
        # No URL means history is unavailable, which is not the same as no match.
        assert bus.of_type(SpeakRequest)[0].text == UNAVAILABLE
        assert _wait_for(lambda: store.dropped == 1)
        assert fake_db.connect_urls == []
    finally:
        store.stop()


# namer.register ---------------------------------------------------------------


def test_namer_register_subscribes_name_request() -> None:
    """namer.register subscribes on_name_request to NameRequest and returns the Namer."""
    bus = TestBus()
    namer = namer_register(bus)
    try:
        assert isinstance(namer, Namer)
        assert dict(bus.subscribers) == {
            NameRequest: [namer.on_name_request],
            FrameResult: [namer.questions.on_frame],
            SceneQuestion: [namer.questions.on_question],
        }
    finally:
        namer.stop(timeout=2.0)


# fakes: same bus interface as the real modules ---------------------------------


def test_fake_store_register_matches_storage() -> None:
    """fakes.storage registers the same three types and answers a query with SpeakRequest."""
    bus = TestBus()
    store = fake_store.register(bus)
    assert set(bus.subscribers) == {TouchEvent, HazardEvent, LastSeenQuery}
    bus.publish(
        TouchEvent(
            ts=time.time() - 240,
            object_id=1,
            class_label="bottle",
            name="Heinz ketchup",
            kind="touch",
            box=(0.0, 0.0, 10.0, 10.0),
            neighbours=["mug"],
        )
    )
    bus.publish(_hazard())
    bus.publish(LastSeenQuery(ts=time.time(), text="ketchup"))
    answers = bus.of_type(SpeakRequest)
    assert len(answers) == 1
    assert answers[0].text == "Heinz ketchup, 4 minutes ago, next to mug."
    assert answers[0].source == "storage"
    assert len(store.hazard_events) == 1
    store.stop()


def test_fake_namer_register_matches_namer() -> None:
    """fakes.namer registers on NameRequest and publishes a NameResult back on the bus."""
    bus = TestBus()
    namer = fake_namer.register(bus)
    try:
        assert set(bus.subscribers) == {NameRequest, SceneQuestion}
        bus.publish(
            NameRequest(ts=NOW, object_id=3, class_label="bottle", crop_jpeg=b"")
        )
        assert _wait_for(lambda: len(bus.of_type(NameResult)) == 1)
        result = bus.of_type(NameResult)[0]
        assert (result.object_id, result.name, result.ok) == (3, "Heinz ketchup", True)
    finally:
        namer.stop(timeout=2.0)
