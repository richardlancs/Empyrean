"""The real alarm must not stop the app from exiting on SIGTERM."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM is POSIX only")
def test_sigterm_still_stops_process_after_alarm_mixer_starts() -> None:
    """Opening the pygame alarm leaves SIGTERM's default action in place."""
    pytest.importorskip("pygame")
    script = textwrap.dedent(
        """
        import sys, time
        from audio.backends import PygameAlarm
        try:
            PygameAlarm()
        except Exception as exc:  # no audio device on this machine
            print("SKIP", exc, flush=True)
            sys.exit(0)
        print("READY", flush=True)
        time.sleep(30)
        """
    )
    env = {key: value for key, value in os.environ.items() if key != "SDL_NO_SIGNAL_HANDLERS"}
    process = subprocess.Popen(
        [sys.executable, "-c", script], cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        first = process.stdout.readline().strip() if process.stdout else ""
        if first.startswith("SKIP"):
            pytest.skip(f"alarm mixer unavailable: {first}")
        assert first == "READY"
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == -signal.SIGTERM
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
