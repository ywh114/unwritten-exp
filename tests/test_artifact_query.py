"""Tests for the k15 artifact query tool (ticket 0038).

Fast tier only.  Runs against the REAL seed-1 artifact
(exp/k15_simdiff/out/seed_00000001) and skips with a clear message when
that artifact is missing.  The world-join tests additionally skip when
the k11/k14 world products are absent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:                    # tools/ is a namespace pkg
    sys.path.insert(0, str(ROOT))

import tools.artifact_query as aq
from tools.artifact_query import (
    Artifact,
    ArtifactError,
    WorldUnavailable,
    coexist,
    events,
    identity,
    list_species,
    range_info,
    tuning,
    world_join,
)

ARTIFACT_DIR = ROOT / "exp" / "k15_simdiff" / "out" / "seed_00000001"

pytestmark = pytest.mark.skipif(
    not ARTIFACT_DIR.is_dir(),
    reason=f"seed-1 k15 artifact missing at {ARTIFACT_DIR} — regenerate "
           "it with exp/k15_simdiff before running these tests")

K11_NPZ = ROOT / "exp" / "k11_worldgen" / "out" / "seed_00000001" / "world.npz"
K14_NPZ = ROOT / "exp" / "k14_worldprod" / "out" / "seed_00000001" / "derived.npz"

WORLD_PRESENT = K11_NPZ.is_file() and K14_NPZ.is_file()

EVENT_TYPES = {"amend", "merge", "split", "subspecies", "extinct"}
TREE_RANKS = {"kingdom", "phylum", "class", "order", "family", "genus",
              "species", "subspecies"}


@pytest.fixture(scope="module")
def artifact() -> Artifact:
    """One shared artifact per worker: the density parse and the sparse
    cell sets are built once, not once per test."""
    return Artifact(ARTIFACT_DIR)


# ── helpers (independent decodes, kept out of the module under test) ───


def _decode_species_cells(sid: str, a: Artifact) -> set[int]:
    """Independent decode of a species' occupied flat indices directly
    from the raw density.json payload (mirrors the windowed-mask
    convention: box = [y0, y1, x0, x1], Y-first, both ends exclusive,
    row-major)."""
    H, W = a.world_shape()
    cells: set[int] = set()
    for e in a.density()["instances"]:
        if e["sid"] != sid:
            continue
        y0, y1, x0, x1 = e["box"]
        w = x1 - x0
        for i, v in enumerate(e["mask"]):
            if v:
                cells.add((y0 + i // w) * W + (x0 + i % w))
    return cells


def _live_sids(a: Artifact) -> list[str]:
    return sorted({rec["sid"] for rec in a.state()["instances"].values()})


def _largest_live_sid(a: Artifact) -> str:
    per = {}
    for rec in a.state()["instances"].values():
        per[rec["sid"]] = per.get(rec["sid"], 0) + rec["cells"]
    return max(sorted(per), key=lambda s: per[s])


# ── artifact / loading ─────────────────────────────────────────────────


def test_artifact_loads_all_files(artifact):
    st = artifact.state()
    assert st["seed"] == 1
    assert st["world"] == [256, 256]
    assert st["lineages"] == len({r["sid"] for r in st["instances"].values()})
    assert len(artifact.tree()["nodes"]) >= st["lineages"]
    assert len(artifact.reflog()) == st["reflog"]
    assert len(artifact.density()["instances"]) == len(st["instances"])
    gens = {i["generator"] for i in artifact.manifest()["inputs"]}
    assert "k11_worldgen" in gens


def test_missing_artifact_dir_raises():
    with pytest.raises(ArtifactError):
        Artifact(ARTIFACT_DIR / "does-not-exist")


# ── 1. identity ───────────────────────────────────────────────────────


def test_identity_live_species(artifact):
    sid = _largest_live_sid(artifact)
    info = identity(artifact, sid)
    assert info["sid"] == sid
    assert info["rank"] in TREE_RANKS
    assert "binomial" in info and "folk" in info   # None is legitimate
    assert info["axes"]                              # salient trait axes
    assert isinstance(info["nearest_named_ancestor"], (dict, type(None)))
    assert info["alive"] is True
    assert info["instances"] >= 1
    assert info["cells"] >= info["instances"]


def test_identity_extinct_species(artifact):
    live = set(_live_sids(artifact))
    extinct = sorted(n["sid"] for n in artifact.tree()["nodes"]
                     if n.get("rank") == "species" and n["sid"] not in live)
    assert extinct, "artifact has no extinct species nodes"
    info = identity(artifact, extinct[0])
    assert info["alive"] is False
    assert info["instances"] == 0
    assert info["cells"] == 0


def test_identity_unknown_sid_raises(artifact):
    with pytest.raises(ArtifactError):
        identity(artifact, "0000000000000000")


# ── 2. range ──────────────────────────────────────────────────────────


def test_range_matches_independent_decode(artifact):
    sid = _largest_live_sid(artifact)
    info = range_info(artifact, sid)
    cells = _decode_species_cells(sid, artifact)
    assert info["cells"] == len(cells) > 0
    W = artifact.world_shape()[1]
    xs = [c % W for c in cells]
    ys = [c // W for c in cells]
    assert info["bbox"] == [min(xs), max(xs) + 1, min(ys), max(ys) + 1]
    H, W = artifact.world_shape()
    x0, x1, y0, y1 = info["bbox"]
    assert 0 <= x0 < x1 <= W and 0 <= y0 < y1 <= H


def test_range_per_instance_cells_consistent(artifact):
    """The persist invariant: per-instance mask occupancy == the state
    digest's cells count, every instance."""
    st = artifact.state()
    for e in artifact.density()["instances"]:
        assert sum(e["mask"]) == st["instances"][e["iid"]]["cells"]


