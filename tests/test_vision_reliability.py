"""Optional model and capture failures must not break COCO or saved datasets."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from vision import capture_demo_refs as capture
from vision import vision
from vision.build_demo_weights import DEMO_OBJECTS


def loader_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Provide required assets and cheap model/hand stand-ins without hardware."""
    for name in (
        "YOLO_WEIGHTS",
        "HAND_MODEL",
        "TRAINED_DEMO_WEIGHTS",
        "DEMO_WEIGHTS",
        "DEMO_PROMPTS",
    ):
        path = tmp_path / name
        monkeypatch.setattr(vision, name, path)
        if name in ("YOLO_WEIGHTS", "HAND_MODEL"):
            path.touch()
    hands = SimpleNamespace(close=lambda: None)
    monkeypatch.setitem(
        sys.modules,
        "mediapipe",
        SimpleNamespace(
            tasks=SimpleNamespace(
                BaseOptions=lambda **kw: kw,
                vision=SimpleNamespace(
                    HandLandmarkerOptions=lambda **kw: kw,
                    RunningMode=SimpleNamespace(VIDEO=1),
                    HandLandmarker=SimpleNamespace(create_from_options=lambda _: hands),
                ),
            )
        ),
    )
    return SimpleNamespace(names={0: "car"})


@pytest.mark.parametrize("failure", ["trained", "prompts", "extra_class"])
def test_optional_demo_failure_keeps_required_coco(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    failure: str,
) -> None:
    """A damaged optional model/prompt or non-eight-class head leaves actual mode usable."""
    coco = loader_environment(monkeypatch, tmp_path)

    def model(path: str) -> Any:
        if path == str(vision.YOLO_WEIGHTS):
            return coco
        if failure == "extra_class":
            return SimpleNamespace(
                names=dict(enumerate([*DEMO_OBJECTS, DEMO_OBJECTS[0]]))
            )
        raise RuntimeError("damaged demo checkpoint")

    monkeypatch.setitem(
        sys.modules, "ultralytics", SimpleNamespace(YOLO=model, YOLOE=model)
    )
    if failure == "prompts":
        vision.DEMO_WEIGHTS.touch()
        vision.DEMO_PROMPTS.touch()
        monkeypatch.setitem(
            sys.modules,
            "torch",
            SimpleNamespace(
                load=lambda *a, **k: (_ for _ in ()).throw(ValueError("bad prompt"))
            ),
        )
    else:
        vision.TRAINED_DEMO_WEIGHTS.touch()
    processor = vision.load_processor()
    try:
        assert processor.detector is coco
        assert processor.demo_detector is None
        assert not processor.set_mode("demo")
    finally:
        processor.close()


def test_required_coco_failure_is_not_silenced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The fallback must not pretend vision works if its mandatory model is broken."""
    loader_environment(monkeypatch, tmp_path)

    def broken(_path: str) -> Any:
        raise RuntimeError("required model broken")

    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=broken))
    with pytest.raises(RuntimeError, match="required model broken"):
        vision.load_processor()


def test_camera_open_finishing_after_timeout_releases_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A late camera-open result cannot hold the webcam after the caller gives up."""
    finish = threading.Event()
    released = threading.Event()

    def slow_open(*_args: Any) -> Any:
        assert finish.wait(2)
        return SimpleNamespace(isOpened=lambda: True, release=released.set)

    monkeypatch.setattr(capture.cv2, "VideoCapture", slow_open)
    try:
        assert capture._try_open(0, 0, 0) is None
    finally:
        finish.set()
    assert released.wait(2)


@pytest.mark.parametrize("opened", [False, True])
def test_failed_open_releases_device_but_success_transfers_ownership(
    monkeypatch: pytest.MonkeyPatch,
    opened: bool,
) -> None:
    """Both failure and success have exactly one camera owner."""
    releases: list[bool] = []
    camera = SimpleNamespace(
        isOpened=lambda: opened, release=lambda: releases.append(opened)
    )
    monkeypatch.setattr(capture.cv2, "VideoCapture", lambda *_: camera)
    result = capture._try_open(0, 0, 1)
    assert (result is camera) is opened
    assert releases == ([] if opened else [False])


@pytest.mark.parametrize("save_ok", [False, True])
def test_capture_never_labels_a_failed_write_or_overwrites_an_existing_photo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    save_ok: bool,
) -> None:
    """Failed JPEG writes stay out of the manifest and existing photos keep their bytes."""
    old = tmp_path / "watch_1.jpg"
    old.write_bytes(b"previous photo")
    keys = iter((ord(" "), ord("q")))
    writes = []
    monkeypatch.setattr(capture, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        capture,
        "_open_camera",
        lambda _: SimpleNamespace(
            set=lambda *a: True, get=lambda _: 640, release=lambda: None
        ),
    )
    monkeypatch.setattr(
        capture, "_read_frame", lambda _: np.zeros((360, 640, 3), np.uint8)
    )
    monkeypatch.setattr(capture.cv2, "imshow", lambda *a: None)
    monkeypatch.setattr(capture.cv2, "setWindowProperty", lambda *a: None)
    monkeypatch.setattr(capture.cv2, "destroyAllWindows", lambda: None)
    monkeypatch.setattr(capture.cv2, "waitKey", lambda _: next(keys))
    monkeypatch.setattr(capture.cv2, "selectROI", lambda *a, **k: (20, 20, 100, 100))

    def write(path: str, _image: Any) -> bool:
        writes.append(Path(path).name)
        if save_ok:
            Path(path).write_bytes(b"new photo")
        return save_ok

    monkeypatch.setattr(capture.cv2, "imwrite", write)
    assert capture.capture(tmp_path, ("watch",), camera_index=0) == int(save_ok)
    assert old.read_bytes() == b"previous photo"
    assert writes == ["watch_2.jpg"]
    manifest = tmp_path / "refs.json"
    if save_ok:
        assert json.loads(manifest.read_text())[0]["file"] == "watch_2.jpg"
    else:
        assert not manifest.exists()
