"""Generate realistic BGR frames, stable objects, and a touch-and-release cycle."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np

from config.thresholds import PROCESS_FPS, PROCESS_HEIGHT, PROCESS_WIDTH
from contracts import FrameResult, Hand, TrackedObject

log = logging.getLogger("vision")
Publish = Callable[[object], None]
CYCLE_FRAMES = 60


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
        hand_box = (148.0, 105.0, 205.0, 185.0)
        cv2.rectangle(image, (148, 105), (205, 185), (105, 155, 195), -1)
        hands.append(Hand("right", (165.0, 145.0), (180.0, 160.0), hand_box))
    if frame_id % PROCESS_FPS == 0:
        log.debug("Script frame %d, hands=%d", frame_id, len(hands))
    return FrameResult(ts=ts, frame_id=frame_id, image=image, objects=objects, hands=hands)


class FakeVision:
    """Publish scripted FrameResults on a stoppable timer."""

    def __init__(self, publish: Publish) -> None:
        self._publish = publish
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="fake-vision", daemon=True)
        self._thread.start()

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
            if deadline < time.monotonic():
                deadline = time.monotonic()
            self._stop.wait(max(0.0, deadline - time.monotonic()))

    def stop(self) -> None:
        """Request the worker to exit without waiting a full frame period."""
        self._stop.set()
        self._thread.join(timeout=2.0)


def register(bus: Any) -> FakeVision:
    """Start a fake FrameResult publisher through bus.publish."""
    return FakeVision(bus.publish)
