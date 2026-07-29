"""M5 — clock & forces: the world-blind sampler (docs/m5-clock-forces.md).

Turns a parent Node into a descendant Node. Three forces (drift / stress
descent / runaway) share-weighted by population Condition; g-clock in
generations with allometric gen_time and per-lineage rate multipliers;
speciation gated by per-clade seeded g*. All randomness via K1 Stream.

Force share ratios (RFC §4): large+stressed → descent; small isolate →
drift; benign → slow mixed. The per-axis adapt_weight (0=decorative ..
1=adaptive) selects which forces may touch an axis: descent needs weight,
runaway needs weight==0, drift touches everything mutable. N/A is sticky.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from exp.k13_treegen.content import ContentPack
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.registry import AxisSpec, MutationKind, Tier, ValueType
from kernel.hashrng import Stream

# ── clock ────────────────────────────────────────────────────────────────
# lineage rate multiplier spread: exp(N(0, 0.5)) — central 95% ≈ [0.38,
# 2.7], giving fast radiators AND living fossils without absurdity.
SIGMA_RATE = 0.5
# a fully stressed lineage accrues generations at 2x the base rate.
STRESS_G_BOOST = 1.0
# speciation cutoff: median 500 generations with lognormal spread — the
# seeded variance IS the radiation tempo (RFC §4).
G_STAR_MEDIAN = 500.0
G_STAR_SIGMA = 0.5

# ── mutation magnitude ∝ f(g) ────────────────────────────────────────────
# step scale reference: at g = G_REF the scale has doubled (leaky linear).
G_REF = 1000.0
# steady-tier novelty ramp: steady axes are effectively frozen at low g and
# open smoothly — 1 - exp(-(g - onset)/ramp). NO hard unlock (user ruling:
# processes are continuous and leaky; only commitments are categorical).
G_STEADY_ONSET = 200.0
G_STEADY_RAMP = 200.0
# heavy tail: p_novel saturates at P_NOVEL_MAX (leaky asymptote — the tail
# stays a TAIL). 0.02 lands ~1 novelty-jumped axis per species (the
# occasional striking trait); at 0.1 every species had ~6 and the
# fecundity/lifespan coupling loop amplified them past 10 sigma (the
# integration diversity test caught it). A novel step is x NOVELTY_MULT.
P_NOVEL_MAX = 0.02
G_NOVEL = 800.0
NOVELTY_MULT = 5.0

# ── force rates (per generation, before share weighting) ─────────────────
# drift step = sigma x DRIFT_RATE x scale x sqrt(dg). 0.1 lands the M7
# acceptance: median sister distance ~= sigma (at 1.0 a family edge was
# ~20 sigma and body mass pegged at its upper bound).
DRIFT_RATE = 0.1
DESCENT_RATE = 0.05    # exponential approach toward the clade center
RUNAWAY_RATE = 0.05    # constant directional push on ornament axes
ENUM_RATE = 0.004      # enum redraw probability rate per generation
# (at 0.02 a species edge redraws ~70% of enums and sister
# resemblance scrambles; 0.004 keeps clade texture coherent)

# ── share-ratio raw weights (RFC §4 condition table) ─────────────────────
# NO benign descent baseline (user ruling, drift-and-commit: children
# drift from the parent's committed record; clade ranks are not
# attractors). Descent enters only through stress (world rounds).
SHARE_DESCENT_BASE = 0.0
SHARE_DESCENT_PER_STRESS = 2.0
SHARE_DRIFT_BASE = 1.0
SHARE_DRIFT_PER_ISOLATION = 2.0
SHARE_RUNAWAY = 0.3

# ── mass envelope (the drift-and-commit sanity bound) ────────────────────
# Soft per-preset envelope on body_mass: within 10^ENVELOPE_LOG10 of the
# preset's authored mass the walk is free; beyond it the log-excess is
# damped per edge (leaky — tail draws like minicows still happen, but
# sustained walks decay instead of producing 10 kg insects).
ENVELOPE_LOG10 = 2.0
ENVELOPE_DAMP = 0.5

# adapt_weight default by block when TOML is silent: niche/physiology
# adaptive, patternation/decoration light, morphometrics mixed.
ADAPT_WEIGHT_DEFAULT = {
    "patternation": 0.2, "morphometrics": 0.4, "niche": 0.9, "diet": 0.7,
    "life_history": 0.7, "behavior": 0.5, "ecosystem": 0.8,
    "sex_age_season": 0.3,
}


# ── generic rebinds (RFC §2: regular evolution rebinds WITHIN plan
# limits; magic rebinds without them) ────────────────────────────────────
# One draw per speciation edge; on success one generic rebinds to another
# plan-legal realization. Deep machinery (support, respiration,
# metabolism, osmoreg) is plan-defining and never rebinds here.
REBIND_RATE = 0.002        # per generation (species edge ~11%, family ~30%)
REBINDABLE = ("locomotor", "feeding_organ", "signal", "covering",
              "defense", "storage", "sensor_array", "sustenance")
UNBINDABLE = ("signal", "storage", "defense")  # None is a legal state


@dataclass(frozen=True)
class Condition:
    """Population condition, caller-supplied (world-blind seam).

    The blind backbone passes the default; the rounds layer passes values
    derived from the world. ``env`` carries named world variables
    (temperature, moisture, salinity, ley proximity — ledger W7) for
    env-gated couplings; an absent key means the gate stays silent."""
    stress: float = 0.0        # 0 benign .. 1 fully stressed
    isolation: float = 0.0     # 0 connected .. 1 total isolate
    env: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Shares:
    descent: float
    drift: float
    runaway: float


def share_ratios(c: Condition) -> Shares:
    # RFC §4: large+stressed -> adaptive (drift quiets, descent dominates);
    # small isolate -> drift; benign -> slow mixed. Drift scales DOWN with
    # stress: under full stress selection is nearly the only force.
    raw = (SHARE_DESCENT_BASE + SHARE_DESCENT_PER_STRESS * c.stress,
           SHARE_DRIFT_BASE * (1 + SHARE_DRIFT_PER_ISOLATION * c.isolation)
           * (1.0 - c.stress),
           SHARE_RUNAWAY)
    total = sum(raw)
    return Shares(*(w / total for w in raw))


def adapt_weight(pack: ContentPack, spec: AxisSpec) -> float:
    if spec.adapt_weight is not None:
        return spec.adapt_weight
    return ADAPT_WEIGHT_DEFAULT.get(spec.block.value, 0.5)


# ── clock ────────────────────────────────────────────────────────────────


def gen_time_years(mass_kg: float, rate_mult: float = 1.0,
                   coeff: float = 1.0, exponent: float = 0.25) -> float:
    return coeff * mass_kg ** exponent * rate_mult


def rate_multiplier(stream: Stream) -> float:
    """Per-lineage lognormal rate multiplier (both tails, tested). Draw
    from the LINEAGE's stream so every edge of the lineage agrees."""
    return math.exp(SIGMA_RATE * stream.normal(0))


