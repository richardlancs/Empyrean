"""Touch state machine. Compares fingertips with object boxes."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from config.thresholds import (
    BOX_SHRINK_FRACTION,
    HELD_LOST_SECONDS,
    HELD_MERGE_IOU,
    HELD_MOVE_FRACTION,
    PROCESS_WIDTH,
    TOUCH_ENTER_FRAMES,
    TOUCH_EXIT_FRAMES,
)
from contracts.messages import Box, Hand, TouchEvent


@dataclass
class TouchTrack:
    """Contact state for one object on the processed frame."""

    object_id: int
    class_label: str
    name: str
    state: str
    box: Box
    detected: bool
    phase: str
    on_frames: int
    off_frames: int
    anchor_cx: float | None
    anchor_cy: float | None
    lost_since_ts: float | None
    hand_clear_frames: int


@dataclass(frozen=True)
class TouchStep:
    """Tracks, touch events, and ids removed by a held-object merge."""

    tracks: list[TouchTrack]
    events: list[TouchEvent]
    dropped_ids: list[int]


@dataclass(frozen=True)
class _Draft:
    """Touch or release before neighbour names are filled in."""

    object_id: int
    class_label: str
    name: str
    kind: str
    box: Box


def step_touch(tracks: list[TouchTrack], hands: list[Hand], ts: float) -> TouchStep:
    """Advance touch phases by one processed frame. Does not mutate the input tracks."""
    on_ids = _on_ids(tracks, hands)
    drafts: list[_Draft] = []
    updated = [replace(track) for track in tracks]
    for track in updated:
        _advance(track, track.object_id in on_ids, hands, ts, drafts)
    dropped = _merge_held(updated, hands)
    dropped_ids = set(dropped)
    kept = [track for track in updated if track.object_id not in dropped_ids]
    events = [
        TouchEvent(
            ts=ts,
            object_id=draft.object_id,
            class_label=draft.class_label,
            name=draft.name,
            kind=draft.kind,
            box=draft.box,
            neighbours=_neighbours(kept, draft.object_id, draft.box),
        )
        for draft in drafts
    ]
    return TouchStep(tracks=kept, events=events, dropped_ids=dropped)


def release_on_removal(
    track: TouchTrack,
    others: list[TouchTrack],
    ts: float,
) -> TouchEvent | None:
    """Release for a track the scene is about to delete, or None if not in contact.

    A touching or held object that stays lost past the keep time would
    otherwise vanish with its touch still open.
    """
    if track.phase not in ("touching", "held"):
        return None
    return TouchEvent(
        ts=ts,
        object_id=track.object_id,
        class_label=track.class_label,
        name=track.name,
        kind="release",
        box=track.box,
        neighbours=_neighbours(others, track.object_id, track.box),
    )


def _center(box: Box) -> tuple[float, float]:
    """Return the box centre in pixels."""
    x1, y1, x2, y2 = box
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _contains_shrunk(box: Box, x: float, y: float) -> bool:
    """Return whether the point lies inside the box after it is shrunk."""
    bx1, by1, bx2, by2 = box
    width = bx2 - bx1
    height = by2 - by1
    x1 = bx1 + BOX_SHRINK_FRACTION * width
    x2 = bx2 - BOX_SHRINK_FRACTION * width
    y1 = by1 + BOX_SHRINK_FRACTION * height
    y2 = by2 - BOX_SHRINK_FRACTION * height
    if x1 > x2 or y1 > y2:
        return False
    return x1 <= x <= x2 and y1 <= y <= y2


def _iou(a: Box, b: Box) -> float:
    """Return intersection over union. No overlap or a zero union is 0."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_w = min(ax2, bx2) - max(ax1, bx1)
    inter_h = min(ay2, by2) - max(ay1, by1)
    if inter_w <= 0.0 or inter_h <= 0.0:
        return 0.0
    inter = inter_w * inter_h
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _is_candidate(track: TouchTrack) -> bool:
    """Return whether a fingertip is allowed to land on this track."""
    return track.state != "new" or track.phase in ("touching", "held")


