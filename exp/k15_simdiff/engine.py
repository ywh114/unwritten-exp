"""K15 sim-diff engine — the round loop (spec §4) and its wiring.

One engine instance owns: the world context (stress_adapter.WorldContext
reused), the §5.0 engine world fields (capacity, mean wind vector, D8
downstream pointer, mean currents), the per-instance reduced stress
cache (§5.1), the dressed instances (spatial state the tree never
sees), and the TreeAuthority commit bridge (§9).

Round sequence (spec §4, in order): verdict feed (§5.2 aggregation →
select → per-generation mutate) → population update (§6) → dispersal
(§7) → dressing (§8 per-instance components) → commit (§9 handshake).

Determinism (hard rule): every draw from kernel.hashrng Streams keyed
(world_seed, "k15.<stage>", f"{round}:{instance_id}"); instances are
processed in sorted instance_id order, cells row-major. No uuid, no
random, no wall-clock reads.

Downstream pointer: the delivered dump persists h_flow_dir — the SAME
deterministic K11 hydrology function's output (priority-flood + D8 to
lowest filled neighbor) at delivery resolution, which IS the anchor on
current packs. It is reused verbatim (re-deriving would be redundant);
if a future pack omits it, it is re-derived from w_elev via the K11
functions (spec §5.0 wording covers both).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from exp.k13_treegen.flora.backbone import build as build_backbone
from exp.k13_treegen.flora.content import ContentPack, load_content
from exp.k13_treegen.flora.sim import FloraSim
from exp.k13_treegen.forces import (
    Condition, G_NOVEL, G_REF, G_STEADY_ONSET, G_STEADY_RAMP,
    NOVELTY_MULT, P_NOVEL_MAX, STRESS_G_BOOST, g_star as draw_g_star,
    rate_multiplier, share_ratios, step_scale,
)
from exp.k13_treegen.interface import (ChangeLog, Instance, StressVerdict,
                                       VitalRates)
from exp.k13_treegen.model import Rank, Tree
from exp.k13_treegen.registry import Tier, ValueType
from exp.k15_simdiff import authority as auth
from exp.k15_simdiff import dispersal as dsp
from exp.k15_simdiff import genesis as gen
from exp.k15_simdiff import population as pop
from exp.k15_simdiff import stress_adapter as sa
from exp.k15_simdiff.req_flora import REQ_LIGHT
from kernel.hashrng import Stream
from kernel.stress.stress import compose

FLORA_CONTENT = Path("exp/k13_treegen/content/flora")

# ── spec §13 knobs not owned by the sub-modules ───────────────────────
ROUND_YEARS = pop.ROUND_YEARS      # the T in every per-round conversion
N_GEN_CAP = 400                    # mutate calls per round cap (§4)
RE_EVAL_D = 0.15                   # cache invalidation distance (§5.1)
EST_F_MIN = dsp.EST_F_MIN          # establishment gate (settled 0.3)

# ── rule B+ founding / differentiation knobs (spec v0.4 §7.3/§8) ──────
DIFF_D = 0.2          # verdict-gap base threshold (s_env scale; cal
                      # 2026-08-01: above generalist medians ≤0.16,
                      # below specialist medians ≥0.3, seed 1 stat pass)
MOB_K = 1.0           # mobility gain: TH = DIFF_D · (1 + MOB_K · mob)
DIFF_MIN_CELLS = 32   # divergent sub-range split size floor (sliver
                      # suppression: below it the blob incubates inside
                      # the parent, never mints)
CONSOL_EVERY = 5      # full-lineage consolidation period (spec v0.4.2
                      # §9): every CONSOL_EVERY-th commit the merge
                      # candidates are ALL same-lineage pairs (not just
                      # touching/overlapping), collapsing every
                      # non-differentiated (d < MERGE_D, grace-honored)
                      # instance cluster to one record. The §9 "final
                      # pass" run periodically — the instance-count
                      # governor (owner ruling 2026-08-01)

# ── g currency (ticket 0008 — fauna RFC §1: generation-time clock,
#    three forces, per-clade seeded g*; forces.py constants referenced,
#    never duplicated) ────────────────────────────────────────────────
# The per-round Δg formula (ticket 0008 item a), per generation:
#   Δg_gen = rate_mult × (drift baseline + stress-descent share ×
#            (1 + STRESS_G_BOOST·stress) + runaway share × ornament
#            fraction + enum share)
# with the shares from forces.py's Condition table (isolation 0 — the
# rounds have no isolate input; the dressed partition is the rounds'
# vicariance and g* decides the rank). At benign stress the shares
# normalize so Δg ≈ n_gen (the anchor: g_star median 500 generations ≈
# 9 rounds for a fast grass, ~50 for a slow tree at ROUND_YEARS=100).
DG_DRIFT_BASE = 1.0     # the drift baseline (~1 generation-distance
                        # per generation; the plain generation clock)
DG_ENUM_SHARE = 0.05    # enum redraws' g contribution per generation
                        # (forces.py ENUM_RATE is small; a redraw is a
                        # discrete jump worth a few % of a generation)
G_STEP_REF = 100.0      # the species-edge dg scale (flora backbone
                        # DG_* medians 300/150/60): forces.py's p_novel
                        # is a per-EDGE rate, so the rounds' per-round
                        # novel probability per axis is
                        # p_novel × n_gen / G_STEP_REF
# flora display/ornament axes — the runaway force's target (fauna RFC
# §1: "runaway applies to flora display organs: flowers"). The CONTENT
# names them: axes whose consumers include "runaway" (flower_symmetry,
# pigment_expression, flower_size_mm — the display section of
# axes_core.toml). The ornament FRACTION of the mutable registry axes
# is computed at engine init; the runaway share scales the g accrual
# by it (a flora without flowers runs no runaway contribution).

_D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0),
       (1, 1)]


# ── §5.1 reduced cache ────────────────────────────────────────────────


@dataclass
class CachedFields:
    """The reduced per-instance stress fields (spec §5.1): the worst
    (growing) month's product and provenance, plus the substrate-share
    capacity plane U(c). ``traits`` is the gene view the cache was
    computed from — re-evaluation compares drift against it with the
    §9 distance metric at RE_EVAL_D (the metric is defined on genes,
    not on the derived view)."""

    traits: dict
    view: dict
    f_worst: np.ndarray          # (H,W) f32
    s_env: np.ndarray            # (H,W) f32
    prov: np.ndarray             # (R,H,W) f32 — per-requirement at m*
    names: tuple[str, ...]
    U: np.ndarray                # (H,W) f32 — substrate share (1 water)


@dataclass
class Dressed:
    """Y: one instance's spatial dressing (sim-side; the tree never
    sees it). N, rain and div are WINDOWED (bbox) arrays — the
    bounding-box optimization (2026-08-01): most instances occupy a
    tiny fraction of the 256² world, so every per-instance field is
    stored as its bounding window and world fields (cache planes, K,
    wind) are sliced on read. ``box`` = (y0, y1, x0, x1) world coords
    of the window; all three arrays share it and it always covers
    every nonzero cell of N, rain and div. rain is the transient
    propagule deposit (spec §3 two-density accounting); div tags the
    DIVERGENT sub-range (rule B+, spec v0.4 §7.3): cells that joined
    despite failing the verdict gate — they count toward the parent's
    gene pool while incubating and split off only when a contiguous
    divergent region reaches DIFF_MIN_CELLS and is still divergent
    (§8). orphan tags cells that were DISCONNECTED from the main
    component at the last dressing (§8 split hysteresis): a fragment
    mints only when it stays disconnected across consecutive dressings,
    so a one-round bridge loss (mortality hole, sparse rain) does not
    oscillate join/split."""

    x: Instance
    N: np.ndarray
    rain: np.ndarray
    cache: CachedFields
    view: dict
    percap: float
    vital: VitalRates
    div: np.ndarray
    orphan: np.ndarray
    box: tuple[int, int, int, int]

    @property
    def cells(self) -> np.ndarray:
        return self.N > 0.0

    @property
    def mass(self) -> float:
        return float(self.N.sum())

    def world_slice(self) -> tuple[slice, slice]:
        y0, y1, x0, x1 = self.box
        return np.s_[y0:y1, x0:x1]

    def rewindow(self, new_box: tuple[int, int, int, int]) -> None:
        """Re-embed the three windowed arrays at *new_box* (which must
        cover every nonzero cell)."""
        if new_box == self.box:
            return
        old = self.box
        self.N = _embed(self.N, old, new_box, 0.0)
        self.rain = _embed(self.rain, old, new_box, 0.0)
        self.div = _embed(self.div, old, new_box, False)
        self.orphan = _embed(self.orphan, old, new_box, False)
        self.box = new_box


def _embed(src: np.ndarray, src_box, dst_box, fill) -> np.ndarray:
    """Re-embed window *src* (world box *src_box*) into a fresh array
    at *dst_box*, copying the overlap (handles both grow and shrink)."""
    y0, y1, x0, x1 = dst_box
    out = np.full((y1 - y0, x1 - x0), fill, dtype=src.dtype)
    ov = _overlap_view(src, src_box, dst_box)
    if ov is not None:
        out[ov[1]] = ov[0]
    return out


def _mask_box(mask: np.ndarray, box) -> tuple[int, int, int, int] | None:
    """World bbox of the True cells of window *mask* at world *box*;
    None when empty."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None
    y0, _, x0, _ = box
    return (y0 + int(ys.min()), y0 + int(ys.max()) + 1,
            x0 + int(xs.min()), x0 + int(xs.max()) + 1)


