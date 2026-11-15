# Person 1 candidate-v1: watch and water bottle

## Local crop correction

All 30 training and 10 evaluation watch photos now use the original watch box plus 16 pixels of context on each side. Images are cropped without resizing; box coordinates are translated into the crop. This removes unlabelled background bottles and keeps the watch intact. The 40 bottle photos are unchanged. `results/watch-crop-manifest.json` records original/new hashes, crop rectangles and boxes. Capture metadata retains the original camera resolution and describes postprocessing separately.

The candidate-v1 checkpoint and scores in the historical sections below use the **original uncropped images**. A corrected candidate has now been trained: see [corrected candidate results](results/candidate-cropped/README.md). It matches 10/10 cropped watches, 3/10 original full-frame watches, 10/10 bottles and 11/13 bootstrap targets. Cropping also changes apparent watch scale during model preprocessing; these evaluation images no longer measure full-frame recognition. Retain full-frame live checks for demo readiness.

Original images and annotations are backed up locally in ignored `scratch/person1-original-before-watch-crops/`. The one-time crop operation can be reproduced on original PR inputs with `python training_data/person1/results/crop_watch_captures.py --backup scratch/person1-original-before-watch-crops`. It refuses already processed inputs.

## Original candidate data and run

Own webcam: 30 training and 10 separately captured evaluation photos per item. All 80 images and bounding boxes were validated; no identical images cross the split. The shared bootstrap plus additions retains all eight classes: 131 training images, 30 validation images (33 boxes). The 19 earlier headphones-labelled captures are excluded.

Training: 45 epochs, pretrained YOLO11s initialization, MPS (Apple M5), Python 3.11.9 and the pinned team dependencies. Elapsed training time: 205.289 seconds. Full arguments, initialization/checkpoint hashes and revision are in `results/candidate-v1-metadata.json`. Weights are local at `scratch/p1-runs/candidate-v1/weights/best.pt` and are not committed.

## Historical saved-image evaluation (before cropping)

Correct means matching class with IoU >= 0.5 at the app confidence threshold 0.25. CPU evaluation uses four PyTorch threads and image size 416. Latency is model-call latency, not camera-to-speech or full-app latency.

| Set / item | Shared baseline | candidate-v1 |
|---|---:|---:|
| Own eval: watch | 0/10 | 10/10 |
| Own eval: water bottle | 4/10 | 10/10 |
| Bootstrap val: charger | 1/2 | 1/2 |
| Bootstrap val: headphones | 1/2 | 2/2 |
| Bootstrap val: keys | 1/2 | 2/2 |
| Bootstrap val: phone | 1/1 | 1/1 |
| Bootstrap val: toothbrush | 0/1 | 0/1 |
| Bootstrap val: toothpaste | 1/2 | 1/2 |
| Bootstrap val: watch | 2/2 | 2/2 |
| Bootstrap val: water bottle | 1/1 | 1/1 |

Own eval extra/unmatched boxes: baseline 8, candidate 2. Candidate produces two extra water-bottle boxes in `water_bottle_3.jpg`. No watch/charger misclassification was observed in the ten own-watch evaluation images.

Own eval median CPU latency: baseline 19.04 ms, candidate 18.30 ms (includes a cold first image in the median). Bootstrap warmed median CPU latency: baseline 24.80 ms, candidate 20.19 ms.

Bootstrap still fails on `charger_5.jpg` (miss), `toothbrush_6.jpg` (miss), and `toothpaste_8.jpg` (phone confusion). Bootstrap extra/unmatched boxes fall from 3 to 2. Full detections, boxes, scores and failures are in the JSON reports.

## Limits and integration status

This is a candidate, not a production checkpoint. All captures use the same room and physical objects, mostly held views. These are not independent backgrounds, glasses-camera tests or a representative accuracy benchmark. Evaluation images were not used for gradient training, but are included in validation for checkpoint selection, so scores are subject to selection bias. The shared bootstrap validation also served the earlier baseline training. Tabletop/adjacent-object rehearsals and live scene/touch/spoken-answer sign-off remain pending. No runtime model, shared default or detector source was changed.

## Train and evaluate the corrected dataset

From the repository root, in the pinned Python 3.11 environment:

```bash
python -m vision.extend_demo_dataset --base training_data/bootstrap --train-refs training_data/person1/train --val-refs training_data/person1/eval --output scratch/p1-dataset-cropped
python -m vision.train_demo_detector --data scratch/p1-dataset-cropped/data.yaml --weights vision/models/yolo11s.pt --project scratch/p1-runs --name candidate-cropped --epochs 45 --device mps
python -m vision.evaluate_demo_detector --weights scratch/p1-runs/candidate-cropped/weights/best.pt --refs training_data/person1/eval --output training_data/person1/results/candidate-cropped-person1-eval.json
```

Use fresh output names when repeating. The bootstrap comparison script accepts `--candidate`, `--baseline` and `--output-dir` to evaluate a new checkpoint separately. To reproduce the bootstrap comparison, download the published `demo-training-2026-11-14` model into `scratch/p1-comparison-baseline.pt`, then run `python training_data/person1/results/evaluate_bootstrap.py`. It evaluates both checkpoints with a warmup on the frozen bootstrap validation set.

Validation: full suite 207 passed, 1 skipped (live database), existing FastAPI/httpx warning. Root Ruff checks passed before adding this evaluation script; script lint checked separately.
