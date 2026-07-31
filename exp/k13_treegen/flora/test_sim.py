"""Flora KingdomSim tests — the K15 sim contract, organism side.

Covers: protocol conformance (duck-typed against interface.KingdomSim),
the req_flora DerivedView from derive(), select() routing (shortfall
weighting, no-responder and unknown names, [niche] metadata never
pressured, the split one-sided pH direction), mutate() (determinism,
bounds, discrete threshold + pinned switch, anthocyanin ⊥ betalain,
generic switches), and provisional vital rates (tree vs duckweed).

Run: uv run pytest -q exp/k13_treegen/flora/
"""

from __future__ import annotations

import inspect
import pathlib

import pytest

from exp.k13_treegen.flora.content import load_content, merged_preset
from exp.k13_treegen.flora.sim import DISCRETE_THRESHOLD, FloraSim
from exp.k13_treegen.interface import Instance, StressVerdict
from kernel.hashrng import Stream

CONTENT = pathlib.Path(__file__).parent.parent / "content" / "flora"

# The DerivedView keys req_flora.py documents (its comment block), plus
# the adapter's submerged flag. Hardcoded here so the test reads the
# documented vocabulary directly (req_flora itself carries only comments).
REQ_VIEW_KEYS = (
    "temp_opt_c", "temp_breadth_c", "moisture_opt", "moisture_breadth",
    "drought_tolerance", "waterlogging_tolerance", "salinity_tolerance",
    "ph_tolerance", "fertility_requirement", "growing_season_req",
    "root_depth_m", "height_m", "woodiness",
    "photosynthesis", "winter_deciduous", "leafout_month",
    "drought_deciduous", "bloom_start_month", "bloom_length_months",
    "medium", "anchoring_need", "holdfast", "submerged",
)
# [niche] metadata keys — clade metadata, never a driftable trait.
NICHE_KEYS = ("temp_opt_c", "temp_breadth_c", "moisture_opt",
              "moisture_breadth")


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


@pytest.fixture(scope="module")
def sim(pack):
    return FloraSim(pack)


def _traits(pack, preset_id: str) -> dict:
    """Flat WIP-gene mapping the way the tree's mint hands it out: axes +
    generics + the plan/preset keys (see sim.py contract notes)."""
    preset = pack.presets[preset_id]
    axes, generics = merged_preset(pack, preset)
    return {**axes, **generics, "plan": preset["preset"]["plan"],
            "preset": preset_id}


# ── protocol conformance ──────────────────────────────────────────────


def test_protocol_conformance(sim):
    """FloraSim exposes the four KingdomSim methods with the protocol's
    signatures (duck-typed: the sim calls them by name and keywords)."""
    expected = {
        "derive": ["traits", "pack"],
        "select": ["verdict", "traits", "pack"],
        "mutate": ["x", "rng"],
        "vital": ["traits", "pack"],
    }
    for name, params in expected.items():
        m = getattr(sim, name)
        assert callable(m), name
        sig = inspect.signature(m)
        got = [p.name for p in sig.parameters.values() if p.name != "self"]
        assert got == params, (name, got)


# ── derive: the DerivedView ───────────────────────────────────────────


def test_derive_oak_has_all_req_keys(sim, pack):
    view = sim.derive(_traits(pack, "tree.oak"), pack)
    assert isinstance(view, dict)
    for key in REQ_VIEW_KEYS:
        assert key in view, key


def test_derive_medium_gating_land_vs_aquatic(sim, pack):
    """A land plan (oak) and an aquatic plan (kelp) differ on medium and
    every medium-gating key the adapter reads."""
    oak = sim.derive(_traits(pack, "tree.oak"), pack)
    kelp = sim.derive(_traits(pack, "macroalgae_holdfast.kelp"), pack)
    assert oak["medium"] == "land"
    assert kelp["medium"] == "water"
    assert oak["anchoring_need"] > kelp["anchoring_need"]   # 1.0 vs 0.0
    assert oak["holdfast"] == 0 and kelp["holdfast"] == 1
    assert oak["submerged"] == 0 and kelp["submerged"] == 1
    assert oak["winter_deciduous"] == 1 and kelp["winter_deciduous"] == 0
    assert kelp["photosynthesis"] == "C3"


# ── select ────────────────────────────────────────────────────────────


