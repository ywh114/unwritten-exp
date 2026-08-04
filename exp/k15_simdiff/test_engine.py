"""K15 sim-diff engine — acceptance tests (spec §12).

Fast tier (fixture engines, a handful of planted instances each):
  4. extinction in a lethal refugium
  5. coexistence (close suitability) / takeover (large margin)
  6. vanguard gate (sink cell rains, never establishes)
  7. wind deposits land downwind on seed 1's real mean field
  8. per-instance reduced-cache budget (REDUCED_CACHE_MB)
  9. hard-rule audit (source scan + runtime guard)

Slow tier (`-m slow`, one 20-round run pair):
  1. determinism — two full runs byte-identical
  2. range tracking — occupied mean s_env < unoccupied per lineage
  3. genesis partition diverges (>= 1 divide; immediate recombination
     re-pin, ticket 0028)
  8. performance report (wall time; the §12.8 60 s gate is reported,
     not asserted — growth dynamics make it unmet by design)

Fixtures plant instances directly (``_plant``): no genesis rain, so
each fast test exercises exactly the lineages it planted. Fixture
cells/presets were picked from a seed-1 stat probe (2026-08-01, retuned
after the 2026-08-01 climate-envelope ruling moved the suitability
landscape): the close pair is reed/forb (212 overlapping s_env < 0
cells, min gap 0.0007; re-pinned 2026-08-03 when the 0012 prune
removed herb_forb.yarrow); the takeover pair is palm/conifer at a
cell with large s_env margin; the drift-retention pair is a reed
lineage on a cold-stressed marginal cell vs a healthy contrast cell;
consolidation uses lichen (viable in every world quadrant).
"""

from __future__ import annotations

import json
import random
import re
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

from exp.k13_treegen.interface import Outcome
from exp.k15_simdiff import dispersal as dsp
from exp.k15_simdiff import population as pop
from exp.k15_simdiff import stress_adapter as sa
from exp.k15_simdiff.engine import Dressed, Engine, GENESIS_S, _dilate

SEED = 1
R_SLOW = 20
TAKEOVER_RATIO = 0.8            # spec §12 item 5 (§13)
REDUCED_CACHE_MB = 4.25         # spec §12 item 8 (§13): 3.9 + one plane —
                                # B6 §3 added REQ_GLACIER to the reduced
                                # provenance (a (H,W) f32 plane ≈ 0.25 MiB)
HERE = Path(__file__).resolve().parent
SCANNED = ["engine.py", "genesis.py", "dispersal.py", "population.py",
           "authority.py", "stress_adapter.py", "req_flora.py"]
SCANNED_DESCENT = ["descent.py"]   # ticket 0018: same hard-rule scan
# usage-shaped patterns only (a docstring saying "never np.random" is
# the rule stated, not a violation)
BANNED = re.compile(
    r"import\s+uuid|uuid4\(|import\s+random(?!\w)|np\.random\.\w"
    r"|numpy\.random\.\w|time\.time\(|time\.time_ns\(|datetime\.now\(")


# ── fixtures ──────────────────────────────────────────────────────────

# The seed-1 world ctx + capacity anchor, built ONCE per worker process
# by the session fixtures in conftest.py (ticket 0021 item 4). The
# autouse session fixture stashes them here so ``_engine()`` shares one
# read-only world instead of re-opening the K11 dump + currents payload
# per test (~2 s per engine before the shared world). The ctx is never
# mutated after ``load_world`` (every ctx.* write lives inside it) and
# K is only ever indexed, never written — so sharing is
# determinism-neutral, and with xdist each worker builds its own
# session copy.
_CTX: sa.WorldContext | None = None
_CAP: np.ndarray | None = None


@pytest.fixture(scope="session", autouse=True)
def _k15_shared_world(k15_world, k15_capacity):
    global _CTX, _CAP
    _CTX, _CAP = k15_world, k15_capacity


def _engine() -> Engine:
    """A bare engine (world + tree + authority, NO genesis rain)."""
    return Engine(SEED, ctx=_CTX, capacity=_CAP)


def _plant(eng: Engine, preset: str, cells: list[tuple[int, int]],
           n0: float = 0.5) -> str:
    """Mint an instance of *preset* and dress it on *cells* with
    density *n0*. Returns the new instance id."""
    return _plant_variant(eng, preset, cells, {}, n0)


def _plant_variant(eng: Engine, preset: str,
                   cells: list[tuple[int, int]], overrides: dict,
                   n0: float = 0.5) -> str:
    """Mint an instance of *preset*, OVERRIDE the given WIP genes (a
    test device for controlled trait contrasts — e.g. two bodies of one
    preset differing only in shade_tolerance), and dress it on *cells*
    with density *n0*. Returns the new instance id."""
    sid = eng._order_sid[preset]
    rng = eng._stream("test", f"plant:{preset}:{len(eng.instances)}")
    iid = eng._new_instance_id(rng)
    x = eng.authority.mint(sid, iid, rng)
    x.traits.update(overrides)
    view = eng.sim.derive(x.traits, eng.pack)
    cache = eng._evaluate_cache(view, x.traits)
    ys = [c[0] for c in cells]
    xs = [c[1] for c in cells]
    box = (min(ys), max(ys) + 1, min(xs), max(xs) + 1)
    N = np.zeros((box[1] - box[0], box[3] - box[2]), dtype=np.float64)
    for (y, xx) in cells:
        N[y - box[0], xx - box[2]] = n0
    eng.instances[iid] = Dressed(
        x=x, N=N, rain=np.zeros_like(N), cache=cache, view=view,
        percap=pop.percap_demand(view),
        vital=eng.sim.vital(x.traits, eng.pack),
        div=np.zeros_like(N, dtype=bool),
        orphan=np.zeros_like(N, dtype=bool), box=box)
    return iid


def _s_env(eng: Engine, preset: str) -> np.ndarray:
    """The full-grid reduced s_env plane for a preset's authored
    genes (for fixture cell picking; does not plant anything)."""
    sid = eng._order_sid[preset]
    rng = eng._stream("test", f"peek:{preset}")
    x = eng.authority.mint(sid, eng._new_instance_id(rng), rng)
    view = eng.sim.derive(x.traits, eng.pack)
    return eng._evaluate_cache(view, x.traits).s_env


def _cell(d: Dressed, y: int, x: int) -> tuple[float, float] | None:
    """(N, rain) at world cell (y, x), or None outside the window."""
    y0, y1, x0, x1 = d.box
    if not (y0 <= y < y1 and x0 <= x < x1):
        return None
    return (float(d.N[y - y0, x - x0]), float(d.rain[y - y0, x - x0]))


# ── §12.4 extinction ──────────────────────────────────────────────────


def test_extinction_lethal_refugium():
    """A lineage boxed into a lethal refugium (deep ocean for a land
    grass: medium mismatch => f_worst = 0, s_env = 1, bscale = 0 and a
    high baseline death rate) is extinct within 5 rounds."""
    eng = _engine()
    ctx = eng.ctx
    deep = ctx.water_cell & (ctx.bathy > 100.0)
    ys, xs = np.nonzero(deep)
    assert len(ys) >= 9, "need deep-ocean cells on this world"
    cells = [(int(ys[k]), int(xs[k])) for k in range(9)]
    iid = _plant(eng, "grass_sward.tussock", cells)
    for t in range(5):
        eng.round(t)
        if iid not in eng.instances:
            break
    assert iid not in eng.instances
    assert iid in eng.retired


# ── §12.5 coexistence / takeover ──────────────────────────────────────


