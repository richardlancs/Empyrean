"""TEST HARNESS ONLY: app/ with fakes plus replayed speech telemetry marked mode "real".

The fake audio module reports mode "fake", so the dashboard's speech signal
never moves in a fake run (by design). To check the Rive animation and its
performance while the camera stream and events are live, this harness also
publishes scripted SpeechStatus messages with mode "real". Nothing is spoken.
Never use it as evidence that audio works.

    PORT=8003 PYTHONPATH=. python tests/ui/bauhaus/launch_with_speech.py
"""

from __future__ import annotations

import itertools
import os
import threading
import time

import app.__main__ as app_main
from contracts import SpeechStatus
from dashboard import server

PORT = int(os.environ.get("PORT", "8003"))
SPEAK_SECONDS = 4.0
PAUSE_SECONDS = 3.0


def main() -> None:
    """Start the app on PORT and replay speaking/completed statuses until Ctrl+C."""
    original = server.Dashboard.serve
    server.Dashboard.serve = lambda self, host="127.0.0.1", port=PORT: original(self, host, PORT)
    running = app_main.start(fakes=("vision", "namer", "storage", "audio"))
    stop = threading.Event()

    def replay() -> None:
        for speech_id in itertools.count(10_000):
            for status, wait in (("speaking", SPEAK_SECONDS), ("completed", PAUSE_SECONDS)):
                running.bus.publish(
                    SpeechStatus(
                        ts=time.time(),
                        speech_id=speech_id,
                        text="Test harness phrase",
                        status=status,
                        mode="real",
                        kind="answer",
                        source="test-harness",
                        detail="Replayed by tests/ui/bauhaus/launch_with_speech.py",
                    )
                )
                if stop.wait(wait):
                    return

    threading.Thread(target=replay, daemon=True).start()
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        running.stop()


if __name__ == "__main__":
    main()
