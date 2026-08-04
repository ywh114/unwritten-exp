"""The per-cell balance sheet — who holds what share and why, for any
cell (ticket 0047; spec B10 §1, §2, §5, §6).

The L2 debug hook (plan §5): for one cell, the full L2 accounting —
the cell header (productivity on the B2 scale, cell_ha, the pool with
usage + remainder, the substrate mix); per structural layer the
geometric coverage budget (m²), usage and remainder; and per lineage:
biomass held, share of the pool, its layer and its share of that
layer's coverage, substrate match + substrate-weighted demand, its
three competition-stress readings with their causes, and a WHY line
naming which budget binds (or would bind first), which crowding field
is highest, and which stress type dominates.

The sheet READS ONLY occupancy (``exp.k15_biosphere.occupancy``) +
crowding (``exp.k15_biosphere.crowding``) + the assembled species
views — it computes nothing itself: every number is one of the model's
own reads (``pool_remainder_t``, ``layer_remainder_m2``,
``substrate_capacity_t``, ``competition_stress``, ...) or plain
arithmetic over them (shares, headrooms, fractions).  No persisted
world exists yet, so the CLI runs built-in demo fixtures assembled
from REAL content presets (the house fixture style: content loader +
the canonical view assembler); real cells come from the L6 artifact
later.

Runnable against the built-in demo fixtures:

    PYTHONPATH=. uv run python -m exp.k15_biosphere.balance ab_rich

Determinism hard rule: iteration over lineages / layers / substrate
classes / stress terms is sorted; no randomness, no wall-clock; two
identical runs are byte-identical.
"""

from __future__ import annotations

import math
import sys
from functools import partial
from pathlib import Path

from exp.k15_biosphere.content import ContentPack, load_content, merged_preset
from exp.k15_biosphere.crowding import (competition_stress,
                                        substrate_capacity_t,
                                        substrate_field)
from exp.k15_biosphere.flora.view import assemble_view
from exp.k15_biosphere.occupancy import CellInput, Lineage, OccupancyState
from exp.k15_biosphere.record import SpeciesRecord

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied, never imported).
CONTENT_DIR = Path(__file__).parent.parent / "k13_treegen" / "content" / "flora"

# The pack loads lazily: only the demo fixture builders need it, and
# module import (test collection) stays cheap.
_PACK: ContentPack | None = None


def _pack() -> ContentPack:
    global _PACK
    if _PACK is None:
        _PACK = load_content(CONTENT_DIR)
    return _PACK


# ══════════════════════════════════════════════════════════════════════
# ──  number formatting (describe.py's house style)  ──────────────────────
# ══════════════════════════════════════════════════════════════════════


def _fmt(value) -> str:
    """Sheet number formatting: integral magnitudes under 10⁶ print
    plainly (cell 1600 ha, holdings 400000 t); everything else three
    significant digits (describe.py's house format)."""
    v = float(value)
    if abs(v - round(v)) < 1e-9 and abs(v) < 1e6:
        return f"{round(v):d}"
    return f"{v:.3g}"


def _pct(value: float) -> str:
    """A fraction as a percent string, one decimal."""
    return f"{value * 100:.1f}%"


# ══════════════════════════════════════════════════════════════════════
# ──  the WHY line  ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════


def _binding_budget(state: OccupancyState, ref: str) -> str:
    """Which budget binds now — the pool, the lineage's layer coverage,
    or its matching-substrate capacity — or, when nothing binds yet,
    which WOULD bind first as the lineage grows alone.

    Headroom is "how many more tonnes this lineage can add before the
    budget is reached", in one unit (t): pool_remainder_t for the pool;
    layer_remainder_m2 converted through the lineage's own reference
    area × percap for its layer's coverage (∞ when the lineage claims
    no space — no mass/area model); substrate_capacity_t − holdings
    for the substrate (∞ for a lineage with no usable substrate and
    nothing held).  Reads only occupancy reads + ``substrate_capacity_t``;
    everything else is arithmetic over them."""
    layer = state.layer_of(ref)
    pool_h = state.pool_remainder_t
    ref_area = state.reference_area_m2(ref)
    percap_kg = state.percap_kg(ref)
    if ref_area > 0.0 and percap_kg > 0.0:
        cov_h = (state.layer_remainder_m2(layer) / ref_area
                 * (percap_kg / 1000.0))
    else:
        cov_h = math.inf
    cap = substrate_capacity_t(state, ref)
    holding = state.holdings_t[ref]
    sub_h = math.inf if cap <= 0.0 and holding <= 0.0 else cap - holding
    budgets = (("pool", pool_h),
               (f"{layer} coverage", cov_h),
               ("substrate capacity", sub_h))
    over = sorted(n for n, h in budgets if h < 0.0)
    if over:
        return f"{' and '.join(over)} over budget — binds now"
    at = sorted(n for n, h in budgets if h == 0.0)
    if at:
        return f"{' and '.join(at)} at budget — binds now"
    finite = [(n, h) for n, h in budgets if math.isfinite(h)]
    if not finite:
        return "no budget in reach (no mass/space model)"
    name, h = min(finite, key=lambda nh: (nh[1], nh[0]))
    return f"{name} would bind first ({_fmt(h)} t of headroom)"


