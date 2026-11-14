# Demo detection: four-person training handoff

**Status: not demo-ready.** Toothpaste works in the latest live test. The watch
is frequently detected as a charger, and the actual charger is missed in some
views. Headphones and keys remain sensitive to scale, pose and partial framing.
Passing Python tests does not establish recognition accuracy.

Person 2 explicitly authorized training, integration and publishing this work
to `main` on 2026-11-14. The assignment below authorizes each person to collect,
label and train their two items in their own data directory. Keep production
code ownership, message contracts, hazard priority and shared defaults intact.

## Two items each

| Member | Items | Immediate focus | Data directory |
|---|---|---|---|
| Person 1 | **watch, water bottle** | Watch versus coiled charger; face/back/band views; bottle shape and occlusion. Own the final eight-class integration. | `training_data/person1/` |
| Person 2 | **charger, toothpaste** | The actual charger in the demo, with its cable coiled; tabletop and held views; preserve toothpaste accuracy. | `training_data/person2/` |
| Person 3 | **keys, phone** | Small keys and fob on the table versus phone; close/far views; screen on/off. | `training_data/person3/` |
| Person 4 | **headphones, toothbrush** | Complete and partial headsets at demo distance; thin toothbrush at different orientations; dashboard and spoken-answer checks. | `training_data/person4/` |

Each person actively collects data **and runs a candidate training job**. Use the
complete shared eight-class dataset plus your additions. Do not train a
two-class replacement and install it globally: that would remove the other six
classes. Do not try to merge four `.pt` files. Merge reviewed datasets, then
Person 1 trains/selects the final full eight-class detector.

**Every member must use their own webcam for imaging.** A laptop's built-in
webcam is acceptable; nobody has to borrow Person 2's Logitech or wait for the
glasses camera. The shared bootstrap is a starting point, not your contribution.
Capture your assigned items yourself in both sessions. Camera/lighting variation
is intentional; the final combined model must also be tested on the glasses camera.

## What is already included

- `training_data/bootstrap/`: **71 training images, 10 validation images**, YOLO
  labels, portable `data.yaml`, and a SHA-256 split manifest. Training includes
  54 original references, 14 new manually labelled tabletop frames and 3
  background examples. Validation has 13 labelled objects across 10 images.
- `vision/train_demo_detector.py`: dataset preparation and fine-tuning.
- `vision/capture_demo_refs.py`: now supports per-person folders and item lists.
- `vision/extend_demo_dataset.py`: append your sessions without altering the
  frozen baseline or leaking identical images across train/validation.
- `vision/evaluate_demo_detector.py`: per-item box/class results and false
  positive counts, with no Grok calls or camera access.
- The local experimental model was initialized from pretrained YOLO11s and
  fine-tuned on our data. This is **not training from scratch**.

The selected checkpoint detected **3/5** target objects in two saved tabletop
validation frames, versus **0/5** for the old visual prompts. It still failed
the live watch/charger test. Treat it as a baseline to beat, not a finished fix.
An extra incorrect box can also appear. These few related photos are not an
independent accuracy benchmark.

## Install the same baseline

