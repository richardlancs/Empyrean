"""Smoke test for fakes/namer/crop_recorder.py."""

from __future__ import annotations

import csv
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from contracts import NameRequest
from fakes.namer.crop_recorder import register


class Bus:
    def __init__(self) -> None:
        self.subs: dict[type, list[Any]] = defaultdict(list)

    def subscribe(self, kind: type, handler: Any) -> None:
        self.subs[kind].append(handler)

    def publish(self, msg: Any) -> None:
        for handler in self.subs[type(msg)]:
            handler(msg)


def test_records_crops_and_manifest_off_the_handler(tmp_path: Path) -> None:
    bus = Bus()
    recorder = register(bus, tmp_path)
    worst = 0.0
    for oid, label in [(1, "bottle"), (2, "cup"), (1, "bottle")]:  # object 1 retried
        t0 = time.perf_counter()
        bus.publish(NameRequest(time.time(), oid, label, b"\xff\xd8jpeg" + bytes([oid])))
        worst = max(worst, time.perf_counter() - t0)
    recorder.stop()

    assert worst < 0.005
    assert recorder.saved == 3
    assert sorted(p.name for p in tmp_path.glob("*.jpg")) == ["1-1.jpg", "1-2.jpg", "2-1.jpg"]
    assert (tmp_path / "2-1.jpg").read_bytes() == b"\xff\xd8jpeg\x02"
    with (tmp_path / "manifest.csv").open(newline="") as f:
        rows = list(csv.DictReader(f))
    assert [(Path(r["file"]).name, r["class_label"]) for r in rows] == [
        ("1-1.jpg", "bottle"), ("2-1.jpg", "cup"), ("1-2.jpg", "bottle"),
    ]
    assert all(r["expected_brand"] == "" and r["category"] == "camera" for r in rows)
