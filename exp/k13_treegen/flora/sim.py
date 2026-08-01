"""Flora KingdomSim — the organism side of the K15 sim contract.

Implements ``exp.k13_treegen.interface.KingdomSim`` for flora — the four
space-blind behaviors the K15 sim drives (checkout/commit model,
interface.py): derive, select, mutate, vital.

┌─ derive ────────────────────────────────────────────────────────────
Wraps ``flora.derive.effective_climate`` (the climate ENVELOPE as a
pure DERIVED of the trait bundle — owner ruling 2026-08-01, no [niche]
metadata — plus the stored tolerance traits) and adds the plan/
phenology keys ``req_flora.py`` documents: root_depth_m, height_m,
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
only ever driftable TRAITS (axes + generics); the climate ENVELOPE is a
derived (never pressured directly) and plan-level medium never receives
pressure. One documented rule:

* No-responder requirements (pressure:medium — medium is plan-level
  registry data) emit NO pressure: the lineage accumulates nowhere and
  simply shrinks where it is unsuitable. Intended (interface ruling).
  pressure:cold / pressure:heat DO route (owner ruling 2026-08-01:
  the envelope is a pure derived, so the backward pass moves it).

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
  appear with different toward sets in two table rows (checked at
  construction — ValueError).
"""

from __future__ import annotations

import math
from typing import Mapping

from exp.k13_treegen.flora.backbone import GEN_TIME_COEFF, GEN_TIME_EXP
from exp.k13_treegen.flora.constraints import enforce, triggered
from exp.k13_treegen.flora.content import ContentPack
from exp.k13_treegen.flora.derive import (
    DERIVED_AXES,
    _derived_canopy_density,
    effective_climate,
)
from exp.k13_treegen.interface import Instance, VitalRates
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.registry import AxisSpec, MutationKind, ValueType
from kernel.hashrng import Stream

# ── pressure -> nudge (mutate) ────────────────────────────────────────
# z = pressure x NUDGE_RATE sigma-units per call. mutate is invoked at
# generation boundaries inside the round (gen_time decides call
# frequency); at full pressure (shortfall 1) a trait moves ~0.5 sigma
# per call — big enough that changes are made even with the ~90-axis
# dilution of genes_distance (owner directive 2026-08-01).
# Calibrated 2026-08-01 (tmp/k15_drift_calib2.py, grass_sward.reed pair
# on a cold-shortfall vs a heat-shortfall cell, 20 rounds, no-merge
# observation, after the continuous heat dials): pairwise genes_distance
# mean drift/round at NUDGE_RATE 0.25/0.5/1.0 = +0.000433 / +0.000899 /
# +0.000969, d@round20 = 0.0087 / 0.0180 / 0.0194, monotonic throughout.
# 0.5 is the smallest rate that lands the pair inside the d ~ 0.01-0.05
# window within 20 rounds (d >= 0.01 at round 12); 1.0 buys ~nothing
# more (both envelopes saturate their dials by round ~8-19). Pre-fix
# (one-way envelope) the same pair converged at +0.00043/round with a
# ~0.009 ceiling — the dial fix removed the ceiling, so 0.5 diverges.
NUDGE_RATE = 0.5
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
#       the backbone's formula, rate multiplier assumed 1), x the
#       GROWTH_RATE multiplier (B6 §2: growth_rate scales birth — a
#       fast-growing plan packs more reproduction per year),
#   establish = (ESTABLISH_REF_MG / propagule_mg)^ESTABLISH_EXP, x clonal
#       multiplier (a runner/floater need not gamble on a seed), x seed-
#       bank multiplier, capped at 1 (rain -> established conversion),
#   death = 1 / longevity, discounted for woodiness (structural
#       persistence), x the WOOD_DENSITY multiplier (B6 §2: denser wood
#       dies slower — the density axis is the physiology under the
#       woodiness fraction), floored.
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