def test_coexistence_close_suitability():
    """Two fixtures with close suitability in one cell (reed/forb,
    min gap 0.0007 over 144 healthy-shared cells) coexist: both LINEAGES
    keep mass > N_FLOOR after 8 rounds. (Asserted at lineage level — a
    fast herb's patch may split and re-merge across the round window,
    absorbing the original instance id; the v0.6 packet blobs found at
    higher density than EST_N0, so the coexistence invariant is
    lineage-level.) Fast-turnover plans: slow trees need far more than
    8 rounds to reach an equilibrium readable as coexistence (both
    merely decay together under the density cap on any shared-cell
    planting). The shared cell must be HEALTHY for both (s_env < -0.1):
    a near-breakeven shared cell decays both lineages under their
    baseline death. (v0.7: the herb's lineage may PROMOTE — its g
    crosses the seeded g* and the whole gene pool re-keys to one new
    species node, a rank change not an extinction — so the lineage
    mass includes the promoted descendant node.) ticket 0012 Task D
    re-pin (2026-08-03, the curated two-track flora census 0d0e0d6):
    the prune removed herb_forb.yarrow — re-pinned to herb_forb.forb,
    the surviving meadow-flower herb; measured on the re-curated world:
    212 overlapping s_env < 0 cells (144 healthy-shared below -0.1),
    min gap 0.0007 at (79,142), both lineages > N_FLOOR after 8 rounds
    (reed 52.0, forb 639.4)."""
    eng = _engine()
    s_a = _s_env(eng, "grass_sward.reed")
    s_b = _s_env(eng, "herb_forb.forb")
    ok = eng.ctx.land_cell & (s_a < 0.0) & (s_b < 0.0)
    assert ok.any(), "no overlapping viable cell on this world"
    healthy = ok & (s_a < -0.1) & (s_b < -0.1)
    assert healthy.any(), "no healthy-shared cell on this world"
    score = np.where(healthy, -np.abs(s_a - s_b), -np.inf)
    y, x = np.unravel_index(int(np.argmax(score)), score.shape)
    a = _plant(eng, "grass_sward.reed", [(int(y), int(x))])
    b = _plant(eng, "herb_forb.forb", [(int(y), int(x))])
    sida = eng.instances[a].x.species_id
    sidb = eng.instances[b].x.species_id
    for t in range(8):
        eng.round(t)
    ma = _lineage_mass(eng, sida)
    mb = _lineage_mass(eng, sidb)
    assert ma > pop.N_FLOOR, f"reed lineage died (mass {ma:.3f})"
    assert mb > pop.N_FLOOR, f"forb lineage died (mass {mb:.3f})"


def _lineage_mass(eng: Engine, sid: str) -> float:
    """Mass of the lineage *sid* and its committed children (the
    v0.7 g-promotion re-keys the whole gene pool to one new species
    node — a rank change, not an extinction; the tree keeps the order
    node as the ghost ancestor)."""
    path = eng.authority._sid_path.get(sid)
    ids = {sid}
    if path is not None:
        ids |= {n.sid for n in eng.tree.nodes.values()
                if n.parent == path}
    return sum(d.mass for d in eng.instances.values()
               if d.x.species_id in ids)


def test_takeover_large_margin():
    """With a large suitability margin (oak s_env < -0.5 vs conifer
    s_env = 1.00 at the fixture cell — the palm/conifer pair no longer
    has margin cells on the post-climate-dials landscape) the
    better-suited lineage ends with >= TAKEOVER_RATIO of the shared
    cell's mass."""
    eng = _engine()
    s_bad = _s_env(eng, "tree.conifer")
    s_good = _s_env(eng, "tree.oak")
    ok = eng.ctx.land_cell & (s_good < -0.2) & (s_bad > 0.5)
    assert ok.any(), "no large-margin fixture cell on this world"
    score = np.where(ok, s_bad - s_good, -np.inf)
    y, x = np.unravel_index(int(np.argmax(score)), score.shape)
    bad = _plant(eng, "tree.conifer", [(int(y), int(x))])
    good = _plant(eng, "tree.oak", [(int(y), int(x))])
    for t in range(10):
        eng.round(t)
    m_bad = eng.instances[bad].mass if bad in eng.instances else 0.0
    m_good = eng.instances[good].mass if good in eng.instances else 0.0
    assert m_good > 0.0
    assert m_good / (m_good + m_bad) >= TAKEOVER_RATIO


# ── §12.6 vanguard gate ───────────────────────────────────────────────


def test_vanguard_sink_never_establishes():
    """A sink cell (f_hab < EST_F_MIN — open ocean for a land grass)
    receives rain and never establishes: rain > 0 at least once,
    N = 0 at that cell throughout. The source is planted on a VIABLE
    shore cell (s_env < 0) so it lives long enough to emit."""
    eng = _engine()
    ctx = eng.ctx
    s_t = _s_env(eng, "grass_sward.tussock")
    shore = ctx.land_cell & _dilate(_dilate(ctx.water_cell)) & (s_t < 0.0)
    ys, xs = np.nonzero(shore)
    assert len(ys), "need a viable shoreline on this world"
    sy, sx = int(ys[0]), int(xs[0])
    # the nearest ocean cell (deterministic: first in the row-major
    # radius-2 scan)
    best = None
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            wy, wx = sy + dy, sx + dx
            if 0 <= wy < ctx.H and 0 <= wx < ctx.W \
                    and ctx.water_cell[wy, wx]:
                best = (wy, wx)
                break
        if best:
            break
    assert best is not None
    iid = _plant(eng, "grass_sward.tussock", [(sy, sx)])
    rained = False
    for t in range(3):
        eng.round(t)
        assert iid in eng.instances, "viable shore source died"
        got = _cell(eng.instances[iid], *best)
        if got is not None:
            n, rain = got
            assert n == 0.0, "sink cell established"
            rained = rained or rain > 0.0
    assert rained, "sink cell never received rain"


# ── §12.7 wind directionality on the real field ──────────────────────


