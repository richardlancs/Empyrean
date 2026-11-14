"""Person 3 modules use the exact shared classes from contracts/, not look-alikes.

A copied dataclass with the same name and fields is a different class. On a bus
that routes by message type, a copy silently misses its subscribers. These
checks compare class identity (`is`), and route through a bus that delivers by
exact type, so a look-alike fails here instead of in the demo.
"""

from __future__ import annotations

import importlib
import importlib.util
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import httpx
import pytest

import config
import contracts
import namer
from fakes.namer.fake_namer import FakeNamer
from fakes.storage.fake_store import FakeStore
from namer.namer import Namer
from storage.writer import Store


class TypeBus:
    """Test bus: delivers a message only to handlers subscribed with its exact class."""

    def __init__(self) -> None:
        self.handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.undelivered: list[Any] = []
        self._lock = threading.Lock()

    def subscribe(self, message_type: type, handler: Callable[[Any], None]) -> None:
        """Register handler for exactly this class (no subclass or name matching)."""
        self.handlers[message_type].append(handler)

    def publish(self, msg: Any) -> None:
        """Deliver msg to the handlers of type(msg); record it if nobody listens."""
        handlers = self.handlers.get(type(msg), [])
        if not handlers:
            with self._lock:
                self.undelivered.append(msg)
        for handler in handlers:
            handler(msg)


class Inbox:
    """Thread-safe collector with a polling wait."""

    def __init__(self) -> None:
        self.items: list[Any] = []
        self._lock = threading.Lock()

    def __call__(self, msg: Any) -> None:
        with self._lock:
            self.items.append(msg)

    def wait_for(self, count: int, timeout: float = 3.0) -> list[Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if len(self.items) >= count:
                    return list(self.items)
            time.sleep(0.01)
        raise AssertionError(f"expected {count} messages, got {len(self.items)}")


def _touch(name: str = "Heinz ketchup") -> contracts.TouchEvent:
    return contracts.TouchEvent(
        ts=time.time(),
        object_id=7,
        class_label="bottle",
        name=name,
        kind="touch",
        box=(100.0, 80.0, 220.0, 300.0),
        neighbours=["blue mug"],
    )


# 1. the shims are gone ---------------------------------------------------


@pytest.mark.parametrize(
    "module",
    [
        "namer._pending",
        "storage._pending",
        "fakes.namer._pending",
        "fakes.storage._pending",
    ],
)
def test_pending_shims_are_gone(module: str) -> None:
    assert importlib.util.find_spec(module) is None


# 2. every message name a Person 3 module uses is the contracts class ------


@pytest.mark.parametrize(
    ("module", "names"),
    [
        ("namer", ["NameRequest"]),
        ("namer.namer", ["NameRequest", "NameResult"]),
        (
            "storage._deps",
            ["TouchEvent", "HazardEvent", "LastSeenQuery", "SpeakRequest"],
        ),
        (
            "storage.writer",
            ["TouchEvent", "HazardEvent", "LastSeenQuery", "SpeakRequest"],
        ),
        ("fakes.namer.fake_namer", ["NameRequest", "NameResult"]),
        (
            "fakes.storage.fake_store",
            ["TouchEvent", "HazardEvent", "LastSeenQuery", "SpeakRequest"],
        ),
    ],
)
def test_module_message_names_are_the_shared_classes(
    module: str, names: list[str]
) -> None:
    mod = importlib.import_module(module)
    for name in names:
        assert getattr(mod, name) is getattr(contracts, name), f"{module}.{name}"


def test_storage_deps_thresholds_come_from_config() -> None:
    deps = importlib.import_module("storage._deps")
    assert (deps.PROCESS_WIDTH, deps.PROCESS_HEIGHT) == (
        config.PROCESS_WIDTH,
        config.PROCESS_HEIGHT,
    )


# 3. real modules: subscribe and publish with the shared classes -----------


def test_namer_register_subscribes_to_contracts_name_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GROK_API_KEY", "test-key")
    monkeypatch.setenv("GROK_MODEL", "test-model")
    bus = TypeBus()
    real = namer.register(bus)
    try:
        assert list(bus.handlers) == [contracts.NameRequest]
    finally:
        real.stop()


def test_real_namer_publishes_contracts_name_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "NAME_MIN_INTERVAL_SECONDS", 0.05)
    monkeypatch.setenv("GROK_API_KEY", "test-key")
    monkeypatch.setenv("GROK_MODEL", "test-model")

    async def grok(_req: httpx.Request) -> httpx.Response:
        body = {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Heinz ketchup"}],
                }
            ]
        }
        return httpx.Response(200, json=body)

    bus, inbox = TypeBus(), Inbox()
    bus.subscribe(contracts.NameResult, inbox)
    real = Namer(
        bus.publish,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(grok)),
    )
    bus.subscribe(contracts.NameRequest, real.on_name_request)
    try:
        bus.publish(
            contracts.NameRequest(
                ts=time.time(), object_id=1, class_label="bottle", crop_jpeg=b"x"
            )
        )
        (result,) = inbox.wait_for(1)
    finally:
        real.stop()
    assert type(result) is contracts.NameResult
    assert (result.object_id, result.name, result.ok) == (1, "Heinz ketchup", True)
    assert bus.undelivered == []


def test_real_store_answers_with_contracts_speak_request() -> None:
    bus, inbox = TypeBus(), Inbox()
    bus.subscribe(contracts.SpeakRequest, inbox)
    store = Store(bus.publish, None)  # no database: answers with the fallback sentence
    bus.subscribe(contracts.LastSeenQuery, store.on_last_seen_query)
    try:
        bus.publish(contracts.LastSeenQuery(ts=time.time(), text="ketchup"))
        (answer,) = inbox.wait_for(1)
    finally:
        store.stop()
    assert type(answer) is contracts.SpeakRequest
    assert (answer.text, answer.priority, answer.source) == (
        "I have not seen that.",
        "normal",
        "storage",
    )


# 4. fakes: same classes as the real modules --------------------------------


def test_fake_namer_publishes_contracts_name_result() -> None:
    bus, inbox = TypeBus(), Inbox()
    bus.subscribe(contracts.NameResult, inbox)
    fake = FakeNamer(bus.publish, seed=1, delay_range=(0.01, 0.02))
    bus.subscribe(contracts.NameRequest, fake.on_name_request)
    try:
        bus.publish(
            contracts.NameRequest(
                ts=time.time(), object_id=0, class_label="bottle", crop_jpeg=b"x"
            )
        )
        (result,) = inbox.wait_for(1)
    finally:
        fake.stop()
    assert type(result) is contracts.NameResult
    assert result.object_id == 0
    assert bus.undelivered == []


def test_fake_store_routes_touch_and_answers_with_contracts_speak_request() -> None:
    bus, inbox = TypeBus(), Inbox()
    bus.subscribe(contracts.SpeakRequest, inbox)
    fake = FakeStore(bus.publish)
    bus.subscribe(contracts.TouchEvent, fake.on_touch_event)
    bus.subscribe(contracts.HazardEvent, fake.on_hazard_event)
    bus.subscribe(contracts.LastSeenQuery, fake.on_last_seen_query)

    bus.publish(_touch())
    bus.publish(
        contracts.HazardEvent(
            ts=time.time(), type="vehicle", source="yolo", confidence=0.9
        )
    )
    bus.publish(contracts.LastSeenQuery(ts=time.time(), text="ketchup"))
    (answer,) = inbox.wait_for(1)

    assert type(answer) is contracts.SpeakRequest
    assert answer.text.startswith("Heinz ketchup, ")
    assert "blue mug" in answer.text
    assert bus.undelivered == []
