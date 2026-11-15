"""Message shapes from SPEC.md section 5.

Field names, types and units are fixed by the spec. Coordinates are pixels in
the 640 x 360 processed frame, origin top-left. Every ts is float seconds since
the Unix epoch, UTC. Do not redefine these locally.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

Box = tuple[float, float, float, float]  # x1, y1, x2, y2 in 640 x 360 pixels
Point = tuple[float, float]  # x, y in 640 x 360 pixels


@dataclass
class TrackedObject:
    """One entry of FrameResult.objects, from vision to everyone."""

    object_id: int
    class_label: str
    confidence: float  # 0 to 1
    box: Box


@dataclass
class Hand:
    """One entry of FrameResult.hands, from vision to everyone."""

    side: Literal["left", "right", "unknown"]
    thumb_tip: Point
    index_tip: Point
    box: Box
    landmarks: list[Point] = field(default_factory=list)  # 21 MediaPipe points, or empty


@dataclass
class FrameResult:
    """Vision to everyone, once per processed frame."""

    ts: float  # capture time
    frame_id: int  # counts up from 0
    image: Any  # 640 x 360 BGR image
    objects: list[TrackedObject] = field(default_factory=list)
    hands: list[Hand] = field(default_factory=list)


@dataclass
class SceneObject:
    """One entry of SceneSnapshot.objects, from scene to dashboard."""

    object_id: int
    class_label: str
    name: str  # Grok name, or empty
    state: Literal["new", "idle", "touching", "held", "lost"]
    box: Box
    last_seen_ts: float


@dataclass
class SceneSnapshot:
    """Scene to dashboard, once per processed frame."""

    ts: float  # time of the frame it describes
    frame_id: int  # matches the FrameResult
    objects: list[SceneObject] = field(default_factory=list)


@dataclass
class NameRequest:
    """Scene to namer."""

    ts: float  # when requested
    object_id: int
    class_label: str  # COCO class, as a hint
    crop_jpeg: bytes  # JPEG of the object, padded 10%


@dataclass
class NameResult:
    """Namer to scene and audio."""

    ts: float  # when answered
    object_id: int
    name: str  # at most 40 characters, empty if naming failed
    ok: bool  # False on timeout or error


@dataclass
class TouchEvent:
    """Scene to audio, storage and dashboard."""

    ts: float  # when the transition happened
    object_id: int
    class_label: str  # COCO class
    name: str  # Grok name if known, else empty
    kind: Literal["touch", "release"]
    box: Box  # object box at that moment
    neighbours: list[str] = field(default_factory=list)  # up to 3 nearest others


@dataclass
class HazardEvent:
    """Hazard to audio, storage and dashboard."""

    ts: float  # when detected
    type: Literal["stairs_down", "drop_off", "vehicle", "obstacle"]
    source: Literal["yolo", "grok"]
    confidence: float  # 0 to 1


@dataclass
class LastSeenQuery:
    """Dashboard to storage."""

    ts: float  # when asked
    text: str  # what to search for
    request_id: str | None = None  # optional; set to get a LastSeenResult back


@dataclass
class LastSeenResult:
    """Storage to dashboard: the outcome of one LastSeenQuery that had a request_id."""

    ts: float  # when answered
    request_id: str  # copied from the LastSeenQuery
    status: Literal["found", "not_found", "unavailable"]
    answer: str  # exactly the sentence published as the SpeakRequest
    matched_at: float | None = None  # ts of the matching touch, None unless found
    label: str = ""  # name or class label of the match, empty unless found
    neighbours: list[str] = field(default_factory=list)  # recorded with the match


@dataclass
class SpeakRequest:
    """Anyone to audio. Alarms come from HazardEvent, never from here."""

    ts: float  # when requested
    text: str  # what to say
    priority: Literal["normal"]
    source: str  # folder name of the sender


@dataclass
class SpeechStatus:
    """Audio to dashboard: one step in the life of one spoken phrase.

    completed means the speech engine returned, not that anyone heard it.
    """

    ts: float  # when the step happened
    speech_id: int  # the same for every step of one phrase
    text: str  # what is, was, or would have been said
    status: Literal["queued", "speaking", "completed", "interrupted", "failed"]
    mode: Literal["real", "fake", "unavailable"]  # real = a speech engine on a device
    kind: Literal["touch", "answer", "hazard"]
    object_id: int | None = None  # set for touch speech
    source: str = ""  # folder name of whoever asked for it
    detail: str = ""  # why it was interrupted or failed


@dataclass
class ModuleStatus:
    """Any module to dashboard: an explicit lifecycle or availability change."""

    ts: float  # when the status changed
    module: str  # folder name: vision, scene, namer, storage, audio, hazard
    status: Literal["starting", "active", "degraded", "offline", "unknown"]
    mode: Literal["real", "fake", "unknown"] = "unknown"
    detail: str = ""  # short plain reason; never a key or connection string


@dataclass
class ModeChange:
    """Dashboard to vision: a request to switch detectors (from main, extended).

    Vision answers with DetectorStatus; a ModeChange is never a confirmation.
    """

    ts: float  # when the switch was requested
    mode: Literal["actual", "demo"]  # actual: general COCO detector. demo: demo detector
    request_id: str | None = None  # optional; echoed in the DetectorStatus that answers it


@dataclass
class DetectorStatus:
    """Vision to dashboard: which detector is really running, and any switch in progress.

    This is the only confirmation of a mode change. active_mode is what the
    frame loop uses now; it changes only after the replacement detector is
    loaded, validated and swapped in.
    """

    ts: float  # when this status was true
    state: Literal["active", "switching", "failed"]
    active_mode: Literal["actual", "demo"]  # the detector processing frames now
    detector: str  # plain identity of the active detector, never a guess
    requested_mode: Literal["actual", "demo"] | None = None  # set while switching or after a failure
    request_id: str | None = None  # from the ModeChange this answers, if any
    checkpoint: str = ""  # file, size, SHA-256 prefix of the loaded demo checkpoint
    demo_kind: Literal["trained", "prompt-fallback", "fake", "none"] = "none"
    demo_available: bool | None = None  # None: not checked yet
    message: str = ""  # why a switch failed, or how to make Demo available
    fake: bool = False  # True when vision is a fake (recorded clip): no model runs


@dataclass
class VoiceChange:
    """Dashboard to audio: a request to switch the spoken voice. Never a confirmation."""

    ts: float  # when the switch was requested
    voice: str  # preset key, for example "ava"
    request_id: str | None = None  # echoed in the VoiceStatus that answers it


@dataclass
class VoiceStatus:
    """Audio to dashboard: the voice speech really uses now.

    This is the only confirmation of a voice switch. Audio applies a switch
    between phrases, never mid-phrase and never ahead of a hazard.
    """

    ts: float  # when this status was true
    state: Literal["active", "failed"]
    active_voice: str  # preset key in use now
    label: str  # display name of the active preset, for example "Ava"
    quality: Literal["premium", "enhanced", "compact", "fallback"]
    voices: dict[str, str] = field(default_factory=dict)  # preset key -> label, menu order
    installed: list[str] = field(default_factory=list)  # keys whose own voice is installed
    requested_voice: str | None = None  # set when answering or refusing a VoiceChange
    request_id: str | None = None  # from the VoiceChange this answers, if any
    detail: str = ""  # why a switch failed, or which voice stands in


@dataclass
class SceneQuestion:
    """Dashboard to namer: ask Grok about the current camera view."""

    ts: float
    text: str
