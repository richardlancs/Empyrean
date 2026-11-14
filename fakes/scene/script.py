"""Scripted SceneSnapshot, NameRequest, and TouchEvent messages."""

from collections.abc import Callable

from contracts.messages import (
    Box,
    NameRequest,
    SceneObject,
    SceneSnapshot,
    TouchEvent,
)

Publish = Callable[[str, object], None]

# Smallest JPEG (start and end markers). Stand-in until a recorded crop exists.
_CROP_JPEG = b"\xff\xd8\xff\xd9"


def scripted_messages() -> list[tuple[str, object]]:
    """Return a short realistic scene sequence.

    A bottle and a cup appear, become idle, are sent for naming, and the
    bottle is touched and then lost while the hand covers it.
    """
    ts = 1763000000.0
    bottle_box = Box(100, 80, 220, 300)
    cup_box = Box(260, 140, 360, 280)
    messages: list[object] = [
        SceneSnapshot(
            ts,
            0,
            [
                SceneObject(1, "bottle", "", "new", bottle_box, ts),
                SceneObject(2, "cup", "", "new", cup_box, ts),
            ],
        ),
        SceneSnapshot(
            ts + 1.0,
            5,
            [
                SceneObject(1, "bottle", "", "idle", bottle_box, ts + 1.0),
                SceneObject(2, "cup", "", "idle", cup_box, ts + 1.0),
            ],
        ),
        NameRequest(ts + 1.0, 1, "bottle", _CROP_JPEG),
        NameRequest(ts + 1.0, 2, "cup", _CROP_JPEG),
        SceneSnapshot(
            ts + 1.4,
            7,
            [
                SceneObject(1, "bottle", "Heinz ketchup", "idle", bottle_box, ts + 1.4),
                SceneObject(2, "cup", "blue mug", "idle", cup_box, ts + 1.4),
            ],
        ),
        TouchEvent(
            ts + 1.6,
            1,
            "bottle",
            "Heinz ketchup",
            "touch",
            bottle_box,
            ["blue mug"],
        ),
        SceneSnapshot(
            ts + 1.6,
            8,
            [
                SceneObject(
                    1, "bottle", "Heinz ketchup", "touching", bottle_box, ts + 1.6
                ),
                SceneObject(2, "cup", "blue mug", "idle", cup_box, ts + 1.6),
            ],
        ),
        SceneSnapshot(
            ts + 1.8,
            9,
            [
                SceneObject(1, "bottle", "Heinz ketchup", "lost", bottle_box, ts + 1.6),
                SceneObject(2, "cup", "blue mug", "idle", cup_box, ts + 1.8),
            ],
        ),
        TouchEvent(
            ts + 2.4,
            1,
            "bottle",
            "Heinz ketchup",
            "release",
            bottle_box,
            ["blue mug"],
        ),
    ]
    return [(type(message).__name__, message) for message in messages]


def publish_script(publish: Publish) -> None:
    """Publish scripted_messages in order."""
    for topic, message in scripted_messages():
        publish(topic, message)