def test_select_water_shortfall_weights(sim, pack):
    """The worse the suitability factor, the harder the push: 0.2 pushes
    drought_tolerance upward more than 0.8."""
    traits = _traits(pack, "tree.oak")
    weak = sim.select(StressVerdict(s=0.0,
                                    provenance={"pressure:water": 0.8}),
                      traits, pack)
    strong = sim.select(StressVerdict(s=0.0,
                                      provenance={"pressure:water": 0.2}),
                        traits, pack)
    assert 0.0 < weak["drought_tolerance"] < strong["drought_tolerance"]
    assert strong["succulence"] > 0.0


def test_select_no_responder_yields_empty(sim, pack):
    """pressure:climate has no driftable responder (its terms are the
    never-drifting [niche] metadata) — the pressure plane stays empty."""
    traits = _traits(pack, "tree.oak")
    p = sim.select(StressVerdict(s=0.0,
                                 provenance={"pressure:climate": 0.1}),
                   traits, pack)
    assert p == {}
    p = sim.select(StressVerdict(s=0.0,
                                 provenance={"pressure:medium": 0.1}),
                   traits, pack)
    assert p == {}


def test_select_unknown_names_do_not_crash(sim, pack):
    traits = _traits(pack, "tree.oak")
    for prov in ({"pressure:bogus": 0.1}, {"pull:food": 0.9},
                 {"ley:radiation": 0.5}, {"lift:sand": 0.3},
                 {"bogus": 0.1}):
        p = sim.select(StressVerdict(s=0.0, provenance=prov), traits, pack)
        assert isinstance(p, dict) and not p, prov
    # plain names are the defensive class per the interface ruling
    p = sim.select(StressVerdict(s=0.0, provenance={"water": 0.2}),
                   traits, pack)
    assert p["drought_tolerance"] > 0.0


def test_select_never_pressures_niche_metadata(sim, pack):
    traits = _traits(pack, "tree.oak")
    for prov in ({"pressure:climate": 0.1}, {"pressure:ph_low": 0.2},
                 {"pressure:water": 0.2}):
        p = sim.select(StressVerdict(s=0.0, provenance=prov), traits, pack)
        assert not (set(p) & set(NICHE_KEYS)), (prov, p)


def test_select_ph_split_direction(sim, pack):
    """The pH requirement is split one-sided env-side (req_flora ruling
    2026-08-01): pressure:ph_low (cell too acidic for the position)
    pushes ph_tolerance UP; pressure:ph_high (too alkaline) pushes it
    DOWN — the factor carries the side, no hedge needed."""
    traits = _traits(pack, "tree.oak")
    p = sim.select(StressVerdict(s=0.0,
                                 provenance={"pressure:ph_low": 0.2}),
                   traits, pack)
    assert p["ph_tolerance"] > 0.0
    p = sim.select(StressVerdict(s=0.0,
                                 provenance={"pressure:ph_high": 0.2}),
                   traits, pack)
    assert p["ph_tolerance"] < 0.0


def test_select_rooting_pushes_shallower(sim, pack):
    """pressure:rooting is a saturating excess of root_depth_m over
    eff_rooting_m (B5 §4.3): low suitability means roots too deep for
    the soil, so the drift must push root_depth_m DOWN, not up."""
    traits = _traits(pack, "tree.oak")
    p = sim.select(StressVerdict(s=0.0,
                                 provenance={"pressure:rooting": 0.2}),
                   traits, pack)
    assert p["root_depth_m"] < 0.0


def test_select_bloom_frost_routes_phenology(sim, pack):
    traits = _traits(pack, "tree.oak")
    p = sim.select(StressVerdict(s=0.0,
                                 provenance={"pressure:bloom_frost": 0.2}),
                   traits, pack)
    assert p["bloom_start_month"] > 0.0        # later window
    assert p["leafout_month"] > 0.0            # later leafout
    assert p["bloom_length_months"] < 0.0      # shorter window
    assert p["deciduous_trigger"] > 0.0        # toward winter
    assert p["phenology"] > 0.0                # generic, toward winter


# ── mutate ────────────────────────────────────────────────────────────


def _mutated(pack, traits, pressure, seed, context="ctx"):
    x = Instance("s", "i", traits=dict(traits), pressure=dict(pressure))
    FloraSim(pack).mutate(x, Stream(seed, "mut", context))
    return x


def test_mutate_deterministic(pack):
    """Same Stream seed -> identical trait outcomes across two runs, and
    the pressure plane is cleared."""
    traits = _traits(pack, "tree.oak")
    traits["deciduous_trigger"] = "none"
    pressure = {"drought_tolerance": 2.0, "deciduous_trigger": 3.0}
    a = _mutated(pack, traits, pressure, 7)
    b = _mutated(pack, traits, pressure, 7)
    assert a.traits == b.traits
    assert a.pressure == {}


