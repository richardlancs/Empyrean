"""Dashboard HTTP layer: last-touch search, thumbnails, overlays, static files, simulation."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Any, ClassVar

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from config import (
    LAST_SEEN_TIMEOUT_SECONDS,
    PROCESS_HEIGHT,
    PROCESS_WIDTH,
    THUMBNAIL_MAX_AGE_SECONDS,
)
from contracts import (
    FrameResult,
    HazardEvent,
    LastSeenQuery,
    LastSeenResult,
    SceneObject,
    SceneSnapshot,
    TouchEvent,
    TrackedObject,
)
from dashboard import DashboardState, VideoFeed, create_app, register
from dashboard import server as server_module
from dashboard.services.last_seen import MAX_PENDING, MAX_QUERY_CHARS, LastSeenService
from dashboard.thumbnails import ThumbnailCache
from dashboard.video import OverlayOptions, mjpeg_stream, render_frame

NOW = 1_800_000_000.0
BOTTLE = (100.0, 80.0, 200.0, 240.0)
CUP = (320.0, 150.0, 420.0, 290.0)


class Clock:
    def __init__(self, start: float = NOW) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class SyncBus:
    """Deliver messages inline and record them."""

    def __init__(self) -> None:
        self.handlers: dict[type, list[Callable[[Any], None]]] = defaultdict(list)
        self.published: list[Any] = []

    def subscribe(self, msg_type: type, handler: Callable[[Any], None]) -> None:
        self.handlers[msg_type].append(handler)

    def publish(self, msg: Any) -> None:
        self.published.append(msg)
        for handler in list(self.handlers.get(type(msg), [])):
            handler(msg)


def _frame(frame_id: int = 7, background: int = 0) -> FrameResult:
    image = np.full((PROCESS_HEIGHT, PROCESS_WIDTH, 3), background, dtype=np.uint8)
    image[80:240, 100:200] = (40, 120, 200)  # the bottle
    return FrameResult(
        ts=NOW, frame_id=frame_id, image=image,
        objects=[TrackedObject(1, "bottle", 0.9, BOTTLE), TrackedObject(2, "cup", 0.9, CUP)],
    )


def _snapshot(frame_id: int = 7) -> SceneSnapshot:
    return SceneSnapshot(NOW, frame_id, [
        SceneObject(1, "bottle", "Heinz ketchup", "touching", BOTTLE, NOW),
        SceneObject(2, "cup", "", "idle", CUP, NOW),
    ])


# Last-touch search ---------------------------------------------------------------


def _client_with_bus(clock: Clock | None = None) -> tuple[TestClient, SyncBus, Any]:
    bus = SyncBus()
    dashboard = register(bus, DashboardState(clock=clock or Clock()), serve=False)
    if clock is not None:
        dashboard.last_seen._clock = clock  # same controllable time for expiry
    return TestClient(create_app(dashboard.state)), bus, dashboard


def _queries(bus: SyncBus) -> list[LastSeenQuery]:
    return [m for m in bus.published if isinstance(m, LastSeenQuery)]


def test_last_seen_found_through_the_bus() -> None:
    """POST 202 -> LastSeenQuery with the id on the bus -> result -> GET found."""
    client, bus, _ = _client_with_bus()
    reply = client.post("/api/last-seen", json={"query": "  ketchup "})
    assert reply.status_code == 202
    request_id = reply.json()["request_id"]
    assert reply.json()["status"] == "pending"
    (query,) = _queries(bus)
    assert (query.text, query.request_id) == ("ketchup", request_id)
    assert client.get(f"/api/last-seen/{request_id}").json()["status"] == "pending"

    bus.publish(LastSeenResult(NOW, request_id, "found", "Heinz ketchup, just now.", NOW - 30,
                               "Heinz ketchup", ["mug"]))
    body = client.get(f"/api/last-seen/{request_id}").json()
    assert body["status"] == "found" and body["matched_at"] == NOW - 30
    assert body["answer"] == "Heinz ketchup, just now." and body["neighbours"] == ["mug"]
    assert set(body) >= {"request_id", "status", "answer", "matched_at"}


def test_last_seen_not_found_and_unavailable_stay_distinct() -> None:
    """Each outcome shows exactly the sentence that was spoken, and says why."""
    client, bus, _ = _client_with_bus()
    a = client.post("/api/last-seen", json={"query": "zebra"}).json()["request_id"]
    b = client.post("/api/last-seen", json={"query": "keys"}).json()["request_id"]
    bus.publish(LastSeenResult(NOW, a, "not_found", "I have not seen that."))
    bus.publish(LastSeenResult(NOW, b, "unavailable", "Touch history is unavailable right now."))
    first, second = (client.get(f"/api/last-seen/{i}").json() for i in (a, b))
    assert first["status"] == "not_found" and first["answer"] == "I have not seen that."
    assert second["status"] == "unavailable"
    assert second["answer"] == "Touch history is unavailable right now."
    assert "not a 'not found'" in second["detail"]


def test_concurrent_searches_never_get_each_others_answers() -> None:
    """Results arriving out of order, plus one for an unknown id, land on the right search."""
    client, bus, _ = _client_with_bus()
    ids = [client.post("/api/last-seen", json={"query": q}).json()["request_id"]
           for q in ("keys", "phone", "mug")]
    assert len(set(ids)) == 3
    bus.publish(LastSeenResult(NOW, "someone-else", "found", "Wallet, just now.", NOW))
    bus.publish(LastSeenResult(NOW, ids[2], "found", "Mug, just now.", NOW - 1, "mug"))
    bus.publish(LastSeenResult(NOW, ids[0], "not_found", "I have not seen that."))
    # A duplicate late answer for a finished search is ignored.
    bus.publish(LastSeenResult(NOW, ids[0], "found", "Keys, just now.", NOW))
    answers = [client.get(f"/api/last-seen/{i}").json() for i in ids]
    assert [a["status"] for a in answers] == ["not_found", "pending", "found"]
    assert answers[2]["answer"] == "Mug, just now." and answers[0]["matched_at"] is None


def test_search_times_out_as_unavailable_and_results_expire() -> None:
    """No answer within the timeout is unavailable; finished searches are later forgotten."""
    clock = Clock()
    client, _, dashboard = _client_with_bus(clock)
    request_id = client.post("/api/last-seen", json={"query": "keys"}).json()["request_id"]
    clock.now += LAST_SEEN_TIMEOUT_SECONDS + 0.1
    body = client.get(f"/api/last-seen/{request_id}").json()
    assert body["status"] == "unavailable" and "did not answer" in body["detail"]
    # A late answer after the timeout does not turn it into a match.
    dashboard.last_seen.on_result(LastSeenResult(clock.now, request_id, "found", "Keys.", NOW))
    assert client.get(f"/api/last-seen/{request_id}").json()["status"] == "unavailable"
    clock.now += 1000
    assert client.get(f"/api/last-seen/{request_id}").status_code == 404


def test_search_input_and_pending_limits() -> None:
    """Empty, too long and extra-field bodies are 422; too many pending is 429; unknown id 404."""
    client, bus, _ = _client_with_bus()
    for body in ({"query": "   "}, {"query": "x" * (MAX_QUERY_CHARS + 1)}, {}, {"query": "a", "x": 1}):
        reply = client.post("/api/last-seen", json=body)
        assert reply.status_code == 422, body
        assert isinstance(reply.json()["detail"], str)
    for _ in range(MAX_PENDING):
        assert client.post("/api/last-seen", json={"query": "keys"}).status_code == 202
    over = client.post("/api/last-seen", json={"query": "keys"})
    assert over.status_code == 429 and "Too many" in over.json()["detail"]
    assert len(_queries(bus)) == MAX_PENDING  # the rejected one was never published
    assert client.get("/api/last-seen/unknown").status_code == 404


def test_search_without_an_engine_is_503_and_capability_false() -> None:
    """python -m dashboard has no bus: the page is told plainly, nothing pretends to search."""
    client = TestClient(create_app(DashboardState(clock=Clock())))
    reply = client.post("/api/last-seen", json={"query": "keys"})
    assert reply.status_code == 503 and "engine" in reply.json()["detail"]
    assert client.get("/api/state").json()["capabilities"]["last_seen"] is False


def test_last_seen_service_bounds_retained_results() -> None:
    """Finished searches are trimmed so memory stays bounded."""
    published: list[Any] = []
    service = LastSeenService(published.append, clock=Clock())
    for _ in range(200):
        request_id = service.submit("keys")
        service.on_result(LastSeenResult(NOW, request_id, "not_found", "I have not seen that."))
    assert len(service._records) <= 64 + MAX_PENDING


# Simulation stays on the page ---------------------------------------------------


def test_simulation_never_reaches_hazard_audio_or_storage() -> None:
    """With the real Bus, real fake-audio and the fake store: simulate publishes nothing."""
    from app.bus import Bus
    from audio.audio import AudioManager
    from fakes.storage.fake_store import register as register_store

    class Alarm:
        duration = 0.0
        mode = "fake"
        plays = 0

        def play(self) -> None:
            Alarm.plays += 1

        def close(self) -> None:
            pass

    class Speaker:
        mode = "fake"
        said: ClassVar[list[str]] = []

        def say(self, text: str, should_stop: Callable[[], bool]) -> None:
            Speaker.said.append(text)

    bus = Bus()
    seen: list[Any] = []
    bus.subscribe(HazardEvent, seen.append)
    manager = AudioManager(Speaker, Alarm(), publish=bus.publish)
    bus.subscribe(HazardEvent, manager.on_hazard)
    store = register_store(bus)
    dashboard = register(bus, serve=False)
    try:
        client = TestClient(create_app(dashboard.state))
        snap = client.post("/api/simulate-alert").json()
        assert snap["latest_simulated_warning"]["simulated"] is True
        assert snap["latest_real_warning"] is None
        time.sleep(0.2)  # give every bus worker time to deliver anything that was sent
        assert seen == [] and Alarm.plays == 0 and Speaker.said == []
        assert store.hazard_events == [] and store.touch_events == []
    finally:
        manager.stop()
        bus.stop()


# Thumbnails -------------------------------------------------------------------------


def test_thumbnail_endpoint_serves_recent_crop_then_expires() -> None:
    """A visible object gets a small JPEG; after the max age it is 404 and the URL goes away."""
    clock = Clock()
    thumbnails = ThumbnailCache(clock=clock)
    state = DashboardState(clock=clock)
    client = TestClient(create_app(state, thumbnails=thumbnails))
    assert client.get("/api/objects/1/thumbnail").status_code == 404
    thumbnails.on_frame(_frame())
    thumbnails.on_scene(_snapshot())
    state.on_scene(_snapshot())
    objects = client.get("/api/state").json()["objects"]
    url = next(o["thumbnail_url"] for o in objects if o["object_id"] == 1)
    assert url.startswith("/api/objects/1/thumbnail")
    reply = client.get(url)
    assert reply.status_code == 200 and reply.headers["content-type"] == "image/jpeg"
    crop = cv2.imdecode(np.frombuffer(reply.content, np.uint8), cv2.IMREAD_COLOR)
    assert max(crop.shape[:2]) <= 160
    assert client.get("/api/state").json()["capabilities"]["thumbnails"] is True

    clock.now += THUMBNAIL_MAX_AGE_SECONDS + 1
    assert client.get("/api/objects/1/thumbnail").status_code == 404
    objects = client.get("/api/state").json()["objects"]
    assert all(o["thumbnail_url"] is None for o in objects)


def test_thumbnail_cache_is_bounded_and_skips_lost_objects() -> None:
    """At most max_items crops; a lost object's stale box is never cropped."""
    cache = ThumbnailCache(clock=Clock(), max_items=3)
    cache.on_frame(_frame())
    objects = [SceneObject(i, "cup", "", "idle", (10.0 * i, 10.0, 10.0 * i + 30, 60.0), NOW)
               for i in range(10)]
    objects.append(SceneObject(50, "cup", "", "lost", CUP, NOW))
    cache.on_scene(SceneSnapshot(NOW, 7, objects))
    assert len(cache) == 3 and cache.get(50) is None


