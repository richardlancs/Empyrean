"""Publish unmirrored camera frames with COCO tracks and two hand landmark sets."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

import cv2

from config.thresholds import (
    DET_MIN_AREA_FRACTION,
    DET_MIN_CONFIDENCE,
    PROCESS_FPS,
    PROCESS_HEIGHT,
    PROCESS_WIDTH,
)
from contracts import FrameResult, Hand, TrackedObject

log = logging.getLogger("vision")
MODEL_DIR = Path(__file__).resolve().parent / "models"
YOLO_WEIGHTS = MODEL_DIR / "yolo11s.pt"
HAND_MODEL = MODEL_DIR / "hand_landmarker.task"
CAPTURE_WIDTH = PROCESS_WIDTH * 2
CAPTURE_HEIGHT = PROCESS_HEIGHT * 2
# Camera recovery timing. Module constants, not SPEC.md section 9 thresholds.
READ_RETRY_SECONDS = 0.05
READ_FAILURES_BEFORE_REOPEN = 20
REOPEN_WAIT_SECONDS = 1.0


def _clamp(value: float, maximum: int) -> float:
    return max(0.0, min(float(maximum), value))


def tracked_objects(result: Any) -> list[TrackedObject]:
    """Convert Ultralytics tracked COCO boxes into filtered contract objects."""
    boxes = result.boxes
    if boxes is None or boxes.id is None:
        return []
    names = result.names
    objects: list[TrackedObject] = []
    for box, score, class_id, object_id in zip(
        boxes.xyxy.tolist(),
        boxes.conf.tolist(),
        boxes.cls.tolist(),
        boxes.id.tolist(),
    ):
        confidence = float(score)
        label = str(names[int(class_id)])
        x1 = _clamp(float(box[0]), PROCESS_WIDTH)
        y1 = _clamp(float(box[1]), PROCESS_HEIGHT)
        x2 = _clamp(float(box[2]), PROCESS_WIDTH)
        y2 = _clamp(float(box[3]), PROCESS_HEIGHT)
        area = (x2 - x1) * (y2 - y1)
        if (
            label == "person"
            or confidence < DET_MIN_CONFIDENCE
            or area < DET_MIN_AREA_FRACTION * PROCESS_WIDTH * PROCESS_HEIGHT
            or x2 <= x1
            or y2 <= y1
        ):
            continue
        objects.append(TrackedObject(int(object_id), label, confidence, (x1, y1, x2, y2)))
    return objects


def tracked_hands(result: Any) -> list[Hand]:
    """Map MediaPipe's first two sets of 21 landmarks to processed-frame pixels."""
    hands: list[Hand] = []
    handedness = getattr(result, "handedness", [])
    for index, landmarks in enumerate(result.hand_landmarks[:2]):
        if len(landmarks) < 21:
            continue
        points = [
            (_clamp(mark.x * PROCESS_WIDTH, PROCESS_WIDTH),
             _clamp(mark.y * PROCESS_HEIGHT, PROCESS_HEIGHT))
            for mark in landmarks
        ]
        xs, ys = zip(*points)
        box = (min(xs), min(ys), max(xs), max(ys))
        if box[0] >= box[2] or box[1] >= box[3]:
            continue
        side = "unknown"
        if index < len(handedness) and handedness[index]:
            category = handedness[index][0]
            label = str(getattr(category, "category_name", "")).lower()
            # Handedness is returned for selfie/mirrored frames; our camera isn't mirrored.
            side = {"left": "right", "right": "left"}.get(label, "unknown")
        hands.append(Hand(side, points[4], points[8], box))
    return hands


class VisionProcessor:
    """Run pretrained tracking models on one processed-size frame."""

    def __init__(self, detector: Any, hand_landmarker: Any, mp_module: Any) -> None:
        self.detector = detector
        self.hand_landmarker = hand_landmarker
        self.mp = mp_module
        self._last_ms = -1
        self._start_monotonic = time.monotonic()

    def process(self, image: Any, frame_id: int, captured_ts: float) -> FrameResult:
        """Build a single FrameResult with the original, unmirrored BGR image."""
        processed = cv2.resize(image, (PROCESS_WIDTH, PROCESS_HEIGHT))
        results = self.detector.track(
            processed,
            persist=True,
            tracker="bytetrack.yaml",
            conf=DET_MIN_CONFIDENCE,
            verbose=False,
        )
        objects = tracked_objects(results[0]) if results else []
        rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
        mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = max(int((time.monotonic() - self._start_monotonic) * 1000),
                           self._last_ms + 1)
        self._last_ms = timestamp_ms
        hands = tracked_hands(self.hand_landmarker.detect_for_video(mp_image, timestamp_ms))
        return FrameResult(
            ts=captured_ts,
            frame_id=frame_id,
            image=processed,
            objects=objects,
            hands=hands,
        )

    def close(self) -> None:
        """Close MediaPipe resources after capture ends."""
        self.hand_landmarker.close()


