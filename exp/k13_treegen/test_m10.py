"""M10 tests — K13 phylogenetic tree viewer and headless-browser test suite."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parent.parent.parent
VIEWER_DIR = pathlib.Path(__file__).parent / "viewer"


def _node_available() -> bool:
    return shutil.which("node") is not None


@pytest.mark.skipif(not _node_available(), reason="node not installed")
def test_viewer_puppeteer_suite():
    """Run the puppeteer test suite for the tree viewer."""
    test_script = VIEWER_DIR / "test_viewer.mjs"
    assert test_script.exists(), f"test script not found: {test_script}"

    r = subprocess.run(
        ["node", str(test_script)],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=REPO,
    )

    stdout = r.stdout
    stderr = r.stderr

    # Assert exit code 0
    assert r.returncode == 0, (
        f"Test script exited with code {r.returncode}\n"
        f"STDERR:\n{stderr}\n"
        f"STDOUT:\n{stdout}"
    )

    # Every line with "PASS" counts; ensure no "FAIL" lines
    lines = stdout.splitlines()
    pass_lines = [l for l in lines if "PASS" in l]
    fail_lines = [l for l in lines if "FAIL" in l]

    assert len(pass_lines) > 0, f"No PASS lines in output:\n{stdout}"
    assert len(fail_lines) == 0, (
        f"FAIL lines found:\n" + "\n".join(fail_lines)
    )

    # Verify screenshots were produced
    screenshot_init = REPO / "tmp" / "m10_viewer.png"
    screenshot_expand = REPO / "tmp" / "m10_viewer_expanded.png"
    assert screenshot_init.exists(), f"Missing screenshot: {screenshot_init}"
    assert screenshot_expand.exists(), f"Missing screenshot: {screenshot_expand}"
