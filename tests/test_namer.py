"""Smoke tests for namer/ using httpx.MockTransport (no network)."""

from __future__ import annotations

import asyncio
import base64
import itertools
import json
import threading
import time
from collections.abc import Awaitable, Callable

import httpx
import pytest

import config
from contracts import NameRequest, NameResult
from namer.grok_client import INSTRUCTION
from namer.namer import Namer, clean_name

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


def crop_size(request: httpx.Request) -> int:
    body = json.loads(request.content)
    url = body["input"][0]["content"][0]["image_url"]
    return len(base64.b64decode(url.split(",", 1)[1]))


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


def test_publishes_the_contracts_name_result_class() -> None:
    """The namer publishes contracts.NameResult itself, not a look-alike copy."""

    async def handler(_req: httpx.Request) -> httpx.Response:
        return reply("Heinz ketchup")

    out = Collector()
    namer = make_namer(handler, out)
    try:
        namer.on_name_request(request(1))
        [result] = out.wait_for(1)
    finally:
        namer.stop(timeout=5)
    assert type(result) is NameResult
    assert (result.object_id, result.name, result.ok) == (1, "Heinz ketchup", True)


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
            starts.append((time.monotonic(), crop_size(req)))
        await asyncio.sleep(0.45)  # longer than INTERVAL so calls overlap
        with lock:
            in_flight -= 1
        return reply("thing")

    out = Collector()
    namer = make_namer(handler, out, autostart=False)
    sizes = [10, 50, 20, 40, 30]
    for i, size in enumerate(sizes):
        namer.on_name_request(request(i, size))
    namer.start()
    results = out.wait_for(5)
    namer.stop(timeout=5)

    assert all(r.ok for r in results)
    assert max_in_flight <= config.NAME_MAX_IN_FLIGHT
    assert max_in_flight == 2
    assert [size for _, size in starts] == sorted(sizes, reverse=True)
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


def test_timeout_then_success_is_retried_once() -> None:
    calls = 0

    async def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            await asyncio.sleep(TIMEOUT * 3)  # trips NAME_TIMEOUT_SECONDS
        return reply("Tropicana orange juice")

    out = Collector()
    namer = make_namer(handler, out)
    namer.on_name_request(request(3))
    results = out.wait_for(1)
    namer.stop(timeout=5)

    assert calls == 2
    assert len(results) == 1
    assert results[0].ok is True and results[0].name == "Tropicana orange juice"


def test_two_failures_publish_one_failed_result() -> None:
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

    assert calls == 2
    assert [(r.object_id, r.name, r.ok) for r in out.results] == [(4, "", False)]


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