def test_mutate_continuous_respects_bounds(pack):
    traits = _traits(pack, "tree.oak")
    x = _mutated(pack, traits, {"drought_tolerance": 1e6}, 1)
    assert 0.0 <= x.traits["drought_tolerance"] <= 1.0
    x = _mutated(pack, traits, {"drought_tolerance": -1e6}, 1)
    assert 0.0 <= x.traits["drought_tolerance"] <= 1.0
    # int month axes stay inside their [1, 12] bounds too
    x = _mutated(pack, traits, {"leafout_month": 1e6}, 1)
    assert 1 <= x.traits["leafout_month"] <= 12
    x = _mutated(pack, traits, {"leafout_month": -1e6}, 1)
    assert 1 <= x.traits["leafout_month"] <= 12


def test_mutate_discrete_below_threshold_stays(pack):
    for seed in range(30):
        traits = _traits(pack, "tree.oak")
        traits["deciduous_trigger"] = "none"
        x = _mutated(pack, traits,
                     {"deciduous_trigger": 0.5 * DISCRETE_THRESHOLD}, seed)
        assert x.traits["deciduous_trigger"] == "none", seed


def test_mutate_discrete_switch_pinned(pack):
    """Past the threshold, pressure becomes switch propensity: find a
    Stream seed that flips deciduous_trigger and pin it — the pinned
    seed must flip on every replay."""
    pinned = None
    for seed in range(300):
        traits = _traits(pack, "tree.oak")
        traits["deciduous_trigger"] = "none"
        x = _mutated(pack, traits, {"deciduous_trigger": 3.0}, seed)
        if x.traits["deciduous_trigger"] == "winter":
            pinned = seed
            break
    assert pinned is not None, "no switch found in 300 seeds"
    for _ in range(3):
        traits = _traits(pack, "tree.oak")
        traits["deciduous_trigger"] = "none"
        x = _mutated(pack, traits, {"deciduous_trigger": 3.0}, pinned)
        assert x.traits["deciduous_trigger"] == "winter"


def test_mutate_generic_switch(pack):
    """Plan generics switch the same way, targets bounded by the plan's
    permission table (phenology -> winter_deciduous is tree-legal)."""
    pinned = None
    for seed in range(300):
        traits = _traits(pack, "tree.oak")
        traits["phenology"] = "evergreen"
        x = _mutated(pack, traits, {"phenology": 3.0}, seed)
        if x.traits["phenology"] == "winter_deciduous":
            pinned = seed
            break
    assert pinned is not None, "no generic switch found in 300 seeds"
    traits = _traits(pack, "tree.oak")
    traits["phenology"] = "evergreen"
    x = _mutated(pack, traits, {"phenology": 3.0}, pinned)
    assert x.traits["phenology"] == "winter_deciduous"


def test_mutate_anthocyanin_never_betalain(pack):
    """B5 §8.6: switching pigment_pathway is bounded by the constraint
    gate — an anthocyanin record (bee syndrome, showy pigment rule
    firing) can only reach a pigment that is not betalain."""
    from exp.k13_treegen.flora.derive import PIGMENT_PATHWAYS
    outcomes = set()
    for seed in range(60):
        traits = _traits(pack, "tree.oak")
        traits.update({"pollination_syndrome": "bee",
                       "pigment_pathway": "anthocyanin",
                       "flower_size_mm": 12.0})
        x = _mutated(pack, traits, {"pigment_pathway": 8.0}, seed)
        v = x.traits["pigment_pathway"]
        assert v in PIGMENT_PATHWAYS
        assert v != "betalain", seed
        outcomes.add(v)
    assert outcomes <= {"anthocyanin", "carotenoid"}


# ── vital ─────────────────────────────────────────────────────────────


def test_vital_tree_vs_duckweed(sim, pack):
    """PROVISIONAL rates: a duckweed's rain->established conversion and
    per-capita birth dwarf an oak's; the oak's death rate is far lower."""
    oak = sim.vital(_traits(pack, "tree.oak"), pack)
    duck = sim.vital(_traits(pack, "floater.duckweed"), pack)
    assert duck.establish > oak.establish
    assert duck.birth > oak.birth
    assert 0.0 < oak.death < duck.death
    assert 0.0 < oak.birth
