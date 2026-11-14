"""Publish HazardEvents from local box growth and asynchronous Grok checks."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

import cv2
import httpx

from config.thresholds import (
    HAZARD_COOLDOWN_SECONDS,
    HAZARD_GROK_INTERVAL_SECONDS,
    HAZARD_GROK_MIN_CONFIDENCE,
    HAZARD_GROK_TIMEOUT_SECONDS,
    HAZARD_GROK_WIDTH,
    HAZARD_VEHICLE_GROWTH,
    HAZARD_VEHICLE_MIN_AREA_FRACTION,
    PROCESS_HEIGHT,
    PROCESS_WIDTH,
)
from contracts import FrameResult, HazardEvent

log = logging.getLogger("hazard")
GROK_URL = "https://api.x.ai/v1/responses"
# Narrower than the SPEC.md 4.7 wording, which made Grok flag ordinary rooms as an
# obstacle (or stairs) about every 6 seconds. See DEVLOG 2026-11-14.
GROK_PROMPT = (
    "This is the forward view from a camera worn at eye level by a blind pedestrian, "
    "tilted about 20 degrees down so their hands and any tabletop are in view. "
    "Is there an immediate hazard the wearer would hit or fall from within their "
    "next two steps if they walked straight ahead? "
    "Count only: a downward step, stair edge or drop at floor level directly ahead "
    "(stairs_down or drop_off); a moving vehicle approaching (vehicle); or a solid "
    "object directly in the walking path at body or head height within about "
    "1 metre (obstacle). "
    "Do not count: objects on a table or desk, objects in or near the wearer's "
    "hands, furniture or walls beside the path, floors and rugs, open space, or "
    "anything far away. A table edge seen from above is not a drop. If you are not "
    "sure, answer hazard false. "
    "Reply with only a JSON object with fields hazard (true or false), type (one "
    "of stairs_down, drop_off, vehicle, obstacle, none) and confidence (0 to 1)."
)
VEHICLE_LABELS = frozenset(("car", "bus", "truck", "motorcycle", "bicycle"))
VALID_TYPES = frozenset(("stairs_down", "drop_off", "vehicle", "obstacle"))
LOOKBACK_SECONDS = 1.0
CODE_FENCE = re.compile(r"^```[A-Za-z0-9_-]*\s*(.*?)\s*```$", re.DOTALL)


def _reply_text(data: Any) -> str:
    """Extract the response text from an xAI Responses API envelope."""
    if not isinstance(data, dict):
        raise TypeError("Unexpected Grok response")
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    for item in data.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if isinstance(part, dict) and part.get("type") == "output_text":
                return str(part.get("text", ""))
    raise ValueError("No Grok output text")


def _strip_code_fence(text: str) -> str:
    """Remove one surrounding Markdown code fence, such as ```json ... ```."""
    match = CODE_FENCE.match(text)
    return match.group(1).strip() if match else text


def parse_hazard_response(data: Any) -> tuple[str, float] | None:
    """Validate Grok's JSON decision, returning only an actionable hazard."""
    text = _strip_code_fence(_reply_text(data).strip())
    decision = json.loads(text)
    if not isinstance(decision, dict) or decision.get("hazard") is not True:
        return None
    kind = decision.get("type")
    confidence = decision.get("confidence")
    if (
        kind not in VALID_TYPES
        or isinstance(confidence, bool)
        or not isinstance(confidence, (float, int))
        or not 0.0 <= confidence <= 1.0
        or confidence < HAZARD_GROK_MIN_CONFIDENCE
    ):
        return None
    return str(kind), float(confidence)