def test_range_patch_partition(artifact):
    sid = _largest_live_sid(artifact)
    info = range_info(artifact, sid)
    total = sum(size * count for size, count in info["patch_sizes"])
    assert total == info["cells"]
    assert info["components"] == sum(c for _, c in info["patch_sizes"])
    assert info["largest_patch"] == max(info["patch_sizes"])[0]
    assert info["components"] >= 1


def test_range_no_live_instances_raises(artifact):
    live = set(_live_sids(artifact))
    extinct = sorted(n["sid"] for n in artifact.tree()["nodes"]
                     if n.get("rank") == "species" and n["sid"] not in live)
    with pytest.raises(ArtifactError):
        range_info(artifact, extinct[0])


@pytest.mark.skipif(not WORLD_PRESENT,
                    reason=f"world products missing "
                           f"({K11_NPZ} / {K14_NPZ})")
def test_range_world_mix(artifact):
    world = world_join(artifact)
    assert world["seed"] == 1
    assert len(world["biome_map"]) == 256 * 256
    assert len(world["substrate_map"]) == 256 * 256
    info = range_info(artifact, _largest_live_sid(artifact), world)
    for key in ("biomes", "substrates"):
        mix = info[key]
        assert sum(mix.values()) == info["cells"]
        names = set(world["biome_names" if key == "biomes"
                          else "substrate_names"])
        assert set(mix) <= names


def test_world_join_degrades_gracefully(artifact, tmp_path, monkeypatch):
    """A missing world product raises WorldUnavailable (clear message),
    and the CLI 'range --world' degrades to a stderr note instead of
    failing."""
    monkeypatch.setattr(aq, "_repo_root", lambda _dir: tmp_path)
    with pytest.raises(WorldUnavailable):
        world_join(artifact)
    rc = aq.main(["--dir", str(ARTIFACT_DIR), "range",
                  _largest_live_sid(artifact), "--world"])
    assert rc == 0


# ── 3. compositional / coexistence ────────────────────────────────────


def test_coexist_invariants(artifact):
    sid = _largest_live_sid(artifact)
    for share in (0.1, 0.5):
        res = coexist(artifact, sid, share)
        assert res["n_coexist"] == len(res["pairs"])
        for p in res["pairs"]:
            assert p["sid"] != sid
            assert p["overlap"] >= 1
            assert share - 1e-9 <= p["share"] <= 1.0


def test_coexist_threshold_monotone(artifact):
    sid = _largest_live_sid(artifact)
    loose = {p["sid"] for p in coexist(artifact, sid, 0.1)["pairs"]}
    tight = {p["sid"] for p in coexist(artifact, sid, 0.5)["pairs"]}
    assert tight <= loose


def test_coexist_cross_checked_against_independent_decode(artifact):
    """One pair's overlap recomputed from a direct mask decode."""
    sid = _largest_live_sid(artifact)
    res = coexist(artifact, sid, 0.0)
    assert res["n_coexist"] >= 1
    p = res["pairs"][0]
    A = _decode_species_cells(sid, artifact)
    B = _decode_species_cells(p["sid"], artifact)
    overlap = len(A & B)
    assert overlap == p["overlap"]
    # share is rounded to 6 dp in the API
    assert abs(overlap / len(A) - p["share"]) < 1e-5
    assert res["with_any_overlap"] == res["n_coexist"]


def test_coexist_bad_share_raises(artifact):
    sid = _largest_live_sid(artifact)
    with pytest.raises(ArtifactError):
        coexist(artifact, sid, 1.5)
    with pytest.raises(ArtifactError):
        coexist(artifact, sid, -0.1)


