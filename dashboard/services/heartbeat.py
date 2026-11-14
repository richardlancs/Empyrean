"""A small background ticker so time-based statuses change even when no message arrives.

Once a second it expires old last-touch searches and thumbnails and pushes the
page state, so a stopped camera or an ended warning shows up without waiting
for the next frame. The work per tick is bounded and never touches the bus.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

LOGGER = logging.getLogger("dashboard")
HEARTBEAT_SECONDS = 1.0


class Heartbeat:
    """Run tick() on a daemon thread every interval until stop()."""

    def __init__(self, tick: Callable[[], None], interval: float = HEARTBEAT_SECONDS) -> None:
        """Hold the work to run; call start() to begin."""
        self._tick = tick
        self._interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failed_once = False

    def start(self) -> None:
        """Start ticking if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="dashboard-heartbeat", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Stop ticking and wait briefly for the thread."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._tick()
            except Exception:
                if not self._failed_once:
                    LOGGER.exception("Dashboard heartbeat failed")
                    self._failed_once = True
