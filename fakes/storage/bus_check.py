"""Live Tiger Data check through storage.register(bus), run by hand with .env loaded.

Run from the repo root:  .venv/bin/python -m fakes.storage.bus_check [--keep]

Uses a minimal exact-type bus in place of Person 1's, and the real
storage.register(bus). It publishes touch, release and retouch TouchEvents and
one HazardEvent, checks the rows with a separate connection, asks two
LastSeenQuery questions over the bus, then simulates a database outage in this
process (connect fails) and checks writes resume after the real reconnect.

Every row it writes carries this process's session_id; at the end it deletes
only those rows (unless --keep), and it reports the table totals before and
after so you can see nothing else changed. Never prints TIGER_DATABASE_URL.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import psycopg
from dotenv import find_dotenv, load_dotenv

from contracts import HazardEvent, LastSeenQuery, SpeakRequest, TouchEvent
from storage import db, register, writer
from storage.last_seen import NOT_SEEN


class Bus:
    """Minimal exact-type publish/subscribe, standing in for Person 1's app bus."""

    def __init__(self) -> None:
        self._subs: dict[type, list[Callable[[Any], None]]] = defaultdict(list)

    def subscribe(self, kind: type, handler: Callable[[Any], None]) -> None:
        """Register a handler for one message class."""
        self._subs[kind].append(handler)

    def publish(self, msg: Any) -> None:
        """Deliver to every handler of this exact class."""
        for handler in self._subs.get(type(msg), []):
            handler(msg)


