"""Touch table from SPEC.md section 4.6."""

import math
from dataclasses import replace

from pointing_helpers import gripping_hand, pointing_hand

from config.thresholds import (
    BOX_SHRINK_FRACTION,
    HELD_LOST_SECONDS,
    HELD_MERGE_IOU,
    HELD_MOVE_FRACTION,
    PROCESS_WIDTH,
    TOUCH_ENTER_FRAMES,
    TOUCH_EXIT_FRAMES,
)
from contracts.messages import Box, Hand
from scene.touch import TouchStep, TouchTrack, release_on_removal, step_touch

_BOTTLE = (100, 60, 220, 280)
_TIP = (160.0, 170.0)
_AWAY = (2.0, 2.0)


def _track(
    object_id: int = 1,
    class_label: str = "bottle",
    name: str = "",
    state: str = "idle",
    box: Box | None = None,
    detected: bool = True,
    phase: str = "open",
    on_frames: int = 0,
    off_frames: int = 0,
    anchor_cx: float | None = None,
    anchor_cy: float | None = None,
    lost_since_ts: float | None = None,
    hand_clear_frames: int = 0,
) -> TouchTrack:
    return TouchTrack(
        object_id=object_id,
        class_label=class_label,
        name=name,
        state=state,
        box=_BOTTLE if box is None else box,
        detected=detected,
        phase=phase,
        on_frames=on_frames,
        off_frames=off_frames,
        anchor_cx=anchor_cx,
        anchor_cy=anchor_cy,
        lost_since_ts=lost_since_ts,
        hand_clear_frames=hand_clear_frames,
    )


def _hand(
    index: tuple[float, float],
    thumb: tuple[float, float] | None = None,
    box: Box | None = None,
) -> Hand:
    return Hand(
        side="right",
        thumb_tip=index if thumb is None else thumb,
        index_tip=index,
        box=box if box is not None else (1, 1, 12, 12),
    )


def _run(
    track: TouchTrack,
    hands: list[Hand],
    frames: int,
    ts: float,
) -> list[TouchStep]:
    steps: list[TouchStep] = []
    current = track
    for _ in range(frames):
        step = step_touch([current], hands, ts)
        steps.append(step)
        current = step.tracks[0]
    return steps


