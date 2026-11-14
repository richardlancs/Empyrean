"""Smoke tests for the scene database and the scene fake."""

from config.thresholds import (
    LOST_KEEP_SECONDS,
    PROCESS_HEIGHT,
    PROCESS_WIDTH,
    STABLE_FRAMES,
    TOUCH_ENTER_FRAMES,
    TOUCH_EXIT_FRAMES,
)
from contracts.messages import (
    Box,
    FrameResult,
    Hand,
    NameRequest,
    NameResult,
    SceneSnapshot,
    TouchEvent,
    TrackedObject,
)
from fakes.scene import publish_script, scripted_messages
from scene import SceneDatabase


def _detection(
    object_id: int = 1,
    class_label: str = "bottle",
    box: Box | None = None,
) -> TrackedObject:
    return TrackedObject(
        object_id=object_id,
        class_label=class_label,
        confidence=0.91,
        box=box if box is not None else (100, 80, 220, 300),
    )


def _frame(
    frame_id: int,
    ts: float,
    objects: list[TrackedObject] | None = None,
    image: object | None = None,
    hands: list[Hand] | None = None,
) -> FrameResult:
    return FrameResult(
        ts=ts,
        frame_id=frame_id,
        image=image,
        objects=[] if objects is None else objects,
        hands=[] if hands is None else hands,
    )


def _image() -> object:
    import numpy as np

    return np.zeros((PROCESS_HEIGHT, PROCESS_WIDTH, 3), dtype=np.uint8)


def _hand_on(box: Box) -> Hand:
    center_x = (box[0] + box[2]) / 2.0
    center_y = (box[1] + box[3]) / 2.0
    return Hand(
        side="right",
        thumb_tip=(center_x, center_y),
        index_tip=(center_x, center_y),
        box=box,
    )


def _settle(
    database: SceneDatabase,
    det: TrackedObject,
    image: object | None = None,
) -> None:
    for index in range(STABLE_FRAMES):
        database.handle_frame(_frame(index, index * 0.2, [det], image=image))


def _database() -> tuple[SceneDatabase, list[tuple[str, object]]]:
    published: list[tuple[str, object]] = []
    database = SceneDatabase(lambda topic, message: published.append((topic, message)))
    return database, published


def test_object_stays_new_until_it_has_been_stable() -> None:
    database, _published = _database()
    det = _detection()
    snapshot = None
    for index in range(STABLE_FRAMES - 1):
        snapshot = database.handle_frame(_frame(index, index * 0.2, [det]))
    assert snapshot is not None
    assert snapshot.objects[0].state == "new"
    assert snapshot.objects[0].name == ""


def test_object_becomes_idle_after_stable_frames() -> None:
    database, published = _database()
    det = _detection()
    snapshot = None
    for index in range(STABLE_FRAMES):
        snapshot = database.handle_frame(_frame(index, 10.0 + index * 0.2, [det]))
    assert snapshot is not None
    assert snapshot.objects[0].state == "idle"
    assert snapshot.frame_id == STABLE_FRAMES - 1
    assert snapshot.ts == 10.0 + (STABLE_FRAMES - 1) * 0.2
    assert len(published) == STABLE_FRAMES
    assert all(topic == "SceneSnapshot" for topic, _message in published)


def test_missing_object_becomes_lost_and_keeps_its_box() -> None:
    database, _published = _database()
    box = (40, 50, 140, 200)
    det = _detection(box=box)
    for index in range(STABLE_FRAMES):
        database.handle_frame(_frame(index, 50.0 + index, [det]))
    lost = database.handle_frame(_frame(STABLE_FRAMES, 50.0 + STABLE_FRAMES, []))
    assert len(lost.objects) == 1
    assert lost.objects[0].state == "lost"
    assert lost.objects[0].box == box
    assert lost.objects[0].last_seen_ts == 50.0 + STABLE_FRAMES - 1


def test_lost_object_is_removed_after_keep_seconds() -> None:
    database, _published = _database()
    det = _detection()
    database.handle_frame(_frame(0, 0.0, [det]))
    last_seen = 0.0
    kept = database.handle_frame(_frame(1, last_seen + LOST_KEEP_SECONDS - 0.01, []))
    assert len(kept.objects) == 1
    assert kept.objects[0].state == "lost"
    gone = database.handle_frame(_frame(2, last_seen + LOST_KEEP_SECONDS, []))
    assert gone.objects == []


