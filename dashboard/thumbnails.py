"""Small recent crops of objects in view, for the object list.

Runs on the dashboard's own SceneSnapshot worker, never on the camera path. It
keeps references to the last few frames only, refreshes each object's crop at
most once per REFRESH_SECONDS, holds at most MAX_ITEMS crops, and forgets a crop
THUMBNAIL_MAX_AGE_SECONDS after it was taken. The original frame is only read.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import Any

import cv2

from config import THUMBNAIL_MAX_AGE_SECONDS
from contracts import FrameResult, SceneSnapshot

LOGGER = logging.getLogger("dashboard")

MAX_ITEMS = 32
FRAMES_KEPT = 3  # SceneSnapshot follows its FrameResult closely
REFRESH_SECONDS = 5.0  # also how often an object's thumbnail_url changes
MAX_EDGE_PIXELS = 160
PAD_FRACTION = 0.08
JPEG_QUALITY = 75
CROPPED_STATES = {"new", "idle", "touching", "held"}  # never a lost (stale) box


def crop_thumbnail(image: Any, box: tuple[float, float, float, float]) -> bytes | None:
    """Return a JPEG of the padded box, scaled so its longer edge is MAX_EDGE_PIXELS."""
    if image is None or getattr(image, "ndim", 0) < 2:
        return None
    height, width = image.shape[:2]
    x1, y1, x2, y2 = box
    pad_x, pad_y = (x2 - x1) * PAD_FRACTION, (y2 - y1) * PAD_FRACTION
    left, top = max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y))
    right, bottom = min(width, round(x2 + pad_x)), min(height, round(y2 + pad_y))
    if right - left < 2 or bottom - top < 2:
        return None
    crop = image[top:bottom, left:right]
    scale = MAX_EDGE_PIXELS / max(crop.shape[0], crop.shape[1])
    if scale < 1:
        size = (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale)))
        crop = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    return buffer.tobytes() if ok else None


class ThumbnailCache:
    """Bounded, expiring object crops keyed by object_id."""

    def __init__(
        self,
        clock: Callable[[], float] = time.time,
        max_items: int = MAX_ITEMS,
        max_age: float = THUMBNAIL_MAX_AGE_SECONDS,
    ) -> None:
        """Start empty; clock returns seconds since the Unix epoch."""
        self._clock = clock
        self._max_items = max_items
        self._max_age = max_age
        self._lock = threading.Lock()
        self._frames: deque[FrameResult] = deque(maxlen=FRAMES_KEPT)
        self._items: OrderedDict[int, tuple[float, bytes]] = OrderedDict()
        self._failed_once = False
        self.receiving = False  # True once a frame has arrived

    def on_frame(self, msg: FrameResult) -> None:
        """Keep a reference to the newest frames (no copy, no drawing)."""
        with self._lock:
            self._frames.append(msg)
            self.receiving = True

    def on_scene(self, msg: SceneSnapshot) -> None:
        """Refresh crops for visible objects from the frame this snapshot describes."""
        now = self._clock()
        with self._lock:
            frame = next((f for f in self._frames if f.frame_id == msg.frame_id), None)
            due = [
                obj
                for obj in msg.objects
                if obj.state in CROPPED_STATES
                and now - self._items.get(obj.object_id, (float("-inf"), b""))[0]
                >= REFRESH_SECONDS
            ]
        if frame is None or not due:
            return
        fresh: list[tuple[int, bytes]] = []
        for obj in due:
            try:
                jpeg = crop_thumbnail(frame.image, obj.box)
            except Exception:
                if not self._failed_once:
                    LOGGER.exception("Could not make an object thumbnail")
                    self._failed_once = True
                continue
            if jpeg:
                fresh.append((obj.object_id, jpeg))
        with self._lock:
            for object_id, jpeg in fresh:
                self._items[object_id] = (now, jpeg)
                self._items.move_to_end(object_id)
            while len(self._items) > self._max_items:
                self._items.popitem(last=False)

    def get(self, object_id: int) -> bytes | None:
        """Return the crop for object_id if one exists and is not too old."""
        with self._lock:
            item = self._items.get(object_id)
            if item is None:
                return None
            if self._clock() - item[0] > self._max_age:
                del self._items[object_id]
                return None
            return item[1]

    def fresh_ids(self) -> dict[int, float]:
        """Return {object_id: crop time} for every crop that has not expired."""
        now = self._clock()
        with self._lock:
            return {k: v[0] for k, v in self._items.items() if now - v[0] <= self._max_age}

    def expire(self) -> None:
        """Forget crops older than max_age."""
        now = self._clock()
        with self._lock:
            for object_id in [k for k, v in self._items.items() if now - v[0] > self._max_age]:
                del self._items[object_id]

    def __len__(self) -> int:
        """Number of crops held, expired or not."""
        with self._lock:
            return len(self._items)