def load_processor() -> VisionProcessor:
    """Load local pretrained YOLO/MediaPipe assets; never download during capture."""
    if not YOLO_WEIGHTS.is_file():
        raise FileNotFoundError(
            f"Missing YOLO COCO small weights at {YOLO_WEIGHTS}. "
            "Run python -c \'from ultralytics import YOLO; YOLO(\"yolo11s.pt\")\' "
            "in a setup shell, then move yolo11s.pt into vision/models/."
        )
    if not HAND_MODEL.is_file():
        raise FileNotFoundError(
            f"Missing MediaPipe hand model at {HAND_MODEL}. "
            "Download hand_landmarker.task from "
            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
            "hand_landmarker/float16/1/hand_landmarker.task "
            "and put it in vision/models/."
        )
    import mediapipe as mp
    from ultralytics import YOLO

    detector = YOLO(str(YOLO_WEIGHTS))
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(HAND_MODEL)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
    )
    hands = mp.tasks.vision.HandLandmarker.create_from_options(options)
    return VisionProcessor(detector, hands, mp)


class LatestCamera:
    """Capture continuously and overwrite older frames rather than queueing."""

    def __init__(self, index: int) -> None:
        self._index = index
        self._capture = cv2.VideoCapture(index)
        if not self._capture.isOpened():
            self._capture.release()
            raise RuntimeError(f"Camera index {index} unavailable; adjust CAMERA_INDEX in .env")
        self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
        self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._latest: tuple[int, float, Any] | None = None
        self._sequence = 0
        self._thread = threading.Thread(target=self._capture_loop, name="vision-capture", daemon=True)
        self._thread.start()

    def _reopen(self) -> bool:
        """Release and reopen the device after repeated read failures."""
        self._capture.release()
        capture = cv2.VideoCapture(self._index)
        if not capture.isOpened():
            capture.release()
            return False
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture = capture
        return True

    def _capture_loop(self) -> None:
        failures = 0
        while not self._stop.is_set():
            ok, frame = self._capture.read()
            if not ok:
                failures += 1
                if failures == 1:
                    log.warning("Camera read failed; retrying")
                if failures % READ_FAILURES_BEFORE_REOPEN == 0:
                    if self._reopen():
                        log.info("Camera reopened")
                    else:
                        self._stop.wait(REOPEN_WAIT_SECONDS)
                else:
                    self._stop.wait(READ_RETRY_SECONDS)
                continue
            if failures:
                log.info("Camera reads recovered after %d failures", failures)
                failures = 0
            captured_ts = time.time()
            with self._lock:
                self._latest = (self._sequence, captured_ts, frame)
                self._sequence += 1

    def latest_after(self, sequence: int) -> tuple[int, float, Any] | None:
        """Return the newest captured frame only when it is newer than sequence."""
        with self._lock:
            if self._latest is None or self._latest[0] <= sequence:
                return None
            return self._latest

    @property
    def stopped(self) -> bool:
        """Report whether camera capture has ended."""
        return self._stop.is_set()

    def close(self) -> None:
        """Stop reader and release the OpenCV device."""
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._capture.release()


class Vision:
    """Drive frame processing at PROCESS_FPS on a background producer."""

    def __init__(self, publish: Any) -> None:
        self._publish = publish
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="vision", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        processor: VisionProcessor | None = None
        camera: LatestCamera | None = None
        try:
            processor = load_processor()
            index = int(os.environ.get("CAMERA_INDEX", "0"))
            camera = LatestCamera(index)
            frame_id = 0
            last_sequence = -1
            next_at = time.monotonic()
            while not self._stop.is_set() and not camera.stopped:
                delay = next_at - time.monotonic()
                if delay > 0:
                    self._stop.wait(min(delay, 0.05))
                    continue
                latest = camera.latest_after(last_sequence)
                if latest is None:
                    self._stop.wait(0.005)
                    continue
                last_sequence, captured_ts, image = latest
                result = processor.process(image, frame_id, captured_ts)
                self._publish(result)
                frame_id += 1
                elapsed = time.time() - captured_ts
                if elapsed > 0.150 and frame_id % PROCESS_FPS == 0:
                    log.warning("Capture-to-publish latency %.0f ms exceeds 150 ms target",
                                elapsed * 1000)
                next_at = max(next_at + 1.0 / PROCESS_FPS, time.monotonic())
        except (FileNotFoundError, ValueError, RuntimeError, ImportError) as exc:
            log.error("Vision unavailable: %s", exc)
        except Exception:
            log.exception("Vision stopped due to an error")
        finally:
            if camera is not None:
                camera.close()
            if processor is not None:
                processor.close()

    def stop(self) -> None:
        """Request shutdown of the capture and processing workers."""
        self._stop.set()
        self._thread.join(timeout=2.0)


def register(bus: Any) -> Vision:
    """Publish live FrameResults from the configured camera to the bus."""
    return Vision(bus.publish)