# ── B6 §2 vital wiring (growth_rate / wood_density) ────────────────────
# growth_rate (m/yr, axis [0.005, 5.0]) scales BIRTH: a saturating
# multiplier 1 + GROWTH_BIRTH_COEF x sat(growth_rate / GROWTH_REF_MY).
# At the reference rate (1 m/yr) the multiplier is 1 + COEF — modest;
# a 5 m/yr kelp saturates at 1 + COEF. Bounds [0.005, 5], reference 1.0.
GROWTH_REF_MY = 1.0
GROWTH_BIRTH_COEF = 0.5
# wood_density (g/cm3, axis [0.1, 1.5]) scales DEATH inversely: x
# (1 - WOOD_DENSITY_DEATH_COEF x sat(wood_density / WOOD_DENSITY_REF)).
# Reference 1.0 g/cm3 (oak-grade); balsa (0.1) ~ no discount, lignum
# vitae (1.5) saturates at the full discount. Plans without the axis
# (plan_scope tree/shrub/succulent only) read 0 -> multiplier 1.
WOOD_DENSITY_REF = 1.0
WOOD_DENSITY_DEATH_COEF = 0.3


def _plan_of(traits) -> str | None:
    return traits.get("plan") if isinstance(traits, Mapping) else None


def _num(traits: Mapping, key: str, default: float = 0.0) -> float:
    v = traits.get(key)
    return float(v) if isinstance(v, (int, float)) else default


class _AxisPlan:
    """One axis's per-mutate plan (ticket 0023): the registry fields
    the per-axis hot path reads, resolved ONCE at FloraSim init instead
    of per `_mutate_axis` call (3.67M calls / 6 rounds in the phase
    profile). plan_scope is split into an "all" flag + the scoped set
    so the scope test in `_mutate_axis` is two attribute reads + one
    set membership. Only mutable, non-derived axes are planned (the
    gate prefix of the pre-0023 `_mutate_axis`); the registry's own
    validate() rejects a string plan_scope other than "all", so the
    frozenset conversion matches its interpretation."""

    __slots__ = ("value_type", "mutation_kind", "sigma", "bounds",
                 "scope_all", "scope", "is_cont", "is_int", "is_enum")

    def __init__(self, spec: AxisSpec) -> None:
        self.value_type = spec.value_type
        self.mutation_kind = spec.mutation_kind
        self.sigma = spec.sigma
        self.bounds = spec.bounds
        scope = spec.plan_scope
        self.scope_all = scope == "all"
        self.scope = frozenset() if self.scope_all else frozenset(scope)
        # value-type dispatch flags, resolved once (the per-call tuple
        # memberships were part of the _mutate_axis churn)
        self.is_cont = spec.value_type in (ValueType.SCALAR, ValueType.INT)
        self.is_int = spec.value_type is ValueType.INT
        self.is_enum = spec.value_type is ValueType.ENUM


def _node(axes: Mapping, plan, preset, copy: bool = True) -> Node:
    """Throwaway Node for the trait->derived projection / gate. Keep it
    cheap: no path/sid/naming machinery is touched. ``copy`` is False in
    mutate's gate call: enforce() snaps child.axes IN PLACE, so the
    child may share the instance's traits dict (the update-back is then
    a no-op and is dropped)."""
    return Node(path="", rank=Rank.SPECIES, parent=None, sid="0" * 16,
                plan=plan, preset=preset,
                axes=dict(axes) if copy else axes)


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


