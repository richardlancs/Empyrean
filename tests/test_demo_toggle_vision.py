"""Detector switching in vision: background loading, validation and DetectorStatus."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from contracts import DetectorStatus, ModeChange
from tests.test_vision_p1 import FakeHands, FakeMP, FakeWorld, FakeYOLO
from vision.build_demo_weights import DEMO_OBJECTS
from vision.vision import (
    TRAINED_IDENTITY,
    DemoCandidate,
    DemoUnavailable,
    Vision,
    VisionProcessor,
    load_demo_candidate,
)

RAW = np.zeros((720, 1280, 3), dtype=np.uint8)


def statuses(published: list[Any]) -> list[DetectorStatus]:
    return [m for m in published if isinstance(m, DetectorStatus)]


def wait_for(predicate: Any, timeout: float = 3.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def candidate(detector: Any) -> DemoCandidate:
    return DemoCandidate(detector, False, "trained", TRAINED_IDENTITY, "demo-yolo11s.pt, 19.2 MB, SHA-256 abc", None)


def test_switch_to_demo_loads_off_the_frame_path_then_swaps_between_frames() -> None:
    """Regular keeps processing while Demo loads; active changes only after the swap."""
    gate = threading.Event()
    world = FakeWorld()

    def slow_loader() -> DemoCandidate:
        gate.wait(2)
        return candidate(world)

    published: list[Any] = []
    vision = Vision(published.append, loader=slow_loader, start=False)
    processor = VisionProcessor(FakeYOLO(), FakeHands(), FakeMP)
    first = processor.process(RAW, 0, 1.0).objects[0]
    vision.on_mode(ModeChange(ts=1.0, mode="demo", request_id="d1"))
    vision._apply_mode(processor)
    assert [(s.state, s.active_mode) for s in statuses(published)] == [("switching", "actual")]
    # Still loading: frames are processed by Regular and nothing claims Demo.
    vision._apply_mode(processor)
    assert processor.mode == "actual" and processor.process(RAW, 1, 2.0).objects[0].class_label == "bottle"
    gate.set()
    assert wait_for(lambda: vision._ready is not None)
    vision._apply_mode(processor)
    last = statuses(published)[-1]
    assert (last.state, last.active_mode, last.request_id, last.detector) == ("active", "demo", "d1", TRAINED_IDENTITY)
    assert "SHA-256" in last.checkpoint and last.demo_kind == "trained"
    demo_obj = processor.process(RAW, 2, 3.0).objects[0]
    assert demo_obj.class_label == "toothpaste" and demo_obj.object_id != first.object_id

    vision.on_mode(ModeChange(ts=4.0, mode="actual", request_id="a1"))
    vision._apply_mode(processor)
    last = statuses(published)[-1]
    assert (last.state, last.active_mode, last.request_id) == ("active", "actual", "a1")
    back = processor.process(RAW, 3, 4.0).objects[0]
    assert back.object_id not in {first.object_id, demo_obj.object_id}  # no reused id, no stale name


def test_a_superseded_load_is_cached_not_installed_and_reused_later() -> None:
    """Regular requested while Demo loads: stay Regular; a later Demo request swaps at once."""
    gate = threading.Event()
    loads: list[int] = []

    def loader() -> DemoCandidate:
        loads.append(1)
        gate.wait(2)
        return candidate(FakeWorld())

    published: list[Any] = []
    vision = Vision(published.append, loader=loader, start=False)
    processor = VisionProcessor(FakeYOLO(), FakeHands(), FakeMP)
    vision.on_mode(ModeChange(ts=1.0, mode="demo", request_id="d1"))
    vision._apply_mode(processor)
    vision.on_mode(ModeChange(ts=2.0, mode="actual", request_id="a1"))
    vision._apply_mode(processor)
    gate.set()
    assert wait_for(lambda: vision._cached is not None)
    vision._apply_mode(processor)
    assert processor.mode == "actual"
    assert statuses(published)[-1].active_mode == "actual"
    assert not any(s.active_mode == "demo" for s in statuses(published))
    vision.on_mode(ModeChange(ts=3.0, mode="demo", request_id="d2"))
    vision._apply_mode(processor)
    assert processor.mode == "demo" and statuses(published)[-1].request_id == "d2"
    assert len(loads) == 1  # the validated candidate was reused, not reloaded


def test_a_cached_fallback_is_not_reused_once_trained_weights_are_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fallback cached, then demo-yolo11s.pt installed: re-entering Demo loads the trained one."""
    import vision.vision as v

    trained = tmp_path / "demo-yolo11s.pt"
    prompts = tmp_path / "demo-prompts.pt"
    prompts.write_bytes(b"prompts")
    monkeypatch.setattr(v, "TRAINED_DEMO_WEIGHTS", trained)
    fallback = DemoCandidate(FakeWorld(), False, "prompt-fallback", v.FALLBACK_IDENTITY,
                             "yoloe + prompts", v.checkpoint_stamp(prompts))
    loads: list[str] = []

    def loader() -> DemoCandidate:
        if trained.is_file():
            loads.append("trained")
            return candidate(FakeWorld())
        loads.append("prompt-fallback")
        return fallback

    published: list[Any] = []
    vision = Vision(published.append, loader=loader, start=False)
    processor = VisionProcessor(FakeYOLO(), FakeHands(), FakeMP)
    vision.on_mode(ModeChange(ts=1.0, mode="demo", request_id="d1"))
    vision._apply_mode(processor)
    assert wait_for(lambda: vision._ready is not None)
    vision._apply_mode(processor)
    assert statuses(published)[-1].demo_kind == "prompt-fallback"
    vision.on_mode(ModeChange(ts=2.0, mode="actual", request_id="a1"))
    vision._apply_mode(processor)

    trained.write_bytes(b"trained weights")  # installed without restarting
    vision.on_mode(ModeChange(ts=3.0, mode="demo", request_id="d2"))
    vision._apply_mode(processor)
    assert processor.mode == "actual"  # the stale fallback was not swapped in
    assert (statuses(published)[-1].state, statuses(published)[-1].request_id) == ("switching", "d2")
    assert wait_for(lambda: vision._ready is not None)
    vision._apply_mode(processor)
    last = statuses(published)[-1]
    assert processor.mode == "demo"
    assert (last.state, last.request_id, last.demo_kind) == ("active", "d2", "trained")
    assert loads == ["prompt-fallback", "trained"]


