"""M9 tests — persistence round-trip and the CLI."""

from __future__ import annotations

import pathlib
import subprocess

import pytest

from exp.k13_treegen.content import load_content
from exp.k13_treegen.model import Tree

CONTENT = pathlib.Path(__file__).parent / "content" / "fauna"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


def test_json_round_trip(pack):
    from exp.k13_treegen.__main__ import generate
    tree, report = generate(3, pack)
    blob = tree.dumps()
    assert Tree.from_json(__import__("json").loads(blob)).dumps() == blob
    assert report.ok


def test_cli(tmp_path, pack):
    out = tmp_path / "o"
    r = subprocess.run(
        ["uv", "run", "python", "-m", "exp.k13_treegen", "5",
         "--out", str(out), "--species", "3"],
        capture_output=True, text=True, cwd=pathlib.Path(__file__)
        .parent.parent.parent)
    assert r.returncode == 0, r.stderr
    tree_path = out / "k13_seed00000005.json"
    report_path = out / "k13_seed00000005.report"
    assert tree_path.exists() and report_path.exists()
    assert "OK" in report_path.read_text()
    assert "species" in tree_path.read_text()
    # --species printed descriptions
    assert " with " in r.stdout or "-like" in r.stdout


def test_cli_seed_in_filename(tmp_path):
    """8-digit zero-padded seeds (user convention)."""
    r = subprocess.run(
        ["uv", "run", "python", "-m", "exp.k13_treegen", "42",
         "--out", str(tmp_path)],
        capture_output=True, text=True, cwd=pathlib.Path(__file__)
        .parent.parent.parent)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "k13_seed00000042.json").exists()
