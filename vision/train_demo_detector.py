"""Prepare boxed demo photos and fine-tune YOLO11s in an offline setup session.

Training requires the human approval in AGENTS.md rule 7. Person 2 explicitly
approved this exception and vision integration on 2026-11-14. Model weights and
datasets stay local and git-ignored. Never run training on the camera frame path.

    python -m vision.train_demo_detector --prepare-only
    python -m vision.train_demo_detector --data scratch/demo_dataset/data.yaml

The withheld images come from the same reference capture session. They are a
small validation set, not an independent estimate of live demo accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

from vision.build_demo_weights import DEMO_OBJECTS, REFS_DIR, load_refs

log = logging.getLogger("vision")
BASE_WEIGHTS = Path(__file__).resolve().parent / "models" / "yolo11s.pt"
DEFAULT_DATASET = Path("scratch/demo_dataset")
DEFAULT_RUNS = Path("scratch/demo-training")


def prepare_dataset(refs_dir: Path, output: Path) -> Path:
    """Validate reference boxes and create a dataset withholding one photo per class."""
    refs = load_refs(refs_dir)
    counts = Counter(ref["label"] for ref in refs)
    if set(counts) != set(DEMO_OBJECTS) or any(count < 2 for count in counts.values()):
        raise ValueError("Need at least two boxed photos of each of the eight demo items")
    if len({ref["file"] for ref in refs}) != len(refs):
        raise ValueError("Each reference must name a unique photo")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Dataset directory is not empty: {output}; use --data to reuse it")
    withheld = {
        next(ref["file"] for ref in reversed(refs) if ref["label"] == label)
        for label in DEMO_OBJECTS
    }
    validated: list[tuple[dict[str, Any], Path, int, int]] = []
    root = refs_dir.resolve()
    for ref in refs:
        source = (root / ref["file"]).resolve()
        if source.parent != root:
            raise ValueError(f"Reference must be a file in {root}: {ref['file']}")
        image = cv2.imread(str(source))
        if image is None:
            raise ValueError(f"Cannot read {source}")
        height, width = image.shape[:2]
        x1, y1, x2, y2 = ref["box"]
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError(f"Box outside image bounds: {ref['file']}")
        validated.append((ref, source, width, height))
    hashes = {source.name: hashlib.sha256(source.read_bytes()).hexdigest()
              for _ref, source, _width, _height in validated}
    train_hashes = {digest for file, digest in hashes.items() if file not in withheld}
    val_hashes = {digest for file, digest in hashes.items() if file in withheld}
    if train_hashes & val_hashes:
        raise ValueError("Duplicate image content crosses the training/validation split")
    manifest = []
    for ref, source, width, height in validated:
        split = "val" if ref["file"] in withheld else "train"
        images, annotations = output / "images" / split, output / "labels" / split
        images.mkdir(parents=True, exist_ok=True)
        annotations.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, images / source.name)
        x1, y1, x2, y2 = ref["box"]
        values = [
            DEMO_OBJECTS.index(ref["label"]), (x1 + x2) / (2 * width),
            (y1 + y2) / (2 * height), (x2 - x1) / width, (y2 - y1) / height,
        ]
        (annotations / f"{source.stem}.txt").write_text(
            " ".join(str(value) for value in values) + "\n", encoding="utf-8",
        )
        manifest.append({
            "file": source.name, "label": ref["label"], "split": split,
            "sha256": hashes[source.name],
        })
    names = "".join(f"  {index}: {label}\n" for index, label in enumerate(DEMO_OBJECTS))
    config = output / "data.yaml"
    config.write_text(
        f"path: {output.resolve().as_posix()}\ntrain: images/train\nval: images/val\n"
        f"names:\n{names}", encoding="utf-8",
    )
    (output / "split.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return config


def main() -> None:
    """Prepare data or train local demo weights after explicit human authorization."""
    parser = argparse.ArgumentParser(prog="python -m vision.train_demo_detector")
    parser.add_argument("--refs", type=Path, default=REFS_DIR)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--data", type=Path, help="reuse an already prepared data.yaml")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--epochs", type=int, default=45)
    parser.add_argument("--device", default="cpu", help="cpu, mps, or a CUDA device such as 0")
    parser.add_argument("--weights", type=Path, default=BASE_WEIGHTS)
    parser.add_argument("--freeze", type=int, default=10)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--mosaic", type=float, default=0.5)
    parser.add_argument("--freeze-bn", action="store_true",
                        help="keep batch-normalization statistics fixed for tiny datasets")
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--project", type=Path, default=DEFAULT_RUNS)
    parser.add_argument("--name", default="yolo11s-demo")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    data = args.data or prepare_dataset(args.refs, args.dataset)
    log.info("Demo dataset: %s", data)
    if args.prepare_only:
        return
    if not args.weights.is_file():
        raise FileNotFoundError(f"Missing local initialization weights: {args.weights}")
    os.environ["YOLO_AUTOINSTALL"] = "False"
    import torch
    from ultralytics import YOLO
    from ultralytics.utils import torch_utils

    torch_utils.NUM_THREADS = 4
    torch.set_num_threads(4)
    model = YOLO(str(args.weights))
    if args.freeze_bn:
        def freeze_batch_statistics(trainer: Any) -> None:
            """Avoid changing normalization statistics from a handful of small batches."""
            for layer in trainer.model.modules():
                if isinstance(layer, torch.nn.BatchNorm2d):
                    layer.eval()

        model.add_callback("on_train_batch_start", freeze_batch_statistics)
    result = model.train(
        data=str(data.resolve()), project=str(args.project.resolve()), name=args.name,
        device=args.device, epochs=args.epochs, patience=args.patience, imgsz=416, batch=4, nbs=4,
        workers=0, freeze=args.freeze, optimizer="AdamW", lr0=args.lr, lrf=0.05,
        warmup_epochs=1.0, warmup_bias_lr=0.0, cos_lr=True,
        mosaic=args.mosaic, close_mosaic=8 if args.mosaic else 0, degrees=12, scale=0.35,
        cache=False, amp=False, plots=False, seed=42, deterministic=True,
        save=True, val=True, verbose=False,
    )
    log.info("Training completed: %s; validate best.pt before installing it", result.save_dir)


if __name__ == "__main__":
    main()
