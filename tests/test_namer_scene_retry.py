"""Scene and namer together: one naming retry in total, owned by scene.

SPEC.md 4.5 allows one retry per object. Scene sends it (a second NameRequest
after a failed NameResult) and the namer makes exactly one HTTP attempt per
uncached request, so a failing object costs at most two Grok calls.

The real SceneDatabase and Namer are wired through a tiny in-test bus. HTTP is
httpx.MockTransport, so nothing leaves the machine. NameResults are queued and
handed to scene on the test thread between frames, like a frame loop would.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections.abc import Awaitable, Callable

import httpx
import numpy as np
import pytest

import config
from config.thresholds import PROCESS_HEIGHT, PROCESS_WIDTH
from contracts.messages import (
    FrameResult,
    NameRequest,
    NameResult,
    SceneSnapshot,
    TrackedObject,
)
from namer.namer import Namer
from scene import SceneDatabase

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]

INTERVAL = 0.2
TIMEOUT = 0.5
FRAME_GAP = 0.02
# A handler call that takes this long would be visible as a stalled frame loop.
# It is far below TIMEOUT, so any wait on the network would break it.
MAX_HANDLER_SECONDS = 0.05


@pytest.fixture(autouse=True)
def _fast_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "NAME_MIN_INTERVAL_SECONDS", INTERVAL)
    monkeypatch.setattr(config, "NAME_TIMEOUT_SECONDS", TIMEOUT)
    monkeypatch.setenv("GROK_API_KEY", "test-key")
    monkeypatch.setenv("GROK_MODEL", "test-model")


def reply(text: str) -> httpx.Response:
    body = {
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": text}]}
        ]
    }
    return httpx.Response(200, json=body)


class CountingHandler:
    """Mock Grok endpoint that counts calls and answers from a script."""

    def __init__(self, answer: Callable[[int], Awaitable[httpx.Response]]) -> None:
        self.calls = 0
        self._answer = answer
        self._lock = threading.Lock()

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.calls += 1
            n = self.calls
        return await self._answer(n)


class Rig:
    """Real scene and real namer joined by a minimal bus, driven frame by frame."""

    def __init__(self, handler: Handler) -> None:
        self.results: queue.SimpleQueue[NameResult] = queue.SimpleQueue()
        self.requests: list[NameRequest] = []
        self.handled: list[NameResult] = []
        self.slowest = 0.0
        self.frames = 0
        self.namer = Namer(
            self.results.put,
            client_factory=lambda: httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ),
        )
        self.scene = SceneDatabase(self._scene_publish)
        self.image = np.zeros((PROCESS_HEIGHT, PROCESS_WIDTH, 3), dtype=np.uint8)
        self.det = TrackedObject(
            object_id=1, class_label="bottle", confidence=0.9, box=(100, 80, 220, 300)
        )
        self.snapshot: SceneSnapshot | None = None

    def _scene_publish(self, _topic: str, msg: object) -> None:
        if isinstance(msg, NameRequest):
            self.requests.append(msg)
            self.namer.on_name_request(msg)

    def _timed(self, fn: Callable[[], object]) -> object:
        t0 = time.perf_counter()
        out = fn()
        self.slowest = max(self.slowest, time.perf_counter() - t0)
        return out

    def step(self) -> None:
        """Deliver any NameResults to scene, then run one frame."""
        while True:
            try:
                result = self.results.get_nowait()
            except queue.Empty:
                break
            self.handled.append(result)
            self._timed(lambda r=result: self.scene.handle_name(r))
        frame = FrameResult(
            ts=time.time(),
            frame_id=self.frames,
            image=self.image,
            objects=[self.det],
            hands=[],
        )
        self.snapshot = self._timed(lambda: self.scene.handle_frame(frame))  # type: ignore[assignment]
        self.frames += 1

    def run(self, seconds: float, until: Callable[[], bool] | None = None) -> None:
        """Step frames for up to `seconds`, or until `until()` is true."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.step()
            if until is not None and until():
                return
            time.sleep(FRAME_GAP)
        if until is not None:
            raise AssertionError("condition not reached in time")

    def name(self) -> str:
        assert self.snapshot is not None
        return self.snapshot.objects[0].name

    def failures(self) -> int:
        return sum(1 for r in self.handled if not r.ok)

    def close(self) -> None:
        self.namer.stop(timeout=5)


# Long enough for any extra attempt to start and finish if one were made.
QUIET = INTERVAL + TIMEOUT + 0.3


def test_persistent_failure_makes_at_most_two_http_attempts() -> None:
    async def answer(_n: int) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    handler = CountingHandler(answer)
    rig = Rig(handler)
    try:
        rig.run(5.0, until=lambda: rig.failures() >= 2)
        rig.run(QUIET)  # keep the frame loop going; nothing else should be sent
    finally:
        rig.close()

    assert handler.calls == 2
    assert len(rig.requests) == 2  # the first request plus scene's one retry
    assert [(r.name, r.ok) for r in rig.handled] == [("", False), ("", False)]
    assert rig.name() == ""


def test_first_failure_then_success_stores_the_name() -> None:
    async def answer(n: int) -> httpx.Response:
        if n == 1:
            return httpx.Response(503, json={"error": "busy"})
        return reply("Heinz ketchup")

    handler = CountingHandler(answer)
    rig = Rig(handler)
    try:
        rig.run(5.0, until=lambda: rig.snapshot is not None and rig.name() != "")
        rig.run(QUIET)
    finally:
        rig.close()

    assert rig.name() == "Heinz ketchup"
    assert handler.calls == 2
    assert len(rig.requests) == 2
    assert [(r.name, r.ok) for r in rig.handled] == [
        ("", False),
        ("Heinz ketchup", True),
    ]


def test_cached_success_makes_no_further_http_request() -> None:
    async def answer(_n: int) -> httpx.Response:
        return reply("Tropicana orange juice")

    handler = CountingHandler(answer)
    rig = Rig(handler)
    try:
        rig.run(5.0, until=lambda: rig.snapshot is not None and rig.name() != "")
        assert handler.calls == 1 and len(rig.requests) == 1
        # Ask again for the same object, as a late duplicate would.
        rig.namer.on_name_request(rig.requests[0])
        rig.run(5.0, until=lambda: len(rig.handled) >= 2)
        rig.run(QUIET)
    finally:
        rig.close()

    assert handler.calls == 1
    assert [(r.name, r.ok) for r in rig.handled] == [
        ("Tropicana orange juice", True)
    ] * 2
    assert rig.name() == "Tropicana orange juice"


def test_timeouts_never_block_frame_or_event_handling() -> None:
    async def answer(_n: int) -> httpx.Response:
        await asyncio.sleep(TIMEOUT * 4)  # always trips NAME_TIMEOUT_SECONDS
        return reply("too late")

    handler = CountingHandler(answer)
    rig = Rig(handler)
    t0 = time.monotonic()
    try:
        rig.run(5.0, until=lambda: rig.failures() >= 2)
        elapsed = time.monotonic() - t0
        rig.run(QUIET)
    finally:
        rig.close()

    assert handler.calls == 2
    assert rig.failures() == 2 and rig.name() == ""
    # Two sequential timeouts, so the run took at least that long...
    assert elapsed >= 2 * TIMEOUT - 0.05
    # ...yet no handle_frame or handle_name call (which also publishes the
    # retry into the namer) waited on the network.
    assert rig.slowest < MAX_HANDLER_SECONDS
    # The loop kept stepping the whole time, not just once per result.
    assert rig.frames >= elapsed / (FRAME_GAP + MAX_HANDLER_SECONDS)
