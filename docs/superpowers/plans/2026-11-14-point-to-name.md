# Point-to-Name Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speak an object's name when the wearer **points at it** with one or more extended fingers, instead of when a fingertip lands on it.

**Architecture:** `vision/` already gets all 21 MediaPipe hand landmarks but only publishes the thumb and index tips. It will also publish the full 21 points on `Hand` as a new defaulted field. A new pure module, `scene/pointing.py`, decides which fingers are extended and casts a 2D ray from each one to find the first object box it hits. `scene/touch.py` uses that result to start an episode. The rest of the pipeline stays as it is: same `TouchEvent(kind="touch")`, same audio, storage and dashboard. "Touch" now means "pointed at" in this event.

**Tech Stack:** Python 3.11, MediaPipe Hands landmarks, pytest, ruff. No new dependencies.

**Spec:** `SPEC.md` sections 4.3, 4.6, 5 (`FrameResult.hands`) and 9, as updated in Task 1. There is no separate design doc: the user skipped the design questions and asked to go straight to a plan. The design decisions below are the spec for this work.

**Branch:** `pointing-trigger` (already created from `main` at `94abe6e`).

**Authority:** The user explicitly overrode the person-to-person folder ownership rule for this work. This branch edits `contracts/`, `config/`, `SPEC.md`, `vision/`, `scene/`, `fakes/vision/` and `tests/`. Teammates must be told in `DEVLOG.md` before merging.

---

## Packages, models and plugins required

**Nothing new is required.** Everything this plan uses is already pinned in the repo and already installed by `python scripts/install_dependencies.py`:

| What | Already pinned / present | Used for |
|---|---|---|
| `mediapipe==0.10.21` | `requirements.txt` | The 21 hand landmarks. Vision already computes them and this plan only publishes them |
| `vision/models/hand_landmarker.task` | Downloaded by `scripts/setup_models.py` (git-ignored) | MediaPipe hand model, unchanged |
| `ultralytics==8.4.212`, `yolo11s.pt` | `requirements-vision.txt`, `vision/models/` | Object boxes, unchanged |
| `numpy==1.26.4`, `opencv-contrib-python==4.11.0.86` | `requirements.txt` | Drawing the scripted pointing hand in `fakes/vision/` |
| Python stdlib `math` | n/a | Ray and box geometry in `scene/pointing.py`. The geometry is a few lines of arithmetic, so no geometry library (shapely, etc.) is added |
| `pytest==9.2.0`, `ruff==0.17.5` | `requirements.txt` | Tests and lint |

- **No new MediaPipe model.** MediaPipe's Gesture Recognizer (`gesture_recognizer.task`) has a built-in "Pointing_Up" gesture, but it was rejected for three reasons. It only recognises one fixed pose, not "one or more fingers". It gives no direction to cast a ray along. And it would be a second model on the frame path.
- **No Claude Code plugins or MCP servers** are needed to build or run this. The skills used to carry out the plan (`superpowers:subagent-driven-development` or `superpowers:executing-plans`) are already installed. Context7 lookups aren't needed either, because the plan relies only on landmark indices vision already reads (MediaPipe Hands: 0 wrist, 1–4 thumb, 5–8 index, 9–12 middle, 13–16 ring, 17–20 pinky).
- **If any of this changes** (for example, the real camera shows landmarks too noisy and a smoothing package is wanted), AGENTS.md rule 8 applies: pin the version in the requirements file and note it in `DEVLOG.md` so teammates reinstall.

## Design decisions (my calls; review these first)