def test_failed_load_keeps_regular_working() -> None:
    """An exception in the loader is a failed status; Regular keeps processing frames."""

    def broken() -> DemoCandidate:
        raise RuntimeError("corrupt")

    published: list[Any] = []
    vision = Vision(published.append, loader=broken, start=False)
    processor = VisionProcessor(FakeYOLO(), FakeHands(), FakeMP)
    vision.on_mode(ModeChange(ts=1.0, mode="demo", request_id="d1"))
    vision._apply_mode(processor)
    assert wait_for(lambda: statuses(published)[-1].state == "failed")
    assert processor.mode == "actual" and statuses(published)[-1].active_mode == "actual"
    assert processor.process(RAW, 0, 1.0).objects[0].class_label == "bottle"


# --------------------------- checkpoint validation ---------------------------


class FakeModel:
    """Stands in for an Ultralytics model: names, task, predict."""

    def __init__(self, names: Any, task: str = "detect", predict_error: Exception | None = None) -> None:
        self.names = names
        self.task = task
        self._predict_error = predict_error

    def predict(self, *args: Any, **kwargs: Any) -> list[Any]:
        if self._predict_error:
            raise self._predict_error
        return [SimpleNamespace()]


def installed(tmp_path: Path, age: float = 60.0) -> Path:
    path = tmp_path / "demo-yolo11s.pt"
    path.write_bytes(b"checkpoint bytes")
    past = time.time() - age
    os.utime(path, (past, past))
    return path


