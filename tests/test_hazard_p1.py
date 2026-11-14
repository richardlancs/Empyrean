"""Person 1 tests for vehicle growth, shared cooldown and mocked Grok."""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np

from contracts import FrameResult, HazardEvent, TrackedObject
from hazard.hazard import HazardDetector, parse_hazard_response


class Clock:
    """Allow deterministic cooldown and Grok interval tests."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        """Return controlled monotonic time."""
        return self.now


def frame(ts: float, side: float) -> FrameResult:
    """Build a frame containing a growing car track."""
    return FrameResult(
        ts, int(ts * 5), np.zeros((360, 640, 3), dtype=np.uint8),
        [TrackedObject(11, "car", 0.93, (10., 10., 10. + side, 10. + side))], [],
    )


def test_tier_a_vehicle_growth_and_shared_cooldown(monkeypatch: Any) -> None:
    """Emit on growth above threshold, then suppress repeat events during cooldown."""
    monkeypatch.delenv("GROK_API_KEY", raising=False)
    clock = Clock()
    events: list[HazardEvent] = []
    detector = HazardDetector(events.append, clock=clock)
    detector.on_frame(frame(0.0, 130.0))
    clock.now = 0.2
    detector.on_frame(frame(0.2, 170.0))
    assert len(events) == 1
    assert (events[0].type, events[0].source) == ("vehicle", "yolo")
    clock.now = 0.4
    detector.on_frame(frame(0.4, 190.0))
    assert len(events) == 1
    clock.now = 3.7
    detector.on_frame(frame(3.7, 140.0))
    clock.now = 3.9
    detector.on_frame(frame(3.9, 200.0))
    assert len(events) == 2
    detector.stop()


def test_tier_b_mocked_response_and_local_tier_remains(monkeypatch: Any) -> None:
    """Mock Grok JSON and ensure the worker emits once without blocking on_frame."""
    monkeypatch.setenv("GROK_API_KEY", "test-only")
    monkeypatch.setenv("GROK_MODEL", "mock-model")
    done = threading.Event()
    events: list[HazardEvent] = []

    def mocked_grok(image: Any, key: str, model: str) -> tuple[str, float] | None:
        assert image.shape == (360, 640, 3)
        result = parse_hazard_response({"output_text":
            '{"hazard": true, "type": "stairs_down", "confidence": 0.9}'})
        done.set()
        return result

    detector = HazardDetector(events.append, grok_request=mocked_grok)
    try:
        start = time.monotonic()
        detector.on_frame(FrameResult(time.time(), 0, np.zeros((360, 640, 3),
                                                 dtype=np.uint8)))
        assert time.monotonic() - start < 0.2
        assert done.wait(timeout=1.0)
        end = time.monotonic() + 1.0
        while not events and time.monotonic() < end:
            time.sleep(0.01)
        assert len(events) == 1
        assert (events[0].type, events[0].source) == ("stairs_down", "grok")
    finally:
        detector.stop()


def test_grok_below_threshold_is_ignored() -> None:
    """Invalid or low-confidence JSON must never raise an alarm."""
    assert parse_hazard_response({"output_text":
        '{"hazard": true, "type": "obstacle", "confidence": 0.2}'}) is None
    assert parse_hazard_response({"output_text":
        '{"hazard": false, "type": "none", "confidence": 0.9}'}) is None


def test_httpx_payload_uses_scaled_jpeg_and_timeout(monkeypatch: Any) -> None:
    """Tier B uses the specified image width and timeout in the Responses API."""
    import base64
    import cv2

    from config.thresholds import HAZARD_GROK_TIMEOUT_SECONDS, HAZARD_GROK_WIDTH
    from hazard import hazard

    observed: dict[str, Any] = {}

    class FakeResponse:
        """Return JSON text in the xAI response envelope."""

        def raise_for_status(self) -> None:
            """Simulate a successful request."""

        def json(self) -> dict[str, str]:
            """Give the detector a valid hazard answer."""
            return {"output_text":
                    '{"hazard": true, "type": "obstacle", "confidence": 0.8}'}

    def fake_post(url: str, **kwargs: Any) -> FakeResponse:
        """Record the outgoing payload without sending anything."""
        observed.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(hazard.httpx, "post", fake_post)
    image = np.zeros((360, 640, 3), dtype=np.uint8)
    assert hazard.request_grok(image, "test", "mock") == ("obstacle", 0.8)
    assert observed["timeout"] == HAZARD_GROK_TIMEOUT_SECONDS
    uri = observed["json"]["input"][0]["content"][0]["image_url"]
    raw = base64.b64decode(uri.partition(",")[2])
    decoded = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[1] == HAZARD_GROK_WIDTH