def test_coexist_no_live_instances_raises(artifact):
    live = set(_live_sids(artifact))
    extinct = sorted(n["sid"] for n in artifact.tree()["nodes"]
                     if n.get("rank") == "species" and n["sid"] not in live)
    with pytest.raises(ArtifactError):
        coexist(artifact, extinct[0], 0.5)


# ── 4. events ─────────────────────────────────────────────────────────


def test_events_sequence_consistency(artifact):
    log = artifact.reflog()
    sid = max(_live_sids(artifact), key=lambda s: sum(
        1 for e in log if e.get("sid") == s or e.get("parent_sid") == s))
    res = events(artifact, sid)
    assert "round stamp" in res["note"].lower() or "round" in res["note"]
    assert res["total"] == len(res["entries"])
    assert res["total"] >= 1
    seqs = [e["seq"] for e in res["entries"]]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    for e in res["entries"]:
        assert e["event"] in EVENT_TYPES
        raw = log[e["seq"]]
        if e["role"] == "own":
            assert raw.get("sid") == sid
        else:
            assert raw.get("parent_sid") == sid


def test_events_limit(artifact):
    sid = _largest_live_sid(artifact)
    res = events(artifact, sid, limit=3)
    assert len(res["entries"]) == min(3, res["total"])
    assert [e["seq"] for e in res["entries"]] == \
        [e["seq"] for e in events(artifact, sid)["entries"][:3]]


def test_events_no_round_stamps(artifact):
    """The reflog carries no round field — seq index is the ordering."""
    for e in artifact.reflog()[:20]:
        assert "round" not in e


# ── 5. tuning ─────────────────────────────────────────────────────────


def test_tuning_all_species(artifact):
    res = tuning(artifact)
    assert "capacity" in res["note"]
    assert res["lineages"] == artifact.state()["lineages"]
    assert res["instances"] == len(artifact.state()["instances"])
    assert len(res["per_sid"]) == res["lineages"]
    total_cells = sum(d["cells"] for d in res["per_sid"].values())
    assert total_cells == sum(r["cells"]
                              for r in artifact.state()["instances"].values())


def test_tuning_one_species(artifact):
    sid = _largest_live_sid(artifact)
    res = tuning(artifact, sid)
    assert res["sid"] == sid
    assert res["instances"] == len(res["rows"]) >= 1
    mine = [(iid, rec) for iid, rec in
            artifact.state()["instances"].items() if rec["sid"] == sid]
    assert res["cells"] == sum(rec["cells"] for _, rec in mine)
    assert res["mass"] == pytest.approx(sum(rec["mass"] for _, rec in mine),
                                        abs=1e-4)
    assert [r["iid"] for r in res["rows"]] == sorted(iid for iid, _ in mine)


# ── discovery + determinism ───────────────────────────────────────────


def test_list_species(artifact):
    res = list_species(artifact)
    assert res["live"] == artifact.state()["lineages"] == 107
    rows = res["rows"]
    assert len(rows) == 107
    cells = [r["cells"] for r in rows]
    assert cells == sorted(cells, reverse=True)      # desc by cells
    for r in rows:
        assert r["rank"] in TREE_RANKS
        assert r["binomial"] is None or isinstance(r["binomial"], str)


def test_deterministic_across_instances(artifact):
    sid = _largest_live_sid(artifact)
    fresh = Artifact(ARTIFACT_DIR)                   # independent load
    assert range_info(artifact, sid) == range_info(fresh, sid)
    assert coexist(artifact, sid, 0.1) == coexist(fresh, sid, 0.1)


def test_cell_sets_sparse(artifact):
    """The density payload decodes to sparse cell-index sets — far below
    any (n_species, H, W) materialization (65536 cells)."""
    sets = artifact.cell_sets()
    assert len(sets) == artifact.state()["lineages"]
    total = sum(len(s) for s in sets.values())
    assert total <= 10 * 256 * 256
    assert all(0 <= idx < 256 * 256 for s in sets.values() for idx in s)


# ── CLI surface ───────────────────────────────────────────────────────


def test_cli_identity_json(capsys):
    sid = _largest_live_sid(Artifact(ARTIFACT_DIR))
    rc = aq.main(["--dir", str(ARTIFACT_DIR), "identity", sid])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["sid"] == sid


def test_cli_unknown_sid_fails(capsys):
    rc = aq.main(["--dir", str(ARTIFACT_DIR), "identity", "0000000000000000"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "no tree node" in captured.err


def test_cli_missing_dir_fails(capsys):
    rc = aq.main(["--dir", str(ROOT / "nope"), "list"])
    captured = capsys.readouterr()
    assert rc == 1
    assert "artifact directory not found" in captured.err
