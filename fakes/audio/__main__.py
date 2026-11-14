"""Print what audio/ would play for a short scripted sequence. Used as `python -m fakes.audio`."""

from __future__ import annotations

import time

from contracts import HazardEvent, NameResult, SpeakRequest, TouchEvent
from fakes.audio.fake_audio import FakeAudio, Played


def main() -> None:
    """Feed scripted messages to FakeAudio and print each would-be sound."""

    def show(item: Played) -> None:
        label = "ALARM (three beeps), then" if item.kind == "alarm" else "SPEAK"
        print(f"{label}: {item.text}")

    audio = FakeAudio(show)
    now = time.time()
    box = (100.0, 80.0, 200.0, 240.0)
    audio.on_touch(
        TouchEvent(
            ts=now,
            object_id=1,
            class_label="bottle",
            name="Heinz ketchup",
            kind="touch",
            box=box,
        )
    )
    audio.on_touch(
        TouchEvent(
            ts=now + 1,
            object_id=1,
            class_label="bottle",
            name="Heinz ketchup",
            kind="release",
            box=box,
        )
    )
    audio.on_touch(
        TouchEvent(
            ts=now + 2, object_id=2, class_label="cup", name="", kind="touch", box=box
        )
    )
    audio.on_name_result(
        NameResult(ts=now + 2.8, object_id=2, name="Starbucks coffee cup", ok=True)
    )
    audio.on_hazard(
        HazardEvent(ts=now + 4, type="stairs_down", source="grok", confidence=0.82)
    )
    audio.on_speak_request(
        SpeakRequest(
            ts=now + 6,
            text="Keys last seen 2 minutes ago.",
            priority="normal",
            source="storage",
        )
    )


if __name__ == "__main__":
    main()