def test_stable_object_returns_to_idle_when_seen_again() -> None:
    database, _published = _database()
    first = (10, 10, 80, 80)
    moved = (20, 15, 90, 90)
    for index in range(STABLE_FRAMES):
        database.handle_frame(_frame(index, float(index), [_detection(box=first)]))
    database.handle_frame(_frame(STABLE_FRAMES, float(STABLE_FRAMES), []))
    back = database.handle_frame(
        _frame(STABLE_FRAMES + 1, float(STABLE_FRAMES + 1), [_detection(box=moved)])
    )
    assert back.objects[0].state == "idle"
    assert back.objects[0].box == moved


def test_gap_before_stable_resets_the_streak() -> None:
    database, _published = _database()
    det = _detection()
    last_index = STABLE_FRAMES - 3
    for index in range(last_index + 1):
        snapshot = database.handle_frame(_frame(index, float(index), [det]))
    assert snapshot.objects[0].state == "new"
    # The miss stays inside the keep window, so the object is lost rather than removed.
    missed = database.handle_frame(_frame(last_index + 1, float(last_index) + 0.2, []))
    assert missed.objects[0].state == "lost"
    for index in range(STABLE_FRAMES):
        snapshot = database.handle_frame(_frame(100 + index, 100.0 + index, [det]))
        expected = "idle" if index == STABLE_FRAMES - 1 else "new"
        assert snapshot.objects[0].state == expected


def test_objects_reach_idle_independently() -> None:
    database, _published = _database()
    bottle = _detection(1, "bottle", (100, 80, 220, 300))
    cup = _detection(2, "cup", (260, 140, 360, 280))
    snapshot = None
    for index in range(STABLE_FRAMES - 1):
        snapshot = database.handle_frame(_frame(index, float(index), [bottle]))
    assert snapshot is not None
    assert snapshot.objects[0].state == "new"
    both = database.handle_frame(
        _frame(STABLE_FRAMES - 1, float(STABLE_FRAMES - 1), [bottle, cup])
    )
    by_id = {item.object_id: item for item in both.objects}
    assert by_id[1].state == "idle"
    assert by_id[2].state == "new"
    assert by_id[2].class_label == "cup"


def test_each_frame_publishes_one_snapshot() -> None:
    database, published = _database()
    snapshot = database.handle_frame(_frame(3, 12.5, []))
    assert snapshot.objects == []
    assert snapshot.frame_id == 3
    assert snapshot.ts == 12.5
    assert published == [("SceneSnapshot", snapshot)]


def test_fake_publishes_snapshot_name_request_and_touch() -> None:
    messages = scripted_messages(start_ts=1763000000.0)  # fixed time: compared below
    topics = {topic for topic, _message in messages}
    assert topics == {"SceneSnapshot", "NameRequest", "TouchEvent"}
    kinds = [
        message.kind for _topic, message in messages if isinstance(message, TouchEvent)
    ]
    assert kinds == ["touch", "release"]
    requests = [
        message for _topic, message in messages if isinstance(message, NameRequest)
    ]
    assert requests[0].crop_jpeg.startswith(b"\xff\xd8")
    assert requests[0].object_id == 1
    states = [
        obj.state
        for _topic, message in messages
        if isinstance(message, SceneSnapshot)
        for obj in message.objects
    ]
    assert "touching" in states
    assert "lost" in states
    published: list[tuple[str, object]] = []
    publish_script(lambda topic, message: published.append((topic, message)), 1763000000.0)
    assert published == messages


def test_becoming_idle_publishes_one_name_request() -> None:
    database, published = _database()
    det = _detection()
    image = _image()
    for index in range(STABLE_FRAMES - 1):
        database.handle_frame(_frame(index, float(index), [det], image=image))
    assert [topic for topic, _message in published if topic == "NameRequest"] == []
    database.handle_frame(
        _frame(STABLE_FRAMES - 1, float(STABLE_FRAMES), [det], image=image)
    )
    requests = [
        message for topic, message in published if isinstance(message, NameRequest)
    ]
    assert len(requests) == 1
    assert requests[0].object_id == 1
    assert requests[0].class_label == "bottle"
    assert requests[0].crop_jpeg.startswith(b"\xff\xd8")
    database.handle_frame(
        _frame(STABLE_FRAMES, float(STABLE_FRAMES + 1), [det], image=image)
    )
    assert (
        len(
            [
                message
                for topic, message in published
                if isinstance(message, NameRequest)
            ]
        )
        == 1
    )


