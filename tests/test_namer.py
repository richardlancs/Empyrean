"""Smoke tests for namer/ using httpx.MockTransport (no network)."""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import threading
import time
from collections.abc import Awaitable, Callable

import cv2
import httpx
import numpy as np
import pytest

import config
from contracts import NameRequest, NameResult
from namer.grok_client import INSTRUCTION
from namer.namer import Namer, clean_name, jpeg_area

Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]

INTERVAL = 0.2
TIMEOUT = 0.5


@pytest.fixture(autouse=True)
def _fast_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "NAME_MIN_INTERVAL_SECONDS", INTERVAL)
    monkeypatch.setattr(config, "NAME_TIMEOUT_SECONDS", TIMEOUT)
    monkeypatch.setenv("GROK_API_KEY", "test-key")
    monkeypatch.setenv("GROK_MODEL", "test-model")


def reply(text: str) -> httpx.Response:
    body = {
        "object": "response",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": text}]},
        ],
    }
    return httpx.Response(200, json=body)


def sent_jpeg(request: httpx.Request) -> bytes:
    body = json.loads(request.content)
    url = body["input"][0]["content"][0]["image_url"]
    return base64.b64decode(url.split(",", 1)[1])


def crop_area(request: httpx.Request) -> int:
    return jpeg_area(sent_jpeg(request))


def jpeg(width: int, height: int, noisy: bool = False, **params: int) -> bytes:
    """A valid JPEG. Flat images compress tiny; noisy ones compress large."""
    if noisy:
        rng = np.random.default_rng(width * 7919 + height)
        img = rng.integers(0, 256, (height, width, 3), dtype=np.uint8)
    else:
        img = np.full((height, width, 3), 128, dtype=np.uint8)
    flags: list[int] = []
    for key, value in params.items():
        flags += [getattr(cv2, key), value]
    ok, buf = cv2.imencode(".jpg", img, flags)
    assert ok
    return buf.tobytes()


def jpeg_request(object_id: int, data: bytes) -> NameRequest:
    return NameRequest(
        ts=time.time(), object_id=object_id, class_label="bottle", crop_jpeg=data
    )


class Collector:
    def __init__(self) -> None:
        self.results: list[NameResult] = []
        self._lock = threading.Lock()

    def __call__(self, result: NameResult) -> None:
        with self._lock:
            self.results.append(result)

    def wait_for(self, count: int, timeout: float = 5.0) -> list[NameResult]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if len(self.results) >= count:
                    return list(self.results)
            time.sleep(0.01)
        raise AssertionError(f"expected {count} results, got {len(self.results)}")


def make_namer(handler: Handler, collector: Collector, autostart: bool = True) -> Namer:
    return Namer(
        collector,
        client_factory=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ),
        autostart=autostart,
    )


def request(object_id: int, size: int = 100, label: str = "bottle") -> NameRequest:
    return NameRequest(
        ts=time.time(), object_id=object_id, class_label=label, crop_jpeg=b"x" * size
    )


def test_reply_is_trimmed_and_cut() -> None:
    seen: list[httpx.Request] = []

    async def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return reply(
            '  "Heinz Tomato Ketchup squeeze bottle, extra large family size."\n'
        )

    out = Collector()
    namer = make_namer(handler, out)
    namer.on_name_request(request(1))
    [result] = out.wait_for(1)
    namer.stop(timeout=5)

    assert result.ok is True and result.object_id == 1
    assert result.name == "Heinz Tomato Ketchup squeeze bottle, ext"
    assert len(result.name) == config.NAME_MAX_CHARS
    assert clean_name(" 'Coca-Cola can.' ") == "Coca-Cola can"

    body = json.loads(seen[0].content)
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert body["model"] == "test-model" and body["store"] is False
    assert "reasoning" not in body  # non-reasoning models reject it
    image, text = body["input"][0]["content"]
    assert image["type"] == "input_image"
    assert image["image_url"].startswith("data:image/jpeg;base64,")
    assert text["type"] == "input_text" and text["text"].startswith(INSTRUCTION)
    assert "bottle" in text["text"]


def test_concurrency_interval_and_largest_first() -> None:
    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0
    starts: list[tuple[float, int]] = []

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
            starts.append((time.monotonic(), crop_area(req)))
        await asyncio.sleep(0.45)  # longer than INTERVAL so calls overlap
        with lock:
            in_flight -= 1
        return reply("thing")

    out = Collector()
    namer = make_namer(handler, out, autostart=False)
    sides = [10, 50, 20, 40, 30]
    for i, side in enumerate(sides):
        namer.on_name_request(jpeg_request(i, jpeg(side * 4, side * 2)))
    namer.start()
    results = out.wait_for(5)
    namer.stop(timeout=5)

    assert all(r.ok for r in results)
    assert max_in_flight <= config.NAME_MAX_IN_FLIGHT
    assert max_in_flight == 2
    expected = sorted((s * 4 * s * 2 for s in sides), reverse=True)
    assert [area for _, area in starts] == expected
    gaps = [b - a for (a, _), (b, _) in itertools.pairwise(starts)]
    assert min(gaps) >= INTERVAL - 0.01


def test_cache_by_object_id() -> None:
    calls = 0

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return reply("Heinz ketchup")

    out = Collector()
    namer = make_namer(handler, out)
    namer.on_name_request(request(7))
    namer.on_name_request(request(7))  # while the first is pending
    out.wait_for(2)
    namer.on_name_request(request(7))  # after it is cached
    results = out.wait_for(3)
    namer.stop(timeout=5)

    assert calls == 1
    assert [(r.object_id, r.name, r.ok) for r in results] == [
        (7, "Heinz ketchup", True)
    ] * 3


