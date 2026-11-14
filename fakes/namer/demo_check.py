"""Live naming checklist: real scene + real namer + live Grok on a test bus.

Run from the repo root with .env reachable (GROK_API_KEY, GROK_MODEL):
    .venv/bin/python -m fakes.namer.demo_check --images scratch/eval

This is not the demo camera. Frames are a 640 x 360 composite built from
still photos (IMG_8121.jpg, a phone photo of a held Sour Strips bag, plus four
catalog photos squeezed to small labels). Scene still makes the real padded
crops and NameRequests, and the namer makes the real Grok calls.

It runs at PROCESS_FPS in real time and walks through:
  1. three objects become idle together (queue wait vs Grok call time),
  2. touch before the name is back (delayed naming), release, retouch,
  3. Grok failure (an invalid key, set in this process only) with scene's one retry,
  4. recovery (the real key again) on a new object.
Touch-to-speech is NOT measured here: that needs Person 4's audio module.
NameResults reach scene on this frame thread, like a frame loop would.
Prints a report. Never prints keys. Makes about 7 Grok calls.
"""

from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
import time
import unicodedata
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from dotenv import find_dotenv, load_dotenv

import config
from contracts import (
    FrameResult,
    Hand,
    NameRequest,
    NameResult,
    TouchEvent,
    TrackedObject,
)
from namer import register as register_namer
from scene import SceneDatabase

FRAME_SECONDS = 1.0 / config.PROCESS_FPS
BAD_KEY = "invalid-key-for-failure-test"


@dataclass
class Item:
    """One object in the composite frame."""

    object_id: int
    label: str  # COCO class the detector would give
    image: str  # path under --images
    expected: str  # brand that must appear in the name
    slot: tuple[int, int, int, int]  # where it is pasted, x1 y1 x2 y2
    box: tuple[float, float, float, float] | None = None  # detector box, set on paste


ITEMS = [
    # Real phone photo, hand partly covering the bag. Its box is the bag only.
    Item(1, "book", "IMG_8121.jpg", "sour strips", (0, 0, 270, 360)),
    Item(2, "bottle", "condiments/heinz-ketchup.jpg", "heinz", (285, 60, 370, 300)),
    Item(3, "bottle", "drinks/coca-cola.jpg", "coca", (375, 60, 460, 300)),
    Item(4, "cup", "objects/starbucks-mug.jpg", "starbucks", (465, 60, 550, 300)),
    Item(5, "cup", "snacks/pringles-original.jpg", "pringles", (555, 60, 640, 300)),
]
# Bag position inside IMG_8121.jpg (960 x 1280), as fractions of the photo.
BAG_FRACTION = (0.30, 0.10, 0.74, 0.60)


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


def norm(text: str) -> str:
    """Lowercase ASCII letters and digits only, for brand matching."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return "".join(c for c in text.lower() if c.isalnum())


def fit(img: np.ndarray, w: int, h: int) -> tuple[np.ndarray, float, int, int]:
    """Scale img to fit w x h; return it with the scale and the x, y offset."""
    scale = min(w / img.shape[1], h / img.shape[0])
    out = cv2.resize(img, (max(1, int(img.shape[1] * scale)), max(1, int(img.shape[0] * scale))))
    return out, scale, (w - out.shape[1]) // 2, (h - out.shape[0]) // 2


def build_frame(images: Path) -> np.ndarray:
    """Paste every item into one 640 x 360 frame and set each item's box."""
    frame = np.full((config.PROCESS_HEIGHT, config.PROCESS_WIDTH, 3), 170, np.uint8)
    for item in ITEMS:
        img = cv2.imread(str(images / item.image))
        if img is None:
            raise SystemExit(f"cannot read {images / item.image}")
        x1, y1, x2, y2 = item.slot
        small, _scale, dx, dy = fit(img, x2 - x1, y2 - y1)
        ox, oy = x1 + dx, y1 + dy
        frame[oy : oy + small.shape[0], ox : ox + small.shape[1]] = small
        if item.object_id == 1:
            fx1, fy1, fx2, fy2 = BAG_FRACTION
            w, h = small.shape[1], small.shape[0]
            item.box = (ox + fx1 * w, oy + fy1 * h, ox + fx2 * w, oy + fy2 * h)
        else:
            item.box = (float(ox), float(oy), float(ox + small.shape[1]), float(oy + small.shape[0]))
    return frame


