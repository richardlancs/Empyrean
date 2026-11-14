"""Measure a candidate's class and box accuracy on separately captured reference photos."""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2

from config import DEMO_DET_MIN_CONFIDENCE
from vision.build_demo_weights import DEMO_OBJECTS, load_refs
from vision.vision import TRAINED_DEMO_IMAGE_SIZE

log = logging.getLogger("vision")


def box_iou(a: list[float], b: list[float]) -> float:
    """Return the intersection over union of two xyxy boxes."""
    intersection = max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(
        0.0, min(a[3], b[3]) - max(a[1], b[1]),
    )
    union = ((a[2] - a[0]) * (a[3] - a[1])
             + (b[2] - b[0]) * (b[3] - b[1]) - intersection)
    return intersection / union if union > 0 else 0.0


def evaluate(weights: Path, refs_dir: Path, output: Path, device: str = "cpu") -> dict[str, Any]:
    """Score single-target photos at the actual demo confidence and IoU >= 0.5."""
    if not weights.is_file():
        raise FileNotFoundError(weights)
    os.environ["YOLO_AUTOINSTALL"] = "False"
    from ultralytics import YOLO

    model = YOLO(str(weights))
    if set(model.names.values()) != set(DEMO_OBJECTS):
        raise ValueError("Candidate must keep the complete eight-class head")
    rows = []
    per_class: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    latencies = []
    false_positives = 0
    root = refs_dir.resolve()
    for ref in load_refs(root):
        source = (root / ref["file"]).resolve()
        if source.parent != root or ref["label"] not in DEMO_OBJECTS:
            raise ValueError(f"Invalid reference: {ref['file']}")
        image = cv2.imread(str(source))
        if image is None:
            raise ValueError(f"Cannot read {source}")
        start = time.perf_counter()
        prediction = model.predict(image, conf=DEMO_DET_MIN_CONFIDENCE,
                                   imgsz=TRAINED_DEMO_IMAGE_SIZE, device=device,
                                   agnostic_nms=True, verbose=False)[0]
        latencies.append((time.perf_counter() - start) * 1000)
        detections = [
            {"label": model.names[int(cls)], "confidence": float(score), "box": box}
            for box, cls, score in zip(prediction.boxes.xyxy.tolist(),
                                      prediction.boxes.cls.tolist(), prediction.boxes.conf.tolist())
        ]
        matches = [row for row in detections if row["label"] == ref["label"]]
        best = max((box_iou(row["box"], ref["box"]) for row in matches), default=0.0)
        correct = best >= 0.5
        per_class[ref["label"]][0] += int(correct)
        per_class[ref["label"]][1] += 1
        false_positives += len(detections) - int(correct)
        rows.append({"file": ref["file"], "expected": ref["label"], "correct": correct,
                     "best_iou": best, "detections": detections})
    result = {
        "weights": str(weights), "confidence": DEMO_DET_MIN_CONFIDENCE,
        "iou_required": 0.5, "per_class": {
            name: {"correct": values[0], "total": values[1]} for name, values in per_class.items()
        }, "false_positive_boxes": false_positives,
        "median_inference_ms": statistics.median(latencies), "images": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    """Write a shareable per-item evaluation without starting the camera or Grok."""
    parser = argparse.ArgumentParser(prog="python -m vision.evaluate_demo_detector")
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--refs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    result = evaluate(args.weights, args.refs, args.output, args.device)
    log.info("%s", json.dumps({"per_class": result["per_class"],
                               "false_positive_boxes": result["false_positive_boxes"]}, indent=2))


if __name__ == "__main__":
    main()
