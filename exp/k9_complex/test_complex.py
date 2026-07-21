"""K9 acceptance tests — the 10-item test list from the spec."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from kernel.complex.audit import audit
from kernel.complex.cells import Complex, Edge, Node, Patch
from kernel.complex.constraints import (
    AND,
    adjacent_to_edge_kind,
    evaluate,
    measure,
    sector,
)
from kernel.complex.cover import (
    CoverState,
    latent_rot,
    summon_eligible,
    transition as cover_transition,
)
from exp.k9_complex.fixtures import build_clean_complex, build_defect_complex
from kernel.complex.history import ComplexHistory, _apply_commit
from kernel.complex.refine import split_edge, split_patch
from kernel.gmm_dynamics.dynamics import DriftField


# ---- 1. Incidence integrity --------------------------------------------------

class TestIncidence:
    def test_neighbors(self):
        c = build_clean_complex()
        nbrs = c.neighbors("settlement")
        assert set(nbrs) == {
            "ford", "northeast", "crossroads",
            "southeast", "southwest", "bridge",
        }

    def test_shared_boundary(self):
        c = build_clean_complex()
        sb = c.shared_boundary("north_field", "west_pasture")
        assert sb == {"e_road_ford"}

        sb2 = c.shared_boundary("north_field", "east_wood")
        assert sb2 == {"e_road_ne"}

        # non-adjacent
        sb3 = c.shared_boundary("north_field", "south_meadow")
        assert sb3 == set()

    def test_graph_distance(self):
        c = build_clean_complex()
        # settlement to ford: direct road, length=7.07
        d = c.graph_distance("settlement", "ford")
        assert d == pytest.approx(7.0710678, rel=1e-6)

        # ford to northeast: river, length=10.0
        d2 = c.graph_distance("ford", "northeast")
        assert d2 == pytest.approx(10.0, rel=1e-6)

        # same node
        assert c.graph_distance("settlement", "settlement") == 0.0


# ---- 2. Subdivision ----------------------------------------------------------

class TestSubdivision:
    def test_parentage_set(self):
        c = build_clean_complex()
        children = [
            (DriftField(mu=(2.0, 0.5), theta=(0.2, 0.15), sigma=(0.3, 0.35)), 4.0),
            (DriftField(mu=(2.0, 0.0), theta=(0.2, 0.1), sigma=(0.3, 0.3)), 4.5),
            (DriftField(mu=(1.5, 0.0), theta=(0.15, 0.1), sigma=(0.25, 0.3)), 4.0),
        ]
        detail = Edge(
            id="e_detail", node_a="settlement", node_b="crossroads",
            length=0.5, kind="path", quality=0.1,
        )
        commit = split_patch(c, "east_wood", children, [detail])
        for child in commit["children"]:
            assert child["parent"] == "east_wood"

    def test_measure_conservation_enforced(self):
        c = build_clean_complex()
        # children don't sum to parent measure
        children_bad = [
            (DriftField(mu=(2.0, 0.5), theta=(0.2, 0.15), sigma=(0.3, 0.35)), 5.0),
            (DriftField(mu=(2.0, 0.0), theta=(0.2, 0.1), sigma=(0.3, 0.3)), 5.0),
        ]
        with pytest.raises(ValueError, match="do not sum to parent"):
            split_patch(c, "east_wood", children_bad, [])

    def test_child_fields_distinct(self):
        c = build_clean_complex()
        children = [
            (DriftField(mu=(2.0, 0.5), theta=(0.2, 0.15), sigma=(0.3, 0.35)), 4.0),
            (DriftField(mu=(2.0, 0.0), theta=(0.2, 0.1), sigma=(0.3, 0.3)), 4.5),
            (DriftField(mu=(1.5, 0.0), theta=(0.15, 0.1), sigma=(0.25, 0.3)), 4.0),
        ]
        commit = split_patch(c, "east_wood", children, [])
        child_mus = [tuple(ch["field_mu"]) for ch in commit["children"]]
        assert len(set(child_mus)) == 3


# ---- 3. Never-rewire ---------------------------------------------------------

class TestNeverRewire:
    def test_edge_endpoints_preserved(self):
        c = build_clean_complex()
        children = [
            (DriftField(mu=(2.0, 0.5), theta=(0.2, 0.15), sigma=(0.3, 0.35)), 4.0),
            (DriftField(mu=(2.0, 0.0), theta=(0.2, 0.1), sigma=(0.3, 0.3)), 4.5),
            (DriftField(mu=(1.5, 0.0), theta=(0.15, 0.1), sigma=(0.25, 0.3)), 4.0),
        ]
        detail = Edge(
            id="e_detail", node_a="settlement", node_b="crossroads",
            length=0.5, kind="path", quality=0.1,
        )
        commit = split_patch(c, "east_wood", children, [detail])

        history = ComplexHistory(c)
        history.add(commit)
        after = history.at_latest()

        # All original edges (except the split patch's boundary edges which
        # are preserved) must have same endpoints
        for eid, orig in c.edges.items():
            if eid in after.edges:
                new = after.edges[eid]
                assert (new.node_a, new.node_b) == (orig.node_a, orig.node_b), \
                    f"Edge {eid} was rewired"


# ---- 4. Split edge -----------------------------------------------------------

class TestSplitEdge:
    def test_child_lengths_sum_to_parent(self):
        c = build_clean_complex()
        new_node = Node(id="mid_river", pos=(5.0, 10.0))
        commit = split_edge(c, "e_river_north", at_s=3.0, new_node=new_node)

        child_a_len = commit["child_a"]["length"]
        child_b_len = commit["child_b"]["length"]
        assert child_a_len + child_b_len == pytest.approx(10.0)

    def test_new_node_degree_2(self):
        c = build_clean_complex()
        new_node = Node(id="mid_river", pos=(5.0, 10.0))
        commit = split_edge(c, "e_river_north", at_s=3.0, new_node=new_node)

        history = ComplexHistory(c)
        history.add(commit)
        after = history.at_latest()

        # new node should have degree 2 (connected by the two child edges)
        deg = after.degree("mid_river")
        assert deg == 2

    def test_rejects_at_s_out_of_range(self):
        c = build_clean_complex()
        new_node = Node(id="mid_river", pos=(5.0, 5.0))
        with pytest.raises(ValueError, match="must be in"):
            split_edge(c, "e_river_north", at_s=0.0, new_node=new_node)
        with pytest.raises(ValueError, match="must be in"):
            split_edge(c, "e_river_north", at_s=10.0, new_node=new_node)


# ---- 5. Cover transitions ----------------------------------------------------

class TestCoverTransitions:
    def test_each_legal_transition(self):
        # UNREFINED → REFINED_UNOBSERVED
        cover_transition(CoverState.UNREFINED, CoverState.REFINED_UNOBSERVED)
        # REFINED_UNOBSERVED → OBSERVED
        cover_transition(CoverState.REFINED_UNOBSERVED, CoverState.OBSERVED)
        # UNREFINED → OBSERVED
        cover_transition(CoverState.UNREFINED, CoverState.OBSERVED)

    def test_every_illegal_raises(self):
        # All 3×3 pairs; only 3 are legal, so 6 should raise
        all_states = list(CoverState)
        legal = {
            (CoverState.UNREFINED, CoverState.REFINED_UNOBSERVED),
            (CoverState.REFINED_UNOBSERVED, CoverState.OBSERVED),
            (CoverState.UNREFINED, CoverState.OBSERVED),
        }
        for before in all_states:
            for after in all_states:
                if (before, after) in legal:
                    continue
                with pytest.raises(ValueError):
                    cover_transition(before, after)


# ---- 6. Summon-eligibility ---------------------------------------------------

class TestSummonEligibility:
    def test_observed_in_set_returns_false(self):
        cover = {
            "north_field": CoverState.OBSERVED,
            "east_wood": CoverState.UNREFINED,
        }
        assert not summon_eligible({"north_field", "east_wood"}, cover)

    def test_clean_set_returns_true(self):
        cover = {
            "north_field": CoverState.UNREFINED,
            "east_wood": CoverState.UNREFINED,
        }
        assert summon_eligible({"north_field", "east_wood"}, cover)


# ---- 7. Latent rot -----------------------------------------------------------

class TestLatentRot:
    def test_flips_when_unrefined_measure_below_min(self):
        c = build_clean_complex()
        cells = {"north_field", "south_meadow"}
        cover = {
            "north_field": CoverState.UNREFINED,
            "south_meadow": CoverState.UNREFINED,
        }

        # total unrefined = 25 + 25 = 50
        # min_measure = 30 → not rotten
        assert not latent_rot(cells, cover, 30.0, c)

        # observe north_field → unrefined = 25 (< 30) → rotten
        cover["north_field"] = CoverState.OBSERVED
        assert latent_rot(cells, cover, 30.0, c)

    def test_rot_stays_false_if_enough_measure(self):
        c = build_clean_complex()
        cells = {"north_field", "east_wood", "south_meadow"}
        cover = {pid: CoverState.UNREFINED for pid in cells}
        # total measure = 25 + 12.5 + 25 = 62.5
        # min_measure = 12.0 → observing one still leaves 50 → not rotten
        cover["east_wood"] = CoverState.OBSERVED
        assert not latent_rot(cells, cover, 12.0, c)


# ---- 8. Audit ----------------------------------------------------------------

class TestAudit:
    def test_each_defect_class_caught(self):
        d = build_defect_complex()
        defects = audit(d)
        defect_text = " ".join(defects)
        assert "dangling" in defect_text
        assert "isolated" in defect_text
        assert "nodeless_intersection" in defect_text

    def test_clean_fixture_clean(self):
        c = build_clean_complex()
        defects = audit(c)
        assert len(defects) == 0

    def test_nodeless_on_cross_not_on_shared_node(self):
        c = build_clean_complex()
        # The crossing edges share a node (e.g., settlement) — the crossing
        # test should NOT fire since the node is shared at the intersection.
        # Verify that the clean fixture's polylines (which converge at ford etc.)
        # don't produce false positives.
        defect_text = " ".join(audit(c))
        assert "nodeless_intersection" not in defect_text


# ---- 9. Versioning -----------------------------------------------------------

class TestVersioning:
    def test_at_0_equals_initial(self):
        c = build_clean_complex()
        h = ComplexHistory(c)
        assert h.at(0) == c

    def test_at_latest_after_commits(self):
        c = build_clean_complex()
        h = ComplexHistory(c)
        children = [
            (DriftField(mu=(2.0, 0.5), theta=(0.2, 0.15), sigma=(0.3, 0.35)), 4.0),
            (DriftField(mu=(2.0, 0.0), theta=(0.2, 0.1), sigma=(0.3, 0.3)), 4.5),
            (DriftField(mu=(1.5, 0.0), theta=(0.15, 0.1), sigma=(0.25, 0.3)), 4.0),
        ]
        commit = split_patch(c, "east_wood", children, [])
        h.add(commit)
        assert h.at_latest() == h.at(1)

    def test_reconstruction_is_replay(self):
        c = build_clean_complex()
        h = ComplexHistory(c)
        children = [
            (DriftField(mu=(2.0, 0.5), theta=(0.2, 0.15), sigma=(0.3, 0.35)), 4.0),
            (DriftField(mu=(2.0, 0.0), theta=(0.2, 0.1), sigma=(0.3, 0.3)), 4.5),
            (DriftField(mu=(1.5, 0.0), theta=(0.15, 0.1), sigma=(0.25, 0.3)), 4.0),
        ]
        commit = split_patch(c, "east_wood", children, [])
        h.add(commit)

        replay = _apply_commit(c, commit)
        assert replay == h.at(1)


# ---- 10. Determinism ---------------------------------------------------------

class TestDeterminism:
    def test_fixture_identical_on_rebuild(self):
        a = build_clean_complex()
        b = build_clean_complex()
        assert a == b

    def test_audit_output_identical(self):
        a = build_defect_complex()
        b = build_defect_complex()
        assert audit(a) == audit(b)

    def test_demo_json_byte_identical(self):
        """Run the demo twice with --json and compare."""
        cmd = [sys.executable, "-m", "exp.k9_complex", "demo", "--seed", "1", "--json"]
        r1 = subprocess.run(cmd, capture_output=True, text=True)
        r2 = subprocess.run(cmd, capture_output=True, text=True)
        assert r1.returncode == 0
        assert r2.returncode == 0
        assert r1.stdout == r2.stdout