def test_timeout_makes_one_attempt_and_publishes_failure() -> None:
    calls = 0

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(TIMEOUT * 3)  # trips NAME_TIMEOUT_SECONDS
        return reply("Tropicana orange juice")

    out = Collector()
    namer = make_namer(handler, out)
    t0 = time.monotonic()
    namer.on_name_request(request(3))
    [result] = out.wait_for(1)
    elapsed = time.monotonic() - t0
    namer.stop(timeout=5)

    assert calls == 1  # the namer does not retry; scene owns the one retry
    assert (result.object_id, result.name, result.ok) == (3, "", False)
    assert TIMEOUT - 0.05 <= elapsed < TIMEOUT * 2


def test_error_makes_one_attempt_and_publishes_failure() -> None:
    calls = 0

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={"error": "boom"})

    out = Collector()
    namer = make_namer(handler, out)
    namer.on_name_request(request(4))
    out.wait_for(1)
    namer.stop(timeout=5)

    assert calls == 1
    assert [(r.object_id, r.name, r.ok) for r in out.results] == [(4, "", False)]


def test_failure_is_not_cached_so_a_new_request_tries_again() -> None:
    calls = 0

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, json={"error": "busy"})
        return reply("Heinz ketchup")

    out = Collector()
    namer = make_namer(handler, out)
    namer.on_name_request(request(5))
    out.wait_for(1)
    namer.on_name_request(request(5))  # what scene sends after a failed result
    out.wait_for(2)
    namer.on_name_request(request(5))  # now cached
    results = out.wait_for(3)
    namer.stop(timeout=5)

    assert calls == 2
    assert [(r.name, r.ok) for r in results] == [
        ("", False),
        ("Heinz ketchup", True),
        ("Heinz ketchup", True),
    ]


def test_coalesced_requests_share_one_failed_attempt() -> None:
    calls = 0

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.1)
        return httpx.Response(500, json={"error": "boom"})

    out = Collector()
    namer = make_namer(handler, out, autostart=False)
    namer.on_name_request(request(6))
    namer.on_name_request(request(6))  # joins the first, no second call
    namer.start()
    results = out.wait_for(2)
    namer.stop(timeout=5)

    assert calls == 1
    assert [(r.object_id, r.name, r.ok) for r in results] == [(6, "", False)] * 2


def test_on_name_request_returns_fast() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.1)
        return reply("mug")

    out = Collector()
    namer = make_namer(handler, out)
    durations = []
    for i in range(5):
        t0 = time.perf_counter()
        namer.on_name_request(request(100 + i))
        durations.append(time.perf_counter() - t0)
    namer.stop(timeout=10)

    assert max(durations) < 0.005
    assert len(out.results) == 5


def test_jpeg_area_reads_the_frame_header() -> None:
    assert jpeg_area(jpeg(64, 48)) == 64 * 48
    assert jpeg_area(jpeg(640, 360, noisy=True)) == 640 * 360
    progressive = jpeg(120, 30, IMWRITE_JPEG_PROGRESSIVE=1)  # SOF2, not SOF0
    assert jpeg_area(progressive) == 120 * 30
    assert jpeg_area(b"") == 0
    assert jpeg_area(b"x" * 100) == 0  # not a JPEG
    assert jpeg_area(jpeg(64, 48)[:20]) == 0  # cut before the frame header


def test_priority_follows_pixel_area_not_jpeg_bytes() -> None:
    big_flat = jpeg(400, 300)  # large area, compresses to few bytes
    small_busy = jpeg(120, 90, noisy=True)  # small area, many bytes
    medium_busy = jpeg(200, 150, noisy=True)
    broken = b"\xff\xd8not a real jpeg" * 50  # unreadable header: goes last
    # The byte order really is the opposite of the area order.
    assert len(big_flat) < len(small_busy) < len(medium_busy)
    assert jpeg_area(big_flat) > jpeg_area(medium_busy) > jpeg_area(small_busy)

    order: list[bytes] = []

    async def handler(req: httpx.Request) -> httpx.Response:
        order.append(sent_jpeg(req))
        return reply("thing")

    out = Collector()
    namer = make_namer(handler, out, autostart=False)
    for i, data in enumerate([broken, small_busy, medium_busy, big_flat]):
        namer.on_name_request(jpeg_request(i, data))
    namer.start()
    out.wait_for(4)
    namer.stop(timeout=5)

    assert order == [big_flat, medium_busy, small_busy, broken]


def test_timings_separate_queue_wait_from_api_time() -> None:
    api_seconds = 0.3

    async def handler(req: httpx.Request) -> httpx.Response:
        await asyncio.sleep(api_seconds)
        return reply("thing")

    out = Collector()
    namer = make_namer(handler, out, autostart=False)
    for i in range(3):  # two slots, so the third must wait for one to free up
        namer.on_name_request(request(200 + i))
    namer.start()
    out.wait_for(3)
    namer.stop(timeout=5)

    timings = sorted(namer.timings, key=lambda t: t.queued_s)
    assert [t.ok for t in timings] == [True] * 3
    assert all(api_seconds - 0.02 <= t.api_s < api_seconds + 0.2 for t in timings)
    assert timings[0].queued_s < 0.1
    assert INTERVAL - 0.02 <= timings[1].queued_s < api_seconds  # start spacing
    assert timings[2].queued_s >= api_seconds - 0.02  # waited for a free slot


def test_failed_call_is_timed_too() -> None:
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    out = Collector()
    namer = make_namer(handler, out)
    namer.on_name_request(request(300))
    out.wait_for(1)
    namer.stop(timeout=5)

    [timing] = list(namer.timings)
    assert (timing.object_id, timing.ok) == (300, False)
    assert timing.api_s >= 0 and timing.queued_s >= 0
