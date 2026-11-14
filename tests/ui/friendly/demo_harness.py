"""DEMO INPUTS FOR TESTING ONLY. app/ with fakes plus scripted engine inputs.

No hardware or external service is used and nothing is spoken. Everything this
harness adds is labelled in its messages ("demo harness") so it can never be
mistaken for real evidence:

  SPEECH=1        replays SpeechStatus messages: real-mode queued, speaking,
                  completed, failed, then log-only ("unavailable" mode).
  CAMERA_GAP=a,b  repeatedly: runs the recorded clip for a seconds, then stops it
                  for b seconds (camera goes stale, then offline), then restarts
                  it (recovery).
  REAL_STORAGE=1  uses the real storage module with no database, so last-touch
                  searches come back "unavailable".

    PORT=8011 SPEECH=1 PYTHONPATH=. python tests/ui/friendly/demo_harness.py
"""

from __future__ import annotations

import itertools
import os
import threading
import time

import app.__main__ as app_main
from contracts import SpeechStatus
from dashboard import server

PORT = int(os.environ.get("PORT", "8011"))
SPEECH_SCRIPT = (
    ("queued", "real", 1.5),
    ("speaking", "real", 3.0),
    ("completed", "real", 3.0),
    ("failed", "real", 3.0),
    ("completed", "unavailable", 3.0),
)


def _replay_speech(running: app_main.RunningApp, stop: threading.Event) -> None:
    """Publish the scripted speech statuses in a loop."""
    for speech_id in itertools.count(20_000):
        for status, mode, wait in SPEECH_SCRIPT:
            running.bus.publish(
                SpeechStatus(
                    ts=time.time(),
                    speech_id=speech_id if mode == "real" else speech_id + 500_000,
                    text="Demo harness phrase",
                    status=status,  # type: ignore[arg-type]
                    mode=mode,  # type: ignore[arg-type]
                    kind="answer",
                    source="demo-harness",
                    detail="Scripted by tests/ui/friendly/demo_harness.py" if status == "failed" else "",
                )
            )
            if stop.wait(wait):
                return


def _camera_gap(running: app_main.RunningApp, on: float, off: float, stop: threading.Event) -> None:
    """Repeatedly run the recorded clip for `on` seconds, then stop it for `off` seconds."""
    from fakes.vision.fake_vision import FakeVision

    while True:
        if stop.wait(on):
            return
        for instance in running.instances:
            publisher = getattr(instance, "publisher", instance)
            if isinstance(publisher, FakeVision):
                publisher.stop()
        if stop.wait(off):
            return
        running.instances.append(FakeVision(running.bus.publish))


def main() -> None:
    """Start the app on PORT with the requested demo inputs until Ctrl+C."""
    original = server.Dashboard.serve
    server.Dashboard.serve = lambda self, host="127.0.0.1", port=PORT: original(self, host, PORT)
    fakes = ["vision", "namer", "audio"]
    if not os.environ.get("REAL_STORAGE"):
        fakes.append("storage")
    else:
        os.environ.pop("TIGER_DATABASE_URL", None)
    running = app_main.start(fakes=fakes)
    stop = threading.Event()
    if os.environ.get("SPEECH"):
        threading.Thread(target=_replay_speech, args=(running, stop), daemon=True).start()
    if os.environ.get("CAMERA_GAP"):
        a, b = (float(v) for v in os.environ["CAMERA_GAP"].split(","))
        threading.Thread(target=_camera_gap, args=(running, a, b, stop), daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        running.stop()


if __name__ == "__main__":
    main()
