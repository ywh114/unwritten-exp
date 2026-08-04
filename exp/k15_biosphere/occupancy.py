"""The per-cell occupancy data model for the K15 biosphere rewrite
(ticket 0045; spec B10 §1, B8).

The L2 data+accounting layer: per cell, per-lineage biomass holdings
(the stored primitive) and the four derived quantities the L3 stages
read — computed on read, never stored:

- **Coverage per structural layer** — geometric budgets from B7
  geometry: a layer's plane packs ~cell_area / crown_area adults
  (canopy-class layers, per-lineage via the view's ``crown_spread_m``)
  or bounds swards/mats likewise (ground-class layers, via the view's
  ``mass_proportions`` footprint / cover / per-area keys).  Budgets are
  SPACE, never productivity — two cells at different productivity pack
  the same crowns.
- **The productivity pool** (B8): ``C(c) = productivity · X · cell_ha``
  with ``X = 400 t/ha per productivity unit`` (``POOL_X_T_PER_HA``),
  linear in p, per-hectare so resolution-independent.  The biomass
  guardrail.
- **Substrate-weighted demand** — per-lineage demand (a Lineage
  scalar) × the cell's substrate mix matching the lineage's
  preferences, multiplicative (B10 §1's unit-calibration anchor).
- **Remainder** — pool and coverage left after current holdings; this
  is the A/B mechanism (B10 §6.1) that later painting stages read.

No dynamics, no stress: painting APPLIES a biomass delta in full and
REPORTS any overshoot (coverage > budget, holdings > pool) — never
silently clamps.  Caps are guardrails; crowding stress (a later
ticket, B10 §5) is the mechanism.

Kingdom-neutral (interface.py contract): occupancy reads the assembled
species VIEW only — a Lineage carries its view dict, never a record or
a kingdom hook — so the same accounting serves flora and fauna.  The
view's ``layer`` key drives layer assignment; the per-lineage area
reference resolves from view geometry (see ``reference_area_m2``).

Determinism hard rule: no randomness, no wall-clock; float
accumulation in sorted order (lineages sorted by ref, sums over
sorted refs / sorted substrates); two identical builds are equal and
byte-stable.

Substrates are SYNTHETIC for now (``SUBSTRATE_TYPES``): the real
substrate pass — and the lineage substrate-preference axis in the
content — is a deferred B2 addendum (B3 spec).  The synthetic
vocabulary below is a minimal representative set of ground/water-bed
classes; it will be replaced by the B2 pass's class map, unchanged
downstream.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

# ══════════════════════════════════════════════════════════════════════
# ──  constants  ─────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

# B8: the productivity pool X — t/ha per productivity unit (provisional;
# revisit with ticket 0019 — it may need readjustment or become moot).
POOL_X_T_PER_HA = 400.0

CELL_M2_PER_HA = 10000.0        # cell_ha -> m² (coverage budgets' plane)

# The SYNTHETIC substrate vocabulary (deferred B2 addendum, see the
# module docstring): a minimal representative set of ground/seabed
# classes, covering the real content's plants (peat/sand for swards,
# mud/sand for benthics, ...).
SUBSTRATE_TYPES = ("sand", "silt", "clay", "gravel", "peat", "bedrock")

# Which layers are ground-class (footprint-driven coverage: swards,
# mats, per-area models) vs canopy-class (crown-driven: everything
# else — canopy, subcanopy, shrub, epiphyte, and any future value).
GROUND_CLASS_LAYERS = frozenset({
    "sward", "ground", "aquatic_surface", "aquatic_benthic",
})

# The mass hook's group fallback for per-capita space when neither a
# crown nor a footprint key is available (flora/mass.py footprint_m2:
# everything else -> (0.3·H)²).  Mirrored here so coverage stays
# consistent with the mass model for columnar / spore-mass plans.
FALLBACK_CROWN_FACTOR = 0.3


# ══════════════════════════════════════════════════════════════════════
# ──  input records  ─────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CellInput:
    """The per-cell fields occupancy accounts against (B10 §1).

    ``productivity`` is on the absolute B2 scale: 1.0 = a productive
    class, tropical moist forest ≈ 2.5, terrestrial range ≈ 0–2.5 (+
    bounded bonuses).  ``cell_ha`` makes the pool per-hectare (1600 ha
    at 256², 100 ha at 1024² — resolution-independent).  ``substrate_mix``
    maps the synthetic substrate class -> fraction (a pmf over
    ``SUBSTRATE_TYPES``).  NO climate fields — those are L3's business.
    """

    productivity: float
    cell_ha: float
    substrate_mix: Mapping[str, float]

    def __post_init__(self) -> None:
        if not (isinstance(self.productivity, (int, float))
                and self.productivity >= 0.0):
            raise ValueError(
                f"productivity must be a non-negative number on the B2 "
                f"scale (got {self.productivity!r})")
        if not (isinstance(self.cell_ha, (int, float)) and self.cell_ha > 0.0):
            raise ValueError(
                f"cell_ha must be > 0 (got {self.cell_ha!r})")
        mix = dict(self.substrate_mix)
        unknown = sorted(set(mix) - set(SUBSTRATE_TYPES))
        if unknown:
            raise ValueError(
                f"substrate_mix has substrates outside the synthetic "
                f"vocabulary {SUBSTRATE_TYPES}: {unknown}")
        if not mix:
            raise ValueError("substrate_mix must be non-empty")
        for s, frac in mix.items():
            if not (isinstance(frac, (int, float)) and frac >= 0.0):
                raise ValueError(
                    f"substrate_mix fractions must be non-negative "
                    f"(got {s}: {frac!r})")
        total = sum(mix.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"substrate_mix is a pmf and must sum to 1.0 "
                f"(got {total:.4f})")
        object.__setattr__(self, "substrate_mix", mix)


@dataclass(frozen=True)
class Lineage:
    """One lineage's stake in a cell (B10 §1).

    ``view`` is the assembled species view (B9 §3 — the ONLY derive
    path); occupancy reads view geometry/mass/layer keys and nothing
    else.  ``substrate_pref`` maps the synthetic substrate class ->
    suitability weight in [0, 1]; a missing key reads 0.0 (the class is
    unusable — B8's spill-at-reduced-suitability is a preference over
    several classes, authored here), and an EMPTY preference matches
    everything at full weight (no substrate preference = full match).
    ``demand_t`` is the biomass (t) the lineage would draw at full
    substrate match — a Lineage scalar, set by the painting stage;
    ``substrate_weighted_demand_t`` reports it × the cell's match.
    """

    ref: str
    view: Mapping[str, object]
    substrate_pref: Mapping[str, float] = field(default_factory=dict)
    demand_t: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.ref, str) or not self.ref:
            raise ValueError(
                f"lineage ref must be a non-empty string (got {self.ref!r})")
        pref = dict(self.substrate_pref)
        unknown = sorted(set(pref) - set(SUBSTRATE_TYPES))
        if unknown:
            raise ValueError(
                f"substrate_pref has substrates outside the synthetic "
                f"vocabulary {SUBSTRATE_TYPES}: {unknown}")
        for s, w in pref.items():
            if not (isinstance(w, (int, float)) and 0.0 <= w <= 1.0):
                raise ValueError(
                    f"substrate_pref weights must be in [0, 1] "
                    f"(got {s}: {w!r})")
        if not (isinstance(self.demand_t, (int, float))
                and self.demand_t >= 0.0):
            raise ValueError(
                f"demand_t must be non-negative (got {self.demand_t!r})")
        object.__setattr__(self, "substrate_pref", pref)


# ══════════════════════════════════════════════════════════════════════
# ──  the painting report  ───────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class PaintReport:
    """What one paint did — the ledger line a painting stage reads.

    ``overshoots`` names the budgets the resulting holdings exceed,
    in fixed order (subset of {"pool", "coverage"}); the magnitudes are
    reported separately (``overshoot_pool_t`` / ``overshoot_coverage_m2``)
    so the caller sees HOW MUCH over, never silently clamped.  Coverage
    is the layer's used/budget fraction and may exceed 1.0.
    """

    ref: str
    delta_t: float
    holdings_t: float            # this lineage's holding after (t)
    pool_used_t: float           # whole cell after (t)
    pool_remainder_t: float      # pool − pool_used after (t)
    layer: str                   # the lineage's structural layer
    coverage: float              # that layer's coverage fraction after
    layer_used_m2: float         # that layer's covered area after (m²)
    layer_remainder_m2: float    # cell_area − layer_used after (m²)
    overshoots: tuple[str, ...]  # "pool" / "coverage" exceeded, sorted
    overshoot_pool_t: float      # max(0, pool_used − pool) (t)
    overshoot_coverage_m2: float  # max(0, layer_used − cell_area) (m²)
    substrate_match: float       # the cell's matching substrate fraction
    substrate_weighted_demand_t: float  # demand × match (t)


# ══════════════════════════════════════════════════════════════════════
# ──  the occupancy state  ───────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

@dataclass
class OccupancyState:
    """One cell's occupancy state (B10 §1): holdings + derived reads.

    ``holdings_t`` (lineage ref -> biomass t) is the STORED primitive;
    everything else — pool usage, per-layer coverage, substrate-weighted
    demand, remainders — is computed on read, never stored.  Lineages
    are sorted by ref at construction (deterministic iteration and
    float accumulation).  ``paint`` is the only mutation path.
    """

    cell: CellInput
    lineages: tuple[Lineage, ...]
    holdings_t: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.lineages:
            raise ValueError("a cell needs at least one lineage")
        refs = [ln.ref for ln in self.lineages]
        dup = sorted({r for r in refs if refs.count(r) > 1})
        if dup:
            raise ValueError(
                f"lineage refs must be unique (duplicated: {dup})")
        self.lineages = tuple(sorted(self.lineages, key=lambda ln: ln.ref))
        self.holdings_t = {ln.ref: 0.0 for ln in self.lineages}

    # ── lineage lookup (all reads go through here) ──

    def _lineage(self, ref: str) -> Lineage:
        for ln in self.lineages:
            if ln.ref == ref:
                return ln
        raise ValueError(
            f"no lineage {ref!r} in this cell "
            f"(have {sorted(ln.ref for ln in self.lineages)})")

    @staticmethod
    def _num(value: object) -> float:
        return float(value) if isinstance(value, (int, float)) else 0.0

    # ── the cell's geometry and pool (computed on read) ──

    @property
    def cell_area_m2(self) -> float:
        """The coverage budgets' plane (m²) — cell_ha × 10000."""
        return self.cell.cell_ha * CELL_M2_PER_HA

    @property
    def pool_t(self) -> float:
        """B8: C(c) = productivity · X · cell_ha — linear in p, the
        biomass guardrail (per-hectare, resolution-independent)."""
        return (self.cell.productivity * POOL_X_T_PER_HA
                * self.cell.cell_ha)

    @property
    def pool_used_t(self) -> float:
        """Σ lineage holdings, accumulated over refs in sorted order."""
        return sum(self.holdings_t[r] for r in sorted(self.holdings_t))

    @property
    def pool_remainder_t(self) -> float:
        """Pool left for later painting stages — the A/B mechanism."""
        return self.pool_t - self.pool_used_t

    # ── per-lineage reads ──

    def layer_of(self, ref: str) -> str:
        """The lineage's structural layer — the view's ``layer`` key
        drives layer assignment (defaults to "ground", the assembler's
        own neutral)."""
        return str(self._lineage(ref).view.get("layer") or "ground")

    def percap_kg(self, ref: str) -> float:
        """Per-individual dry biomass (kg) from the view's
        ``mass_total_kg``; 0.0 when the view has no mass model."""
        return self._num(self._lineage(ref).view.get("mass_total_kg"))

    def individuals(self, ref: str) -> float:
        """Equivalent individual count for the holding: holdings (t)
        × 1000 / percap (kg).  0.0 when the view carries no mass model
        (nothing countable, no space claim — the biomass still counts
        against the pool)."""
        percap = self.percap_kg(ref)
        if percap <= 0.0:
            return 0.0
        return self.holdings_t[ref] * 1000.0 / percap

    @staticmethod
    def _crown_area_m2(view: Mapping[str, object]) -> float:
        """Crown area from the view's ``crown_spread_m``; the mass
        hook's (0.3·H)² group fallback when no crown is carried; 0.0
        when neither exists (no space claim)."""
        crown = view.get("crown_spread_m")
        if isinstance(crown, (int, float)) and crown > 0.0:
            return math.pi * (crown / 2.0) ** 2
        height = view.get("height_m")
        if isinstance(height, (int, float)) and height > 0.0:
            return (FALLBACK_CROWN_FACTOR * height) ** 2
        return 0.0

    def reference_area_m2(self, ref: str) -> float:
        """The per-unit area (m²) this lineage claims in its layer.

        Ground-class layers (sward, ground, aquatic_*) resolve from the
        view's mass proportions, in the mass hook's own keys — so
        coverage stays consistent with the percap mass:
        ``footprint_m2`` (swards/mats that carry it) → ``cover_m2``
        (herbs/ferns) → ``kg_m2`` (moss/mat/lichen per-area models,
        where per-individual area = percap_kg / kg_m2) → the crown
        fallback.  Canopy-class layers (canopy, subcanopy, shrub,
        epiphyte, anything unknown) pack by crown area from
        ``crown_spread_m``.  Returns 0.0 when nothing is available."""
        view = self._lineage(ref).view
        if self.layer_of(ref) not in GROUND_CLASS_LAYERS:
            return self._crown_area_m2(view)
        props = view.get("mass_proportions") or {}
        for key in ("footprint_m2", "cover_m2"):
            area = self._num(props.get(key))
            if area > 0.0:
                return area
        kg_m2 = self._num(props.get("kg_m2"))
        percap = self._num(view.get("mass_total_kg"))
        if kg_m2 > 0.0 and percap > 0.0:
            return percap / kg_m2
        return self._crown_area_m2(view)

    def substrate_match(self, ref: str) -> float:
        """The cell's matching substrate fraction for the lineage:
        Σ over substrates (sorted) of mix[s] × pref[s].  Multiplicative
        (B10 §1); an empty preference matches everything at 1.0."""
        pref = self._lineage(ref).substrate_pref
        if not pref:
            return 1.0
        return sum(self.cell.substrate_mix[s] * pref.get(s, 0.0)
                   for s in sorted(self.cell.substrate_mix))

    def substrate_weighted_demand_t(self, ref: str) -> float:
        """The lineage's demand at full match × the cell's matching
        substrate fraction — what the lineage can actually draw."""
        return self._lineage(ref).demand_t * self.substrate_match(ref)

    # ── per-layer reads ──

    def layer_used_m2(self, layer: str) -> float:
        """Covered area in *layer*: Σ over refs (sorted) of
        individuals × reference area.  May exceed cell_area (reported,
        never clamped)."""
        return sum(
            self.individuals(r) * self.reference_area_m2(r)
            for r in sorted(self.holdings_t)
            if self.layer_of(r) == layer)

    def layer_remainder_m2(self, layer: str) -> float:
        """The layer's plane left for later stages (may go negative —
        overshoot is reported, never clamped)."""
        return self.cell_area_m2 - self.layer_used_m2(layer)

    def coverage(self, layer: str) -> float:
        """The layer's used/budget fraction (budget = cell_area); may
        exceed 1.0 when the layer is overshooting its geometric budget."""
        return self.layer_used_m2(layer) / self.cell_area_m2

    # ── painting ──

    def paint(self, ref: str, delta_t: float) -> PaintReport:
        """Apply a biomass delta (t) to *ref* with remainder accounting.

        The delta is applied IN FULL — an overshooting paint is reported
        (``PaintReport.overshoots`` / magnitudes), never silently
        clamped: caps are guardrails; crowding stress (a later ticket,
        B10 §5) is the mechanism.  Raises ValueError for an unknown ref
        or a delta that would push a holding below zero.
        """
        self._lineage(ref)      # unknown-ref guard
        new = self.holdings_t[ref] + delta_t
        if new < 0.0:
            raise ValueError(
                f"paint: delta {delta_t:g} would take {ref!r} below zero "
                f"(holdings {self.holdings_t[ref]:g} t)")
        self.holdings_t[ref] = new

        layer = self.layer_of(ref)
        used = self.layer_used_m2(layer)
        pool_used = self.pool_used_t
        pool_t = self.pool_t
        overshoots: list[str] = []
        if pool_used > pool_t:
            overshoots.append("pool")
        if used > self.cell_area_m2:
            overshoots.append("coverage")
        return PaintReport(
            ref=ref, delta_t=delta_t, holdings_t=new,
            pool_used_t=pool_used, pool_remainder_t=pool_t - pool_used,
            layer=layer, coverage=used / self.cell_area_m2,
            layer_used_m2=used, layer_remainder_m2=self.cell_area_m2 - used,
            overshoots=tuple(overshoots),
            overshoot_pool_t=max(0.0, pool_used - pool_t),
            overshoot_coverage_m2=max(0.0, used - self.cell_area_m2),
            substrate_match=self.substrate_match(ref),
            substrate_weighted_demand_t=self.substrate_weighted_demand_t(ref),
        )
