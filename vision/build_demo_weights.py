"""Build the demo-mode detector prompts once, in a setup shell.

    python -m vision.capture_demo_refs     (first: take reference pictures)
    python -m vision.build_demo_weights

Demo mode detects with pretrained YOLOE. YOLOE is shown a reference picture of
each demo object (a "visual prompt") and turns it into an embedding; nothing is
trained. This script reads the pictures and boxes listed in
vision/demo_refs/refs.json, keeps one prompt per picture plus one averaged prompt
per object, adds text
embeddings for the vehicle classes hazard/ needs, and saves the result to
vision/models/demo-prompts.pt.

The first run downloads the YOLOE weights and a text encoder, so run it with a
network connection before the demo. The app only loads the saved files and
never downloads anything itself.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("vision")
VISION_DIR = Path(__file__).resolve().parent
MODEL_DIR = VISION_DIR / "models"
REFS_DIR = VISION_DIR / "demo_refs"
REFS_FILE = "refs.json"
BASE_WEIGHTS = MODEL_DIR / "yoloe-11s-seg.pt"
DEMO_PROMPTS = MODEL_DIR / "demo-prompts.pt"

# The objects shown in the demo. The label is what is spoken if Grok has not
# named the object yet, and is the hint Grok gets.
DEMO_OBJECTS = (
    "water bottle",
    "toothbrush",
    "toothpaste",
    "charger",
    "phone",
    "headphones",
    "keys",
    "watch",
)
# hazard/ tier A looks for these labels, so demo mode must keep detecting them.
VEHICLE_LABELS = ("car", "bus", "truck", "motorcycle", "bicycle")


def load_refs(refs_dir: Path) -> list[dict[str, Any]]:
    """Read refs.json: a list of {"file", "label", "box"} with box as x1, y1, x2, y2 pixels."""
    path = refs_dir / REFS_FILE
    if not path.is_file():
        raise FileNotFoundError(
            f"No reference list at {path}. Run `python -m vision.capture_demo_refs` first."
        )
    refs = json.loads(path.read_text(encoding="utf-8"))
    if not refs:
        raise ValueError(f"{path} lists no reference pictures")
    return refs


def _embed_reference(model: Any, image: Any, box: list[float]) -> Any:
    """Return YOLOE's visual prompt embedding (1 x 1 x dim) for one boxed object."""
    import numpy as np
    from ultralytics.models.yolo.yoloe import YOLOEVPSegPredictor

    predictor = YOLOEVPSegPredictor(
        overrides={"task": "segment", "mode": "predict", "save": False, "batch": 1, "verbose": False}
    )
    predictor.set_prompts({"bboxes": np.array([box], dtype=float), "cls": np.array([0])})
    predictor.setup_model(model=model.model, verbose=False)
    return predictor.get_vpe(image)


def build(refs_dir: Path = REFS_DIR, output: Path = DEMO_PROMPTS) -> list[str]:
    """Save class names and prompt embeddings for the demo detector; return the names."""
    import cv2
    import torch
    from ultralytics import YOLOE

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model = YOLOE(str(BASE_WEIGHTS))
    per_label: dict[str, list[Any]] = {}
    for ref in load_refs(refs_dir):
        image = cv2.imread(str(refs_dir / ref["file"]))
        if image is None:
            raise FileNotFoundError(f"Cannot read reference picture {refs_dir / ref['file']}")
        embedding = _embed_reference(model, image, ref["box"])
        per_label.setdefault(ref["label"], []).append(embedding[0, 0])
    # One prompt per picture plus one averaged prompt per object. Measured on the
    # first 62 pictures (each left out in turn): 45% found, against 29% for the
    # average alone and 40% for single pictures alone. The "/n" suffix is cut off
    # by vision.tracked_objects, so every prompt reports the plain object name.
    names: list[str] = []
    rows: list[Any] = []
    for label, embeddings in per_label.items():
        for number, embedding in enumerate(embeddings, start=1):
            names.append(f"{label}/{number}")
            rows.append(torch.nn.functional.normalize(embedding, dim=-1))
        names.append(f"{label}/mean")
        rows.append(torch.nn.functional.normalize(torch.stack(embeddings).mean(dim=0), dim=-1))
    visual = torch.stack(rows).unsqueeze(0)
    # Ultralytics looks for (and downloads) the text encoder in the working directory.
    previous = Path.cwd()
    os.chdir(MODEL_DIR)
    try:
        text = model.get_text_pe(list(VEHICLE_LABELS))
    finally:
        os.chdir(previous)
    names += list(VEHICLE_LABELS)
    torch.save({"names": names, "embeddings": torch.cat([visual, text.to(visual)], dim=1)}, output)
    for missing in sorted(set(DEMO_OBJECTS) - set(per_label)):
        log.warning("No reference picture for '%s'; demo mode will not detect it", missing)
    return names


def main() -> None:
    """Build the prompts and log what was written."""
    parser = argparse.ArgumentParser(prog="python -m vision.build_demo_weights")
    parser.add_argument("--refs", type=Path, default=REFS_DIR, help="folder holding refs.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    names = build(args.refs)
    log.info("Demo prompts written to %s", DEMO_PROMPTS)
    log.info("Prompts: %d for: %s", len(names), ", ".join(dict.fromkeys(n.split("/")[0] for n in names)))


if __name__ == "__main__":
    main()
