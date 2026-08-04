"""Fast-tier tests for exp/k15_biosphere (ticket 0035).

Per-case reality ranges, the all-14-plans-positive guarantee, tree
monotonicity, zero-height ⇒ zero mass, tree proportions, and the unknown-
plan guard.  Plain pytest, no marks — runs in milliseconds.
"""

from __future__ import annotations

import pytest

from exp.k15_biosphere.flora.mass import PLANS, percap_biomass
from exp.k15_biosphere.flora.reality import CASES, evaluate

# Reasonable axes per plan for the positive-mass guarantee.
REASONABLE_AXES = {
    "tree": {"height_m": 12.0, "crown_spread_m": 5.0, "wood_density": 0.6},
    "shrub": {"height_m": 1.5, "crown_spread_m": 1.8, "woodiness": 0.4},
    "herb_forb": {"height_m": 0.4, "crown_spread_m": 0.25},
    "grass_sward": {"height_m": 0.3, "crown_spread_m": 0.2},
    "rosette_mat": {"height_m": 0.1, "crown_spread_m": 0.3},
    "succulent": {"height_m": 0.8, "crown_spread_m": 0.5},
    "fern_grade": {"height_m": 0.6, "crown_spread_m": 0.4},
    "moss_grade": {"height_m": 0.1, "crown_spread_m": 0.2},
    "runner_meadow": {"height_m": 0.5, "crown_spread_m": 0.3},
    "floating_leaf": {"height_m": 0.05, "crown_spread_m": 0.4},
    "floater": {"height_m": 0.02, "crown_spread_m": 0.2},
    "macroalgae_holdfast": {"height_m": 5.0, "crown_spread_m": 0.5},
    "fungus": {"height_m": 0.1, "crown_spread_m": 0.0},
    "lichen": {"height_m": 0.02, "crown_spread_m": 0.3},
}


def _case_results() -> dict:
    return {r["name"]: r for r in evaluate()}


@pytest.mark.parametrize("name", [c["name"] for c in CASES])
def test_reality_case_in_range(name):
    """One test per reality case: computed flux within the locked range."""
    r = _case_results()[name]
    assert r["lo"] <= r["computed"] <= r["hi"], (
        f"{name}: {r['computed']:.4f} {r['unit']} outside "
        f"[{r['lo']:.4f}, {r['hi']:.4f}] {r['unit']}"
    )


@pytest.mark.parametrize("plan", PLANS)
def test_all_plans_positive_mass(plan):
    """Every plan yields positive dry mass for reasonable axes."""
    est = percap_biomass(REASONABLE_AXES[plan], plan)
    assert est.total_kg > 0.0
    assert est.agb_kg > 0.0


@pytest.mark.parametrize("plan", PLANS)
def test_zero_height_zero_mass(plan):
    """Height 0 (or missing) means no organism: zero mass for every plan."""
    est = percap_biomass({"height_m": 0.0}, plan)
    assert est.total_kg == 0.0
    assert est.agb_kg == 0.0
    assert percap_biomass({}, plan).total_kg == 0.0


def test_tree_mass_increases_with_height():
    base = {"crown_spread_m": 5.0, "wood_density": 0.6}
    low = percap_biomass({**base, "height_m": 10.0}, "tree").total_kg
    high = percap_biomass({**base, "height_m": 20.0}, "tree").total_kg
    assert high > low


def test_tree_mass_increases_with_crown():
    base = {"height_m": 12.0, "wood_density": 0.6}
    low = percap_biomass({**base, "crown_spread_m": 4.0}, "tree").total_kg
    high = percap_biomass({**base, "crown_spread_m": 8.0}, "tree").total_kg
    assert high > low


def test_tree_mass_increases_with_wood_density():
    base = {"height_m": 12.0, "crown_spread_m": 5.0}
    low = percap_biomass({**base, "wood_density": 0.5}, "tree").total_kg
    high = percap_biomass({**base, "wood_density": 0.7}, "tree").total_kg
    assert high > low


def test_tree_proportions_exposed():
    est = percap_biomass(
        {"height_m": 25.0, "crown_spread_m": 14.0, "wood_density": 0.6},
        "tree", "broadleaf",
    )
    assert "dbh_m" in est.proportions
    assert "crown_dbh_ratio" in est.proportions
    assert est.proportions["dbh_m"] == pytest.approx(14.0 / 18.0)
    assert est.proportions["crown_dbh_ratio"] == pytest.approx(18.0)


def test_unknown_plan_raises():
    with pytest.raises(ValueError):
        percap_biomass({"height_m": 1.0}, "dragon")


def test_unknown_tree_form_raises():
    with pytest.raises(ValueError):
        percap_biomass({"height_m": 10.0, "crown_spread_m": 4.0}, "tree", "bogus")
