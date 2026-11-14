"""Fake namer: answers NameRequest with canned NameResult messages, no Grok call.

Run the demo:  .venv/bin/python -m fakes.namer.fake_namer

Publishes: NameResult (SPEC.md section 5), one per NameRequest, after a random
300 to 900 ms delay on a background worker thread. Names come from a lookup on
class_label; every 10th uncached request fails with ok=False and an empty name.
Successful names are cached by object_id, so an object is named once.
"""

from __future__ import annotations

import queue
import random
import threading
import time
from collections.abc import Callable

from config import NAME_MAX_CHARS
from contracts import NameRequest, NameResult

FAKE_NAMES: dict[str, str] = {
    "bottle": "Heinz ketchup",
    "cup": "Starbucks coffee cup",
    "cell phone": "iPhone 15",
    "book": "Penguin paperback",
    "bowl": "Kellogg's cereal bowl",
}
FAIL_EVERY = 10

Publish = Callable[[object], None]


class FakeNamer:
    """Stand-in for namer/: publishes NameResult after a short random delay."""

    def __init__(
        self,
        publish: Publish,
        seed: int | None = None,
        delay_range: tuple[float, float] = (0.3, 0.9),
    ) -> None:
        """Start the worker thread; delay_range is in seconds."""
        self._publish = publish
        self._rng = random.Random(seed)
        self._delay_range = delay_range
        self._cache: dict[int, str] = {}
        self._count = 0
        self._lock = threading.Lock()
        self._queue: queue.Queue[NameRequest | None] = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="fake-namer", daemon=True)
        self._thread.start()

    def on_name_request(self, msg: NameRequest) -> None:
        """Queue a request and return immediately."""
        self._queue.put(msg)

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the worker after pending requests are answered."""
        self._queue.put(None)
        self._thread.join(timeout)

    def _run(self) -> None:
        """Worker loop: answer requests one at a time."""
        while True:
            msg = self._queue.get()
            if msg is None:
                return
            self._publish(self._answer(msg))

    def _answer(self, msg: NameRequest) -> NameResult:
        """Build the NameResult for one request, sleeping on this worker only."""
        with self._lock:
            cached = self._cache.get(msg.object_id)
        if cached is not None:
            return NameResult(ts=time.time(), object_id=msg.object_id, name=cached, ok=True)

        time.sleep(self._rng.uniform(*self._delay_range))
        with self._lock:
            self._count += 1
            fail = self._count % FAIL_EVERY == 0
            if fail:
                return NameResult(ts=time.time(), object_id=msg.object_id, name="", ok=False)
            name = FAKE_NAMES.get(msg.class_label, msg.class_label)[:NAME_MAX_CHARS]
            self._cache[msg.object_id] = name
        return NameResult(ts=time.time(), object_id=msg.object_id, name=name, ok=True)


if __name__ == "__main__":

    def _print_publish(msg: object) -> None:
        """Print whatever the fake publishes."""
        print(f"published: {msg}")

    labels = ["bottle", "cup", "cell phone", "book", "bowl", "keyboard"]
    namer = FakeNamer(_print_publish, seed=1, delay_range=(0.05, 0.1))
    start = time.monotonic()
    for i in range(11):
        namer.on_name_request(
            NameRequest(ts=time.time(), object_id=i, class_label=labels[i % len(labels)],
                        crop_jpeg=b"")
        )
    print(f"queued 11 requests in {(time.monotonic() - start) * 1000:.1f} ms (non-blocking)")
    namer.on_name_request(NameRequest(ts=time.time(), object_id=0, class_label="bottle",
                                      crop_jpeg=b""))
    namer.stop(timeout=5.0)
