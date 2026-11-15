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
    assert result.objects == [TrackedObject(1, "bottle", 0.9, (10., 20., 110., 170.))]
    assert len(result.hands) == 1 and type(result.hands[0]) is Hand
    assert result.hands[0].side == "right"
    assert len(result.hands[0].landmarks) == 21
    assert result.hands[0].landmarks[8] == result.hands[0].index_tip
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
    monkeypatch.setattr(vision.cv2, "VideoCapture", lambda *_args: device)
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
    monkeypatch.setattr(vision.cv2, "VideoCapture", lambda *_args: devices.pop(0))
    monkeypatch.setattr(vision, "READ_RETRY_SECONDS", 0.001)
    monkeypatch.setattr(vision, "READ_FAILURES_BEFORE_REOPEN", 5)
    camera = vision.LatestCamera(0)
    try:
        assert _wait_for_frame(camera)
        assert broken.released
        assert not camera.stopped
    finally:
        camera.close()


class FakeWorld:
    """A demo detector: one low-confidence toothpaste whose track id restarts at 1."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def track(self, image: Any, **kwargs: Any) -> list[Any]:
        """Return a box that only passes the demo confidence threshold."""
        self.calls.append(kwargs)
        boxes = SimpleNamespace(
            xyxy=Array([[300, 100, 420, 260]]),
            conf=Array([0.3]),
            cls=Array([0]),
            id=Array([1]),
        )
        return [SimpleNamespace(boxes=boxes, names={0: "toothpaste"})]


def test_demo_mode_switches_detector_and_keeps_ids_unique() -> None:
    """Demo mode uses the demo detector, its threshold, a fresh tracker and new ids."""
    from config import DEMO_DET_MIN_CONFIDENCE, DET_MIN_CONFIDENCE

    standard, world = FakeYOLO(), FakeWorld()
    processor = VisionProcessor(standard, FakeHands(), FakeMP, demo_detector=world)
    raw = np.zeros((720, 1280, 3), dtype=np.uint8)
    original = processor.process(raw, 0, 1.0).objects[0]

    assert processor.set_mode("demo") is True
    demo = processor.process(raw, 1, 2.0).objects
    assert [o.class_label for o in demo] == ["toothpaste"]
    assert demo[0].object_id != original.object_id
    assert world.calls[0]["persist"] is False
    assert world.calls[0]["conf"] == DEMO_DET_MIN_CONFIDENCE
    again = processor.process(raw, 2, 3.0).objects
    assert again[0].object_id == demo[0].object_id
    assert world.calls[1]["persist"] is True
    assert len(standard.calls) == 1  # the standard detector does not run in demo mode

    assert processor.set_mode("actual") is True
    back = processor.process(raw, 3, 4.0).objects
    assert [o.class_label for o in back] == ["bottle"]
    assert back[0].object_id not in {original.object_id, demo[0].object_id}
    assert standard.calls[1]["conf"] == DET_MIN_CONFIDENCE
    processor.close()


def test_demo_mode_refused_without_demo_weights() -> None:
    """No usable demo detector: vision keeps Regular running and reports why (DetectorStatus)."""
    import time as _time

    from contracts import DetectorStatus, ModeChange
    from vision.vision import DemoUnavailable, Vision

    processor = VisionProcessor(FakeYOLO(), FakeHands(), FakeMP)
    assert processor.set_mode("demo") is False and processor.mode == "actual"

    def no_demo() -> Any:
        raise DemoUnavailable("No demo-trained checkpoint is installed.")

    published: list[Any] = []
    vision = Vision(published.append, loader=no_demo, start=False)
    vision.on_mode(ModeChange(ts=1.0, mode="demo", request_id="r1"))
    vision._apply_mode(processor)
    deadline = _time.monotonic() + 2
    while len(published) < 2 and _time.monotonic() < deadline:
        _time.sleep(0.01)
    statuses = [m for m in published if isinstance(m, DetectorStatus)]
    assert [(m.state, m.active_mode, m.request_id) for m in statuses] == [
        ("switching", "actual", "r1"),
        ("failed", "actual", "r1"),
    ]
    assert "No demo-trained checkpoint" in statuses[-1].message
    assert statuses[-1].demo_available is False
    vision._apply_mode(processor)  # nothing more to report; Regular keeps running
    assert len(published) == 2 and processor.mode == "actual"
    assert processor.process(np.zeros((720, 1280, 3), dtype=np.uint8), 0, 1.0).objects
    processor.close()


def test_demo_reference_list_is_required_and_read(tmp_path: Any) -> None:
    """The prompt build refuses a folder with no refs.json and reads one that has it."""
    import json

    import pytest

    from vision.build_demo_weights import REFS_FILE, load_refs

    with pytest.raises(FileNotFoundError):
        load_refs(tmp_path)
    refs = [{"file": "keys_1.jpg", "label": "keys", "box": [10.0, 20.0, 110.0, 90.0]}]
    (tmp_path / REFS_FILE).write_text(json.dumps(refs), encoding="utf-8")
    assert load_refs(tmp_path) == refs


class ChangingDetector:
    """Return a sequence of single-box results with deliberately reused raw IDs."""

    def __init__(self, labels: list[str], sides: list[float] | None = None) -> None:
        self.labels = labels
        self.sides = sides or [170.0] * len(labels)
        self.calls = 0
        self.predictor = SimpleNamespace(args=SimpleNamespace(iou=0.7))

    def track(self, image: Any, **kwargs: Any) -> list[Any]:
        """Return the next class and size under raw tracker ID 1."""
        index = min(self.calls, len(self.labels) - 1)
        self.calls += 1
        side = self.sides[index]
        boxes = SimpleNamespace(
            xyxy=Array([[10.0, 10.0, 10.0 + side, 10.0 + side]]),
            conf=Array([0.9]), cls=Array([0]), id=Array([1]),
        )
        return [SimpleNamespace(boxes=boxes, names={0: self.labels[index]})]


def test_changed_tracker_class_cannot_reuse_a_cached_scene_name() -> None:
    """A bottle-to-laptop raw ID switch must not attach water bottle to the laptop."""
    from contracts import NameResult
    from scene import SceneDatabase

    processor = VisionProcessor(
        ChangingDetector(["bottle", "bottle", "laptop"]), FakeHands(), FakeMP,
    )
    scene = SceneDatabase(lambda _topic, _message: None, stable_frames=1)
    raw = np.zeros((360, 640, 3), dtype=np.uint8)
    first = processor.process(raw, 0, 0.0)
    scene.handle_frame(first)
    bottle_id = first.objects[0].object_id
    scene.handle_name(NameResult(0.1, bottle_id, "water bottle", True))
    second = processor.process(raw, 1, 0.2)
    assert second.objects[0].object_id == bottle_id
    scene.handle_frame(second)
    third = processor.process(raw, 2, 0.4)
    laptop_id = third.objects[0].object_id
    assert laptop_id != bottle_id
    objects = {obj.object_id: obj for obj in scene.handle_frame(third).objects}
    assert objects[laptop_id].class_label == "laptop"
    assert objects[laptop_id].name == ""
    processor.close()


def test_custom_demo_keeps_vehicle_growth_alarms_and_separate_ids(monkeypatch: Any) -> None:
    """Demo items and COCO vehicles coexist, even when both trackers use raw ID 1."""
    from hazard.hazard import HazardDetector

    monkeypatch.delenv("GROK_API_KEY", raising=False)
    events: list[Any] = []
    hazard = HazardDetector(events.append)
    coco = ChangingDetector(["car", "car"], [130.0, 170.0])
    demo = ChangingDetector(["keys", "keys"])
    processor = VisionProcessor(coco, FakeHands(), FakeMP, demo, True)
    assert processor.set_mode("demo")
    raw = np.zeros((360, 640, 3), dtype=np.uint8)
    try:
        first = processor.process(raw, 0, 0.0)
        second = processor.process(raw, 1, 0.2)
        assert {obj.class_label for obj in first.objects} == {"car", "keys"}
        assert len({obj.object_id for obj in first.objects}) == 2
        assert {obj.class_label: obj.object_id for obj in first.objects} == {
            obj.class_label: obj.object_id for obj in second.objects
        }
        hazard.on_frame(first)
        hazard.on_frame(second)
        assert [(event.type, event.source) for event in events] == [("vehicle", "yolo")]
        assert coco.calls == demo.calls == 2
    finally:
        processor.close()
        hazard.stop()


def test_custom_demo_does_not_publish_unrelated_coco_objects() -> None:
    """A laptop from COCO cannot be confused with an eight-class demo detection."""
    coco = ChangingDetector(["laptop"])
    demo = ChangingDetector(["charger"])
    processor = VisionProcessor(coco, FakeHands(), FakeMP, demo, True)
    processor.set_mode("demo")
    frame = processor.process(np.zeros((360, 640, 3), dtype=np.uint8), 0, 0.0)
    assert [obj.class_label for obj in frame.objects] == ["charger"]
    assert coco.calls == 1
    processor.close()


def test_custom_demo_preserves_coco_demo_items_and_deduplicates_them() -> None:
    """A confident COCO bottle stays available without a duplicate custom bottle box."""
    coco = ChangingDetector(["bottle"])
    demo = ChangingDetector(["water bottle"])
    processor = VisionProcessor(coco, FakeHands(), FakeMP, demo, True)
    processor.set_mode("demo")
    image = np.zeros((360, 640, 3), dtype=np.uint8)
    first = processor.process(image, 0, 0.0)
    second = processor.process(image, 1, 0.2)
    assert [obj.class_label for obj in first.objects] == ["water bottle"]
    assert first.objects[0].object_id == second.objects[0].object_id
    assert first.objects[0].confidence == 0.9
    processor.close()


def test_trained_toothpaste_suppresses_an_overlapping_coco_bottle_guess() -> None:
    """The known COCO mislabelling of toothpaste as bottle cannot create two objects."""
    coco = ChangingDetector(["bottle"])
    demo = ChangingDetector(["toothpaste"])
    processor = VisionProcessor(coco, FakeHands(), FakeMP, demo, True)
    processor.set_mode("demo")
    frame = processor.process(np.zeros((360, 640, 3), dtype=np.uint8), 0, 0.0)
    assert [obj.class_label for obj in frame.objects] == ["toothpaste"]
    assert frame.objects[0].confidence == 0.9
    processor.close()


def test_windows_camera_uses_directshow_on_open_and_reopen(monkeypatch: Any) -> None:
    """A Windows restart must not return to the backend that hung the real webcam."""
    from vision import vision

    calls: list[tuple[Any, ...]] = []
    devices = [FlakyCapture([]), FlakyCapture([])]

    def open_capture(*args: Any) -> FlakyCapture:
        calls.append(args)
        return devices.pop(0)

    monkeypatch.setattr(vision.sys, "platform", "win32")
    monkeypatch.setattr(vision.cv2, "VideoCapture", open_capture)
    camera = vision.LatestCamera(1)
    try:
        assert _wait_for_frame(camera)
        assert camera._reopen()
        assert calls == [(1, vision.cv2.CAP_DSHOW), (1, vision.cv2.CAP_DSHOW)]
    finally:
        camera.close()


def test_capture_uses_own_explicit_webcam_instead_of_another_laptops_env(
    monkeypatch: Any, tmp_path: Any,
) -> None:
    """A teammate's explicit index 0 overrides the demo laptop's CAMERA_INDEX=1."""
    import json

    from vision import capture_demo_refs as capture

    opened: list[int] = []
    released: list[bool] = []
    device = SimpleNamespace(
        set=lambda *_args: True,
        get=lambda prop: 1280 if prop == capture.cv2.CAP_PROP_FRAME_WIDTH else 720,
        release=lambda: released.append(True),
    )

    def open_device(index: int) -> Any:
        opened.append(index)
        return device

    monkeypatch.setenv("CAMERA_INDEX", "1")
    monkeypatch.setattr(capture, "load_dotenv", lambda: None)
    monkeypatch.setattr(capture, "_open_camera", open_device)
    monkeypatch.setattr(capture, "_read_frame", lambda _camera: np.zeros((360, 640, 3), np.uint8))
    monkeypatch.setattr(capture.cv2, "imshow", lambda *_args: None)
    monkeypatch.setattr(capture.cv2, "setWindowProperty", lambda *_args: None)
    monkeypatch.setattr(capture.cv2, "waitKey", lambda _delay: ord("q"))
    monkeypatch.setattr(capture.cv2, "destroyAllWindows", lambda: None)
    assert capture.capture(tmp_path, ("keys",), camera_index=0) == 0
    assert opened == [0]
    assert released == [True]
    info = json.loads((tmp_path / "capture_info.json").read_text())
    assert info["camera_index"] == 0
    assert info["items"] == ["keys"]
    assert (info["processed_width"], info["processed_height"]) == (640, 360)


class OffFrameHands(FakeHands):
    """Return a hand whose wrist and knuckles lie below the frame."""

    def detect_for_video(self, image: Any, timestamp: int) -> Any:
        """Return landmarks with the lower half outside the image."""
        landmarks = [SimpleNamespace(x=0.4 + i * 0.01, y=1.1 - i * 0.02) for i in range(21)]
        return SimpleNamespace(
            hand_landmarks=[landmarks],
            handedness=[[SimpleNamespace(category_name="Left")]],
        )


def test_landmarks_keep_off_frame_points_unclamped() -> None:
    """Pointing needs true knuckle positions, so landmarks are not clamped to the frame."""
    processor = VisionProcessor(FakeYOLO(), OffFrameHands(), FakeMP)
    result = processor.process(np.zeros((720, 1280, 3), dtype=np.uint8), frame_id=0, captured_ts=1.0)
    hand = result.hands[0]
    assert hand.landmarks[0][1] > 360.0
    assert hand.box[3] <= 360.0
    assert all(0.0 <= value <= 360.0 for value in (hand.thumb_tip[1], hand.index_tip[1]))
    processor.close()