def _on_ids(tracks: list[TouchTrack], hands: list[Hand]) -> set[int]:
    """Assign each fingertip to at most one candidate and return those ids."""
    candidates = [track for track in tracks if _is_candidate(track)]
    tipped: set[int] = set()
    for hand in hands:
        for point in (hand.thumb_tip, hand.index_tip):
            winner = _assign_fingertip(candidates, point)
            if winner is not None:
                tipped.add(winner)
    return tipped


def _assign_fingertip(
    candidates: list[TouchTrack],
    point: tuple[float, float],
) -> int | None:
    """Pick the containing box whose centre is nearest as a fraction of its diagonal."""
    px, py = point
    best_id: int | None = None
    best_ratio: float | None = None
    for track in candidates:
        if not _contains_shrunk(track.box, px, py):
            continue
        x1, y1, x2, y2 = track.box
        width = x2 - x1
        height = y2 - y1
        diagonal = math.hypot(width, height)
        if diagonal == 0.0:
            continue
        cx, cy = _center(track.box)
        ratio = math.hypot(px - cx, py - cy) / diagonal
        if best_ratio is None or ratio < best_ratio:
            best_ratio = ratio
            best_id = track.object_id
    return best_id


def _clear_episode(track: TouchTrack) -> None:
    """Clear counters and anchors for an open contact episode."""
    track.on_frames = 0
    track.off_frames = 0
    track.hand_clear_frames = 0
    track.anchor_cx = None
    track.anchor_cy = None
    track.lost_since_ts = None


def _end_contact(track: TouchTrack) -> None:
    """Open the episode and set idle or lost from the current detection."""
    track.phase = "open"
    track.state = "idle" if track.detected else "lost"
    _clear_episode(track)


def _remember(drafts: list[_Draft], track: TouchTrack, kind: str) -> None:
    """Snapshot a touch or release using the track box at this moment."""
    drafts.append(
        _Draft(
            object_id=track.object_id,
            class_label=track.class_label,
            name=track.name,
            kind=kind,
            box=track.box,
        )
    )


def _moved_far(track: TouchTrack) -> bool:
    """Return whether the box centre has moved past the held threshold."""
    if track.anchor_cx is None or track.anchor_cy is None:
        return False
    cx, cy = _center(track.box)
    distance = math.hypot(cx - track.anchor_cx, cy - track.anchor_cy)
    return distance > HELD_MOVE_FRACTION * PROCESS_WIDTH


def _advance(
    track: TouchTrack,
    on: bool,
    hands: list[Hand],
    ts: float,
    drafts: list[_Draft],
) -> None:
    """Apply one frame of the touch phase machine to a copied track."""
    if track.state == "new" and track.phase == "open":
        _clear_episode(track)
        track.state = "new"
        return

    if track.phase == "open":
        _advance_open(track, on, drafts)
        return

    if track.phase == "touching":
        _advance_touching(track, on, ts, drafts)
        return

    if track.phase == "held":
        _advance_held(track, on, hands, drafts)


def _advance_open(track: TouchTrack, on: bool, drafts: list[_Draft]) -> None:
    """Count consecutive on-frames and emit the single enter event."""
    if on:
        track.on_frames += 1
        track.off_frames = 0
    else:
        track.on_frames = 0
    if track.on_frames < TOUCH_ENTER_FRAMES:
        return
    cx, cy = _center(track.box)
    track.phase = "touching"
    track.state = "touching"
    track.anchor_cx = cx
    track.anchor_cy = cy
    track.lost_since_ts = None
    track.off_frames = 0
    _remember(drafts, track, "touch")