def g_star(stream: Stream) -> float:
    """Per-clade seeded speciation cutoff in generations."""
    return G_STAR_MEDIAN * math.exp(G_STAR_SIGMA * stream.normal(0))


def classify(g_since_split: float, star: float) -> str:
    """The g* boundary: species beyond, subspecies below."""
    return "species" if g_since_split > star else "subspecies"


def step_scale(g: float) -> float:
    """Mutation magnitude ∝ f(g): leaky linear, doubles by G_REF."""
    return 1.0 + g / G_REF


def _tier_gate(spec: AxisSpec, g: float) -> float:
    """Leaky tier gate: 1.0 for labile, a smooth 0->1 ramp for steady
    (effectively frozen at low g, fully open at high g), 0.0 for
    invariant/clade-steady."""
    if not spec.mutable:
        return 0.0
    if spec.tier is Tier.STEADY:
        return 1.0 - math.exp(-max(0.0, g - G_STEADY_ONSET) / G_STEADY_RAMP)
    return 1.0


# ── per-axis mutation ────────────────────────────────────────────────────


def _clip(x: float, spec: AxisSpec) -> float:
    """Respect authored content bounds."""
    if spec.bounds is not None:
        lo, hi = spec.bounds
        return min(max(x, lo), hi)
    return x


