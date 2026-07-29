"""exp/artifacts tests — the cross-exp artifact resolver.

Covers: path layout, find/stamp/require on fast generators (k14 regen
is seconds; k11 regen is minutes and only its find/stamp path is
exercised against the existing seed-1 dump), and the manifest chain.
"""

from __future__ import annotations

import json

import pytest

from exp.artifacts import (artifact_path, current_commit, find, require,
                           stamp, write_manifest)

K14_SEED = 1
K11_SEED = 1


def test_layout():
    assert str(artifact_path("k11", 1)).endswith(
        "exp/k11_worldgen/out/seed_00000001")
    assert str(artifact_path("k13", 12)).endswith(
        "exp/k13_treegen/out/k13_seed00000012.json")
    assert str(artifact_path("k14", 1)).endswith(
        "exp/k14_flora/out/seed_00000001/k14_seed00000001.json")
    with pytest.raises(KeyError):
        artifact_path("k99", 1)


def test_find_missing():
    assert find("k14", 999999) is None


def test_require_regenerates(tmp_path):
    """k14 seed 424242 is absent -> require() regenerates via the CLI."""
    assert find("k14", 424242) is None
    p = require("k14", 424242)
    try:
        assert p.is_file()
        meta = json.loads(p.read_text())["meta"]
        assert meta["generator"] == "k14_flora"
        assert meta["seed"] == 424242
        assert meta["commit"]
    finally:
        p.unlink()   # test artifact — don't leave it in the demo out/
        p.with_suffix(".report").unlink(missing_ok=True)


def test_stamp_k14():
    require("k14", K14_SEED)
    s = stamp("k14", K14_SEED)
    assert s["generator"] == "k14_flora"
    assert s["version"] == 2
    assert s["seed"] == K14_SEED
    # the producing commit is historical truth — it records WHEN the
    # artifact was generated and legitimately differs from HEAD after
    # later commits/amends. It must be present and well-formed.
    assert s["commit"] and len(s["commit"]) >= 7
    assert len(s["sha256"]) == 64
    # hash is stable and covers the bytes
    assert stamp("k14", K14_SEED)["sha256"] == s["sha256"]


def test_stamp_k11_existing_dump():
    """The existing seed-1 K11 dump stamps without regeneration."""
    if find("k11", K11_SEED) is None:
        pytest.skip("no local k11 seed-1 dump")
    s = stamp("k11", K11_SEED)
    assert s["generator"] == "k11_worldgen"
    assert s["version"] == 2
    assert s["seed"] == K11_SEED
    assert len(s["sha256"]) == 64


def test_manifest(tmp_path):
    require("k14", K14_SEED)
    mpath = write_manifest(tmp_path, inputs=[("k14", K14_SEED)],
                           note="test")
    m = json.loads(mpath.read_text())
    assert m["inputs"][0]["generator"] == "k14_flora"
    assert m["inputs"][0]["seed"] == K14_SEED
    assert len(m["inputs"][0]["sha256"]) == 64
    assert m["created_commit"] == current_commit()
    assert m["note"] == "test"
