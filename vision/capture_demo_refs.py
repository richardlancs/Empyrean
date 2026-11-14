"""Take reference pictures of the demo objects for the demo-mode detector.

    python -m vision.capture_demo_refs

Stop `python -m app` first so the camera is free. For each demo object the
window shows the live camera. Put the object where it will be in the demo:

    SPACE  freeze the frame, then drag a box tightly around the object and
           press ENTER (C cancels the box)
    N      next object (take two or three pictures per object, from different
           angles, before moving on)
    Q      finish

Pictures and boxes go to vision/demo_refs/. Then run
`python -m vision.build_demo_weights`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

import cv2
from dotenv import load_dotenv

from config.thresholds import PROCESS_HEIGHT, PROCESS_WIDTH
from vision.build_demo_weights import DEMO_OBJECTS, REFS_DIR, REFS_FILE

log = logging.getLogger("vision")
WINDOW = "Demo reference capture"
DISPLAY_SCALE = 2  # show the 640 x 360 frame at twice the size so boxes are easy to drag


def _slug(label: str) -> str:
    """Turn an object label into a file-name stem."""
    return label.replace(" ", "_")


def _draw_help(frame: Any, label: str, taken: int) -> Any:
    """Return a display copy of the frame with the current object and keys written on it."""
    view = cv2.resize(frame, (PROCESS_WIDTH * DISPLAY_SCALE, PROCESS_HEIGHT * DISPLAY_SCALE))
    lines = (
        f"Show: {label}   (pictures taken: {taken})",
        "SPACE capture   N next object   Q finish",
    )
    for row, text in enumerate(lines):
        origin = (16, 34 + 32 * row)
        cv2.putText(view, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
        cv2.putText(view, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return view


BUSY_HINT = (
    "No picture from the camera. Another program is probably using it: stop "
    "`python -m app` and any other copy of this tool (Ctrl+C in its terminal), "
    "then try again. If it still fails, check CAMERA_INDEX in .env"
)
READ_GIVE_UP_SECONDS = 5.0  # setup tool only, not a SPEC.md section 9 threshold


OPEN_GIVE_UP_SECONDS = 15.0  # setup tool only; Windows can hang opening a busy camera


def _try_open(index: int, backend: int, seconds: float) -> Any | None:
    """Open one camera backend on a helper thread; return None if it fails or hangs."""
    result: list[Any] = []
    opener = threading.Thread(
        target=lambda: result.append(cv2.VideoCapture(index, backend)), daemon=True
    )
    opener.start()
    opener.join(seconds)
    if result and result[0].isOpened():
        return result[0]
    return None


def _open_camera(index: int) -> Any:
    """Open the camera, falling back to DirectShow if the default Windows driver hangs."""
    camera = _try_open(index, cv2.CAP_ANY, OPEN_GIVE_UP_SECONDS)
    if camera is None and sys.platform == "win32":
        log.info("Default camera driver did not respond; trying DirectShow")
        camera = _try_open(index, cv2.CAP_DSHOW, OPEN_GIVE_UP_SECONDS)
    if camera is None:
        raise RuntimeError(f"{BUSY_HINT} (camera {index} would not open)")
    return camera


def _read_frame(camera: Any) -> Any:
    """Return the next frame at 640 x 360, as vision sees it, or raise if none arrives."""
    deadline = time.monotonic() + READ_GIVE_UP_SECONDS
    while time.monotonic() < deadline:
        ok, raw = camera.read()
        if ok:
            return cv2.resize(raw, (PROCESS_WIDTH, PROCESS_HEIGHT))
        time.sleep(0.05)
    raise RuntimeError(BUSY_HINT)


def capture(refs_dir: Path = REFS_DIR) -> int:
    """Run the capture window; return how many reference pictures are now listed."""
    load_dotenv()
    refs_dir.mkdir(parents=True, exist_ok=True)
    refs_path = refs_dir / REFS_FILE
    refs: list[dict[str, Any]] = (
        json.loads(refs_path.read_text(encoding="utf-8")) if refs_path.is_file() else []
    )
    index = int(os.environ.get("CAMERA_INDEX", "0"))
    log.info("Opening camera %d (close the app and any other capture window first)", index)
    camera = _open_camera(index)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, PROCESS_WIDTH * 2)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, PROCESS_HEIGHT * 2)
    try:
        first = True
        for label in DEMO_OBJECTS:
            taken = sum(1 for ref in refs if ref["label"] == label)
            while True:
                frame = _read_frame(camera)
                if first:
                    log.info("Camera ready. Click the '%s' window, then use its keys", WINDOW)
                cv2.imshow(WINDOW, _draw_help(frame, label, taken))
                if first:
                    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_TOPMOST, 1)  # do not open behind
                    first = False
                key = cv2.waitKey(30) & 0xFF
                if key == ord("q"):
                    return len(refs)
                if key == ord("n"):
                    break
                if key != ord(" "):
                    continue
                view = cv2.resize(
                    frame, (PROCESS_WIDTH * DISPLAY_SCALE, PROCESS_HEIGHT * DISPLAY_SCALE)
                )
                x, y, w, h = cv2.selectROI(WINDOW, view, showCrosshair=False)
                if w == 0 or h == 0:
                    continue
                box = [value / DISPLAY_SCALE for value in (x, y, x + w, y + h)]
                name = f"{_slug(label)}_{taken + 1}.jpg"
                cv2.imwrite(str(refs_dir / name), frame)
                refs.append({"file": name, "label": label, "box": box})
                refs_path.write_text(json.dumps(refs, indent=2), encoding="utf-8")
                taken += 1
                log.info("Saved %s", name)
    finally:
        camera.release()
        cv2.destroyAllWindows()
    return len(refs)


def main() -> None:
    """Capture reference pictures and say what to run next."""
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    try:
        count = capture()
    except RuntimeError as exc:
        log.error("%s", exc)
        sys.exit(1)
    log.info("%d reference pictures listed in %s", count, REFS_DIR / REFS_FILE)
    log.info("Next: python -m vision.build_demo_weights")


if __name__ == "__main__":
    main()