def _mutate_scalar(spec: AxisSpec, x: float, dg: float, g: float,
                   shares: Shares, w: float, stream: Stream, clock: int,
                   center: float | None, runaway_dir: float,
                   p_novel: float, gate: float) -> tuple[float, dict]:
    """One scalar axis step; returns (new_value, force decomposition).
    *gate* is the leaky tier ramp multiplying the whole step."""
    scale = step_scale(g)
    z_drift = (shares.drift * DRIFT_RATE * scale * math.sqrt(dg)
               * stream.normal(clock))
    if stream.bernoulli(p_novel, clock, 1):
        z_drift *= NOVELTY_MULT
    z_descent = 0.0
    if center is not None and w > 0 and spec.sigma > 0:
        # the gap must be measured in the axis's OWN space: raw for
        # additive axes, log for multiplicative ones (raw-unit descent on
        # a log_gaussian axis gave z ~ 1e5 sigma and pinned mass to the
        # bounds — the M7 convergence test caught it).
        if spec.mutation_kind is MutationKind.GAUSSIAN:
            gap_z = (center - x) / spec.sigma
        else:
            tiny = 1e-12
            gap_z = (math.log(max(center, tiny))
                     - math.log(max(x, tiny))) / spec.sigma
        z_descent = (shares.descent * w * gap_z
                     * (1.0 - math.exp(-dg * DESCENT_RATE)))
    z_runaway = 0.0
    if w == 0.0:
        z_runaway = shares.runaway * runaway_dir * RUNAWAY_RATE * dg
    z = (z_drift + z_descent + z_runaway) * gate
    z_drift, z_descent, z_runaway = (z_drift * gate, z_descent * gate,
                                     z_runaway * gate)
    if spec.mutation_kind is MutationKind.GAUSSIAN or x <= 0.0:
        # additive: gaussian always; ratio/log_gaussian AT ZERO too — zero
        # is absorbing under multiplication and would freeze the dial
        # forever (the first blind build froze 5 labile dials this way).
        new = x + z * spec.sigma
    else:  # log_gaussian / ratio: multiplicative in log space
        new = x * math.exp(z * spec.sigma)
    return _clip(new, spec), {"drift": z_drift, "descent": z_descent,
                              "runaway": z_runaway}


# enum axes whose legal states are palette-restricted (M3: the sampler
# must respect palettes, not just authored content — the first named
# build produced 71 green/iridescent tetrapods without this). K14 flora:
# flower_color is the same mechanism (plan palettes, syndrome-color
# correlation stays a k14 constraint, not a palette cut).
COLOR_AXES = ("base_color", "belly_color", "accent_color", "flower_color")

# vertical_stratum redraw legality (user: "Canis giganteus is an aerial
# wolf"): a stratum shift is a real adaptation, not a free redraw — it
# needs the machinery (flight for aerial, aquatic gear for water,
# climbing gear for trees) or an already-adapted parent (hereditary).
# Base strata (ground, fossorial) are always legal. Mirror of
# lint.ACTIVE_FLIGHT (kept local: lint sits above this layer).
ACTIVE_FLIGHT_STATES = {"soaring", "sustained_flapping", "hovering",
                        "bounding"}
ARB_STRATA = {"understorey", "canopy"}
AQUATIC_STRATA = {"benthic", "demersal", "pelagic"}


def substrate_ok(name: str, node: Node) -> bool:
    """Part-dial substrate check (user: manes only for fur; no webbed
    feet on horses): without the substrate the dial is inapplicable — the
    R11 "N/A" class, enforced by the sampler/renderer instead of
    per-preset authoring."""
    if name == "mane_ruff_extent":
        return node.generics.get("covering") == "fur"
    if name == "foot_webbing_grade":
        loco = str(node.generics.get("locomotor", ""))
        return "aquatic" in loco or \
            node.axes.get("vertical_stratum") in AQUATIC_STRATA
    return True


