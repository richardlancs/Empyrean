"""Smoke test: contracts/ and config/ match SPEC.md sections 5 and 9."""

import dataclasses
import re
import typing
from pathlib import Path

import config
import contracts
from contracts import (
    FrameResult,
    Hand,
    HazardEvent,
    LastSeenQuery,
    ModeChange,
    NameRequest,
    NameResult,
    SceneObject,
    SceneQuestion,
    SceneSnapshot,
    SpeakRequest,
    TouchEvent,
    TrackedObject,
)

SPEC = Path(__file__).resolve().parents[1] / "SPEC.md"
BOX = (100.0, 80.0, 220.0, 300.0)
TS = 1_763_100_000.0


def _section(number: int) -> str:
    """Return the text of one top-level SPEC.md section."""
    text = SPEC.read_text(encoding="utf-8")
    match = re.search(rf"^## {number}\. .*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert match, f"SPEC.md section {number} not found"
    return match.group(0)


def _spec_messages() -> dict[str, list[str]]:
    """Map each section 5 message name to its field names, in table order."""
    out: dict[str, list[str]] = {}
    for block in re.split(r"^### ", _section(5), flags=re.MULTILINE)[1:]:
        name = re.match(r"`(\w+)`", block).group(1)
        out[name] = re.findall(r"^\| `(\w+)` \|", block, re.MULTILINE)
    return out


def _spec_thresholds() -> dict[str, int | float]:
    """Map each section 9 threshold name to its value, typed as written."""
    out: dict[str, int | float] = {}
    for names, values in re.findall(
        r"^\| (`[A-Z_]+`.*?) \| ([\d., ]+) \|", _section(9), re.MULTILINE
    ):
        for name, value in zip(
            re.findall(r"`(\w+)`", names), values.split(","), strict=True
        ):
            value = value.strip()
            out[name] = float(value) if "." in value else int(value)
    return out


def _all_messages() -> list[object]:
    """Build one valid instance of every message type."""
    obj = TrackedObject(object_id=3, class_label="bottle", confidence=0.87, box=BOX)
    hand = Hand(
        side="right", thumb_tip=(150.0, 200.0), index_tip=(160.0, 190.0), box=BOX
    )
    scene_obj = SceneObject(
        object_id=3,
        class_label="bottle",
        name="Heinz ketchup",
        state="touching",
        box=BOX,
        last_seen_ts=TS,
    )
    return [
        obj,
        hand,
        FrameResult(ts=TS, frame_id=0, image=None, objects=[obj], hands=[hand]),
        scene_obj,
        SceneSnapshot(ts=TS, frame_id=0, objects=[scene_obj]),
        NameRequest(
            ts=TS, object_id=3, class_label="bottle", crop_jpeg=b"\xff\xd8\xff\xd9"
        ),
        NameResult(ts=TS, object_id=3, name="Heinz ketchup", ok=True),
        TouchEvent(
            ts=TS,
            object_id=3,
            class_label="bottle",
            name="Heinz ketchup",
            kind="touch",
            box=BOX,
            neighbours=["cup"],
        ),
        HazardEvent(ts=TS, type="stairs_down", source="grok", confidence=0.8),
        LastSeenQuery(ts=TS, text="keys"),
        SceneQuestion(ts=TS, text="Where are my keys?"),
        ModeChange(ts=TS, mode="demo"),
        SpeakRequest(ts=TS, text="Heinz ketchup", priority="normal", source="audio"),
    ]


def test_every_message_builds() -> None:
    """One instance of every section 5 message can be built with valid values."""
    built = {type(m).__name__ for m in _all_messages()}
    assert built == set(_spec_messages()) | {"TrackedObject", "Hand", "SceneObject"}


def test_message_fields_match_spec() -> None:
    """Top-level message fields have the exact names and order from section 5."""
    for name, fields in _spec_messages().items():
        cls = getattr(contracts, name)
        assert [f.name for f in dataclasses.fields(cls)] == fields, name


def test_entry_fields_match_spec() -> None:
    """List entries inside messages have the fields section 5 lists inline."""
    expected = {
        TrackedObject: ["object_id", "class_label", "confidence", "box"],
        Hand: ["side", "thumb_tip", "index_tip", "box"],
        SceneObject: [
            "object_id",
            "class_label",
            "name",
            "state",
            "box",
            "last_seen_ts",
        ],
    }
    for cls, fields in expected.items():
        assert [f.name for f in dataclasses.fields(cls)] == fields, cls.__name__


def test_fixed_values_match_spec() -> None:
    """Every Literal field allows exactly the values section 5 lists."""
    expected = {
        (Hand, "side"): {"left", "right", "unknown"},
        (SceneObject, "state"): {"new", "idle", "touching", "held", "lost"},
        (TouchEvent, "kind"): {"touch", "release"},
        (HazardEvent, "type"): {"stairs_down", "drop_off", "vehicle", "obstacle"},
        (HazardEvent, "source"): {"yolo", "grok"},
        (SpeakRequest, "priority"): {"normal"},
        (ModeChange, "mode"): {"actual", "demo"},
    }
    for (cls, field_name), values in expected.items():
        hint = typing.get_type_hints(cls)[field_name]
        assert set(typing.get_args(hint)) == values, f"{cls.__name__}.{field_name}"


def test_list_fields_default_to_empty() -> None:
    """List fields can be left out and start empty, not shared between instances."""
    a = FrameResult(ts=TS, frame_id=0, image=None)
    b = FrameResult(ts=TS, frame_id=1, image=None)
    a.objects.append(_all_messages()[0])
    assert b.objects == [] and b.hands == []


def test_config_matches_spec_section_9() -> None:
    """config has every section 9 name with the spec's value and type, and nothing else."""
    spec = _spec_thresholds()
    assert len(spec) == 30
    assert set(config.__all__) == set(spec)
    for name, value in spec.items():
        actual = getattr(config, name)
        assert actual == value and type(actual) is type(value), name
