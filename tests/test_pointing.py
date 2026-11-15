"""Finger-ray pointing geometry from SPEC.md section 4.6."""

from pointing_helpers import pointing_hand

from contracts.messages import Hand
from scene.pointing import finger_rays, has_landmarks, pointed_ids, ray_box_distance

BOTTLE = (100.0, 60.0, 220.0, 280.0)
CUP = (320.0, 155.0, 425.0, 292.0)


def test_extended_index_pointing_at_box_from_outside() -> None:
    hand = pointing_hand(wrist=(400.0, 340.0), toward=(160.0, 170.0))
    assert pointed_ids([(1, BOTTLE)], [hand]) == {1}


def test_curled_fingers_cast_no_ray() -> None:
    hand = pointing_hand(wrist=(400.0, 340.0), toward=(160.0, 170.0), extended=())
    assert finger_rays(hand) == []
    assert pointed_ids([(1, BOTTLE)], [hand]) == set()


def test_first_box_along_ray_wins() -> None:
    near = (250.0, 200.0, 300.0, 260.0)  # between the hand and the bottle on the same line
    hand = pointing_hand(wrist=(400.0, 340.0), toward=(160.0, 170.0))
    assert pointed_ids([(1, BOTTLE), (2, near)], [hand]) == {2}


def test_box_behind_fingertip_is_ignored() -> None:
    hand = pointing_hand(wrist=(300.0, 170.0), toward=(600.0, 170.0))  # pointing right
    assert pointed_ids([(1, BOTTLE)], [hand]) == set()


def test_two_fingers_can_mark_two_objects() -> None:
    at_bottle = pointing_hand(wrist=(300.0, 340.0), toward=(160.0, 170.0), side="left")
    at_cup = pointing_hand(wrist=(470.0, 340.0), toward=(372.5, 223.5))
    assert pointed_ids([(1, BOTTLE), (2, CUP)], [at_bottle, at_cup]) == {1, 2}


def test_each_finger_marks_at_most_one_object() -> None:
    hand = pointing_hand(wrist=(400.0, 340.0), toward=(160.0, 170.0), extended=(0, 1, 2, 3))
    assert len(finger_rays(hand)) == 4
    assert len(pointed_ids([(1, BOTTLE), (2, CUP)], [hand])) <= len(finger_rays(hand))


def test_fingertip_inside_box_is_distance_zero() -> None:
    assert ray_box_distance((160.0, 170.0), (1.0, 0.0), BOTTLE) == 0.0


def test_wrong_landmark_count_means_no_landmarks() -> None:
    hand = Hand("right", (1.0, 1.0), (2.0, 2.0), (0.0, 0.0, 3.0, 3.0), landmarks=[(1.0, 1.0)] * 20)
    assert not has_landmarks(hand)
    assert finger_rays(hand) == []


def test_zero_length_finger_is_skipped() -> None:
    hand = Hand("right", (5.0, 5.0), (5.0, 5.0), (4.0, 4.0, 6.0, 6.0), landmarks=[(5.0, 5.0)] * 21)
    assert finger_rays(hand) == []


def test_degenerate_box_is_never_hit() -> None:
    assert ray_box_distance((0.0, 0.0), (1.0, 0.0), (10.0, 0.0, 10.0, 0.0)) is None


def test_ties_go_to_lower_object_id() -> None:
    hand = pointing_hand(wrist=(400.0, 340.0), toward=(160.0, 170.0))
    assert pointed_ids([(7, BOTTLE), (3, BOTTLE)], [hand]) == {3}