class Rig:
    """Scene and namer on one test bus, stepped at PROCESS_FPS in real time."""

    def __init__(self, frame: np.ndarray) -> None:
        self.bus = Bus()
        self.frame = frame
        self.inbox: queue.SimpleQueue[NameResult] = queue.SimpleQueue()
        self.scene = SceneDatabase(lambda _topic, msg: self.bus.publish(msg))
        self.namer = register_namer(self.bus)
        self.bus.subscribe(NameResult, self.inbox.put)  # handed to scene on the frame thread
        self.bus.subscribe(TouchEvent, self._on_touch)
        self.bus.subscribe(NameRequest, self._on_request)
        self.touches: list[tuple[float, TouchEvent]] = []
        self.requests: list[tuple[float, NameRequest]] = []
        self.results: list[tuple[float, NameResult]] = []
        self.visible: list[int] = []
        self.finger_on: int | None = None
        self.frame_id = 0
        self.slowest_frame = 0.0

    def _on_touch(self, ev: TouchEvent) -> None:
        self.touches.append((time.monotonic(), ev))

    def _on_request(self, req: NameRequest) -> None:
        self.requests.append((time.monotonic(), req))

    def step(self) -> None:
        """Deliver NameResults to scene, then process one frame; keep the frame pace."""
        t0 = time.monotonic()
        while True:
            try:
                res = self.inbox.get_nowait()
            except queue.Empty:
                break
            self.results.append((time.monotonic(), res))
            self.scene.handle_name(res)
        hands = []
        if self.finger_on is not None:
            b = ITEMS[self.finger_on - 1].box
            assert b is not None
            tip = ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            hands = [Hand("right", tip, tip, (tip[0] - 40, tip[1] - 40, tip[0] + 40, tip[1] + 40))]
        objects = [
            TrackedObject(i, ITEMS[i - 1].label, 0.9, ITEMS[i - 1].box)  # type: ignore[arg-type]
            for i in self.visible
        ]
        self.scene.handle_frame(FrameResult(time.time(), self.frame_id, self.frame, objects, hands))
        self.frame_id += 1
        spent = time.monotonic() - t0
        self.slowest_frame = max(self.slowest_frame, spent)
        time.sleep(max(0.0, FRAME_SECONDS - spent))

    def frames(self, n: int) -> None:
        """Step n frames."""
        for _ in range(n):
            self.step()

    def until(self, cond: Callable[[], bool], limit: float) -> bool:
        """Step frames until cond() or limit seconds pass."""
        end = time.monotonic() + limit
        while time.monotonic() < end:
            self.step()
            if cond():
                return True
        return False

    def result_for(self, oid: int) -> list[tuple[float, NameResult]]:
        """NameResults received for one object, in order."""
        return [(t, r) for t, r in self.results if r.object_id == oid]

    def touch_events(self, oid: int) -> list[tuple[float, TouchEvent]]:
        """TouchEvents published for one object, in order."""
        return [(t, e) for t, e in self.touches if e.object_id == oid]


