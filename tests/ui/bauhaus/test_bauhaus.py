"""Bauhaus redesign checks: assets and licences, decorative images, local-only runtime, node tests."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "dashboard" / "static"
HERE = Path(__file__).resolve().parent
ILLUSTRATIONS = STATIC / "assets" / "illustrations"
SHIPPED_SOURCES = [
    *STATIC.glob("styles/*.css"),
    *STATIC.glob("features/*/*.css"),
    *STATIC.glob("features/*/*.js"),
    *STATIC.glob("components/*.js"),
    *STATIC.glob("core/*.js"),
    STATIC / "app.js",
    ROOT / "dashboard" / "index.html",
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_speech_signal_node_tests_pass() -> None:
    """components/speech-signal.js: motion only for real speaking, fallback, cleanup."""
    result = subprocess.run(
        ["node", "--test", str(HERE / "speech-signal.test.mjs")],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_rive_runtime_and_asset_are_vendored_with_licences() -> None:
    """The pinned runtime, its WASM, the recoloured asset and both MIT licences ship locally."""
    vendor = STATIC / "vendor" / "rive"
    for name in ("rive.js", "rive.wasm", "LICENSE"):
        assert (vendor / name).is_file(), name
    assert "MIT License" in (vendor / "LICENSE").read_text(encoding="utf-8")
    assets = STATIC / "assets" / "rive"
    assert (assets / "speech_signal.riv").read_bytes()[:4] == b"RIVE"
    assert "MIT License" in (assets / "LICENSE-rive-android").read_text(encoding="utf-8")
    component = (STATIC / "components" / "speech-signal.js").read_text(encoding="utf-8")
    assert 'RIVE_RUNTIME_VERSION = "2.47.1"' in component
    assert "setWasmFallbackUrl?.(null)" in component  # never a CDN fallback
    digest = hashlib.sha256((vendor / "rive.js").read_bytes()).hexdigest()
    inventory = (ROOT / "docs" / "dashboard-redesign" / "bauhaus" / "README.md").read_text(encoding="utf-8")
    assert digest in inventory, "the inventory records the vendored runtime's hash"


def test_recoloured_asset_is_still_a_valid_riv() -> None:
    """tools/riv_recolor.py can read the shipped file end to end and lists only palette colours."""
    result = subprocess.run(
        ["python3", str(ROOT / "tools" / "riv_recolor.py"), str(STATIC / "assets" / "rive" / "speech_signal.riv"), "--list"],
        check=True,
        capture_output=True,
        text=True,
    )
    colours = {line.split()[-1][-6:].upper() for line in result.stdout.splitlines()}
    assert colours <= {"171717", "1947B8", "F2C94C", "000000"}, colours


def test_illustrations_have_no_embedded_text_and_are_decorative() -> None:
    """Artwork carries no text (labels are HTML) and every use marks it decorative."""
    svgs = sorted(ILLUSTRATIONS.glob("*.svg"))
    assert len(svgs) >= 4
    for svg in svgs:
        assert "<text" not in svg.read_text(encoding="utf-8"), svg.name
    uses = {
        "touch-idle.svg": STATIC / "features" / "experience" / "touch-card.js",
        "history-empty.svg": STATIC / "features" / "operations" / "event-history.js",
        "how-it-works.svg": STATIC / "components" / "app-shell.js",
        "speech-signal-still.svg": STATIC / "components" / "speech-signal.js",
    }
    for name, source in uses.items():
        text = source.read_text(encoding="utf-8")
        assert name in text, f"{name} is placed in {source.name}"
        assert re.search(r'alt(:|\s*=)\s*""', text), f"{source.name} gives an empty alt"


def test_artwork_never_enters_camera_or_thumbnails() -> None:
    """Illustrations are page chrome only, never part of the video or object evidence."""
    for path in (
        STATIC / "features" / "experience" / "camera-panel.js",
        STATIC / "features" / "experience" / "object-list.js",
        ROOT / "dashboard" / "video.py",
        ROOT / "dashboard" / "thumbnails.py",
    ):
        assert "illustrations/" not in path.read_text(encoding="utf-8"), path.name


def test_shipped_page_loads_nothing_from_other_origins() -> None:
    """No CDN or external URL in the page's own sources (the vendored runtime's defaults are disabled)."""
    for path in SHIPPED_SOURCES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://(?!www\.w3\.org/2000/svg)", text), path.name


def test_red_is_not_used_for_non_error_camera_states() -> None:
    """Stale or opening video uses the yellow caution fill, not the hazard red."""
    css = (STATIC / "features" / "experience" / "experience.css").read_text(encoding="utf-8")
    tail = css[css.index("Bauhaus pass 2") :]
    block = tail[tail.index(".experience-camera-stale-mark") : tail.index("}", tail.index(".experience-camera-stale-mark"))]
    assert "caution-fill" in block and "danger" not in block