def _center(box: Box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _shift(box: Box, dx: float) -> Box:
    return (box[0] + dx, box[1], box[2] + dx, box[3])


def _iou(a: Box, b: Box) -> float:
    inter_w = min(a[2], b[2]) - max(a[0], b[0])
    inter_h = min(a[3], b[3]) - max(a[1], b[1])
    if inter_w <= 0.0 or inter_h <= 0.0:
        return 0.0
    inter = inter_w * inter_h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _same_size_shifted(box: Box, target_iou: float) -> Box:
    width = box[2] - box[0]
    height = box[3] - box[1]
    inter = target_iou * 2.0 * width * height / (1.0 + target_iou)
    dx = width - inter / height
    return (box[0] + dx, box[1], box[2] + dx, box[3])


def test_idle_becomes_touching_after_enter_frames() -> None:
    original = _track(name="Heinz ketchup")
    hand = _hand(_TIP, thumb=_AWAY)
    steps = _run(original, [hand], TOUCH_ENTER_FRAMES, 10.0)

    assert original.state == "idle"
    assert original.phase == "open"
    assert original.on_frames == 0
    assert steps[-1].tracks[0] is not original
    for index, step in enumerate(steps[:-1]):
        assert step.events == []
        assert step.tracks[0].state == "idle"
        assert step.tracks[0].phase == "open"
        assert step.tracks[0].on_frames == index + 1

    last = steps[-1]
    assert len(last.events) == 1
    event = last.events[0]
    assert event.kind == "touch"
    assert event.ts == 10.0
    assert event.object_id == 1
    assert event.class_label == "bottle"
    assert event.name == "Heinz ketchup"
    assert event.box == _BOTTLE
    assert event.neighbours == []
    assert last.tracks[0].state == "touching"
    assert last.tracks[0].phase == "touching"
    assert last.tracks[0].on_frames == TOUCH_ENTER_FRAMES
    assert last.tracks[0].anchor_cx == _TIP[0]
    assert last.tracks[0].anchor_cy == _TIP[1]
    assert last.dropped_ids == []


def test_lost_becomes_touching_after_enter_frames() -> None:
    track = _track(state="lost", detected=False, phase="open", name="mug")
    hand = _hand(_AWAY, thumb=_TIP)
    steps = _run(track, [hand], TOUCH_ENTER_FRAMES, 4.0)

    for step in steps[:-1]:
        assert step.events == []
        assert step.tracks[0].state == "lost"
        assert step.tracks[0].phase == "open"
    last = steps[-1]
    assert [event.kind for event in last.events] == ["touch"]
    assert last.tracks[0].state == "touching"
    assert last.tracks[0].phase == "touching"
    assert last.tracks[0].detected is False


def test_staying_on_does_not_emit_a_second_touch() -> None:
    hand = _hand(_TIP, thumb=_AWAY)
    entered = _run(_track(name="Heinz ketchup"), [hand], TOUCH_ENTER_FRAMES, 1.0)
    extra = _run(
        entered[-1].tracks[0],
        [hand],
        TOUCH_ENTER_FRAMES + TOUCH_EXIT_FRAMES,
        1.0,
    )
    assert [event.kind for event in entered[-1].events] == ["touch"]
    assert all(step.events == [] for step in extra)
    assert extra[-1].tracks[0].phase == "touching"
    assert extra[-1].tracks[0].state == "touching"


def test_release_waits_for_exit_frames_and_a_gap_does_not_release() -> None:
    on_hand = _hand(_TIP, thumb=_AWAY)
    away = _hand(_AWAY)
    entered = _run(_track(), [on_hand], TOUCH_ENTER_FRAMES, 2.0)
    gap = step_touch([entered[-1].tracks[0]], [away], 2.0)
    assert gap.events == []
    assert gap.tracks[0].phase == "touching"
    assert gap.tracks[0].state == "touching"
    assert gap.tracks[0].off_frames == 1

    back = step_touch([gap.tracks[0]], [on_hand], 2.0)
    assert back.events == []
    assert back.tracks[0].phase == "touching"
    assert back.tracks[0].off_frames == 0

    current = back.tracks[0]
    for _ in range(TOUCH_EXIT_FRAMES - 1):
        step = step_touch([current], [away], 2.0)
        assert step.events == []
        assert step.tracks[0].phase == "touching"
        current = step.tracks[0]
    last = step_touch([current], [away], 2.0)
    assert [event.kind for event in last.events] == ["release"]
    assert last.events[0].box == _BOTTLE
    assert last.tracks[0].phase == "open"
    assert last.tracks[0].state == "idle"
    assert last.tracks[0].anchor_cx is None
    assert last.tracks[0].off_frames == 0


def test_retouch_emits_another_touch_without_cooldown() -> None:
    on_hand = _hand(_TIP, thumb=_AWAY)
    away = _hand(_AWAY)
    entered = _run(_track(name="Heinz ketchup"), [on_hand], TOUCH_ENTER_FRAMES, 6.0)
    released = _run(entered[-1].tracks[0], [away], TOUCH_EXIT_FRAMES, 6.0)
    retouched = _run(released[-1].tracks[0], [on_hand], TOUCH_ENTER_FRAMES, 6.0)
    kinds = [
        event.kind
        for step in (*entered, *released, *retouched)
        for event in step.events
    ]
    assert kinds == ["touch", "release", "touch"]
    assert retouched[-1].tracks[0].phase == "touching"
    assert retouched[-1].events[0].name == "Heinz ketchup"


def test_new_object_is_not_touchable() -> None:
    hand = _hand(_TIP, thumb=_AWAY)
    track = _track(state="new", phase="open")
    steps = _run(track, [hand], TOUCH_ENTER_FRAMES + TOUCH_EXIT_FRAMES, 3.0)
    assert all(step.events == [] for step in steps)
    assert all(step.tracks[0].state == "new" for step in steps)
    assert all(step.tracks[0].phase == "open" for step in steps)
    assert all(step.tracks[0].on_frames == 0 for step in steps)


def test_overlapping_boxes_use_distance_over_diagonal() -> None:
    # The small box is closer in pixels. Its centre is farther as a fraction
    # of its diagonal, so the large box wins the fingertip.
    small = (80, 85, 120, 115)
    large = (50, 25, 350, 275)
    tip = (116.0, 100.0)
    small_distance = math.hypot(tip[0] - 100.0, tip[1] - 100.0)
    large_distance = math.hypot(tip[0] - 200.0, tip[1] - 150.0)
    assert small_distance < large_distance

    tracks = [
        _track(object_id=1, box=small, class_label="cup"),
        _track(object_id=2, box=large, class_label="bottle"),
    ]
    result = step_touch(tracks, [_hand(tip, thumb=_AWAY)], 1.0)
    assert result.events == [] or TOUCH_ENTER_FRAMES == 1
    by_id = {track.object_id: track for track in result.tracks}
    assert by_id[1].on_frames == 0
    assert by_id[2].on_frames == 1


def test_outer_shrink_ring_is_not_on_and_center_is() -> None:
    box = (100, 40, 300, 240)
    width = box[2] - box[0]
    inset = BOX_SHRINK_FRACTION * width
    ring = (box[0] + inset / TOUCH_ENTER_FRAMES, (box[1] + box[3]) / 2.0)
    center = _center(box)
    assert box[0] < ring[0] < box[0] + inset

    missed = step_touch([_track(box=box)], [_hand(ring, thumb=_AWAY)], 1.0)
    assert missed.tracks[0].on_frames == 0
    assert missed.events == []

    hit = step_touch([_track(box=box)], [_hand(center, thumb=_AWAY)], 1.0)
    assert hit.tracks[0].on_frames == 1


def test_touching_becomes_held_only_after_the_center_moves_far_enough() -> None:
    box = (40, 30, 440, 330)
    tip = _center(box)
    hand = _hand(tip, thumb=_AWAY)
    entered = _run(
        _track(box=box, name="Heinz ketchup"), [hand], TOUCH_ENTER_FRAMES, 8.0
    )
    base = entered[-1].tracks[0]
    assert base.phase == "touching"
    assert base.anchor_cx == tip[0]
    assert base.anchor_cy == tip[1]

    limit = HELD_MOVE_FRACTION * PROCESS_WIDTH
    smaller = limit / TOUCH_ENTER_FRAMES
    stayed = step_touch([replace(base, box=_shift(box, smaller))], [hand], 8.0)
    assert stayed.events == []
    assert stayed.tracks[0].phase == "touching"
    assert stayed.tracks[0].state == "touching"

    exact = step_touch([replace(base, box=_shift(box, limit))], [hand], 8.0)
    assert exact.events == []
    assert exact.tracks[0].phase == "touching"
    assert exact.tracks[0].state == "touching"

    held = step_touch([replace(base, box=_shift(box, limit + smaller))], [hand], 8.0)
    assert held.events == []
    assert held.tracks[0].phase == "held"
    assert held.tracks[0].state == "held"
    assert held.tracks[0].anchor_cx == tip[0]
    assert held.tracks[0].anchor_cy == tip[1]


def test_covered_touch_stays_lost_until_held_seconds() -> None:
    hand = _hand(_TIP, thumb=_AWAY)
    entered = _run(_track(name="Heinz ketchup"), [hand], TOUCH_ENTER_FRAMES, 20.0)
    covered = replace(entered[-1].tracks[0], detected=False, state="lost")
    t0 = 20.0
    first = step_touch([covered], [hand], t0)
    assert first.events == []
    assert first.tracks[0].state == "lost"
    assert first.tracks[0].phase == "touching"
    assert first.tracks[0].lost_since_ts == t0

    before_ts = t0 + HELD_LOST_SECONDS - HELD_LOST_SECONDS / TOUCH_EXIT_FRAMES
    before = step_touch([first.tracks[0]], [hand], before_ts)
    assert before.events == []
    assert before.tracks[0].state == "lost"
    assert before.tracks[0].phase == "touching"

    fired = step_touch([before.tracks[0]], [hand], t0 + HELD_LOST_SECONDS)
    assert fired.events == []
    assert fired.tracks[0].state == "held"
    assert fired.tracks[0].phase == "held"


def test_held_releases_after_fingertips_stay_off() -> None:
    held = _track(
        state="held",
        phase="held",
        anchor_cx=_TIP[0],
        anchor_cy=_TIP[1],
        on_frames=TOUCH_ENTER_FRAMES,
    )
    hands = [_hand(_AWAY)]
    current = held
    for _ in range(TOUCH_EXIT_FRAMES - 1):
        step = step_touch([current], hands, 9.0)
        assert step.events == []
        current = step.tracks[0]
        assert current.phase == "held"
        assert current.state == "held"
    assert current.off_frames == TOUCH_EXIT_FRAMES - 1
    assert current.hand_clear_frames == 0

    last = step_touch([current], hands, 9.0)
    assert [event.kind for event in last.events] == ["release"]
    assert last.tracks[0].phase == "open"
    assert last.tracks[0].state == "idle"
    assert last.tracks[0].anchor_cx is None
    assert last.tracks[0].hand_clear_frames == 0


def test_held_releases_after_hands_stay_empty() -> None:
    held = _track(
        state="held",
        phase="held",
        detected=True,
        anchor_cx=_TIP[0],
        anchor_cy=_TIP[1],
    )
    current = held
    for _ in range(TOUCH_EXIT_FRAMES - 1):
        step = step_touch([current], [], 9.0)
        assert step.events == []
        current = step.tracks[0]
        assert current.phase == "held"
        assert current.state == "held"
    assert current.hand_clear_frames == TOUCH_EXIT_FRAMES - 1
    assert current.off_frames == TOUCH_EXIT_FRAMES - 1

    last = step_touch([current], [], 9.0)
    assert [event.kind for event in last.events] == ["release"]
    assert last.tracks[0].phase == "open"
    assert last.tracks[0].state == "idle"
    assert last.tracks[0].hand_clear_frames == 0
    assert last.tracks[0].off_frames == 0


def test_merge_inherits_held_name_when_hand_iou_is_high_enough() -> None:
    hand_box = (80, 80, 180, 180)
    det_box = _same_size_shifted(hand_box, (HELD_MERGE_IOU + 1.0) / 2.0)
    assert _iou(hand_box, det_box) >= HELD_MERGE_IOU
    detection = _track(
        object_id=8,
        class_label="cup",
        name="soda",
        state="new",
        box=det_box,
        off_frames=TOUCH_EXIT_FRAMES,
        hand_clear_frames=TOUCH_EXIT_FRAMES,
    )
    held = _track(
        object_id=7,
        name="Heinz ketchup",
        state="held",
        phase="held",
        detected=False,
        box=(300, 40, 420, 200),
        anchor_cx=360.0,
        anchor_cy=120.0,
        lost_since_ts=11.0,
    )
    result = step_touch([detection, held], [_hand(_AWAY, box=hand_box)], 5.0)
    assert result.events == []
    assert result.dropped_ids == [7]
    assert [track.object_id for track in result.tracks] == [8]
    heir = result.tracks[0]
    assert heir.name == "Heinz ketchup"
    assert heir.class_label == "cup"
    assert heir.phase == "held"
    assert heir.state == "held"
    assert heir.anchor_cx == 360.0
    assert heir.anchor_cy == 120.0
    assert heir.lost_since_ts == 11.0
    assert heir.off_frames == 0
    assert heir.hand_clear_frames == 0


def test_merge_does_not_happen_below_hand_iou() -> None:
    hand_box = (80, 80, 180, 180)
    det_box = _same_size_shifted(hand_box, HELD_MERGE_IOU / 2.0)
    assert _iou(hand_box, det_box) < HELD_MERGE_IOU
    detection = _track(
        object_id=8, class_label="cup", name="soda", state="new", box=det_box
    )
    held = _track(
        object_id=7,
        name="Heinz ketchup",
        state="held",
        phase="held",
        detected=False,
        box=(300, 40, 420, 200),
    )
    result = step_touch([detection, held], [_hand(_AWAY, box=hand_box)], 5.0)
    assert result.events == []
    assert result.dropped_ids == []
    assert [track.object_id for track in result.tracks] == [8, 7]
    assert result.tracks[0].name == "soda"
    assert result.tracks[0].phase == "open"
    assert result.tracks[1].phase == "held"
    assert result.tracks[1].name == "Heinz ketchup"


def test_touch_neighbours_prefer_name_and_keep_three_nearest() -> None:
    main_box = (150, 130, 250, 230)
    tip = _center(main_box)
    near = _track(
        object_id=2,
        class_label="cup",
        name="mug",
        box=(180, 200, 220, 240),
    )
    mid = _track(
        object_id=3,
        class_label="bowl",
        name="",
        box=(260, 160, 300, 200),
    )
    farther = _track(
        object_id=6,
        class_label="box",
        name="cereal",
        box=(180, 280, 220, 320),
    )
    phone = _track(
        object_id=5,
        class_label="cell phone",
        name="phone",
        box=(500, 160, 540, 200),
    )
    ghost = _track(
        object_id=4,
        name="ghost",
        state="held",
        phase="held",
        detected=False,
        box=(190, 160, 230, 200),
        anchor_cx=210.0,
        anchor_cy=180.0,
    )
    heir_box = (560, 280, 630, 350)
    heir = _track(
        object_id=7,
        class_label="cup",
        name="other",
        state="new",
        box=heir_box,
    )
    main = _track(
        object_id=1,
        name="Heinz ketchup",
        box=main_box,
        on_frames=TOUCH_ENTER_FRAMES - 1,
    )
    result = step_touch(
        [main, phone, mid, ghost, near, farther, heir],
        [_hand(tip, thumb=_AWAY, box=heir_box)],
        15.0,
    )
    assert result.dropped_ids == [4]
    assert [event.kind for event in result.events] == ["touch"]
    assert result.events[0].neighbours == ["mug", "bowl", "cereal"]
    assert "ghost" not in result.events[0].neighbours
    assert "phone" not in result.events[0].neighbours


def test_merge_never_takes_over_a_stable_object_near_the_hand() -> None:
    hand_box = (80, 80, 180, 180)
    mug_box = _same_size_shifted(hand_box, (HELD_MERGE_IOU + 1.0) / 2.0)
    assert _iou(hand_box, mug_box) >= HELD_MERGE_IOU
    mug = _track(object_id=8, class_label="cup", name="blue mug", box=mug_box)
    held = _track(
        object_id=7,
        name="Heinz ketchup",
        state="held",
        phase="held",
        box=(300, 40, 420, 200),
        anchor_cx=360.0,
        anchor_cy=120.0,
    )
    result = step_touch([mug, held], [_hand((360.0, 120.0), box=hand_box)], 5.0)
    assert result.dropped_ids == []
    by_id = {track.object_id: track for track in result.tracks}
    assert by_id[8].name == "blue mug"
    assert by_id[8].phase == "open"
    assert by_id[8].state == "idle"
    assert by_id[7].name == "Heinz ketchup"
    assert by_id[7].phase == "held"


def test_release_on_removal_only_for_objects_in_contact() -> None:
    touching = _track(object_id=1, name="Heinz ketchup", phase="touching")
    held = _track(object_id=2, name="soda", phase="held", box=(300, 40, 400, 200))
    idle = _track(
        object_id=3, class_label="cup", name="mug", box=(230, 60, 290, 120)
    )
    event = release_on_removal(touching, [idle], 9.0)
    assert event is not None
    assert event.kind == "release"
    assert event.object_id == 1
    assert event.name == "Heinz ketchup"
    assert event.box == touching.box
    assert event.neighbours == ["mug"]
    assert event.ts == 9.0
    held_event = release_on_removal(held, [], 9.0)
    assert held_event is not None and held_event.kind == "release"
    assert release_on_removal(idle, [], 9.0) is None


_POINT_AT_BOTTLE = pointing_hand(wrist=(400.0, 340.0), toward=(160.0, 170.0))
_POINT_AWAY = pointing_hand(wrist=(400.0, 340.0), toward=(600.0, 340.0))
_GRIP_BOTTLE = gripping_hand(wrist=(160.0, 250.0))  # thumb and index tips land inside _BOTTLE


def _kinds_over(track: TouchTrack, frames: list[list[Hand]]) -> tuple[list[str], TouchTrack]:
    """Run one hand list per frame and return every event kind plus the final track."""
    kinds: list[str] = []
    current = track
    for index, hands in enumerate(frames):
        step = step_touch([current], hands, 1.0 + index * 0.2)
        kinds.extend(event.kind for event in step.events)
        current = step.tracks[0]
    return kinds, current


def test_pointing_for_enter_frames_announces_once() -> None:
    kinds, track = _kinds_over(_track(), [[_POINT_AT_BOTTLE]] * 10)
    assert kinds == ["touch"]
    assert track.state == "touching"


def test_single_frame_point_does_not_announce() -> None:
    frames = [[_POINT_AT_BOTTLE], [_POINT_AWAY]] * 4
    kinds, _ = _kinds_over(_track(), frames)
    assert kinds == []


def test_stop_pointing_releases_after_exit_frames() -> None:
    frames = [[_POINT_AT_BOTTLE]] * TOUCH_ENTER_FRAMES + [[_POINT_AWAY]] * TOUCH_EXIT_FRAMES
    kinds, track = _kinds_over(_track(), frames)
    assert kinds == ["touch", "release"]
    assert track.state == "idle"


def test_repoint_announces_again() -> None:
    frames = (
        [[_POINT_AT_BOTTLE]] * TOUCH_ENTER_FRAMES
        + [[_POINT_AWAY]] * TOUCH_EXIT_FRAMES
        + [[_POINT_AT_BOTTLE]] * TOUCH_ENTER_FRAMES
    )
    kinds, _ = _kinds_over(_track(), frames)
    assert kinds == ["touch", "release", "touch"]


def test_grasp_without_pointing_does_not_announce() -> None:
    kinds, track = _kinds_over(_track(), [[_GRIP_BOTTLE]] * 10)
    assert kinds == []
    assert track.state == "idle"


def test_grasp_keeps_pointed_object_touching() -> None:
    frames = [[_POINT_AT_BOTTLE]] * TOUCH_ENTER_FRAMES + [[_GRIP_BOTTLE]] * 5
    kinds, track = _kinds_over(_track(), frames)
    assert kinds == ["touch"]
    assert track.state == "touching"


def test_new_object_cannot_be_pointed_at() -> None:
    kinds, _ = _kinds_over(_track(state="new"), [[_POINT_AT_BOTTLE]] * 5)
    assert kinds == []


def test_legacy_hand_without_landmarks_still_touches() -> None:
    kinds, _ = _kinds_over(_track(), [[_hand(_TIP)]] * TOUCH_ENTER_FRAMES)
    assert kinds == ["touch"]


def test_remote_point_at_lost_object_does_not_make_it_held() -> None:
    kinds, track = _kinds_over(_track(), [[_POINT_AT_BOTTLE]] * TOUCH_ENTER_FRAMES)
    assert kinds == ["touch"]
    track = replace(track, detected=False)
    ts = 2.0
    for _ in range(10):  # 2 s of pointing at the lost bottle from outside its box
        step = step_touch([track], [_POINT_AT_BOTTLE], ts)
        track = replace(step.tracks[0], detected=False)
        ts += 0.2
    assert ts - 2.0 > HELD_LOST_SECONDS
    assert track.phase == "touching"
    assert track.state == "lost"


def test_open_neighbour_does_not_steal_keep_fingertip() -> None:
    inner = (120.0, 200.0, 180.0, 265.0)  # holds both grip tips, centre nearer than the bottle's
    held = _track(object_id=1, phase="touching", state="touching", anchor_cx=160.0, anchor_cy=170.0)
    neighbour = _track(object_id=2, class_label="cup", box=inner)
    tracks = [held, neighbour]
    kinds: list[str] = []
    for index in range(TOUCH_EXIT_FRAMES + 2):
        step = step_touch(tracks, [_GRIP_BOTTLE], 3.0 + index * 0.2)
        kinds.extend(f"{event.object_id}:{event.kind}" for event in step.events)
        tracks = step.tracks
    assert kinds == []
    assert tracks[0].state == "touching"


def test_remote_point_after_box_movement_does_not_transfer_name() -> None:
    """Camera-relative movement must not let a remote point rename an item at the hand."""
    _, track = _kinds_over(
        _track(name="Heinz ketchup"), [[_POINT_AT_BOTTLE]] * TOUCH_ENTER_FRAMES
    )
    track = replace(track, box=_shift(track.box, 110.0))
    hand = pointing_hand(wrist=(500.0, 340.0), toward=(270.0, 170.0))
    step = step_touch([track], [hand], 2.0)
    neighbour = _track(object_id=2, class_label="cup", state="new", box=hand.box)
    step = step_touch([*step.tracks, neighbour], [hand], 2.2)
    by_id = {item.object_id: item for item in step.tracks}
    assert by_id[1].phase == "touching"
    assert by_id[1].name == "Heinz ketchup"
    assert by_id[2].phase == "open"
    assert by_id[2].name == ""
    assert step.events == []


def test_grasp_after_pointing_still_becomes_held_when_moved() -> None:
    """Requiring contact must preserve pickup after pointing with landmark-rich hands."""
    _, track = _kinds_over(_track(), [[_POINT_AT_BOTTLE]] * TOUCH_ENTER_FRAMES)
    track = replace(track, box=_shift(track.box, 110.0))
    hand = gripping_hand(wrist=(270.0, 250.0))
    step = step_touch([track], [hand], 2.0)
    assert step.tracks[0].phase == "held"
    assert step.events == []
