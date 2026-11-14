"""Extend the frozen eight-class baseline with one teammate's labelled capture sessions."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
from pathlib import Path

import cv2
import yaml

from vision.build_demo_weights import DEMO_OBJECTS, load_refs

log = logging.getLogger("vision")


def extend_dataset(
    base: Path, output: Path, train_refs: list[Path], val_refs: list[Path],
) -> Path:
    """Copy the baseline, append labelled sessions, and reject train/validation leakage."""
    if output.exists():
        raise ValueError(f"Choose a new output directory: {output}")
    config = yaml.safe_load((base / "data.yaml").read_text(encoding="utf-8"))
    names = config["names"]
    names = [names[index] for index in range(len(names))] if isinstance(names, dict) else names
    if names != list(DEMO_OBJECTS):
        raise ValueError("Baseline must retain the canonical eight-class order")
    additions = []
    for split, directories in (("train", train_refs), ("val", val_refs)):
        for source_index, directory in enumerate(directories):
            root = directory.resolve()
            refs = load_refs(root)
            if len({ref["file"] for ref in refs}) != len(refs):
                raise ValueError("Capture one demo item per image; duplicate image annotations found")
            for ref in refs:
                source = (root / ref["file"]).resolve()
                if source.parent != root or ref["label"] not in DEMO_OBJECTS:
                    raise ValueError(f"Invalid source or class: {ref['file']}")
                image = cv2.imread(str(source))
                if image is None:
                    raise ValueError(f"Cannot read {source}")
                height, width = image.shape[:2]
                x1, y1, x2, y2 = ref["box"]
                if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                    raise ValueError(f"Box outside image: {source}")
                values = [DEMO_OBJECTS.index(ref["label"]), (x1 + x2) / (2 * width),
                          (y1 + y2) / (2 * height), (x2 - x1) / width, (y2 - y1) / height]
                name = f"extra-{source_index}-{source.stem}.jpg"
                additions.append((split, source, name, values, ref["label"]))
    hashes = {split: set() for split in ("train", "val")}
    for split, values in hashes.items():
        for image in (base / "images" / split).iterdir():
            if image.is_file():
                values.add(hashlib.sha256(image.read_bytes()).hexdigest())
    for split, source, _name, _values, _label in additions:
        hashes[split].add(hashlib.sha256(source.read_bytes()).hexdigest())
    if hashes["train"] & hashes["val"]:
        raise ValueError("Identical photo content crosses the training/validation split")
    shutil.copytree(base, output, ignore=shutil.ignore_patterns("*.cache"))
    manifest_path = output / "split.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    for split, source, name, values, label in additions:
        target = output / "images" / split / name
        if target.exists():
            raise ValueError(f"Duplicate output filename: {name}")
        shutil.copy2(source, target)
        (output / "labels" / split / f"{Path(name).stem}.txt").write_text(
            " ".join(str(value) for value in values) + "\n", encoding="utf-8",
        )
        manifest.append({"file": name, "label": label, "split": split,
                         "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    config["path"] = output.resolve().as_posix()
    (output / "data.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return output / "data.yaml"


def main() -> None:
    """Build a separate candidate dataset without changing the frozen baseline."""
    parser = argparse.ArgumentParser(prog="python -m vision.extend_demo_dataset")
    parser.add_argument("--base", type=Path, default=Path("training_data/bootstrap"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-refs", type=Path, nargs="+", required=True)
    parser.add_argument("--val-refs", type=Path, nargs="+", required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    log.info("Candidate dataset: %s", extend_dataset(
        args.base, args.output, args.train_refs, args.val_refs,
    ))


if __name__ == "__main__":
    main()
