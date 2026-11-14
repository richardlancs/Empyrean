"""Run Empyrean's modules against the real camera or scripted fakes."""

from __future__ import annotations

import argparse
import importlib
import inspect
import logging
import os
import tempfile
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.bus import Bus
from config.thresholds import PROCESS_FPS
from contracts import FrameResult, ModuleStatus, NameResult

log = logging.getLogger("app")
# Dashboard first: it only subscribes, and must be listening before the other
# modules announce their status (ModuleStatus) while they register.
MODULES = ("dashboard", "hazard", "scene", "namer", "storage", "audio", "vision")
FAKE_PATHS = {
    "vision": "fakes.vision.fake_vision",
    "hazard": "fakes.hazard.fake_hazard",
    "namer": "fakes.namer.fake_namer",
    "storage": "fakes.storage.fake_store",
    "scene": "fakes.scene",
    "audio": "fakes.audio",
    "dashboard": "fakes.dashboard",
}


class RunningApp:
    """Hold module lifetimes and stop producers before the bus."""

    def __init__(self, bus: Bus, instances: list[Any]) -> None:
        self.bus = bus
        self.instances = instances

    def stop(self) -> None:
        """Stop registered modules in reverse startup order."""
        for instance in reversed(self.instances):
            stop = getattr(instance, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    log.exception("Module shutdown failed")
        self.bus.stop()


def _scene_adapter(bus: Bus) -> Any:
    """Bridge Person 2's existing publish(topic, message) scene interface."""
    from scene import SceneDatabase

    scene = SceneDatabase(lambda _topic, message: bus.publish(message))
    scene_lock = threading.Lock()

    def on_frame(message: FrameResult) -> None:
        """Process a frame without overlapping name callbacks."""
        with scene_lock:
            scene.handle_frame(message)
            if message.frame_id % PROCESS_FPS == 0:
                log.info("Scene received FrameResult %d", message.frame_id)

    def on_name(message: NameResult) -> None:
        """Apply one asynchronous name result."""
        with scene_lock:
            scene.handle_name(message)

    bus.subscribe(FrameResult, on_frame)
    bus.subscribe(NameResult, on_name)
    return scene


class _FakeScenePlayback:
    """Adapt the existing Person 2 fake script to the message bus."""

    def __init__(self, bus: Bus) -> None:
        from fakes.scene.script import scripted_messages

        self._messages = scripted_messages()
        self._publish = bus.publish
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="fake-scene", daemon=True)

    def start(self) -> None:
        """Publish the fake script after the other module subscriptions exist."""
        self._thread.start()

    def _run(self) -> None:
        for _topic, message in self._messages:
            if self._stop.is_set():
                return
            self._publish(message)
            if self._stop.wait(0.2):
                return

    def stop(self) -> None:
        """Stop the playback, if it is still running."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)


class _Deferred:
    """A fake publisher created unstarted; start() runs after all registrations."""

    def __init__(self, publisher: Any) -> None:
        self.publisher = publisher

    def start(self) -> None:
        """Start publishing."""
        self.publisher.start()

    def stop(self) -> None:
        """Stop publishing."""
        stop = getattr(self.publisher, "stop", None)
        if callable(stop):
            stop()


def _accepts_start(register: Any) -> bool:
    """True when register(bus, start=False) is supported."""
    try:
        return "start" in inspect.signature(register).parameters
    except (TypeError, ValueError):
        return False


def _register(name: str, fake: bool, bus: Bus) -> Any:
    """Load one module entry point, allowing not-yet-written folders."""
    dotted = FAKE_PATHS.get(name, f"fakes.{name}") if fake else name
    try:
        module = importlib.import_module(dotted)
    except ModuleNotFoundError as exc:
        if exc.name == dotted or dotted.startswith(f"{exc.name}."):
            log.warning("Module %s is not available yet; continuing", dotted)
        else:
            log.error("Module %s needs dependency %s", dotted, exc.name)
        return None
    except ImportError:
        log.exception("Could not import module %s", dotted)
        return None

    register = getattr(module, "register", None)
    if callable(register):
        if fake and _accepts_start(register):
            # Scripted publishers wait until every consumer has subscribed;
            # start() is called by start() below, like _FakeScenePlayback.
            return _Deferred(register(bus, start=False))
        return register(bus)
    if name == "scene":
        return _FakeScenePlayback(bus) if fake else _scene_adapter(bus)
    log.warning("Module %s has no register(bus); continuing", dotted)
    return None


def _lifecycle(module: str, status: str, mode: str, detail: str) -> ModuleStatus:
    """Build the ModuleStatus app/ publishes for one module at startup."""
    return ModuleStatus(
        ts=time.time(),
        module=module,
        status=status,  # type: ignore[arg-type]
        mode=mode,  # type: ignore[arg-type]
        detail=detail,
    )


def start(
    only: str | None = None,
    fakes: Sequence[str] = (),
    record_crops: Path | None = None,
) -> RunningApp:
    """Load environment settings and register selected modules with a fresh bus."""
    load_dotenv()
    os.environ.setdefault("CAMERA_INDEX", "0")
    unknown = set(fakes) - set(MODULES)
    if only is not None and only not in MODULES:
        raise ValueError(f"Unknown module: {only}")
    if unknown:
        raise ValueError(f"Unknown fake modules: {', '.join(sorted(unknown))}")
    selected = {only} if only else set(MODULES)
    selected.update(fakes)
    bus = Bus()
    instances: list[Any] = []
    lifecycle: list[ModuleStatus] = []
    # Vision is last, so subscribers are ready before the first camera frame.
    for name in MODULES:
        mode = "fake" if name in fakes else "real"
        if name not in selected:
            lifecycle.append(_lifecycle(name, "offline", "unknown", "Not started in this run"))
            continue
        try:
            instance = _register(name, name in fakes, bus)
        except Exception:
            log.exception("Module %s could not start; continuing", name)
            lifecycle.append(_lifecycle(name, "offline", mode, "Could not start"))
            continue
        if instance is not None:
            instances.append(instance)
            log.info("Started %s%s", name, " (fake)" if name in fakes else "")
            detail = "Started with a fake" if name in fakes else "Started"
            lifecycle.append(_lifecycle(name, "starting", mode, detail))
        else:
            lifecycle.append(_lifecycle(name, "offline", mode, "Not available"))
    if record_crops is not None:
        # From main (vision/DEMO.md rehearsal): save naming crops for later review.
        from fakes.namer.crop_recorder import register as register_recorder

        record_crops.mkdir(parents=True, exist_ok=True)
        session = Path(tempfile.mkdtemp(prefix="session-", dir=record_crops))
        instances.append(register_recorder(bus, out_dir=session))
        log.info("Recording naming crops to %s", session)
    # Lifecycle facts for the dashboard. A module's own later status wins over these.
    for message in lifecycle:
        if message.module != "dashboard":
            bus.publish(message)
    # Scripted fakes publish only now, so their first message reaches every
    # consumer (for example the first fake hazard reaches audio).
    for instance in instances:
        if isinstance(instance, _FakeScenePlayback | _Deferred):
            instance.start()
    return RunningApp(bus, instances)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse module selection flags and run until interrupted."""
    parser = argparse.ArgumentParser(description="Run Empyrean")
    parser.add_argument("--only", choices=MODULES)
    parser.add_argument("--fake", nargs="+", metavar="MODULE", default=[])
    parser.add_argument(
        "--record-crops", type=Path, nargs="?",
        const=Path("scratch/camera_crops"),
        help="Save naming crops in a fresh session folder under this directory",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        running = start(only=args.only, fakes=args.fake, record_crops=args.record_crops)
    except ValueError as exc:
        parser.error(str(exc))
    stop = threading.Event()
    try:
        # A timed wait lets Ctrl+C interrupt the main thread on Windows.
        while not stop.wait(0.5):
            pass
    except KeyboardInterrupt:
        log.info("Shutting down")
    finally:
        running.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
