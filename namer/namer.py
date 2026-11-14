"""Grok namer: turns NameRequest into NameResult on a background asyncio thread."""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from namer import _pending as c
from namer.grok_client import name_crop

log = logging.getLogger("namer")

NameRequest = c.NameRequest
NameResult = c.NameResult

_QUOTES = "\"'`“”‘’"


def clean_name(raw: str) -> str:
    """Trim whitespace, quotes and trailing periods, then cut to NAME_MAX_CHARS."""
    text = " ".join(raw.split())
    previous = None
    while text != previous:
        previous = text
        text = text.strip().strip(_QUOTES).strip()
        text = text.removesuffix(".")
    return text[: c.NAME_MAX_CHARS].rstrip()


def _default_client() -> httpx.AsyncClient:
    """Create the HTTP client used for Grok calls."""
    return httpx.AsyncClient(timeout=c.NAME_TIMEOUT_SECONDS)


@dataclass(order=True)
class _Job:
    """One queued Grok call; sorts largest crop first, then oldest first."""

    sort_key: tuple[int, int]
    request: NameRequest = field(compare=False)
    attempt: int = field(default=0, compare=False)


class Namer:
    """Names objects with Grok, rate limited, cached by object_id, off the bus thread."""

    def __init__(
        self,
        publish: Callable[[NameResult], None],
        client_factory: Callable[[], httpx.AsyncClient] = _default_client,
        autostart: bool = True,
    ) -> None:
        """Create the namer; starts its worker thread unless autostart is False."""
        self._publish = publish
        self._client_factory = client_factory
        self._inbox: queue.SimpleQueue[NameRequest] = queue.SimpleQueue()
        self._stopping = threading.Event()
        self._thread = threading.Thread(
            target=self._thread_main, name="namer", daemon=True
        )
        self._started = False
        self._seq = itertools.count()
        # Everything below is touched only on the worker thread.
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake: asyncio.Event | None = None
        self._heap: list[_Job] = []
        self._cache: dict[int, str] = {}
        self._waiting: dict[
            int, int
        ] = {}  # object_id -> requests waiting on its answer
        self._in_flight: set[asyncio.Task[None]] = set()
        self._failing = False
        if autostart:
            self.start()

    def start(self) -> None:
        """Start the worker thread (idempotent)."""
        if not self._started:
            self._started = True
            self._thread.start()

    def on_name_request(self, msg: NameRequest) -> None:
        """Bus handler: enqueue the request and return immediately."""
        if self._stopping.is_set():
            log.debug("namer stopped; dropping request for object %s", msg.object_id)
            return
        self._inbox.put(msg)
        self._poke()

    def stop(self, timeout: float | None = None) -> None:
        """Finish queued and in-flight requests, then stop the worker thread."""
        self._stopping.set()
        self._poke()
        if self._started:
            self._thread.join(timeout)

    # ---- worker thread ------------------------------------------------------

    def _poke(self) -> None:
        """Wake the dispatcher from any thread."""
        loop, wake = self._loop, self._wake
        if loop is None or wake is None:
            return
        try:
            loop.call_soon_threadsafe(wake.set)
        except RuntimeError:
            pass  # loop already closed

    def _thread_main(self) -> None:
        """Run the worker's event loop until stop() has drained everything."""
        try:
            asyncio.run(self._main())
        except Exception:
            log.exception("namer worker crashed")

    async def _main(self) -> None:
        """Set up the loop state and HTTP client, then dispatch until drained."""
        self._wake = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        slots = asyncio.Semaphore(c.NAME_MAX_IN_FLIGHT)
        client = self._client_factory()
        try:
            await self._dispatch(client, slots)
        finally:
            await client.aclose()

    async def _dispatch(
        self, client: httpx.AsyncClient, slots: asyncio.Semaphore
    ) -> None:
        """Start jobs largest first, within the in-flight and start-interval limits."""
        assert self._loop is not None and self._wake is not None
        last_start: float | None = None
        while True:
            self._wake.clear()
            self._drain_inbox()
            if not self._heap:
                if self._stopping.is_set() and not self._in_flight:
                    return
                await self._wake.wait()
                continue
            await slots.acquire()
            if last_start is not None:
                delay = last_start + c.NAME_MIN_INTERVAL_SECONDS - self._loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
            self._drain_inbox()  # a larger crop may have arrived while waiting
            job = heapq.heappop(self._heap)
            last_start = self._loop.time()
            task = asyncio.create_task(self._run_job(client, job, slots))
            self._in_flight.add(task)
            task.add_done_callback(self._job_done)

    def _job_done(self, task: asyncio.Task[None]) -> None:
        """Forget a finished job and let the dispatcher re-check its exit condition."""
        self._in_flight.discard(task)
        if self._wake is not None:
            self._wake.set()

    def _drain_inbox(self) -> None:
        """Move everything from the thread-safe inbox into the priority queue."""
        while True:
            try:
                msg = self._inbox.get_nowait()
            except queue.Empty:
                return
            self._admit(msg)

    def _admit(self, msg: NameRequest) -> None:
        """Answer from cache, join a pending request, or queue a new Grok call."""
        cached = self._cache.get(msg.object_id)
        if cached is not None:
            self._emit(msg.object_id, cached, True)
        elif msg.object_id in self._waiting:
            self._waiting[msg.object_id] += 1
        else:
            self._waiting[msg.object_id] = 1
            self._push(msg, 0)

    def _push(self, request: NameRequest, attempt: int) -> None:
        """Queue one Grok call, keyed by crop size so the largest goes first."""
        key = (-len(request.crop_jpeg), next(self._seq))
        heapq.heappush(self._heap, _Job(key, request, attempt))
        if self._wake is not None:
            self._wake.set()

    async def _run_job(
        self, client: httpx.AsyncClient, job: _Job, slots: asyncio.Semaphore
    ) -> None:
        """Make one Grok call; cache and publish on success, retry once on failure."""
        req = job.request
        try:
            raw = await asyncio.wait_for(
                name_crop(client, req.crop_jpeg, req.class_label),
                c.NAME_TIMEOUT_SECONDS,
            )
            name = clean_name(raw)
            if not name:
                raise ValueError("Grok returned an empty name")
        except Exception as exc:  # noqa: BLE001 - any failure means retry once, then ok=False
            self._log_failure(req.object_id, job.attempt, exc)
            if job.attempt == 0:
                self._push(req, 1)
            else:
                self._finish(req.object_id, "", False)
        else:
            if self._failing:
                log.info("Grok naming recovered")
                self._failing = False
            self._cache[req.object_id] = name
            self._finish(req.object_id, name, True)
        finally:
            slots.release()

    def _log_failure(self, object_id: int, attempt: int, exc: Exception) -> None:
        """Log the first failure loudly and repeats quietly until a call succeeds."""
        level = logging.DEBUG if self._failing else logging.WARNING
        self._failing = True
        log.log(
            level,
            "Grok naming failed for object %s (attempt %d): %s: %s",
            object_id,
            attempt + 1,
            type(exc).__name__,
            exc,
        )

    def _finish(self, object_id: int, name: str, ok: bool) -> None:
        """Publish the outcome once for every request waiting on this object."""
        for _ in range(self._waiting.pop(object_id, 1)):
            self._emit(object_id, name, ok)

    def _emit(self, object_id: int, name: str, ok: bool) -> None:
        """Publish one NameResult without letting a subscriber error kill the worker."""
        try:
            self._publish(
                NameResult(ts=time.time(), object_id=object_id, name=name, ok=ok)
            )
        except Exception:
            log.exception("publishing NameResult for object %s failed", object_id)
