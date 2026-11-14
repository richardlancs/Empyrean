# Frozen bootstrap dataset

71 training images (82 boxes, including three background images with no boxes)
and 10 validation images (13 boxes). Images are 640 x 360. `split.json` records
content hashes and canonical classes; there is no identical image across splits.
Keep this baseline unchanged while the four people collect separate sessions.

The 62 original reference images came from Person 2's Logitech capture. New
training contains 14 manually reviewed tabletop frames from two later camera
sequences. The first two tabletop snapshots were kept for validation only.
Some retained frames show partial objects; ambiguous/blurred frames were excluded.

`data.yaml` has no machine-specific path. The training CLI resolves this file
absolutely before handing it to Ultralytics. Start with:

```bash
python -m vision.train_demo_detector --data training_data/bootstrap/data.yaml
```

See [demotraining.md](../../demotraining.md) for ownership, extensions, current
failures and model distribution. This baseline is insufficient to certify the demo.