def test_fingertip_dwell_publishes_touch_and_release() -> None:
    database, published = _database()
    det = _detection()
    _settle(database, det)
    hand = _hand_on(det.box)
    snapshot = None
    for index in range(TOUCH_ENTER_FRAMES):
        snapshot = database.handle_frame(
            _frame(100 + index, 20.0 + index * 0.2, [det], hands=[hand])
        )
    assert snapshot is not None
    assert snapshot.objects[0].state == "touching"
    for index in range(TOUCH_EXIT_FRAMES):
        snapshot = database.handle_frame(_frame(200 + index, 30.0 + index * 0.2, [det]))
    assert snapshot is not None
    assert snapshot.objects[0].state == "idle"
    kinds = [
        message.kind for _topic, message in published if isinstance(message, TouchEvent)
    ]
    assert kinds == ["touch", "release"]


def test_name_result_is_stored_and_a_failure_retries_once() -> None:
    database, published = _database()
    det = _detection()
    image = _image()
    _settle(database, det, image)
    database.handle_name(NameResult(40.0, 1, "Heinz ketchup", True))
    named = database.handle_frame(_frame(40, 40.0, [det], image=image))
    assert named.objects[0].name == "Heinz ketchup"
    assert (
        len(
            [
                message
                for _topic, message in published
                if isinstance(message, NameRequest)
            ]
        )
        == 1
    )

    failed, failed_published = _database()
    _settle(failed, det, image)
    failed.handle_name(NameResult(41.0, 1, "", False))
    failed.handle_name(NameResult(42.0, 1, "", False))
    retries = [
        message
        for _topic, message in failed_published
        if isinstance(message, NameRequest)
    ]
    assert len(retries) == 2
    assert retries[1].crop_jpeg.startswith(b"\xff\xd8")
    still_unnamed = failed.handle_frame(_frame(42, 42.0, [det], image=image))
    assert still_unnamed.objects[0].name == ""


def test_touched_object_removed_while_covered_publishes_release() -> None:
    database, published = _database()
    box = (100, 80, 220, 300)
    det = _detection(box=box)
    _settle(database, det)
    hand = _hand_on(box)
    ts = STABLE_FRAMES * 0.2
    for index in range(TOUCH_ENTER_FRAMES):
        database.handle_frame(_frame(10 + index, ts, [det], hands=[hand]))
        ts += 0.2
    last_seen = ts - 0.2
    frame_id = 20
    while ts - last_seen < LOST_KEEP_SECONDS + 0.2:
        snapshot = database.handle_frame(_frame(frame_id, ts, [], hands=[hand]))
        frame_id += 1
        ts += 0.2
    assert snapshot.objects == []
    events = [message for topic, message in published if topic == "TouchEvent"]
    assert [event.kind for event in events] == ["touch", "release"]
    assert events[1].object_id == 1
    assert events[1].box == box


def test_untouched_object_removed_publishes_no_touch_event() -> None:
    database, published = _database()
    _settle(database, _detection())
    database.handle_frame(_frame(10, STABLE_FRAMES * 0.2 + LOST_KEEP_SECONDS, []))
    assert not any(topic == "TouchEvent" for topic, _message in published)


def test_holding_one_object_does_not_rename_its_neighbour() -> None:
    database, _published = _database()
    ketchup_box = (100, 100, 200, 300)
    mug_box = (190, 120, 300, 300)
    ketchup = _detection(1, "bottle", ketchup_box)
    mug = _detection(2, "cup", mug_box)
    for index in range(STABLE_FRAMES):
        database.handle_frame(_frame(index, index * 0.2, [ketchup, mug]))
    database.handle_name(NameResult(1.0, 1, "Heinz ketchup", True))
    database.handle_name(NameResult(1.0, 2, "blue mug", True))
    grip = Hand("right", (150, 200), (150, 180), (120, 120, 260, 300))
    ts = 1.2
    for index in range(TOUCH_ENTER_FRAMES):
        database.handle_frame(_frame(10 + index, ts, [ketchup, mug], hands=[grip]))
        ts += 0.2
    moved = _detection(1, "bottle", (220, 100, 320, 300))
    carry = Hand("right", (270, 200), (270, 180), (200, 110, 330, 300))
    snapshot = database.handle_frame(_frame(20, ts, [moved, mug], hands=[carry]))
    by_id = {item.object_id: item for item in snapshot.objects}
    assert by_id[1].name == "Heinz ketchup"
    assert by_id[1].state == "held"
    assert by_id[2].name == "blue mug"
    assert by_id[2].state != "held"
