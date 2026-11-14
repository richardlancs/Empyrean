"""Thread-safe in-process bus with independent, nonblocking subscribers."""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Callable
from typing import Any

from contracts import FrameResult

log = logging.getLogger("app")


class _Subscription:
    """Own a worker so one slow callback cannot delay another."""

    def __init__(self, message_type: type, handler: Callable[[Any], None]) -> None:
        self.message_type = message_type
        self.handler = handler
        self._pending: deque[Any] = deque()
        self._condition = threading.Condition()
        self._closed = False
        self._thread = threading.Thread(
            target=self._run,
            name=f"bus-{message_type.__name__}",
            daemon=True,
        )
        self._thread.start()

    def enqueue(self, message: Any) -> None:
        """Enqueue immediately, replacing stale frames instead of buffering them."""
        with self._condition:
            if self._closed:
                return
            if self.message_type is FrameResult:
                self._pending.clear()
            self._pending.append(message)
            self._condition.notify()

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._pending or self._closed)
                if self._closed:
                    return
                message = self._pending.popleft()
            try:
                self.handler(message)
            except Exception:
                log.exception("Subscriber for %s failed", self.message_type.__name__)

    def stop(self, timeout: float) -> None:
        """Discard queued messages and request worker termination."""
        with self._condition:
            self._closed = True
            self._pending.clear()
            self._condition.notify_all()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=timeout)


class Bus:
    """Dispatch contract messages by exact type to separate callback workers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[type, list[_Subscription]] = {}
        self._closed = False

    def subscribe(self, message_type: type, handler: Callable[[Any], None]) -> None:
        """Subscribe a callback to messages of exactly ``message_type``."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Bus has stopped")
            self._subscribers.setdefault(message_type, []).append(
                _Subscription(message_type, handler)
            )

    def publish(self, message: Any) -> None:
        """Fan out without waiting for any subscriber to run."""
        with self._lock:
            subscribers = tuple(self._subscribers.get(type(message), ()))
        for subscriber in subscribers:
            subscriber.enqueue(message)

    def stop(self, timeout: float = 1.0) -> None:
        """Stop accepting messages and ask subscriber workers to exit."""
        with self._lock:
            self._closed = True
            subscribers = tuple(
                subscriber
                for group in self._subscribers.values()
                for subscriber in group
            )
            self._subscribers.clear()
        for subscriber in subscribers:
            subscriber.stop(timeout)
