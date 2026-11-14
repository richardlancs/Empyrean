"""Publish representative local and Grok hazard events without a network request."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from config.thresholds import HAZARD_COOLDOWN_SECONDS
from contracts import HazardEvent

log = logging.getLogger("hazard")
SCRIPT = (
    ("vehicle", "yolo", 0.94),
    ("vehicle", "grok", 0.83),
    ("stairs_down", "grok", 0.91),
    ("drop_off", "grok", 0.88),
    ("obstacle", "grok", 0.86),
)


class FakeHazard:
    """Publish one sample of each supported tier/type pairing repeatedly."""

    def __init__(self, publish: Callable[[object], None], *, autostart: bool = True) -> None:
        self._publish = publish
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="fake-hazard", daemon=True)
        if autostart:
            self.start()

    def start(self) -> None:
        """Start publishing after consumers have subscribed."""
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            for kind, source, confidence in SCRIPT:
                if self._stop.is_set():
                    return
                self._publish(HazardEvent(time.time(), kind, source, confidence))
                log.info("Scripted %s hazard from %s", kind, source)
                if self._stop.wait(HAZARD_COOLDOWN_SECONDS):
                    return

    def stop(self) -> None:
        """Stop the fake event stream."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)


def register(bus: Any, *, autostart: bool = True) -> FakeHazard:
    """Start the scripted hazard publisher using bus.publish."""
    return FakeHazard(bus.publish, autostart=autostart)