def _resource(key: str) -> str:
    """The shared resource behind a competition-stress key:
    'competition:canopy' -> 'canopy'."""
    return key.split(":", 1)[1]


def _reading(key: str, term: dict) -> str:
    """The raw field reading behind a dominant stress term — what the
    lineage actually sees of the resource: the shade fraction for the
    canopy, the total share for the ground plane, the contested
    pressure Q for the substrate (the term's own ``field`` read)."""
    field = term["field"]
    if key == "competition:canopy":
        return f"shade {_fmt(field['above_fraction'])}"
    if key == "competition:ground_cover":
        return f"share {_fmt(field['total_share'])}"
    return f"Q={_fmt(field['total_pressure'])}"


def _why(state: OccupancyState, ref: str, terms: dict) -> str:
    """The WHY line: which budget binds (now or first) + which crowding
    field is highest + which stress type dominates — the highest
    competition-stress value (ties name every resource, sorted)."""
    budget = _binding_budget(state, ref)
    max_value = max(t["value"] for t in terms.values())
    dominant = sorted(k for k, t in terms.items()
                      if t["value"] == max_value)
    highest = ", ".join(
        f"{_resource(k)} ({_reading(k, terms[k])})" for k in dominant)
    dom = ", ".join(f"{k} {_fmt(max_value)}" for k in dominant)
    return (f"{budget}; highest crowding field: {highest}; "
            f"dominant stress: {dom}")


# ══════════════════════════════════════════════════════════════════════
# ──  the sheet  ──────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════