1. **Which fingers count.** These four fingers count: index (MediaPipe landmarks MCP 5, PIP 6, tip 8), middle (9, 10, 12), ring (13, 14, 16) and pinky (17, 18, 20). The **thumb is excluded**, because it sticks out sideways in most hand poses and would cast rays at random objects. "One or more fingers" means any one of these four is enough, and each extended finger casts its own ray.
2. **"Extended" test.** A finger is extended when `dist(wrist, tip) > POINT_EXTENDED_RATIO * dist(wrist, pip)`, with the wrist at landmark 0 and `POINT_EXTENDED_RATIO = 1.1`. A curled finger folds its tip back toward the wrist, so the tip ends up closer to the wrist than the PIP joint. This is the only new threshold.
3. **Ray.** Each ray starts at the fingertip and runs in the direction MCP → tip, normalised. MCP → tip is steadier than PIP → tip, because the joints are spread further apart. The ray runs to the edge of the frame, with no maximum length.
4. **What it hits.** The hit test uses the same 10%-shrunk box as today (`BOX_SHRINK_FRACTION`). If several boxes are hit, the one with the **smallest distance along the ray** wins, i.e. the first one hit. Ties go to the lower `object_id`. A fingertip that sits inside a shrunk box counts as distance 0, so pointing at something you're touching still works. Objects in state `new` cannot be pointed at (unchanged rule).
5. **What starts an announcement.** For a hand **with** landmarks, only pointing can move an object from open to touching; a fingertip inside a box without an extended finger aimed at it (a grasp) does not. For a hand **without** landmarks (old recordings, tests, any fake that hasn't been updated), the old fingertip-inside test is used unchanged. This keeps every existing test and the scripted fakes working.
6. **What keeps an episode open.** Once an object is `touching` or `held`, both pointing at it **and** a fingertip inside its box count as "on". Without this, picking an object up (fingers wrap around it and stop being extended) would release it after 0.6 s and break the held logic in section 4.6.
7. **Timing is unchanged.** It takes 2 frames (0.4 s) of pointing to announce and 3 frames (0.6 s) without pointing to release. Pointing again announces again, and there is still no cooldown.
8. **Messages and names stay the same.** `TouchEvent.kind` stays `touch`/`release`, `SceneObject.state` stays `touching`, and audio, storage and the dashboard are not touched. Renaming these would ripple through four modules and the database for no change in behaviour.
9. **Contract change is additive.** `Hand.landmarks: list[Point]` is added last with `field(default_factory=list)`, so every existing `Hand(side, thumb_tip, index_tip, box)` call still works. A list with any length other than 21 is treated as "no landmarks".
10. **Speech default.** Audio's `announce_touches=True` (current code) stays. `SPEC.md` sections 1 and 4.8 still say "question-only, off by default", which contradicts the code; Task 1 makes them match the code.

## Global Constraints

- Python 3.11, type hints on every function, one short docstring per public function (AGENTS.md rule 11).
- Thresholds come from `config/thresholds.py` only. `tests/test_contracts.py::test_config_matches_spec_section_9` requires config and SPEC section 9 to match exactly, so both change together.
- `tests/test_contracts.py` parses SPEC section 5, so the `Hand` field list in the test and the SPEC text change together.
- Coordinates are pixels in the 640 × 360 processed frame, origin top-left.
- No network, database or sleep on the frame path. Pointing is pure arithmetic over at most 2 hands × 4 fingers × N objects per frame.
- No copy may call this a safety device.
- Logging uses the module folder name as the logger name; no `print` outside `fakes/` and tests.

## Review Focus

1. **Open palm.** All four fingers are extended, so up to 4 rays may hit up to 4 objects at once, and each starts its own episode. Expected: the scene makes no attempt to throttle this. Audio's one-item queue keeps the newest, so the wearer hears one or two names, not four queued ones. The test pins that each finger marks at most one object (Task 3).
2. **Sweeping finger.** A finger moving across several objects in one frame each marks nothing until it has stayed 2 frames on one object. Expected: no announcement for an object passed over in a single frame (Task 4 test).
3. **Bad landmark data.** Landmarks may have the wrong length (not 21), MCP may equal tip (a zero-length finger), or landmarks may sit at the clamped frame edge. Expected: no crash and no ray for that finger, and a wrong-length list falls back to the fingertip test (Task 3 tests).
4. **Grasp versus point.** A hand gripping an object, with fingertips inside its box and fingers curled, must not announce it. Once it has been announced by pointing, it must stay touching or held while gripped (Task 4 tests).
5. **Ray hits a box behind the finger.** A box behind the fingertip, against the pointing direction, must not count (Task 3 test).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `contracts/messages.py` | Modify `Hand` | Add `landmarks: list[Point] = field(default_factory=list)` |
| `config/thresholds.py` | Modify | Add `POINT_EXTENDED_RATIO = 1.1  # scene` and to `__all__` |
| `SPEC.md` | Modify §1, §3.2, §4.3, §4.6, §4.8, §5, §9 | Describe pointing; fix speech default text |
| `tests/test_contracts.py` | Modify | `Hand` entry fields include `landmarks` |
| `vision/vision.py` | Modify `tracked_hands` (lines 117–140) | Pass all 21 points as `landmarks` |
| `tests/test_vision_p1.py` | Modify | Assert 21 landmarks published |
| `scene/pointing.py` | **Create** | Pure functions: finger extension, ray casting, pointed ids |
| `tests/test_pointing.py` | **Create** | Unit tests for `scene/pointing.py` |
| `scene/touch.py` | Modify `_on_ids`, `step_touch`, `_advance*` | Use pointing to start an episode; pointing or fingertip to keep it open |
| `tests/test_touch.py` | Modify (add tests only) | Episode behaviour with pointing hands |
| `fakes/vision/fake_vision.py` | Modify `scripted_frame` | Scripted hand points at the bottle from outside its box |
| `DEVLOG.md` | Append entry | What changed, tests, teammate notice |

---

### Task 1: Contract, threshold and spec

**Files:**
- Modify: `contracts/messages.py:25-32`
- Modify: `config/thresholds.py` (constant + `__all__`)
- Modify: `SPEC.md` sections 1, 3.2 step 5, 4.3, 4.6, 4.8, 5 (`FrameResult` hands row), 9
- Test: `tests/test_contracts.py:157-170`

**Interfaces:**
- Produces: `Hand(side, thumb_tip, index_tip, box, landmarks=[])`, where `landmarks: list[Point]` holds 21 points in MediaPipe order, or is empty. `config.thresholds.POINT_EXTENDED_RATIO: float = 1.1`.

- [ ] **Step 1: Update the failing test.** In `test_entry_fields_match_spec`, change the `Hand` row to `["side", "thumb_tip", "index_tip", "box", "landmarks"]`. Add:

```python
def test_hand_landmarks_default_empty() -> None:
    """Hands built without landmarks start with their own empty list."""
    a = Hand("right", (1.0, 1.0), (2.0, 2.0), (0.0, 0.0, 3.0, 3.0))
    b = Hand("left", (1.0, 1.0), (2.0, 2.0), (0.0, 0.0, 3.0, 3.0))
    a.landmarks.append((5.0, 5.0))
    assert b.landmarks == []
```

- [ ] **Step 2: Run it.** `pytest tests/test_contracts.py -v`. Expected: FAIL on the field list and on `landmarks` missing.
- [ ] **Step 3: Add the field** to `Hand` as the last field, `landmarks: list[Point] = field(default_factory=list)  # 21 MediaPipe points, or empty`.
- [ ] **Step 4: Add the threshold.** Add `POINT_EXTENDED_RATIO = 1.1  # scene` after `HELD_MERGE_IOU`, and add it to `__all__` in alphabetical position.
- [ ] **Step 5: Update SPEC.md.**
  - §1: the speaker says what the wearer **points at**. Object names are spoken automatically on point (audio `announce_touches`, on by default), and questions still work independently.
  - §3.2 step 5: "The touch detector casts a ray from each extended finger. When one lands on an object it publishes a `TouchEvent`."
  - §4.3: also report all 21 landmarks per hand.
  - §4.6: rewrite the first two paragraphs per Design decisions 1–6. Keep the transition table, changing the first row's condition to "Pointed at for 2 consecutive processed frames (0.4 s)". Add a line saying `touch`/`touching` names are kept for compatibility and now mean "pointed at".
  - §4.8: priority-2 row becomes "Spoken object name (on by default; `announce_touches=False` silences it)". Fix the first bullet to match.
  - §5 `FrameResult.hands` row: append "`landmarks` (21 `x, y` points in MediaPipe order, or empty)".
  - §9: add the row `| POINT_EXTENDED_RATIO | 1.1 | scene |` after `HELD_MERGE_IOU`.
- [ ] **Step 6: Run** `pytest tests/test_contracts.py -v`. Expected: all PASS, including `test_config_matches_spec_section_9` and `test_message_fields_match_spec`.
- [ ] **Step 7: Run the full suite** with `pytest -q`. Expected: the same pass count as `main` plus 1 new test. No other test builds `Hand` with keywords that clash with the new field.
- [ ] **Step 8: Commit** with `git commit -am "contracts: add Hand.landmarks and POINT_EXTENDED_RATIO for pointing"`, adding the attribution footer.

---

### Task 2: Vision publishes landmarks

**Files:**
- Modify: `vision/vision.py:139`
- Test: `tests/test_vision_p1.py:72-86`

**Interfaces:**
- Consumes: `Hand.landmarks` (Task 1).
- Produces: each real `Hand` carries `landmarks` = the same 21 clamped points the box is computed from.

- [ ] **Step 1: Add the assertion** in the existing test around line 84: `assert len(result.hands[0].landmarks) == 21` and `assert result.hands[0].landmarks[8] == result.hands[0].index_tip`.
- [ ] **Step 2: Run** `pytest tests/test_vision_p1.py -v`. Expected: FAIL (`landmarks` is empty).
- [ ] **Step 3: Change** the append to `Hand(side, points[4], points[8], box, landmarks=points)`.
- [ ] **Step 4: Run** `pytest tests/test_vision_p1.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** with `"vision: publish all 21 hand landmarks"`.

---

### Task 3: `scene/pointing.py`, pure pointing geometry

**Files:**
- Create: `scene/pointing.py`
- Create: `tests/test_pointing.py`, `tests/pointing_helpers.py`

**Interfaces:**
- Consumes: `Hand`, `Box`, `Point` from `contracts.messages`; `BOX_SHRINK_FRACTION`, `POINT_EXTENDED_RATIO` from `config.thresholds`.
- Produces:
  - `FINGERS: tuple[tuple[int, int, int], ...] = ((5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20))`, giving (mcp, pip, tip) for index, middle, ring and pinky; and `WRIST = 0`, `LANDMARK_COUNT = 21`.
  - `has_landmarks(hand: Hand) -> bool`: True when `len(hand.landmarks) == LANDMARK_COUNT`.
  - `finger_rays(hand: Hand) -> list[tuple[Point, Point]]`: (origin = tip, unit direction) for each extended finger. Empty when there are no landmarks. Skips any finger whose MCP → tip length is 0.
  - `ray_box_distance(origin: Point, direction: Point, box: Box) -> float | None`: distance along the ray to the **shrunk** box; 0.0 when the origin is inside; None on a miss or a degenerate shrunk box.
  - `pointed_ids(boxes: list[tuple[int, Box]], hands: list[Hand]) -> set[int]`: for each ray, the id with the smallest distance (ties go to the lower id), unioned over all rays.

The shrink must match `scene/touch.py::_contains_shrunk` exactly. Put a private `_shrink(box: Box) -> Box | None` in `pointing.py`; Task 4 may reuse it from there.

`ray_box_distance` uses the slab method, which the signature doesn't fully determine:

```python
# per axis a in (x, y): if |d_a| < 1e-9, origin_a must lie in [lo_a, hi_a] else miss;
# otherwise t1=(lo_a-o_a)/d_a, t2=(hi_a-o_a)/d_a, tmin=max(tmin,min(t1,t2)), tmax=min(tmax,max(t1,t2))
# start tmin=0.0, tmax=inf; miss if tmin > tmax; return tmin
```

**Test helper** (create `tests/pointing_helpers.py`, shared with Task 4): `pointing_hand(wrist: Point, toward: Point, extended: tuple[int, ...] = (0,)) -> Hand` builds 21 landmarks. Each finger listed in `extended` (an index into `FINGERS`) is laid out in a straight line from the wrist toward `toward`: MCP at 40 px, PIP at 60 px, tip at 85 px. Every other finger is curled, with MCP at 40 px, PIP at 55 px and tip at 30 px along the same line. The thumb sits at the wrist plus (−20, 0). `index_tip`/`thumb_tip` are set from landmarks 8 and 4, and `box` is the bounding box of the landmarks.

- [ ] **Step 1: Write the failing tests** in `tests/test_pointing.py`:

```python
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
    hand = pointing_hand(wrist=(300.0, 170.0), toward=(600.0, 170.0))  # pointing right, bottle is left
    assert pointed_ids([(1, BOTTLE)], [hand]) == set()

def test_two_fingers_can_mark_two_objects() -> None:
    # build two hands, one aimed at each box; union is both ids
    ...  # assert == {1, 2}

def test_each_finger_marks_at_most_one_object() -> None:
    hand = pointing_hand(wrist=(400.0, 340.0), toward=(160.0, 170.0), extended=(0, 1, 2, 3))
    assert len(pointed_ids([(1, BOTTLE), (2, CUP)], [hand])) <= len(finger_rays(hand))

def test_fingertip_inside_box_is_distance_zero() -> None:
    assert ray_box_distance((160.0, 170.0), (1.0, 0.0), BOTTLE) == 0.0

def test_wrong_landmark_count_means_no_landmarks() -> None:
    hand = Hand("right", (1.0, 1.0), (2.0, 2.0), (0.0, 0.0, 3.0, 3.0), landmarks=[(1.0, 1.0)] * 20)
    assert not has_landmarks(hand) and finger_rays(hand) == []

def test_zero_length_finger_is_skipped() -> None:
    # all 21 landmarks at the same point: no crash, no rays
    hand = Hand("right", (5.0, 5.0), (5.0, 5.0), (4.0, 4.0, 6.0, 6.0), landmarks=[(5.0, 5.0)] * 21)
    assert finger_rays(hand) == []

def test_degenerate_box_is_never_hit() -> None:
    assert ray_box_distance((0.0, 0.0), (1.0, 0.0), (10.0, 0.0, 10.0, 0.0)) is None
```

(Write `test_two_fingers_can_mark_two_objects` concretely, with two `pointing_hand` calls aimed at the centre of each box.)

- [ ] **Step 2: Run** `pytest tests/test_pointing.py -v`. Expected: FAIL (`ModuleNotFoundError: scene.pointing`).
- [ ] **Step 3: Implement** `scene/pointing.py` with the signatures above and a module docstring. Use `math.hypot` for distances. No logging is needed (pure functions on the frame path).
- [ ] **Step 4: Run** `pytest tests/test_pointing.py -v`. Expected: all PASS.
- [ ] **Step 5: Run** `ruff check scene/pointing.py tests/test_pointing.py`. Expected: clean.
- [ ] **Step 6: Commit** with `"scene: add finger-ray pointing geometry"`.

---

### Task 4: Touch machine uses pointing

**Files:**
- Modify: `scene/touch.py`, specifically `step_touch` (line 60), `_on_ids` (line 152), and `_advance`, `_advance_open`, `_advance_touching`, `_advance_held` (lines 222–318)
- Test: `tests/test_touch.py` (append tests; do not change existing ones)

**Interfaces:**
- Consumes: `has_landmarks`, `pointed_ids` from `scene.pointing` (Task 3).
- Produces: `step_touch(tracks, hands, ts) -> TouchStep`, whose signature and return type are unchanged. `scene/database.py` needs no change.

**Behaviour to implement** (Design decisions 5–6):
- Split hands into `legacy = [h for h in hands if not has_landmarks(h)]` and `rich = [h for h in hands if has_landmarks(h)]`.
- `tipped = _on_ids(tracks, hands)`: the existing fingertip logic, over **all** hands.
- `start = _on_ids(tracks, legacy) | pointed_ids(candidate boxes, rich)`, where the candidate boxes are `(track.object_id, track.box)` for tracks passing `_is_candidate`.
- `keep = start | tipped`.
- When calling `_advance`, pass `on = id in start` for tracks in phase `open`, and `on = id in keep` for tracks in `touching`/`held`.
- `_merge_held` and `_neighbours` are unchanged.

- [ ] **Step 1: Write the failing tests** in `tests/test_touch.py`. Import it with `from pointing_helpers import pointing_hand` (Task 3; `tests/` has no `__init__.py`, so pytest puts `tests/` on `sys.path`). Use `_BOTTLE` and a wrist at `(400.0, 340.0)` aimed at `(160.0, 170.0)`.

```python
def test_pointing_two_frames_announces_once() -> None:
    steps = _run(_track(), [point_at_bottle], frames=10, ts=1.0)
    kinds = [e.kind for s in steps for e in s.events]
    assert kinds == ["touch"]
    assert steps[1].tracks[0].state == "touching"

def test_single_frame_point_does_not_announce() -> None:
    # frame1 point, frame2 hand pointing elsewhere, frame3 point, frame4 elsewhere
    ...  # assert no events

def test_stop_pointing_releases_after_exit_frames() -> None:
    # 2 frames pointing -> touch; then TOUCH_EXIT_FRAMES frames with hand pointing away -> one release
    ...

def test_repoint_announces_again() -> None:
    # point 2, away 3, point 2 -> kinds == ["touch", "release", "touch"]
    ...

def test_grasp_without_pointing_does_not_announce() -> None:
    # rich hand, all fingers curled, index_tip/thumb_tip set inside _BOTTLE
    ...  # 10 frames -> no events

def test_grasp_keeps_pointed_object_touching() -> None:
    # 2 frames pointing -> touch; then 5 frames of curled hand with tips inside _BOTTLE -> no release
    ...

def test_new_object_cannot_be_pointed_at() -> None:
    steps = _run(_track(state="new"), [point_at_bottle], frames=5, ts=1.0)
    assert all(not s.events for s in steps)

def test_legacy_hand_without_landmarks_still_touches() -> None:
    steps = _run(_track(), [_hand(_TIP)], frames=2, ts=1.0)
    assert [e.kind for e in steps[1].events] == ["touch"]
```

Write each `...` test with explicit frame loops and exact expected `kinds` lists. Use `TOUCH_ENTER_FRAMES` and `TOUCH_EXIT_FRAMES` from config rather than literal 2 and 3.

- [ ] **Step 2: Run** `pytest tests/test_touch.py -v`. Expected: the new pointing tests FAIL. The existing 17 tests and `test_legacy_hand_without_landmarks_still_touches` PASS.
- [ ] **Step 3: Implement** the behaviour above in `scene/touch.py`. Update the module docstring to "Touch state machine. An extended finger pointing at an object starts contact; pointing or a fingertip keeps it."
- [ ] **Step 4: Run** `pytest tests/test_touch.py tests/test_scene.py tests/test_pointing.py -v`. Expected: all PASS.
- [ ] **Step 5: Run** `ruff check scene tests`. Expected: clean.
- [ ] **Step 6: Commit** with `"scene: announce on pointing instead of fingertip contact"`.

---

### Task 5: Fake vision points instead of touching

**Files:**
- Modify: `fakes/vision/fake_vision.py:34-41`
- Test: `tests/test_fake_start_order.py` / `tests/test_app_p1.py` (existing; run them, no edits expected)

**Interfaces:**
- Consumes: `Hand.landmarks` (Task 1), and the same 21-point layout as the `pointing_hand` helper.

- [ ] **Step 1: Replace the scripted hand** for frames 10–24 of each cycle with a hand **outside** the bottle box. The wrist is at `(290.0, 340.0)`, the index finger is extended toward the bottle centre `(170.0, 187.5)`, and the other fingers are curled, built with landmarks in the same layout as Task 3's helper. Put a small `_pointing_hand_landmarks(wrist: Point, toward: Point) -> list[Point]` inside `fake_vision.py`; fakes may not import from `tests/`. Draw the hand as a filled polyline or circles on the image so the dashboard feed shows it. Thumb and index tips come from landmarks 4 and 8, and the box from the landmarks.
- [ ] **Step 2: Check the geometry** in a Python REPL: `pointed_ids([(1, (120,75,220,300)), (2, (320,155,425,292))], [scripted_frame(12, 0.0).hands[0]]) == {1}`. Expected: True (the cup is not hit).
- [ ] **Step 3: Run** `pytest tests/test_fake_start_order.py tests/test_app_p1.py -v`. Expected: PASS.
- [ ] **Step 4: Run the app on fakes** in the background with `python -m app --fake vision`. Watch the logs for about 15 s, then check that a `TouchEvent` with kind `touch` for object 1 appears once per cycle and that audio logs speaking "bottle" (or the fake name). Stop the process afterwards.
- [ ] **Step 5: Commit** with `"fakes: scripted hand points at the bottle"`.

---

### Task 6: Log, full verification, push

**Files:**
- Modify: `DEVLOG.md` (append an entry in that file's format)

- [ ] **Step 1: Run the full suite** with `pytest -q`. Expected: all pass (main's count + new tests), 1 skipped (live DB).
- [ ] **Step 2: Run lint** with `ruff check .`. Expected: clean, or only warnings that were already present on `main`.
- [ ] **Step 3: Append a DEVLOG entry** dated 2026-11-14 with these parts:
  - **Changed:** pointing replaces touch as the trigger, plus the design decisions in brief.
  - **Tested:** the exact commands and counts.
  - **Teammates need to know:** the shared `contracts/`, `config/` and `SPEC.md` changed with ownership overridden by the user. `Hand.landmarks` is additive. Event and state names are unchanged. The real camera has not been verified yet. The dashboard still says "touching", and drawing rays would be a follow-up.
  - **Agent:** Claude Code.
- [ ] **Step 4: Commit** with `"devlog: pointing trigger"`.
- [ ] **Step 5: Push** with `git push -u origin pointing-trigger`. Do not open a PR or merge to `main` without the user's go-ahead.

---

## Not in this plan (follow-ups)

- Drawing finger rays on the dashboard video overlay (`dashboard/video.py`) to tune pointing live.
- Renaming "touch"/"touching" in UI copy, storage columns and the dashboard to "point".
- A longer dwell for pointing (a separate `POINT_ENTER_FRAMES`), if sweeping a finger across the table announces too much in real use.
- Testing on the real camera: MediaPipe landmark noise on a tilted head-mounted camera may need `POINT_EXTENDED_RATIO` tuned.
