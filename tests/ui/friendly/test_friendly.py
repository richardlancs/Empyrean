"""Friendly-clarity checks: Pip assets and placement rules, removed Rive, local-only sources."""

from __future__ import annotations

import re
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
STATIC = ROOT / "dashboard" / "static"
PIP = STATIC / "assets" / "pip"
POSES = ("pip-wave", "pip-point", "pip-sit", "pip-peek", "pip-recline", "pip-peek-edge", "pip-wait", "pip-concerned")
# Crops that end on a straight edge by design (the sign top; the frame edge Pip peeks over).
FLUSH_BOTTOM = ("pip-peek", "pip-peek-edge")
SOURCES = [
    *STATIC.glob("styles/*.css"),
    *STATIC.glob("features/*/*.css"),
    *STATIC.glob("features/*/*.js"),
    *STATIC.glob("components/*.js"),
    *STATIC.glob("core/*.js"),
    STATIC / "app.js",
    ROOT / "dashboard" / "index.html",
]


def test_pip_assets_are_clean_single_shapes_with_transparent_padding() -> None:
    """Each pose is one shape, fully transparent at the edges, opaque in the body."""
    for name in POSES:
        image = cv2.imread(str(PIP / f"{name}.png"), cv2.IMREAD_UNCHANGED)
        assert image is not None and image.shape[2] == 4, name
        alpha = image[:, :, 3]
        count, _labels, _stats, _ = cv2.connectedComponentsWithStats((alpha > 8).astype(np.uint8), 8)
        assert count - 1 == 1, f"{name}: {count - 1} separate shapes (specks left?)"
        edges = (alpha[0], alpha[:, 0], alpha[:, -1]) if name in FLUSH_BOTTOM else (alpha[0], alpha[-1], alpha[:, 0], alpha[:, -1])
        if name != "pip-peek":  # the sign peek is also trimmed to the sign's width
            for edge in edges:
                assert edge.max() == 0, f"{name}: artwork touches the image edge"
        assert (alpha == 255).mean() > 0.25, f"{name}: body is not opaque"
        assert max(image.shape[:2]) <= 480, f"{name}: larger than needed"


def test_pip_is_decorative_everywhere_and_never_in_camera_or_thumbnails() -> None:
    """Every Pip has an empty alt; artwork never enters the video, thumbnails or history."""
    uses = {
        "pip-sit.png": STATIC / "features" / "operations" / "event-history.js",
        "pip-wave.png": STATIC / "components" / "app-shell.js",
        "pip-recline.png": STATIC / "features" / "experience" / "pip-companion.js",
        "pip-peek-edge.png": STATIC / "features" / "experience" / "pip-companion.js",
        "pip-wait.png": STATIC / "features" / "experience" / "pip-companion.js",
        "pip-concerned.png": STATIC / "features" / "experience" / "pip-companion.js",
    }
    for name, source in uses.items():
        text = source.read_text(encoding="utf-8")
        assert name in text, f"{name} placed in {source.name}"
        assert re.search(r'alt(:|\s*=)\s*""', text), f"{source.name}: Pip needs alt=\"\""
    for path in (
        STATIC / "features" / "experience" / "camera-panel.js",
        STATIC / "features" / "experience" / "object-list.js",
        ROOT / "dashboard" / "video.py",
        ROOT / "dashboard" / "thumbnails.py",
        ROOT / "dashboard" / "state.py",
    ):
        assert "assets/pip" not in path.read_text(encoding="utf-8"), path.name


def test_pip_steps_aside_during_an_active_real_hazard() -> None:
    """layout.css hides every Pip, the camera companion and its bubble while the warning slot is urgent."""
    css = (STATIC / "styles" / "layout.css").read_text(encoding="utf-8")
    rule = re.search(r'((?::root:has\(\.app-slot--warning\[data-emphasis="urgent"\]\) [.\w-]+,?\s*)+)\{\s*display: none;', css)
    assert rule, "no urgent-hazard rule"
    for selector in (".pip", ".pip-perch", ".pip-bubble"):
        assert re.search(re.escape(selector) + r"\b(?!-)", rule.group(1)), selector


def test_camera_pip_is_a_named_help_button_that_never_switches_models() -> None:
    """Pip is a real button with a fixed name, a decorative image, and no request to the engine."""
    pip = (STATIC / "features" / "experience" / "pip-companion.js").read_text(encoding="utf-8")
    assert '"aria-label": "Help with the camera."' in pip
    assert 'alt: ""' in pip and '"aria-expanded"' in pip and '"Close help"' in pip
    assert "Escape" in pip
    for forbidden in ("request(", "fetch(", "/api/", "aria-live", 'role: "status"', 'role: "alert"'):
        assert forbidden not in pip, forbidden
    css = (STATIC / "features" / "experience" / "experience.css").read_text(encoding="utf-8")
    pip_css = css[css.index("Pip, the camera companion") :]
    assert "infinite" not in pip_css, "Pip must not loop"
    assert "prefers-reduced-motion: reduce" in pip_css


def test_speech_never_infers_success_from_a_touch() -> None:
    """The speech view model reads only state.speech; log-only audio leads with no sound.

    Fake (printed) audio is no longer labelled on the page, at the user's request.
    """
    selectors = (STATIC / "features" / "experience" / "selectors.js").read_text(encoding="utf-8")
    body = selectors[selectors.index("export function selectSpeech") :]
    body = body[: body.index("\n}\n")]
    assert "state?.speech" in body and "current_touch" not in body and "events" not in body
    assert 'unavailable: "No sound' in selectors and 'fake: "Demo audio' not in selectors


def test_rive_and_bauhaus_artwork_were_removed_completely() -> None:
    """The ambiguous speech ring is gone, with its runtime, asset and references."""
    assert not (STATIC / "vendor" / "rive").exists()
    assert not (STATIC / "assets" / "rive").exists()
    assert not (STATIC / "components" / "speech-signal.js").exists()
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        assert "speech-signal" not in text and "assets/illustrations" not in text, path.name


def test_shipped_page_loads_nothing_from_other_origins() -> None:
    """No CDN or external URL in the page's own sources."""
    for path in SOURCES:
        assert not re.search(r"https?://(?!www\.w3\.org/2000/svg)", path.read_text(encoding="utf-8")), path.name
