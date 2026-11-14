"""Person 1 contract and filter tests using synthetic pretrained-model results."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np

from contracts import FrameResult, Hand, TrackedObject
from fakes.vision.fake_vision import scripted_frame
from vision.vision import VisionProcessor


class Array:
    """Provide the list conversion used by the Ultralytics boxes interface."""

    def __init__(self, data: list[Any]) -> None:
        self.data = data

    def tolist(self) -> list[Any]:
        """Return the synthetic values."""
        return self.data


class FakeYOLO:
    """Return one valid box plus a low-confidence, person, and tiny box."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def track(self, image: Any, **kwargs: Any) -> list[Any]:
        """Mimic persistent tracking with deterministic IDs."""
        self.calls.append(kwargs)
        boxes = SimpleNamespace(
            xyxy=Array([[10, 20, 110, 170], [200, 30, 330, 200],
                        [20, 20, 180, 180], [50, 50, 60, 60]]),
            conf=Array([0.9, 0.2, 0.96, 0.93]),
            cls=Array([0, 0, 1, 0]),
            id=Array([7, 8, 9, 10]),
        )
        return [SimpleNamespace(boxes=boxes, names={0: "bottle", 1: "person"})]


class FakeHands:
    """Return one MediaPipe-style hand with 21 landmarks."""

    def detect_for_video(self, image: Any, timestamp: int) -> Any:
        """Return a synthetic right-hand classification and landmarks."""
        landmarks = [SimpleNamespace(x=(0.3 + i * 0.003), y=(0.3 + i * 0.003))
                     for i in range(21)]
        return SimpleNamespace(
            hand_landmarks=[landmarks],
            handedness=[[SimpleNamespace(category_name="Left")]],
        )

    def close(self) -> None:
        """Release nothing in the fake."""


class FakeMP:
    """Mimic MediaPipe's image constructor interface."""

    ImageFormat = SimpleNamespace(SRGB=0)

    @staticmethod
    def Image(image_format: int, data: Any) -> Any:
        """Return a fake image without modifying BGR input."""
        return data


def test_frame_result_and_detection_filters() -> None:
    """Vision processing publishes contracted dimensions, ids, hands and filters."""
    detector = FakeYOLO()
    processor = VisionProcessor(detector, FakeHands(), FakeMP)
    raw = np.zeros((720, 1280, 3), dtype=np.uint8)
    raw[:, :640, :] = [7, 8, 9]
    result = processor.process(raw, frame_id=0, captured_ts=1234.5)
    assert type(result) is FrameResult
    assert (result.ts, result.frame_id) == (1234.5, 0)
    assert result.image.shape == (360, 640, 3)
    assert result.image[0, 0].tolist() == [7, 8, 9]
    assert result.objects == [TrackedObject(7, "bottle", 0.9, (10., 20., 110., 170.))]
    assert len(result.hands) == 1 and type(result.hands[0]) is Hand
    assert result.hands[0].side == "right"
    assert detector.calls[0]["persist"] is True
    assert detector.calls[0]["tracker"] == "bytetrack.yaml"
    processor.close()


def test_fake_vision_stabilizes_then_touches_and_releases() -> None:
    """A stable bottle is contacted only after the one-second establishment period."""
    frames = [scripted_frame(i, i / 5) for i in range(30)]
    assert all(frame.objects[0].object_id == 1 for frame in frames)
    assert all(not frame.hands for frame in frames[:10])
    assert all(frame.hands for frame in frames[10:25])
    assert all(not frame.hands for frame in frames[25:])
    assert all(frame.image.shape == (360, 640, 3) for frame in frames)


class FlakyCapture:
    """Stand in for cv2.VideoCapture with a scripted list of read results."""

    def __init__(self, reads: list[bool]) -> None:
        self.reads = reads
        self.released = False

    def isOpened(self) -> bool:
        """Report the device as open."""
        return True

    def set(self, _prop: int, _value: float) -> bool:
        """Accept capture settings."""
        return True

    def read(self) -> tuple[bool, Any]:
        """Return the next scripted result, then keep succeeding."""
        ok = self.reads.pop(0) if self.reads else True
        return ok, np.zeros((720, 1280, 3), dtype=np.uint8) if ok else None

    def release(self) -> None:
        """Record the release."""
        self.released = True


def _wait_for_frame(camera: Any, timeout: float = 3.0) -> bool:
    """Poll until the camera has published a frame."""
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if camera.latest_after(-1) is not None:
            return True
        time.sleep(0.01)
    return False


def test_camera_survives_a_few_failed_reads(monkeypatch: Any) -> None:
    """Startup read failures do not end capture."""
    from vision import vision

    device = FlakyCapture([False, False, False, True])
    monkeypatch.setattr(vision.cv2, "VideoCapture", lambda _index: device)
    monkeypatch.setattr(vision, "READ_RETRY_SECONDS", 0.001)
    camera = vision.LatestCamera(0)
    try:
        assert _wait_for_frame(camera)
        assert not camera.stopped
    finally:
        camera.close()


def test_camera_reopens_after_repeated_failures(monkeypatch: Any) -> None:
    """A device that keeps failing is released and reopened."""
    from vision import vision

    broken = FlakyCapture([False] * 100)
    fresh = FlakyCapture([])
    devices = [broken, fresh]
    monkeypatch.setattr(vision.cv2, "VideoCapture", lambda _index: devices.pop(0))
    monkeypatch.setattr(vision, "READ_RETRY_SECONDS", 0.001)
    monkeypatch.setattr(vision, "READ_FAILURES_BEFORE_REOPEN", 5)
    camera = vision.LatestCamera(0)
    try:
        assert _wait_for_frame(camera)
        assert broken.released
        assert not camera.stopped
    finally:
        camera.close()
