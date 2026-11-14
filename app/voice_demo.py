"""Optional microphone demo against fake Empyrean data (not production integration).

Run: python -m app.voice_demo

Voice recognition uses the microphone, SpeechRecognition and PyAudio, plus Google's
online transcription endpoint. Those two Python packages are NOT part of the
approved project stack and need team agreement before this can be merged.
Camera, naming and storage are fake; spoken answers use the existing audio bus.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence

from contracts import LastSeenQuery, SceneObject, SceneSnapshot, SpeakRequest

log = logging.getLogger("app.voice_demo")


def make_reply(
    question: str,
    objects: Sequence[SceneObject],
    timestamp: float,
) -> LastSeenQuery | SpeakRequest:
    """Route a transcribed question to an existing bus message."""
    text = question.casefold().strip()
    if "last touch" in text:
        item = text.split("last touch", 1)[1].strip(" ?.!")
        for prefix in ("the ", "my ", "a "):
            if item.startswith(prefix):
                item = item[len(prefix):]
                break
        if item:
            return LastSeenQuery(ts=timestamp, text=item)
        answer = "Please specify an object."
    elif "hold" in text or "touching" in text:
        names = list(dict.fromkeys(
            obj.name or obj.class_label
            for obj in objects
            if obj.state in ("touching", "held")
        ))
        answer = (
            "You are touching " + ", ".join(names) + "."
            if names
            else "I don't detect you holding anything right now."
        )
    elif "see" in text or "in front" in text:
        names = list(dict.fromkeys(
            obj.name or obj.class_label
            for obj in objects
            if obj.state not in ("new", "lost")
        ))
        answer = (
            "I can see " + ", ".join(names[:4]) + "."
            if names
            else "I don't detect any objects right now."
        )
    else:
        answer = "Try asking what I can see or what you're holding."

    return SpeakRequest(
        ts=timestamp, text=answer, priority="normal", source="app"
    )


def main() -> int:
    """Listen interactively and publish answers through the existing audio bus."""
    try:
        import speech_recognition as sr
    except ImportError:
        log.error(
            "Voice demo requires locally installed SpeechRecognition and PyAudio "
            "(pending team approval as project dependencies)"
        )
        return 2

    from app.__main__ import start

    # Fake camera, naming and storage: no models, Grok key or Tiger Data needed.
    # The real audio manager stays in charge of speech and hazard priority.
    running = start(fakes=("vision", "namer", "storage"))
    lock = threading.Lock()
    current: list[SceneObject] = []

    def on_scene(snapshot: SceneSnapshot) -> None:
        """Keep only the most recent published scene."""
        nonlocal current
        with lock:
            current = list(snapshot.objects)

    running.bus.subscribe(SceneSnapshot, on_scene)
    recognizer = sr.Recognizer()
    log.info("Voice demo ready (fake camera). Press Ctrl+C to stop.")

    try:
        while True:
            try:
                input("\nPress Enter to ask a question...")
            except EOFError:
                log.error("Use an interactive terminal: python -m app.voice_demo")
                return 2

            try:
                with sr.Microphone() as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    log.info("Listening! Speak now...")
                    audio = recognizer.listen(
                        source, timeout=10, phrase_time_limit=8
                    )
                question = recognizer.recognize_google(audio)
            except (sr.WaitTimeoutError, sr.UnknownValueError):
                log.info("No clear question heard; try again.")
                continue
            except (sr.RequestError, OSError) as exc:
                log.warning("Speech recognition unavailable: %s", exc)
                continue

            log.info("You asked: %s", question)
            with lock:
                objects = list(current)
            reply = make_reply(question, objects, time.time())
            if isinstance(reply, SpeakRequest):
                log.info("Answer: %s", reply.text)
            else:
                log.info("Searching fake touch history for: %s", reply.text)
            running.bus.publish(reply)
    except KeyboardInterrupt:
        return 0
    finally:
        running.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
