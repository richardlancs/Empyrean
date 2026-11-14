"""Last-touch lookups for the page: correlate each LastSeenQuery with its LastSeenResult.

The HTTP route calls submit() and get(); neither touches the database. submit()
publishes a LastSeenQuery with a fresh request_id on the bus (an in-memory
enqueue), the storage worker answers on its own thread, and on_result() files
the answer under that id. Everything is bounded: query length, pending
requests, how long a request may stay pending, and how many answers are kept.
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from config import LAST_SEEN_TIMEOUT_SECONDS
from contracts import LastSeenQuery, LastSeenResult

MAX_QUERY_CHARS = 60  # longer than any object name (NAME_MAX_CHARS is 40)
MAX_PENDING = 8  # concurrent lookups waiting for storage
MAX_RESULTS = 64  # finished lookups kept for polling
RESULT_TTL_SECONDS = 120.0  # how long a finished lookup can still be read
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_SPACES = re.compile(r"\s+")


class QueryRejected(Exception):
    """A lookup that was not sent; status_code says which HTTP error fits."""

    def __init__(self, status_code: int, message: str) -> None:
        """Keep the HTTP status and a plain message for the page."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def clean_query(text: str) -> str:
    """Return the query trimmed and with runs of whitespace collapsed; raise if unusable."""
    if not isinstance(text, str):
        raise QueryRejected(422, "The search text must be text.")
    text = _SPACES.sub(" ", _CONTROL.sub(" ", text)).strip()
    if not text:
        raise QueryRejected(422, "Type what to look for, for example: keys.")
    if len(text) > MAX_QUERY_CHARS:
        raise QueryRejected(422, f"Keep the search under {MAX_QUERY_CHARS} characters.")
    return text


class LastSeenService:
    """Send lookups to storage over the bus and hand back correlated answers."""

    def __init__(
        self,
        publish: Callable[[Any], None] | None,
        clock: Callable[[], float] = time.time,
        timeout: float = LAST_SEEN_TIMEOUT_SECONDS,
    ) -> None:
        """publish is bus.publish, or None when the dashboard runs with no bus."""
        self._publish = publish
        self._clock = clock
        self._timeout = timeout
        self._lock = threading.Lock()
        self._records: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._listeners: list[Callable[[], None]] = []

    @property
    def available(self) -> bool:
        """True when lookups can reach storage over a bus."""
        return self._publish is not None

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Call listener after a lookup finishes or expires."""
        with self._lock:
            self._listeners.append(listener)

    def submit(self, text: str) -> str:
        """Publish one lookup and return its request_id. Raises QueryRejected."""
        if self._publish is None:
            raise QueryRejected(
                503, "Last-touch search needs the full app; this page has no engine attached."
            )
        query = clean_query(text)
        self.expire()
        now = self._clock()
        request_id = uuid.uuid4().hex
        with self._lock:
            pending = sum(1 for r in self._records.values() if r["status"] == "pending")
            if pending >= MAX_PENDING:
                raise QueryRejected(429, "Too many searches are waiting. Try again shortly.")
            self._records[request_id] = {
                "request_id": request_id,
                "status": "pending",
                "query": query,
                "answer": None,
                "matched_at": None,
                "label": None,
                "neighbours": [],
                "detail": "Searching recorded touches",
                "submitted_at": now,
                "finished_at": None,
            }
            self._trim()
        self._publish(LastSeenQuery(ts=now, text=query, request_id=request_id))
        return request_id

    def on_result(self, msg: LastSeenResult) -> None:
        """Bus handler: file storage's answer under its request_id; ignore unknown ids."""
        with self._lock:
            record = self._records.get(msg.request_id)
            if record is None or record["status"] != "pending":
                return  # expired, already answered, or someone else's lookup
            record.update(
                status=msg.status,
                answer=msg.answer or None,
                matched_at=msg.matched_at if msg.status == "found" else None,
                label=msg.label or None,
                neighbours=list(msg.neighbours) if msg.status == "found" else [],
                detail=_DETAIL[msg.status],
                finished_at=self._clock(),
            )
        self._notify()

    def get(self, request_id: str) -> dict[str, Any] | None:
        """Return a copy of one lookup's record, or None if unknown or expired."""
        self.expire()
        with self._lock:
            record = self._records.get(request_id)
            return dict(record, neighbours=list(record["neighbours"])) if record else None

    def expire(self) -> bool:
        """Time out old pending lookups and forget old answers; True if anything changed."""
        now = self._clock()
        changed = False
        with self._lock:
            for request_id in list(self._records):
                record = self._records[request_id]
                if record["status"] == "pending":
                    if now - record["submitted_at"] > self._timeout:
                        record.update(
                            status="unavailable",
                            detail="History storage did not answer in time",
                            finished_at=now,
                        )
                        changed = True
                elif now - record["finished_at"] > RESULT_TTL_SECONDS:
                    del self._records[request_id]
        if changed:
            self._notify()
        return changed

    def _trim(self) -> None:
        """Drop the oldest finished lookups past MAX_RESULTS. Caller holds the lock."""
        while len(self._records) > MAX_RESULTS + MAX_PENDING:
            for request_id, record in self._records.items():
                if record["status"] != "pending":
                    del self._records[request_id]
                    break
            else:
                return

    def _notify(self) -> None:
        """Tell listeners a lookup changed."""
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener()


_DETAIL = {
    "found": "Found in recorded touches",
    "not_found": "No recorded touch matches",
    "unavailable": "History storage is unavailable, so this is not a 'not found'",
}
