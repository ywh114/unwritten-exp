"""Flora KingdomSim — the organism side of the K15 sim contract.

Implements ``exp.k13_treegen.interface.KingdomSim`` for flora — the four
space-blind behaviors the K15 sim drives (checkout/commit model,
interface.py): derive, select, mutate, vital.

┌─ derive ────────────────────────────────────────────────────────────
Wraps ``flora.derive.effective_climate`` (niche-METADATA baseline from
the preset's [niche] table + stored tolerance traits) and adds the
plan/phenology keys ``req_flora.py`` documents: root_depth_m, height_m,
woodiness, photosynthesis, winter_deciduous/leafout_month,
drought_deciduous, the bloom window, medium (from the plan registry),
anchoring_need = clip(height x woodiness / ANCHOR_REF_M), holdfast, and
the adapter's submerged flag. The result is a drop-in for the env-side
species_view (stress_adapter reads exactly these keys). ``traits`` is the
flat WIP-gene mapping: axes + generics, plus the optional "plan"/"preset"
keys the tree's mint carries (derive is a pure projection; missing
plan/preset degrade to defaults).

┌─ select ────────────────────────────────────────────────────────────
Routes each verdict provenance factor (the ENV-defined req_flora names)
through content/flora/stress_response.toml (loaded into the ContentPack)
to the driftable traits that answer it. Magnitude = (1 - suitability) x
row weight: the worse the factor, the harder the push. Responders are
only ever driftable TRAITS (axes + generics); [niche] metadata and
plan-level medium never receive pressure. One documented rule:

* No-responder requirements (pressure:climate — its terms are the
  [niche] metadata that never drifts; pressure:medium — medium is
  plan-level) emit NO pressure: the lineage accumulates nowhere and
  simply shrinks where it is unsuitable. Intended (interface ruling).

(Symmetric requirements are SPLIT one-sided env-side — pressure:ph_low /
pressure:ph_high, req_flora ruling 2026-08-01 — so every verdict factor
carries its own sign and no direction-from-context hedge is needed.)

┌─ mutate ────────────────────────────────────────────────────────────
Applies x.pressure to x.traits, then clears the plane. Continuous traits
nudge by pressure x NUDGE_RATE sigma-units — additive for gaussian/int,
multiplicative in log space for log_gaussian/ratio (the forces.py
idiom), clipped to the axis bounds. Discrete traits (enums, plan
generics) treat |pressure| past DISCRETE_THRESHOLD as a switch propensity
resolved by an rng draw among legal targets: the row's ``toward`` set
intersected with the registry states / plan permission table AND the
constraint gate (anthocyanin ⊥ betalain is enforced here). A changed
record runs the flora constraint gate once (enforce) — legality is the
final word, as in the backbone. All draws go through the passed K1
Stream via rng.child(name) — the forces.py per-axis idiom. No ``random``,
no uuid.

┌─ vital ─────────────────────────────────────────────────────────────
PROVISIONAL base per-year rates at s = 0 (see the VITAL_* constants).
Simple documented trait proxies; replace when the K15 vital-rate model
lands.

Contract notes (ambiguities resolved here):

* mutate() takes no pack in the protocol, so the adapter is constructed
  per content pack: FloraSim(pack). derive/select/vital use their passed
  pack; mutate uses the carried one.
* The ``toward`` target sets must be unambiguous per trait: no trait may
  appear with different toward sets in two table rows (checked at mutate
  time — ValueError).
"""

from __future__ import annotations

import math
from typing import Mapping

from exp.k13_treegen.flora.backbone import GEN_TIME_COEFF, GEN_TIME_EXP
from exp.k13_treegen.flora.constraints import enforce, triggered
from exp.k13_treegen.flora.content import ContentPack
from exp.k13_treegen.flora.derive import DERIVED_AXES, effective_climate
from exp.k13_treegen.interface import Instance, VitalRates
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.registry import AxisSpec, MutationKind, ValueType
from kernel.hashrng import Stream

