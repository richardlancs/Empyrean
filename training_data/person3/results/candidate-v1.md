# Person 3 candidate-v1: keys and phone

**Status: training photos and a first candidate only. The separate eval
session has not been captured yet, so there is no true holdout score.**

## Data

- `train/`: 60 photos from the operator's own MacBook webcam (camera 0), in two
  sessions. `capture_info-session1.json` is the first session and
  `capture_info.json` is the second.
  - Session 1: keys 1-15 and phone 1-20, held up in the hand against the room.
  - Session 2: keys 16-30 and phone 21-30, on a table and on a pillow, partly
    covered by a hand, phone face up and face down.
- One item per photo. Every box was checked by eye. The `keys_16.jpg` box was
  redrawn to cover the whole key bunch, because the captured box covered only
  the fob. The old box was `[297, 257.5, 351.5, 295.5]`.
- Gap: few keys at true demo distance on a table. Most tabletop key shots are
  close-ups.

## Training run

- Dataset: frozen `training_data/bootstrap` plus 50 Person 3 photos, built with
  `vision.extend_demo_dataset`. 121 training images cover all eight classes.
- Temporary check set: no eval session existed, so 10 training photos were held
  back for validation (`keys_5`, `keys_10`, `keys_20`, `keys_25`, `keys_30`,
  `phone_5`, `phone_10`, `phone_15`, `phone_25`, `phone_30`), plus the
  bootstrap's 10 validation images. These photos come from the same sessions as
  the training set, so the scores below overstate real accuracy.
- Command: `python -m vision.train_demo_detector --data scratch/p3-dataset-v1/data.yaml --weights vision/models/yolo11s.pt --project scratch/p3-runs --name candidate-v1 --epochs 45 --device mps`
- Tool defaults: batch 4, imgsz 416, freeze 10, lr0 0.001, mosaic 0.5, patience 12, seed 42.
- Device: Apple M2 GPU (MPS), Ultralytics 8.4.212, torch 2.15.0. Took 7 min 43 s.
  Stopped early at epoch 34, and the best checkpoint is epoch 22.
- Weights are not committed. `best.pt` SHA-256:
  `ecee53731361899127266beb5de59461e14bb52c378d0bf8b983ac8cf8b32cac`.

## Results

`vision.evaluate_demo_detector` on the 10 held-back photos (confidence 0.25, IoU 0.5):

| | Baseline `demo-yolo11s.pt` | candidate-v1 |
|---|---|---|
| keys | 0/5 | 4/5 |
| phone | 0/5 | 5/5 |
| false boxes | 1 | 0 |

The one miss is `keys_5.jpg`, keys held near the face, with no detection.
There was no keys/phone confusion. Median inference was 43 ms per image on the
M2 GPU, not on the demo laptop. JSON files: `candidate-v1-holdout.json` and
`baseline-holdout.json`.

mAP50 on all 20 validation images, per class (each other class has only 1 or 2 images):

| Class | Baseline | candidate-v1 |
|---|---|---|
| water bottle | 0.995 | 0.995 |
| toothbrush | 0.015 | 0.000 |
| toothpaste | 0.606 | 0.828 |
| charger | 0.495 | 0.495 (recall 0/2 vs 1/2) |
| phone | 0.254 | 0.972 |
| headphones | 0.515 | 0.995 |
| keys | 0.327 | 0.953 |
| watch | 0.995 | 0.828 |
| all | 0.525 | 0.758 |

The charger and watch dips rest on two images each, so they may be noise.
Recheck them on the merged dataset.

## Still to do

1. Eval session in `training_data/person3/eval/`: about 10 photos per item in
   new positions, including keys far away on a table. Then rerun
   `vision.evaluate_demo_detector` and add the report here.
2. Live sign-off on keys and phone once Person 1 installs the merged model.