def _switch_targets(name: str, cur: str, traits: Mapping,
                    plan: str | None, pack: ContentPack,
                    toward: frozenset | None) -> list[str]:
    """Legal switch targets for one enum axis: registry states ∩ the
    row's toward set ∩ the constraint gate (forbid/require rules that
    fire on the CURRENT record). Mirrors the snap-candidate logic in
    flora.constraints. plan arrives pre-resolved from mutate (ticket
    0023 — no per-call _plan_of)."""
    spec = pack.registry.axes.get(name)
    states = list(spec.states) if spec is not None else []
    if toward:
        states = [s for s in states if s in toward]
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
        # the stress_response toward sets (trait/generic -> target
        # frozenset) — a pure function of the immutable pack table,
        # computed once at construction (mutate ran a full table walk
        # per call; ticket 0022). The ambiguity ValueError fires here.
        self._toward = _toward_map(pack.stress_response)
        # per-axis mutation plans (ticket 0023): the mutable non-derived
        # registry axes resolved once — value_type/mutation_kind/sigma/
        # bounds + the plan-scope gate — instead of the per-`_mutate_axis`
        # registry walk + isinstance/typing churn (3.67M calls / 6 rounds
        # in the phase profile). An axis absent from the plan either does
        # not exist in the registry or never moves (gate-0 semantics).
        self._mut_plan = {n: _AxisPlan(s)
                          for n, s in pack.registry.axes.items()
                          if s.mutable and n not in DERIVED_AXES}
        # plan -> generic permission table (model.rebind legality),
        # resolved once instead of per _mutate_generic call.
        self._plan_generics = {pid: ps.generics
                               for pid, ps in pack.registry.plans.items()}

    # ── derive ──────────────────────────────────────────────────────

    def derive(self, traits: Mapping, pack: ContentPack) -> dict:
        """Project WIP genes to the derived vocabulary the env reads
        (req_flora): effective_climate's DERIVED envelope + tolerance
        traits, plus the plan/phenology descriptors. Drop-in for the
        env-side species_view."""
        node = _node(traits, _plan_of(traits), traits.get("preset"))
        view = dict(effective_climate(node, pack))
        axes = node.axes
        plan = pack.registry.plans.get(node.plan or "")
        medium = plan.medium if plan is not None else "land"
        lp = str(axes.get("leaf_persistence") or "evergreen")
        dt = str(axes.get("deciduous_trigger") or "none")
        height = float(axes.get("height_m") or 0.0)
        wood = float(axes.get("woodiness") or 0.0)
        view.update({
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
            # ── B6 hand-wiring keys (biosphere-addendum-b6; the k15
            # ── stress strata read them — mirrors stress_adapter's
            # ── _view_from_record exactly).
            "mycorrhizal": str(axes.get("mycorrhizal") or "none"),
            "n_fixation": str(axes.get("n_fixation") or "none"),
            "nutrient_package": str(axes.get("nutrient_package") or "none"),
            "drip_tips": axes.get("drip_tips"),
            "leaf_margin": str(axes.get("leaf_margin") or "entire"),
            "snow_adaptation": str(axes.get("snow_adaptation") or "none"),
            "layer": str(axes.get("layer") or "ground"),
            "canopy_density": _derived_canopy_density(node),
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
            # jump-dispersal frequency (long-range hops/yr) for the engine
            "jump_rate": axes.get("jump_rate"),
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
        toward = self._toward
        # plan / generic permissions are pure functions of the pack +
        # the instance's plan, resolved once per call (ticket 0023) —
        # _plan_of's isinstance/typing churn was 4.4M calls / 15.5 s in
        # the phase profile; x.traits is always a dict (Instance).
        plan = x.traits.get("plan")
        generics = self._plan_generics.get(plan)
        before = dict(x.traits)
        changed = False
        for name in sorted(x.pressure):
            p = x.pressure[name]
            if not isinstance(p, (int, float)) or isinstance(p, bool) \
                    or p == 0.0:
                continue
            pl = self._mut_plan.get(name)
            if pl is not None:
                changed = self._mutate_axis(pl, name, p, x, rng, plan,
                                            toward) or changed
            elif name in pack.registry.axes:
                continue           # registry axis, never moves (gate 0)
            elif generics is not None and name in generics:
                changed = self._mutate_generic(name, p, x, rng, plan,
                                               generics, toward) or changed
        if changed:
            # parent shares the private `before` snapshot (copy=False —
            # it is already a fresh dict and enforce never writes it);
            # child shares x.traits (copy=False): enforce snaps in place,
            # so no update-back pass over the ~90-key dict is needed
            # (ticket 0023 — 357K changed records / 6 rounds).
            parent = _node(before, plan, x.traits.get("preset"),
                           copy=False)
            child = _node(x.traits, plan, x.traits.get("preset"),
                          copy=False)
            enforce(parent, child, pack)
        x.pressure.clear()

    def _mutate_axis(self, pl, name, p, x, rng, plan, toward) -> bool:
        """One pressured axis. *pl* is the precomputed _AxisPlan (the
        registry gate — mutable, non-derived — was applied at plan
        build; only the plan-scope test remains per call). Same draws,
        same order, same float ops as the pre-0023 spec-walk version."""
        if not (pl.scope_all or plan in pl.scope):
            return False
        cur = x.traits.get(name)
        if cur is None:
            return False
        if pl.is_cont and isinstance(cur, (int, float)):
            z = p * NUDGE_RATE
            if pl.mutation_kind is MutationKind.GAUSSIAN \
                    or float(cur) <= 0.0:
                # additive; zero is absorbing under multiplication and
                # would freeze the dial (the forces.py freeze fix)
                new = float(cur) + z * pl.sigma
            else:  # log_gaussian / ratio: multiplicative in log space
                ex = max(-MUTATE_EXP_CLAMP,
                         min(MUTATE_EXP_CLAMP, z * pl.sigma))
                new = float(cur) * math.exp(ex)
            b = pl.bounds
            if b is not None:
                new = min(b[1], max(b[0], new))
            if pl.is_int:
                new = int(round(new))
            x.traits[name] = new
            return True
        if pl.is_enum and isinstance(cur, str):
            if abs(p) < DISCRETE_THRESHOLD:
                return False
            prop = min(1.0, (abs(p) - DISCRETE_THRESHOLD) * DISCRETE_RATE)
            s = rng.child(name)
            if not s.bernoulli(prop, 0):
                return False
            targets = [t for t in _switch_targets(name, cur, x.traits,
                                                  plan, self.pack,
                                                  toward.get(name))
                       if t != cur]
            if not targets:
                return False
            x.traits[name] = targets[s.randrange(len(targets), 0, 1)]
            return True
        return False

    def _mutate_generic(self, name, p, x, rng, plan, generics, toward) -> bool:
        if abs(p) < DISCRETE_THRESHOLD:
            return False
        legal = list(generics.get(name, []))
        tw = toward.get(name)
        if tw:
            legal = [r for r in legal if r in tw]
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
        # B6 §2: growth_rate scales birth (saturating at GROWTH_REF_MY).
        growth = max(_num(traits, "growth_rate"), 0.0)
        growth_mult = 1.0 + GROWTH_BIRTH_COEF * min(
            1.0, growth / GROWTH_REF_MY)
        birth = min(BIRTH_MAX,
                    fecundity * BIRTH_GEN_RATE * growth_mult
                    / max(gen_time, 1e-6))

        est = min(1.0, (ESTABLISH_REF_MG / prop) ** ESTABLISH_EXP)
        if _num(traits, "clonal_spread_m") >= CLONAL_ESTABLISH_M:
            est *= CLONAL_ESTABLISH_MULT
        if str(traits.get("seed_bank") or "") == "persistent":
            est *= SEED_BANK_MULT
        est = min(1.0, est)

        lon = max(_num(traits, "longevity_yr"), 1e-6)
        wood = min(max(_num(traits, "woodiness"), 0.0), 1.0)
        # B6 §2: wood_density scales death inversely (saturating at
        # WOOD_DENSITY_REF); absent axis -> 0 -> multiplier 1.
        wd = max(_num(traits, "wood_density"), 0.0)
        wd_mult = 1.0 - WOOD_DENSITY_DEATH_COEF * min(
            1.0, wd / WOOD_DENSITY_REF)
        death = max(DEATH_MIN,
                    (1.0 / lon ** DEATH_LONGEVITY_EXP)
                    * (1.0 - DEATH_WOODY_DISCOUNT * wood) * wd_mult)
        return VitalRates(birth=birth, death=death, establish=est)