def _union_box(a, b) -> tuple[int, int, int, int]:
    return (min(a[0], b[0]), max(a[1], b[1]),
            min(a[2], b[2]), max(a[3], b[3]))


def _dressed_box(d: Dressed) -> tuple[int, int, int, int]:
    """The tight box covering every nonzero cell of N, rain, div
    (falls back to the current box when all empty)."""
    return _mask_box((d.N > 0.0) | (d.rain > 0.0) | d.div, d.box) \
        or d.box


def _crop(d: Dressed, mask: np.ndarray
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray,
                     tuple[int, int, int, int]]:
    """Crop a Dressed's windowed arrays to *mask*'s world bbox (for
    splits): (N, rain, div, orphan) masked then cropped, plus the world
    box."""
    box = _mask_box(mask, d.box) or d.box
    y0, _, x0, _ = d.box
    sl = np.s_[box[0] - y0:box[1] - y0, box[2] - x0:box[3] - x0]
    return (np.where(mask, d.N, 0.0)[sl],
            np.where(mask, d.rain, 0.0)[sl],
            np.where(mask, d.div, False)[sl],
            np.where(mask, d.orphan, False)[sl], box)


def _overlap_view(arr: np.ndarray, box, rect):
    """The portion of window *arr* (world *box*) inside world *rect*:
    (sub-array, slice-in-rect), or None when there is no overlap."""
    y0, y1, x0, x1 = box
    oy0, oy1 = max(y0, rect[0]), min(y1, rect[1])
    ox0, ox1 = max(x0, rect[2]), min(x1, rect[3])
    if oy0 >= oy1 or ox0 >= ox1:
        return None
    return (arr[oy0 - y0:oy1 - y0, ox0 - x0:ox1 - x0],
            np.s_[oy0 - rect[0]:oy1 - rect[0],
                  ox0 - rect[2]:ox1 - rect[2]])


# ── §5.0 engine world fields ──────────────────────────────────────────


def mean_wind(z: dict, H: int, W: int) -> tuple[np.ndarray, np.ndarray]:
    """Annual mean wind vector (u, v) at anchor (spec §5.0): the monthly
    delivered fields averaged over the month AND sample axes, bilinear-
    upsampled via the adapter's convention when the delivered grid is
    coarser (c_wind_* are (12, samples, h, w) at 128² on seed 1)."""
    wu = z["c_wind_u"].astype(np.float64).mean(axis=(0, 1))
    wv = z["c_wind_v"].astype(np.float64).mean(axis=(0, 1))
    out = []
    for a in (wu, wv):
        if a.shape != (H, W):
            fy, fx = H // a.shape[0], W // a.shape[1]
            a = sa._upsample(a.astype(np.float32), fy).astype(np.float64) \
                if fx == fy else np.repeat(np.repeat(a, fy, 0), fx, 1)
        out.append(np.ascontiguousarray(a))
    return out[0], out[1]


def downstream_pointer(z: dict) -> np.ndarray:
    """D8 downstream pointer as flattened neighbor indices (-1 =
    terminal). Reuses the persisted h_flow_dir (the K11 hydrology
    function's own output); re-derives via priority_flood +
    flow_direction when absent (spec §5.0)."""
    H, W = z["h_ocean_mask"].shape
    if "h_flow_dir" in z:
        codes = z["h_flow_dir"].astype(np.int32)
    else:
        from exp.k11_worldgen.hydrology import (flow_direction,
                                                priority_flood)
        ocean = (z["h_ocean_mask"] | z["h_sea_mask"]).astype(bool)
        w = priority_flood(z["w_elev"].astype(np.float64), ocean)
        codes, _cost = flow_direction(w, z["w_elev"].astype(np.float64))
        codes = codes.astype(np.int32)
    ptr = np.full((H, W), -1, dtype=np.int32)
    for i, (dy, dx) in enumerate(_D8):
        m = codes == i
        ys, xs = np.nonzero(m)
        ny, nx = ys + dy, xs + dx
        inside = (ny >= 0) & (ny < H) & (nx >= 0) & (nx < W)
        ptr[ys[inside], xs[inside]] = ny[inside] * W + nx[inside]
    return ptr


def mean_currents(seed_dir: Path) -> tuple[np.ndarray, np.ndarray]:
    """Monthly-mean current field (u, v) at anchor (spec §5.0): the
    persisted payload's mean velocity (the adapter's private loader,
    promoted to shared use here)."""
    p = sa._currents_payload(seed_dir)
    return (np.ascontiguousarray(p["u"], dtype=np.float64),
            np.ascontiguousarray(p["v"], dtype=np.float64))


def mobility(view: dict, wspd: np.ndarray, cells: np.ndarray) -> float:
    """Sustained-channel mobility scalar (rule B+, spec v0.4 §7.3):
    channel pmf mass × mean kernel reach — wind λ from the mean wind
    speed over the instance's own cells and propagule mass, water/
    animal/local at their kernel scales. Jump is EXCLUDED (episodic —
    jump landings mint by rule, they do not homogenize). High mobility
    = strong gene flow = differentiation needs a larger verdict gap."""
    pmf = view.get("dispersal_channels") or {}
    mass = view.get("propagule_mass_mg")
    lam_w = 0.0
    if isinstance(mass, (int, float)) and not isinstance(mass, bool) \
            and mass > 0.0 and cells.any():
        lam_w = min(dsp.WIND_K
                    * float(wspd[cells].mean()) / math.sqrt(mass),
                    dsp.WIND_MAX_CELLS)
    return float(pmf.get("wind", 0.0)) * lam_w \
        + float(pmf.get("water", 0.0)) * dsp.WATER_LAMBDA \
        + float(pmf.get("animal", 0.0)) * dsp.ANIMAL_RADIUS_CELLS \
        + float(pmf.get("local", 0.0)) * 1.5


# ── the engine ────────────────────────────────────────────────────────


