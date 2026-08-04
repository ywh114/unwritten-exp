"""Per-cell L3 evolutionary pressure with provenance (ticket 0051; spec
B10 §4, §6).

Stress has exactly TWO effects (B10 §3); dynamics.py implements effect 1
(VITAL SUPPRESSION — birth down, death up, the lower equilibrium).  This
module implements effect 2: EVOLUTIONARY PRESSURE with provenance — the
trait backprop through the responder wiring, the trace recording WHY
(the B10 §4 machinery).  The owner rulings, implemented here:

- **pressure = stress × marginal relief.**  The marginal relief of a
  wired trait move is the local change in the stress term PER UNIT
  TRAIT CHANGE, PROBED — nudge the trait, recompute the stress, read
  the difference.  Stress functions are pure, so the probe is
  deterministic and cheap.  Benefits may be NONLINEAR (height pays
  nothing until the crown clears the canopy shading it); the probe
  feels this because it reads the REAL stress landscape, not a
  hand-shaped rule.
- **Strict zero.**  Zero marginal relief → zero pull.  A
  deep-understory tree is NOT pulled toward height (an evolutionary
  leap with no benefit in the middle) — its height pressure reads
  EXACTLY 0.0; it adapts toward shade tolerance and low-energy
  survival, which pay immediately.  A tree one probe step below the
  canopy top feels the step and is dragged through.  Emergent
  lineages are born at gaps and edges, not by grinding.
- **Low stress → no pull.**  Pressure is PROPORTIONAL to the stress
  (``pressure = stress × marginal_relief``): in a low-stress
  environment there is NO selection pressure toward any niche —
  stress relief is the only currency selection spends.
- **Selection force only.**  Marginal-benefit pressure modulates the
  SELECTION force; drift and runaway stay undirected — they are L4's
  (speciation, merging, the g currency), never this module's.  This
  module reports WHICH moves the benefit landscape motivates and HOW
  STRONGLY; it never decides that a move happens.
- **Time-reversal locality.**  Our evolution is after-the-fact
  history that KNOWS the consequences of its moves (closed-form, no
  ticks) — so every step must be locally motivated in both time
  directions: non-decreasing benefit (selection) or neutrality
  (drift).  Because pressure is read from the actual benefit
  landscape, a move crossing a flat-benefit zone (deep understory →
  height) reads ZERO pressure — reversed, every intermediate step
  would be unmotivated, so it never appears as a selected step — and
  a move crossing a benefit step (just below the canopy top) reads
  STRONG pressure — a tree at the step shooting through passes
  time-reversal.  Seeing ahead decides HOW FAR a move goes along a
  motivated path, never WHICH paths are legal (L4's business).

THE PROBE: nudges happen in the RECORD's committed axes (B9 §1 — the
committed traits, never a derived field), the view REASSEMBLED through
the one assembler (flora/view.assemble_view — the only derive path),
and the stress term recomputed.  Nudges ripple through derived
quantities honestly: a height nudge changes the shade read, the
per-capita mass (hence the covered fraction), the canopy profile's own
stratum, and the support ratio in ONE recompute.  Probes run on COPIES
only — the record's axes dict is copied for the nudge, and the
occupancy state is deep-copied with the probed lineage's view swapped
in (the lineage keeps its substrate preference and demand — its
identity, so the crowding stress resolves the probe view to the
lineage's OWN substrate distribution via crowding's identity match);
the caller's record / state / pack are never mutated.

THE WIRING TABLE (``WIRING_TABLE``) is the L3 responder table (B10 §4:
"the responder TABLE is L3 content"): the stress types with machine
wiring — the three competition types (crowding.py) and the two
intrinsic types (flora/view.py) — each with the responder traits and
their allowed move directions, mirroring the human wiring texts in
crowding.py (CANOPY: height_m / crown_spread_m / shade_tolerance —
the tolerance attenuates the shade stress, effective = shade × (1 −
tolerance), direction "+" only, B10 §6.4; GROUND_COVER: height_m /
crown_spread_m / footprint — footprint is the mass-hook geometry
π·max(clonal_spread_m, crown_spread_m)², so clonal_spread_m is wired
as its second driver; SUBSTRATE: root_depth_m / substrate preference —
the preference axis is a deferred B2 addendum, so root_depth_m is the
only probeable responder today) and flora/view.py (MECHANICAL:
crown_spread_m / height_m / wood_density; ENERGETICS: root_depth_m /
root_spread_m).  The table is deliberately MINIMAL and graduates to
content later (ticket note); the environmental responders
(dynamics.py's wiring strings) are not wired yet.  Whether a wired
trait actually carries relief is the LANDSCAPE's call, not the table's:
several wired traits show zero relief on today's content (wood_density
does not enter the support-ratio metric; root_depth_m does not enter
the substrate contest — that contest is relieved by partitioning, a
preference the record does not carry yet); B10 §4's strict zero makes
exactly those traits unpulled, which the probe reports honestly.

Determinism hard rule: no randomness, no wall-clock; iteration over
wired stress types / traits / directions is fixed; probes never
mutate; two identical probes are byte-stable.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from typing import Mapping

from exp.k15_biosphere.content import ContentPack
from exp.k15_biosphere.crowding import competition_stress
from exp.k15_biosphere.flora.view import assemble_view
from exp.k15_biosphere.occupancy import Lineage, OccupancyState
from exp.k15_biosphere.record import SpeciesRecord

# ══════════════════════════════════════════════════════════════════════
# ──  the probe step (B10 §4 — named constant)  ──────────────────────────
# ══════════════════════════════════════════════════════════════════════

# "one small probe step" — RELATIVE to the committed trait value, not
# absolute: wired traits span orders of magnitude (height 0.1–200 m,
# wood_density 0.1–0.8), so a single absolute step cannot be "small"
# everywhere.  1e-3 (0.1% of the trait) reads as a marginal move across
# scales.  A trait committed at 0.0 probes with step 0 — no move, no
# relief (the honest read: the trait expresses nothing to move).
PROBE_REL_STEP = 1e-3

# ══════════════════════════════════════════════════════════════════════
# ──  the L3 responder table (B10 §4)  ───────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

# stress key -> tuple of (trait, allowed directions) — the machine
# mirror of the human wiring texts in crowding.py and flora/view.py
# (the module docstring maps each entry to its text).  The directions
# constrain which moves the probe may consider (feasibility — e.g. a
# non-negative trait's downward move); today's content allows both on
# every wired trait, and the probe reports whichever side the landscape
# relieves.
WIRING_TABLE: Mapping[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    # competition:canopy — shade (CANOPY_WIRING: "height_m /
    # crown_spread_m / shade_tolerance"): height clears the canopy step,
    # crown spreads it, and shade_tolerance attenuates the shade stress
    # (effective = shade × (1 − tolerance), B10 §6.4 — a shaded lineage
    # adapts toward tolerance; direction "+" only: more tolerance always
    # attenuates more).
    "competition:canopy": (
        ("height_m", ("+", "-")),
        ("crown_spread_m", ("+", "-")),
        ("shade_tolerance", ("+",)),
    ),
    # competition:ground_cover — the ground-plane contest
    # (GROUND_COVER_WIRING: "height_m / crown_spread_m / footprint";
    # footprint is the mass-hook π·max(clonal, crown)² geometry, so
    # clonal_spread_m is its second driver).
    "competition:ground_cover": (
        ("height_m", ("+", "-")),
        ("crown_spread_m", ("+", "-")),
        ("clonal_spread_m", ("+", "-")),
    ),
    # competition:substrate — the substrate contest (SUBSTRATE_WIRING:
    # "root_depth_m / substrate preference"; the preference axis is a
    # deferred B2 addendum — root_depth_m is the only probeable
    # responder today).
    "competition:substrate": (
        ("root_depth_m", ("+", "-")),
    ),
    # mechanical_support (MECHANICAL_WIRING: "crown_spread_m /
    # height_m / wood_density (trunk strength)").
    "mechanical_support": (
        ("crown_spread_m", ("+", "-")),
        ("height_m", ("+", "-")),
        ("wood_density", ("+", "-")),
    ),
    # energetics (ENERGETICS_WIRING: "root_depth_m / root_spread_m /
    # storage_organ"; the proportion knobs are locked per-plan
    # constants in mass.py today).
    "energetics": (
        ("root_depth_m", ("+", "-")),
        ("root_spread_m", ("+", "-")),
    ),
}

_COMPETITION_KEYS = frozenset((
    "competition:canopy", "competition:ground_cover",
    "competition:substrate",
))


@dataclass(frozen=True)
class TraitPressure:
    """One probed trait move against one stress term — full provenance
    (B10 §4): the stress term, the wired trait, the direction that
    relieves, the base stress, the probe geometry, and the pressure.

    ``direction`` is ``"+"`` (increasing the trait relieves), ``"-"``
    (decreasing relieves), or ``"none"`` (no relief either way).
    ``relief`` is the drop in the term along ``direction`` for a move
    of ``probe_step`` (≥ 0; EXACTLY 0.0 when the landscape is flat —
    strict zero, B10 §4).  ``marginal_relief`` is the per-unit local
    change (``relief / probe_step``).  ``pressure`` is
    ``stress × marginal_relief`` SIGNED toward relief: positive pulls
    toward larger trait values, negative toward smaller, 0.0 exactly
    when relief is zero (no leakage) or the base stress is zero (low
    stress → no pull)."""

    stress_key: str          # the term probed ("competition:canopy", ...)
    trait: str               # the committed trait axis ("height_m", ...)
    direction: str           # "+" | "-" | "none"
    stress: float            # the term's base value (what the channel reads)
    base_value: float        # the committed trait value probed
    probe_step: float        # PROBE_REL_STEP · |base_value|
    relief: float            # the term's drop along `direction` (≥ 0)
    marginal_relief: float   # relief / probe_step (per-unit local change)
    pressure: float          # stress · marginal_relief, signed toward relief
    cause: str               # the human WHY


# ══════════════════════════════════════════════════════════════════════
# ──  the probe (B10 §4 — nudge, reassemble, recompute)  ─────────────────
# ══════════════════════════════════════════════════════════════════════


def _term_value(view: Mapping, state: OccupancyState, stress_key: str) -> float:
    """The stress term's scalar value for *view* in *state* — the SAME
    value the dynamics channel reads: the competition block from
    crowding.competition_stress, the intrinsic block from the view's
    own ``intrinsic_stress`` (B10 §2's one channel)."""
    if stress_key in _COMPETITION_KEYS:
        return competition_stress(view, state)[stress_key]["value"]
    return float((view.get("intrinsic_stress") or {})
                 .get(stress_key, {}).get("value", 0.0))


def _probe_state(state: OccupancyState, ref: str, view: Mapping
                 ) -> OccupancyState:
    """A deep copy of *state* with the probed lineage's view swapped for
    *view*.  The lineage keeps its identity — substrate preference and
    demand — so crowding's ``_lineage_for_view`` resolves *view* to the
    lineage's OWN substrate distribution (identity match), and the
    probed lineage's own stratum / covered fraction respond to the
    nudge (the honest ripple: height changes shade AND mass AND the
    profile's own stratum in one recompute).  Pure — *state* is never
    mutated."""
    st = copy.deepcopy(state)
    st.lineages = tuple(
        Lineage(ref=ln.ref, view=view if ln.ref == ref else ln.view,
                substrate_pref=ln.substrate_pref, demand_t=ln.demand_t)
        for ln in state.lineages)
    return st


def _relief(record: SpeciesRecord, pack: ContentPack, state: OccupancyState,
            ref: str, stress_key: str, base_stress: float, trait: str,
            nudged_value: float) -> float:
    """The drop in the term when *trait* moves to *nudged_value*:
    base_stress − recomputed(nudged view, probe state).  The nudged
    value is clamped at 0.0 (a trait cannot go negative — the
    feasibility guard; at the 0 clamp the move is a no-op, relief 0)."""
    axes = dict(record.axes)
    axes[trait] = max(0.0, nudged_value)
    nudged_view = assemble_view(replace(record, axes=axes), pack)
    nudged = _term_value(nudged_view,
                         _probe_state(state, ref, nudged_view), stress_key)
    return base_stress - nudged


def probe_trait(record: SpeciesRecord, pack: ContentPack,
                state: OccupancyState, ref: str, stress_key: str,
                trait: str,
                directions: tuple[str, ...] = ("+", "-")) -> TraitPressure:
    """Probe ONE wired trait of *record* against the stress term
    *stress_key* in *state* (the cell the lineage *ref* occupies):
    nudge the committed axis ± one probe step, reassemble the view (the
    only derive path), recompute the term, read the relief.  Returns
    the TraitPressure — signed toward relief, strict zero when the
    landscape gives none (B10 §4).  *directions* limits which moves are
    considered (the table's allowed directions); relief from a
    disallowed side counts as zero.  Raises ValueError for a trait the
    record does not commit (there is nothing to probe)."""
    if trait not in record.axes \
            or not isinstance(record.axes[trait], (int, float)):
        raise ValueError(
            f"{record.sid!r} does not commit {trait!r} numerically — "
            f"nothing to probe")
    base_view = assemble_view(record, pack)
    stress = _term_value(base_view, state, stress_key)
    value = float(record.axes[trait])
    step = PROBE_REL_STEP * abs(value)

    if step == 0.0:
        # a trait committed at 0.0 moves nothing within a relative
        # step — no relief, no pull (the honest read)
        direction, relief = "none", 0.0
    else:
        plus = _relief(record, pack, state, ref, stress_key, stress,
                       trait, value + step) if "+" in directions else 0.0
        minus = _relief(record, pack, state, ref, stress_key, stress,
                        trait, value - step) if "-" in directions else 0.0
        if plus > 0.0 and plus >= minus:
            direction, relief = "+", plus
        elif minus > 0.0:
            direction, relief = "-", minus
        else:
            direction, relief = "none", 0.0

    marginal = relief / step if step > 0.0 else 0.0
    sign = 1.0 if direction == "+" else (-1.0 if direction == "-" else 0.0)
    pressure = sign * stress * marginal
    cause = _cause(stress_key, trait, direction, value, step, relief,
                   marginal, pressure, stress)
    return TraitPressure(
        stress_key=stress_key, trait=trait, direction=direction,
        stress=stress, base_value=value, probe_step=step, relief=relief,
        marginal_relief=marginal, pressure=pressure, cause=cause)


def _cause(stress_key: str, trait: str, direction: str, value: float,
           step: float, relief: float, marginal: float, pressure: float,
           stress: float) -> str:
    """The human WHY for one probe — the provenance text."""
    if direction == "none":
        if stress == 0.0:
            return (f"{stress_key} reads 0.0 at the base (no stress) — "
                    f"low stress → no pull (B10 §4)")
        return (f"{stress_key} reads {stress:.4g}; {trait} {value:.4g} "
                f"±{step:.4g} moves it by nothing (no marginal relief) — "
                f"zero pull (B10 §4 strict zero)")
    toward = "larger" if direction == "+" else "smaller"
    nudged = value + (step if direction == "+" else -step)
    return (f"{stress_key} reads {stress:.4g}; {direction}{step:.4g} "
            f"{trait} ({value:.4g} → {nudged:.4g}) "
            f"relieves {relief:.4g} (marginal {marginal:.4g}/unit) — "
            f"pressure {pressure:.4g} toward {toward} {trait}")


def pressure_probe(record: SpeciesRecord, pack: ContentPack,
                   state: OccupancyState, ref: str
                   ) -> dict[str, tuple[TraitPressure, ...]]:
    """The B10 §4 pressure block for the lineage *ref* committed at
    *record* in *state*: every machine-wired stress type (WIRING_TABLE,
    keys sorted — determinism), each with its wired traits probed in
    table order.  A wired trait the record does not commit is OMITTED
    (the trait is not expressed — nothing to probe).  Pure: the record,
    the state, and the pack are never mutated; two identical probes are
    byte-stable."""
    out: dict[str, tuple[TraitPressure, ...]] = {}
    for key in sorted(WIRING_TABLE):
        entries: list[TraitPressure] = []
        for trait, directions in WIRING_TABLE[key]:
            if trait not in record.axes \
                    or not isinstance(record.axes[trait], (int, float)):
                continue
            entries.append(probe_trait(record, pack, state, ref, key,
                                       trait, directions))
        out[key] = tuple(entries)
    return out
