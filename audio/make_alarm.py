"""Write audio/sounds/alarm.wav: three short 880 Hz beeps (SPEC.md section 4.8).

The alarm is a pre-made file, so this script is run once by hand and its output
is committed. The app never generates sound at run time.

Run:  python -m audio.make_alarm
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

ALARM_PATH = Path(__file__).resolve().parent / "sounds" / "alarm.wav"
SAMPLE_RATE = 44100
FREQUENCY_HZ = 880.0
BEEPS = 3
BEEP_SECONDS = 0.15
GAP_SECONDS = 0.08
FADE_SECONDS = 0.005  # short ramps so the beeps do not click
AMPLITUDE = 0.7


def beep_samples() -> list[int]:
    """Return 16-bit mono samples for the full three-beep alarm."""
    beep_len = round(BEEP_SECONDS * SAMPLE_RATE)
    gap_len = round(GAP_SECONDS * SAMPLE_RATE)
    fade_len = round(FADE_SECONDS * SAMPLE_RATE)
    samples: list[int] = []
    for index in range(BEEPS):
        for n in range(beep_len):
            envelope = min(1.0, n / fade_len, (beep_len - 1 - n) / fade_len)
            value = (
                AMPLITUDE
                * envelope
                * math.sin(2 * math.pi * FREQUENCY_HZ * n / SAMPLE_RATE)
            )
            samples.append(round(value * 32767))
        if index < BEEPS - 1:
            samples.extend([0] * gap_len)
    return samples


def write_alarm(path: Path = ALARM_PATH) -> Path:
    """Write the alarm WAV to path and return it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = beep_samples()
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return path


if __name__ == "__main__":
    print(f"Wrote {write_alarm()}")
