"""The set of services one dashboard app instance serves."""

from __future__ import annotations

from dataclasses import dataclass

from dashboard.services.detector_mode import DetectorModeService
from dashboard.services.last_seen import LastSeenService
from dashboard.services.questions import QuestionService
from dashboard.state import DashboardState
from dashboard.thumbnails import ThumbnailCache
from dashboard.video import VideoFeed


@dataclass
class DashboardServices:
    """The read model, video pipeline and query services that routes call into."""

    state: DashboardState
    video: VideoFeed
    last_seen: LastSeenService
    thumbnails: ThumbnailCache
    detector_mode: DetectorModeService
    questions: QuestionService
