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
from storage._deps import (
    DEFAULT_LANGUAGE,
    HazardEvent,
    LastSeenQuery,
    LastSeenResult,
    ModuleStatus,
    SpeakRequest,
    TouchEvent,
    VoiceStatus,
    known_language,
)
from storage.last_seen import format_answer, not_seen, unavailable

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
        status_publish: Callable[[Any], None] | None = None,
    ) -> None:
        """Create the store; start=True launches the worker thread immediately.

        status_publish, if given, receives a ModuleStatus whenever the database
        availability changes. It must not block (bus.publish only enqueues).
        """
        self._publish = publish
        self._status_publish = status_publish
        self._last_status: tuple[str, str] | None = None
        self._url = url or None
        self._queue: queue.Queue[Any] = queue.Queue(maxsize=QUEUE_MAX_ITEMS)
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._dropped = 0
        self._language = DEFAULT_LANGUAGE  # from audio's last VoiceStatus
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

    @property
    def language(self) -> str:
        """Language code of audio's confirmed voice; answers are worded in it."""
        with self._lock:
            return self._language

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

    def on_voice_status(self, status: VoiceStatus) -> None:
        """Bus handler: remember the active voice's language; only sets a field."""
        language = known_language(getattr(status, "language", None))
        with self._lock:
            self._language = language

    def on_last_seen_query(self, query: LastSeenQuery) -> None:
        """Bus handler: queue a last-seen lookup; the answer is published as a SpeakRequest.

        A query with a request_id also gets a LastSeenResult with the same id.
        The answer's language is captured here, when the query arrives.
        """
        text = str(getattr(query, "text", "") or "")
        request_id = getattr(query, "request_id", None)
        rid = None if request_id is None else str(request_id)
        self._enqueue(("query", (text, rid, self.language)))

    def _enqueue(self, item: tuple[str, Any]) -> None:
        """Put without blocking; count and drop when the queue is full."""
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self._count_drop()
            if not self._full_warned:
                self._full_warned = True
                log.warning("storage queue full (%d items); dropping events", QUEUE_MAX_ITEMS)
                self._report("degraded", "Storage queue full; dropping events")

    def _count_drop(self) -> None:
        """Increment the dropped counter."""
        with self._lock:
            self._dropped += 1

    # ---- worker thread ----------------------------------------------------

    def _report(self, status: str, detail: str) -> None:
        """Publish a ModuleStatus when the availability changes; never raises."""
        if self._status_publish is None:
            return
        with self._lock:  # called from the worker and from bus handler threads
            if self._last_status == (status, detail):
                return
            self._last_status = (status, detail)
        try:
            self._status_publish(
                ModuleStatus(
                    ts=time.time(),
                    module="storage",
                    status=status,  # type: ignore[arg-type]
                    mode="real",
                    detail=detail,
                )
            )
        except Exception:
            log.exception("publishing storage status failed")

    def _run(self) -> None:
        """Worker loop: drain the queue until stop()."""
        if self._url is None:
            self._report("offline", "TIGER_DATABASE_URL is not set; history is not saved")
        else:
            self._report("starting", "Connecting to Tiger Data")
            self._connection()
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

    def _answer(
        self, payload: tuple[str, str | None, str] | tuple[str, str | None] | str
    ) -> None:
        """Run a last-seen query and publish the spoken answer.

        "I have not seen that." is said only when the query ran and matched
        nothing. A database outage or failed query says "Touch history is
        unavailable right now." When the query had a request_id, a
        LastSeenResult follows carrying the same sentence the wearer heard.
        Every sentence is in the language captured when the query arrived; if
        the voice's language changed meanwhile, the unavailable sentence is said
        in the current language instead.
        """
        if isinstance(payload, str):
            payload = (payload, None)
        text, request_id = payload[0], payload[1]
        language = payload[2] if len(payload) > 2 else DEFAULT_LANGUAGE
        answer = not_seen(language)
        status = "not_found"
        row: dict[str, Any] | None = None
        text = text.strip()
        conn = self._connection() if text else None
        if text and conn is None:
            status = "unavailable"
            answer = unavailable(language)
        if conn is not None:
            try:
                row = db.last_seen(conn, text)
                answer = format_answer(row, time.time(), language)
                status = "found" if answer != not_seen(language) else "not_found"
            except Exception as exc:  # noqa: BLE001
                self._on_db_error(exc)
                answer = unavailable(language)
                status = "unavailable"
                row = None
        current = self.language
        if current != language:
            # The voice changed while the query ran: never speak the old
            # language's sentence with the new voice.
            answer = unavailable(current)
            status = "unavailable"
            row = None
        try:
            self._publish(
                SpeakRequest(ts=time.time(), text=answer, priority="normal", source="storage")
            )
        except Exception:
            log.exception("publishing last-seen answer failed")
        if request_id is None:
            return
        found = status == "found" and row is not None
        label = ""
        if found:
            label = (row.get("name") or "").strip() or (row.get("class_label") or "").strip()
        try:
            self._publish(
                LastSeenResult(
                    ts=time.time(),
                    request_id=request_id,
                    status=status,  # type: ignore[arg-type]
                    answer=answer,  # exactly what was spoken
                    matched_at=float(row["ts"]) if found else None,
                    label=label,
                    neighbours=[str(n) for n in (row.get("neighbours") or [])] if found else [],
                )
            )
        except Exception:
            log.exception("publishing last-seen result failed")

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
        self._report("active", "Connected to Tiger Data")
        return conn

    def _warn_down(self, reason: str) -> None:
        """Log the unreachable warning once per outage."""
        if self._down_warned:
            return
        self._down_warned = True
        if self._url is not None:  # the missing-URL case was reported at start
            self._report("offline", f"Tiger Data unavailable ({reason}); writes are dropped")
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
            self._report("degraded", f"Tiger Data rejected a statement ({type(exc).__name__})")

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
