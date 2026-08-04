"""Crowding fields, competition stress, and the derived cap (ticket
0046; spec B10 §1, §2, §5, §6).

The mechanism half of L2.  Crowding fields — one per shared resource,
computed from the occupancy state and NOTHING else (B10 §1):

- **canopy** — the height-stratified canopy profile: per canopy-layer
  lineage its height (the view's ``height_m``) and its covered fraction
  of the cell plane (individuals × reference area / cell area —
  occupancy's own geometry), sorted by height so the profile CARRIES
  height structure.  This is the field the shade step (§4) reads: a
  canopy that is all one crown at the top shades deeply and flatly
  below it, and the covered fraction concentrated just under the top
  is what makes the marginal-relief step exist.
- **ground_cover** — the ground-class layers' coverage shares of the
  cell plane.
- **substrate** — per-class claimed fractions and the total contested
  pressure.

The crowding function maps a shared resource's demand pressure to a
crowding scalar in [0, 1]; the three competition stress types (B10 §2 —
the initial sanity-check set, no more) each read their resource's field
and return a scalar with provenance (which resource, which lineages
dominate it) as a PURE function of (view, OccupancyState): probing —
nudge a view trait, recompute, read the difference (B10 §4) — never
mutates anything.

CALIBRATION (B10 §5): the lineage cap is DERIVED — the n=1
(monoculture) solution of the crowding system — and f is the target it
must match.  At n=1 a lone lineage with holdings x reads

    canopy        0   (nothing stands above it — its crown is the top)
    ground_cover  0   (no claim on the ground plane, canopy lineage)
    substrate     crowding(x / C),  C = f(p) · L · cell_ha · match(ref)

Growth zeroes at total crowding 1 ⇒ x* = C = f(p)·L·cell_ha·match(ref):
the cap is the monoculture solution of the same crowding function, so
no guardrail can disagree with it.  C carries the owner's prodscale
target f (FIXED — the calibration target, never tuned) and the one
tuning knob L (the lineage cap at unit productivity, started at the
midpoint 0.625 of the spec's 0.5–0.75 band of the p=1 cell pool); the
crowding scalar with g(1) = 1 closes the loop.  The cell pool stays
linear in p — productivity buys lineage count, never lineage size
(f(2.5) ≈ 1.04 against a pool ×2.5; f(0.75) ≈ 0.90 — a rainforest
canopy lineage caps ~16% above a temperate one while its cell pool is
3.3× larger).

Determinism hard rule: no randomness, no wall-clock; iteration over
lineages / strata / substrate classes is sorted; float accumulation in
sorted order; two identical builds are byte-stable.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Mapping

from exp.k15_biosphere.occupancy import (
    GROUND_CLASS_LAYERS,
    OccupancyState,
    POOL_X_T_PER_HA,
)

# ══════════════════════════════════════════════════════════════════════
# ──  the derived cap: prodscale f and the one tuning knob L (B10 §5)  ───
# ══════════════════════════════════════════════════════════════════════


def prodscale_f(p: float) -> float:
    """The owner's prodscale target (B10 §5): f(p) = 5/4 − 4^(−p) for
    p < 1, f(p) = 39/40 + p/40 for p ≥ 1, anchored f(1) = 1.  Against
    the real B2 scale: f(2.5) ≈ 1.04, f(0.75) ≈ 0.90 — nearly
    productivity-flat above unit.  p is the cell's productivity (≥ 0,
    CellInput-validated)."""
    if p < 1.0:
        return 1.25 - 4.0 ** (-p)
    return 0.975 + p / 40.0


# L, the one tuning knob (B10 §5): the lineage cap at unit productivity
# as a fraction of the p=1 cell pool.  Started at the midpoint of the
# spec's 0.5–0.75 band; the Phase-2 probe's top-species per-cell median
# share (75%) sits at the band's top.  EVERY cap scales linearly with
# this; f is never touched.
LINEAGE_CAP_POOL_FRACTION = 0.625


def lineage_cap_scale_t(state: OccupancyState) -> float:
    """L · cell_ha (tonnes): the lineage-cap scale for this cell —
    0.625 × the p=1 cell pool (B10 §5)."""
    return LINEAGE_CAP_POOL_FRACTION * POOL_X_T_PER_HA * state.cell.cell_ha


def substrate_capacity_t(state: OccupancyState, ref: str) -> float:
    """C(ref) = f(p) · L · cell_ha · match(ref) — the matching-substrate
    capacity (tonnes) the n=1 crowding equilibrium is calibrated against
    (B10 §5: the cap scales with the matching-substrate ha — a sward
    covering all of its preferred substrate has a reasonable mass, one
    on half its substrate caps at half).  0.0 for a lineage with no
    usable substrate in the cell (match 0): nothing to claim, no
    pressure, no capacity."""
    return (prodscale_f(state.cell.productivity)
            * lineage_cap_scale_t(state)
            * state.substrate_match(ref))


def crowding(pressure: float) -> float:
    """The crowding scalar for a shared resource: demand pressure →
    crowding in [0, 1].  g(p̃) = min(1, p̃): g(0) = 0 (no pressure, no
    crowding), g(1) = 1 (the n=1 calibration point — a pressure of one
    capacity zeroes net growth), saturating beyond (full suppression,
    never oversuppression).  Any monotone g with g(1) = 1 satisfies the
    n=1 calibration; the shape is the L3 pressure machinery's tuning
    surface, not a second knob here."""
    return min(1.0, pressure)


# ══════════════════════════════════════════════════════════════════════
# ──  the crowding fields (B10 §1 — pure functions of the occupancy)  ────
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CanopyProfile:
    """The height-stratified canopy field (B10 §1): the cell's canopy
    as (ref, height, covered fraction) strata — the covered fraction of
    the cell plane each canopy-layer lineage holds (individuals ×
    reference area / cell area — occupancy's own geometry) — sorted by
    height DESCENDING (ties by ref) so the profile carries height
    structure.  Only lineages with a positive covered fraction appear.

    ``coverage_strictly_above(h)`` is the profile's shading function —
    the fraction of the plane covered by canopy standing strictly above
    height *h* — the field the shade stress (and its benefit step, B10
    §4) reads."""

    strata: tuple[tuple[str, float, float], ...]
    top_height_m: float
    covered_fraction: float

    def coverage_strictly_above(self, height_m: float) -> float:
        """Σ covered fractions of strata with height > *height_m* —
        accumulated over the height-descending strata in order."""
        return sum(frac for _, h, frac in self.strata if h > height_m)


def canopy_profile(state: OccupancyState) -> CanopyProfile:
    """The canopy field (B10 §1): every canopy-class lineage (a layer
    outside GROUND_CLASS_LAYERS — canopy, subcanopy, shrub, epiphyte,
    ...) with a positive covered fraction, as a height-descending
    stratum list.  Ground-class lineages never appear: swards shade
    nothing."""
    cell_area = state.cell_area_m2
    strata: list[tuple[str, float, float]] = []
    for ln in state.lineages:                    # already sorted by ref
        if state.layer_of(ln.ref) in GROUND_CLASS_LAYERS:
            continue
        h = ln.view.get("height_m")
        h = float(h) if isinstance(h, (int, float)) else 0.0
        cover = (state.individuals(ln.ref)
                 * state.reference_area_m2(ln.ref) / cell_area)
        if cover > 0.0:
            strata.append((ln.ref, h, cover))
    strata.sort(key=lambda s: (-s[1], s[0]))
    return CanopyProfile(
        strata=tuple(strata),
        top_height_m=strata[0][1] if strata else 0.0,
        covered_fraction=sum(frac for _, _, frac in strata),
    )


@dataclass(frozen=True)
class GroundCoverField:
    """The ground-cover share field (B10 §1): each ground-class
    lineage's covered fraction of the cell plane (sorted by ref), and
    the total share — the fraction of the ground plane contested.  The
    total may exceed 1.0 (overshoot is reported, never clamped)."""

    shares: tuple[tuple[str, float], ...]
    total_share: float


def ground_cover_field(state: OccupancyState) -> GroundCoverField:
    """The ground-cover share field: ground-class lineages (sward,
    ground, aquatic_surface, aquatic_benthic) with a positive covered
    fraction, sorted by ref."""
    cell_area = state.cell_area_m2
    shares: list[tuple[str, float]] = []
    for ln in state.lineages:                    # already sorted by ref
        if state.layer_of(ln.ref) not in GROUND_CLASS_LAYERS:
            continue
        cover = (state.individuals(ln.ref)
                 * state.reference_area_m2(ln.ref) / cell_area)
        if cover > 0.0:
            shares.append((ln.ref, cover))
    return GroundCoverField(shares=tuple(shares),
                            total_share=sum(frac for _, frac in shares))


@dataclass(frozen=True)
class SubstrateField:
    """The substrate share field (B10 §1): the per-class claimed
    fraction (Σ over lineages of holdings × preference for the class /
    the class's capacity f(p)·L·cell_ha·mix[class]), the per-lineage
    pressures (holdings / C(ref)), and the total contested pressure
    Q = Σ pressures — the field the substrate stress reads.  Pressures
    use the lineage's HOLDINGS (the biomass actually present — what
    painting moves), not the static demand_t: crowding must respond to
    the round loop (crowding recomputed after every paint).  Lineages
    with no usable substrate (match 0) contribute nothing."""

    per_class: tuple[tuple[str, float], ...]
    pressures: tuple[tuple[str, float], ...]
    total_pressure: float


def substrate_field(state: OccupancyState) -> SubstrateField:
    """The substrate share field: per-class claimed fractions (classes
    sorted; claims are holdings × preference, allocated in lineage-ref
    order) and per-lineage pressures (holdings / capacity, in ref
    order)."""
    f = prodscale_f(state.cell.productivity)
    scale = lineage_cap_scale_t(state)
    per_class: list[tuple[str, float]] = []
    for s in sorted(state.cell.substrate_mix):
        capacity_s = f * scale * state.cell.substrate_mix[s]
        claim = sum(state.holdings_t[ln.ref]
                    * ln.substrate_pref.get(s, 0.0)
                    for ln in state.lineages)    # ref-sorted accumulation
        per_class.append((s, claim / capacity_s if capacity_s > 0.0
                          else 0.0))
    pressures: list[tuple[str, float]] = []
    total = 0.0
    for ln in state.lineages:                    # already sorted by ref
        cap = substrate_capacity_t(state, ln.ref)
        p = state.holdings_t[ln.ref] / cap if cap > 0.0 else 0.0
        pressures.append((ln.ref, p))
        total += p
    return SubstrateField(per_class=tuple(per_class),
                          pressures=tuple(pressures),
                          total_pressure=total)


# ══════════════════════════════════════════════════════════════════════
# ──  competition stress (B10 §2 — the initial sanity-check set)  ────────
# ══════════════════════════════════════════════════════════════════════

# responder wiring documentation, house style (the responder TABLE is
# L3 content; B10 §2's trait wiring: canopy → height/crown, substrate →
# roots/substrate preference, phenology → leafout/bloom timing).
CANOPY_WIRING = (
    "responder traits height_m / crown_spread_m (canopy → height/crown): "
    "a lineage below the canopy profile is pulled through the shade step "
    "by marginal relief (probed); deep below it, zero marginal relief — "
    "no height pull, adaptation toward shade tolerance instead (B10 §4). "
    "The responder TABLE is L3 content."
)
GROUND_COVER_WIRING = (
    "responder traits height_m / crown_spread_m / footprint (ground → "
    "cover): the ground plane's contest is relieved by partitioning, "
    "not outgrowing it.  The responder TABLE is L3 content."
)
SUBSTRATE_WIRING = (
    "responder traits root_depth_m / substrate preference (substrate → "
    "roots): the substrate contest is relieved by partitioning across "
    "classes (B10 §2 — the only true escape).  The responder TABLE is "
    "L3 content."
)

# how many lineages name in the provenance (deterministic: by
# covered fraction / pressure descending, ties by ref).
PROVENANCE_TOP_N = 3


def _term(key: str, value: float, resource: str, cause: str,
          dominant_refs: tuple[str, ...], field: dict, wiring: str) -> dict:
    """Assemble one competition-stress term: the scalar ``value`` (the
    vital cost), the resource it is wired to, human ``cause``, the
    ``dominant_refs`` provenance (which lineages dominate the field),
    the ``field`` read, and the responder ``wiring`` — mirroring the
    intrinsic-stress term shape in flora/view.py."""
    return dict(key=key, value=value, resource=resource, cause=cause,
                dominant_refs=dominant_refs, field=field, wiring=wiring)


def _dominant_refs(entries: tuple[tuple[str, float, ...], ...],
                   frac_index: int) -> tuple[str, ...]:
    """The up-to-``PROVENANCE_TOP_N`` refs dominating a field, by their
    covered fraction / pressure (descending), ties by ref — the
    deterministic provenance."""
    return tuple(e[0] for e in
                 sorted(entries, key=lambda e: (-e[frac_index], e[0]))
                 [:PROVENANCE_TOP_N])


def competition_canopy(view: Mapping, state: OccupancyState) -> dict:
    """competition:canopy — shade (B10 §2): stress as a function of the
    lineage's height RELATIVE to the local canopy profile — the shaded
    fraction of the cell plane covered by canopy standing strictly above
    it.  This is where the benefit step lives (§4): well below the
    profile the shade is high and FLAT (small height gains buy no
    marginal relief — the shade trap, zero pull toward height); just
    below the canopy top a nudge crosses the top stratum's coverage
    (strong marginal relief — the lineage is dragged through the step);
    at or above the top it is quiet (0 — nothing stands above the
    lineage's own crown)."""
    h = view.get("height_m")
    h = float(h) if isinstance(h, (int, float)) else 0.0
    prof = canopy_profile(state)
    shade = prof.coverage_strictly_above(h)
    if not prof.strata:
        cause = "no canopy in this cell (quiet)"
    elif shade <= 0.0:
        cause = (f"at/above the canopy top {prof.top_height_m:.3g} m "
                 f"— quiet")
    else:
        n = len(prof.strata)
        cause = (f"shade {shade:.3g}: {n} "
                 f"{'stratum' if n == 1 else 'strata'} above {h:.3g} m "
                 f"(top {prof.top_height_m:.3g} m, "
                 f"total cover {prof.covered_fraction:.3g})")
    return _term(
        key="competition:canopy", value=shade, resource="canopy",
        cause=cause, dominant_refs=_dominant_refs(prof.strata, 2),
        field=dict(top_height_m=prof.top_height_m,
                   covered_fraction=prof.covered_fraction,
                   above_fraction=shade),
        wiring=CANOPY_WIRING)


def competition_ground_cover(view: Mapping, state: OccupancyState) -> dict:
    """competition:ground_cover — share-based crowding stress (B10 §2):
    the ground plane's contested level — crowding(total ground-cover
    share) — for ground-class lineages (swards, mats, aquatic ground
    covers: the lineages that claim the ground plane).  A canopy-class
    lineage reads 0 (no claim on the ground plane).  Reciprocal: when
    one sward's cover grows, every ground dweller's stress grows."""
    layer = str(view.get("layer") or "ground")
    if layer not in GROUND_CLASS_LAYERS:
        return _term(
            key="competition:ground_cover", value=0.0,
            resource="ground_cover",
            cause=f"layer {layer!r} claims no ground plane (quiet)",
            dominant_refs=(), field=dict(total_share=0.0),
            wiring=GROUND_COVER_WIRING)
    fld = ground_cover_field(state)
    return _term(
        key="competition:ground_cover",
        value=crowding(fld.total_share), resource="ground_cover",
        cause=(f"ground-plane contest {fld.total_share:.3g} "
               f"({len(fld.shares)} "
               f"{'claimant' if len(fld.shares) == 1 else 'claimants'})"),
        dominant_refs=_dominant_refs(fld.shares, 1),
        field=dict(total_share=fld.total_share), wiring=GROUND_COVER_WIRING)


def competition_substrate(view: Mapping, state: OccupancyState) -> dict:
    """competition:substrate — share-based crowding stress (B10 §2): the
    substrate's contested level Q = Σ lineages' pressures (holdings /
    matching-substrate capacity) — the same for every lineage in the
    cell, since all biomass draws from the substrate.  Reciprocal: when
    a lineage grows (or adapts to crowd better), everyone's substrate
    stress grows.  The cap is the n=1 monoculture solution of exactly
    this pressure (B10 §5 — see the module docstring)."""
    fld = substrate_field(state)
    claimants = [p for _, p in fld.pressures if p > 0.0]
    return _term(
        key="competition:substrate",
        value=crowding(fld.total_pressure), resource="substrate",
        cause=(f"substrate contest {fld.total_pressure:.3g} "
               f"({len(claimants)} "
               f"{'claimant' if len(claimants) == 1 else 'claimants'})"),
        dominant_refs=_dominant_refs(fld.pressures, 1),
        field=dict(total_pressure=fld.total_pressure,
                   per_class=dict(fld.per_class)),
        wiring=SUBSTRATE_WIRING)


def competition_stress(view: Mapping, state: OccupancyState) -> dict:
    """The B10 §2 competition block: one scalar stress term per shared
    resource — canopy (shade), ground_cover, substrate — each a pure
    function of (view, OccupancyState), summed through the same channel
    as the environmental and intrinsic stresses by L3."""
    return {
        "competition:canopy": competition_canopy(view, state),
        "competition:ground_cover": competition_ground_cover(view, state),
        "competition:substrate": competition_substrate(view, state),
    }


# ══════════════════════════════════════════════════════════════════════
# ──  the n=1 monoculture solution (B10 §5)  ──────────────────────────────
# ══════════════════════════════════════════════════════════════════════


def self_crowding_equilibrium_t(state: OccupancyState, ref: str) -> float:
    """The n=1 monoculture solution (B10 §5): the holdings at which the
    lineage's OWN total crowding — the sum of its three competition
    stresses — reaches 1 and net growth zeroes.  Bisection on a deep
    copy of the state (the stress functions are pure; only the scratch
    copy is mutated).  For a lone canopy lineage this solves to exactly
    f(p) · L · cell_ha · match(ref) — the derived cap (module
    docstring).  Assumes the lineage starts at or below its
    equilibrium; the pool guardrail (occupancy's business) is not
    consulted — crowding is the mechanism, the pool the guardrail."""
    view = next(ln.view for ln in state.lineages if ln.ref == ref)
    st = copy.deepcopy(state)
    current = state.holdings_t[ref]
    cap = substrate_capacity_t(state, ref)

    def total(x: float) -> float:
        st.holdings_t[ref] = x
        terms = competition_stress(view, st)
        return sum(t["value"] for t in terms.values())

    lo = current
    hi = current + max(cap, 1.0)
    # a lone lineage's crowding grows without bound in holdings (the
    # substrate term alone reaches 1 at current + cap); double the
    # bracket until the crossing is inside (guarded — a lineage with no
    # usable substrate and nothing above it never self-crowds).
    guard = 0
    while total(hi) < 1.0 and guard < 64:
        hi = 2.0 * hi
        guard += 1
    if total(lo) >= 1.0:
        return lo
    scale = max(1.0, hi)
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if total(mid) < 1.0:
            lo = mid
        else:
            hi = mid
        if hi - lo <= 1e-9 * scale:
            break
    return (lo + hi) / 2.0
