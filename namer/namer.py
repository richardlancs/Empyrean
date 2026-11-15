"""Grok namer: turns NameRequest into NameResult on a background asyncio thread."""

from __future__ import annotations

import asyncio
import heapq
import itertools
import logging
import queue
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

import config
from contracts import NameRequest, NameResult, VoiceStatus
from contracts.languages import (
    DEFAULT_LANGUAGE,
    LANGUAGE_NAMES_EN,
    LANGUAGES,
    known_language,
)
from namer.grok_client import name_crop
from namer.questions import SceneQuestions

log = logging.getLogger("namer")

_QUOTES = "\"'`“”‘’"


def clean_name(raw: str) -> str:
    """Trim whitespace, quotes and trailing periods, then cut to NAME_MAX_CHARS."""
    text = " ".join(raw.split())
    previous = None
    while text != previous:
        previous = text
        text = text.strip().strip(_QUOTES).strip()
        text = text.removesuffix(".")
    return text[: config.NAME_MAX_CHARS].rstrip()


# "Spanish: botella" -> label "Spanish". Only a label that names a language is dropped.
_LABEL_PREFIX = re.compile(r"^([^:：]{1,40})[:：]\s*(.+)$")


def _strip_language_label(line: str, language: str) -> str:
    """Drop a leading "<language>:" label Grok may put before a line."""
    match = _LABEL_PREFIX.match(line.strip())
    if match is None:
        return line
    vocabulary = {"translation", "name", LANGUAGES.get(language, "").lower()}
    vocabulary.update(
        re.findall(r"[a-z]+", LANGUAGE_NAMES_EN.get(language, "").lower())
    )
    words = re.findall(r"\w+", match.group(1).lower())
    if words and all(word in vocabulary for word in words):
        return match.group(2)
    return line


def split_reply(raw: str, language: str) -> tuple[str, str]:
    """Split Grok's reply into (English name, name in language).

    English: the whole reply is cleaned exactly as before and the second part is
    empty. Otherwise the first non-empty line is the English name and the second
    non-empty line, trimmed and cut to NAME_MAX_CHARS, is the spoken name; a
    missing second line gives an empty spoken name.
    """
    if language == DEFAULT_LANGUAGE:
        return clean_name(raw), ""
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return "", ""
    name = clean_name(_strip_language_label(lines[0], DEFAULT_LANGUAGE))
    spoken = ""
    if len(lines) > 1:
        spoken = clean_name(_strip_language_label(lines[1], language))
    return name, spoken


def _default_client() -> httpx.AsyncClient:
    """Create the HTTP client used for Grok calls."""
    return httpx.AsyncClient(timeout=config.NAME_TIMEOUT_SECONDS)


# Start-of-frame markers that carry the image size. C4 (DHT), C8 (JPG) and
# CC (DAC) share the range but are not frame headers.
_SOF_MARKERS = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
# Markers with no length field.
_STANDALONE = frozenset({0x01, *range(0xD0, 0xD9)})


def jpeg_area(data: bytes) -> int:
    """Pixel area (width x height) read from a JPEG's frame header, 0 if unreadable.

    Reads only the header bytes and decodes nothing, so it is cheap. A JPEG's
    byte count says little about its area: a flat crop compresses far smaller
    than a busy one of the same size.
    """
    if len(data) < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return 0
    i = 2
    n = len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            return 0  # lost sync with the marker stream
        marker = data[i + 1]
        if marker == 0xFF:  # fill byte before a marker
            i += 1
            continue
        if marker in _STANDALONE:
            i += 2
            continue
        if marker in (0xD9, 0xDA) or i + 4 > n:  # end of image, or scan data starts
            return 0
        length = (data[i + 2] << 8) | data[i + 3]
        if length < 2:
            return 0
        if marker in _SOF_MARKERS:
            if i + 9 > n:
                return 0
            height = (data[i + 5] << 8) | data[i + 6]
            width = (data[i + 7] << 8) | data[i + 8]
            return width * height
        i += 2 + length
    return 0


@dataclass(frozen=True)
class NameTiming:
    """How long one Grok call waited in the namer's queue, and how long the call took."""

    object_id: int
    queued_s: float  # request received to Grok call started
    api_s: float  # Grok call started to answer or failure
    ok: bool


@dataclass(order=True)
class _Job:
    """One queued Grok call; sorts largest crop area first, then oldest first."""

    sort_key: tuple[int, int]
    request: NameRequest = field(compare=False)
    received: float = field(compare=False)  # time.monotonic() when the request arrived
    language: str = field(compare=False, default=DEFAULT_LANGUAGE)  # at request time