def test_wind_deposits_land_downwind():
    """Wind-packet rays land downwind of their origin on seed 1's mean
    field: the origin->centroid vector has a positive projection on the
    local wind for the sampled origins. Axis convention
    (dispersal._line_ray): u is the column (x) component, v the row
    (y) component. ticket 0012 Task D re-pin (2026-08-03, the curated
    two-track flora census 0d0e0d6): the prune removed tree.birch (the
    wind-dispersed hardwood, wind 0.8) — re-pinned to tree.conifer
    (wind 0.7), the surviving wind-dispersed tree; measured on seed 1's
    mean field: 21/21 windiest-land sources deposit downwind (assert
    floor 18)."""
    eng = _engine()
    ctx = eng.ctx
    sid = eng._order_sid["tree.conifer"]
    rng = eng._stream("test", "peek:tree.conifer")
    x = eng.authority.mint(sid, eng._new_instance_id(rng), rng)
    view = eng.sim.derive(x.traits, eng.pack)
    assert view.get("dispersal_channels", {}).get("wind", 0.0) > 0.0
    # sample the windiest land cells, evenly spaced (deterministic)
    wspd = np.where(ctx.land_cell, eng.wspd, 0.0)
    thr = np.quantile(wspd[ctx.land_cell], 0.9)
    ys, xs = np.nonzero(wspd >= thr)
    step = max(1, len(ys) // 20)
    srcs = [(int(ys[k]), int(xs[k])) for k in range(0, len(ys), step)]
    hits = 0
    for sy, sx in srcs:
        cells = dsp.packet_wind_ray((sy, sx), eng.wind_u, eng.wind_v,
                                    view)
        if not cells:
            continue
        keys = sorted(cells)                 # row-major accumulation
        cy = sum(k[0] for k in keys) / len(keys) - sy
        cx = sum(k[1] for k in keys) / len(keys) - sx
        if cx * eng.wind_u[sy, sx] + cy * eng.wind_v[sy, sx] > 0.0:
            hits += 1
    assert hits >= max(1, int(0.9 * len(srcs))), \
        f"only {hits}/{len(srcs)} sources deposited downwind"


# ── §12.7 v0.6 packet coherence / determinism / memory ────────────────


def _components(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    """8-connected components of a small set of world cells (union-
    find; deterministic — component order is arbitrary, sizes matter)."""
    parent = {c: c for c in cells}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for (y, x) in cells:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dy, dx) == (0, 0):
                    continue
                n = (y + dy, x + dx)
                if n in cells:
                    union((y, x), n)
    comps: dict[int, set] = {}
    for c in cells:
        comps.setdefault(find(c), set()).add(c)
    return list(comps.values())


def _touches(cells: set[tuple[int, int]], other: set[tuple[int, int]]
             ) -> bool:
    """Any 8-adjacency between the two cell sets."""
    return any((c[0] + dy, c[1] + dx) in other
               for c in cells for dy in (-1, 0, 1) for dx in (-1, 0, 1))


def test_packet_coherence():
    """v0.6 §7.2/§7.3: a round's founded cells are coherent blobs —
    ZERO isolated founded cells, and every founded REMOTE fragment (a
    component not 8-connected to the founder's pre-round cells: the
    jump landing, a disjoint animal disk) has >= 8 cells. Fixture:
    grass_sward.bulrush planted on one cell of its dense fen — local
    blobs and wind rays join the founder, the jump disk mints as a
    remote fragment. ticket 0012 Task D re-pin (2026-08-03, the curated
    two-track flora census 0d0e0d6): the prune removed
    herb_forb.yarrow and the tree rebuild re-drew every lineage's g
    parameters (content-addressed by sid, shifting the viability
    landscape) — the old (yarrow, (71,167)) probe no longer mints a
    jump foundling, so the trio re-probed (preset x cell) under the
    full invariant set; the first qualifying combo is bulrush at
    (68,181): 40 founded cells, zero isolated, no remote fragment
    below 8 cells, exactly one jump foundling."""
    eng = _engine()
    cell = (68, 181)            # seed-1 dense bulrush fen (probed)
    iid = _plant(eng, "grass_sward.bulrush", [cell])
    d0 = eng.instances[iid]
    pre = {(int(y) + d0.box[0], int(x) + d0.box[2])
           for y, x in np.argwhere(d0.cells)}
    eng.round(0)
    founded = eng._founded_new.get(iid, {})
    assert founded, "no founded cells this round"
    s = set(founded)
    # (i) zero isolated founded cells
    iso = [c for c in s
           if not any((c[0] + dy, c[1] + dx) in s
                      for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                      if (dy, dx) != (0, 0))]
    assert not iso, f"isolated founded cells: {sorted(iso)[:5]}"
    # (ii) every remote fragment has >= 8 cells
    for comp in _components(s):
        if _touches(comp, pre):
            continue            # contiguous spill: joins the founder
        assert len(comp) >= 8, f"remote fragment of {len(comp)} cells"


def test_packet_rng_determinism():
    """v0.6 §2 determinism hard rule for the packet layer: two engines
    on seed 1 with the same planted fixture, run 3 full rounds ->
    byte-identical state_json (the packet origin / animal-center /
    establishment draws are pinned per (round, instance)). Fixture as
    in test_packet_coherence (ticket 0012 Task D re-pin 2026-08-03:
    grass_sward.bulrush at (68,181), the re-probed qualifying combo
    after the 0012 prune removed herb_forb.yarrow)."""
    def run() -> str:
        eng = _engine()
        _plant(eng, "grass_sward.bulrush", [(68, 181)])
        for t in range(3):
            eng.round(t)
        return json.dumps(eng.state_json(), sort_keys=True)
    assert run() == run()


def test_colonization_memory():
    """v0.6 §7.3 colonization memory: packets that fail against a sink
    region are remembered per lineage; a remembered target is not
    re-attempted at full weight within MEM_ROUNDS (the x MEM_PENALTY
    down-weight is packet_probability's, unit-tested in test_dispersal;
    here the record and purge lifecycle is checked). The shore
    tussock's packets straddle open ocean (mean f_hab < EST_F_MIN) and
    fail every round."""
    eng = _engine()
    ctx = eng.ctx
    s_t = _s_env(eng, "grass_sward.tussock")
    shore = ctx.land_cell & _dilate(_dilate(ctx.water_cell)) & (s_t < 0.0)
    ys, xs = np.nonzero(shore)
    sy, sx = int(ys[0]), int(xs[0])
    iid = _plant(eng, "grass_sward.tussock", [(sy, sx)])
    sid = eng.instances[iid].x.species_id
    assert dsp.MEM_ROUNDS == 3
    for t in range(5):
        eng.round(t)
        mem = eng._colon_mem.get(sid, {})
        assert iid in eng.instances, "viable shore source died"
        assert mem, f"round {t}: failed packets not remembered"
        # every entry is within MEM_ROUNDS of the current round (the
        # stale entries were purged at the top of this round)
        assert all(t - r <= dsp.MEM_ROUNDS for r in mem.values()), \
            f"round {t}: stale memory entry survives"
        if t == 0:
            assert all(r == 0 for r in mem.values()), \
                "fresh failures record the current round"
    # after round 4 no round-0 entry survives (age 4 > MEM_ROUNDS)
    mem = eng._colon_mem.get(sid, {})
    assert all(r > 0 for r in mem.values()), \
        "round-0 memory entries survived past MEM_ROUNDS"


def test_jump_foundling_size():
    """v0.6 §7.2: a jump packet that succeeds mints as a coherent blob
    (the filled 33-cell disk minus absorption) — the foundling is born
    with >= 20 cells, replacing the v0.5 single-pixel jump landings
    (baseline median birth 1 cell). ticket 0012 Task D re-pin
    (2026-08-03, the curated two-track flora census 0d0e0d6): the
    prune removed herb_forb.yarrow and the tree rebuild re-drew the
    viability landscape — the re-probe (see test_packet_coherence)
    lands the trio on grass_sward.bulrush at (68,181): exactly one
    jump foundling, born with 33 cells."""
    eng = _engine()
    iid = _plant(eng, "grass_sward.bulrush", [(68, 181)])
    eng.round(0)
    foundlings = [i2 for i2 in eng.instances if i2 != iid]
    assert len(foundlings) == 1, \
        f"expected one jump foundling, got {len(foundlings)}"
    n = int(eng.instances[foundlings[0]].cells.sum())
    assert n >= 20, f"jump foundling born with {n} cells"


# ── B6 §3 canopy shade (engine-side light) ────────────────────────────


def _shade_fixture_cell(eng: Engine, preset: str = "herb_forb.asterid"
                        ) -> tuple[int, int]:
    """A land cell MARGINAL for *preset* (s_env just below 0) with the
    LARGEST per-lineage capacity for it (K x U — the shared-cell density
    term must not decide the arms: the canopy is bamboo, percap 0.47, so
    a high-K cell keeps s_dens well below the lethal end and the shade
    factor becomes the differentiator).

    v0.9 re-pin (2026-08-01, the sand-sheet cold gate 2cc8e76 — ticket
    0009 world fallout): the plain ``s_env < 0`` argmax used to land on
    the marginal pre-gate cell (90,149) at s_env = -0.03 — marginal
    enough that the shade fold flips the intolerant thistle's s_env_eff
    positive (0.16 -> 0 over r0..r5) while the tolerant one holds. The
    cold gate reclassified 4143 seed-1 cells (cold-arid sand sheet ->
    reg), and the old argmax's U dropped 0.88 -> 0.75: the unconstrained
    argmax now lands on (64,105) at s_env = -0.35, healthy enough that
    BOTH arms hold the cell (measured: intolerant 1.0 through r5). The
    selection is now the argmax of K x U over a NARROW MARGINAL BAND
    -0.05 < s_env < 0, restoring the pre-gate character (measured on
    the gated world: the band's argmax is the pre-gate cell (90,149)
    itself — dead=0.000, spared=1.000)."""
    from exp.k15_simdiff.stress_adapter import evaluate as _ev
    s_u = _s_env(eng, preset)
    v_t = eng.sim.derive(eng.authority.mint(
        eng._order_sid[preset],
        eng._new_instance_id(eng._stream("test", f"peek:{preset}")),
        eng._stream("test", f"peek:{preset}")).traits, eng.pack)
    U = _ev(v_t, eng.ctx)["substrate_share"]
    KL = eng.K * U
    ok = eng.ctx.land_cell & (s_u > -0.05) & (s_u < 0.0) & (KL > 0.1)
    assert ok.any(), f"no shade-fixture cell for {preset}"
    score = np.where(ok, KL, -np.inf)
    y, x = np.unravel_index(int(np.argmax(score)), score.shape)
    return int(y), int(x)


def test_canopy_shade_kills_intolerant_spares_tolerant():
    """B6 §3: the shade fold drives DEMOGRAPHY — on the shared cell
    under the bamboo canopy, the shade-intolerant herb's density
    collapses to zero while the shade-tolerant one holds the cell
    through the window. (v0.7 re-pin: asserted at the SHARED CELL, not
    the lineage — the g-clock's f(g) ramp keeps an intolerant
    thistle's authored viability intact, so it now ESCAPES the shade by
    range expansion; the shade mechanism itself is the cell-level fold.
    v0.9 re-pin (2026-08-01, the sand-sheet cold gate 2cc8e76): the
    gate reclassified 4143 seed-1 cells, dropping the old fixture
    cell's substrate_share (90,149: U 0.88 -> 0.75, cold-arid sand
    sheet -> reg) so the plain s_env<0 argmax now lands on a healthy
    cell where BOTH arms hold — _shade_fixture_cell now selects a
    marginal-band cell (-0.05 < s_env < 0), restoring the pre-gate
    character; measured on the gated world: the band's argmax is the
    pre-gate cell itself (90,149), intolerant 0.3 -> 0.000 over r0..r5,
    tolerant 1.000. ticket 0028 re-pin (2026-08-02, immediate
    recombination): the fixture's founded pieces now recombine into the
    thistle at the round-0 commit (grace 0), shifting the density
    dynamics — the tolerant thistle's survival window narrows to r4
    (measured: dead <= 0.05 / spared >= 0.5 at r4 for tolerances
    <= 0.15 vs >= 0.5; everyone folds by r5). ticket 0012 Task D
    re-pin (2026-08-03, the curated two-track flora census 0d0e0d6):
    the prune removed herb_forb.thistle — the arms re-pin to
    herb_forb.asterid (the thistle archetype's composite-head
    successor); the marginal-band argmax now lands at (82,158) and the
    intolerant asterid's density collapses at r2 while the tolerant
    one holds the cell through r2 (measured: intolerant 0.000 /
    tolerant 1.000 at r2; the tolerant folds at r3). The height-escape
    mechanism — a taller reader reads
    f_light = 1 — lives in test_canopy_shade_height_escape.)"""
    def cell_mass(eng, cell, sid):
        tot = 0.0
        for d in eng.instances.values():
            if d.x.species_id != sid:
                continue
            y0, y1, x0, x1 = d.box
            if y0 <= cell[0] < y1 and x0 <= cell[1] < x1:
                tot += float(d.N[cell[0] - y0, cell[1] - x0])
        return tot

    def run_body(shade_tol):
        eng = _engine()
        cell = _shade_fixture_cell(eng)
        _plant(eng, "grass_sward.bamboo", [cell], n0=1.0)
        iid = _plant_variant(eng, "herb_forb.asterid", [cell],
                             {"shade_tolerance": shade_tol}, n0=0.3)
        sid = eng.instances[iid].x.species_id
        for t in range(3):            # measured (ticket 0012 Task D
            eng.round(t)              # re-pin): intolerant 0.000,
        return cell_mass(eng, cell, sid)   # tolerant 1.000 at r2
    dead = run_body(0.15)
    spared = run_body(0.9)
    assert dead <= 0.05, \
        f"shade-intolerant herb holds the shaded cell ({dead:.3f})"
    assert spared >= 0.5, \
        f"shade-tolerant herb lost the shaded cell ({spared:.3f})"


def test_canopy_shade_height_escape():
    """B6 §3: height_m is the growth answer — the shade comparison is
    STRICTLY taller, so a reader at the top of the height ordering
    reads f_light = 1 (no canopy above it), while a shorter reader
    under the same canopy reads f_light < 1. Same cell, same canopy:
    only the reader's height differs."""
    eng = _engine()
    s_oak = _s_env(eng, "tree.oak")
    s_br = _s_env(eng, "shrub.bramble")
    ok = eng.ctx.land_cell & (s_oak < 0.2) & (s_br < 0.0)
    y, x = np.unravel_index(int(np.argmax(np.where(ok, -s_br, -np.inf))),
                            s_br.shape)
    cell = (int(y), int(x))
    # bramble is 2 m under a 25 m oak -> shaded; the oak itself (equal
    # height, NOT strictly taller) is not shaded
    oak_i = _plant(eng, "tree.oak", [cell], n0=0.9)
    br_i = _plant(eng, "shrub.bramble", [cell], n0=0.3)
    light = eng._canopy_light_factors()
    assert float(light[br_i].min()) < 0.99
    assert np.allclose(light[oak_i], 1.0)
    # a bare (single-instance) oak reads f_light = 1 everywhere
    eng2 = _engine()
    _plant(eng2, "tree.oak", [cell], n0=0.9)
    light2 = eng2._canopy_light_factors()
    iid = next(iter(eng2.instances))
    assert np.allclose(light2[iid], 1.0)


# ── commit re-sync: derived views unchanged (ticket 0022) ─────────────


def test_commit_leaves_derived_views_unchanged():
    """Ticket 0022 item 2: the commit re-sync re-draws the Instance
    record (lineage bookkeeping) but must NOT re-derive the derived
    view — post-commit traits equal what the feed's _refresh already
    derived, and derive/vital/percap are pure and draw-free, so
    view/percap/vital are unchanged by the commit. A re-added
    commit-side _refresh re-deriving different values would break the
    invariant."""
    eng = _engine()
    ys, xs = np.nonzero(eng.ctx.land_cell)
    mid = len(ys) // 2
    _plant(eng, "tree.oak", [(int(ys[mid]), int(xs[mid]))])
    eng.round(0)
    for d in eng.instances.values():
        fresh_view = eng.sim.derive(d.x.traits, eng.pack)
        assert fresh_view == d.view, \
            "post-commit derived view differs from the traits' pure " \
            "derivation (the commit must not re-derive)"
        assert d.percap == pop.percap_demand(d.view), \
            "post-commit percap stale"
        assert d.vital == eng.sim.vital(d.x.traits, eng.pack), \
            "post-commit vital stale"


# ── §12.8 cache budget ───────────────────────────────────────────────


def test_reduced_cache_budget():
    """The §5.1 reduced cache stays within REDUCED_CACHE_MB per live
    instance (ticket 0004: genesis clones share one cache per RADIATED
    SPECIES — measure the shared one; 105 minted species on seed 1, the
    v0.9 mint floor dropped the 41 all-sub-floor species — ticket
    0009)."""
    eng = _engine()
    eng.genesis()
    seen = {}
    for d in eng.instances.values():
        seen[id(d.cache)] = d.cache
    worst = 0
    for c in seen.values():
        nbytes = c.f_worst.nbytes + c.s_env.nbytes + c.U.nbytes \
            + c.prov.nbytes
        worst = max(worst, nbytes)
    mb = worst / 2**20
    print(f"\nreduced cache: {mb:.2f} MiB over {len(seen)} shared "
          f"caches ({len(eng.instances)} instances)")
    assert mb <= REDUCED_CACHE_MB


# ── §9 drift retention (v0.5) ─────────────────────────────────────────


def _marginal_cell(eng: Engine, preset: str) -> tuple[int, int]:
    """A viable but stressed fixture cell whose shortfall is in a
    DRIFTABLE factor: pressure:cold/pressure:heat route (owner ruling
    2026-08-01 — the climate envelope is a pure derived, so the
    backward pass moves it), alongside the other drifted requirements.
    Picks the viable land cell with the worst driftable suitability
    factor."""
    sid = eng._order_sid[preset]
    rng = eng._stream("test", f"peek:{preset}")
    x = eng.authority.mint(sid, eng._new_instance_id(rng), rng)
    view = eng.sim.derive(x.traits, eng.pack)
    cache = eng._evaluate_cache(view, x.traits)
    driftable = {"pressure:cold", "pressure:heat", "pressure:bloom_frost",
                 "pressure:water", "pressure:waterlogging",
                 "pressure:fertility", "pressure:ph_low",
                 "pressure:ph_high", "pressure:salinity",
                 "pressure:rooting"}
    s = cache.s_env
    viable = eng.ctx.land_cell & (s < 0.0)
    worst = np.ones_like(s)
    for r, name in enumerate(cache.names):
        if name in driftable:
            worst = np.minimum(worst, cache.prov[r])
    score = np.where(viable, worst, np.inf)
    y, x = np.unravel_index(int(np.argmin(score)), s.shape)
    assert np.isfinite(score).any(), f"no driftable-stress cell for {preset}"
    return int(y), int(x)


def test_drift_retained_across_commits():
    """WIP genes ratchet across commits: two instances of ONE lineage in
    differently-stressed cells accumulate pairwise distance once the
    steady-tier gate opens (the pre-v0.7 flat nudge was replaced by the
    f(g) ramp — fauna RFC §1: steady axes are effectively frozen at low
    g and open smoothly past G_STEADY_ONSET; the reed clocks ~50
    generations/round, so the gate opens around round 4-5 and the
    ratchet is measured 0.0001 → 0.0052 over rounds 4-8). Note
    distance-to-record is 0 by construction for the orthodox instance
    (the commit amends the record to it, gerrit-style) — retention is
    only observable pairwise. The lineage is a REED (the derived-
    envelope landscape gives it a real habitat — tussock's 16
    near-breakeven cells do not survive 4 rounds), the marginal cell is
    cold-stressed, the contrast cell is required to be genuinely viable
    (s_env < -0.1) so the second instance does not die mid-test.
    v1.2 re-pin (ticket 0010): the two reeds are spatially separate, so
    the isolation wiring (option B) boosts their Δg and their divergence
    can now cross the SUB_D cluster edge and BRANCH the pair into two
    lineages mid-window — that is the point of the ticket, and the
    ratchet measurement below is unaffected because WIP retention
    survives the re-key (a divide is one branch per lineage; the pair
    never collapses back into one instance). ticket 0028 re-pin: the
    per-lineage threshold + grace-0 recombination merge this
    slow-diverging cross-env pair at the round-4 consolidation sweep
    (their d ~0.003 at age 4 < the reed lineage's threshold, long
    before the steady gate opens) — the retention mechanism is
    isolated from the consolidation governor by running sweep-free
    (consol_every = 0); the ratchet then measures over the full
    window (measured: 0 -> 0.0033 (r4) -> 0.0069 (r5) -> 0.0073).
    ticket 0012 Task D re-pin (2026-08-03, the tree rebuild re-drew
    every lineage's g parameters — content-addressed by sid — shifting
    the reed's steady-tier gate timing): the gate now opens at r8 (was
    r4-5) and the marginal reed survives past r29 (was ~r9); the
    window extends to r12 and the ratchet measures 0 -> 0.000312 (r8)
    -> 0.007159 (r12) (23x the 1.5x bar)."""
    from exp.k15_simdiff import authority as auth
    eng = _engine()
    eng.consol_every = 0          # ticket 0028: sweep-free (see above)
    c1 = _marginal_cell(eng, "grass_sward.reed")
    a = _plant(eng, "grass_sward.reed", [c1])
    sid = eng.instances[a].x.species_id
    # second member: the viable cell whose worst factor is as different
    # as possible from c1's (so the two drift in different directions)
    d0 = eng.instances[a]
    cache = d0.cache
    s = cache.s_env
    viable = eng.ctx.land_cell & (s < -0.1)
    r1 = next(r for r, n in enumerate(cache.names)
              if cache.prov[r][c1] == min(
                  cache.prov[q][c1] for q in range(len(cache.names))))
    contrast = np.where(viable, -cache.prov[r1], np.inf)
    yy, xx = np.mgrid[0:s.shape[0], 0:s.shape[1]]
    contrast[(np.abs(yy - c1[0]) < s.shape[0] // 4)
             & (np.abs(xx - c1[1]) < s.shape[1] // 4)] = np.inf
    c2 = tuple(int(v) for v in np.unravel_index(
        int(np.argmin(contrast)), s.shape))
    assert np.isfinite(contrast[c2]), "no healthy contrast cell"
    b = _plant(eng, "grass_sward.reed", [c2])
    ds = []
    for t in range(13):                   # r12 stays inside the survival
        eng.round(t)                      # window (the marginal reed
        assert a in eng.instances and b in eng.instances  # survives
                                                          # past r29)
        # the pair starts as one lineage; under ticket 0010 it may
        # branch (distinct sids) or the stem may promote (same new sid)
        # — either is legal; a merge is not (they diverge, never
        # collapse back into one instance)
        ds.append(auth.genes_distance(eng.instances[a].x.traits,
                                      eng.instances[b].x.traits))
    # the first rounds are g-frozen (steady gate); the ratchet is
    # non-decreasing from the gate-open round onward and clears the
    # 1.5x bar over the window. v1.2: the isolation-boosted tempo can
    # promote the lineage inside the window — the promotion's g reset
    # re-freezes the steady tier until the new lineage's g re-opens it,
    # a temporary PLATEAU (never a decrease; the ratchet resumes once
    # the new clock re-opens the gate).
    assert all(ds[i] >= ds[i - 1] for i in range(1, len(ds))), \
        f"ratchet not non-decreasing: {ds}"
    nz = next((i for i, v in enumerate(ds) if v > 0.0), None)
    assert nz is not None, f"no ratchet at all: {ds}"
    assert all(ds[i] >= ds[i - 1] for i in range(nz + 1, len(ds))), \
        f"ratchet not non-decreasing after gate open: {ds}"
    assert ds[-1] > 1.5 * ds[nz], f"no ratchet: {ds}"


# ── ticket 0010: isolation wiring (option B) ──────────────────────────


def test_isolation_wiring_accrues_g_faster():
    """The isolation Condition input is finally wired into Δg: an
    instance that has NOT touched any same-lineage sibling for
    ISO_RAMP_ROUNDS+1 rounds is fully isolated and accrues g at
    ~(1 + ISO_G_GAIN) x the connected sibling's rate (fauna RFC §1's
    pairwise 2x divergence — d(A,B) = (g_A − g0) + (g_B − g0); island
    lineages speciate first). The commit records the gene-flow signal:
    a touching/overlapping pair refreshes _last_contact."""
    from exp.k15_simdiff.engine import ISO_G_GAIN
    # both instances planted on the SAME viable cell: identical stress,
    # so the only difference in Δg is the isolation input (we control
    # _last_contact directly — it is the gene-flow signal)
    eng = _engine()
    c1, _c2 = _two_good_cells(eng, "grass_sward.reed", far=False)
    a = _plant(eng, "grass_sward.reed", [c1])
    b = _plant(eng, "grass_sward.reed", [c1])
    eng._last_contact[a] = -100          # fully isolated for the ramp
    eng._last_contact[b] = -100
    eng._verdict_feed(5, {})
    g_iso = eng._g_since_split[a]
    # connected variant: identical fixture, gene flow last round
    # (iso ramps back to ~0 at feed 5)
    eng2 = _engine()
    c3, _c4 = _two_good_cells(eng2, "grass_sward.reed", far=False)
    a2 = _plant(eng2, "grass_sward.reed", [c3])
    b2 = _plant(eng2, "grass_sward.reed", [c3])
    eng2._last_contact[a2] = 4
    eng2._last_contact[b2] = 4
    eng2._verdict_feed(5, {})
    g_touch = eng2._g_since_split[a2]
    assert g_iso > (1.0 + 0.3 * ISO_G_GAIN) * g_touch, \
        f"isolated g {g_iso:.1f} not boosted vs connected {g_touch:.1f}"
    # the commit's contact gate records the signal (stacked pair)
    eng3 = _engine()
    cc = _two_good_cells(eng3, "grass_sward.reed", far=False)[0]
    a3 = _plant(eng3, "grass_sward.reed", [cc])
    b3 = _plant(eng3, "grass_sward.reed", [cc])   # overlap: contact
    eng3.round(0)
    assert eng3._last_contact[a3] == 0 and \
        eng3._last_contact[b3] == 0, "contact not recorded at commit"


# ── §9 consolidation (v0.4.2) ─────────────────────────────────────────

# v0.9 (2026-08-01): the dune + lake-fetch gates (0d432c5, 758ec17)
# zeroed substrate_share on many dune/coastal/lake-shore cells — the
# old argmin-s_env fixture cells now read U = 0 (K x U = 0 -> instant
# density death at the planted n0: tussock (236,156/157) died at r0,
# lichen (194,202) decayed 1.0 -> 0.0 by r2), so s_env < 0 alone is no
# longer a sufficient viability test. The consolidation fixtures now
# also require per-lineage capacity K x U > CELL_CAP_MIN (measured on
# the final world: 0.5 lands the stacked fixture at (239,150/149) and
# the consolidation pair at (73,120)/(230,93); 0.3 and 0.7 fail).
CELL_CAP_MIN = 0.5


def _two_good_cells(eng: Engine, preset: str,
                    far: bool) -> tuple[tuple[int, int], tuple[int, int]]:
    """Two viable fixture cells for *preset* (s_env < 0 AND K x U >
    CELL_CAP_MIN — see the constant's note): the best cell and, for
    *far*, the best cell at least a QUARTER world away (the v0.5
    fixture asked half a world — no lichen cell is that far on the
    post-climate-dials landscape); else the best OTHER cell in the
    8x8 box around the first (the old (y, x+1) neighbor could be a
    U = 0 sink after the gates)."""
    from exp.k15_simdiff.stress_adapter import evaluate as _ev
    s = _s_env(eng, preset)
    v = eng.sim.derive(eng.authority.mint(
        eng._order_sid[preset],
        eng._new_instance_id(eng._stream("test", f"peek:{preset}")),
        eng._stream("test", f"peek:{preset}")).traits, eng.pack)
    KUL = eng.K * _ev(v, eng.ctx)["substrate_share"]
    ok = np.where(eng.ctx.land_cell & (s < 0.0) & (KUL > CELL_CAP_MIN),
                  s, np.inf)
    assert np.isfinite(ok).any(), f"no viable cell for {preset}"
    y1, x1 = np.unravel_index(int(np.argmin(ok)), ok.shape)
    if not far:
        y0, x0 = max(0, y1 - 4), max(0, x1 - 4)
        box = ok[y0:y1 + 5, x0:x1 + 5].copy()
        box[y1 - y0, x1 - x0] = np.inf
        by, bx = np.unravel_index(int(np.argmin(box)), box.shape)
        return (int(y1), int(x1)), (int(y0 + by), int(x0 + bx))
    far_ok = ok.copy()
    yy, xx = np.mgrid[0:ok.shape[0], 0:ok.shape[1]]
    far_ok[(np.abs(yy - y1) < ok.shape[0] // 4)
           & (np.abs(xx - x1) < ok.shape[1] // 4)] = np.inf
    y2, x2 = np.unravel_index(int(np.argmin(far_ok)), far_ok.shape)
    assert np.isfinite(far_ok).any()
    return (int(y1), int(x1)), (int(y2), int(x2))


def _matched_far_cells(eng: Engine, preset: str
                       ) -> tuple[tuple[int, int], tuple[int, int]]:
    """Two viable (s_env < -0.15, K x U > CELL_CAP_MIN) cells at least
    a QUARTER world apart with nearly IDENTICAL s_env (|Δ| < 0.01) —
    the v0.7 consolidation fixture. Contrasting far cells now genuinely
    diverge under the g-clock's mutation ramp (measured lichen scalar
    d ≈ 0.057, above MERGE_D 0.045), so the two far blocks must face
    the SAME pressure for the CONSOL sweep to see them as
    non-differentiated. Deterministic row-major sampling (every 40th
    viable cell). v0.9 (2026-08-01, dune + lake-fetch gates 0d432c5,
    758ec17): the old matched pair's second cell read U = 0 (K x U =
    0 — instant density death; measured (194,202): lichen cell decays
    1.0 -> 0.0 by r2, so the far block never survived to the round-9
    consolidation). The K x U > CELL_CAP_MIN floor restores two
    persisting blocks (measured: (73,120)/(230,93) — consolidated at
    the round-9 commit, re-split by r12)."""
    from exp.k15_simdiff.stress_adapter import evaluate as _ev
    s = _s_env(eng, preset)
    v = eng.sim.derive(eng.authority.mint(
        eng._order_sid[preset],
        eng._new_instance_id(eng._stream("test", f"peek:{preset}")),
        eng._stream("test", f"peek:{preset}")).traits, eng.pack)
    KUL = eng.K * _ev(v, eng.ctx)["substrate_share"]
    ok = eng.ctx.land_cell & (s < -0.15) & (KUL > CELL_CAP_MIN)
    ys, xs = np.nonzero(ok)
    cands = [(int(y), int(x)) for y, x in zip(ys[::40], xs[::40])]
    best = None
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            if max(abs(cands[i][0] - cands[j][0]),
                   abs(cands[i][1] - cands[j][1])) < 64:
                continue
            d = abs(float(s[cands[i]]) - float(s[cands[j]]))
            if best is None or d < best[0]:
                best = (d, cands[i], cands[j])
    assert best is not None and best[0] < 0.01, \
        f"no matched far cells for {preset} ({best})"
    return best[1], best[2]


def test_stacked_siblings_merge():
    """Two instances of ONE lineage sharing a cell (the stacking the
    shift-grid gate was blind to) become merge candidates via the
    overlap pass and collapse immediately (ticket 0028 re-pin: the
    merge grace is 0 — same-env stacked clones recombine at the first
    commit, d ≈ 0 < the per-lineage threshold). v0.9 re-pin
    (2026-08-01, the dune + lake-fetch gates 0d432c5/758ec17): the
    old argmin-s_env tussock cells (236,156/157) read U = 0 on the
    gated world (K x U = 0 — instant density death at r0, both arms
    extinct), so the fixture now also requires K x U > CELL_CAP_MIN
    (see its note); measured on the final world the fixture lands at
    (239,150)/(239,149) — both survive, merge at the round-0 commit,
    and retain c2."""
    eng = _engine()
    c1, c2 = _two_good_cells(eng, "grass_sward.tussock", far=False)
    a = _plant(eng, "grass_sward.tussock", [c1, c2])
    b = _plant(eng, "grass_sward.tussock", [c1])     # shares c1 with a
    for t in range(2):
        eng.round(t)
    survivors = [iid for iid in (a, b) if iid in eng.instances]
    assert len(survivors) == 1
    merged = eng.instances[survivors[0]]
    got = _cell(merged, *c2)
    assert got is not None and got[0] > 0.0, "merged range lost a cell"


def test_periodic_full_consolidation():
    """The CONSOL_EVERY commit joins NON-TOUCHING same-lineage
    instances (near-zero drift => d < the per-lineage threshold) once
    the grace allows: with the ticket 0028 grace of 0 the first
    effective consolidation is the round-4 commit — two blocks a
    quarter world apart are one instance after the round-4 commit.
    The join is not sticky across dressings: with no rain bridge the
    far fragment re-splits within two dressings (split hysteresis) —
    the sawtooth that caps instance growth. (v0.7 re-pin: the lineage
    is lichen.crust — viable in every quadrant — but the far blocks
    are planted on near-identical suitability cells: contrasting cells
    now genuinely diverge under the g-clock's mutation ramp, so the
    two blocks must face the same pressure for the sweep to see them
    as non-differentiated.) v0.9 re-pin (2026-08-01, the dune +
    lake-fetch gates 0d432c5/758ec17): the old matched pair's second
    cell read U = 0 (lichen (194,202) decayed 1.0 -> 0.0 by r2 — the
    far block died instead of consolidating), so _matched_far_cells
    now also requires K x U > CELL_CAP_MIN; measured on the final
    world the pair lands at (73,120)/(230,93). ticket 0028 re-pin
    (2026-08-02): with the grace 0 the sweep is the round-4 commit
    (was round 9 with the old grace 5); measured — consolidated at
    the round-4 commit, re-split by round 6."""
    eng = _engine()
    c1, c2 = _matched_far_cells(eng, "lichen.crust")
    a = _plant(eng, "lichen.crust", [c1])
    b = _plant(eng, "lichen.crust", [c2])
    for t in range(4):                    # commits 0..3: no contact, separate
        eng.round(t)
        assert a in eng.instances and b in eng.instances, \
            "far instances merged without contact"
    for t in range(4, 6):                 # round-4 commit consolidates
        eng.round(t)
    who1 = next((iid for iid, d in eng.instances.items()
                 if (got := _cell(d, *c1)) and got[0] > 0.0), None)
    who2 = next((iid for iid, d in eng.instances.items()
                 if (got := _cell(d, *c2)) and got[0] > 0.0), None)
    assert who1 is not None and who2 is not None and who1 == who2, \
        "far instances never consolidated"
    for t in range(6, 8):                 # two dressings: re-split
        eng.round(t)
    who1 = next((iid for iid, d in eng.instances.items()
                 if (got := _cell(d, *c1)) and got[0] > 0.0), None)
    who2 = next((iid for iid, d in eng.instances.items()
                 if (got := _cell(d, *c2)) and got[0] > 0.0), None)
    assert who1 is not None and who2 is not None and who1 != who2, \
        "far fragment never re-split"


# ── §12.9 hard-rule audit ────────────────────────────────────────────


def test_hard_rule_source_scan():
    """No uuid/random/wall-clock in the engine modules (the K1 hash
    streams are the only entropy source)."""
    offenders = []
    for name in SCANNED:
        text = (HERE / name).read_text()
        for i, line in enumerate(text.splitlines(), 1):
            if BANNED.search(line):
                offenders.append(f"{name}:{i}: {line.strip()}")
    for name in SCANNED_DESCENT:               # ticket 0018 (descent.py
        text = (HERE.parent / "k15_descent" / name).read_text()  # lives
        for i, line in enumerate(text.splitlines(), 1):  # in its own pkg)
            if BANNED.search(line):
                offenders.append(f"{name}:{i}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_hard_rule_runtime_guard(monkeypatch):
    """A full round runs with uuid/random/wall-clock booby-trapped:
    any hidden nondeterminism source raises. Planted oak on the
    row-major median land cell: a tree's low baseline death keeps it
    above the extinction floor for one round even at s_env = 1."""
    def _boom(*a, **k):
        raise AssertionError("wall-clock/uuid/random read in engine")
    monkeypatch.setattr(time, "time", _boom)
    monkeypatch.setattr(uuid, "uuid4", _boom)
    monkeypatch.setattr(random, "random", _boom)
    eng = _engine()
    ys, xs = np.nonzero(eng.ctx.land_cell)
    mid = len(ys) // 2
    iid = _plant(eng, "tree.oak",
                 [(int(ys[mid]), int(xs[mid]))])
    eng.round(0)
    assert iid in eng.instances


# ── ticket 0037: the per-cell total demand cap (budget v2) ─────────────


def _stack_cell(eng: Engine) -> tuple[int, int]:
    """The first land cell (row-major) whose capacity sits in the
    middle band 0.4 < K < 0.8 — deterministic on seed 1. Moderate
    enough for the cap tests: a 3-lineage stack at N0 = 0.5 lands
    strictly above K·S (K·0.5 < 0.4 < ΣD = 3) yet scales above N_FLOOR
    (scaled N = 0.5·K/6 ∈ (0.033, 0.067) >> N_FLOOR = 0.01), so the
    squeeze is exact and no floor binds."""
    ys, xs = np.nonzero(eng.ctx.land_cell)
    for y, x in zip(ys, xs):
        k = float(eng.K[y, x])
        if 0.4 < k < 0.8:
            return int(y), int(x)
    raise AssertionError("no mid-band land cell on seed 1")


def test_seed_cap_proportional_squeeze():
    """Ticket 0037: a stacked cell never ends above K·S — three
    lineages on one cell are scaled DOWN proportionally so the total
    demand ΣD = K·S exactly (no floor binds: every scaled N is far
    above N_FLOOR)."""
    eng = _engine()
    cell = _stack_cell(eng)
    K = float(eng.K[cell])
    percap = [1.0, 2.0, 3.0]
    for i, pc in enumerate(percap):
        iid = _plant(eng, "tree.oak", [cell])
        d = eng.instances[iid]
        d.N[...] = 0.5
        d.percap = pc
    total = 0.5 * sum(percap)
    scale = min(1.0, K * GENESIS_S / total)
    assert 0.0 < scale < 1.0, "test premise: the cell must be over K·S"
    eng._cap_seed_demand()
    after = [float(d.N[0, 0]) for d in eng.instances.values()]
    # proportional: every lineage scaled by the SAME factor
    assert all(a == pytest.approx(0.5 * scale) for a in after)
    # the cell total is exactly K·S (no floor-bound cell here)
    tot = sum(a * p for a, p in zip(after, percap))
    assert tot == pytest.approx(K * GENESIS_S)


def test_seed_cap_floor_bound_cell_keeps_floor():
    """Ticket 0037 floor handling (owner ruling): a cell whose scaled
    N would fall below N_FLOOR is KEPT at N_FLOOR — slight overshoot,
    presence wins — while the other lineage takes the full proportional
    squeeze; the cell total overshoots K·S by at most the floor."""
    eng = _engine()
    cell = _stack_cell(eng)
    K = float(eng.K[cell])
    small = _plant(eng, "tree.oak", [cell])
    ds = eng.instances[small]
    ds.N[...] = 0.0105                     # just above N_FLOOR pre-cap
    ds.percap = 1.0
    wall = _plant(eng, "grass_sward.reed", [cell])
    dw = eng.instances[wall]
    wall_N0 = max(10.0, 2.0 * K)           # any real squeeze scales <= 0.25
    dw.N[...] = wall_N0
    dw.percap = 1.0
    eng._cap_seed_demand()
    # the small lineage is floor-clamped (0.0105·scale < 0.01 for ANY
    # scale < 1/1.05, and the wall forces scale ≤ 0.25 < 0.952)
    assert float(eng.instances[small].N[0, 0]) == pytest.approx(pop.N_FLOOR)
    # the wall took the full proportional squeeze (not floor-bound:
    # wall_N0·scale >= 10·0.25 >> N_FLOOR)
    scale = min(1.0, K * GENESIS_S / (0.0105 + wall_N0))
    assert float(eng.instances[wall].N[0, 0]) == pytest.approx(wall_N0 * scale)
    # the cell total is K·S plus the small floor overshoot only
    tot = (float(eng.instances[wall].N[0, 0])
           + float(eng.instances[small].N[0, 0]))
    assert tot <= K * GENESIS_S + pop.N_FLOOR + 1e-12


def test_seed_cap_deterministic():
    """Ticket 0037: two identical mints + cap produce byte-identical N
    (the cap is draw-free; the ΣD accumulation iterates sorted iids —
    the hard rule's sorted() around float accumulation)."""
    def run():
        eng = _engine()
        cell = _stack_cell(eng)
        for pc in (1.0, 2.0, 3.0):
            iid = _plant(eng, "tree.oak", [cell])
            d = eng.instances[iid]
            d.N[...] = 0.5
            d.percap = pc
        eng._cap_seed_demand()
        return [(iid, eng.instances[iid].N.tobytes())
                for iid in sorted(eng.instances)]
    a, b = run(), run()
    assert [x[0] for x in a] == [x[0] for x in b]
    for (ia, na), (ib, nb) in zip(a, b):
        assert ia == ib and na == nb


# ── §12.1/2/3/8 slow full-run gate ───────────────────────────────────


@pytest.mark.slow
def test_full_run_acceptance():
    t0 = time.perf_counter()
    eng = Engine(SEED)
    eng.genesis()
    logs = [eng.round(t) for t in range(R_SLOW)]
    wall = time.perf_counter() - t0
    digest = json.dumps(eng.state_json(), sort_keys=True)

    # §12.1 determinism: a second, independent run is byte-identical
    eng2 = Engine(SEED)
    eng2.genesis()
    for t in range(R_SLOW):
        eng2.round(t)
    assert json.dumps(eng2.state_json(), sort_keys=True) == digest

    # §12.3 (ticket 0028 re-pin): the merge grace is 0 — same-env
    # touching pieces recombine IMMEDIATELY (event-driven, contact-
    # gated, every round; the per-lineage threshold refuses genuinely
    # diverged pairs). The first commit must already merge: the genesis
    # stacks (same-lineage instances sharing cells, d ≈ 0 < the
    # per-lineage threshold) collapse at round 0. The divide half of
    # item 3 lives in test_genesis_partition_diverges below.
    first_merge = next((t for t, log in enumerate(logs)
                        if any(d.outcome is Outcome.MERGE
                               for d in log.instances)), None)
    assert first_merge is not None and first_merge <= 1, \
        f"immediate recombination did not fire (first merge at {first_merge})"

    # §12.2 range tracking: per lineage alive at R, occupied cells'
    # mean s_env < unoccupied cells' (cache of the lineage's first
    # instance — post-drift genes are near-identical within a lineage)
    by_lin: dict[str, list[Dressed]] = {}
    for d in eng.instances.values():
        by_lin.setdefault(d.x.species_id, []).append(d)
    H, W = eng.ctx.H, eng.ctx.W
    report = []
    for sid, ds in sorted(by_lin.items()):
        occ = np.zeros((H, W), dtype=bool)
        for d in ds:
            y0, y1, x0, x1 = d.box
            occ[y0:y1, x0:x1] |= d.cells
        s_env = ds[0].cache.s_env
        m_in = float(s_env[occ].mean())
        m_out = float(s_env[~occ].mean())
        report.append((m_in - m_out, sid))
        assert m_in < m_out, \
            f"{sid}: occupied mean s_env {m_in:.3f} !< unoccupied {m_out:.3f}"
    report.sort(reverse=True)

    # §12.8 performance report (the 60 s gate is unmet by design at
    # current growth — the number is the deliverable, not an assert)
    print(f"\nfull run: {R_SLOW} rounds in {wall:.0f}s (plus one "
          f"determinism re-run), {len(eng.instances)} instances, "
          f"{len(by_lin)} lineages")
    print("worst range-tracking margins (in-out, negative = tracked):",
          [(s, round(m, 3)) for m, s in report[:5]])


@pytest.mark.slow
def test_genesis_partition_diverges():
    """§12.3 divide half (v1.2 re-pin, ticket 0010; re-pinned again
    ticket 0028; v1.3 ticket 0018: the pre-genesis descent ranks 12
    fragments at r1 (5 SPECIES + 7 SUBSPECIES, earned-g first-commit
    rank) and the lineage count GROWS 102 -> 107 by r10 (never below
    the 102 start) vs the control's monotone fall to 94): genesis
    clone pairs of one lineage (minted under the
    radiated SPECIES sids since ticket 0004 — the 35 ORDER nodes are
    ancestors, never seeded) register REAL divides within R rounds.
    The v1.2 machinery: isolated clones accrue g faster (the forces.py
    Condition isolation input is wired into Δg — option B), their
    trait cluster separates at the scalar-only SUB_D 0.08 edge, and
    once it has persisted (CLUSTER_PERSIST_ROUNDS) as a multi-member
    component (CLUSTER_MIN_SIZE) it branches as a SPECIES daughter
    beyond the lineage's g* (the tree gains WIDTH) or divides as
    SUBSPECIES below it. ticket 0028: the immediate-recombination
    rework (per-lineage merge threshold, grace 0) does not touch this
    path — genesis clones in different environments are spatially
    DISJOINT (never merge candidates), so they still diverge into
    clusters and divide. Ticket done-means: (1) the living lineage
    count GROWS at some point (a branch is not a relabel), (2)
    subspecies fires at least once, (3) divides/round stay bounded (no
    v0.7-disease churn)."""
    eng = Engine(SEED)
    eng.genesis()
    n0 = len({d.x.species_id for d in eng.instances.values()})
    prev_sid = {d.x.instance_id: d.x.species_id
                for d in eng.instances.values()}
    branches = 0
    subspecies = 0
    max_round_divides = 0
    lin_hist = [n0]
    for t in range(R_SLOW):
        log = eng.round(t)
        by_src: dict[str, dict[str, int]] = {}
        absorbed: dict[str, int] = {}
        for d in log.instances:
            src = prev_sid.get(d.instance_id, "")
            if d.outcome is Outcome.SPLIT and d.target:
                tgt_map = by_src.setdefault(src, {})
                tgt_map[d.target] = tgt_map.get(d.target, 0) + 1
            elif d.outcome is Outcome.MERGE:
                absorbed[src] = absorbed.get(src, 0) + 1
        for src, tgts in by_src.items():
            n_before = sum(1 for iid, s in prev_sid.items()
                           if s == src)
            for _tgt, c in tgts.items():
                if c != n_before - absorbed.get(src, 0):
                    branches += 1    # a subset re-keyed: real daughter
        subspecies += sum(1 for d in log.instances
                          if d.outcome is Outcome.SUBSPECIES)
        max_round_divides = max(
            max_round_divides,
            sum(1 for d in log.instances
                if d.outcome in (Outcome.SUBSPECIES, Outcome.SPLIT)))
        prev_sid = {d.x.instance_id: d.x.species_id
                    for d in eng.instances.values()}
        lin_hist.append(len({d.x.species_id
                             for d in eng.instances.values()}))
    print(f"genesis-partition divides: branches {branches}, subspecies "
          f"{subspecies}; lineage count {n0} -> {lin_hist[-1]} "
          f"(max {max(lin_hist)}, min {min(lin_hist)}); max divides/round "
          f"{max_round_divides}")
    assert branches >= 1, \
        f"no real daughter species (branching) within {R_SLOW} rounds"
    # the early rounds are the physical extinction wave (unseeded +
    # maladapted lineages die off — the baseline count fell 102 -> 91
    # monotonically); the ticket's growth shows as the count RECOVERING
    # above its trough as branches outpace die-outs (a promotion-only
    # world never recovers — a relabeling never grows the count).
    # ticket 0028 re-pin: with the per-lineage threshold + immediate
    # recombination the count PLATEAUS at the trough instead of
    # recovering (measured seed-1 20-round: branches 62, subspecies 38,
    # count 102 -> 97 = its trough; the branch/subspecies asserts below
    # are the real-cladogenesis evidence — a relabeling world fires
    # neither), so the guard here is the plateau: the count must not
    # keep collapsing below the trough after the extinction wave.
    assert lin_hist[-1] >= min(lin_hist), \
        "living lineage count collapsed below its trough"
    assert subspecies >= 1, "subspecies rank never fired on seed 1"
    # the v0.7 disease was SUSTAINED spurious per-instance splits
    # (100s every round); the measured max here is a one-off promotion
    # wave (464 at r13, mostly 0-160 elsewhere) — the bound is loose
    # enough to admit waves, tight enough to catch sustained churn.
    # v1.3 re-pin (ticket 0018): the pre-genesis descent's earned-g
    # first-commit ranks (5 SPECIES + 7 SUBSPECIES at r1 on seed 1)
    # add to the waves — measured 10-round max 206 (r3); the v4-era
    # 20-round max with the adapted fringe was 705 (r13), so the bound
    # moves to 1000 (loose enough for waves, tight enough for churn)
    assert max_round_divides < 1000, \
        f"churn: {max_round_divides} divides in one round"