def _advance_touching(
    track: TouchTrack,
    on: bool,
    ts: float,
    drafts: list[_Draft],
) -> None:
    """Move a touching episode to held, lost, or release."""
    if on and track.detected and _moved_far(track):
        track.phase = "held"
        track.state = "held"
        track.off_frames = 0
        track.hand_clear_frames = 0
        return
    if on and not track.detected:
        if track.lost_since_ts is None:
            track.lost_since_ts = ts
        if ts - track.lost_since_ts >= HELD_LOST_SECONDS:
            track.phase = "held"
            track.state = "held"
        else:
            track.state = "lost"
        return
    if on and track.detected:
        track.lost_since_ts = None
        track.phase = "touching"
        track.state = "touching"
        track.off_frames = 0
        return
    track.off_frames += 1
    if track.off_frames >= TOUCH_EXIT_FRAMES:
        _remember(drafts, track, "release")
        _end_contact(track)
        return
    track.state = "touching" if track.detected else "lost"


def _advance_held(
    track: TouchTrack,
    on: bool,
    hands: list[Hand],
    drafts: list[_Draft],
) -> None:
    """Release a held object after the hand leaves or the fingertips stay off."""
    if len(hands) == 0:
        track.hand_clear_frames += 1
    else:
        track.hand_clear_frames = 0
    if on:
        track.off_frames = 0
    else:
        track.off_frames += 1
    if (
        track.hand_clear_frames >= TOUCH_EXIT_FRAMES
        or track.off_frames >= TOUCH_EXIT_FRAMES
    ):
        _remember(drafts, track, "release")
        _end_contact(track)
        return
    track.phase = "held"
    track.state = "held"


def _merge_held(tracks: list[TouchTrack], hands: list[Hand]) -> list[int]:
    """Give a new detection the identity of a held track when it overlaps a hand.

    Only tracks still in state new can inherit, so a stable object next to the
    hand never loses its own identity. Pairs are ranked by IoU with a hand box.
    IoU with the held box breaks ties so two held objects keep the detection
    that overlaps them. Each id is used once. The match emits no event.
    """
    pairs: list[tuple[float, float, int, int]] = []
    for held_index, held in enumerate(tracks):
        if held.phase != "held":
            continue
        for det_index, det in enumerate(tracks):
            if det.object_id == held.object_id or not det.detected:
                continue
            if det.state != "new" or det.phase != "open":
                continue
            hand_iou = _best_hand_iou(det.box, hands)
            if hand_iou < HELD_MERGE_IOU:
                continue
            pairs.append((hand_iou, _iou(det.box, held.box), held_index, det_index))
    pairs.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))

    used: set[int] = set()
    dropped: list[int] = []
    for _hand_iou, _held_iou, held_index, det_index in pairs:
        held = tracks[held_index]
        det = tracks[det_index]
        if held.object_id in used or det.object_id in used:
            continue
        used.add(held.object_id)
        used.add(det.object_id)
        det.name = held.name
        det.phase = "held"
        det.state = "held"
        det.anchor_cx = held.anchor_cx
        det.anchor_cy = held.anchor_cy
        det.lost_since_ts = held.lost_since_ts
        det.off_frames = 0
        det.hand_clear_frames = 0
        if held.detected:
            held.phase = "open"
            held.state = "idle"
            _clear_episode(held)
        else:
            dropped.append(held.object_id)
    return dropped


def _best_hand_iou(box: Box, hands: list[Hand]) -> float:
    """Return the greatest IoU between a box and any hand box."""
    best = 0.0
    for hand in hands:
        best = max(best, _iou(box, hand.box))
    return best


def _neighbours(tracks: list[TouchTrack], object_id: int, origin: Box) -> list[str]:
    """Return up to three nearest other labels, preferring a non-empty name."""
    cx, cy = _center(origin)
    ranked: list[tuple[float, int, str]] = []
    for index, track in enumerate(tracks):
        if track.object_id == object_id:
            continue
        ox, oy = _center(track.box)
        label = track.name if track.name else track.class_label
        ranked.append((math.hypot(ox - cx, oy - cy), index, label))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [label for _distance, _index, label in ranked[:3]]
