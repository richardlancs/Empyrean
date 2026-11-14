"""Install the tested Python 3.11 dependencies without conflicting OpenCV wheels."""

from __future__ import annotations

import importlib.metadata
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("scripts")


def main() -> None:
    """Install runtime packages, then the Ultralytics wheel with dependencies disabled."""
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    if sys.version_info[:2] != (3, 11):
        raise SystemExit("Use a Python 3.11 virtual environment for this tested dependency set.")
    if sys.prefix == sys.base_prefix:
        raise SystemExit("Create and activate a virtual environment before installing dependencies.")
    for package in ("opencv-python", "opencv-python-headless", "opencv-contrib-python-headless"):
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
        raise SystemExit(
            f"{package} is already installed. Use a fresh venv so it cannot conflict with "
            "opencv-contrib-python; the installer does not remove existing packages."
        )
    if subprocess.run([sys.executable, "-m", "pip", "--version"],
                      capture_output=True, check=False).returncode:
        subprocess.run([sys.executable, "-m", "ensurepip"], check=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
        check=True,
    )
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "-r",
         str(ROOT / "requirements-vision.txt")], check=True,
    )
    import cv2
    import mediapipe
    import torch
    import ultralytics

    log.info("Ready: OpenCV %s, MediaPipe %s, PyTorch %s, Ultralytics %s",
             cv2.__version__, mediapipe.__version__, torch.__version__, ultralytics.__version__)
    log.info("Ultralytics' metadata still names opencv-python; contrib provides the same cv2 "
             "import. Do not install the second wheel to silence that metadata warning.")


if __name__ == "__main__":
    main()
