"""Replay a scripted stairs event through the normal hazard consumers."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from config import HAZARD_COOLDOWN_SECONDS
from contracts import HazardEvent


class DemoAlertRejected(Exception):
    """A demo alarm that could not be published."""

    def __init__(self, status_code: int, message: str) -> None:
        """Keep the HTTP status and explanation for the page."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class DemoAlertService:
    """Publish the same scripted stairs event used by the hazard fake."""

    def __init__(
        self,
        publish: Callable[[Any], None] | None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Keep the bus publisher, or None for a standalone dashboard."""
        self._publish = publish
        self._clock = clock
        self._last_request: float | None = None
        self._lock = threading.Lock()

    def request(self) -> dict[str, Any]:
        """Request the live stairs alarm without waiting for sound or storage."""
        if self._publish is None:
            raise DemoAlertRejected(503, "The stairs alarm needs the full app; no engine is attached.")
        with self._lock:
            now = self._clock()
            if self._last_request is not None and now - self._last_request < HAZARD_COOLDOWN_SECONDS:
                raise DemoAlertRejected(429, "The stairs alarm was just requested. Try again in a moment.")
            # Replay the existing fake's Grok stairs result with the unchanged
            # contract. This is scripted, not a fresh model inference.
            self._publish(HazardEvent(ts=now, type="stairs_down", source="grok", confidence=0.91))
            self._last_request = now
        return {"status": "requested", "type": "stairs_down", "ts": now}