# ── pressure -> nudge (mutate) ────────────────────────────────────────
# z = pressure x NUDGE_RATE sigma-units per call. mutate is invoked at
# generation boundaries inside the round (gen_time decides call
# frequency); at full pressure (shortfall 1) a trait moves ~0.5 sigma
# per 10 generations — slow, deliberate drift, tunable.
NUDGE_RATE = 0.05
# log-space nudge clamp: exp(±50) is far past any authored bound, so a
# pathological pressure cannot overflow float before the bound clip.
MUTATE_EXP_CLAMP = 50.0
# |pressure| below this never triggers a discrete switch; above it the
# switch propensity is (|p| - threshold) x DISCRETE_RATE, capped at 1.
DISCRETE_THRESHOLD = 0.5
DISCRETE_RATE = 0.2

# ── derive ───────────────────────────────────────────────────────────
# anchoring_need = clip(height_m x woodiness / ANCHOR_REF_M) — mirrors
# k15 stress_adapter.ANCHOR_REF_M exactly. flora must not import k15
# (the direction would be a cycle), so the constant is duplicated here;
# keep in sync with exp/k15_simdiff/stress_adapter.py.
ANCHOR_REF_M = 25.0

# ── vital (PROVISIONAL — replace when the K15 vital-rate model lands) ─
# Base per-year rates at s = 0, simple trait proxies with documented
# shapes:
#   fecundity = (FECUNDITY_REF_MG / propagule_mg)^FECUNDITY_EXP — the
#       classic mass/fecundity trade-off (small seeds -> many propagules),
#   birth = fecundity x BIRTH_GEN_RATE / gen_time — annualized over the
#       generation clock (gen_time = GEN_TIME_COEFF x height^GEN_TIME_EXP,
#       the backbone's formula, rate multiplier assumed 1),
#   establish = (ESTABLISH_REF_MG / propagule_mg)^ESTABLISH_EXP, x clonal
#       multiplier (a runner/floater need not gamble on a seed), x seed-
#       bank multiplier, capped at 1 (rain -> established conversion),
#   death = 1 / longevity, discounted for woodiness (structural
#       persistence), floored.
FECUNDITY_REF_MG = 10.0
FECUNDITY_EXP = 0.5
FECUNDITY_CAP = 100.0     # cap on the per-generation fecundity proxy
BIRTH_GEN_RATE = 1.0      # offspring per generation per unit fecundity
BIRTH_MAX = 100.0         # per-year birth cap; the density feedback
                          # crushes the rest, keeps field updates sane
ESTABLISH_REF_MG = 1.0
ESTABLISH_EXP = 0.35      # small propagules establish more readily
CLONAL_ESTABLISH_M = 0.5  # clonal spread at/above this multiplies ...
CLONAL_ESTABLISH_MULT = 4.0  # ... establishment (rhizome/runner/floater)
SEED_BANK_MULT = 1.5      # persistent seed bank smooths establishment
DEATH_LONGEVITY_EXP = 1.0 # death = 1 / longevity^exp
DEATH_WOODY_DISCOUNT = 0.5  # x (1 - discount x woodiness): wood lasts
DEATH_MIN = 1e-4          # floor so immortals still leak a little


def _plan_of(traits) -> str | None:
    return traits.get("plan") if isinstance(traits, Mapping) else None


def _num(traits: Mapping, key: str, default: float = 0.0) -> float:
    v = traits.get(key)
    return float(v) if isinstance(v, (int, float)) else default


def _clip(x: float, spec: AxisSpec) -> float:
    if spec.bounds is not None:
        lo, hi = spec.bounds
        return min(hi, max(lo, x))
    return x


def _node(axes: Mapping, plan, preset) -> Node:
    """Throwaway Node for the trait->derived projection / gate. Keep it
    cheap: no path/sid/naming machinery is touched."""
    return Node(path="", rank=Rank.SPECIES, parent=None, sid="0" * 16,
                plan=plan, preset=preset, axes=dict(axes))


def _generic_permissions(pack: ContentPack, plan) -> dict[str, list]:
    """The plan's generic permission table (model.rebind legality)."""
    if plan is None:
        return {}
    ps = pack.registry.plans.get(plan)
    return ps.generics if ps is not None else {}


def _toward_map(table: Mapping[str, list]) -> dict[str, frozenset]:
    """trait/generic -> toward target set, validated unambiguous across
    the whole table: two rows may not disagree on one trait's targets
    (the TraitPressure plane carries magnitudes only, so a trait's switch
    direction must be resolvable from content alone)."""
    out: dict[str, frozenset] = {}
    for rows in table.values():
        for row in rows:
            key = row.get("trait") or row.get("generic")
            if key is None or "toward" not in row:
                continue
            ts = frozenset(row["toward"])
            prev = out.get(key)
            if prev is not None and prev != ts:
                raise ValueError(
                    f"stress_response: toward targets for {key!r} conflict "
                    f"across requirements ({sorted(prev)} vs {sorted(ts)})")
            out[key] = ts
    return out


def _switch_targets(name: str, cur: str, traits: Mapping, pack: ContentPack,
                    toward: frozenset | None) -> list[str]:
    """Legal switch targets for one enum axis: registry states ∩ the
    row's toward set ∩ the constraint gate (forbid/require rules that
    fire on the CURRENT record). Mirrors the snap-candidate logic in
    flora.constraints."""
    spec = pack.registry.axes.get(name)
    states = list(spec.states) if spec is not None else []
    if toward:
        states = [s for s in states if s in toward]
    plan = _plan_of(traits)
    for rule in pack.constraints:
        if not triggered(rule, traits, plan):
            continue
        if name in rule.forbid_enum:
            states = [s for s in states if s not in rule.forbid_enum[name]]
        if name in rule.require_enum:
            req = rule.require_enum[name]
            if cur not in req:   # current illegal -> must land inside req
                states = [s for s in states if s in req]
    return states


