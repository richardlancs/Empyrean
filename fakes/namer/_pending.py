# TEMPORARY until contracts/ and config/ land.
# Mirrors SPEC.md section 5 (messages) and section 9 (thresholds) exactly.
# Do not edit by hand: identical copies live in namer/, storage/, fakes/namer/, fakes/storage/.
# When contracts/ and config/ exist, delete every copy and import from those instead.
"""Temporary stand-in for contracts/ and config/ (SPEC.md sections 5 and 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 in 640 x 360 pixels
Point = tuple[float, float]  # x, y in 640 x 360 pixels

# ---- SPEC.md section 5: messages -------------------------------------------


@dataclass
class TrackedObject:
    """One entry of FrameResult.objects."""

    object_id: int
    class_label: str
    confidence: float
    box: Box


@dataclass
class Hand:
    """One entry of FrameResult.hands."""

    side: Literal["left", "right", "unknown"]
    thumb_tip: Point
    index_tip: Point
    box: Box


@dataclass
class FrameResult:
    """Vision to everyone, once per processed frame."""

    ts: float
    frame_id: int
    image: Any  # 640 x 360 BGR image
    objects: list[TrackedObject] = field(default_factory=list)
    hands: list[Hand] = field(default_factory=list)


@dataclass
class SceneObject:
    """One entry of SceneSnapshot.objects."""

    object_id: int
    class_label: str
    name: str
    state: Literal["new", "idle", "touching", "held", "lost"]
    box: Box
    last_seen_ts: float


@dataclass
class SceneSnapshot:
    """Scene to dashboard, once per processed frame."""

    ts: float
    frame_id: int
    objects: list[SceneObject] = field(default_factory=list)


@dataclass
class NameRequest:
    """Scene to namer."""

    ts: float
    object_id: int
    class_label: str
    crop_jpeg: bytes


@dataclass
class NameResult:
    """Namer to scene and audio."""

    ts: float
    object_id: int
    name: str  # at most 40 characters, empty if naming failed
    ok: bool


@dataclass
class TouchEvent:
    """Scene to audio, storage, dashboard."""

    ts: float
    object_id: int
    class_label: str
    name: str
    kind: Literal["touch", "release"]
    box: Box
    neighbours: list[str] = field(default_factory=list)


@dataclass
class HazardEvent:
    """Hazard to audio, storage, dashboard."""

    ts: float
    type: Literal["stairs_down", "drop_off", "vehicle", "obstacle"]
    source: Literal["yolo", "grok"]
    confidence: float


@dataclass
class LastSeenQuery:
    """Dashboard to storage."""

    ts: float
    text: str


@dataclass
class SpeakRequest:
    """Anyone to audio."""

    ts: float
    text: str
    priority: Literal["normal"]
    source: str


# ---- SPEC.md section 9: thresholds -----------------------------------------

PROCESS_FPS = 5
PROCESS_WIDTH = 640
PROCESS_HEIGHT = 360
DET_MIN_CONFIDENCE = 0.5
DET_MIN_AREA_FRACTION = 0.02
STABLE_FRAMES = 5
LOST_KEEP_SECONDS = 2.0
BOX_SHRINK_FRACTION = 0.10
TOUCH_ENTER_FRAMES = 2
TOUCH_EXIT_FRAMES = 3
HELD_MOVE_FRACTION = 0.15
HELD_LOST_SECONDS = 1.0
HELD_MERGE_IOU = 0.3
NAME_CROP_PADDING = 0.10
NAME_MAX_IN_FLIGHT = 2
NAME_MIN_INTERVAL_SECONDS = 1.0
NAME_TIMEOUT_SECONDS = 4.0
NAME_MAX_CHARS = 40
LATE_NAME_WINDOW_SECONDS = 1.5
HAZARD_VEHICLE_MIN_AREA_FRACTION = 0.10
HAZARD_VEHICLE_GROWTH = 0.30
HAZARD_GROK_INTERVAL_SECONDS = 1.5
HAZARD_GROK_WIDTH = 512
HAZARD_GROK_MIN_CONFIDENCE = 0.6
HAZARD_GROK_TIMEOUT_SECONDS = 3.0
HAZARD_COOLDOWN_SECONDS = 3.0
DASHBOARD_PORT = 8000