Use **Python 3.11** in a fresh virtual environment. On Windows:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe scripts/install_dependencies.py
.venv/Scripts/python.exe scripts/setup_models.py
```

On macOS/Linux:

```bash
python3.11 -m venv .venv
.venv/bin/python scripts/install_dependencies.py
.venv/bin/python scripts/setup_models.py
```

After activating that environment, the remaining commands use `python`.
`requirements.txt` pins the tested application/training stack.
`requirements-vision.txt` pins Ultralytics, installed separately with
`--no-deps`: MediaPipe needs contrib OpenCV, and installing Ultralytics normally
would also pull plain OpenCV. **Only `opencv-contrib-python` should provide
`cv2`.** Do not install plain/headless OpenCV alongside it. A metadata-only
`opencv-python` warning from `pip check` is expected with this arrangement.
The Windows CPU environment is the tested baseline; macOS uses its native
PyTorch wheels. Microphone input now on `main` uses browser speech recognition,
not Python SpeechRecognition/PyAudio.

Setup validation: the installer and vision imports succeeded in a fresh Windows
venv. Windows Application Control blocked the newly downloaded Postgres binary
in that venv, so its complete database test collection could not run; the existing
working venv is used for the full suite. If your OS blocks a package, follow its
normal trust/admin process; do not disable security controls to run training.

Model weights are never committed to Git. The current failed/experimental
checkpoint is distributed as a **prerelease** for comparison:

```bash
gh release download demo-training-2026-11-14 --repo richardlancs/Empyrean --pattern demo-yolo11s.pt --dir vision/models
```

If that file already exists, keep/rename your current candidate before choosing
another; do not silently overwrite it. The release includes a checksum and
status manifest. Git pull alone does not install a trained model. Pretrained
YOLOE prompt files are only needed for the old fallback, not the trained path.

## Capture and label your pair

Stop your own camera app first. Use **your own webcam** and physical examples of
your assigned items, at realistic demo distances and angles. Include a short
note if your item differs from the final demo's item. For example, Person 1:

```bash
python -m vision.capture_demo_refs --camera-index 0 --refs training_data/person1/train --objects watch "water bottle"
python -m vision.capture_demo_refs --camera-index 0 --refs training_data/person1/eval --objects watch "water bottle"
```

Other pairs: Person 2 `--objects charger toothpaste`; Person 3
`--objects keys phone`; Person 4 `--objects headphones toothbrush`.
Index 0 is usually the built-in webcam. If the preview is wrong, quit and try
your actual camera index. The explicit flag overrides any laptop-specific
`CAMERA_INDEX` in `.env`; do not copy Person 2's index 1 blindly. Each session
records `capture_info.json` with its source, index, resolution and platform.
SPACE freezes the image, drag a tight box, ENTER accepts it; N moves to the
next item, Q finishes. Images and `refs.json` stay in your own folder.

Aim initially for **30 useful training images and 10 separate evaluation
images per item**, covering multiple capture sequences. Avoid copying adjacent
video frames as if they were independent examples. Capture tabletop, held,
touching/partly covered, rotated, near and farther views. Small items must be
represented at their actual demo size, not only as giant close-ups.

Capture **one visible demo item per training/evaluation photo** with this tool:
it writes one box per photo. Unlabelled neighbouring demo items would become
bad negative examples. Test adjacent items separately in the live app; use a
multi-object labelling workflow before adding such photos to training.

Use consistent boxes: tube + cap; complete headset; whole key bunch + fob;
watch face + visible band; bottle body + cap/handle; complete phone; complete
toothbrush. For the charger, keep the adapter and cable coiled together and
box that assembly, matching the current baseline. Do not alternate between an
adapter-only box and a huge box spanning a loose cable across the table.
Any change in that definition needs the old labels reviewed too.

The `eval` session must have different poses/positions from `train`. Never add
failed evaluation images back into training and still report them as holdouts.
Check boxes by eye before training. Inspect watch/charger examples side by
side, since this is a measured confusion, not a threshold problem.

## Train your candidate without dropping other items

Example for Person 1; replace `person1`/`p1` for your directory/run name:

```bash
python -m vision.extend_demo_dataset --base training_data/bootstrap --train-refs training_data/person1/train --val-refs training_data/person1/eval --output scratch/p1-dataset-v1
python -m vision.train_demo_detector --data scratch/p1-dataset-v1/data.yaml --weights vision/models/yolo11s.pt --project scratch/p1-runs --name candidate-v1 --epochs 45
python -m vision.evaluate_demo_detector --weights scratch/p1-runs/candidate-v1/weights/best.pt --refs training_data/person1/eval --output training_data/person1/results/candidate-v1.json
```

Use a new output directory/run name for each experiment. CPU is the default;
`--device mps` or `--device 0` is available if your existing environment supports
that accelerator. Record the device, data, weights, arguments and elapsed time.
Changing `--epochs` is allowed; do not blindly lower the app's confidence to
make more boxes appear. Checkpoint selection must consider class errors and
false boxes, not only aggregate mAP.

The canonical class IDs are fixed in `DEMO_OBJECTS`:

| ID | Class | ID | Class |
|---|---|---|---|
| 0 | water bottle | 4 | phone |
| 1 | toothbrush | 5 | headphones |
| 2 | toothpaste | 6 | keys |
| 3 | charger | 7 | watch |

The extension tool preserves the frozen baseline and the complete class map.
The original preparation tool holds out only one reference per class; that
alone is too small to certify quality. Use the separate sessions above.

## Share results and integrate

Commit your own JPEGs, `refs.json`, `capture_info.json`, evaluation JSON and a short result note on
your branch, then open a PR. Include every failure, the inference latency,
watch/charger or keys/phone confusions, and performance on the other six
classes. Do not commit `.env`, weights, scratch runs or long videos. Attach
candidate weights separately or pass them to Person 1 with SHA-256 and their
training metadata.

Person 1 merges the four reviewed data contributions into one dataset,
retains all eight classes and frozen holdouts, trains/selects one candidate,
and installs it as `vision/models/demo-yolo11s.pt` only after comparison.
The loader validates the eight-class head. COCO still supplies vehicles and
its known demo classes; object deduplication must never suppress vehicles.

Each owner must then sign off on their two items **in the live app**, alone
and next to another item: stable boxes, correct name, no wrong neighbouring
name, touch/hold/release/retouch state, and spoken answers. Current `main`
speaks object names in response to questions; use the question panel or
supported Chrome microphone, not automatic touch speech as the audio test.
Record detection class separately from Grok name: our trace sometimes calls
the watch `charger` first and Grok later corrects the name to `watch`.

Before final integration run `python -m pytest -q` and
`python -m app --fake vision audio`. Measure camera latency as well: the
training-session live trace was near 5 fps but sometimes exceeded the 150 ms
target. No one should mark an item complete just because a `.pt` file exists.
