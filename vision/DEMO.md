# Local demo detector

The Person 2 human authorized fine-tuning and changes in `vision/` on 2026-11-14.
This is an explicit exception to the pretrained-only rule. No training runs in
the camera process, and no model is downloaded there.

The dashboard's Demo mode toggle selects:

- **Off:** the existing COCO YOLO11s detector.
- **On, with `vision/models/demo-yolo11s.pt`:** the local fine-tuned eight-class
  detector, plus COCO vehicles and its known bottle, phone and toothbrush classes.
  Overlapping boxes are deduplicated. Vehicle boxes always survive this merge.
- **On, without trained weights:** the previous YOLOE visual-prompt detector, if
  its weights and prompts exist. The loader logs which detector is actually ready.

Each published object ID is scoped to its detector and class. A raw tracker ID
changing from bottle to laptop gets a new public ID, preventing reuse of the
previous object's cached name. The camera uses DirectShow on Windows to avoid
the default backend's observed hang during webcam reopening.

## Prepare and train

Use the existing Python 3.11 environment. Training needs the human's approval.
The setup tool rejects invalid boxes, duplicate photos crossing the validation
split, and an already populated dataset directory.

```powershell
python -m vision.train_demo_detector --prepare-only
python -m vision.train_demo_detector --data scratch/demo_dataset/data.yaml
```

The original 62 reference photos produce 54 training photos and 8 validation
photos. The local tabletop refinement used 71 training photos (54 originals,
14 new manually labelled frames, 3 background examples) and 10 validation photos
containing 13 labelled objects. The first two tabletop snapshots remain outside
training. These are small, related camera samples, not an independent accuracy
benchmark.

The final local refinement can be repeated with its local dataset and parent
checkpoint:

```powershell
python -m vision.train_demo_detector --data scratch/demo-training/stage3_dataset/data.yaml --weights scratch/demo-training/yolo11s-demo-v2/weights/best.pt --epochs 25 --patience 8 --freeze 10 --lr 0.0005 --mosaic 0 --freeze-bn
```

Validate candidates on every demo object, on background objects, and on the real
camera before copying one to `vision/models/demo-yolo11s.pt`. The selected local
checkpoint and its SHA-256 are recorded in `scratch/demo-training/install.json`.
Weights and captured data are git-ignored and must be copied separately to the
demo laptop; a Git pull alone does not deliver them.

## Rehearse

Run `python -m app --record-crops`, open localhost:8000 and enable Demo mode.
Keep each item fully in the frame and check its box before touching it. Check
touch, a five-second hold, release and retouch. Also check two adjacent items.
The current candidate improves several tabletop detections but still misses
some small, partial or changed-pose views, especially headphones and keys.
Training completion does not mean the demo is ready.

Run `python -m pytest -q` for regression tests. Synthetic tests verify that
vehicle-growth alarms still work in trained demo mode; they do not establish
real-world hazard detection accuracy.
