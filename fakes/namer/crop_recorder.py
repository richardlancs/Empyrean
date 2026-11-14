"""Save every NameRequest crop to disk, for evaluating naming on real camera crops.

Wire it next to the real namer once app/ has a bus:
    from fakes.namer.crop_recorder import register as record_crops
    recorder = record_crops(bus)              # writes to scratch/camera_crops/
    ...
    recorder.stop()

Each crop is saved exactly as scene sent it to Grok, as <object_id>-<n>.jpg,
with a row in manifest.csv. Fill in expected_brand and expected_product by hand,
then run:
    .venv/bin/python -m fakes.namer.eval_batch \
        --manifest scratch/camera_crops/manifest.csv \
        --results scratch/camera_crops/results.csv
The bus handler only enqueues; a background thread does the disk writes.
"""

from __future__ import annotations

import csv
import logging
import queue
import threading
from pathlib import Path
from typing import Any

from contracts import NameRequest

log = logging.getLogger("namer")

DEFAULT_DIR = Path("scratch/camera_crops")
FIELDS = ["file", "category", "variant", "class_label", "expected_brand", "expected_product"]
_STOP = object()


class CropRecorder:
    """Writes NameRequest crops and a manifest on its own thread."""

    def __init__(self, out_dir: Path = DEFAULT_DIR, variant: str = "camera") -> None:
        """Create the folder and start the writer thread."""
        self.out_dir = out_dir
        self.variant = variant
        self.saved = 0
        self._queue: queue.SimpleQueue[Any] = queue.SimpleQueue()
        self._counts: dict[int, int] = {}
        out_dir.mkdir(parents=True, exist_ok=True)
        self._manifest = out_dir / "manifest.csv"
        self._thread = threading.Thread(target=self._run, name="crop-recorder", daemon=True)
        self._thread.start()

    def on_name_request(self, msg: NameRequest) -> None:
        """Bus handler: enqueue the crop and return immediately."""
        self._queue.put(msg)

    def stop(self, timeout: float = 5.0) -> None:
        """Write what is queued, then stop."""
        self._queue.put(_STOP)
        self._thread.join(timeout)

    def _run(self) -> None:
        """Write each queued crop and append its manifest row."""
        new_file = not self._manifest.exists()
        with self._manifest.open("a", newline="", encoding="utf-8") as f:
            rows = csv.DictWriter(f, fieldnames=FIELDS)
            if new_file:
                rows.writeheader()
            while (msg := self._queue.get()) is not _STOP:
                try:
                    n = self._counts.get(msg.object_id, 0) + 1
                    self._counts[msg.object_id] = n
                    path = self.out_dir / f"{msg.object_id}-{n}.jpg"
                    path.write_bytes(msg.crop_jpeg)
                    rows.writerow({
                        "file": str(path), "category": "camera", "variant": self.variant,
                        "class_label": msg.class_label, "expected_brand": "",
                        "expected_product": "",
                    })
                    f.flush()
                    self.saved += 1
                except Exception:
                    log.exception("could not save crop for object %s", msg.object_id)


def register(bus: Any, out_dir: Path = DEFAULT_DIR, variant: str = "camera") -> CropRecorder:
    """Subscribe a CropRecorder to NameRequest and return it so the caller can stop() it."""
    recorder = CropRecorder(out_dir, variant)
    bus.subscribe(NameRequest, recorder.on_name_request)
    return recorder