def _legal_states(spec: AxisSpec, name: str, pack: ContentPack,
                  parent: Node) -> list[str] | None:
    """Restricted legal states for enum redraws; None = unrestricted."""
    if name == "vertical_stratum":
        cur = parent.axes.get("vertical_stratum")
        loco = str(parent.generics.get("locomotor", ""))
        flight = str(parent.axes.get("flight_style"))
        legal = []
        for s in spec.states:
            if s in ("ground", "fossorial"):
                legal.append(s)
            elif s == "aerial":
                if cur == "aerial" or flight in ACTIVE_FLIGHT_STATES:
                    legal.append(s)
            elif s in ARB_STRATA:
                if cur in ARB_STRATA or "scansorial" in loco \
                        or "climbing" in loco:
                    legal.append(s)
            elif s in AQUATIC_STRATA:
                if cur in AQUATIC_STRATA or "aquatic" in loco:
                    legal.append(s)
        return legal or None
    if name not in COLOR_AXES or parent.plan is None:
        return None
    palette = pack.palettes.get(parent.plan)
    if palette is None:
        return None
    preset = pack.presets.get(parent.preset or "", {})
    palette = palette + list(preset.get("preset", {})
                           .get("palette_extra", []))
    legal = [s for s in spec.states if s in palette]
    return legal or None


def _mutate_enum(spec: AxisSpec, value: str, dg: float, g: float,
                 stream: Stream, clock: int, gate: float,
                 legal: list[str] | None = None) -> tuple[str, dict]:
    """Enums are directionless: drift-only redraw, prob ∝ Δg and f(g).
    Redraws come from *legal* states (palette) when restricted."""
    states = legal or spec.states
    p = (1.0 - math.exp(-dg * ENUM_RATE * step_scale(g))) * gate
    if value in spec.states and stream.bernoulli(p, clock):
        idx = stream.randrange(len(states), clock, 1)
        new = states[idx]
        return new, {"drift": 0.0 if new == value else 1.0,
                     "descent": 0.0, "runaway": 0.0}
    return value, {"drift": 0.0, "descent": 0.0, "runaway": 0.0}


def _mutate_weighted_set(spec: AxisSpec, value: dict, dg: float, g: float,
                         stream: Stream, clock: int,
                         gate: float) -> tuple[dict, dict]:
    """Jitter weights ∝ step, renormalize."""
    step = math.sqrt(dg) * step_scale(g) * (spec.sigma or 0.1) * gate
    out = {}
    for i, (k, w) in enumerate(sorted(value.items())):
        out[k] = w * math.exp(step * stream.normal(clock, i))
    total = sum(out.values()) or 1.0
    return {k: w / total for k, w in out.items()}, {
        "drift": step, "descent": 0.0, "runaway": 0.0}


# ── the evolve step ──────────────────────────────────────────────────────


