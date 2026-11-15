"""Synthetic MediaPipe-style hands for pointing tests."""

import math

from contracts.messages import Hand, Point

# (mcp, pip, tip) landmark indices for index, middle, ring and pinky.
_FINGERS = ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))
_EXTENDED = (40.0, 60.0, 85.0)  # mcp, pip, tip distance from the wrist
_CURLED = (40.0, 55.0, 30.0)  # tip folded back toward the wrist


def pointing_hand(
    wrist: Point,
    toward: Point,
    extended: tuple[int, ...] = (0,),
    side: str = "right",
    scale: float = 1.0,
) -> Hand:
    """Build a hand whose listed fingers point from the wrist toward a point."""
    dx = toward[0] - wrist[0]
    dy = toward[1] - wrist[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    points: list[Point] = [wrist] * 21
    for offset, index in enumerate((1, 2, 3, 4)):
        points[index] = (wrist[0] - 5.0 * (offset + 1), wrist[1])
    for finger, (mcp, pip, tip) in enumerate(_FINGERS):
        distances = _EXTENDED if finger in extended else _CURLED
        for landmark, distance in zip((mcp, pip, tip), distances, strict=True):
            points[landmark] = (wrist[0] + ux * distance * scale, wrist[1] + uy * distance * scale)
        dip = (points[pip][0] + points[tip][0]) / 2.0, (points[pip][1] + points[tip][1]) / 2.0
        points[tip - 1] = dip
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return Hand(
        side=side,
        thumb_tip=points[4],
        index_tip=points[8],
        box=(min(xs), min(ys), max(xs), max(ys)),
        landmarks=points,
    )


def gripping_hand(wrist: Point) -> Hand:
    """Build a gripping hand: every finger curled, tips folded back near the wrist."""
    return pointing_hand(wrist, (wrist[0], wrist[1] - 100.0), extended=())
