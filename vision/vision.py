"""Publish unmirrored camera frames with tracked objects and two hand landmark sets.

Actual mode detects with COCO yolo11s.pt. Demo mode prefers a locally fine-tuned
detector for the eight demo objects, while COCO still supplies vehicle boxes.
Without trained weights it falls back to the existing YOLOE reference prompts.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Literal

import cv2

from config.thresholds import (
    DEMO_DET_MIN_CONFIDENCE,
    DET_MIN_AREA_FRACTION,
    DET_MIN_CONFIDENCE,
    PROCESS_FPS,
    PROCESS_HEIGHT,
    PROCESS_WIDTH,
)
from contracts import FrameResult, Hand, ModeChange, TrackedObject
from vision.build_demo_weights import DEMO_OBJECTS, VEHICLE_LABELS

log = logging.getLogger("vision")
MODEL_DIR = Path(__file__).resolve().parent / "models"
YOLO_WEIGHTS = MODEL_DIR / "yolo11s.pt"
TRAINED_DEMO_WEIGHTS = MODEL_DIR / "demo-yolo11s.pt"
TRAINED_DEMO_IMAGE_SIZE = 416  # Internal inference size used by the approved training run.
COCO_DEMO_LABELS = {"bottle": "water bottle", "cell phone": "phone", "toothbrush": "toothbrush"}
# Demo mode: pretrained YOLOE plus prompts built once by
# `python -m vision.build_demo_weights`. Neither is downloaded at run time.
DEMO_WEIGHTS = MODEL_DIR / "yoloe-11s-seg.pt"
DEMO_PROMPTS = MODEL_DIR / "demo-prompts.pt"
Mode = Literal["actual", "demo"]
HAND_MODEL = MODEL_DIR / "hand_landmarker.task"
CAPTURE_WIDTH = PROCESS_WIDTH * 2
CAPTURE_HEIGHT = PROCESS_HEIGHT * 2
# Camera recovery timing. Module constants, not SPEC.md section 9 thresholds.
READ_RETRY_SECONDS = 0.05
READ_FAILURES_BEFORE_REOPEN = 20
REOPEN_WAIT_SECONDS = 1.0


def _clamp(value: float, maximum: int) -> float:
    return max(0.0, min(float(maximum), value))


def tracked_objects(
    result: Any, min_confidence: float = DET_MIN_CONFIDENCE, id_offset: int = 0
) -> list[TrackedObject]:
    """Convert Ultralytics tracked boxes into filtered contract objects.

    id_offset is added to every track id so ids stay unique across a mode switch.
    """
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
        # Demo prompts are named "keys/3"; report the plain object name.
        label = str(names[int(class_id)]).split("/", 1)[0]
        x1 = _clamp(float(box[0]), PROCESS_WIDTH)
        y1 = _clamp(float(box[1]), PROCESS_HEIGHT)
        x2 = _clamp(float(box[2]), PROCESS_WIDTH)
        y2 = _clamp(float(box[3]), PROCESS_HEIGHT)
        area = (x2 - x1) * (y2 - y1)
        if (
            label == "person"
            or confidence < min_confidence
            or area < DET_MIN_AREA_FRACTION * PROCESS_WIDTH * PROCESS_HEIGHT
            or x2 <= x1
            or y2 <= y1
        ):
            continue
        objects.append(TrackedObject(int(object_id) + id_offset, label, confidence, (x1, y1, x2, y2)))
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
    """Run local tracking models on one processed-size frame."""

    def __init__(
        self,
        detector: Any,
        hand_landmarker: Any,
        mp_module: Any,
        demo_detector: Any | None = None,
        demo_needs_vehicle_detector: bool = False,
    ) -> None:
        self.detector = detector
        self.demo_detector = demo_detector
        self.demo_needs_vehicle_detector = demo_needs_vehicle_detector
        self.hand_landmarker = hand_landmarker
        self.mp = mp_module
        self.mode: Mode = "actual"
        self._fresh_tracker = False  # True for the first frame after a mode switch
        self._next_id = 0
        self._identities: dict[tuple[str, int], tuple[str, int]] = {}
        self._last_ms = -1
        self._start_monotonic = time.monotonic()

    def process(self, image: Any, frame_id: int, captured_ts: float) -> FrameResult:
        """Build a single FrameResult with the original, unmirrored BGR image."""
        processed = cv2.resize(image, (PROCESS_WIDTH, PROCESS_HEIGHT))
        demo = self.mode == "demo" and self.demo_detector is not None
        objects: list[TrackedObject] = []
        if demo and self.demo_needs_vehicle_detector:
            # The custom eight-class head does not know vehicles. Keep the original
            # COCO detector running for hazard tier A and the demo classes it knows.
            objects.extend(self._detect(self.detector, processed, "coco", DET_MIN_CONFIDENCE,
                                        coco_demo_only=True))
        detector = self.demo_detector if demo else self.detector
        min_confidence = DEMO_DET_MIN_CONFIDENCE if demo else DET_MIN_CONFIDENCE
        selected = self._detect(detector, processed, "demo" if demo else "coco",
                                min_confidence,
                                image_size=TRAINED_DEMO_IMAGE_SIZE
                                if demo and self.demo_needs_vehicle_detector else None)
        objects = self._merge_demo_objects(objects, selected) if objects else selected
        self._fresh_tracker = False
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

    def _detect(
        self, detector: Any, image: Any, namespace: str, min_confidence: float,
        *, coco_demo_only: bool = False, image_size: int | None = None,
    ) -> list[TrackedObject]:
        options = {"imgsz": image_size} if image_size is not None else {}
        if image_size is not None:
            # A single physical item must not produce overlapping boxes with
            # different demo class names.
            options["agnostic_nms"] = True
        results = detector.track(
            image,
            persist=not self._fresh_tracker,  # False rebuilds the tracker after a switch
            tracker="bytetrack.yaml",
            conf=min_confidence,
            verbose=False,
            **options,
        )
        objects = tracked_objects(results[0], min_confidence) if results else []
        if coco_demo_only:
            objects = [obj for obj in objects
                       if obj.class_label in VEHICLE_LABELS or obj.class_label in COCO_DEMO_LABELS]
            for obj in objects:
                obj.class_label = COCO_DEMO_LABELS.get(obj.class_label, obj.class_label)
        for obj in objects:
            slot = (namespace, obj.object_id)
            identity = self._identities.get(slot)
            if identity is None or identity[0] != obj.class_label:
                self._next_id += 1
                identity = (obj.class_label, self._next_id)
                self._identities[slot] = identity
            obj.object_id = identity[1]
        return objects

    def _merge_demo_objects(
        self, standard: list[TrackedObject], custom: list[TrackedObject],
    ) -> list[TrackedObject]:
        # Vehicles always survive this merge: object deduplication must never
        # suppress a box needed by hazard tier A.
        vehicles = [obj for obj in standard if obj.class_label in VEHICLE_LABELS]
        known = [obj for obj in standard if obj.class_label not in VEHICLE_LABELS]
        if not known or not custom:
            return vehicles + known + custom
        candidates = known + custom
        boxes = [(obj.box[0], obj.box[1], obj.box[2] - obj.box[0], obj.box[3] - obj.box[1])
                 for obj in candidates]
        # Prefer the trained novel classes over overlapping COCO guesses; use
        # COCO for its known classes and the custom model as a fallback. These
        # values rank NMS candidates only; published confidence stays unchanged.
        scores = [1.0 + obj.confidence for obj in known] + [
            obj.confidence + (0.0 if obj.class_label in COCO_DEMO_LABELS.values() else 2.0)
            for obj in custom
        ]
        iou = float(self.demo_detector.predictor.args.iou)
        kept = cv2.dnn.NMSBoxes(boxes, scores, 0.0, iou)
        return vehicles + [candidates[int(index)] for index in kept]

    def set_mode(self, mode: Mode) -> bool:
        """Switch detector for the next frame; return False if that mode is unavailable."""
        if mode == self.mode:
            return True
        if mode == "demo" and self.demo_detector is None:
            return False
        self.mode = mode
        # Never reuse a published ID across modes, detectors or detector classes:
        # scene, namer and audio all cache object names by that ID.
        self._fresh_tracker = True
        self._identities.clear()
        return True

    def close(self) -> None:
        """Close MediaPipe resources after capture ends."""
        self.hand_landmarker.close()


def load_processor() -> VisionProcessor:
    """Load local YOLO/MediaPipe assets; never download during capture."""
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
    os.environ["YOLO_AUTOINSTALL"] = "False"
    import mediapipe as mp
    from ultralytics import YOLO

    detector = YOLO(str(YOLO_WEIGHTS))
    demo_detector = None
    demo_needs_vehicle_detector = False
    if TRAINED_DEMO_WEIGHTS.is_file():
        try:
            candidate = YOLO(str(TRAINED_DEMO_WEIGHTS))
            names = candidate.names.values() if isinstance(candidate.names, dict) else candidate.names
            if len(names) == len(DEMO_OBJECTS) and set(names) == set(DEMO_OBJECTS):
                demo_detector = candidate
                demo_needs_vehicle_detector = True
                log.info("Demo mode ready with fine-tuned weights: %s; COCO vehicles stay active",
                         TRAINED_DEMO_WEIGHTS)
            else:
                log.error("Ignoring demo weights with unexpected classes: %s", TRAINED_DEMO_WEIGHTS)
        except Exception as exc:  # noqa: BLE001 - optional checkpoints must not stop COCO
            # Demo assets are optional: a failed experiment must not disable COCO
            # tracking and the vehicle-hazard path.
            log.warning("Cannot load optional demo weights (%s); keeping COCO available",
                        type(exc).__name__)
    if demo_detector is None and DEMO_WEIGHTS.is_file() and DEMO_PROMPTS.is_file():
        try:
            import torch
            from ultralytics import YOLOE

            prompts = torch.load(DEMO_PROMPTS, weights_only=True)
            candidate = YOLOE(str(DEMO_WEIGHTS))
            candidate.set_classes(prompts["names"], prompts["embeddings"])
            demo_detector = candidate
            log.info("Demo mode ready for: %s", ", ".join(prompts["names"]))
        except Exception as exc:  # noqa: BLE001 - malformed optional prompt assets
            log.warning("Cannot load optional demo prompts (%s); keeping COCO available",
                        type(exc).__name__)
    elif demo_detector is None:
        log.info(
            "No demo prompts at %s; demo mode is off until "
            "`python -m vision.build_demo_weights` has been run",
            DEMO_PROMPTS,
        )
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(HAND_MODEL)),
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=2,
    )
    hands = mp.tasks.vision.HandLandmarker.create_from_options(options)
    return VisionProcessor(detector, hands, mp, demo_detector, demo_needs_vehicle_detector)


class LatestCamera:
    """Capture continuously and overwrite older frames rather than queueing."""

    def __init__(self, index: int) -> None:
        self._index = index
        self._capture = self._open_device()
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

    def _open_device(self) -> Any:
        # The default Media Foundation backend hung reopening the Logitech on
        # Windows. DirectShow also serves the reference-capture setup tool.
        if sys.platform == "win32":
            return cv2.VideoCapture(self._index, cv2.CAP_DSHOW)
        return cv2.VideoCapture(self._index)

    def _reopen(self) -> bool:
        """Release and reopen the device after repeated read failures."""
        self._capture.release()
        capture = self._open_device()
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
        self._mode_lock = threading.Lock()
        self._wanted_mode: Mode = "actual"
        self._thread = threading.Thread(target=self._run, name="vision", daemon=True)
        self._thread.start()

    def on_mode(self, msg: ModeChange) -> None:
        """Remember the requested mode; the frame loop applies it before its next frame."""
        with self._mode_lock:
            self._wanted_mode = msg.mode

    def _apply_mode(self, processor: VisionProcessor) -> None:
        """Switch the processor to the requested mode, or report back that it cannot."""
        with self._mode_lock:
            wanted = self._wanted_mode
        if wanted == processor.mode:
            return
        if processor.set_mode(wanted):
            log.info("Vision mode is now %s", wanted)
            return
        log.warning("Demo mode requested but the demo prompts are not built; staying in actual")
        with self._mode_lock:
            self._wanted_mode = processor.mode
        self._publish(ModeChange(ts=time.time(), mode=processor.mode))

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
                self._apply_mode(processor)
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
    """Publish live FrameResults from the configured camera and follow ModeChange."""
    vision = Vision(bus.publish)
    bus.subscribe(ModeChange, vision.on_mode)
    return vision
