"""Background Tiger Data writer: bus handlers enqueue, one worker thread does all DB work."""

from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from typing import Any

from storage import db
from storage._deps import HazardEvent, LastSeenQuery, SpeakRequest, TouchEvent
from storage.last_seen import NOT_SEEN, format_answer

log = logging.getLogger("storage")

# Not SPEC section 9 thresholds; fixed by the storage task brief.
QUEUE_MAX_ITEMS = 1000
RETRY_INTERVAL_SECONDS = 10.0
_GET_POLL_SECONDS = 0.25
_STOP_JOIN_SECONDS = 5.0

SESSION_ID = uuid.uuid4().hex  # one per process

_STOP = object()


class Store:
    """Logs TouchEvent and HazardEvent to Tiger Data and answers LastSeenQuery."""

    def __init__(
        self,
        publish: Callable[[Any], None],
        url: str | None,
        *,
        start: bool = True,
    ) -> None:
        """Create the store; start=True launches the worker thread immediately."""
        self._publish = publish
        self._url = url or None
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=QUEUE_MAX_ITEMS)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._dropped = 0
        self._written = 0
        self._full_warned = False
        self._down_warned = False
        self._row_error_warned = False
        self._conn: Any = None
        self._last_attempt = float("-inf")
        self._thread: threading.Thread | None = None
        self.session_id = SESSION_ID
        if start:
            self.start()

    # ---- caller-side API (bus thread): never blocks, never raises ---------

    @property
    def dropped(self) -> int:
        """Number of writes or queries dropped (queue full or DB unavailable)."""
        with self._lock:
            return self._dropped

    @property
    def written(self) -> int:
        """Number of rows written successfully."""
        with self._lock:
            return self._written

    def start(self) -> None:
        """Start the worker thread if it is not running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="storage-writer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the worker thread and close the connection."""
        self._stop_event.set()
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout=_STOP_JOIN_SECONDS)
            self._thread = None

    def on_touch_event(self, event: TouchEvent) -> None:
        """Bus handler: queue a touch_events row."""
        try:
            cx, cy = db.box_centre_fraction(event.box)
            row = {
                "ts": float(event.ts),
                "session_id": self.session_id,
                "object_id": int(event.object_id),
                "class_label": str(event.class_label),
                "name": str(event.name or ""),
                "kind": str(event.kind),
                "cx": cx,
                "cy": cy,
                "neighbours": [str(n) for n in (event.neighbours or [])],
            }
        except Exception:  # noqa: BLE001 - a bad message must never raise into the bus
            log.warning("ignoring malformed TouchEvent")
            return
        self._enqueue(("touch", row))

    def on_hazard_event(self, event: HazardEvent) -> None:
        """Bus handler: queue a hazard_events row."""
        try:
            row = {
                "ts": float(event.ts),
                "session_id": self.session_id,
                "type": str(event.type),
                "source": str(event.source),
                "confidence": float(event.confidence),
            }
        except Exception:  # noqa: BLE001
            log.warning("ignoring malformed HazardEvent")
            return
        self._enqueue(("hazard", row))

    def on_last_seen_query(self, query: LastSeenQuery) -> None:
        """Bus handler: queue a last-seen lookup; the answer is published as a SpeakRequest."""
        self._enqueue(("query", str(getattr(query, "text", "") or "")))

    def _enqueue(self, item: tuple[str, Any]) -> None:
        """Put without blocking; count and drop when the queue is full."""
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._count_drop()
            if not self._full_warned:
                self._full_warned = True
                log.warning("storage queue full (%d items); dropping events", QUEUE_MAX_ITEMS)

    def _count_drop(self) -> None:
        """Increment the dropped counter."""
        with self._lock:
            self._dropped += 1

    # ---- worker thread ----------------------------------------------------

    def _run(self) -> None:
        """Worker loop: drain the queue until stop()."""
        try:
            while not self._stop_event.is_set():
                try:
                    item = self._queue.get(timeout=_GET_POLL_SECONDS)
                except queue.Empty:
                    continue
                if item is _STOP:
                    break
                try:
                    self._handle(item)
                except Exception:
                    log.exception("storage worker error")
        finally:
            self._close()

    def _handle(self, item: tuple[str, Any]) -> None:
        """Process one queued item on the worker thread."""
        kind, payload = item
        if kind == "query":
            self._answer(payload)
            return
        conn = self._connection()
        if conn is None:
            self._count_drop()
            return
        try:
            if kind == "touch":
                db.insert_touch(conn, payload)
            else:
                db.insert_hazard(conn, payload)
        except Exception as exc:  # noqa: BLE001
            self._count_drop()
            self._on_db_error(exc)
            return
        with self._lock:
            self._written += 1

    def _answer(self, text: str) -> None:
        """Run a last-seen query and publish the spoken answer (fallback if the DB is down)."""
        answer = NOT_SEEN
        text = text.strip()
        conn = self._connection() if text else None
        if conn is not None:
            try:
                answer = format_answer(db.last_seen(conn, text), time.time())
            except Exception as exc:  # noqa: BLE001
                self._on_db_error(exc)
                answer = NOT_SEEN
        try:
            self._publish(
                SpeakRequest(ts=time.time(), text=answer, priority="normal", source="storage")
            )
        except Exception:
            log.exception("publishing last-seen answer failed")

    def _connection(self) -> Any:
        """Return a live connection, reconnecting at most every RETRY_INTERVAL_SECONDS."""
        if self._conn is not None and not self._conn.closed and not self._conn.broken:
            return self._conn
        self._conn = None
        if self._url is None:
            self._warn_down("TIGER_DATABASE_URL is not set")
            return None
        now = time.monotonic()
        if now - self._last_attempt < RETRY_INTERVAL_SECONDS:
            return None
        self._last_attempt = now
        conn = None
        try:
            conn = db.connect(self._url)
            db.ensure_schema(conn)
        except Exception as exc:  # noqa: BLE001
            if conn is not None:
                _safe_close(conn)
            # Only the class name: driver messages can contain host or user details.
            self._warn_down(type(exc).__name__)
            return None
        if self._down_warned:
            log.info("Tiger Data reconnected; writes resumed")
        self._down_warned = False
        self._conn = conn
        return conn

    def _warn_down(self, reason: str) -> None:
        """Log the unreachable warning once per outage."""
        if self._down_warned:
            return
        self._down_warned = True
        log.warning(
            "Tiger Data unavailable (%s); dropping writes, retrying at most every %.0f s",
            reason,
            RETRY_INTERVAL_SECONDS,
        )

    def _on_db_error(self, exc: BaseException) -> None:
        """Handle a failed statement: drop the connection if it is broken."""
        conn = self._conn
        if conn is None or conn.closed or conn.broken:
            _safe_close(conn)
            self._conn = None
            self._warn_down(type(exc).__name__)
        elif not self._row_error_warned:
            self._row_error_warned = True
            log.warning("Tiger Data rejected a statement (%s); dropping it", type(exc).__name__)

    def _close(self) -> None:
        """Close the connection from the worker thread."""
        _safe_close(self._conn)
        self._conn = None


def _safe_close(conn: Any) -> None:
    """Close a connection, ignoring errors."""
    if conn is None:
        return
    try:
        conn.close()
    except Exception as exc:  # noqa: BLE001
        log.debug("closing connection failed (%s)", type(exc).__name__)
