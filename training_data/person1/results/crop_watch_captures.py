"""Crop watch references without resizing and translate their pixel boxes."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image


def crop_watches(root: Path, backup: Path) -> dict:
    """Back up source sessions, crop watches with context, and record provenance."""
    manifest_path = root / "results/watch-crop-manifest.json"
    if manifest_path.exists() or backup.exists():
        raise ValueError("Already processed, or backup exists; use fresh original inputs")
    jobs = []
    for split in ("train", "eval"):
        refs = json.loads((root / split / "refs.json").read_text(encoding="utf-8"))
        for ref in refs:
            if ref["label"] != "watch":
                continue
            source = root / split / ref["file"]
            with Image.open(source) as image:
                width, height = image.size
            x1, y1, x2, y2 = ref["box"]
            assert 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height
            crop = [max(0, math.floor(x1) - 16), max(0, math.floor(y1) - 16),
                    min(width, math.ceil(x2) + 16), min(height, math.ceil(y2) + 16)]
            jobs.append((split, ref, crop))
    backup.mkdir(parents=True)
    for split in ("train", "eval"):
        shutil.copytree(root / split, backup / split)
    shutil.copy2(root / "results/capture-validation.json", backup / "capture-validation.json")
    rows = []
    for split, ref, crop in jobs:
        source = root / split / ref["file"]
        original_box = ref["box"][:]
        original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        with Image.open(source) as image:
            cropped = image.crop(crop)
            cropped.save(source, quality=95, subsampling=0)
        ref["box"] = [original_box[0] - crop[0], original_box[1] - crop[1],
                      original_box[2] - crop[0], original_box[3] - crop[1]]
        rows.append({"split": split, "file": ref["file"], "crop_xyxy": crop,
                     "original_box": original_box, "box": ref["box"],
                     "original_sha256": original_hash,
                     "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    for split in ("train", "eval"):
        refs = json.loads((backup / split / "refs.json").read_text(encoding="utf-8"))
        boxes = {row["file"]: row["box"] for row in rows if row["split"] == split}
        for ref in refs:
            if ref["file"] in boxes:
                ref["box"] = boxes[ref["file"]]
        (root / split / "refs.json").write_text(json.dumps(refs, indent=2) + "\n", encoding="utf-8")
    manifest = {"operation": "watch crops with 16 pixels of context; no resizing",
                "purpose": "Remove unlabelled neighbouring demo objects",
                "evaluation_status": "Original candidate scores predate these crops; retrain and reevaluate",
                "images": rows}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    """Apply the crop once to original sessions while retaining a local backup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("training_data/person1"))
    parser.add_argument("--backup", type=Path, required=True)
    args = parser.parse_args()
    crop_watches(args.root, args.backup)


if __name__ == "__main__":
    main()
