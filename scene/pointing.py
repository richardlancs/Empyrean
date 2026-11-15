"""Finger-ray pointing. Decides which object boxes extended fingers point at.

Pure arithmetic on the frame path: no logging, no I/O.
"""

from __future__ import annotations

import math

from config.thresholds import BOX_SHRINK_FRACTION, POINT_EXTENDED_RATIO
from contracts.messages import Box, Hand, Point

WRIST = 0
LANDMARK_COUNT = 21
# (mcp, pip, tip) MediaPipe indices for index, middle, ring and pinky. The thumb is ignored.
FINGERS: tuple[tuple[int, int, int], ...] = ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))

_EPSILON = 1e-9


def has_landmarks(hand: Hand) -> bool:
    """Return whether the hand reports a full set of 21 landmarks."""
    return len(hand.landmarks) == LANDMARK_COUNT


def finger_rays(hand: Hand) -> list[tuple[Point, Point]]:
    """Return (fingertip, unit direction) for each extended finger of the hand."""
    if not has_landmarks(hand):
        return []
    points = hand.landmarks
    wrist = points[WRIST]
    rays: list[tuple[Point, Point]] = []
    for mcp_i, pip_i, tip_i in FINGERS:
        mcp, pip, tip = points[mcp_i], points[pip_i], points[tip_i]
        if _dist(wrist, tip) <= POINT_EXTENDED_RATIO * _dist(wrist, pip):
            continue
        length = _dist(mcp, tip)
        if length < _EPSILON:
            continue
        direction = ((tip[0] - mcp[0]) / length, (tip[1] - mcp[1]) / length)
        rays.append((tip, direction))
    return rays


def ray_box_distance(origin: Point, direction: Point, box: Box) -> float | None:
    """Return the distance along the ray to the shrunk box, 0 inside it, or None on a miss."""
    shrunk = shrink_box(box)
    if shrunk is None:
        return None
    lows = (shrunk[0], shrunk[1])
    highs = (shrunk[2], shrunk[3])
    t_min = 0.0
    t_max = math.inf
    for axis in (0, 1):
        o = origin[axis]
        d = direction[axis]
        if abs(d) < _EPSILON:
            if o < lows[axis] or o > highs[axis]:
                return None
            continue
        t1 = (lows[axis] - o) / d
        t2 = (highs[axis] - o) / d
        t_min = max(t_min, min(t1, t2))
        t_max = min(t_max, max(t1, t2))
        if t_min > t_max:
            return None
    return t_min


def pointed_ids(boxes: list[tuple[int, Box]], hands: list[Hand]) -> set[int]:
    """Return the ids that any extended finger points at, the first box hit per finger."""
    pointed: set[int] = set()
    for hand in hands:
        for origin, direction in finger_rays(hand):
            best: tuple[float, int] | None = None
            for object_id, box in boxes:
                distance = ray_box_distance(origin, direction, box)
                if distance is None:
                    continue
                if best is None or (distance, object_id) < best:
                    best = (distance, object_id)
            if best is not None:
                pointed.add(best[1])
    return pointed


def shrink_box(box: Box) -> Box | None:
    """Return the box shrunk by BOX_SHRINK_FRACTION on every side, or None if it collapses."""
    bx1, by1, bx2, by2 = box
    width = bx2 - bx1
    height = by2 - by1
    x1 = bx1 + BOX_SHRINK_FRACTION * width
    x2 = bx2 - BOX_SHRINK_FRACTION * width
    y1 = by1 + BOX_SHRINK_FRACTION * height
    y2 = by2 - BOX_SHRINK_FRACTION * height
    if x1 >= x2 or y1 >= y2:
        return None
    return (x1, y1, x2, y2)


def _dist(a: Point, b: Point) -> float:
    """Return the distance between two points."""
    return math.hypot(a[0] - b[0], a[1] - b[1])
