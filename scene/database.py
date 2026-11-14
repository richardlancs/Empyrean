"""In-memory object list updated from each FrameResult."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from config.thresholds import LOST_KEEP_SECONDS, STABLE_FRAMES
from contracts.messages import (
    Box,
    FrameResult,
    NameResult,
    SceneObject,
    SceneSnapshot,
    TrackedObject,
)
from scene.naming import after_name_result, request_for_new_idle
from scene.touch import TouchTrack, release_on_removal, step_touch

logger = logging.getLogger("scene")

Publish = Callable[[str, object], None]


@dataclass
class _Track:
    object_id: int
    class_label: str
    name: str
    state: str
    box: Box
    last_seen_ts: float
    seen_streak: int
    stable: bool
    phase: str = "open"
    on_frames: int = 0
    off_frames: int = 0
    anchor_cx: float | None = None
    anchor_cy: float | None = None
    lost_since_ts: float | None = None
    hand_clear_frames: int = 0
    requests_sent: int = 0
    wants_name: bool = False


class SceneDatabase:
    """Tracks objects, asks for names, and publishes touch events.

    Visibility follows SPEC.md section 4.4. The first time an object becomes
    idle it publishes a NameRequest. Fingertips publish TouchEvent. A
    SceneSnapshot goes out after every frame.
    """

    def __init__(
        self,
        publish: Publish,
        stable_frames: int = STABLE_FRAMES,
        lost_keep_seconds: float = LOST_KEEP_SECONDS,
    ) -> None:
        """publish is called as publish(message class name, message)."""
        self._publish = publish
        self._stable_frames = stable_frames
        self._lost_keep_seconds = lost_keep_seconds
        self._tracks: dict[int, _Track] = {}
        self._image: object | None = None

    def handle_frame(self, frame: FrameResult) -> SceneSnapshot:
        """Apply one FrameResult and publish the messages for that frame."""
        self._image = frame.image
        detections = {det.object_id: det for det in frame.objects}
        for det in detections.values():
            track = self._tracks.get(det.object_id)
            if track is None:
                self._tracks[det.object_id] = self._start_track(det, frame.ts)
            else:
                self._refresh(track, det, frame.ts)
        self._retire_unseen(set(detections), frame.ts)
        self._apply_touch(frame)
        self._publish_name_requests(frame)
        snapshot = self._snapshot(frame)
        self._publish(type(snapshot).__name__, snapshot)
        return snapshot

    def handle_name(self, result: NameResult) -> None:
        """Store a NameResult, and publish one retry when naming failed."""
        track = self._tracks.get(result.object_id)
        if track is None:
            logger.debug("name result for unknown object %s", result.object_id)
            return
        name, sent, request = after_name_result(
            result.ts,
            track.class_label,
            track.name,
            track.requests_sent,
            track.box,
            self._image,
            result,
        )
        track.name = name
        track.requests_sent = sent
        track.wants_name = False
        if request is not None:
            self._publish(type(request).__name__, request)

    def _start_track(self, det: TrackedObject, ts: float) -> _Track:
        track = _Track(
            object_id=det.object_id,
            class_label=det.class_label,
            name="",
            state="new",
            box=det.box,
            last_seen_ts=ts,
            seen_streak=1,
            stable=False,
        )
        if track.seen_streak >= self._stable_frames:
            self._mark_idle(track)
        return track

    def _refresh(self, track: _Track, det: TrackedObject, ts: float) -> None:
        track.class_label = det.class_label
        track.box = det.box
        track.last_seen_ts = ts
        if track.state == "lost":
            self._reacquire(track)
            return
        if track.state == "new":
            track.seen_streak += 1
            if track.seen_streak >= self._stable_frames:
                self._mark_idle(track)

    def _reacquire(self, track: _Track) -> None:
        if track.stable:
            track.state = "idle"
            logger.debug("object %s -> idle", track.object_id)
            return
        track.seen_streak = 1
        track.state = "new"
        if track.seen_streak >= self._stable_frames:
            self._mark_idle(track)

    def _mark_idle(self, track: _Track) -> None:
        first = not track.stable
        track.state = "idle"
        track.stable = True
        if first:
            track.wants_name = True
        logger.debug("object %s -> idle", track.object_id)

    def _retire_unseen(self, seen: set[int], ts: float) -> None:
        removed: list[_Track] = []
        for object_id, track in list(self._tracks.items()):
            if object_id in seen:
                continue
            if ts - track.last_seen_ts >= self._lost_keep_seconds:
                del self._tracks[object_id]
                removed.append(track)
                logger.debug("removed object %s", object_id)
                continue
            if track.state != "lost":
                if not track.stable:
                    track.seen_streak = 0
                track.state = "lost"
                logger.debug("object %s -> lost", track.object_id)
        if removed:
            self._release_removed(removed, seen, ts)

    def _release_removed(
        self, removed: list[_Track], seen: set[int], ts: float
    ) -> None:
        """Publish a release for each removed object that was still in contact."""
        others = [
            _touch_track(track, track.object_id in seen)
            for track in sorted(self._tracks.values(), key=lambda item: item.object_id)
        ]
        for track in removed:
            event = release_on_removal(_touch_track(track, False), others, ts)
            if event is not None:
                self._publish(type(event).__name__, event)

    def _apply_touch(self, frame: FrameResult) -> None:
        detected = {det.object_id for det in frame.objects}
        ordered = sorted(self._tracks.values(), key=lambda item: item.object_id)
        step = step_touch(
            [_touch_track(track, track.object_id in detected) for track in ordered],
            frame.hands,
            frame.ts,
        )
        for object_id in step.dropped_ids:
            self._tracks.pop(object_id, None)
            logger.debug("merged away object %s", object_id)
        for updated in step.tracks:
            track = self._tracks.get(updated.object_id)
            if track is None:
                continue
            track.class_label = updated.class_label
            track.name = updated.name
            track.state = updated.state
            track.box = updated.box
            track.phase = updated.phase
            track.on_frames = updated.on_frames
            track.off_frames = updated.off_frames
            track.anchor_cx = updated.anchor_cx
            track.anchor_cy = updated.anchor_cy
            track.lost_since_ts = updated.lost_since_ts
            track.hand_clear_frames = updated.hand_clear_frames
        for event in step.events:
            self._publish(type(event).__name__, event)

    def _publish_name_requests(self, frame: FrameResult) -> None:
        for track in self._tracks.values():
            if not track.wants_name:
                continue
            if track.name.strip() or track.requests_sent != 0:
                track.wants_name = False
                continue
            request = request_for_new_idle(
                frame.ts,
                track.object_id,
                track.class_label,
                track.name,
                track.requests_sent,
                track.box,
                frame.image,
            )
            if request is None:
                continue
            track.requests_sent = 1
            track.wants_name = False
            self._publish(type(request).__name__, request)

    def _snapshot(self, frame: FrameResult) -> SceneSnapshot:
        objects = [
            SceneObject(
                object_id=track.object_id,
                class_label=track.class_label,
                name=track.name,
                state=track.state,
                box=track.box,
                last_seen_ts=track.last_seen_ts,
            )
            for track in sorted(self._tracks.values(), key=lambda item: item.object_id)
        ]
        return SceneSnapshot(ts=frame.ts, frame_id=frame.frame_id, objects=objects)


def _touch_track(track: _Track, detected: bool) -> TouchTrack:
    """Copy a scene track into the touch module's record."""
    return TouchTrack(
        object_id=track.object_id,
        class_label=track.class_label,
        name=track.name,
        state=track.state,
        box=track.box,
        detected=detected,
        phase=track.phase,
        on_frames=track.on_frames,
        off_frames=track.off_frames,
        anchor_cx=track.anchor_cx,
        anchor_cy=track.anchor_cy,
        lost_since_ts=track.lost_since_ts,
        hand_clear_frames=track.hand_clear_frames,
    )
