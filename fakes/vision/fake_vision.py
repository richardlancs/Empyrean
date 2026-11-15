"""Generate realistic BGR frames, stable objects, and a point-and-release cycle."""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np

from config.thresholds import PROCESS_FPS, PROCESS_HEIGHT, PROCESS_WIDTH
from contracts import DetectorStatus, FrameResult, Hand, ModeChange, TrackedObject
from contracts.messages import Point

log = logging.getLogger("vision")
Publish = Callable[[object], None]
CYCLE_FRAMES = 60
# (mcp, pip, dip, tip) MediaPipe indices for index, middle, ring and pinky.
_FINGERS = ((5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
_EXTENDED = (40.0, 60.0, 72.0, 85.0)  # distance from the wrist along the pointing line
_CURLED = (40.0, 55.0, 42.0, 30.0)  # tip folded back toward the wrist


def _pointing_hand_landmarks(wrist: Point, toward: Point) -> list[Point]:
    """Return 21 landmarks for a hand pointing its index finger at a point, others curled."""
    length = math.hypot(toward[0] - wrist[0], toward[1] - wrist[1])
    ux = (toward[0] - wrist[0]) / length
    uy = (toward[1] - wrist[1]) / length
    points: list[Point] = [wrist] * 21
    for index in (1, 2, 3, 4):
        points[index] = (wrist[0] - 6.0 * index, wrist[1] - 4.0 * index)
    for finger, joints in enumerate(_FINGERS):
        distances = _EXTENDED if finger == 0 else _CURLED
        spread = (finger - 1.5) * 6.0  # fan the knuckles a little across the hand
        for landmark, distance in zip(joints, distances, strict=True):
            points[landmark] = (
                wrist[0] + ux * distance - uy * spread,
                wrist[1] + uy * distance + ux * spread,
            )
    return points


def scripted_frame(frame_id: int, ts: float) -> FrameResult:
    """Build one 640x360 BGR image and contract objects for the scripted demo."""
    phase = frame_id % CYCLE_FRAMES
    image = np.full((PROCESS_HEIGHT, PROCESS_WIDTH, 3), (38, 42, 48), dtype=np.uint8)
    bottle = (120.0, 75.0, 220.0, 300.0)
    cup = (320.0, 155.0, 425.0, 292.0)
    cv2.rectangle(image, (120, 75), (220, 300), (65, 150, 210), -1)
    cv2.rectangle(image, (320, 155), (425, 292), (190, 190, 205), -1)
    objects = [
        TrackedObject(1, "bottle", 0.97, bottle),
        TrackedObject(2, "cup", 0.92, cup),
    ]
    hands: list[Hand] = []
    if 10 <= phase < 25:
        # Hand appears only after the bottle has been stable for >1 second.
        # It sits outside the bottle's box and points its index finger at it.
        points = _pointing_hand_landmarks((290.0, 340.0), (170.0, 187.5))
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        hand_box = (min(xs), min(ys), max(xs), max(ys))
        for point in points:
            cv2.circle(image, (int(point[0]), int(point[1])), 4, (105, 155, 195), -1)
        hands.append(Hand("right", points[4], points[8], hand_box, landmarks=points))
    if frame_id % PROCESS_FPS == 0:
        log.debug("Script frame %d, hands=%d", frame_id, len(hands))
    return FrameResult(ts=ts, frame_id=frame_id, image=image, objects=objects, hands=hands)


FAKE_IDENTITY = "No detector: scripted test clip (fake vision)"
# Detector-switch behaviour of the fake, for exercising the dashboard without weights.
#   FAKE_DEMO_DETECTOR=ok|missing|invalid   (default ok)
#   FAKE_DETECTOR_SWITCH_SECONDS=1.5         (simulated load time)
FAKE_FAILURES = {
    "missing": "No demo-trained checkpoint is installed (fake vision: simulated).",
    "invalid": "demo-yolo11s.pt has the wrong classes for the demo (fake vision: simulated).",
}


class FakeVision:
    """Publish scripted FrameResults on a stoppable timer.

    It also answers ModeChange like vision does, with DetectorStatus marked
    fake: the mode label changes, but no detector model ever runs, and the
    recorded clip is the same in both modes.
    """

    def __init__(self, publish: Publish, *, start: bool = True) -> None:
        self._publish = publish
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="fake-vision", daemon=True)
        self._mode_lock = threading.Lock()
        self._mode = "actual"
        self._switching: str | None = None
        self._outcome = os.environ.get("FAKE_DEMO_DETECTOR", "ok")
        self._delay = float(os.environ.get("FAKE_DETECTOR_SWITCH_SECONDS", "1.5"))
        if start:
            self.start()

    def start(self) -> None:
        """Begin publishing; app/ calls this once every consumer has subscribed."""
        if not self._thread.is_alive() and not self._stop.is_set():
            self._status("active", None, None)
            self._thread.start()

    def _status(self, state: str, requested: str | None, request_id: str | None, message: str = "") -> None:
        self._publish(
            DetectorStatus(
                ts=time.time(),
                state=state,  # type: ignore[arg-type]
                active_mode=self._mode,  # type: ignore[arg-type]
                detector=FAKE_IDENTITY,
                requested_mode=requested,  # type: ignore[arg-type]
                request_id=request_id,
                checkpoint="",
                demo_kind="fake",
                demo_available=self._outcome == "ok",
                message=message,
                fake=True,
            )
        )

    def on_mode(self, msg: ModeChange) -> None:
        """Simulate a detector switch: switching, then active or failed."""
        with self._mode_lock:
            if msg.mode == self._mode and self._switching is None:
                self._status("active", None, msg.request_id)
                return
            if self._switching is not None:
                return  # one switch at a time, as in vision
            self._switching = msg.mode
        self._status("switching", msg.mode, msg.request_id)

        def finish() -> None:
            if self._stop.wait(self._delay):
                return
            with self._mode_lock:
                target, self._switching = self._switching, None
                failure = FAKE_FAILURES.get(self._outcome) if target == "demo" else None
                if not failure:
                    self._mode = target or self._mode
            if failure:
                self._status("failed", target, msg.request_id, failure)
            else:
                self._status("active", None, msg.request_id)

        threading.Thread(target=finish, name="fake-vision-switch", daemon=True).start()

    def _run(self) -> None:
        interval = 1.0 / PROCESS_FPS
        deadline = time.monotonic()
        frame_id = 0
        while not self._stop.is_set():
            self._publish(scripted_frame(frame_id, time.time()))
            frame_id += 1
            if frame_id == 1 or frame_id % PROCESS_FPS == 0:
                log.info("Published synthetic FrameResult %d", frame_id - 1)
            deadline += interval
            deadline = max(deadline, time.monotonic())
            self._stop.wait(max(0.0, deadline - time.monotonic()))

    def stop(self) -> None:
        """Request the worker to exit without waiting a full frame period."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)


def register(bus: Any, *, start: bool = True) -> FakeVision:
    """Create a fake FrameResult publisher on bus.publish; start=False defers start()."""
    vision = FakeVision(bus.publish, start=start)
    bus.subscribe(ModeChange, vision.on_mode)
    return vision