def evolve(parent: Node, pack: ContentPack, stream: Stream, dg_base: float,
           *, path: str, condition: Condition | None = None,
           clade_center: dict[str, float] | None = None,
           runaway_dir: float | None = None,
           couplings: bool = True,
           weak: list | None = None,
           rate_mult: float | None = None,
           rank: Rank | None = None,
           rebindable: tuple | None = None,
           unbindable: tuple | None = None,
           rebind_rate: float | None = None,
           derived_axes=None) -> Node:
    """Produce a descendant of *parent* after dg_base base generations.

    *stream* is the lineage's own substream (determinism: same lineage,
    same draws). *clade_center* maps axis -> clade mean for the descent
    force (None = no descent). *runaway_dir* is the clade's seeded ±1
    (None = drawn from the lineage stream, so a lineage is consistent).
    *couplings* runs the M6 rule pass after mutation (False = control).
    *rebindable* / *unbindable* / *rebind_rate* override the generic-
    rebind tables (K14 flora passes its own set — dispersal replaces
    locomotor); *derived_axes* overrides the module DERIVED_AXES set for
    the same reason. Defaults are the K13 fauna tables, unchanged.
    """
    condition = condition or Condition()
    if derived_axes is None:
        from exp.k13_treegen.derive import DERIVED_AXES as derived_axes
    shares = share_ratios(condition)
    dg = dg_base * (1.0 + STRESS_G_BOOST * condition.stress)
    g_line = parent.g + dg
    p_novel = P_NOVEL_MAX * (1.0 - math.exp(-g_line / G_NOVEL))
    if runaway_dir is None:
        runaway_dir = 1.0 if stream.child("runaway_dir").bernoulli(
            0.5, 0) else -1.0

    axes: dict = {}
    edge_delta: dict = {}
    for clock, (name, value) in enumerate(sorted(parent.axes.items())):
        spec = pack.registry.axes.get(name)
        if spec is None or value == "N/A":
            axes[name] = value
            continue
        if name in derived_axes:
            axes[name] = value   # recomputed from the record, never drifts
            continue
        if not substrate_ok(name, parent):
            axes[name] = value   # no substrate: the dial is frozen
            continue
        gate = _tier_gate(spec, parent.g)
        if gate == 0.0:
            axes[name] = value
            continue
        if spec.value_type in (ValueType.SCALAR, ValueType.INT) \
                and isinstance(value, (int, float)):
            center = (clade_center or {}).get(name)
            new, delta = _mutate_scalar(
                spec, float(value), dg, g_line, shares,
                adapt_weight(pack, spec), stream.child(name), clock,
                center, runaway_dir, p_novel, gate)
            if spec.value_type is ValueType.INT:
                new = int(round(new))
        elif spec.value_type is ValueType.ENUM:
            new, delta = _mutate_enum(
                spec, str(value), dg, g_line, stream.child(name), clock,
                gate, _legal_states(spec, name, pack, parent))
        elif spec.value_type is ValueType.WEIGHTED_SET \
                and isinstance(value, dict):
            new, delta = _mutate_weighted_set(spec, value, dg, g_line,
                                              stream.child(name), clock,
                                              gate)
        else:
            new, delta = value, None
        axes[name] = new
        if delta and any(v for v in delta.values()):
            edge_delta[name] = delta

    rate = (rate_mult if rate_mult is not None
            else rate_multiplier(stream.child("lineage_rate")))
    mass = axes.get("body_mass")
    gen_time = (gen_time_years(float(mass), rate)
                if isinstance(mass, (int, float)) and mass > 0 else 0.0)
    child = Node(
        path=path, rank=rank if rank is not None else parent.rank,
        parent=parent.path,
        sid=f"{stream.u64(0):016x}", plan=parent.plan,
        preset=parent.preset, label=None, g=g_line, gen_time=gen_time,
        axes=axes, generics=dict(parent.generics),
        flags=[f for f in parent.flags if f != "pinned"],
        edge_delta=edge_delta,
    )
    # generic rebind: one draw per speciation edge, plan-legal only
    reb = REBINDABLE if rebindable is None else rebindable
    unb = UNBINDABLE if unbindable is None else unbindable
    rrate = REBIND_RATE if rebind_rate is None else rebind_rate
    plan_g = pack.registry.plans.get(parent.plan or "")
    table = plan_g.generics if plan_g else {}
    cands = [g for g in reb if g in table]
    rstream = stream.child("rebind")
    if cands and rstream.bernoulli(
            1.0 - math.exp(-dg * rrate), 0):
        g = cands[rstream.randrange(len(cands), 1)]
        states = list(table[g]) + ([None] if g in unb else [])
        cur = child.generics.get(g)
        alts = [s for s in states if s != cur]
        if alts:
            new = alts[rstream.randrange(len(alts), 2)]
            if new is None:
                child.generics.pop(g, None)
            else:
                child.generics[g] = new
            child.edge_delta["generic_rebind"] = {g: [cur, new]}
    if couplings:
        from exp.k13_treegen.couplings import apply_couplings
        apply_couplings(parent, child, pack, condition,
                        stream.child("couplings"), weak=weak)
    # soft per-preset mass envelope (ENVELOPE_LOG10/DAMP): no convergence
    # anchor, but a leaky squash on sustained far-walks.
    mass = child.axes.get("body_mass")
    if isinstance(mass, (int, float)) and mass > 0 and child.preset:
        pm = pack.preset_body_mass(child.preset)
        if pm:
            dex = math.log10(mass / pm)
            if abs(dex) > ENVELOPE_LOG10:
                excess = abs(dex) - ENVELOPE_LOG10
                new_dex = math.copysign(
                    ENVELOPE_LOG10 + excess * ENVELOPE_DAMP, dex)
                child.axes["body_mass"] = pm * 10.0 ** new_dex
                child.gen_time = gen_time_years(
                    float(child.axes["body_mass"]), rate)
    return child
