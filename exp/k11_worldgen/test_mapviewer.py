"""Pytest wrapper for the K11 map viewer E2E tests.

Runs `node test_mapviewer.mjs` via subprocess.  Skips if Node is
missing; asserts exit 0 and that all test lines contain PASS.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
MJS = HERE / "viewer" / "test_mapviewer.mjs"


def _node_present() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=5,
                       check=False)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _node_present(), reason="Node.js not available")
def test_mapviewer_mjs() -> None:
    cp = subprocess.run(
        ["node", str(MJS)],
        cwd=str(HERE.parent.parent),  # repo root
        capture_output=True,
        text=True,
        timeout=90,
    )
    stdout = cp.stdout
    stderr = cp.stderr

    # Print output so pytest shows it on failure
    if stdout:
        print(stdout, file=sys.stderr)
    if stderr:
        print(stderr, file=sys.stderr)

    # Every asserted test in the mjs must pass
    lines = [l for l in stdout.splitlines() if l.startswith(("PASS ", "FAIL "))]
    fails = [l for l in lines if l.startswith("FAIL ")]

    assert cp.returncode == 0, (
        f"Node test exited with {cp.returncode}\n"
        + "\n".join(lines)
    )
    assert not fails, f"Test failures:\n" + "\n".join(fails)

    # All lines should be PASS
    assert all(l.startswith("PASS ") for l in lines), (
        f"Unexpected output:\n" + "\n".join(lines)
    )
