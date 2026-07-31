"""Smoke tests for the organism-side sim contract (interface.py).

The module is a contract/stub: no env implementation and no commit
engine exist yet. These tests pin the settled parts — the X working
copy and its flat parse, the verdict stub, the changelog shape, the
duck-typed authorities, and the new SUBSPECIES rank — so the seams
are exercised before K15 lands.
"""

from __future__ import annotations

from exp.k13_treegen.interface import (
    ChangeLog,
    Instance,
    InstanceDelta,
    InstanceView,
    KingdomSim,
    Outcome,
    Population,
    SpawnRequest,
    StressFn,
    StressVerdict,
    TreeAuthority,
    TraitPressure,
    VitalRates,
)
from exp.k13_treegen.model import RANK_PREFIX, Rank


def _fake_stress(view, cell, month):
    assert hasattr(view, "keys")
    return StressVerdict(s=0.5, provenance={"predation:avian": 0.25})


# ──  stress stub  ─────────────────────────────────────────────────────


def test_stress_verdict_defaults():
    v = StressVerdict(s=-1.0)
    assert v.s == -1.0
    assert dict(v.provenance) == {}
    assert v.__dataclass_params__.frozen  # verdicts are immutable


def test_stress_fn_seam_accepts_duck_type():
    fn: StressFn = _fake_stress
    v = fn({"temp_opt_c": 15.0}, cell=object(), month=6)
    assert -1.0 <= v.s <= 1.0
    assert all(0.0 <= f <= 1.0 for f in v.provenance.values())


# ──  X working copy  ──────────────────────────────────────────────────


def test_instance_carries_wip_genes_and_parses_flat():
    x = Instance(species_id="ab" * 8, instance_id="inst0001",
                 traits={"temp_opt": 12.0})
    x.traits["temp_opt"] = 13.5           # WIP genes amend freely
    x.pressure["temp_opt"] = -0.2         # pressure accumulates
    view = x.view(mass=420.0)
    assert isinstance(view, InstanceView)
    assert view.species_id == x.species_id
    assert view.instance_id == "inst0001"
    assert view.traits == {"temp_opt": 13.5}
    assert view.mass == 420.0
    assert "pressure" not in view.traits  # plane stays organism-side


def test_view_is_a_copy_not_an_alias():
    x = Instance(species_id="s", instance_id="i", traits={"a": 1.0})
    view = x.view(mass=0.0)
    x.traits["a"] = 2.0
    assert view.traits["a"] == 1.0


# ──  population & vital rates  ────────────────────────────────────────


def test_population_two_density_defaults():
    p = Population()
    assert p.rain == 0.0 and p.established == 0.0
    p.rain += 1.0
    assert p.rain == 1.0


def test_vital_rates_defaults():
    vr = VitalRates()
    assert (vr.birth, vr.death, vr.establish) == (0.0, 0.0, 0.0)


# ──  changelog & spawn  ───────────────────────────────────────────────


def test_changelog_shape():
    log = ChangeLog(
        instances=(
            InstanceDelta(instance_id="i1", outcome=Outcome.KEEP,
                          orthodox=True),
            InstanceDelta(instance_id="i2", outcome=Outcome.SPLIT,
                          target="cd" * 8),
            InstanceDelta(instance_id="i3", outcome=Outcome.MERGE,
                          target="i1"),
        ),
        extinct_species=("ef" * 8,),
        spawns=(SpawnRequest(species_id="00" * 8, hint="origin"),),
    )
    by_id = {d.instance_id: d for d in log.instances}
    assert by_id["i1"].orthodox and by_id["i1"].target is None
    assert by_id["i2"].outcome is Outcome.SPLIT
    assert by_id["i3"].target == "i1"
    assert log.extinct_species == ("ef" * 8,)
    assert log.spawns[0].hint == "origin"


# ──  the authorities, duck-typed  ─────────────────────────────────────


def test_kingdom_sim_protocol_shape():
    class FakeKingdom:
        def derive(self, traits, pack):
            return {"temp_opt_c": traits.get("temp_opt", 0.0)}

        def select(self, verdict, traits, pack):
            return {"temp_opt": -verdict.s}

        def mutate(self, x, rng):
            for k, p in x.pressure.items():
                x.traits[k] = x.traits.get(k, 0.0) + p
            x.pressure.clear()

        def vital(self, traits, pack):
            return VitalRates(birth=0.1, death=0.1, establish=0.01)

    k: KingdomSim = FakeKingdom()
    x = Instance(species_id="s", instance_id="i", traits={"temp_opt": 10.0})
    verdict = _fake_stress(k.derive(x.traits, None), None, 0)
    inc: TraitPressure = k.select(verdict, x.traits, None)
    for key, val in inc.items():
        x.pressure[key] = x.pressure.get(key, 0.0) + val
    k.mutate(x, None)
    assert x.traits["temp_opt"] == 9.5
    assert x.pressure == {}
    assert k.vital(x.traits, None).establish == 0.01


def test_tree_authority_protocol_shape():
    class FakeTree:
        def mint(self, species_id, instance_id, rng):
            return Instance(species_id=species_id,
                            instance_id=instance_id,
                            traits={"temp_opt": 10.0})

        def update(self, views, rng):
            return ChangeLog(instances=tuple(
                InstanceDelta(instance_id=v.instance_id,
                              outcome=Outcome.KEEP, orthodox=True)
                for v in views))

        def redraw(self, instance_id):
            return Instance(species_id="s", instance_id=instance_id)

    t: TreeAuthority = FakeTree()
    x = t.mint("s", "i1", None)
    log = t.update([x.view(mass=1.0)], None)
    assert log.instances[0].outcome is Outcome.KEEP
    assert t.redraw("i1") is not None


# ──  subspecies rank  ─────────────────────────────────────────────────


def test_subspecies_rank_below_species():
    assert Rank.SUBSPECIES > Rank.SPECIES
    assert RANK_PREFIX[Rank.SUBSPECIES] == "ss"
    assert len(Rank) == 8
