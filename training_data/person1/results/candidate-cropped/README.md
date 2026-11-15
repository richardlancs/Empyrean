# Corrected watch-crop candidate

Trained locally on Windows / CPU using Python 3.11.9, PyTorch 2.14.0+cpu, Ultralytics 8.4.212 and the team-pinned dependencies. All 45 epochs completed in 1247.58 seconds. Initialization is the same pretrained YOLO11s checkpoint as candidate-v1. Dataset: 131 train images; 30 validation images / 33 boxes; all eight classes retained. Selected best validation checkpoint remains local at `scratch/p1-runs/candidate-cropped/weights/best.pt`.

Correct target = correct class and IoU >= 0.5, confidence 0.25, image size 416. CPU inference uses four threads.

| Evaluation | Published baseline | Corrected candidate |
|---|---:|---:|
| Cropped watch | 0/10 | 10/10 |
| Original full-frame watch | 0/10 | 3/10 |
| Bottle (unchanged photos) | 4/10 | 10/10 |
| Frozen bootstrap targets | 9/13 | 11/13 |

These are saved-image checks on related captures. Cropped validation participates in checkpoint selection. Original full-frame checks reuse the source photos for those crops and are not an independent test. Tight crops change apparent scale: the crop score does not establish full-frame watch recognition. The historical candidate-v1 report achieved 10/10 full-frame watches, so this candidate is a regression against that historical watch result; its weights are unavailable locally for a same-environment rerun. The published baseline is a different checkpoint and was rerun locally.

Original watch photos contain unlabelled background bottles, so their additional detections are reported as unmatched boxes rather than reliable false positives. Full-frame target accuracy remains scored. Bootstrap additional boxes: baseline 3, candidate 3. Remaining bootstrap failures: charger_5, toothbrush_6, toothpaste_8. No per-class bootstrap target-count drops. Live camera, adjacent objects, touch and spoken-answer checks are pending. This candidate has not been installed in the app.

Reproduce training in the pinned Python 3.11 environment (use a fresh run name if repeating):

```powershell
python -m vision.train_demo_detector --data scratch/p1-dataset-cropped/data.yaml --weights vision/models/yolo11s.pt --project scratch/p1-runs --name candidate-cropped --epochs 45 --device cpu
python training_data/person1/results/evaluate_cropped_candidate.py
```

The evaluation script expects the published baseline at `scratch/comparison-baseline/demo-yolo11s.pt` and original sessions in `scratch/person1-original-before-watch-crops/`. Data preparation/crop provenance is in the parent README and `watch-crop-manifest.json`. `metadata.json`, `training.csv`, `requirements-resolved.txt`, per-image reports and `weights.sha256` record this run. Own-photo latency includes cold startup; bootstrap median is warmed. Model-call latency is not end-to-end camera latency.

Verification: 179 tests passed in the available suite; two additional tests fail importing storage because Windows Application Control blocks the Postgres DLL. The full suite also stops at collection of two storage-dependent modules for the same reason. Dataset validation and lint pass. No security policy was changed.
