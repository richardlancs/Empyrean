"""Run Agent 4's integration node tests under pytest (skipped when Node is missing)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_integration_node_tests_pass() -> None:
    """Fake modules and fake camera clips are labelled as fakes in the merged UI."""
    result = subprocess.run(
        ["node", "--test", str(HERE / "integration.test.mjs")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
