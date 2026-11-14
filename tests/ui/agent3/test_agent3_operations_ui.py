"""Checks for dashboard/static/features/operations (Agent 3): JS unit tests and source guards."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FEATURE = ROOT / "dashboard" / "static" / "features" / "operations"
HERE = Path(__file__).resolve().parent


def _sources() -> dict[str, str]:
    """Return every production file of the feature by name."""
    return {
        p.name: p.read_text(encoding="utf-8") for p in FEATURE.iterdir() if p.is_file()
    }


def test_feature_files_exist() -> None:
    """The feature exports mountOperations and has its split components and scoped styles."""
    files = _sources()
    for name in (
        "index.js",
        "status-strip.js",
        "warning-panel.js",
        "event-history.js",
        "demo-tools.js",
        "selectors.js",
        "operations.css",
    ):
        assert name in files, name
    assert "export function mountOperations(ctx)" in files["index.js"]


def test_no_transport_or_unsafe_html_in_feature() -> None:
    """Transport goes through ctx only; external text is never injected as HTML."""
    for name, text in _sources().items():
        if not name.endswith(".js"):
            continue
        assert "new WebSocket" not in text, name
        assert not re.search(r"\bfetch\(", text), name
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text, name
        assert "speechSynthesis" not in text, name


def test_css_is_scoped() -> None:
    """Every class selector in operations.css uses the operations- prefix."""
    css = re.sub(r"/\*.*?\*/", "", _sources()["operations.css"], flags=re.DOTALL)
    classes = set(re.findall(r"\.([a-zA-Z][\w-]*)", css))
    assert classes and all(c.startswith(("operations-", "op-")) for c in classes), (
        sorted(c for c in classes if not c.startswith("operations-"))
    )


def test_copy_never_claims_safety() -> None:
    """No copy describes the prototype as a safety device or says the path is clear."""
    for name, text in _sources().items():
        lowered = text.lower()
        assert "safety" not in lowered, name
        assert "path is clear." not in lowered.replace(
            "does not mean the path is clear.", ""
        ), name
        assert "you are safe" not in lowered, name


def test_demo_explanation_text() -> None:
    """The required explanation sits beside the simulate control."""
    text = _sources()["demo-tools.js"]
    assert (
        "Adds a simulated warning to this dashboard only. No alarm sounds and nothing is saved to touch history."
        in text
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_selector_unit_tests_pass() -> None:
    """Run the node:test suite for the pure selectors."""
    result = subprocess.run(
        ["node", "--test", str(HERE / "selectors.test.mjs")],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr
