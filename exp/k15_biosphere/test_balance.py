"""Fast-tier tests for the per-cell balance-sheet debug hook (ticket
0047; spec B10 §1, §2, §5, §6).

The sheet READS ONLY occupancy + crowding + the assembled views, so
these tests assert the SHEET's shape, not the underlying numbers (the
occupancy/crowding tests own those): every section prints; each
per-lineage WHY line names a binding budget (pool / layer coverage /
substrate capacity) and a dominant stress; the budget-variant stories
hold across the demo cells (the ab_poor oak holds PAST its derived
cap — substrate binds now; a lone moss mat is SPACE-limited — its
ground coverage would bind first); the A/B demo fixture shows the B10
§6.1 acceptance shape (the same oak biomass on both sides, a very
different pool remainder); the CLI handles fixtures and usage; and
runs are byte-identical (determinism hard rule), with the house
determinism audit.  Plain pytest, no marks — runs in milliseconds.
"""

from __future__ import annotations

import io
import pathlib
import re
from contextlib import redirect_stdout

import pytest

from exp.k15_biosphere.balance import DEMO, balance_sheet, main
from exp.k15_biosphere.content import load_content, merged_preset
from exp.k15_biosphere.flora.view import assemble_view
from exp.k15_biosphere.occupancy import CellInput, Lineage, OccupancyState
from exp.k15_biosphere.record import SpeciesRecord

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = pathlib.Path(__file__).parent.parent / "k13_treegen" \
    / "content" / "flora"

# Loaded once at module scope: the fixtures below are fast and share it.
_PACK = load_content(CONTENT_DIR)


# ──  fixture builders (test_occupancy's house style)  ────────────────────


def _lineage(preset_id: str, ref: str, substrate_pref=None,
             demand_t: float = 0.0) -> Lineage:
    """A real-preset lineage: the committed record assembled to its
    canonical view (the only derive path), wrapped in a Lineage."""
    t = _PACK.presets[preset_id]
    axes, generics = merged_preset(t)
    rec = SpeciesRecord(sid="0" * 16, plan=t["preset"]["plan"],
                        preset=preset_id, axes=axes, generics=generics)
    return Lineage(ref=ref, view=assemble_view(rec, _PACK),
                   substrate_pref=substrate_pref or {}, demand_t=demand_t)


def _oak(**kw) -> Lineage:
    """tree.oak: 25 m canopy, 12 m crown — the A/B canopy actor."""
    return _lineage("tree.oak", "oak", **kw)


def _sphagnum(**kw) -> Lineage:
    """moss_grade.sphagnum: ground layer, kg_m2 (per-area) cover."""
    return _lineage("moss_grade.sphagnum", "moss", **kw)


def _cell(productivity: float = 1.0, cell_ha: float = 1600.0,
          mix: dict | None = None) -> CellInput:
    """A 256²-resolution cell (1600 ha) at the default productivity,
    full-peat substrate unless the caller provides a mix."""
    return CellInput(productivity=productivity, cell_ha=cell_ha,
                     substrate_mix=mix or {"peat": 1.0})


# ──  sheet-shape helpers  ────────────────────────────────────────────────


def _lineage_line(sheet: str, ref: str, prefix: str) -> str:
    """The first line starting with *prefix* inside *ref*'s block of a
    sheet (the per-lineage items are indented under the ref heading).
    Runs of whitespace collapse to single spaces so assertions never
    depend on the sheet's column alignment."""
    lines = sheet.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == ref:
            for nxt in lines[i + 1:]:
                if nxt.strip().startswith(prefix):
                    return re.sub(r"\s+", " ", nxt.strip())
    raise AssertionError(f"no {prefix!r} line for {ref!r} in:\n{sheet}")


def _flat(sheet: str) -> str:
    """The sheet with runs of spaces collapsed to one (alignment-blind
    substring assertions) — line breaks are preserved."""
    return re.sub(r"[ \t]+", " ", sheet)


def _why_line(sheet: str, ref: str) -> str:
    return _lineage_line(sheet, ref, "why")


# ──  the sheet prints every section  ─────────────────────────────────────


def test_sheet_prints_all_sections():
    """The full sheet renders: cell header (B2 productivity, cell_ha,
    pool with usage + remainder, substrate mix), per-layer coverage
    budgets, and per-lineage blocks with every required item."""
    sheet = _flat(balance_sheet(DEMO["ab_rich"](), name="ab_rich"))
    assert "ab_rich" in sheet
    # cell header
    assert "productivity" in sheet and "2.5" in sheet
    assert "cell 1600 ha" in sheet and "area 1.6e+07 m²" in sheet
    assert "pool" in sheet and "used" in sheet and "remainder" in sheet
    assert "peat=1" in sheet
    # per-layer coverage budgets
    assert "layers" in sheet and "canopy" in sheet and "sward" in sheet
    assert "budget 1.6e+07 m²" in sheet and "coverage" in sheet
    # per-lineage blocks
    assert "lineages" in sheet and "oak" in sheet and "sward" in sheet
    for item in ("holdings", "of pool", "layer", "cover",
                 "match", "weighted demand", "capacity", "pressure",
                 "crowding", "competition:canopy",
                 "competition:ground_cover", "competition:substrate",
                 "why"):
        assert item in sheet, f"missing {item!r} in:\n{sheet}"


# ──  the WHY lines name a binding budget and a dominant stress  ──────────


