"""Live Tiger Data check of storage.Store, run by hand with .env loaded.

Run from the repo root:  .venv/bin/python -m fakes.storage.db_check

Feeds 500 TouchEvents and 20 HazardEvents through the real Store (handlers,
queue, worker thread, exactly like the app) under a unique session_id
"evalcheck-<timestamp>", then checks the rows with a separate connection,
runs 15 last-seen queries, measures throughput and query latency, exercises
the outage path with an unreachable URL, and deletes its own rows at the end.
Never prints TIGER_DATABASE_URL; errors are reported by exception class only.
"""

from __future__ import annotations

import csv
import logging
import os
import queue
import random
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import psycopg

from config import PROCESS_HEIGHT, PROCESS_WIDTH
from contracts import (
    HazardEvent,
    LastSeenQuery,
    SpeakRequest,
    TouchEvent,
)
from storage import Store

RESULTS = Path("scratch/eval/results.csv")
MANIFEST = Path("scratch/eval/manifest.csv")
NOT_SEEN = "I have not seen that."
N_TOUCH, N_HAZARD = 500, 20
SPAN_SECONDS = 30 * 60  # touch timestamps spread over the last 30 minutes
DRAIN_TIMEOUT_SECONDS = 300.0
ANSWER_TIMEOUT_SECONDS = 15.0
BAD_URL = "postgresql://evalcheck@192.0.2.1:5432/nothing"  # TEST-NET-1, never routable
# Synthetic names (not Grok replies) that contain LIKE metacharacters.
PERCENT_NAME = "Heinz 50% Less Sugar Ketchup"
UNDERSCORE_NAME = "Snack_Pack Pudding"
CLASS_LABELS = ["bottle", "cup", "book", "cell phone", "bowl", "remote"]


class Check:
    """Collects PASS/FAIL rows for the final table."""

    def __init__(self) -> None:
        """Start with no rows."""
        self.rows: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        """Record one check and return ok."""
        self.rows.append((name, ok, detail))
        return ok

    def print(self) -> None:
        """Print the table."""
        width = max(len(n) for n, _, _ in self.rows)
        print(f"\n{'check':<{width}}  result  detail")
        print(f"{'-' * width}  ------  ------")
        for name, ok, detail in self.rows:
            print(f"{name:<{width}}  {'PASS' if ok else 'FAIL':6}  {detail}")
        failed = sum(not ok for _, ok, _ in self.rows)
        print(f"\n{len(self.rows) - failed} passed, {failed} failed")


