"""Download pretrained camera assets during setup, never inside the frame loop."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("scripts")
HAND_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


def main() -> None:
    """Fetch missing public pretrained assets; retain existing local model files."""
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    os.environ["YOLO_AUTOINSTALL"] = "False"
    from ultralytics import YOLO

    directory = ROOT / "vision" / "models"
    directory.mkdir(parents=True, exist_ok=True)
    detector, hand = directory / "yolo11s.pt", directory / "hand_landmarker.task"
    if not detector.is_file():
        YOLO(str(detector))
    if not hand.is_file():
        temporary = hand.with_suffix(".download")
        try:
            urlretrieve(HAND_URL, temporary)
            temporary.replace(hand)
        finally:
            temporary.unlink(missing_ok=True)
    log.info("Camera assets ready in %s", directory)
    log.info("Optional experimental demo weights are a separate GitHub prerelease asset; "
             "see demotraining.md. They are not downloaded or enabled here.")


if __name__ == "__main__":
    main()