def test_why_lines_name_binding_budget_and_dominant_stress():
    """Every per-lineage WHY line names a binding budget (pool / layer
    coverage / substrate capacity — over budget or would-bind-first)
    and a dominant competition stress, with both phrasings present."""
    for name in ("ab_rich", "ab_poor", "strata"):
        sheet = balance_sheet(DEMO[name](), name=name)
        for ref in ("oak", "sward", "moss", "willow"):
            if ref not in sheet:
                continue
            why = _why_line(sheet, ref)
            assert "would bind first" in why or "binds now" in why, why
            assert re.search(r"\b(pool|coverage|capacity)\b", why), why
            assert "competition:" in why, why
            assert "highest crowding field" in why, why
            assert "dominant stress" in why, why


def test_why_budget_variants_across_demo_cells():
    """The binding-budget verdict tracks the model's own numbers: the
    ab_poor oak holds PAST its derived cap (substrate capacity over
    budget — binds now, B10 §5); the ab_rich oak sits just under it
    (substrate capacity would bind first); a lone moss mat is
    SPACE-limited (its ground coverage would bind first — coverage is
    geometric, productivity-blind)."""
    poor = _why_line(balance_sheet(DEMO["ab_poor"]()), "oak")
    assert "substrate capacity over budget — binds now" in poor
    rich = _why_line(balance_sheet(DEMO["ab_rich"]()), "oak")
    assert "substrate capacity would bind first" in rich
    # a lone moss mat on half its substrate: the ground plane is far
    # closer than the substrate capacity or the pool
    st = OccupancyState(_cell(mix={"peat": 0.5, "sand": 0.5}),
                        [_sphagnum(substrate_pref={"peat": 1.0},
                                   demand_t=1_000.0)])
    st.paint("moss", 1_000.0)
    moss = _why_line(balance_sheet(st, name="moss"), "moss")
    assert "coverage would bind first" in moss


# ──  the A/B demo fixture (B10 §6.1 acceptance shape)  ───────────────────


def test_ab_demo_same_oak_biomass_different_pool_remainders():
    """B10 §6.1 acceptance shape: cells A (rich) and B (poor) hold the
    SAME oak biomass (the lineage cap is nearly productivity-flat above
    unit); A's canopy leaves a large pool remainder for the understory,
    B's nearly exhausts the pool — emergent from the remainder + stage
    order, no understory penalty.  The exact t-values are the
    occupancy tests' business; here we read the SHEET's own numbers."""
    A = _flat(balance_sheet(DEMO["ab_rich"](), name="A"))
    B = _flat(balance_sheet(DEMO["ab_poor"](), name="B"))

    def oak_holdings_t(sheet: str) -> str:
        ln = _lineage_line(sheet, "oak", "holdings")
        return re.search(r"holdings (\S+) t", ln).group(1)

    # the same oak biomass on both sides (400 kt of 1.6 Mt / 480 kt)
    assert oak_holdings_t(A) == oak_holdings_t(B) == "400000"

    def pool_remainder_t(sheet: str) -> str:
        return re.search(r"remainder (\S+) t", sheet).group(1)

    rA, rB = pool_remainder_t(A), pool_remainder_t(B)
    assert rA == "1.2e+06" and rB == "79900"        # different remainders
    assert float(rA) > 10.0 * float(rB)            # rich vs barren
    # the sward's own plane is productivity-blind: its cover reads the
    # same on both sides — understory density is a POOL story, not a
    # coverage story
    for sheet in (A, B):
        assert "cover 0.00195 (100.0% of sward's 0.00195)" in sheet


# ──  the CLI hook  ───────────────────────────────────────────────────────


def test_main_usage_and_unknown_fixture(capsys):
    """No fixture -> usage on stderr, exit 2; an unknown fixture ->
    error, exit 2; a known fixture prints its sheet."""
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "ab_rich" in err and "strata" in err
    assert main(["no_such_fixture"]) == 2
    assert "no_such_fixture" in capsys.readouterr().err
    assert main(["ab_rich"]) == 0
    out = capsys.readouterr().out
    assert "ab_rich" in out and "why" in out and "competition:substrate" \
        in out


def test_demo_runs_are_byte_identical():
    """Determinism hard rule: two fresh builds of a demo fixture and
    two CLI runs print byte-identical sheets (no randomness, no
    wall-clock; iteration sorted)."""
    assert balance_sheet(DEMO["strata"]()) == balance_sheet(DEMO["strata"]())
    for name in DEMO:
        assert balance_sheet(DEMO[name]()) == balance_sheet(DEMO[name]()), \
            name

    out = io.StringIO()
    with redirect_stdout(out):
        assert main(["strata"]) == 0
    again = io.StringIO()
    with redirect_stdout(again):
        assert main(["strata"]) == 0
    assert out.getvalue() == again.getvalue()


# ──  determinism audit  ──────────────────────────────────────────────────


def test_no_nondeterministic_imports():
    """AGENTS.md determinism hard rule: no random/uuid/time/numpy in
    balance.py (same seed ⇒ byte-identical output)."""
    src = (pathlib.Path(__file__).parent / "balance.py").read_text()
    for line in src.splitlines():
        stripped = line.strip()
        for bad in ("import random", "from random", "import uuid",
                    "from uuid", "import time", "from time",
                    "import numpy"):
            assert not stripped.startswith(bad), \
                f"balance.py: forbidden import: {stripped}"