def balance_sheet(state: OccupancyState, name: str | None = None) -> str:
    """The full L2 balance sheet for one cell (reads only — see the
    module docstring).

    Sections: the cell header (productivity on the B2 scale, cell_ha,
    pool with usage + remainder, substrate mix); per structural layer
    (geometric coverage budget m², usage, remainder); per lineage
    (biomass held, share of the pool, its layer + share of that
    layer's coverage, substrate match + substrate-weighted demand,
    its three competition-stress readings with causes, and the WHY
    line)."""
    lines = [f"cell {name!r}" if name is not None else "cell"]
    lines.append(f"  productivity  {_fmt(state.cell.productivity)} (B2 scale)  "
                 f"cell {_fmt(state.cell.cell_ha)} ha  "
                 f"area {_fmt(state.cell_area_m2)} m²")
    lines.append(f"  pool          {_fmt(state.pool_t)} t  "
                 f"used {_fmt(state.pool_used_t)} t  "
                 f"remainder {_fmt(state.pool_remainder_t)} t")
    mix = ", ".join(f"{s}={_fmt(state.cell.substrate_mix[s])}"
                    for s in sorted(state.cell.substrate_mix))
    lines.append(f"  substrate     {mix}")
    lines.append("  layers")
    for layer in sorted({state.layer_of(r) for r in state.holdings_t}):
        lines.append(f"    {layer:<10} budget {_fmt(state.cell_area_m2)} m²  "
                     f"used {_fmt(state.layer_used_m2(layer))} m²  "
                     f"remainder {_fmt(state.layer_remainder_m2(layer))} m²  "
                     f"coverage {_fmt(state.coverage(layer))}")
    lines.append("  lineages")
    pressures = dict(substrate_field(state).pressures)
    for ln in state.lineages:                    # already sorted by ref
        ref = ln.ref
        layer = state.layer_of(ref)
        holding = state.holdings_t[ref]
        own_cover = (state.individuals(ref) * state.reference_area_m2(ref)
                     / state.cell_area_m2)
        layer_total = state.coverage(layer)
        layer_share = own_cover / layer_total if layer_total > 0.0 else 0.0
        lines.append(f"    {ref}")
        lines.append(f"      holdings    {_fmt(holding)} t  "
                     f"({_fmt(holding / state.pool_t)} of pool)")
        lines.append(f"      layer       {layer}  cover {_fmt(own_cover)}  "
                     f"({_pct(layer_share)} of {layer}'s "
                     f"{_fmt(layer_total)})")
        lines.append(f"      substrate   match {_fmt(state.substrate_match(ref))}  "
                     f"weighted demand "
                     f"{_fmt(state.substrate_weighted_demand_t(ref))} t  "
                     f"capacity {_fmt(substrate_capacity_t(state, ref))} t  "
                     f"pressure {_fmt(pressures[ref])}")
        terms = competition_stress(ln.view, state)
        lines.append("      crowding")
        for key in sorted(terms):
            term = terms[key]
            lines.append(f"        {key:<23} {_fmt(term['value'])}  —  "
                         f"{term['cause']}")
        lines.append(f"      why         {_why(state, ref, terms)}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
# ──  the built-in demo fixtures (no persisted world yet — L6 later)  ─────
# ══════════════════════════════════════════════════════════════════════


def _lineage(preset_id: str, ref: str, substrate_pref=None,
             demand_t: float = 0.0) -> Lineage:
    """A real-preset lineage: the committed record assembled to its
    canonical view (the only derive path), wrapped in a Lineage."""
    t = _pack().presets[preset_id]
    axes, generics = merged_preset(t)
    rec = SpeciesRecord(sid="0" * 16, plan=t["preset"]["plan"],
                        preset=preset_id, axes=axes, generics=generics)
    return Lineage(ref=ref, view=assemble_view(rec, _pack()),
                   substrate_pref=substrate_pref or {}, demand_t=demand_t)


def _oak(**kw) -> Lineage:
    """tree.oak: 25 m canopy, 12 m crown — the A/B canopy actor."""
    return _lineage("tree.oak", "oak", **kw)


def _willow(**kw) -> Lineage:
    """tree.willow: 15 m canopy — a second, lower canopy stratum."""
    return _lineage("tree.willow", "willow", **kw)


def _tussock(**kw) -> Lineage:
    """grass_sward.tussock: sward layer, footprint-driven ground cover."""
    return _lineage("grass_sward.tussock", "sward", **kw)


def _sphagnum(**kw) -> Lineage:
    """moss_grade.sphagnum: ground layer, kg_m2 (per-area) cover."""
    return _lineage("moss_grade.sphagnum", "moss", **kw)


def _demo_ab(productivity: float) -> OccupancyState:
    """The A/B acceptance cell (B10 §6.1): an oak canopy with a sward
    understory at *productivity* — the same oak biomass on both sides,
    only the pool remainder differs (rich understory vs barren
    forest), emergent from the remainder + stage order."""
    st = OccupancyState(CellInput(productivity=productivity, cell_ha=1600.0,
                                  substrate_mix={"peat": 1.0}),
                        [_oak(demand_t=400_000.0),
                         _tussock(substrate_pref={"peat": 1.0},
                                  demand_t=100.0)])
    st.paint("oak", 400_000.0)                  # stage 1: the canopy
    st.paint("sward", 100.0)                    # stage 2: the understory
    return st


def _demo_strata() -> OccupancyState:
    """The multi-stratum cell: oak canopy + willow subcanopy + moss mat
    on a half-peat substrate — two canopy strata (the shade step), a
    ground layer, and a partial substrate match (moss caps at half)."""
    st = OccupancyState(CellInput(productivity=2.5, cell_ha=1600.0,
                                  substrate_mix={"peat": 0.5, "sand": 0.5}),
                        [_oak(demand_t=350_000.0),
                         _willow(substrate_pref={"peat": 0.6, "sand": 0.4},
                                 demand_t=80_000.0),
                         _sphagnum(substrate_pref={"peat": 1.0},
                                   demand_t=2_000.0)])
    st.paint("oak", 350_000.0)
    st.paint("willow", 80_000.0)
    st.paint("moss", 2_000.0)
    return st


# fixture name -> fresh-cell builder (each call rebuilds: deterministic,
# never shared mutable state)
DEMO = {
    "ab_rich": partial(_demo_ab, 2.5),   # A: pool 1.6 Mt, canopy leaves 1.2 Mt
    "ab_poor": partial(_demo_ab, 0.75),  # B: pool 480 kt, canopy leaves 80 kt
    "strata": _demo_strata,
}


# ══════════════════════════════════════════════════════════════════════
# ──  the CLI hook (describe.py's house pattern)  ─────────────────────────
# ══════════════════════════════════════════════════════════════════════


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m exp.k15_biosphere.balance <fixture>",
              file=sys.stderr)
        print("fixtures: " + ", ".join(sorted(DEMO)), file=sys.stderr)
        return 2
    name = args[0]
    builder = DEMO.get(name)
    if builder is None:
        print(f"no fixture {name!r} in the demo set "
              f"({', '.join(sorted(DEMO))})", file=sys.stderr)
        return 2
    print(balance_sheet(builder(), name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
