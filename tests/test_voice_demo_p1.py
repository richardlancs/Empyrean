"""Person 1 voice demo routing tests; microphone hardware is not required."""

from __future__ import annotations

from app.voice_demo import make_reply
from contracts import LastSeenQuery, SceneObject, SpeakRequest


def scene_object(
    object_id: int,
    name: str,
    state: str,
    class_label: str = "bottle",
) -> SceneObject:
    """Build a sample object for fake scene questions."""
    return SceneObject(
        object_id=object_id,
        class_label=class_label,
        name=name,
        state=state,
        box=(10.0, 10.0, 100.0, 100.0),
        last_seen_ts=1.0,
    )


def test_fake_scene_question_lists_only_visible_objects() -> None:
    """Ask about the fake scene without revealing new or lost tracks."""
    objects = [
        scene_object(1, "Heinz ketchup", "idle"),
        scene_object(2, "", "held", "cup"),
        scene_object(3, "old book", "lost", "book"),
        scene_object(4, "unnamed", "new"),
    ]
    reply = make_reply("What can you see?", objects, 123.0)
    assert reply == SpeakRequest(
        ts=123.0,
        text="I can see Heinz ketchup, cup.",
        priority="normal",
        source="app",
    )


def test_fake_holding_question_uses_active_states_only() -> None:
    """Only touching/held objects are reported as held or touched."""
    objects = [
        scene_object(1, "Heinz ketchup", "touching"),
        scene_object(2, "", "held", "cup"),
        scene_object(3, "book", "idle"),
    ]
    reply = make_reply("What am I holding?", objects, 124.0)
    assert isinstance(reply, SpeakRequest)
    assert reply.text == "You are touching Heinz ketchup, cup."


def test_last_touch_question_uses_existing_query_contract() -> None:
    """Last-seen questions are delegated to storage, not answered locally."""
    reply = make_reply("Where did I last touch my phone?", [], 125.0)
    assert reply == LastSeenQuery(ts=125.0, text="phone")


def test_missing_object_and_unknown_question_are_spoken() -> None:
    """Unknown objects/questions receive short, safe spoken responses."""
    empty = make_reply("What can you see?", [], 126.0)
    assert isinstance(empty, SpeakRequest)
    assert empty.text == "I don't detect any objects right now."

    unspecified = make_reply("Where did I last touch?", [], 127.0)
    assert isinstance(unspecified, SpeakRequest)
    assert unspecified.text == "Please specify an object."

    unknown = make_reply("Hello?", [], 128.0)
    assert isinstance(unknown, SpeakRequest)
    assert unknown.source == "app"