def request_grok(image: Any, key: str, model: str) -> tuple[str, float] | None:
    """Resize and ask Grok from a worker thread, with a bounded request timeout."""
    height, width = image.shape[:2]
    resized = cv2.resize(image, (HAZARD_GROK_WIDTH, round(height * HAZARD_GROK_WIDTH / width)))
    ok, jpeg = cv2.imencode(".jpg", resized)
    if not ok:
        raise ValueError("Could not encode Grok frame")
    encoded = base64.b64encode(jpeg.tobytes()).decode("ascii")
    payload = {
        "model": model,
        "store": False,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}",
                 "detail": "high"},
                {"type": "input_text", "text": GROK_PROMPT},
            ],
        }],
    }
    response = httpx.post(
        GROK_URL,
        headers={"Authorization": f"Bearer {key}"},
        json=payload,
        timeout=HAZARD_GROK_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return parse_hazard_response(response.json())


class HazardDetector:
    """Inspect every frame locally while Grok runs on at most one worker."""

    def __init__(
        self,
        publish: Callable[[object], None],
        *,
        clock: Callable[[], float] = time.monotonic,
        grok_request: Callable[[Any, str, str], tuple[str, float] | None] = request_grok,
    ) -> None:
        self._publish = publish
        self._clock = clock
        self._grok_request = grok_request
        self._lock = threading.Lock()
        self._history: dict[int, deque[tuple[float, float]]] = {}
        self._last_event_at = float("-inf")
        self._last_grok_at = float("-inf")
        self._grok_busy = False
        self._grok_thread: threading.Thread | None = None
        self._grok_failed_logged = False
        self._key = os.environ.get("GROK_API_KEY", "").strip()
        self._model = os.environ.get("GROK_MODEL", "").strip()
        self._stopped = False

    def _emit(self, kind: str, source: str, confidence: float, ts: float) -> bool:
        with self._lock:
            now = self._clock()
            if self._stopped or now - self._last_event_at < HAZARD_COOLDOWN_SECONDS:
                return False
            self._last_event_at = now
        self._publish(HazardEvent(ts=ts, type=kind, source=source, confidence=confidence))
        return True

    def on_frame(self, frame: FrameResult) -> None:
        """Check Tier A immediately, then schedule Tier B without network I/O."""
        active_ids: set[int] = set()
        for obj in frame.objects:
            if obj.class_label not in VEHICLE_LABELS:
                continue
            active_ids.add(obj.object_id)
            x1, y1, x2, y2 = obj.box
            area_fraction = max(0.0, x2 - x1) * max(0.0, y2 - y1) / (
                PROCESS_WIDTH * PROCESS_HEIGHT
            )
            history = self._history.setdefault(obj.object_id, deque())
            while history and frame.ts - history[0][0] > LOOKBACK_SECONDS:
                history.popleft()
            previous = history[0][1] if history else 0.0
            history.append((frame.ts, area_fraction))
            if (
                previous > 0.0
                and area_fraction >= HAZARD_VEHICLE_MIN_AREA_FRACTION
                and area_fraction >= previous * (1.0 + HAZARD_VEHICLE_GROWTH)
            ):
                self._emit("vehicle", "yolo", obj.confidence, frame.ts)
        for object_id in list(self._history):
            if object_id not in active_ids:
                del self._history[object_id]
        self._schedule_grok(frame)

    def _schedule_grok(self, frame: FrameResult) -> None:
        with self._lock:
            now = self._clock()
            if (
                self._stopped
                or self._grok_busy
                or now - self._last_grok_at < HAZARD_GROK_INTERVAL_SECONDS
            ):
                return
            if not self._key or not self._model:
                if not self._grok_failed_logged:
                    log.warning("Grok hazard check disabled: set GROK_API_KEY and GROK_MODEL in .env")
                    self._grok_failed_logged = True
                return
            self._last_grok_at = now
            self._grok_busy = True
            # FrameResult owns the pixel buffer; no encoding or HTTP call here.
            image = frame.image.copy()
            worker = threading.Thread(
                target=self._grok_worker, args=(image,), name="hazard-grok", daemon=True
            )
            self._grok_thread = worker
        worker.start()

    def _grok_worker(self, image: Any) -> None:
        try:
            result = self._grok_request(image, self._key, self._model)
            if result is not None:
                kind, confidence = result
                if kind in VALID_TYPES and confidence >= HAZARD_GROK_MIN_CONFIDENCE:
                    self._emit(kind, "grok", confidence, time.time())
        except Exception as exc:  # noqa: BLE001 - tier B failure must never stop the hazard path
            with self._lock:
                first = not self._grok_failed_logged
                self._grok_failed_logged = True
            if first:
                log.warning("Grok hazard check unavailable (%s); local tier remains active",
                            type(exc).__name__)
        finally:
            with self._lock:
                self._grok_busy = False

    def stop(self) -> None:
        """Disable future events and join any in-flight Grok request briefly."""
        with self._lock:
            self._stopped = True
            thread = self._grok_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=HAZARD_GROK_TIMEOUT_SECONDS)


def register(bus: Any) -> HazardDetector:
    """Subscribe the live detector to FrameResult and return it for shutdown."""
    detector = HazardDetector(bus.publish)
    bus.subscribe(FrameResult, detector.on_frame)
    return detector
