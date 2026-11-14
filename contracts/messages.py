"""Message shapes from SPEC.md section 5.

Field names, types, and units are fixed. Do not add a required field
without all four teammates agreeing.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Box:
    """Pixel box in the 640 x 360 processed frame. Origin is top-left."""

    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class TrackedObject:
    """One tracked object inside a FrameResult."""

    object_id: int
    class_label: str
    confidence: float
    box: Box


@dataclass(frozen=True)
class Hand:
    """One hand. Tips are (x, y) pixels. side is left, right, or unknown."""

    side: str
    thumb_tip: tuple[float, float]
    index_tip: tuple[float, float]
    box: Box


@dataclass(frozen=True)
class FrameResult:
    """vision to everyone, once per processed frame.

    image is the 640 x 360 BGR frame. Tests that never crop may pass None.
    """

    ts: float
    frame_id: int
    image: object | None
    objects: list[TrackedObject]
    hands: list[Hand]


@dataclass(frozen=True)
class SceneObject:
    """One object inside a SceneSnapshot."""

    object_id: int
    class_label: str
    name: str
    state: str
    box: Box
    last_seen_ts: float


@dataclass(frozen=True)
class SceneSnapshot:
    """scene to dashboard, once per processed frame."""

    ts: float
    frame_id: int
    objects: list[SceneObject]


@dataclass(frozen=True)
class NameRequest:
    """scene to namer."""

    ts: float
    object_id: int
    class_label: str
    crop_jpeg: bytes


@dataclass(frozen=True)
class NameResult:
    """namer to scene and audio."""

    ts: float
    object_id: int
    name: str
    ok: bool


@dataclass(frozen=True)
class TouchEvent:
    """scene to audio, storage, and dashboard."""

    ts: float
    object_id: int
    class_label: str
    name: str
    kind: str
    box: Box
    neighbours: list[str]


@dataclass(frozen=True)
class HazardEvent:
    """hazard to audio, storage, and dashboard."""

    ts: float
    type: str
    source: str
    confidence: float


@dataclass(frozen=True)
class LastSeenQuery:
    """dashboard to storage."""

    ts: float
    text: str


@dataclass(frozen=True)
class SpeakRequest:
    """anyone to audio. priority is normal. Alarms are HazardEvents."""

    ts: float
    text: str
    priority: str
    source: str