def load(tmp_path: Path, factory: Any, **kw: Any) -> DemoCandidate:
    return load_demo_candidate(weights=tmp_path / "demo-yolo11s.pt", manifest=tmp_path / "training-status.json",
                               install_record=tmp_path / "install.json", yolo_factory=factory, **kw)


def test_valid_checkpoint_is_identified_by_size_and_hash(tmp_path: Path) -> None:
    installed(tmp_path)
    result = load(tmp_path, lambda path: FakeModel({i: n for i, n in enumerate(DEMO_OBJECTS)}))
    assert result.kind == "trained" and result.identity == TRAINED_IDENTITY
    assert "demo-yolo11s.pt" in result.checkpoint and "SHA-256" in result.checkpoint


def test_missing_checkpoint_explains_how_to_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import vision.vision as v

    monkeypatch.setattr(v, "DEMO_WEIGHTS", tmp_path / "none.pt")
    calls: list[str] = []
    with pytest.raises(DemoUnavailable, match="No demo-trained checkpoint is installed.*rename"):
        load(tmp_path, lambda path: calls.append(path))
    assert calls == []  # nothing was loaded, nothing downloaded


def test_checkpoint_still_being_copied_is_refused(tmp_path: Path) -> None:
    installed(tmp_path, age=1.0)
    with pytest.raises(DemoUnavailable, match="may still be copying"):
        load(tmp_path, lambda path: FakeModel(list(DEMO_OBJECTS)))


def test_manifest_hash_mismatch_is_refused(tmp_path: Path) -> None:
    installed(tmp_path)
    (tmp_path / "training-status.json").write_text(json.dumps({"sha256": "0" * 64}), encoding="utf-8")
    with pytest.raises(DemoUnavailable, match="does not match the SHA-256"):
        load(tmp_path, lambda path: FakeModel(list(DEMO_OBJECTS)))


def test_manifest_hash_match_is_accepted(tmp_path: Path) -> None:
    import hashlib

    path = installed(tmp_path)
    (tmp_path / "training-status.json").write_text(
        json.dumps({"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "status": "experimental; NOT demo-ready", "classes": list(DEMO_OBJECTS)}),
        encoding="utf-8",
    )
    result = load(tmp_path, lambda p: FakeModel(list(DEMO_OBJECTS)))
    assert result.kind == "trained"
    assert "status: experimental; NOT demo-ready" in result.checkpoint  # the team's status is shown, not hidden


def test_manifest_with_other_classes_is_refused(tmp_path: Path) -> None:
    import hashlib

    path = installed(tmp_path)
    (tmp_path / "training-status.json").write_text(
        json.dumps({"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "classes": ["keys", "phone"]}),
        encoding="utf-8",
    )
    with pytest.raises(DemoUnavailable, match="not the eight demo objects"):
        load(tmp_path, lambda p: FakeModel(list(DEMO_OBJECTS)))


@pytest.mark.parametrize(
    ("factory", "reason"),
    [
        (lambda p: FakeModel({0: "bottle", 1: "cup"}), "wrong classes"),
        (lambda p: FakeModel(list(DEMO_OBJECTS)[:7]), "missing watch"),
        (lambda p: FakeModel(list(DEMO_OBJECTS), task="segment"), "not a detector"),
        (lambda p: (_ for _ in ()).throw(RuntimeError("bad zip")), "could not be loaded"),
        (lambda p: FakeModel(list(DEMO_OBJECTS), predict_error=TypeError("x")), "could not run"),
    ],
)
def test_invalid_or_incompatible_checkpoints_are_refused(tmp_path: Path, factory: Any, reason: str) -> None:
    installed(tmp_path)
    with pytest.raises(DemoUnavailable, match=reason):
        load(tmp_path, factory)
