"""Pytest wrapper for the K15 delivery-pack viewer E2E test.

Runs `node test_k15pack.mjs` via subprocess. Skips if Node is missing;
the mjs itself SKIPs (exit 0) when the k15 delivery pack has not been
produced yet (run the demo first: `python -m exp.k15_simdiff
--seed 1 --rounds N`). Asserts exit 0 and that every reported line is
PASS.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
MJS = HERE / "viewer" / "test_k15pack.mjs"


def _node_present() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=5,
                       check=False)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(not _node_present(), reason="Node.js not available")
def test_k15pack_mjs() -> None:
    cp = subprocess.run(
        ["node", str(MJS)],
        cwd=str(HERE.parent.parent),  # repo root
        capture_output=True,
        text=True,
        timeout=120,
    )
    stdout = cp.stdout
    stderr = cp.stderr

    if stdout:
        print(stdout, file=sys.stderr)
    if stderr:
        print(stderr, file=sys.stderr)

    lines = [l for l in stdout.splitlines()
             if l.startswith(("PASS ", "FAIL ", "SKIP "))]

    # a graceful SKIP (pack not built yet) is not a failure
    if lines and all(l.startswith("SKIP ") for l in lines):
        return
    fails = [l for l in lines if l.startswith("FAIL ")]
    assert cp.returncode == 0, (
        f"Node test exited with {cp.returncode}\n"
        + "\n".join(lines)
    )
    assert not fails, f"Test failures:\n" + "\n".join(fails)
    assert lines and all(l.startswith("PASS ") for l in lines), (
        f"Unexpected output:\n" + "\n".join(lines)
    )
