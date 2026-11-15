"""Evaluate baseline and candidate on all bootstrap validation objects."""

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import torch
import yaml
from ultralytics import YOLO
from ultralytics.utils import torch_utils

sys.path.insert(0, str(Path.cwd()))
from config import DEMO_DET_MIN_CONFIDENCE
from vision.evaluate_demo_detector import box_iou
from vision.vision import TRAINED_DEMO_IMAGE_SIZE

torch_utils.NUM_THREADS = 4
torch.set_num_threads(4)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline", type=Path, default=Path("scratch/p1-comparison-baseline.pt"))
parser.add_argument("--candidate", type=Path,
                    default=Path("scratch/p1-runs/candidate-v1/weights/best.pt"))
parser.add_argument("--output-dir", type=Path, default=Path("training_data/person1/results"))
args = parser.parse_args()
results = args.output_dir
results.mkdir(parents=True, exist_ok=True)
weights = {
    "baseline": args.baseline,
    "candidate": args.candidate,
}
root = Path("training_data/bootstrap")
config = yaml.safe_load((root / "data.yaml").read_text())
names = config["names"]
for tag, path in weights.items():
    model = YOLO(str(path))
    rows = []
    per = defaultdict(lambda: {"correct": 0, "total": 0})
    fp = 0
    latencies = []
    images = sorted((root / "images/val").glob("*.jpg"))
    model.predict(
        cv2.imread(str(images[0])),
        imgsz=TRAINED_DEMO_IMAGE_SIZE,
        conf=DEMO_DET_MIN_CONFIDENCE,
        device="cpu",
        agnostic_nms=True,
        verbose=False,
    )
    for source in images:
        image = cv2.imread(str(source))
        h, w = image.shape[:2]
        gt = []
        for line in (
            (root / "labels/val" / f"{source.stem}.txt").read_text().splitlines()
        ):
            cls, cx, cy, bw, bh = map(float, line.split())
            gt.append(
                {
                    "label": names[int(cls)],
                    "box": [
                        (cx - bw / 2) * w,
                        (cy - bh / 2) * h,
                        (cx + bw / 2) * w,
                        (cy + bh / 2) * h,
                    ],
                }
            )
        start = time.perf_counter()
        pred = model.predict(
            image,
            imgsz=TRAINED_DEMO_IMAGE_SIZE,
            conf=DEMO_DET_MIN_CONFIDENCE,
            device="cpu",
            agnostic_nms=True,
            verbose=False,
        )[0]
        latencies.append((time.perf_counter() - start) * 1000)
        det = [
            {"label": model.names[int(c)], "confidence": float(s), "box": b}
            for b, c, s in zip(
                pred.boxes.xyxy.tolist(),
                pred.boxes.cls.tolist(),
                pred.boxes.conf.tolist(),
            )
        ]
        used = set()
        targets = []
        for target in gt:
            choices = [
                (box_iou(d["box"], target["box"]), i)
                for i, d in enumerate(det)
                if i not in used and d["label"] == target["label"]
            ]
            best, index = max(choices, default=(0, None))
            correct = best >= 0.5
            if correct:
                used.add(index)
            per[target["label"]]["total"] += 1
            per[target["label"]]["correct"] += int(correct)
            overlap = max(
                [(box_iou(d["box"], target["box"]), d["label"]) for d in det],
                default=(0, None),
            )
            targets.append(
                {
                    **target,
                    "correct": correct,
                    "best_correct_class_iou": best,
                    "highest_overlap_label": overlap[1],
                    "highest_overlap_iou": overlap[0],
                }
            )
        fp += len(det) - len(used)
        rows.append(
            {
                "file": source.name,
                "targets": targets,
                "detections": det,
                "inference_ms": latencies[-1],
            }
        )
    report = {
        "weights_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "dataset": "frozen bootstrap validation: 10 images / 13 boxes",
        "confidence": DEMO_DET_MIN_CONFIDENCE,
        "iou_required": 0.5,
        "imgsz": TRAINED_DEMO_IMAGE_SIZE,
        "device": "cpu",
        "torch_threads": 4,
        "warmup_excluded": True,
        "per_class": dict(per),
        "false_positive_boxes": fp,
        "median_inference_ms": statistics.median(latencies),
        "images": rows,
    }
    (results / f"{tag}-bootstrap-eval.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(
        tag,
        json.dumps(
            {
                k: report[k]
                for k in ["per_class", "false_positive_boxes", "median_inference_ms"]
            }
        ),
        flush=True,
    )
