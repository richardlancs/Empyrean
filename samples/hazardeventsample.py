"""Example HazardEvent for Person 4 to build audio and the dashboard against.

Reference only. Real events come from hazard/ over the bus (SPEC.md 4.7, 5).
"""

from contracts import HazardEvent

SAMPLE = HazardEvent(
    ts=1731551400.0,  # seconds since the Unix epoch, UTC
    type="stairs_down",  # stairs_down | drop_off | vehicle | obstacle
    source="grok",  # grok | yolo
    confidence=0.82,  # 0 to 1
)