class WarningCounter(logging.Handler):
    """Counts WARNING and above records on the storage logger."""

    def __init__(self) -> None:
        """Start at zero."""
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Remember the formatted message."""
        self.messages.append(record.getMessage())


def reply_names() -> list[str]:
    """Names from the Part 2 Grok replies; falls back to manifest brands if absent."""
    names: list[str] = []
    if RESULTS.exists():
        with RESULTS.open(newline="", encoding="utf-8") as f:
            names = [r["name"] for r in csv.DictReader(f) if r.get("name")]
    if not names and MANIFEST.exists():
        with MANIFEST.open(newline="", encoding="utf-8") as f:
            names = [f"{r['expected_brand']} {r['expected_product']}" for r in csv.DictReader(f)]
    return sorted(set(names))


def random_box(rng: random.Random) -> tuple[float, float, float, float]:
    """A valid x1 < x2, y1 < y2 box inside the 640 x 360 frame."""
    w, h = rng.uniform(20, 300), rng.uniform(20, 250)
    x1, y1 = rng.uniform(0, PROCESS_WIDTH - w), rng.uniform(0, PROCESS_HEIGHT - h)
    return (x1, y1, x1 + w, y1 + h)


def build_events(names: list[str], rng: random.Random, now: float) -> tuple[list[TouchEvent], list[HazardEvent]]:
    """500 touches with increasing ts over the last 30 minutes, and 20 hazards."""
    pool = [*names, PERCENT_NAME, UNDERSCORE_NAME]
    touches = []
    for i in range(N_TOUCH):
        ts = now - SPAN_SECONDS + i * (SPAN_SECONDS - 60) / (N_TOUCH - 1)
        name = pool[i % len(pool)] if i < len(pool) * 2 else rng.choice(pool)
        others = [n for n in pool if n != name]
        touches.append(TouchEvent(
            ts=ts, object_id=rng.randint(1, 400), class_label=rng.choice(CLASS_LABELS),
            name=name, kind="touch" if i % 2 == 0 else "release", box=random_box(rng),
            neighbours=rng.sample(others, rng.randint(0, 3)),
        ))
    hazards = [
        HazardEvent(
            ts=now - SPAN_SECONDS + i * 60.0,
            type=rng.choice(["stairs_down", "drop_off", "vehicle", "obstacle"]),
            source=rng.choice(["yolo", "grok"]), confidence=round(rng.uniform(0.6, 1.0), 3),
        )
        for i in range(N_HAZARD)
    ]
    return touches, hazards


def join_names(names: list[str]) -> str:
    """'a', 'a and b', 'a, b and c' (independent of storage.last_seen)."""
    names = [n for n in names if n.strip()]
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}" if names else ""


def expected_answer(touches: list[TouchEvent], text: str) -> tuple[TouchEvent | None, str]:
    """Newest touch whose name or class_label contains text (case-insensitive), and its sentence regex."""
    needle = text.casefold()
    match = next(
        (t for t in reversed(touches) if needle in t.name.casefold() or needle in t.class_label.casefold()),
        None,
    )
    if match is None:
        return None, re.escape(NOT_SEEN)
    label = match.name.strip() or match.class_label
    tail = f", next to {re.escape(join_names(match.neighbours))}" if match.neighbours else ""
    return match, rf"{re.escape(label)}, (just now|\d+ minutes? ago|\d+ hours? ago){tail}\."


def age_ok(sentence: str, event: TouchEvent | None, asked: float) -> bool:
    """The spoken age matches the event's real age to within one minute."""
    if event is None:
        return True
    age = asked - event.ts
    if "just now" in sentence:
        return age < 61
    m = re.search(r"(\d+) minutes? ago", sentence)
    return bool(m) and abs(int(m.group(1)) - age // 60) <= 1


def build_queries(names: list[str], rng: random.Random) -> list[tuple[str, str]]:
    """15 (kind, text) queries: exact, lower case, partial word, LIKE metacharacters, no match."""
    real = [n for n in names if len(n) >= 4]
    picks = rng.sample(real, 9) if len(real) >= 9 else (real * 9)[:9]
    partial = []
    for n in picks[6:9]:
        word = max(n.split(), key=len)
        partial.append(word[1:-1] if len(word) > 4 else word)
    nonce = f"zzqx{rng.randint(10**6, 10**7)}"
    return (
        [("exact", n) for n in picks[0:3]]
        + [("lower case", n.lower()) for n in picks[3:6]]
        + [("partial word", p) for p in partial]
        + [("literal %", "50%"), ("only %", "%"), ("only _", "_"), ("% not wildcard", "less%sugar")]
        + [("no match", nonce), ("_ not wildcard", "heinz_")]
    )


def wait_until(predicate: Any, timeout: float) -> bool:
    """Poll predicate every 50 ms until true or timeout."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def live_checks(check: Check, url: str, session: str, rng: random.Random) -> None:
    """Writes, row checks, last-seen queries and timings against the real database."""
    answers: queue.Queue[SpeakRequest] = queue.Queue()
    store = Store(answers.put, url, start=False)
    store.session_id = session
    store.start()
    names = reply_names()
    check.add("names from Part 2 replies", len(names) >= 9, f"{len(names)} distinct names")
    now = time.time()
    touches, hazards = build_events(names, rng, now)
    try:
        t0 = time.monotonic()
        call_ms = []
        for event in [*touches, *hazards]:
            c0 = time.perf_counter()
            (store.on_touch_event if isinstance(event, TouchEvent) else store.on_hazard_event)(event)
            call_ms.append((time.perf_counter() - c0) * 1000)
        total = N_TOUCH + N_HAZARD
        drained = wait_until(lambda: store.written + store.dropped >= total, DRAIN_TIMEOUT_SECONDS)
        elapsed = time.monotonic() - t0
        check.add("handler calls never block", max(call_ms) < 5, f"max {max(call_ms):.2f} ms per call")
        check.add("queue drained", drained, f"{store.written} written, {store.dropped} dropped in {elapsed:.1f} s")
        check.add("write throughput", store.written > 0,
                  f"{store.written / elapsed:.1f} rows/s incl. connect ({elapsed:.1f} s for {total})")

        with psycopg.connect(url, connect_timeout=5, autocommit=True) as conn:
            n_touch, cx_min, cx_max, cy_min, cy_max = conn.execute(
                "SELECT count(*), min(cx), max(cx), min(cy), max(cy) FROM touch_events WHERE session_id = %s",
                (session,),
            ).fetchone()
            (n_hazard,) = conn.execute(
                "SELECT count(*) FROM hazard_events WHERE session_id = %s", (session,)
            ).fetchone()
            check.add("touch_events row count", n_touch == N_TOUCH, f"{n_touch} of {N_TOUCH}")
            check.add("hazard_events row count", n_hazard == N_HAZARD, f"{n_hazard} of {N_HAZARD}")
            in_range = n_touch > 0 and 0 <= cx_min <= cx_max <= 1 and 0 <= cy_min <= cy_max <= 1
            check.add("cx, cy in 0..1", in_range,
                      f"cx {cx_min:.3f}..{cx_max:.3f}, cy {cy_min:.3f}..{cy_max:.3f}" if n_touch else "no rows")
            newest = touches[-1]
            row = conn.execute(
                "SELECT name, kind, neighbours, extract(epoch FROM ts)::float8 FROM touch_events "
                "WHERE session_id = %s ORDER BY ts DESC LIMIT 1", (session,),
            ).fetchone()
            same = row is not None and row[0] == newest.name and row[1] == newest.kind \
                and list(row[2]) == newest.neighbours and abs(row[3] - newest.ts) < 0.001
            check.add("newest row round-trips", same, "name, kind, neighbours, ts")
            (foreign,) = conn.execute(
                "SELECT count(*) FROM touch_events WHERE session_id <> %s AND ts > to_timestamp(%s)",
                (session, now - SPAN_SECONDS),
            ).fetchone()
            check.add("no other session in the window", foreign == 0,
                      f"{foreign} rows from other sessions in the last 30 min")

        latencies = []
        for kind, text in build_queries(names, rng):
            event, pattern = expected_answer(touches, text)
            asked = time.time()
            q0 = time.monotonic()
            store.on_last_seen_query(LastSeenQuery(ts=asked, text=text))
            try:
                answer = answers.get(timeout=ANSWER_TIMEOUT_SECONDS)
            except queue.Empty:
                check.add(f"last seen: {kind} {text!r}", False, "no SpeakRequest")
                continue
            latencies.append((time.monotonic() - q0) * 1000)
            ok = (re.fullmatch(pattern, answer.text) is not None and age_ok(answer.text, event, asked)
                  and answer.priority == "normal" and answer.source == "storage")
            check.add(f"last seen: {kind} {text!r}", ok, answer.text)
        if latencies:
            check.add("last-seen latency", max(latencies) < 1000,
                      f"p50 {statistics.median(latencies):.0f} ms, max {max(latencies):.0f} ms, n={len(latencies)}")
    finally:
        store.stop()


def outage_check(check: Check) -> None:
    """Unreachable URL: one warning, no exception, every handler call under 5 ms."""
    counter = WarningCounter()
    log = logging.getLogger("storage")
    log.addHandler(counter)
    answers: queue.Queue[SpeakRequest] = queue.Queue()
    raised = None
    call_ms: list[float] = []
    store = Store(answers.put, BAD_URL)
    try:
        rng = random.Random(7)
        for i in range(100):
            ev = (TouchEvent(time.time(), i, "cup", "Test mug", "touch", random_box(rng), [])
                  if i % 5 else HazardEvent(time.time(), "obstacle", "yolo", 0.9))
            c0 = time.perf_counter()
            (store.on_touch_event if isinstance(ev, TouchEvent) else store.on_hazard_event)(ev)
            call_ms.append((time.perf_counter() - c0) * 1000)
        settled = wait_until(lambda: store.dropped >= 100, 15.0)
        store.on_last_seen_query(LastSeenQuery(time.time(), "mug"))
        try:
            fallback = answers.get(timeout=15.0).text
        except queue.Empty:
            fallback = "(none)"
    except Exception as exc:  # noqa: BLE001 - the check is that nothing raises
        raised = type(exc).__name__
    finally:
        store.stop()
        log.removeHandler(counter)
    check.add("outage: no exception", raised is None, raised or "")
    check.add("outage: handler calls < 5 ms", bool(call_ms) and max(call_ms) < 5,
              f"max {max(call_ms):.2f} ms over {len(call_ms)} calls" if call_ms else "no calls")
    check.add("outage: all 100 dropped", settled, f"{store.dropped} dropped, {store.written} written")
    check.add("outage: exactly one warning", len(counter.messages) == 1,
              f"{len(counter.messages)}: " + " | ".join(m[:70] for m in counter.messages))
    check.add("outage: last-seen falls back", fallback == NOT_SEEN, fallback)


def cleanup(check: Check, url: str, session: str) -> None:
    """Delete this run's rows and confirm none remain."""
    try:
        with psycopg.connect(url, connect_timeout=5, autocommit=True) as conn:
            t = conn.execute("DELETE FROM touch_events WHERE session_id = %s", (session,)).rowcount
            h = conn.execute("DELETE FROM hazard_events WHERE session_id = %s", (session,)).rowcount
            (left,) = conn.execute(
                "SELECT (SELECT count(*) FROM touch_events WHERE session_id = %s)"
                " + (SELECT count(*) FROM hazard_events WHERE session_id = %s)", (session, session),
            ).fetchone()
        check.add("cleanup", left == 0, f"deleted {t} touch + {h} hazard rows, {left} left")
    except psycopg.Error as exc:
        check.add("cleanup", False, type(exc).__name__)


def main() -> int:
    """Run every check and print the PASS/FAIL table; exit 1 if any failed."""
    from dotenv import load_dotenv

    load_dotenv()
    logging.basicConfig(level=logging.WARNING, format="  log %(levelname)s %(name)s: %(message)s")
    url = os.environ.get("TIGER_DATABASE_URL", "").strip()
    if not url:
        print("TIGER_DATABASE_URL is not set. Add it to .env and retry.")
        return 1
    session = f"evalcheck-{int(time.time())}"
    print(f"session_id {session}")
    check = Check()
    rng = random.Random(20261114)
    try:
        live_checks(check, url, session, rng)
    except Exception as exc:  # noqa: BLE001 - report, then still clean up
        check.add("live checks ran", False, type(exc).__name__)
    finally:
        cleanup(check, url, session)
    outage_check(check)
    check.print()
    return 0 if all(ok for _, ok, _ in check.rows) else 1


if __name__ == "__main__":
    sys.exit(main())
