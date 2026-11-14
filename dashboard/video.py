"""Live camera feed for the dashboard: draw SPEC.md 4.9 overlays and keep the latest JPEG.

Frames come from FrameResult on the bus; object states come from SceneSnapshot.
Each bus subscription has its own worker, so drawing and JPEG encoding here never
delay vision, scene or hazard.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator
from typing import Any

import cv2
import numpy as np

from config import PROCESS_FPS, PROCESS_HEIGHT, PROCESS_WIDTH
from contracts import FrameResult, SceneObject, SceneSnapshot

LOGGER = logging.getLogger("dashboard")

BOUNDARY = "frame"
JPEG_QUALITY = 80
# Poll for a new frame four times per processed frame, so the page lags by at most
# a quarter of a frame.
POLL_SECONDS = 1.0 / (PROCESS_FPS * 4)
# Use a SceneSnapshot for drawing only if it is at most one second of frames old.
SNAPSHOT_MAX_FRAME_LAG = PROCESS_FPS

# Colours are BGR. Thicknesses are pixels in the 640 x 360 frame.
GREY = (140, 140, 140)
WHITE = (255, 255, 255)
GREEN = (80, 185, 63)
YELLOW = (36, 165, 245)
HAND_DOT = (255, 166, 88)
LABEL_TEXT = (15, 17, 21)
BG = (21, 17, 15)
THIN, NORMAL, THICK = 1, 2, 4
DASH_PIXELS = 8
HAND_DOT_RADIUS = 5
FONT = cv2.FONT_HERSHEY_SIMPLEX
FONT_SCALE = 0.5
LABEL_PAD = 4

# state: (colour, thickness, tag before the name, show a label)
STATE_STYLE: dict[str, tuple[tuple[int, int, int], int, str, bool]] = {
    "new": (GREY, THIN, "", False),
    "idle": (WHITE, NORMAL, "", True),
    "touching": (GREEN, THICK, "TOUCHING", True),
    "held": (YELLOW, THICK, "HELD", True),
    "lost": (WHITE, NORMAL, "", False),
}


def _placeholder_jpeg(text: str) -> bytes:
    """Return a dark 640 x 360 JPEG with one centred line of text."""
    image = np.full((PROCESS_HEIGHT, PROCESS_WIDTH, 3), BG, dtype=np.uint8)
    (width, height), _ = cv2.getTextSize(text, FONT, FONT_SCALE * 1.4, NORMAL)
    origin = ((PROCESS_WIDTH - width) // 2, (PROCESS_HEIGHT + height) // 2)
    cv2.putText(image, text, origin, FONT, FONT_SCALE * 1.4, GREY, NORMAL, cv2.LINE_AA)
    return _encode(image)


def _encode(image: Any) -> bytes:
    """Encode a BGR image as JPEG bytes."""
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return buffer.tobytes()


def _point(x: float, y: float) -> tuple[int, int]:
    """Round a contract coordinate to an OpenCV pixel."""
    return round(x), round(y)


def _dashed_rectangle(
    image: Any,
    box: tuple[float, float, float, float],
    colour: tuple[int, int, int],
    thickness: int,
) -> None:
    """Draw a dashed rectangle; OpenCV has no dashed line style."""
    x1, y1, x2, y2 = (round(v) for v in box)
    for start, end, horizontal in (
        ((x1, y1), (x2, y1), True),
        ((x1, y2), (x2, y2), True),
        ((x1, y1), (x1, y2), False),
        ((x2, y1), (x2, y2), False),
    ):
        length = (end[0] - start[0]) if horizontal else (end[1] - start[1])
        for offset in range(0, max(length, 0), DASH_PIXELS * 2):
            stop = min(offset + DASH_PIXELS, length)
            if horizontal:
                a, b = (start[0] + offset, start[1]), (start[0] + stop, start[1])
            else:
                a, b = (start[0], start[1] + offset), (start[0], start[1] + stop)
            cv2.line(image, a, b, colour, thickness)


def _label(image: Any, text: str, x: int, y: int, colour: tuple[int, int, int]) -> None:
    """Draw text on a filled tag sitting on top of a box's top-left corner."""
    # Hershey fonts are ASCII only.
    text = text.encode("ascii", "replace").decode("ascii")
    (width, height), baseline = cv2.getTextSize(text, FONT, FONT_SCALE, THIN)
    top = y - height - baseline - LABEL_PAD * 2
    if top < 0:  # no room above the box, so put the tag just inside it
        top = y
    bottom = top + height + baseline + LABEL_PAD * 2
    cv2.rectangle(
        image, (x, top), (x + width + LABEL_PAD * 2, bottom), colour, cv2.FILLED
    )
    cv2.putText(
        image,
        text,
        (x + LABEL_PAD, bottom - baseline - LABEL_PAD),
        FONT,
        FONT_SCALE,
        LABEL_TEXT,
        THIN,
        cv2.LINE_AA,
    )


