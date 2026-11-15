"""Run reproducible local candidate comparisons after training."""

import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import torch
import yaml
from ultralytics.utils import torch_utils

sys.path.insert(0, str(Path.cwd()))
from vision.evaluate_demo_detector import evaluate

torch_utils.NUM_THREADS = 4
torch.set_num_threads(4)
root = Path('training_data/person1/results/candidate-cropped')
root.mkdir(parents=True, exist_ok=True)
candidate = Path('scratch/p1-runs/candidate-cropped/weights/best.pt')
baseline = Path('scratch/comparison-baseline/demo-yolo11s.pt')
assert hashlib.sha256(baseline.read_bytes()).hexdigest() == 'c1e2dd03c6a1224e198dffe97e523a2894bccd37b1c053fe0716e94cde1d9f22'
for name, weights in [('baseline', baseline), ('candidate', candidate)]:
    for view, refs in [('cropped', Path('training_data/person1/eval')),
                       ('original-full-frame', Path('scratch/person1-original-before-watch-crops/eval'))]:
        output = root / f'{name}-{view}-eval.json'
        report = evaluate(weights, refs, output)
        report.update(weights_sha256=hashlib.sha256(weights.read_bytes()).hexdigest(),
                      evaluation_view=view, torch_threads=4, device='cpu', imgsz=416,
                      warmup_excluded=False,
                      limitation='Same physical objects and capture sessions; cropped validation participates in checkpoint selection, so results are selection-biased.')
        if view == 'original-full-frame':
            report['additional_unmatched_boxes_incompletely_labelled'] = report.pop('false_positive_boxes')
            report['annotation_limitation'] = 'Original watch photos contain unlabelled bottles; additional boxes are not a reliable false-positive metric. Correct target matches remain scored.'
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(name, view, report['per_class'], flush=True)
subprocess.run([sys.executable, 'training_data/person1/results/evaluate_bootstrap.py',
                '--baseline', str(baseline), '--candidate', str(candidate), '--output-dir', str(root)], check=True)
with Path('scratch/p1-runs/candidate-cropped/results.csv').open(encoding='utf-8') as source:
    training_rows = list(csv.DictReader(source))
metadata = {
    'status': 'trained_and_saved_image_evaluated_live_checks_pending',
    'python': sys.version, 'platform': platform.platform(),
    'torch': torch.__version__, 'device': 'cpu', 'torch_threads': 4,
    'epochs_completed': int(training_rows[-1]['epoch']),
    'elapsed_training_seconds': float(training_rows[-1]['time']),
    'git_base_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'local_changes': 'Corrected watch crops and annotations; provenance in ../watch-crop-manifest.json',
    'dataset_manifest_sha256': hashlib.sha256(Path('scratch/p1-dataset-cropped/split.json').read_bytes()).hexdigest(),
    'crop_manifest_sha256': hashlib.sha256(Path('training_data/person1/results/watch-crop-manifest.json').read_bytes()).hexdigest(),
    'weights': str(candidate), 'weights_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
    'initial_weights_sha256': hashlib.sha256(Path('vision/models/yolo11s.pt').read_bytes()).hexdigest(),
    'training_arguments': yaml.safe_load(Path('scratch/p1-runs/candidate-cropped/args.yaml').read_text()),
    'limits': ['Validation participates in checkpoint selection.', 'Watch crops change apparent scale; full-frame target accuracy reported separately.', 'No live glasses-camera, touch, speech, or adjacent-object sign-off.'],
}
(root / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
(root / 'requirements-resolved.txt').write_text(subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True), encoding='utf-8')
shutil.copy2('scratch/p1-runs/candidate-cropped/results.csv', root / 'training.csv')