def main(argv: list[str]) -> int:
    """Run the checklist and print the report."""
    parser = argparse.ArgumentParser(prog="python -m fakes.namer.demo_check")
    parser.add_argument("--images", type=Path, default=Path("scratch/eval"))
    args = parser.parse_args(argv)
    load_dotenv(find_dotenv(usecwd=True))
    missing = [k for k in ("GROK_API_KEY", "GROK_MODEL") if not os.environ.get(k, "").strip()]
    if missing:
        print(f"Missing {', '.join(missing)} in the environment. Add them to .env.")
        return 2
    logging.basicConfig(level=logging.INFO, format="  log %(name)s: %(message)s")
    real_key = os.environ["GROK_API_KEY"]
    rig = Rig(build_frame(args.images))
    checks: list[tuple[str, bool | None, str]] = []
    print(f"model {os.environ['GROK_MODEL']}, {config.PROCESS_FPS} fps, composite frame\n")

    try:
        # 1-2. Three objects appear; touch the bag as soon as it is idle.
        rig.visible = [1, 2, 3]
        rig.frames(config.STABLE_FRAMES)  # all three idle: three NameRequests together
        rig.finger_on = 1
        rig.until(lambda: bool(rig.touch_events(1)), 2)
        first_touch = rig.touch_events(1)[0]
        rig.until(lambda: bool(rig.result_for(1)), 6)
        rig.finger_on = None
        rig.until(lambda: len(rig.touch_events(1)) >= 2, 2)  # release
        rig.finger_on = 1
        rig.until(lambda: len(rig.touch_events(1)) >= 3, 2)  # retouch
        rig.finger_on = None
        rig.until(lambda: len(rig.touch_events(1)) >= 4, 2)
        rig.until(lambda: all(rig.result_for(i) for i in (2, 3)), 8)

        # 3. Grok failure: invalid key for this process only.
        os.environ["GROK_API_KEY"] = BAD_KEY
        rig.visible = [1, 2, 3, 4]
        rig.until(lambda: len(rig.result_for(4)) >= 2, 15)
        rig.frames(int(config.PROCESS_FPS * 2))  # any third attempt would show up here
        rig.finger_on = 4
        rig.until(lambda: bool(rig.touch_events(4)), 2)
        rig.finger_on = None
        rig.until(lambda: len(rig.touch_events(4)) >= 2, 2)

        # 4. Recovery: real key, new object.
        os.environ["GROK_API_KEY"] = real_key
        rig.visible = [1, 2, 3, 4, 5]
        rig.until(lambda: bool(rig.result_for(5)), 10)
        rig.finger_on = 5
        rig.until(lambda: bool(rig.touch_events(5)), 2)
        rig.finger_on = None
        rig.frames(config.TOUCH_EXIT_FRAMES + 1)
    finally:
        os.environ["GROK_API_KEY"] = real_key
        rig.namer.stop(timeout=10)

    # ---- report ---------------------------------------------------------------
    timings: dict[int, list[Any]] = defaultdict(list)
    for t in rig.namer.timings:
        timings[t.object_id].append(t)
    sent = {r.object_id: t for t, r in reversed(rig.requests)}  # first request per object
    print("\nobject | expected | returned | correct | queued s | Grok call s | request->result s")
    for item in ITEMS:
        results = rig.result_for(item.object_id)
        last = results[-1][1] if results else None
        name = last.name if last else "(no result)"
        ok = bool(last and last.ok and norm(item.expected) in norm(last.name))
        tm = timings.get(item.object_id, [])
        q = " / ".join(f"{t.queued_s:.2f}" for t in tm) or "-"
        a = " / ".join(f"{t.api_s:.2f}{'' if t.ok else ' fail'}" for t in tm) or "-"
        rr = f"{results[-1][0] - sent[item.object_id]:.2f}" if results and item.object_id in sent else "-"
        print(f"{item.object_id} {item.image} | {item.expected} | {name!r} | {'yes' if ok else 'no'} | {q} | {a} | {rr}")

    t1 = rig.touch_events(1)
    res1 = rig.result_for(1)
    late = res1[0][0] - first_touch[0] if res1 else float("nan")
    checks.append(("touch publishes TouchEvent kind=touch", first_touch[1].kind == "touch", ""))
    checks.append((
        "delayed naming exercised (touch landed before the name)",
        None if first_touch[1].name else True,
        (f"name at touch={first_touch[1].name!r}; NameResult arrived {late:+.2f} s after the touch "
        f"(audio speaks a late name only within {config.LATE_NAME_WINDOW_SECONDS} s)"),
    ))
    checks.append(("release publishes kind=release", len(t1) >= 2 and t1[1][1].kind == "release", ""))
    retouch_name = t1[2][1].name if len(t1) >= 3 else None
    checks.append((
        "retouch publishes a new touch carrying the name",
        len(t1) >= 3 and t1[2][1].kind == "touch" and bool(retouch_name),
        f"name={retouch_name!r}",
    ))
    fail_calls = [t for t in timings.get(4, []) if not t.ok]
    checks.append((
        "Grok failure: at most 2 calls, ok=False, touch falls back to the class label",
        len(timings.get(4, [])) == 2
        and all(not r.ok for _, r in rig.result_for(4))
        and bool(rig.touch_events(4))
        and rig.touch_events(4)[0][1].name == "",
        (f"{len(fail_calls)} failed calls, {len(rig.result_for(4))} results, "
        f"touch name={rig.touch_events(4)[0][1].name if rig.touch_events(4) else None!r}"),
    ))
    res5 = rig.result_for(5)
    checks.append((
        "recovery: next object is named once the key works",
        bool(res5) and res5[-1][1].ok,
        f"name={res5[-1][1].name if res5 else None!r}",
    ))
    checks.append((
        "frame handling never waited on Grok",
        rig.slowest_frame < 0.05,
        f"slowest frame {rig.slowest_frame * 1000:.1f} ms",
    ))
    print()
    for label, passed, detail in checks:
        tag = "INFO" if passed is None else "PASS" if passed else "FAIL"
        print(f"[{tag}] {label}{': ' + detail if detail else ''}")
    print("\nNot measured: touch-to-speech (needs Person 4's audio module on the bus).")
    return 0 if all(p is not False for _, p, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