def _draw_object(image: Any, obj: SceneObject) -> None:
    """Draw one scene object in the style SPEC.md 4.9 gives its state."""
    colour, thickness, tag, labelled = STATE_STYLE.get(obj.state, STATE_STYLE["new"])
    if obj.state == "lost":
        _dashed_rectangle(image, obj.box, colour, thickness)
    else:
        cv2.rectangle(
            image,
            _point(obj.box[0], obj.box[1]),
            _point(obj.box[2], obj.box[3]),
            colour,
            thickness,
        )
    if labelled:
        name = obj.name or obj.class_label
        text = f"{tag} {name}" if tag else name
        x, y = _point(obj.box[0], obj.box[1])
        _label(image, text, x, y, colour)


def render_frame(frame: FrameResult, snapshot: SceneSnapshot | None) -> Any:
    """Return a copy of the frame with object boxes and fingertip dots drawn on it.

    With a recent SceneSnapshot, boxes use its states (including lost objects).
    Without one, every detected object is drawn in the plain `new` style.
    """
    image = np.ascontiguousarray(frame.image).copy()  # scene crops the original
    if (
        snapshot is not None
        and abs(frame.frame_id - snapshot.frame_id) <= SNAPSHOT_MAX_FRAME_LAG
    ):
        # Touching and held last so their boxes sit on top.
        order = {"lost": 0, "new": 1, "idle": 2, "held": 3, "touching": 4}
        for obj in sorted(snapshot.objects, key=lambda o: order.get(o.state, 0)):
            _draw_object(image, obj)
    else:
        for tracked in frame.objects:
            cv2.rectangle(
                image,
                _point(tracked.box[0], tracked.box[1]),
                _point(tracked.box[2], tracked.box[3]),
                GREY,
                THIN,
            )
    for hand in frame.hands:
        for tip in (hand.thumb_tip, hand.index_tip):
            cv2.circle(
                image, _point(*tip), HAND_DOT_RADIUS, HAND_DOT, cv2.FILLED, cv2.LINE_AA
            )
            cv2.circle(image, _point(*tip), HAND_DOT_RADIUS, BG, THIN, cv2.LINE_AA)
    return image


class VideoFeed:
    """Hold the newest annotated JPEG; bus handlers write it, /video reads it."""

    def __init__(self) -> None:
        """Start with a 'waiting for camera' picture until the first FrameResult."""
        self._lock = threading.Lock()
        self._render_lock = threading.Lock()
        self._frame: FrameResult | None = None
        self._snapshot: SceneSnapshot | None = None
        self._jpeg = _placeholder_jpeg("Waiting for camera")
        self._sequence = 0
        self._closed = threading.Event()
        self._failed_once = False

    @property
    def closed(self) -> bool:
        """True once close() has been called."""
        return self._closed.is_set()

    def on_frame(self, msg: FrameResult) -> None:
        """Keep the newest frame and redraw the feed."""
        with self._lock:
            self._frame = msg
        self._render()

    def on_scene(self, msg: SceneSnapshot) -> None:
        """Keep the newest object states; redraw if they describe the frame on screen."""
        with self._lock:
            self._snapshot = msg
            matches = self._frame is not None and self._frame.frame_id == msg.frame_id
        if matches:
            self._render()

    def latest(self) -> tuple[int, bytes]:
        """Return (sequence number, JPEG); the number goes up with every new picture."""
        with self._lock:
            return self._sequence, self._jpeg

    def close(self) -> None:
        """End every open /video stream."""
        self._closed.set()

    def _render(self) -> None:
        """Draw the newest frame with the newest snapshot and store the JPEG."""
        with self._render_lock:  # one at a time, so an older picture never wins
            with self._lock:
                frame, snapshot = self._frame, self._snapshot
            if frame is None:
                return
            try:
                jpeg = _encode(render_frame(frame, snapshot))
            except Exception:
                if not self._failed_once:  # log once, not on every frame
                    LOGGER.exception("Could not draw the camera feed")
                    self._failed_once = True
                return
            with self._lock:
                self._jpeg = jpeg
                self._sequence += 1


def mjpeg_part(jpeg: bytes) -> bytes:
    """Wrap one JPEG as a multipart/x-mixed-replace part."""
    header = (
        f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n\r\n"
    ).encode("ascii")
    return header + jpeg + b"\r\n"


async def mjpeg_stream(
    feed: VideoFeed, poll_seconds: float = POLL_SECONDS
) -> AsyncIterator[bytes]:
    """Yield the current picture at once, then each new one, until the feed closes."""
    sent = -1
    while not feed.closed:
        sequence, jpeg = feed.latest()
        if sequence != sent:
            sent = sequence
            yield mjpeg_part(jpeg)
        await asyncio.sleep(poll_seconds)
