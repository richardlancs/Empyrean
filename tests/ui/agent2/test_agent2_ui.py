"""Run the experience feature's JavaScript unit tests under pytest (skipped without Node)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_experience_javascript_units() -> None:
    """Selectors and last-seen controller tests pass under `node --test`."""
    files = sorted(str(p) for p in HERE.glob("*.test.mjs"))
    result = subprocess.run(
        [NODE, "--test", *files],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
