"""Smoke tests for dashboard/: Simulate alert, bus wiring and the /ws push."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from config import HAZARD_COOLDOWN_SECONDS
from contracts import FrameResult, HazardEvent, ModeChange, SceneSnapshot, TouchEvent
from dashboard import DashboardState, create_app, register
from dashboard.state import EVENT_LOG_SIZE, HAZARD_LABELS

NOW = 1_800_000_000.0
BOX = (100.0, 80.0, 200.0, 240.0)


class TestBus:
    """Minimal in-process bus: subscribe(MessageType, handler) and publish(message)."""

    __test__ = False  # not a pytest test class

    def __init__(self) -> None:
        """Start with no subscribers and an empty publish log."""
        self.subscribers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.published: list[Any] = []

    def subscribe(self, msg_type: type, handler: Callable[[Any], None]) -> None:
        """Register handler for messages of exactly msg_type."""
        self.subscribers[msg_type].append(handler)

    def publish(self, msg: Any) -> None:
        """Record msg, then deliver it synchronously."""
        self.published.append(msg)
        for handler in list(self.subscribers.get(type(msg), [])):
            handler(msg)


@pytest.fixture
def client_and_state() -> tuple[TestClient, DashboardState]:
    """A test client around a fresh dashboard state with a fixed clock."""
    state = DashboardState(clock=lambda: NOW)
    return TestClient(create_app(state)), state


def test_page_has_button_and_both_areas(
    client_and_state: tuple[TestClient, DashboardState],
) -> None:
    """The single page has the Simulate alert button, Latest warning and Recent events."""
    client, _ = client_and_state
    page = client.get("/")
    assert page.status_code == 200
    for text in ("Simulate alert", "Latest warning", "Recent events", "Simulated"):
        assert text in page.text
    assert "safety" not in page.text.lower()


def test_one_click_sets_latest_warning_and_adds_exactly_one_event(
    client_and_state: tuple[TestClient, DashboardState],
) -> None:
    """One simulate call gives a simulated stairs warning and one log entry."""
    client, _ = client_and_state
    assert client.get("/api/state").json()["events"] == []

    state = client.post("/api/simulate-alert").json()

    warning = state["latest_warning"]
    assert warning["type"] == "stairs_down"
    assert warning["type"] in typing_args_hazard_types()
    assert warning["text"] == HAZARD_LABELS["stairs_down"]
    assert warning["simulated"] is True
    assert len(state["events"]) == 1
    assert state["events"][0] == warning
    assert state["hazard_active_seconds"] == HAZARD_COOLDOWN_SECONDS

    second = client.post("/api/simulate-alert").json()
    assert len(second["events"]) == 2  # each click adds exactly one


def typing_args_hazard_types() -> set[str]:
    """Return the HazardEvent.type values allowed by contracts/."""
    import typing

    return set(typing.get_args(typing.get_type_hints(HazardEvent)["type"]))


def test_simulate_publishes_nothing_on_the_bus() -> None:
    """Simulated alerts stay on the page: no HazardEvent, so no alarm and no storage."""
    bus = TestBus()
    state = register(bus, DashboardState(clock=lambda: NOW), serve=False).state
    client = TestClient(create_app(state))
    client.post("/api/simulate-alert")
    assert bus.published == []


def test_register_and_real_events_are_not_simulated() -> None:
    """Real HazardEvent and touch TouchEvent from the bus are shown without the label."""
    bus = TestBus()
    state = register(bus, serve=False).state
    assert set(bus.subscribers) == {
        HazardEvent,
        TouchEvent,
        FrameResult,
        SceneSnapshot,
        ModeChange,
    }

    bus.publish(HazardEvent(ts=NOW, type="vehicle", source="yolo", confidence=0.91))
    bus.publish(
        TouchEvent(
            ts=NOW + 1,
            object_id=1,
            class_label="bottle",
            name="Heinz ketchup",
            kind="touch",
            box=BOX,
        )
    )
    bus.publish(
        TouchEvent(
            ts=NOW + 2,
            object_id=1,
            class_label="bottle",
            name="Heinz ketchup",
            kind="release",
            box=BOX,
        )
    )
    snap = state.snapshot()
    assert [(e["kind"], e["text"], e["simulated"]) for e in snap["events"]] == [
        ("touch", "Heinz ketchup", False),
        ("hazard", "Vehicle", False),
    ]
    assert snap["latest_warning"]["detail"] == "yolo, 91%"


def test_event_log_keeps_last_ten() -> None:
    """Only the newest EVENT_LOG_SIZE events are kept, newest first."""
    state = DashboardState(clock=lambda: NOW)
    for _ in range(EVENT_LOG_SIZE + 3):
        state.simulate_hazard()
    ids = [e["id"] for e in state.snapshot()["events"]]
    assert len(ids) == EVENT_LOG_SIZE
    assert ids == sorted(ids, reverse=True)


def test_websocket_pushes_state_after_simulate(
    client_and_state: tuple[TestClient, DashboardState],
) -> None:
    """An open page gets the initial state, then the state with the one new event."""
    client, _ = client_and_state
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["events"] == []
        client.post("/api/simulate-alert")
        pushed = ws.receive_json()
    assert len(pushed["events"]) == 1
    assert pushed["latest_warning"]["simulated"] is True


def _free_port() -> int:
    """Return a TCP port nothing is listening on right now."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_serve_starts_the_page_on_a_thread_and_stops() -> None:
    """Under app/, the page is served on a background thread and stop() ends it."""
    import time

    import httpx

    from dashboard import Dashboard

    port = _free_port()
    dashboard = Dashboard(DashboardState(clock=lambda: NOW))
    assert dashboard.serve(port=port) is True
    try:
        deadline = time.monotonic() + 5.0
        while True:
            try:
                reply = httpx.post(f"http://127.0.0.1:{port}/api/simulate-alert")
                break
            except httpx.ConnectError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        assert len(reply.json()["events"]) == 1
    finally:
        dashboard.stop()
    assert not dashboard._thread.is_alive()