def test_thumbnail_needs_the_matching_frame() -> None:
    """A snapshot whose frame is gone produces no crop rather than a mismatched one."""
    cache = ThumbnailCache(clock=Clock())
    cache.on_frame(_frame(frame_id=1))
    cache.on_scene(_snapshot(frame_id=99))
    assert len(cache) == 0


# Video overlays -----------------------------------------------------------------


def test_overlay_flags_hide_boxes_labels_and_hands_without_touching_the_image() -> None:
    """boxes=0 leaves the object area as captured; the frame itself is never changed."""
    frame = _frame()
    original = frame.image.copy()
    plain = render_frame(frame, _snapshot(), OverlayOptions(boxes=False, hands=False, labels=False))
    assert np.array_equal(plain, original)
    assert np.array_equal(frame.image, original)
    default = render_frame(frame, _snapshot())
    assert not np.array_equal(default, original)
    no_labels = render_frame(frame, _snapshot(), OverlayOptions(labels=False))
    assert not np.array_equal(no_labels, default)  # tags gone, boxes kept
    assert np.array_equal(no_labels[200, 100], default[200, 100])  # box edge identical


@pytest.mark.parametrize("background", [0, 255])
def test_selected_object_has_contrast_on_dark_and_light_frames(background: int) -> None:
    """The selection ring has black and white strokes, so it shows on any image."""
    frame = _frame(background=background)
    image = render_frame(frame, _snapshot(), OverlayOptions(selected_id=2))
    x1, y1, x2, y2 = (int(v) for v in CUP)
    ring = np.concatenate([image[y1 - 4:y1 + 5, x1:x2].reshape(-1, 3),
                           image[y1:y2, x1 - 4:x1 + 5].reshape(-1, 3)])
    assert (ring.max(axis=1) < 30).any() and (ring.min(axis=1) > 225).any()
    # Coordinates are drawn unscaled: the ring is centred on the box edge.
    assert tuple(int(v) for v in image[(y1 + y2) // 2, x1]) == (118, 118, 15)


def test_two_viewers_with_different_options_do_not_affect_each_other() -> None:
    """Default stays the shared picture; each option set gets its own cached render."""
    feed = VideoFeed()
    feed.on_frame(_frame())
    feed.on_scene(_snapshot())
    seq, default_jpeg = feed.latest()
    seq_a, a = feed.latest_for(OverlayOptions(boxes=False))
    seq_b, b = feed.latest_for(OverlayOptions(selected_id=1))
    assert seq == seq_a == seq_b
    assert len({default_jpeg, a, b}) == 3
    assert feed.latest() == (seq, default_jpeg)  # viewer options never change the default
    assert feed.latest_for(OverlayOptions(boxes=False)) == (seq_a, a)  # cached, same bytes
    for i in range(20):
        feed.latest_for(OverlayOptions(selected_id=100 + i))
    assert len(feed._variants) <= 8


def test_stream_with_options_sends_newest_picture_only() -> None:
    """A viewer stream with options yields the current picture, then each new one."""
    feed = VideoFeed()
    feed.on_frame(_frame())

    async def collect() -> list[bytes]:
        parts: list[bytes] = []
        async for part in mjpeg_stream(feed, poll_seconds=0.001, options=OverlayOptions(hands=False)):
            parts.append(part)
            if len(parts) == 1:
                feed.on_frame(_frame(frame_id=8))
            else:
                feed.close()
        return parts

    parts = asyncio.run(asyncio.wait_for(collect(), timeout=5))
    assert len(parts) == 2 and all(b"\xff\xd8" in p for p in parts)


def test_video_rejects_bad_overlay_values() -> None:
    """Flags must be 0 or 1 and selected_id a non-negative integer."""
    client = TestClient(create_app(DashboardState()))
    for query in ("boxes=2", "hands=yes", "selected_id=-1"):
        reply = client.get(f"/video?{query}")
        assert reply.status_code == 422, query
        assert isinstance(reply.json()["detail"], str)


# Static files and the original endpoints ----------------------------------------------


def test_static_files_are_served_with_module_mime_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ES modules load as JavaScript and stylesheets as CSS from /static."""
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "store.js").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "base.css").write_text("body{}\n", encoding="utf-8")
    monkeypatch.setattr(server_module, "STATIC_DIR", tmp_path)
    client = TestClient(create_app(DashboardState()))
    js = client.get("/static/core/store.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
    css = client.get("/static/base.css")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert client.get("/static/missing.js").status_code == 404


def test_original_endpoints_still_answer() -> None:
    """/, /api/state, /api/simulate-alert and /ws keep their shapes."""
    client = TestClient(create_app(DashboardState(clock=Clock())))
    assert client.get("/").status_code == 200
    state = client.get("/api/state").json()
    assert {"now", "hazard_active_seconds", "latest_warning", "events", "objects"} <= set(state)
    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["events"] == [] and "diagnostics" in first
        client.post("/api/simulate-alert")
        assert ws.receive_json()["latest_simulated_warning"]["simulated"] is True


def test_public_startup_signatures_are_compatible() -> None:
    """register(bus, state=None, serve=True) and create_app(state=None, video=None) still work."""
    import inspect

    from dashboard import Dashboard

    assert list(inspect.signature(register).parameters)[:3] == ["bus", "state", "serve"]
    assert list(inspect.signature(create_app).parameters)[:2] == ["state", "video"]
    assert list(inspect.signature(Dashboard).parameters)[:2] == ["state", "video"]
    create_app()  # no arguments at all
    create_app(DashboardState(), VideoFeed())  # positional, as before


def test_touch_reaches_websocket_through_register() -> None:
    """A TouchEvent on the bus is pushed to an open page as current_touch."""
    bus = SyncBus()
    dashboard = register(bus, DashboardState(clock=Clock()), serve=False)
    client = TestClient(create_app(dashboard.state))
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["current_touch"] is None
        bus.publish(TouchEvent(NOW, 1, "bottle", "Heinz ketchup", "touch", BOTTLE))
        pushed = ws.receive_json()
    assert pushed["current_touch"]["text"] == "Heinz ketchup"


def test_port_probe_ignores_time_wait_but_not_a_listener() -> None:
    """After a restart with a page attached, TIME_WAIT must not block the dashboard."""
    import socket
    import sys

    from dashboard.server import _port_is_free

    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen()
    port = server.getsockname()[1]
    client = socket.create_connection(("127.0.0.1", port))
    accepted, _ = server.accept()
    assert _port_is_free("127.0.0.1", port) is False  # still listening
    accepted.close()  # server side closes first, so the server port goes to TIME_WAIT
    server.close()
    client.close()
    if sys.platform != "win32":
        assert _port_is_free("127.0.0.1", port) is True