def wait(cond: Callable[[], bool], timeout: float) -> bool:
    """Poll cond() until true or timeout."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def totals(url: str) -> tuple[int, int]:
    """Row counts of touch_events and hazard_events."""
    with db.connect(url) as conn:
        t = conn.execute("SELECT count(*) FROM touch_events").fetchone()[0]
        h = conn.execute("SELECT count(*) FROM hazard_events").fetchone()[0]
    return int(t), int(h)


def main(argv: list[str]) -> int:
    """Run the checks and print PASS or FAIL for each."""
    parser = argparse.ArgumentParser(prog="python -m fakes.storage.bus_check")
    parser.add_argument("--keep", action="store_true", help="leave this run's rows in place")
    args = parser.parse_args(argv)
    load_dotenv(find_dotenv(usecwd=True))
    url = os.environ.get("TIGER_DATABASE_URL", "").strip()
    if not url:
        print("TIGER_DATABASE_URL is not set. Add it to .env.")
        return 2
    logging.basicConfig(level=logging.INFO, format="  log %(name)s: %(message)s")
    session = writer.SESSION_ID
    tag = uuid.uuid4().hex[:8]
    name = f"Validation ketchup {tag}"
    checks: list[tuple[str, bool, str]] = []

    try:
        before = totals(url)
    except psycopg.Error as exc:
        print(f"cannot reach Tiger Data: {type(exc).__name__}")
        return 1
    print(f"session {session}, tag {tag}; rows before: {before[0]} touch, {before[1]} hazard")

    bus = Bus()
    answers: list[tuple[float, SpeakRequest]] = []
    bus.subscribe(SpeakRequest, lambda m: answers.append((time.monotonic(), m)))
    store = register(bus)
    try:
        now = time.time()
        box = (300.0, 160.0, 340.0, 200.0)
        events: list[Any] = [
            TouchEvent(now, 1, "bottle", name, "touch", box, ["mug", "cereal box"]),
            TouchEvent(now + 1, 1, "bottle", name, "release", box, ["mug", "cereal box"]),
            TouchEvent(now + 2, 1, "bottle", name, "touch", box, ["mug", "cereal box"]),
            TouchEvent(now + 3, 2, "cup", "", "touch", (100.0, 100.0, 160.0, 180.0), []),
            HazardEvent(now + 4, "obstacle", "grok", 0.8),
        ]
        worst = 0.0
        for ev in events:
            t0 = time.perf_counter()
            bus.publish(ev)
            worst = max(worst, time.perf_counter() - t0)
        t_write = time.monotonic()
        written = wait(lambda: store.written >= len(events), 20)
        checks.append((
            "bus events written",
            written and store.dropped == 0,
            (f"{store.written}/{len(events)} rows in {time.monotonic() - t_write:.2f} s "
            f"(includes first connect), slowest publish {worst * 1000:.2f} ms"),
        ))

        with db.connect(url) as conn:
            kinds = [r[0] for r in conn.execute(
                "SELECT kind FROM touch_events WHERE session_id = %s AND object_id = 1 ORDER BY ts",
                (session,))]
            hz = conn.execute(
                "SELECT type, source FROM hazard_events WHERE session_id = %s", (session,)).fetchall()
        checks.append(("touch, release, retouch rows in order", kinds == ["touch", "release", "touch"],
                       f"{kinds}"))
        checks.append(("hazard row", hz == [("obstacle", "grok")], f"{hz}"))

        t_q = time.monotonic()
        bus.publish(LastSeenQuery(time.time(), name.upper()))
        got = wait(lambda: len(answers) >= 1, 10)
        text = answers[0][1].text if got else None
        checks.append((
            "last-seen answer over the bus",
            bool(text) and text.startswith(name) and "next to mug and cereal box" in (text or ""),
            f"{text!r} in {answers[0][0] - t_q:.2f} s" if got else "no answer",
        ))
        bus.publish(LastSeenQuery(time.time(), f"never seen {tag}"))
        got = wait(lambda: len(answers) >= 2, 10)
        checks.append(("unknown object answer", got and answers[1][1].text == NOT_SEEN,
                       repr(answers[1][1].text) if got else "no answer"))
    finally:
        store.stop()

    # Outage: connect fails in this process; the real database is untouched.
    real_connect = db.connect
    outage = {"on": True}

    def flaky_connect(u: str) -> Any:
        if outage["on"]:
            raise psycopg.OperationalError("simulated outage")
        return real_connect(u)

    db.connect = flaky_connect  # type: ignore[assignment]
    store2 = writer.Store(lambda _m: None, url)
    try:
        t0 = time.perf_counter()
        for i in range(20):
            store2.on_touch_event(TouchEvent(time.time(), 10 + i, "cup", "", "touch", (1, 1, 9, 9), []))
        slow = time.perf_counter() - t0
        dropped = wait(lambda: store2.dropped == 20, 5)
        checks.append(("outage: events dropped, handlers fast", dropped and store2.written == 0,
                       f"dropped {store2.dropped}, 20 calls took {slow * 1000:.2f} ms"))
        outage["on"] = False
        print(f"  (waiting {writer.RETRY_INTERVAL_SECONDS:.0f} s reconnect interval)")
        time.sleep(writer.RETRY_INTERVAL_SECONDS + 0.5)
        t_rec = time.monotonic()
        store2.on_touch_event(TouchEvent(time.time(), 99, "cup", f"Recovered mug {tag}", "touch",
                                         (1, 1, 9, 9), []))
        recovered = wait(lambda: store2.written == 1, 15)
        checks.append(("recovery: writes resume after reconnect", recovered,
                       f"written {store2.written} in {time.monotonic() - t_rec:.2f} s"))
    finally:
        store2.stop()
        db.connect = real_connect  # type: ignore[assignment]

    if args.keep:
        print(f"kept rows for session {session}")
    else:
        with db.connect(url) as conn:
            t = conn.execute("DELETE FROM touch_events WHERE session_id = %s", (session,)).rowcount
            h = conn.execute("DELETE FROM hazard_events WHERE session_id = %s", (session,)).rowcount
        after = totals(url)
        checks.append(("cleanup removed only this run's rows", after == before,
                       f"deleted {t} touch + {h} hazard; totals now {after[0]} / {after[1]}"))

    print()
    for label, passed, detail in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {label}: {detail}")
    return 0 if all(p for _, p, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