def test_serve_skips_a_busy_port() -> None:
    """If the port is taken, serve() logs and returns False instead of crashing."""
    import socket

    from dashboard import Dashboard

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        assert Dashboard(DashboardState()).serve(port=port) is False


def test_scene_snapshot_fills_object_list_touched_first() -> None:
    """SceneSnapshot objects reach the page state, touched first, name or class shown."""
    from contracts import SceneObject

    bus = TestBus()
    state = register(bus, DashboardState(clock=lambda: NOW), serve=False).state
    bus.publish(
        SceneSnapshot(
            ts=NOW,
            frame_id=3,
            objects=[
                SceneObject(1, "chair", "", "idle", BOX, NOW),
                SceneObject(2, "bottle", "Heinz ketchup", "touching", BOX, NOW),
                SceneObject(3, "cup", "", "lost", BOX, NOW - 1),
            ],
        )
    )
    objects = state.snapshot()["objects"]
    assert [(o["text"], o["state"], o["named"]) for o in objects] == [
        ("Heinz ketchup", "touching", True),
        ("chair", "idle", False),
        ("cup", "lost", False),
    ]
    assert objects[2]["last_seen_ts"] == NOW - 1


def test_demo_button_publishes_mode_change_and_shows_mode() -> None:
    """The Demo mode button publishes ModeChange on the bus and the page state follows."""
    bus = TestBus()
    dashboard = register(bus, DashboardState(clock=lambda: NOW), serve=False)
    client = TestClient(create_app(dashboard.state, publish=bus.publish))
    assert client.get("/api/state").json()["mode"] == "actual"
    assert 'id="mode"' in client.get("/").text

    body = client.post("/api/mode", json={"mode": "demo"}).json()
    assert body["mode"] == "demo"
    assert [(type(m), m.mode) for m in bus.published] == [(ModeChange, "demo")]

    # Vision answers "actual" when it has no demo weights; the page must follow.
    bus.publish(ModeChange(ts=NOW, mode="actual"))
    assert client.get("/api/state").json()["mode"] == "actual"

    assert client.post("/api/mode", json={"mode": "replay"}).status_code == 422