class FloraSim:
    """The flora KingdomSim adapter. Construct per content pack
    (``FloraSim(pack)``): mutate() carries no pack in the protocol, so
    the adapter owns one. Thread-safe/pure otherwise — derive/select/
    vital are functions of their arguments."""

    def __init__(self, pack: ContentPack) -> None:
        self.pack = pack

    # ── derive ──────────────────────────────────────────────────────

    def derive(self, traits: Mapping, pack: ContentPack) -> dict:
        """Project WIP genes to the derived vocabulary the env reads
        (req_flora): effective_climate's niche baseline + tolerance
        traits, plus the plan/phenology descriptors. Drop-in for the
        env-side species_view."""
        node = _node(traits, _plan_of(traits), traits.get("preset"))
        view = dict(effective_climate(node, pack))
        axes = node.axes
        meta = pack.presets.get(node.preset or "", {}).get("niche", {})
        plan = pack.registry.plans.get(node.plan or "")
        medium = plan.medium if plan is not None else "land"
        lp = str(axes.get("leaf_persistence") or "evergreen")
        dt = str(axes.get("deciduous_trigger") or "none")
        height = float(axes.get("height_m") or 0.0)
        wood = float(axes.get("woodiness") or 0.0)
        view.update({
            "w_T": meta.get("w_T"),
            "w_P": meta.get("w_P"),
            "root_depth_m": axes.get("root_depth_m"),
            "height_m": height,
            "woodiness": wood,
            "photosynthesis": str(axes.get("photosynthesis") or "C3"),
            "winter_deciduous": int(lp == "winter_deciduous"
                                    or dt == "winter"),
            "leafout_month": axes.get("leafout_month"),
            "drought_deciduous": int(lp == "drought_deciduous"
                                     or dt == "drought"),
            "bloom_start_month": axes.get("bloom_start_month"),
            "bloom_length_months": axes.get("bloom_length_months"),
            "medium": medium,
            "anchoring_need": min(1.0, max(0.0,
                                           height * wood / ANCHOR_REF_M)),
            "holdfast": int(str(axes.get("root_type") or "") == "holdfast"),
            "submerged": int(str(axes.get("layer") or "")
                             == "aquatic_benthic"),
            # engine-side dispersal (K15 rounds, not the stress
            # adapter): channel weights drive per-vector radius, the
            # propagule mass the distance decay, the seed bank the
            # establishment carryover in sink cells.
            "dispersal_channels": axes.get("dispersal_channels"),
            "propagule_mass_mg": axes.get("propagule_mass_mg"),
            "propagule_count": axes.get("propagule_count"),
            "seed_bank": axes.get("seed_bank"),
            # per-capita space demand for the engine's density term
            "crown_spread_m": axes.get("crown_spread_m"),
        })
        return view

    # ── select ──────────────────────────────────────────────────────

    def select(self, verdict, traits: Mapping, pack: ContentPack) -> dict:
        """One feed's pressure increment: map each provenance factor to
        the driftable traits that answer it, weighted by the shortfall
        (1 - suitability). Names dispatch on the req_flora vocabulary;
        plain names are treated as defensive (interface ruling); other
        namespaced names (pull:/ley:/lift:/unknown) are ignored."""
        pressure: dict[str, float] = {}
        table = pack.stress_response
        plan = _plan_of(traits)
        for name, f in verdict.provenance.items():
            if not isinstance(f, (int, float)) or isinstance(f, bool):
                continue
            if name.startswith("pressure:"):
                key = name
            elif ":" in name:
                continue                       # pull:/ley:/lift:/foreign
            else:
                key = "pressure:" + name       # plain = defensive
            rows = table.get(key)
            if not rows:
                continue
            shortfall = min(1.0, max(0.0, 1.0 - float(f)))
            if shortfall <= 0.0:
                continue
            for row in rows:
                weight = shortfall * float(row.get("weight", 1.0))
                trait = row.get("trait")
                if trait:
                    spec = pack.registry.axes.get(trait)
                    if spec is None or not spec.mutable \
                            or trait in DERIVED_AXES \
                            or not spec.applies_to(plan):
                        continue
                    d = row.get("dir", "up")
                    sign = 1.0 if d == "up" else -1.0
                    pressure[trait] = pressure.get(trait, 0.0) + weight * sign
                    continue
                generic = row.get("generic")
                if generic and generic in _generic_permissions(pack, plan):
                    pressure[generic] = pressure.get(generic, 0.0) + weight
        return pressure

    # ── mutate ──────────────────────────────────────────────────────

    def mutate(self, x: Instance, rng: Stream) -> None:
        """Apply the accumulated pressure plane to x.traits (per
        generation step), run the constraint gate if anything changed,
        then reset the plane. All draws through *rng* (child stream per
        pressured trait — the forces.py idiom)."""
        pack = self.pack
        toward = _toward_map(pack.stress_response)
        plan = _plan_of(x.traits)
        before = dict(x.traits)
        changed = False
        for name in sorted(x.pressure):
            p = x.pressure.get(name)
            if not isinstance(p, (int, float)) or isinstance(p, bool) \
                    or p == 0.0:
                continue
            if name in pack.registry.axes:
                changed = self._mutate_axis(name, p, x, rng, pack, toward) \
                    or changed
            elif name in _generic_permissions(pack, plan):
                changed = self._mutate_generic(name, p, x, rng, pack, toward) \
                    or changed
        if changed:
            parent = _node(before, plan, x.traits.get("preset"))
            child = _node(x.traits, plan, x.traits.get("preset"))
            enforce(parent, child, pack)
            x.traits.update(child.axes)
        x.pressure.clear()

    def _mutate_axis(self, name, p, x, rng, pack, toward) -> bool:
        spec = pack.registry.axes.get(name)
        if spec is None or not spec.mutable or name in DERIVED_AXES \
                or not spec.applies_to(_plan_of(x.traits)):
            return False
        cur = x.traits.get(name)
        if cur is None:
            return False
        if spec.value_type in (ValueType.SCALAR, ValueType.INT) \
                and isinstance(cur, (int, float)):
            z = p * NUDGE_RATE
            if spec.mutation_kind is MutationKind.GAUSSIAN \
                    or float(cur) <= 0.0:
                # additive; zero is absorbing under multiplication and
                # would freeze the dial (the forces.py freeze fix)
                new = float(cur) + z * spec.sigma
            else:  # log_gaussian / ratio: multiplicative in log space
                ex = max(-MUTATE_EXP_CLAMP,
                         min(MUTATE_EXP_CLAMP, z * spec.sigma))
                new = float(cur) * math.exp(ex)
            new = _clip(new, spec)
            if spec.value_type is ValueType.INT:
                new = int(round(new))
            x.traits[name] = new
            return True
        if spec.value_type is ValueType.ENUM and isinstance(cur, str):
            if abs(p) < DISCRETE_THRESHOLD:
                return False
            prop = min(1.0, (abs(p) - DISCRETE_THRESHOLD) * DISCRETE_RATE)
            s = rng.child(name)
            if not s.bernoulli(prop, 0):
                return False
            targets = [t for t in _switch_targets(name, cur, x.traits,
                                                  pack, toward.get(name))
                       if t != cur]
            if not targets:
                return False
            x.traits[name] = targets[s.randrange(len(targets), 0, 1)]
            return True
        return False

    def _mutate_generic(self, name, p, x, rng, pack, toward) -> bool:
        if abs(p) < DISCRETE_THRESHOLD:
            return False
        legal = list(_generic_permissions(pack, _plan_of(x.traits))
                     .get(name, []))
        if toward.get(name):
            legal = [r for r in legal if r in toward.get(name)]
        cur = x.traits.get(name)
        if cur is None:
            return False
        legal = [r for r in legal if r != cur]
        if not legal:
            return False
        prop = min(1.0, (abs(p) - DISCRETE_THRESHOLD) * DISCRETE_RATE)
        s = rng.child(name)
        if s.bernoulli(prop, 0):
            x.traits[name] = legal[s.randrange(len(legal), 0, 1)]
            return True
        return False

    # ── vital ───────────────────────────────────────────────────────

    def vital(self, traits: Mapping, pack: ContentPack) -> VitalRates:
        """PROVISIONAL base per-year rates at s = 0 from trait proxies
        (module constants + docstring). Empty traits -> zero rates."""
        if not isinstance(traits, Mapping):
            return VitalRates()
        prop = max(_num(traits, "propagule_mass_mg"), 1e-9)
        fecundity = min(FECUNDITY_CAP,
                        (FECUNDITY_REF_MG / prop) ** FECUNDITY_EXP)
        height = max(_num(traits, "height_m"), 1e-6)
        gen_time = GEN_TIME_COEFF * height ** GEN_TIME_EXP
        birth = min(BIRTH_MAX,
                    fecundity * BIRTH_GEN_RATE / max(gen_time, 1e-6))

        est = min(1.0, (ESTABLISH_REF_MG / prop) ** ESTABLISH_EXP)
        if _num(traits, "clonal_spread_m") >= CLONAL_ESTABLISH_M:
            est *= CLONAL_ESTABLISH_MULT
        if str(traits.get("seed_bank") or "") == "persistent":
            est *= SEED_BANK_MULT
        est = min(1.0, est)

        lon = max(_num(traits, "longevity_yr"), 1e-6)
        wood = min(max(_num(traits, "woodiness"), 0.0), 1.0)
        death = max(DEATH_MIN,
                    (1.0 / lon ** DEATH_LONGEVITY_EXP)
                    * (1.0 - DEATH_WOODY_DISCOUNT * wood))
        return VitalRates(birth=birth, death=death, establish=est)