class Namer:
    """Names objects with Grok, rate limited, cached by object_id, off the bus thread."""

    def __init__(
        self,
        publish: Callable[[NameResult], None],
        client_factory: Callable[[], httpx.AsyncClient] = _default_client,
        autostart: bool = True,
    ) -> None:
        """Create the namer; starts its worker thread unless autostart is False."""
        self.questions: SceneQuestions | None = None
        self._publish = publish
        self._client_factory = client_factory
        self._inbox: queue.SimpleQueue[tuple[NameRequest, float, str]] = (
            queue.SimpleQueue()
        )
        # Active spoken language from audio's VoiceStatus; English until the first one.
        self._language = DEFAULT_LANGUAGE
        self._language_lock = threading.Lock()
        # The last 200 Grok calls, appended on the worker thread. Read with list().
        self.timings: deque[NameTiming] = deque(maxlen=200)
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
        # object_id -> (English name, spoken name, its language)
        self._cache: dict[int, tuple[str, str, str]] = {}
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
        with self._language_lock:
            language = self._language
        self._inbox.put((msg, time.monotonic(), language))
        self._poke()

    def on_voice_status(self, msg: VoiceStatus) -> None:
        """Bus handler: remember the active spoken language and return."""
        language = known_language(getattr(msg, "language", None))
        with self._language_lock:
            self._language = language

    @property
    def language(self) -> str:
        """The active spoken language new requests are captured with."""
        with self._language_lock:
            return self._language

    def stop(self, timeout: float | None = None) -> None:
        """Finish queued and in-flight requests, then stop the worker thread."""
        if self.questions is not None:
            self.questions.stop()
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
        slots = asyncio.Semaphore(config.NAME_MAX_IN_FLIGHT)
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
                delay = (
                    last_start + config.NAME_MIN_INTERVAL_SECONDS - self._loop.time()
                )
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
                msg, received, language = self._inbox.get_nowait()
            except queue.Empty:
                return
            self._admit(msg, received, language)

    def _admit(self, msg: NameRequest, received: float, language: str) -> None:
        """Answer from cache, join a pending request, or queue a new Grok call.

        A cached spoken name is reused only for a request in that same language.
        """
        cached = self._cache.get(msg.object_id)
        if cached is not None:
            name, spoken, spoken_language = cached
            if spoken_language != language:
                spoken, spoken_language = "", ""
            self._emit(msg.object_id, name, True, spoken, spoken_language)
        elif msg.object_id in self._waiting:
            self._waiting[msg.object_id] += 1
        else:
            self._waiting[msg.object_id] = 1
            self._push(msg, received, language)

    def _push(self, request: NameRequest, received: float, language: str) -> None:
        """Queue one Grok call, keyed by crop pixel area so the largest goes first.

        Runs on the worker thread, never in the bus handler, so reading the JPEG
        header stays off the frame path.
        """
        key = (-jpeg_area(request.crop_jpeg), next(self._seq))
        heapq.heappush(self._heap, _Job(key, request, received, language))
        if self._wake is not None:
            self._wake.set()

    async def _run_job(
        self, client: httpx.AsyncClient, job: _Job, slots: asyncio.Semaphore
    ) -> None:
        """Make exactly one Grok call; cache on success, publish the outcome either way.

        No retry here. Scene owns the one retry SPEC.md 4.5 allows: it sends a
        second NameRequest after a failed NameResult. Failures are not cached, so
        that second request gets its own single call.
        """
        req = job.request
        started = time.monotonic()
        try:
            raw = await asyncio.wait_for(
                name_crop(client, req.crop_jpeg, req.class_label, job.language),
                config.NAME_TIMEOUT_SECONDS,
            )
            name, spoken = split_reply(raw, job.language)
            if not name:
                raise ValueError("Grok returned an empty name")
        except Exception as exc:  # noqa: BLE001 - any failure publishes ok=False
            self._record(job, started, False)
            self._log_failure(req.object_id, exc)
            self._finish(req.object_id, "", False)
        else:
            self._record(job, started, True)
            if self._failing:
                log.info("Grok naming recovered")
                self._failing = False
            spoken_language = job.language if spoken else ""
            self._cache[req.object_id] = (name, spoken, spoken_language)
            self._finish(req.object_id, name, True, spoken, spoken_language)
        finally:
            slots.release()

    def _record(self, job: _Job, started: float, ok: bool) -> None:
        """Keep and log the queue wait and the Grok call time for one job."""
        timing = NameTiming(
            object_id=job.request.object_id,
            queued_s=started - job.received,
            api_s=time.monotonic() - started,
            ok=ok,
        )
        self.timings.append(timing)
        log.info(
            "Grok call for object %s %s in %.2f s after %.2f s queued",
            timing.object_id,
            "answered" if ok else "failed",
            timing.api_s,
            timing.queued_s,
        )

    def _log_failure(self, object_id: int, exc: Exception) -> None:
        """Log the first failure loudly and repeats quietly until a call succeeds."""
        level = logging.DEBUG if self._failing else logging.WARNING
        self._failing = True
        log.log(
            level,
            "Grok naming failed for object %s: %s: %s",
            object_id,
            type(exc).__name__,
            exc,
        )

    def _finish(
        self, object_id: int, name: str, ok: bool, spoken: str = "", language: str = ""
    ) -> None:
        """Publish the outcome once for every request waiting on this object."""
        for _ in range(self._waiting.pop(object_id, 1)):
            self._emit(object_id, name, ok, spoken, language)

    def _emit(
        self, object_id: int, name: str, ok: bool, spoken: str = "", language: str = ""
    ) -> None:
        """Publish one NameResult without letting a subscriber error kill the worker."""
        try:
            self._publish(
                NameResult(
                    ts=time.time(),
                    object_id=object_id,
                    name=name,
                    ok=ok,
                    spoken_name=spoken,
                    language=language,
                )
            )
        except Exception:
            log.exception("publishing NameResult for object %s failed", object_id)
