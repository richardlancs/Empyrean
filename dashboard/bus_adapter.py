"""Engine wiring: which bus messages feed which dashboard service.

This is the only place the dashboard subscribes to the bus. Every handler only
updates memory and returns. Each subscription runs on its own bus worker, so
drawing the video or cropping thumbnails can never delay the read model, and
nothing here can delay vision, scene, hazard or audio.
"""

from __future__ import annotations

from typing import Any

from contracts import (
    DetectorStatus,
    FrameResult,
    HazardEvent,
    LastSeenResult,
    ModuleStatus,
    NameRequest,
    NameResult,
    SceneSnapshot,
    SpeechStatus,
    TouchEvent,
)
from dashboard.services.container import DashboardServices


def connect(bus: Any, services: DashboardServices) -> None:
    """Subscribe the dashboard's services to the bus."""
    state, video = services.state, services.video
    thumbnails, last_seen = services.thumbnails, services.last_seen

    def on_frame_light(msg: FrameResult) -> None:
        """Measure the camera and keep a frame reference for thumbnails (no drawing)."""
        state.on_frame(msg)
        thumbnails.on_frame(msg)

    # Original subscriptions, unchanged.
    bus.subscribe(HazardEvent, state.on_hazard)
    bus.subscribe(TouchEvent, state.on_touch)
    bus.subscribe(FrameResult, video.on_frame)
    bus.subscribe(SceneSnapshot, video.on_scene)
    bus.subscribe(SceneSnapshot, state.on_scene)
    # Added for the redesign.
    bus.subscribe(FrameResult, on_frame_light)
    bus.subscribe(SceneSnapshot, thumbnails.on_scene)
    bus.subscribe(NameRequest, state.on_name_request)
    bus.subscribe(NameResult, state.on_name_result)
    bus.subscribe(SpeechStatus, state.on_speech)
    bus.subscribe(ModuleStatus, state.on_module_status)
    bus.subscribe(LastSeenResult, last_seen.on_result)
    # Regular/Demo: vision's DetectorStatus is the only confirmation of a switch.
    bus.subscribe(DetectorStatus, services.detector_mode.on_status)
