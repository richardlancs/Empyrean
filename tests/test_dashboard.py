"""Smoke tests for dashboard/: Simulate alert, bus wiring and the /ws push."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from config import HAZARD_COOLDOWN_SECONDS
from contracts import (
    FrameResult,
    HazardEvent,
    LastSeenResult,
    ModuleStatus,
    NameRequest,
    NameResult,
    SceneSnapshot,
    SpeechStatus,
    TouchEvent,
)
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
    """The served page loads modules that render Simulate alert, warnings and recent events.

    The page used to be one HTML file with these labels inline. The redesign
    renders them from JavaScript modules, so this follows the same requirement
    through the files the server actually serves for the page. The old labels
    "Latest warning" and "Recent events" are now "Warnings" and "Recent activity".
    """
    client, _ = client_and_state
    page = client.get("/")
    assert page.status_code == 200
    assert '<div id="app">' in page.text and "/static/app.js" in page.text
    served = {"/": page.text}
    for path in (
        "/static/app.js",
        "/static/features/operations/index.js",
        "/static/features/operations/demo-tools.js",
        "/static/features/operations/warning-panel.js",
        "/static/features/operations/event-history.js",
        "/static/features/experience/index.js",
    ):
        reply = client.get(path)
        assert reply.status_code == 200, path
        assert reply.headers["content-type"].startswith("text/javascript"), path
        served[path] = reply.text
    text = "\n".join(served.values())
    for label in ("Simulate alert", "Warnings", "Recent activity", "Simulated"):
        assert label in text, label
    for feature in ("experience", "operations"):
        assert f"/static/features/{feature}/index.js" in served["/static/app.js"], feature
    assert "safety" not in text.lower()


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
    # The original four subscriptions stay; the redesign adds exactly these
    # telemetry and correlation inputs (docs/dashboard-redesign/api.md).
    original = {HazardEvent, TouchEvent, FrameResult, SceneSnapshot}
    added = {NameRequest, NameResult, SpeechStatus, ModuleStatus, LastSeenResult}
    assert set(bus.subscribers) == original | added

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
