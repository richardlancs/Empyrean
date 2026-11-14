"""Dataset checks that prevent label-coordinate errors and train/validation leakage."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from vision.build_demo_weights import DEMO_OBJECTS
from vision.train_demo_detector import prepare_dataset


def references(path: Path) -> None:
    """Write two distinct boxed images of every demo class."""
    path.mkdir()
    refs = []
    for class_id, label in enumerate(DEMO_OBJECTS):
        for number in range(2):
            name = f"{class_id}-{number}.jpg"
            image = np.full((100, 200, 3), class_id * 20 + number, dtype=np.uint8)
            cv2.imwrite(str(path / name), image)
            refs.append({"file": name, "label": label, "box": [20, 10, 180, 90]})
    (path / "refs.json").write_text(json.dumps(refs), encoding="utf-8")


def test_each_class_has_disjoint_training_and_validation_images(tmp_path: Path) -> None:
    """Withhold an image per class and express its box in normalized YOLO coordinates."""
    refs, output = tmp_path / "refs", tmp_path / "dataset"
    references(refs)
    assert prepare_dataset(refs, output).is_file()
    manifest = json.loads((output / "split.json").read_text())
    train = [row for row in manifest if row["split"] == "train"]
    val = [row for row in manifest if row["split"] == "val"]
    assert {row["label"] for row in train} == set(DEMO_OBJECTS)
    assert {row["label"] for row in val} == set(DEMO_OBJECTS)
    assert len(train) == len(val) == len(DEMO_OBJECTS)
    assert not ({row["file"] for row in train} & {row["file"] for row in val})
    assert not ({row["sha256"] for row in train} & {row["sha256"] for row in val})
    box = (output / "labels" / "val" / "0-1.txt").read_text().split()
    assert int(box[0]) == 0
    assert [float(value) for value in box[1:]] == pytest.approx([0.5, 0.5, 0.8, 0.8])


def test_invalid_annotation_is_rejected_before_dataset_is_written(tmp_path: Path) -> None:
    """A box extending beyond its actual photo must not silently become a bad label."""
    refs, output = tmp_path / "refs", tmp_path / "dataset"
    references(refs)
    manifest = json.loads((refs / "refs.json").read_text())
    manifest[-1]["box"] = [20, 10, 250, 90]
    (refs / "refs.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="outside image bounds"):
        prepare_dataset(refs, output)
    assert not output.exists()


def test_preparation_cannot_mix_old_and_new_dataset_splits(tmp_path: Path) -> None:
    """Reusing a populated directory must not leave old training images in a new split."""
    refs, output = tmp_path / "refs", tmp_path / "dataset"
    references(refs)
    prepare_dataset(refs, output)
    with pytest.raises(ValueError, match="not empty"):
        prepare_dataset(refs, output)


def test_duplicate_photo_under_another_name_cannot_leak_into_validation(tmp_path: Path) -> None:
    """Filename separation alone is insufficient when two files contain the same photo."""
    refs, output = tmp_path / "refs", tmp_path / "dataset"
    references(refs)
    (refs / "0-1.jpg").write_bytes((refs / "0-0.jpg").read_bytes())
    with pytest.raises(ValueError, match="Duplicate image content"):
        prepare_dataset(refs, output)
    assert not output.exists()


def test_team_extension_keeps_frozen_validation_and_all_eight_classes(tmp_path: Path) -> None:
    """Adding one person's watch photos cannot drop other classes or overwrite holdouts."""
    from vision.extend_demo_dataset import extend_dataset

    refs, base = tmp_path / "refs", tmp_path / "base"
    references(refs)
    prepare_dataset(refs, base)
    original = (base / "split.json").read_text()
    folders = []
    for name, shade in (("new-train", 200), ("new-val", 220)):
        folder = tmp_path / name
        folder.mkdir()
        cv2.imwrite(str(folder / "watch.jpg"), np.full((100, 200, 3), shade, dtype=np.uint8))
        (folder / "refs.json").write_text(json.dumps([
            {"file": "watch.jpg", "label": "watch", "box": [20, 10, 180, 90]},
        ]))
        folders.append(folder)
    output = tmp_path / "candidate"
    assert extend_dataset(base, output, [folders[0]], [folders[1]]).exists()
    assert (base / "split.json").read_text() == original
    assert len(list((output / "images" / "train").glob("*.jpg"))) == 9
    assert len(list((output / "images" / "val").glob("*.jpg"))) == 9
    assert (output / "labels" / "train" / "extra-0-watch.txt").read_text().startswith("7 ")


def test_team_extension_rejects_training_on_an_existing_holdout(tmp_path: Path) -> None:
    """A renamed baseline holdout must not become somebody's new training example."""
    from vision.extend_demo_dataset import extend_dataset

    refs, base = tmp_path / "refs", tmp_path / "base"
    references(refs)
    prepare_dataset(refs, base)
    extra = tmp_path / "extra"
    extra.mkdir()
    (extra / "renamed.jpg").write_bytes((base / "images" / "val" / "0-1.jpg").read_bytes())
    (extra / "refs.json").write_text(json.dumps([
        {"file": "renamed.jpg", "label": "water bottle", "box": [20, 10, 180, 90]},
    ]))
    output = tmp_path / "candidate"
    with pytest.raises(ValueError, match="crosses"):
        extend_dataset(base, output, [extra], [])
    assert not output.exists()