class Engine:
    """The K15 sim-diff engine (spec §4). Construct per (world seed):
    loads the pack, the world context, the §5.0 fields, builds the
    committed backbone tree and its authority. ``genesis()`` seeds
    round 0; ``round(t)`` runs one round; ``run(rounds)`` both."""

    def __init__(self, seed: int, content: Path = FLORA_CONTENT,
                 pack: ContentPack | None = None) -> None:
        self.seed = seed
        self.pack = pack if pack is not None else load_content(content)
        self.sim = FloraSim(self.pack)
        self.ctx = sa.load_world(seed)
        self.tree: Tree = build_backbone(seed, self.pack)
        self.authority = auth.TreeAuthority(self.tree)
        self.K = gen.load_capacity(seed, self.ctx)
        seed_dir = sa.K11_OUT / f"seed_{seed:08d}"
        with np.load(seed_dir / "world.npz") as zf:
            z = {k: zf[k] for k in zf.files}
        self.wind_u, self.wind_v = mean_wind(z, self.ctx.H, self.ctx.W)
        self.wspd = np.hypot(self.wind_u, self.wind_v)
        self.downstream = downstream_pointer(z)
        self.cur_u, self.cur_v = mean_currents(seed_dir)
        # preset id -> the ORDER node sid carrying the preset record
        self._order_sid = {
            n.preset: n.sid for n in self.tree.nodes.values()
            if n.rank is Rank.ORDER and n.preset}
        self.instances: dict[str, Dressed] = {}
        self.retired: list[str] = []
        self._clone_counter = 0
        # ticket 0008 g bookkeeping: per-instance generations since the
        # last split (the g clock's Δg accrues in _verdict_feed);
        # per-lineage (sid) lognormal rate multiplier and seeded g*
        # (fauna RFC §1: fast radiators AND living fossils; per-clade
        # radiation tempos), drawn once via pinned k15.g streams.
        self._g_since_split: dict[str, float] = {}
        self._rate_mult: dict[str, float] = {}
        self._g_star: dict[str, float] = {}
        # transient diagnostic: instance -> g_since_split at its last
        # divide re-key (the g-currency tempo evidence; the clock
        # resets on re-key, so the post-commit value is 0)
        self._divide_g: dict[str, float] = {}
        reg = self.pack.registry.axes
        mut_axes = [n for n, s in reg.items() if s.mutable]
        # runaway's ornament fraction of the mutable registry axes (the
        # content's own "runaway" consumer tag; plan-scoped axis sets
        # carry the same mutable axes, so this is a pack constant)
        self._ornament_frac = (
            sum(1 for n in mut_axes if "runaway" in reg[n].consumers)
            / max(1, len(mut_axes)))
        # mutable scalar/int axes: the only axes the novelty tail rolls
        # on (forces.py's p_novel lives in the scalar branch)
        self._scalar_axes = {
            n for n, s in reg.items()
            if s.mutable and s.value_type in (ValueType.SCALAR,
                                              ValueType.INT)}
        # f(g) ramp lookup sets (the per-axis hot path of the verdict
        # feed): steady axes get the leaky tier gate, non-mutable axes
        # never move (forces.py gate 0)
        self._steady_axes = {n for n, s in reg.items()
                             if s.mutable and s.tier is Tier.STEADY}
        self._immutable_axes = {n for n, s in reg.items()
                                if not s.mutable}
        # v0.6 §7.3 colonization memory: per lineage (sid), the cells a
        # packet ATTEMPTED and failed -> last-attempt round. A packet
        # whose candidate cells include a remembered cell is
        # down-weighted x MEM_PENALTY; entries older than MEM_ROUNDS are
        # purged each round (deterministic sorted iteration).
        self._colon_mem: dict[str, dict[tuple[int, int], int]] = {}
        # v0.6 diagnostics hook: per instance, the founded cells of the
        # LAST dispersal (world (y, x) -> N) — the packet-coherence
        # acceptance test and the stats harness read it; transient state,
        # never serialized.
        self._founded_new: dict[str, dict[tuple[int, int], float]] = {}

    # ── ids and streams ──────────────────────────────────────────────

    def _new_instance_id(self, rng: Stream) -> str:
        self._clone_counter += 1
        return f"i{rng.u64(0, self._clone_counter):012x}"

    def _stream(self, stage: str, key: str) -> Stream:
        return Stream(self.seed, f"k15.{stage}", key)

    def _seed_lineage(self, sid: str) -> None:
        """Draw the lineage's rate multiplier and g* ONCE (pinned by
        sid through the k15.g stream — fauna RFC §1: per-lineage
        lognormal rate multiplier, per-clade seeded speciation cutoff;
        forces.py rate_multiplier/g_star idioms). Deterministic: the
        stream is content-addressed by sid, so draw order never
        matters."""
        rng = self._stream("g", sid)
        self._rate_mult[sid] = rate_multiplier(rng.child("rate"))
        self._g_star[sid] = draw_g_star(rng.child("star"))

    def _lineage(self, sid: str) -> tuple[float, float]:
        """(rate_mult, g_star) for lineage *sid*, seeded on first use —
        covers every minting path (genesis, divides, foundlings,
        test-planted instances)."""
        if sid not in self._rate_mult:
            self._seed_lineage(sid)
        return self._rate_mult[sid], self._g_star[sid]

    # ── §5.1 cache ───────────────────────────────────────────────────

    def _evaluate_cache(self, view: dict, traits: dict) -> CachedFields:
        factors = sa.evaluate(view, self.ctx)
        # the adapter's F is already the requirement product — reuse it
        # (statpass.reduced convention); provenance excludes the
        # F/s_env/substrate_share bookkeeping planes
        F = factors["F"]
        m = F.argmin(axis=0)
        f_worst = np.take_along_axis(F, m[None], axis=0)[0]
        names = tuple(k for k in factors
                      if k not in ("F", "s_env", "substrate_share"))
        prov = np.stack([
            np.take_along_axis(factors[k], m[None], axis=0)[0]
            for k in names]) if names else np.zeros(
                (0, self.ctx.H, self.ctx.W), dtype=np.float32)
        return CachedFields(
            traits=dict(traits),
            view=dict(view),
            f_worst=f_worst.astype(np.float32),
            s_env=(1.0 - 2.0 * f_worst).astype(np.float32),
            prov=prov.astype(np.float32), names=names,
            U=factors["substrate_share"].astype(np.float32))

    def _refresh(self, d: Dressed) -> None:
        """Re-derive the view from WIP genes; re-cache only when the
        genes drifted ≥ RE_EVAL_D from the cached ones (§5.1, §9
        metric)."""
        d.view = self.sim.derive(d.x.traits, self.pack)
        d.percap = pop.percap_demand(d.view)
        d.vital = self.sim.vital(d.x.traits, self.pack)
        if auth.genes_distance(d.x.traits, d.cache.traits) >= RE_EVAL_D:
            d.cache = self._evaluate_cache(d.view, d.x.traits)

    # ── §10 genesis ──────────────────────────────────────────────────

    def genesis(self) -> None:
        """Round 0 (spec §10): seed every preset, partition into clones,
        mint one instance per clone (the clone carries the preset
        record's genes verbatim — mint makes no draws). Clones of one
        preset have IDENTICAL genes, so the view/vital/percap and the
        §5.1 cache are evaluated ONCE per preset and shared by
        reference (the bbox optimization, 2026-08-01: 1122 clones → 35
        evaluations; _refresh replaces rather than mutates, so sharing
        is copy-on-drift safe)."""
        seeds = gen.genesis_rain(self.pack, self.sim, self.ctx, self.K,
                                 self.seed)
        full = (0, self.ctx.H, 0, self.ctx.W)
        for pid in sorted(seeds):
            sid = self._order_sid[pid]
            self._seed_lineage(sid)
            rng = self._stream("genesis", f"mint:{pid}")
            shared = None
            for i, clone in enumerate(seeds[pid]):
                iid = self._new_instance_id(rng)
                self._g_since_split[iid] = 0.0
                x = self.authority.mint(sid, iid, rng.child(str(i)))
                if shared is None:
                    view = self.sim.derive(x.traits, self.pack)
                    shared = (view, pop.percap_demand(view),
                              self.sim.vital(x.traits, self.pack),
                              self._evaluate_cache(view, x.traits))
                view, percap, vital, cache = shared
                box = _mask_box(clone.N > 0.0, full)
                N = clone.N[np.s_[box[0]:box[1], box[2]:box[3]]] \
                    .astype(np.float64)
                self.instances[iid] = Dressed(
                    x=x, N=N, rain=np.zeros_like(N), cache=cache,
                    view=view, percap=percap, vital=vital,
                    div=np.zeros_like(N, dtype=bool),
                    orphan=np.zeros_like(N, dtype=bool), box=box)

    # ── §4 step 1: verdict feed ──────────────────────────────────────

    def _canopy_light_factors(self) -> dict[str, np.ndarray]:
        """B6 §3 canopy-light pass (engine-side; the stress adapter is
        per-lineage blind, so the shade field is a ROUND-TIME term the
        engine computes). Per LAND instance, the (box-window) f_light
        array over its cells:

            shade(c)   = clip(Σ_i cd_i · N_i(c) over instances i with
                             height_i > height_reader, 0, 1)
            f_light(c) = clip(1 − LAYER_LIGHT_COEF[layer] · shade(c)
                              · (1 − shade_tolerance), 0, 1)

        canopy_density rides the derived view (flora.derive
        _derived_canopy_density, exposed through FloraSim.derive);
        height_m is the growth answer — it enters through the strict
        ``>`` comparison, so a taller reader literally escapes the
        shade of a shorter canopy. The layer axis modulates exposure
        (understory plans EXPECT shade: coef understory < subcanopy <
        canopy). Deterministic: instances processed in sorted id order,
        the canopy planes accumulated in sorted-height order (float
        accumulation pinned by the hard rule)."""
        H, W = self.ctx.H, self.ctx.W
        by_h: dict[float, list[Dressed]] = {}
        for d in self.instances.values():
            cd = float(d.view.get("canopy_density") or 0.0)
            h = float(d.view.get("height_m") or 0.0)
            if cd <= 0.0 or h <= 0.0:
                continue
            by_h.setdefault(h, []).append(d)
        if not by_h:
            return {}
        hs = sorted(by_h, reverse=True)          # descending heights
        planes = []
        for h in hs:
            plane = np.zeros((H, W), dtype=np.float64)
            # sorted instance ids within a height: the float accumulation
            # order is pinned by the hard rule, not by dict insertion
            by_iid = {d.x.instance_id: d for d in by_h[h]}
            for iid in sorted(by_iid):
                d = by_iid[iid]
                plane[d.world_slice()] += d.N * float(
                    d.view.get("canopy_density") or 0.0)
            planes.append(plane)
        # cums[k] = sum of the k TALLEST planes (heights hs[:k]);
        # reader shade = cums[count of heights > height_reader].
        cums = [np.zeros((H, W), dtype=np.float64)]
        for p in planes:
            cums.append(cums[-1] + p)
        out: dict[str, np.ndarray] = {}
        for iid in sorted(self.instances):
            d = self.instances[iid]
            if d.view.get("medium") == "water":
                continue
            h_r = float(d.view.get("height_m") or 0.0)
            cnt = 0
            while cnt < len(hs) and hs[cnt] > h_r:
                cnt += 1
            shade = np.clip(cums[cnt][d.world_slice()], 0.0, 1.0)
            layer = str(d.view.get("layer") or "ground")
            coef = sa.LAYER_LIGHT_COEF.get(layer, 0.5)
            tol = d.view.get("shade_tolerance")
            tol = float(tol) if isinstance(tol, (int, float)) else 0.0
            f = np.clip(1.0 - coef * shade
                        * (1.0 - min(max(tol, 0.0), 1.0)), 0.0, 1.0)
            out[iid] = f.astype(np.float32)
        return out

    def _verdict_feed(self, t: int,
                      light: dict[str, np.ndarray]) -> None:
        for iid in sorted(self.instances):
            d = self.instances[iid]
            total = d.mass
            if total <= 0.0:
                continue
            y0, y1, x0, x1 = d.box
            agg = {d.cache.names[r]: float(
                       (d.cache.prov[r][y0:y1, x0:x1] * d.N).sum()
                       / total)
                   for r in range(len(d.cache.names))}
            # B6 §3 canopy light: the dynamic shade factor joins the
            # cached provenance BEFORE compose (aggregated over the
            # instance's own cells, N-weighted — same shape as the
            # cache aggregation). The factor planes were computed ONCE
            # for the round (the round's entry state — the feed and the
            # population step read the SAME shade field).
            f_light = light.get(iid)
            if f_light is not None:
                agg[REQ_LIGHT] = float((f_light * d.N).sum() / total)
            res = compose(agg)
            verdict = StressVerdict(s=res.s, provenance=res.factors)
            pressure = self.sim.select(verdict, d.x.traits, self.pack)
            height = float(d.view.get("height_m") or 0.0)
            gen_time = 2.0 * math.sqrt(max(height, 1e-6))
            n_gen = int(min(N_GEN_CAP,
                            max(1, math.ceil(ROUND_YEARS / gen_time))))
            # ── g accumulation (ticket 0008, fauna RFC §1) ──────────
            # Δg this round = n_gen × rate_mult × (drift baseline +
            # stress-descent share × (1 + STRESS_G_BOOST·stress) +
            # runaway share × ornament fraction + enum share), the
            # forces.py Condition share table adapted to flora
            # (isolation 0 — the rounds have no isolate input; the
            # dressed partition is the rounds' vicariance and g*
            # decides the rank). n_gen is the flora gen_time clock
            # (gen_time = 2·sqrt(height_m) — spec §4 step 1).
            rate_mult, _star = self._lineage(d.x.species_id)
            stress = min(max(res.s, 0.0), 1.0)
            shares = share_ratios(Condition(stress=stress))
            dg = n_gen * rate_mult * (
                DG_DRIFT_BASE
                + shares.descent * (1.0 + STRESS_G_BOOST * stress)
                + shares.runaway * self._ornament_frac
                + DG_ENUM_SHARE)
            self._g_since_split[iid] = \
                self._g_since_split.get(iid, 0.0) + dg
            # mutation magnitude ∝ f(g) (forces.py): the round's
            # mutations run at the round's POST-accrual g (forces.py's
            # g_line semantics) — step_scale × the leaky steady-tier
            # gate (frozen at low g, open by ~g+2×onset) × the
            # occasional novel 5× jump. forces.py's p_novel is a
            # per-EDGE rate (one roll per axis per evolve call spanning
            # ~DG generations); the rounds' per-round equivalent is
            # p_novel × n_gen / G_STEP_REF per axis — the "striking
            # trait", never a uniform rate (P_NOVEL_MAX 0.02 lands ~1
            # jumped axis per species).
            g_now = self._g_since_split[iid]
            scale_g = step_scale(g_now)
            steady_gate = 1.0 - math.exp(
                -max(0.0, g_now - G_STEADY_ONSET) / G_STEADY_RAMP)
            p_round = min(1.0, P_NOVEL_MAX
                          * (1.0 - math.exp(-g_now / G_NOVEL))
                          * n_gen / G_STEP_REF)
            novel = self._stream("g", f"novel:{t}:{iid}")
            for gen in range(n_gen):
                # the same round pressure re-applied before each call
                # (mutate clears the plane) — spec §4 step 1; scaled by
                # f(g) (the f(g) ramp replaces the pre-ticket flat
                # per-generation nudge). One direct uniform draw per
                # pressured scalar axis (no child streams — the
                # per-(axis,generation) child construction was the
                # commit wall-clock bottleneck at 3k+ instances).
                n_ax = 0
                for k, v in pressure.items():
                    if k in self._immutable_axes:
                        continue          # never moves (forces.py gate 0)
                    mag = v * scale_g
                    if k in self._steady_axes:
                        mag *= steady_gate
                    if p_round > 0.0 and k in self._scalar_axes \
                            and novel.uniform(gen, n_ax) < p_round:
                        mag *= NOVELTY_MULT
                    n_ax += 1
                    d.x.pressure[k] = d.x.pressure.get(k, 0.0) + mag
                self.sim.mutate(
                    d.x, self._stream("mutate", f"{t}:{iid}:{gen}"))
            self._refresh(d)

    def _f_magnitude(self, name: str, g: float) -> float:
        """Mutation magnitude ∝ f(g) for one pressured trait
        (forces.py): step_scale(g) = 1 + g/G_REF on every trait, × the
        leaky steady-tier gate (1 − exp(−(g − G_STEADY_ONSET)/
        G_STEADY_RAMP) — effectively frozen at low g, smoothly open at
        high g) on steady axes. Labile axes and plan generics (no
        registry tier) get scale only; invariant/non-mutable axes get
        0 (they must never move — matches forces.py's gate). The heavy
        tail is the caller's per-axis roll, not this scale. (The
        verdict feed inlines the same math with per-instance scale and
        gate hoisted; this helper is the single-source formulation for
        tests.)"""
        spec = self.pack.registry.axes.get(name)
        if spec is None or not spec.mutable:
            return 0.0 if spec is not None else step_scale(g)
        scale = step_scale(g)
        if spec.tier is Tier.STEADY:
            return scale * (1.0 - math.exp(
                -max(0.0, g - G_STEADY_ONSET) / G_STEADY_RAMP))
        return scale

    # ── §4 step 2: population update ─────────────────────────────────

    def _population(self, light: dict[str, np.ndarray]
                    ) -> dict[str, np.ndarray]:
        """§6 per instance × cell. Returns the per-instance s_real
        WINDOW fields (the dispersal emission gate reads mean s_real).
        The shared cell demand D(c) is accumulated window-by-window
        (bbox optimization) — the same sum the (I,H,W) einsum computed,
        in the same instance order.

        B6 §3 canopy light rides DEMOGRAPHY here, not just the verdict:
        the shade factor is dynamic (the cache is static), so the
        engine folds f_light into the demographic F before the vital
        update — s_env_eff = 1 - 2 x (F_worst x f_light). A shaded
        intolerant understory is pushed over the breakeven; the same
        cell at the same density with shade_tolerance relief stays
        under it (the verdict provenance carries the same factor, so
        selection and demography agree)."""
        live = [d for d in self.instances.values() if d.mass > 0.0]
        if not live:
            return {}
        D = np.zeros((self.ctx.H, self.ctx.W), dtype=np.float64)
        for d in live:
            D[d.world_slice()] += d.N * d.percap
        s_real: dict[str, np.ndarray] = {}
        dead = []
        for d in live:
            ws = d.world_slice()
            f_light = light.get(d.x.instance_id)
            f_worst = d.cache.f_worst[ws]
            if f_light is not None:
                f_worst = f_worst * f_light
            s_env_eff = (1.0 - 2.0 * f_worst).astype(np.float64)
            K_L = pop.lineage_capacity(self.K[ws], d.cache.U[ws])
            N1, _abandoned = pop.update_instance(
                d.N, s_env_eff, D[ws], K_L,
                d.vital.birth, d.vital.death)
            d.N = N1
            if d.mass <= 0.0:
                dead.append(d.x.instance_id)
                continue
            # trim first so the s_real window matches the instance box
            # the dispersal step will see. The light fold is re-sliced
            # at the NEW box — the factor window was computed at the
            # pre-trim box, so it is EMBEDDED to the new box (fill 1.0:
            # cells outside the old window had no N and thus no shade).
            old_box = d.box
            d.rewindow(_dressed_box(d))
            ws = d.world_slice()
            f_light = light.get(d.x.instance_id)
            f_worst = d.cache.f_worst[ws]
            if f_light is not None:
                f_light_now = _embed(f_light, old_box, d.box, 1.0)
                f_worst = f_worst * f_light_now
            s_real[d.x.instance_id] = \
                (1.0 - 2.0 * f_worst).astype(np.float64) \
                + pop.density_stress(D[ws], pop.lineage_capacity(
                    self.K[ws], d.cache.U[ws]))
        for iid in dead:
            self.retired.append(iid)
            del self.instances[iid]
        return s_real

    # ── §4 step 3: dispersal ─────────────────────────────────────────

    def _dispersal(self, t: int, s_real: dict[str, np.ndarray]) -> None:
        # transient rain expires; persistent (seed bank) decays (§7.3)
        for d in self.instances.values():
            d.rain = dsp.decay_rain(d.rain, d.view)
        # colonization-memory purge (spec §7.3 v0.6): entries older than
        # MEM_ROUNDS drop each round; deterministic sorted iteration
        for sid in sorted(self._colon_mem):
            mem = self._colon_mem[sid]
            for c in sorted(mem):
                if t - mem[c] > dsp.MEM_ROUNDS:
                    del mem[c]
        # occupancy per lineage: cell -> owning instance (§3 invariant);
        # world-grid object arrays, filled window-by-window
        owner: dict[str, np.ndarray] = {}
        for d in self.instances.values():
            o = owner.setdefault(
                d.x.species_id,
                np.full((self.ctx.H, self.ctx.W), "", dtype=object))
            y0, y1, x0, x1 = d.box
            o[y0:y1, x0:x1][d.cells] = d.x.instance_id
        # arrival rain per instance as SPARSE dicts (world (y,x) keys —
        # the packet shapes' native form; the bbox optimization keeps
        # per-instance grids windowed, never world-sized). n_new carries
        # the per-packet founded N (rule B+ founding reads it as the
        # N_new field); jump_cells tracks jump-packet landings per
        # absorbing instance (jump-originated fragments mint).
        deposits: dict[str, dict[tuple[int, int], float]] = {
            iid: {} for iid in self.instances}
        n_new: dict[str, dict[tuple[int, int], float]] = {}
        jump_cells: dict[str, set[tuple[int, int]]] = {}
        self._founded_new = {}
        foundlings: list[tuple] = []
        for iid in sorted(self.instances):
            d = self.instances[iid]
            occ = d.cells
            n_occ = int(occ.sum())
            if n_occ == 0:
                continue
            y0, y1, x0, x1 = d.box
            mean_s = float(s_real.get(iid, d.cache.s_env[y0:y1, x0:x1])
                           [occ].mean())
            E = dsp.emission(n_occ, d.view, mean_s)
            if E <= 0.0:
                continue
            pmf = dict(d.view.get("dispersal_channels") or {})
            rng = self._stream("disperse", f"{t}:{iid}")
            shares = {ch: E * w for ch, w in pmf.items() if w > 0.0}
            # packet origins (spec §7.2 v0.6): FRONTIER cells only —
            # occupied cells with an unoccupied 8-neighbor (the window
            # edge qualifies); world coords, row-major
            front = [(y + y0, x + x0) for (y, x) in dsp.frontier_cells(occ)]
            mem = self._colon_mem.setdefault(d.x.species_id, {})
            own = owner[d.x.species_id]
            pk_n = 0            # per-instance packet counter (the
                                # "establish" child's draw index)
            # jump is episodic: the share is the packet size, the rate
            # the frequency; failure redistributes to local (§7.2).
            # maybe_jump returns the (dy,dx) offset; the source cell is
            # drawn here from the FRONTIER with its own pinned stream.
            if "jump" in shares:
                off = dsp.maybe_jump(d.view, ROUND_YEARS,
                                     rng.child("jump"))
                if off is None:
                    shares["local"] = shares.get("local", 0.0) \
                        + shares.pop("jump")
                else:
                    sy, sx = front[rng.child("jump_source").randrange(
                        len(front), 0, 0)]
                    ty, tx = int(sy + off[0]), int(sx + off[1])
                    if 0 <= ty < self.ctx.H and 0 <= tx < self.ctx.W:
                        pk_n += 1
                        self._scatter_packet(
                            t, iid, "jump",
                            dsp.packet_jump_disk(
                                (ty, tx), self.ctx.H, self.ctx.W),
                            shares.pop("jump"), own, mem, d, rng, pk_n,
                            deposits, n_new, jump_cells)
                    else:
                        shares["local"] = shares.get("local", 0.0) \
                            + shares.pop("jump")
            # sustained channels: n_pk packets each, the channel share
            # divided equally, one frontier origin draw per packet
            # (spec §7.2 v0.6 — NOT per source cell)
            for ch in sorted(shares):
                share = shares[ch]
                n_pk = dsp.packet_count(n_occ)
                pk_share = share / n_pk
                pk_rng = rng.child(f"pk:{ch}")
                for k in range(n_pk):
                    pk_n += 1
                    if not front:
                        break
                    oy, ox = front[pk_rng.randrange(len(front), 0, k)]
                    if ch == "local":
                        cells = dsp.packet_local_blob(
                            (oy, ox), occ, y0, x0,
                            self.ctx.H, self.ctx.W,
                            pmf.get("local", 0.0))
                    elif ch == "wind":
                        cells = dsp.packet_wind_ray(
                            (oy, ox), self.wind_u, self.wind_v, d.view)
                    elif ch == "water":
                        marine = d.view.get("medium") == "water"
                        cells = dsp.packet_water_walk(
                            (oy, ox), self.downstream,
                            currents=(self.cur_u, self.cur_v) if marine
                            else None)
                    elif ch == "animal":
                        # one draw per packet for the disk center offset
                        # (clock=1; the origin draw was clock=0)
                        di = pk_rng.randrange(len(dsp._ANIMAL_DISK), 1, k)
                        cy = oy + dsp._ANIMAL_DISK[di][0]
                        cx = ox + dsp._ANIMAL_DISK[di][1]
                        cells = dsp.packet_animal_disk(
                            (cy, cx), self.ctx.H, self.ctx.W)
                    else:
                        continue
                    self._scatter_packet(
                        t, iid, ch, cells, pk_share, own, mem, d, rng,
                        pk_n, deposits, n_new, jump_cells)
        # arrival + founding (rule B+, spec v0.4 §7.3 — UNCHANGED; the
        # packet decision already chose WHICH cells get N): the window
        # is grown to cover the new deposits and founded cells, the
        # rain and N accumulate, then the founding rules route the
        # founded mask (contiguous spill joins / jump landings mint /
        # sustained remote landings join with the verdict gate)
        for iid in sorted(deposits):
            if iid not in self.instances:
                continue
            d = self.instances[iid]
            dep = deposits[iid]
            nn = n_new.get(iid, {})
            if dep or nn:
                ys = [k[0] for k in dep] + [k[0] for k in nn]
                xs = [k[1] for k in dep] + [k[1] for k in nn]
                d.rewindow(_union_box(
                    d.box, (min(ys), max(ys) + 1,
                            min(xs), max(xs) + 1)))
            y0, y1, x0, x1 = d.box
            arr = np.zeros_like(d.rain)
            for (y, x), val in dep.items():
                arr[y - y0, x - x0] += val
            d.rain += arr
            N_new = np.zeros_like(d.rain)
            for (y, x), val in nn.items():
                N_new[y - y0, x - x0] += val
            founded = N_new > 0.0
            if not founded.any():
                continue
            self._founded_new[iid] = nn
            # founding (rule B+, spec v0.4 §7.3) — all masks below are
            # in WINDOW coords
            # 1. contiguous spill: founded cells 8-connected to the
            #    founder THROUGH founded cells join unconditionally
            #    (physical contact = gene flow; the seed-1 stat pass
            #    showed env-gating these would block over half of
            #    normal range expansion)
            grow = d.cells.copy()
            join = np.zeros_like(founded)
            while True:
                new = founded & _dilate(grow) & ~grow
                if not new.any():
                    break
                join |= new
                grow |= new
            d.N = np.where(join, np.maximum(d.N, N_new), d.N)
            rest = founded & ~join
            if not rest.any():
                continue
            # 2. jump landings mint (episodic, no sustained flow). The
            #    minted region is the closure from jump-seeded cells
            #    THROUGH the remaining founded cells — same-round
            #    kernel-connected landings mint as ONE (vicinity
            #    absorption), one new instance per fragment. X-clones
            #    carrying the founder's CURRENT WIP genes.
            mint_region = np.zeros_like(founded)
            jc = jump_cells.get(iid)
            if jc:
                for (y, x) in jc:
                    if rest[y - y0, x - x0]:
                        mint_region[y - y0, x - x0] = True
            if mint_region.any():
                grow = mint_region.copy()
                while True:
                    new = rest & _dilate(grow) & ~grow
                    if not new.any():
                        break
                    mint_region |= new
                    grow |= new
                frags = gen.connected_components(mint_region)
                frags.sort(key=lambda m: int(m.sum()), reverse=True)
                for frag in frags:
                    nid = self._new_instance_id(
                        self._stream("found", f"{t}:{iid}"))
                    # same lineage: the foundling's g clock continues
                    # from the founder's (the gene pool split, the
                    # distance from the lineage's split ancestor is
                    # shared) — ticket 0008
                    self._g_since_split[nid] = \
                        self._g_since_split.get(iid, 0.0)
                    fx = Instance(species_id=d.x.species_id,
                                  instance_id=nid,
                                  traits=dict(d.x.traits))
                    fbox = _mask_box(frag, d.box)
                    N0 = np.where(frag, N_new, 0.0)[
                        np.s_[fbox[0] - y0:fbox[1] - y0,
                              fbox[2] - x0:fbox[3] - x0]]
                    foundlings.append((nid, d.x.species_id, N0, fx,
                                       d.cache, fbox))
            # 3. sustained-channel remote landings (rain-bridged gene
            #    flow) ALWAYS join — ranges may be non-contiguous,
            #    bridged by this round's rain. The verdict gate decides
            #    whether they join CLEANLY or incubate as a tagged
            #    divergent sub-range (div): gap between the fragment's
            #    mean s_env and the founder's density-weighted mean vs
            #    TH = DIFF_D · (1 + MOB_K · mobility). Generalists
            #    (flat stress response) pass; specialists fail and
            #    incubate. Divergent cells count toward the parent's
            #    gene pool until the §8 deferred split.
            rem = rest & ~mint_region
            if not rem.any():
                continue
            s_env_w = d.cache.s_env[y0:y1, x0:x1]
            total = d.mass
            w_mean = float((s_env_w * d.N).sum() / total) \
                if total > 0.0 else 0.0
            th = DIFF_D * (1.0 + MOB_K
                           * mobility(d.view, self.wspd[y0:y1, x0:x1],
                                      d.cells))
            for frag in gen.connected_components(rem):
                d.N = np.where(frag, np.maximum(d.N, N_new), d.N)
                gap = abs(float(s_env_w[frag].mean()) - w_mean)
                if gap > th:
                    d.div |= frag
        for nid, sid, N0, fx, fcache, fbox in foundlings:
            view = self.sim.derive(fx.traits, self.pack)
            # new instances INHERIT the founder's cache — their traits
            # start equal (§5.1); no re-evaluation
            self.instances[nid] = Dressed(
                x=fx, N=N0, rain=np.zeros_like(N0), cache=fcache,
                view=view, percap=pop.percap_demand(view),
                vital=self.sim.vital(fx.traits, self.pack),
                div=np.zeros_like(N0, dtype=bool),
                orphan=np.zeros_like(N0, dtype=bool), box=fbox)

    def _scatter_packet(self, t: int, iid: str, ch: str, cells,
                        pk_share: float, own, mem, d: Dressed,
                        rng: Stream, pk_n: int, deposits, n_new,
                        jump_cells) -> None:
        """Spec §7.2/§7.3 v0.6: ONE colonization packet of instance
        *iid* (channel *ch*, world-coord shape *cells*, budget
        *pk_share*).

        Scatter the packet's cells into the arrival rain (absorption:
        a cell already held by ANY instance of the lineage joins that
        occupant — the §3 invariant, kept exactly as before), then make
        the ONE establishment decision for the packet: it founds iff
            u < P,   P = packet_probability(mean(f_hab^beta over the
            UNOCCUPIED cells), vital.establish, ROUND_YEARS,
            in_memory)
        (u drawn from the per-instance disperse stream's "establish"
        child at (clock=0, index=pk_n) — one draw per packet, never per
        cell). On success the eligible cells (unoccupied AND f_hab >=
        EST_F_MIN — the vanguard sink cells inside a packet carry rain
        but never N) found at N = pk_share / |founded|, clipped to 1;
        on failure the packet's cells are remembered in the lineage's
        colonization memory (spec §7.3: a failed target is not
        re-attempted at full weight within MEM_ROUNDS rounds)."""
        if not cells:
            return
        val = float(pk_share) / len(cells)
        for (y, x) in cells:
            who = own[y, x]
            key = iid if who in ("", iid) else who
            dk = deposits[key]
            dk[(y, x)] = dk.get((y, x), 0.0) + val
            if ch == "jump":
                jump_cells.setdefault(key, set()).add((y, x))
        cand = [c for c in cells if own[c[0], c[1]] == ""]
        if not cand:
            return                              # fully absorbed
        mean_f = dsp.packet_mean_f(d.cache.f_worst, cand)
        in_mem = any(c in mem for c in cand)
        P = dsp.packet_probability(mean_f, d.vital.establish,
                                   ROUND_YEARS, in_mem)
        if rng.child("establish").uniform(0, pk_n) >= P:
            for c in cand:
                mem[c] = t
            return
        founded = [c for c in cand
                   if float(d.cache.f_worst[c[0], c[1]]) >= dsp.EST_F_MIN]
        if not founded:
            for c in cand:
                mem[c] = t
            return
        nv = min(1.0, float(pk_share) / len(founded))
        nn = n_new.setdefault(iid, {})
        for c in founded:
            nn[c] = nn.get(c, 0.0) + nv

    # ── §4 step 4: dressing ──────────────────────────────────────────

    def _dressing(self, t: int) -> None:
        """§8 (v0.4). Two split triggers, in order:

        1. DIVERGENT DEFERRED SPLIT (rule B+): a contiguous divergent
           sub-range (div) of at least DIFF_MIN_CELLS that is STILL
           verdict-divergent breaks off as its own instance (current
           WIP genes). Below the floor it keeps incubating inside the
           parent — slivers never mint. Dead div cells are cleared.
        2. RAIN-BRIDGE connectivity: components are computed over
           N > 0 cells UNION this round's rain — two populated regions
           stay ONE instance while the instance's own rain bridges
           them (sustained gene flow), and split when the bridge is
           lost. NOT plain 8-connectivity of N. Fragments carrying no
           N (rain-only sinks) never split off. SLIVER FLOOR (rule B+,
           symmetric with founding): a fragment below DIFF_MIN_CELLS
           stays dressed to the parent even disconnected — it may
           re-bridge next round, and if it diverges the div machinery
           handles it. HYSTERESIS (v0.4.1): a fragment at or above the
           floor mints only after the bridge stays lost for two
           CONSECUTIVE dressings — the first lost round only tags the
           fragment's cells orphan (the tag clears if the bridge
           re-establishes; slivers are pre-tagged, being chronically
           disconnected). Measured cause breakdown (seed 1, r0–r5):
           ~63% of bridge splits were same-round remote foundlings
           oscillating join/split, ~15% transient mortality carves —
           both absorbed by the grace round; ~22% chronic splits mint
           one round later. Components of different instances that
           touch stay separate.
        """
        splits: list[Dressed] = []
        for iid in sorted(self.instances):
            d = self.instances[iid]
            ws = d.world_slice()
            s_env_w = d.cache.s_env[ws]
            d.div &= d.cells
            if d.div.any():
                base = d.cells & ~d.div
                ref_mask = base if base.any() else d.cells
                ref_total = float((d.N * ref_mask).sum())
                if ref_total > 0.0:
                    ref = float(
                        (s_env_w * d.N * ref_mask).sum() / ref_total)
                    th = DIFF_D * (1.0 + MOB_K
                                   * mobility(d.view, self.wspd[ws],
                                              d.cells))
                    clear = np.zeros_like(d.div)
                    for frag in gen.connected_components(d.div):
                        if int(frag.sum()) < DIFF_MIN_CELLS:
                            continue
                        gap = abs(float(s_env_w[frag].mean()) - ref)
                        if gap <= th:
                            continue
                        nid = self._new_instance_id(
                            self._stream("divsplit", f"{t}:{iid}"))
                        self._g_since_split[nid] = \
                            self._g_since_split.get(iid, 0.0)
                        fx = Instance(species_id=d.x.species_id,
                                      instance_id=nid,
                                      traits=dict(d.x.traits))
                        # the split-off instance is its own gene pool —
                        # it starts with a CLEAN div (its whole range
                        # is "divergent" by definition) and a clean
                        # orphan record (its connectivity is fresh)
                        Nc, rainc, _divc, _orphc, fbox = _crop(d, frag)
                        splits.append(Dressed(
                            x=fx, N=Nc, rain=rainc,
                            cache=d.cache, view=d.view, percap=d.percap,
                            vital=d.vital,
                            div=np.zeros_like(Nc, dtype=bool),
                            orphan=np.zeros_like(Nc, dtype=bool),
                            box=fbox))
                        d.N = np.where(frag, 0.0, d.N)
                        d.rain = np.where(frag, 0.0, d.rain)
                        clear |= frag
                    d.div &= ~clear
            mask = d.cells | (d.rain > 0.0)
            d.orphan &= mask      # tags live only on populated cells
            comps = gen.connected_components(mask)
            if len(comps) <= 1:
                d.orphan[:] = False
                continue
            comps.sort(key=lambda m: float(d.N[m].sum()), reverse=True)
            for frag in comps[1:]:
                if float(d.N[frag].sum()) <= 0.0:
                    continue        # rain-only sink: never an instance
                if int(frag.sum()) < DIFF_MIN_CELLS:
                    # sliver floor: stays with the parent; slivers are
                    # CHRONICALLY disconnected, so they are pre-tagged
                    # orphan (they split promptly if they grow past the
                    # floor — hysteresis targets oscillation, not
                    # chronic disconnection)
                    d.orphan |= frag
                    continue
                if int((d.orphan & frag).sum()) * 2 < int(frag.sum()):
                    # HYSTERESIS (§8): the bridge was lost for the first
                    # time — the fragment keeps one grace round inside
                    # the parent. It mints only if the disconnection
                    # persists to the next dressing (or clears if the
                    # rain bridge re-establishes).
                    d.orphan |= frag
                    continue
                nid = self._new_instance_id(
                    self._stream("split", f"{t}:{iid}"))
                self._g_since_split[nid] = \
                    self._g_since_split.get(iid, 0.0)
                fx = Instance(species_id=d.x.species_id,
                              instance_id=nid,
                              traits=dict(d.x.traits))
                Nc, rainc, divc, orphc, fbox = _crop(d, frag)
                splits.append(Dressed(x=fx, N=Nc, rain=rainc,
                                      cache=d.cache, view=d.view,
                                      percap=d.percap, vital=d.vital,
                                      div=divc, orphan=orphc, box=fbox))
                # only genuinely split-off fragments leave the parent;
                # skipped slivers/sinks keep their N, rain and div
                d.N = np.where(frag, 0.0, d.N)
                d.rain = np.where(frag, 0.0, d.rain)
                d.div = np.where(frag, False, d.div)
                d.orphan = np.where(frag, False, d.orphan)
            d.orphan[comps[0]] = False   # re-bridged: the keep region
            d.rewindow(_dressed_box(d))
        for d in splits:
            self.instances[d.x.instance_id] = d

    # ── §4 step 5: commit ────────────────────────────────────────────

    def _merge_candidates(self) -> set[frozenset[str]]:
        """The engine-side spatial-contact gate (§9): same-lineage
        instance pairs whose N>0 cells 8-touch OR OVERLAP. Vectorized
        world-grid shift method for touching (the pair-by-pair rect
        test produced 100k+ candidates and dominated the commit at high
        instance counts): per lineage, an int grid of instance index
        per occupied cell; each of the 4 forward shift directions
        yields every touching unordered pair exactly once. Overlap
        needs a separate pass: the shift grid holds only ONE index per
        cell (later paints overwrite), so stacked instances — several
        instances of one lineage occupying the SAME cell — are
        invisible to it. A per-cell layer-count grid finds the overlap
        cells, then each instance reports which of them it covers."""
        by_lineage: dict[str, list[Dressed]] = {}
        for d in self.instances.values():
            by_lineage.setdefault(d.x.species_id, []).append(d)
        pairs: set[frozenset[str]] = set()
        H, W = self.ctx.H, self.ctx.W
        for sid, ds in by_lineage.items():
            if len(ds) < 2:
                continue
            who = np.full((H, W), -1, dtype=np.int32)
            layers = np.zeros((H, W), dtype=np.int16)
            for k, d in enumerate(ds):
                y0, y1, x0, x1 = d.box
                who[y0:y1, x0:x1][d.cells] = k
                layers[y0:y1, x0:x1] += d.cells
            for dy, dx in ((1, 0), (0, 1), (1, 1), (1, -1)):
                a = who[max(0, -dy):H - max(0, dy),
                        max(0, -dx):W - max(0, dx)]
                b = who[max(0, dy):H - max(0, -dy),
                        max(0, dx):W - max(0, -dx)]
                m = (a >= 0) & (b >= 0) & (a != b)
                if not m.any():
                    continue
                for key in np.unique(a[m] * len(ds) + b[m]).tolist():
                    ka, kb = divmod(key, len(ds))
                    pairs.add(frozenset((ds[ka].x.instance_id,
                                         ds[kb].x.instance_id)))
            # overlap pass: cells with >= 2 layers of THIS lineage.
            # Star topology per cell (every coverer paired with the
            # cell's first coverer): a complete graph would emit
            # ~k^2/2 pairs for one k-layer cell (the measured 1132-
            # layer hotspot = 640k frozensets from ONE cell). The
            # authority merges a survivor's partners greedily and the
            # star re-forms each round, so deep stacks collapse over a
            # few rounds; CONSOL_EVERY's complete-pair sweep does the
            # same-day full collapse.
            oy, ox = np.nonzero(layers >= 2)
            if not len(oy):
                continue
            covers: list[np.ndarray] = []
            for d in ds:
                y0, y1, x0, x1 = d.box
                in_box = (oy >= y0) & (oy < y1) & (ox >= x0) & (ox < x1)
                cov = np.zeros(len(oy), dtype=bool)
                if in_box.any():
                    cov[in_box] = d.cells[oy[in_box] - y0,
                                          ox[in_box] - x0]
                covers.append(cov)
            cov_m = np.stack(covers)          # (n_instances, n_overlap)
            for i in range(len(oy)):
                ks = np.nonzero(cov_m[:, i])[0]
                for k in ks[1:]:
                    pairs.add(frozenset((ds[ks[0]].x.instance_id,
                                         ds[k].x.instance_id)))
        return pairs

    def _commit(self, t: int) -> ChangeLog:
        views = [self.instances[iid].x.view(self.instances[iid].mass)
                 for iid in sorted(self.instances)]
        rng = self._stream("commit", str(t))
        candidates = self._merge_candidates()
        if (t + 1) % CONSOL_EVERY == 0:
            # full-lineage consolidation (spec v0.4.2 §9, the "final
            # pass" run periodically): every same-lineage pair is a
            # candidate — the authority still re-checks d < MERGE_D and
            # MERGE_GRACE, so only non-differentiated, grace-eligible
            # clusters collapse. Complete pairs per lineage: the
            # authority's greedy survivor absorbs each partner in turn,
            # collapsing the clique in one update.
            by_lineage: dict[str, list[str]] = {}
            for d in self.instances.values():
                by_lineage.setdefault(d.x.species_id, []).append(
                    d.x.instance_id)
            for ids in by_lineage.values():
                ids.sort()
                for i in range(len(ids)):
                    for j in range(i + 1, len(ids)):
                        candidates.add(frozenset((ids[i], ids[j])))
        gs = {iid: self._g_since_split.get(iid, 0.0)
              for iid in sorted(self.instances)}
        log = self.authority.update(
            views, rng, merge_candidates=candidates,
            g_since_split=gs, g_star=dict(self._g_star))
        for delta in log.instances:
            iid = delta.instance_id
            if iid not in self.instances:
                continue
            if delta.outcome is auth.Outcome.MERGE and delta.target:
                # re-key: absorbed instance's N and rain transfer to
                # the survivor (§9 re-sync); its divergent sub-range
                # tags transfer too (the cells keep incubating)
                src = self.instances.pop(iid)
                dst = self.instances.get(delta.target)
                if dst is not None:
                    ub = _union_box(dst.box, src.box)
                    dst.rewindow(ub)
                    dst.N = np.maximum(
                        dst.N, _embed(src.N, src.box, ub, 0.0))
                    dst.rain += _embed(src.rain, src.box, ub, 0.0)
                    dst.div |= _embed(src.div, src.box, ub, False)
                    dst.orphan |= _embed(src.orphan, src.box, ub, False)
            elif delta.target:
                # SUBSPECIES / SPLIT: the instance continues under the
                # new lineage node — fresh g clock from the split
                # ancestor (fauna RFC §1: d(A,B) = (g_A − g0) +
                # (g_B − g0)), and the new lineage draws its own rate
                # multiplier and g* once (ticket 0008)
                self.instances[iid].x.species_id = delta.target
                # transient diagnostic: the g at divide time (the
                # rounds' evidence for the g-currency tempo; the
                # measurement harness reads it — the clock resets
                # below, so the post-commit value would be 0)
                self._divide_g[iid] = \
                    self._g_since_split.get(iid, 0.0)
                self._g_since_split[iid] = 0.0
                if delta.target not in self._g_star:
                    self._seed_lineage(delta.target)
        # RE-SYNC: post-commit X is deprecated; re-draw via the log.
        # DRIFT RETENTION (v0.5, owner ruling "keep WIP" 2026-08-01):
        # the re-mint supplies the current lineage bookkeeping (sid,
        # record keys), but a surviving instance KEEPS its WIP genes —
        # sub-SUB_D divergence now ratchets round-over-round instead of
        # being wiped by the re-mint (measured: max instance-vs-record
        # drift 0.0000 at every round end over 20 rounds, zero
        # divides). The tree still only sees clusters >= SUB_D — no
        # micro-nodes; the authority's invariant is untouched.
        for iid in sorted(self.instances):
            fresh = self.authority.redraw(iid)
            if fresh is None:
                continue
            wip = self.instances[iid].x
            fresh.traits = wip.traits
            fresh.pressure = wip.pressure
            self.instances[iid].x = fresh
            self._refresh(self.instances[iid])
        return log

    # ── the round ────────────────────────────────────────────────────

    def round(self, t: int) -> ChangeLog:
        """One round (spec §4, steps in order). The canopy-light factor
        planes are computed ONCE at the round's entry state and shared
        by the verdict feed and the population update (both must read
        the same shade field)."""
        light = self._canopy_light_factors()
        self._verdict_feed(t, light)
        s_real = self._population(light)
        self._dispersal(t, s_real)
        self._dressing(t)
        return self._commit(t)

    def run(self, rounds: int) -> list[ChangeLog]:
        if not self.instances:
            self.genesis()
        return [self.round(t) for t in range(rounds)]

    # ── acceptance digest ────────────────────────────────────────────

    def state_json(self) -> dict:
        """The deterministic state digest (acceptance §12.1): per
        instance, lineage, cell count, mass, rain, trait digest."""
        out = {}
        for iid in sorted(self.instances):
            d = self.instances[iid]
            out[iid] = {
                "sid": d.x.species_id,
                "cells": int(d.cells.sum()),
                "mass": round(d.mass, 9),
                "rain": round(float(d.rain.sum()), 9),
                "traits": {k: d.x.traits[k] for k in sorted(d.x.traits)},
            }
        return {"seed": self.seed, "instances": out,
                "retired": sorted(self.retired),
                "reflog": len(self.authority.reflog)}


def _dilate(mask: np.ndarray) -> np.ndarray:
    """8-neighborhood dilation of a bool mask (no scipy, no wrap)."""
    p = np.pad(mask, 1)
    out = np.zeros_like(mask)
    for dy, dx in _D8:
        out |= p[1 + dy:1 + dy + mask.shape[0],
                 1 + dx:1 + dx + mask.shape[1]]
    return out
