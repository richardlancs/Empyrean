# Local demo detector

The Person 2 human authorized fine-tuning and changes in `vision/` on 2026-11-14.
This is an explicit exception to the pretrained-only rule. No training runs in
the camera process, and no model is downloaded there.

The dashboard's **Regular | Demo** control (beside the camera heading) selects:

- **Regular:** the existing COCO YOLO11s detector (`vision/models/yolo11s.pt`).
- **Demo, with `vision/models/demo-yolo11s.pt`:** the local fine-tuned eight-class
  detector, plus COCO vehicles and its known bottle, phone and toothbrush classes.
  Overlapping boxes are deduplicated. Vehicle boxes always survive this merge, so
  the hazard path keeps seeing cars, buses, trucks, motorcycles and bicycles.
  The page shows a **Demo-trained model** badge and the checkpoint's recorded
  status (today: "experimental; NOT demo-ready").
- **Demo, without trained weights:** the previous YOLOE visual-prompt detector, if
  its weights and prompts exist. The page labels it **Demo fallback, not trained**;
  it is never called the trained model.
- **Demo, with nothing installed:** the switch fails, the page says why, and
  Regular keeps running.

How a switch works: the page asks (`POST /api/mode`), vision loads and checks the
demo detector on a background thread while Regular keeps detecting, and only when
vision reports `DetectorStatus` with the new mode does the page show it as active.
A second request while one is in progress is refused (HTTP 409). Nothing is
trained or downloaded when the control is used. Switching back to Regular is
immediate. `--fake vision` simulates the switch (`FAKE_DEMO_DETECTOR=ok|missing|invalid`)
and labels it fake: no model runs there.

Before a checkpoint is used, vision checks that it:

1. is at least 10 seconds old and does not change while it is hashed (a file a
   training run is still writing is refused, not loaded);
2. matches the SHA-256 and the eight class names in `vision/models/training-status.json`
   (the release's manifest) or `scratch/demo-training/install.json` (a local
   install record), when either is present; with neither it is still loaded and
   checked, and its status reads "no status manifest";
3. loads as a detection model whose class names are exactly the eight demo
   objects (a two-class or COCO head is refused), and runs one blank frame.

**System details** on the page shows the detector in use and the checkpoint's
file, size, SHA-256 prefix, install time and recorded status.

## Install or replace the demo checkpoint

Do this with the app running or stopped; nothing reloads mid-copy.

```bash
mkdir -p scratch/demo-download
gh release download demo-training-2026-11-14 --repo richardlancs/Empyrean \
  --pattern demo-yolo11s.pt --pattern training-status.json --pattern SHA256SUMS.txt \
  --dir scratch/demo-download
(cd scratch/demo-download && shasum -a 256 -c SHA256SUMS.txt)   # Windows: certutil -hashfile demo-yolo11s.pt SHA256
cp scratch/demo-download/training-status.json vision/models/training-status.json
cp scratch/demo-download/demo-yolo11s.pt vision/models/demo-yolo11s.pt.partial
mv vision/models/demo-yolo11s.pt.partial vision/models/demo-yolo11s.pt
```

If `vision/models/demo-yolo11s.pt` already exists, rename it first (for example
`demo-yolo11s.previous.pt`) rather than overwriting it silently. Copy to a
temporary name and then rename, so vision never sees half a file. For a locally
trained candidate, copy it the same way and record its SHA-256 and classes in
`scratch/demo-training/install.json`.

To start using a newer file while the app runs: wait at least 10 seconds after
the copy, choose **Regular**, then **Demo** again. Vision re-checks the file
whenever its size or modification time changed; an unchanged file is reused
without reloading. Weights, manifests and install records are never committed.

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

Run `python -m app --record-crops`, open localhost:8000 and choose **Demo** beside
the camera heading. Wait for the Demo-trained model badge before testing.
Keep each item fully in the frame and check its box before touching it. Check
touch, a five-second hold, release and retouch. Also check two adjacent items.
The current candidate improves several tabletop detections but still misses
some small, partial or changed-pose views, especially headphones and keys.
Training completion does not mean the demo is ready.

Run `python -m pytest -q` for regression tests. Synthetic tests verify that
vehicle-growth alarms still work in trained demo mode; they do not establish
real-world hazard detection accuracy.
