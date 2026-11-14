"""Smoke tests for the dashboard camera feed: overlays, the bus wiring and /video."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

import cv2
import httpx
import numpy as np

from config import PROCESS_HEIGHT, PROCESS_WIDTH
from contracts import FrameResult, Hand, SceneObject, SceneSnapshot, TrackedObject
from dashboard import Dashboard, DashboardState, VideoFeed, register
from dashboard.video import (
    BOUNDARY,
    GREEN,
    HAND_DOT,
    YELLOW,
    mjpeg_stream,
    render_frame,
)

NOW = 1_800_000_000.0
BOTTLE = (100.0, 80.0, 200.0, 240.0)
CUP = (320.0, 150.0, 420.0, 290.0)


class SyncBus:
    """Deliver each message straight to its subscribers."""

    def __init__(self) -> None:
        """Start with no subscribers."""
        self.handlers: dict[type, list[Callable[[Any], None]]] = {}

    def subscribe(self, msg_type: type, handler: Callable[[Any], None]) -> None:
        """Register handler for messages of exactly msg_type."""
        self.handlers.setdefault(msg_type, []).append(handler)

    def publish(self, msg: object) -> None:
        """Call every handler for this message type."""
        for handler in self.handlers.get(type(msg), []):
            handler(msg)


def _frame(frame_id: int = 7) -> FrameResult:
    """A black frame with a bottle, a cup and one hand."""
    image = np.zeros((PROCESS_HEIGHT, PROCESS_WIDTH, 3), dtype=np.uint8)
    return FrameResult(
        ts=NOW,
        frame_id=frame_id,
        image=image,
        objects=[
            TrackedObject(1, "bottle", 0.9, BOTTLE),
            TrackedObject(2, "cup", 0.9, CUP),
        ],
        hands=[
            Hand("right", (150.0, 120.0), (160.0, 130.0), (130.0, 100.0, 190.0, 160.0))
        ],
    )


def _snapshot(frame_id: int = 7) -> SceneSnapshot:
    """The bottle being touched and the cup held."""
    return SceneSnapshot(
        ts=NOW,
        frame_id=frame_id,
        objects=[
            SceneObject(1, "bottle", "Heinz ketchup", "touching", BOTTLE, NOW),
            SceneObject(2, "cup", "", "held", CUP, NOW),
        ],
    )


def _close(pixel: np.ndarray, bgr: tuple[int, int, int], tolerance: int = 40) -> bool:
    """True if a pixel is within tolerance of a BGR colour on every channel."""
    return all(abs(int(p) - c) <= tolerance for p, c in zip(pixel, bgr))


def test_render_draws_state_colours_and_hand_dots() -> None:
    """Touching is green, held is yellow, fingertips get dots, and the bus image is unchanged."""
    frame = _frame()
    image = render_frame(frame, _snapshot())
    assert image.shape == (PROCESS_HEIGHT, PROCESS_WIDTH, 3)
    assert _close(image[200, 100], GREEN)  # left edge of the touched bottle
    assert _close(image[250, 320], YELLOW)  # left edge of the held cup
    assert _close(image[130, 160], HAND_DOT)  # index fingertip
    assert not frame.image.any()  # scene crops this image, so it must stay clean


def test_render_without_scene_draws_plain_boxes() -> None:
    """With no SceneSnapshot, detections are still outlined, in grey."""
    image = render_frame(_frame(), None)
    b, g, r = (int(v) for v in image[200, 100])
    assert b == g == r and b > 0


def test_old_snapshot_is_ignored() -> None:
    """A snapshot more than a second of frames old is not used for colours."""
    image = render_frame(_frame(frame_id=100), _snapshot(frame_id=1))
    assert not _close(image[200, 100], GREEN)


def test_register_feeds_the_video_from_the_bus() -> None:
    """FrameResult then SceneSnapshot on the bus each produce a new JPEG."""
    bus = SyncBus()
    feed = register(bus, DashboardState(clock=lambda: NOW), serve=False).video
    start, placeholder = feed.latest()
    bus.publish(_frame())
    after_frame, _ = feed.latest()
    bus.publish(_snapshot())
    after_scene, jpeg = feed.latest()
    assert start < after_frame < after_scene
    assert jpeg != placeholder
    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape == (PROCESS_HEIGHT, PROCESS_WIDTH, 3)


def test_stream_sends_placeholder_then_new_frames_then_stops() -> None:
    """The MJPEG generator yields the current picture, each new one, and ends on close."""
    feed = VideoFeed()

    async def collect() -> list[bytes]:
        """Read parts, publishing one frame after the first and closing after the second."""
        parts: list[bytes] = []
        async for part in mjpeg_stream(feed, poll_seconds=0.001):
            parts.append(part)
            if len(parts) == 1:
                feed.on_frame(_frame())
            else:
                feed.close()
        return parts

    parts = asyncio.run(asyncio.wait_for(collect(), timeout=5))
    assert len(parts) == 2
    for part in parts:
        assert part.startswith(f"--{BOUNDARY}\r\nContent-Type: image/jpeg".encode())
        assert b"\xff\xd8" in part  # JPEG start marker


def test_video_endpoint_streams_mjpeg_from_the_real_server() -> None:
    """GET /video on the served page returns multipart JPEG parts."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    dashboard = Dashboard(DashboardState(clock=lambda: NOW))
    dashboard.video.on_frame(_frame())
    assert dashboard.serve(port=port) is True
    try:
        deadline = time.monotonic() + 5.0
        while True:
            try:
                with httpx.stream(
                    "GET", f"http://127.0.0.1:{port}/video", timeout=5
                ) as reply:
                    assert reply.status_code == 200
                    assert reply.headers["content-type"].startswith(
                        "multipart/x-mixed-replace"
                    )
                    received = b""
                    for chunk in reply.iter_bytes():
                        received += chunk
                        if b"\xff\xd9" in received:  # JPEG end marker
                            break
                break
            except httpx.ConnectError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        assert received.startswith(f"--{BOUNDARY}".encode())
        assert b"\xff\xd8" in received
    finally:
        dashboard.stop()
    assert not dashboard._thread.is_alive()


def test_label_near_right_edge_stays_inside_the_frame() -> None:
    """A long label on a box at the right edge is shifted left, not cut off."""
    frame = _frame()
    edge_box = (600.0, 100.0, 639.0, 200.0)
    snapshot = SceneSnapshot(
        ts=NOW,
        frame_id=frame.frame_id,
        objects=[SceneObject(5, "chair", "HON office chair", "idle", edge_box, NOW)],
    )
    image = render_frame(frame, snapshot)
    tag_row = image[90]  # just above the box, where the white tag sits
    white = [x for x in range(PROCESS_WIDTH) if tag_row[x].min() > 200]
    assert white and min(white) < 600  # tag starts left of the box
