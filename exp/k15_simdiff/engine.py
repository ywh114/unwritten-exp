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
from exp.k13_treegen.interface import (ChangeLog, Instance, StressVerdict,
                                       VitalRates)
from exp.k13_treegen.model import Rank, Tree
from exp.k15_simdiff import authority as auth
from exp.k15_simdiff import dispersal as dsp
from exp.k15_simdiff import genesis as gen
from exp.k15_simdiff import population as pop
from exp.k15_simdiff import stress_adapter as sa
from kernel.hashrng import Stream
from kernel.stress.stress import compose

FLORA_CONTENT = Path("exp/k13_treegen/content/flora")

# ── spec §13 knobs not owned by the sub-modules ───────────────────────
ROUND_YEARS = pop.ROUND_YEARS      # the T in every per-round conversion
N_GEN_CAP = 400                    # mutate calls per round cap (§4)
RE_EVAL_D = 0.15                   # cache invalidation distance (§5.1)
EST_F_MIN = dsp.EST_F_MIN          # establishment gate (settled 0.3)
SRC_CAP = 64                       # per-instance dispersal source cap

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

    # ── ids and streams ──────────────────────────────────────────────

    def _new_instance_id(self, rng: Stream) -> str:
        self._clone_counter += 1
        return f"i{rng.u64(0, self._clone_counter):012x}"

    def _stream(self, stage: str, key: str) -> Stream:
        return Stream(self.seed, f"k15.{stage}", key)

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
            rng = self._stream("genesis", f"mint:{pid}")
            shared = None
            for i, clone in enumerate(seeds[pid]):
                iid = self._new_instance_id(rng)
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

    def _verdict_feed(self, t: int) -> None:
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
            res = compose(agg)
            verdict = StressVerdict(s=res.s, provenance=res.factors)
            pressure = self.sim.select(verdict, d.x.traits, self.pack)
            height = float(d.view.get("height_m") or 0.0)
            gen_time = 2.0 * math.sqrt(max(height, 1e-6))
            n_gen = int(min(N_GEN_CAP,
                            max(1, math.ceil(ROUND_YEARS / gen_time))))
            for g in range(n_gen):
                # the same round pressure re-applied before each call
                # (mutate clears the plane) — spec §4 step 1
                for k, v in pressure.items():
                    d.x.pressure[k] = d.x.pressure.get(k, 0.0) + v
                self.sim.mutate(
                    d.x, self._stream("mutate", f"{t}:{iid}:{g}"))
            self._refresh(d)

    # ── §4 step 2: population update ─────────────────────────────────

    def _population(self) -> dict[str, np.ndarray]:
        """§6 per instance × cell. Returns the per-instance s_real
        WINDOW fields (the dispersal emission gate reads mean s_real).
        The shared cell demand D(c) is accumulated window-by-window
        (bbox optimization) — the same sum the (I,H,W) einsum computed,
        in the same instance order."""
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
            K_L = pop.lineage_capacity(self.K[ws], d.cache.U[ws])
            N1, _abandoned = pop.update_instance(
                d.N, d.cache.s_env[ws], D[ws], K_L,
                d.vital.birth, d.vital.death)
            d.N = N1
            if d.mass <= 0.0:
                dead.append(d.x.instance_id)
                continue
            # trim first so the s_real window matches the instance box
            # the dispersal step will see
            d.rewindow(_dressed_box(d))
            ws = d.world_slice()
            s_real[d.x.instance_id] = d.cache.s_env[ws] \
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
        # the deposit kernels' native form; the bbox optimization keeps
        # per-instance grids windowed, never world-sized)
        deposits: dict[str, dict[tuple[int, int], float]] = {
            iid: {} for iid in self.instances}
        # jump-channel deposit cells per absorbing instance (rule B+:
        # jump landings mint; sustained-channel landings join)
        jump_cells: dict[str, set[tuple[int, int]]] = {}
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
            # world-coord source list (the kernels index world fields)
            srcs_w = np.argwhere(occ) + (y0, x0)
            # jump is episodic: the share is the packet size, the rate
            # the frequency; failure redistributes to local (§7.2).
            # maybe_jump returns the (dy,dx) offset; the source cell is
            # drawn here with its own pinned stream (dispersal note 4).
            if "jump" in shares:
                off = dsp.maybe_jump(d.view, ROUND_YEARS,
                                     rng.child("jump"))
                if off is None:
                    shares["local"] = shares.get("local", 0.0) \
                        + shares.pop("jump")
                else:
                    k = rng.child("jump_source").randrange(len(srcs_w),
                                                           0, 0)
                    sy, sx = srcs_w[k]
                    ty, tx = int(sy + off[0]), int(sx + off[1])
                    if 0 <= ty < self.ctx.H and 0 <= tx < self.ctx.W:
                        shares["jump"] = (shares.pop("jump"), (ty, tx))
                    else:
                        shares["local"] = shares.get("local", 0.0) \
                            + shares.pop("jump")
            # per-source kernels (wind/water/animal) take (N,2) cell
            # lists and deposit per source; the engine subsamples the
            # source set to SRC_CAP evenly-spaced cells (row-major,
            # deterministic) and conserves the channel budget: each
            # selected source carries share_E / n_sel (spec §7.2's
            # deposit pattern with a bounded per-instance cost).
            n_src = len(srcs_w)
            n_sel = min(n_src, SRC_CAP)
            sel = srcs_w[np.linspace(0, n_src - 1, n_sel).astype(int)] \
                if n_sel < n_src else srcs_w
            for ch in sorted(shares):
                share = shares[ch]
                if ch == "local":
                    # padded window so the spill is not clipped at the
                    # window edge; keys shifted back to world coords
                    dep = dsp.deposit_local(np.pad(occ, 2), share,
                                            pmf.get("local", 0.0))
                    dep = {(y + y0 - 2, x + x0 - 2): v
                           for (y, x), v in dep.items()}
                elif ch == "wind":
                    dep = dsp.deposit_wind(sel, share / n_sel,
                                           self.wind_u,
                                           self.wind_v, d.view)
                elif ch == "water":
                    marine = d.view.get("medium") == "water"
                    dep = dsp.deposit_water(
                        sel, share / n_sel, self.downstream,
                        currents=(self.cur_u, self.cur_v) if marine
                        else None)
                elif ch == "animal":
                    dep = dsp.deposit_animal(sel, share / n_sel)
                elif ch == "jump":
                    val, (ty, tx) = share
                    dep = {(ty, tx): val}
                else:
                    continue
                # absorption: rain of L landing in a cell occupied by
                # ANOTHER instance of L joins the occupant (§3);
                # out-of-grid keys are dropped (dispersal note 5)
                own = owner[d.x.species_id]
                for (y, x), val in dep.items():
                    if not (0 <= y < self.ctx.H and 0 <= x < self.ctx.W):
                        continue
                    who = own[y, x]
                    key = iid if who in ("", iid) else who
                    deposits[key][(y, x)] = \
                        deposits[key].get((y, x), 0.0) + val
                    if ch == "jump":
                        jump_cells.setdefault(key, set()).add((y, x))
        # arrival + establishment (§7.3): the window is grown to cover
        # the new deposits, then one vectorized gate call per instance
        # over the window; occupancy is the same-lineage mask
        for iid in sorted(deposits):
            if iid not in self.instances:
                continue
            d = self.instances[iid]
            dep = deposits[iid]
            if dep:
                ys = [k[0] for k in dep]
                xs = [k[1] for k in dep]
                d.rewindow(_union_box(
                    d.box, (min(ys), max(ys) + 1, min(xs), max(xs) + 1)))
            y0, y1, x0, x1 = d.box
            arr = np.zeros_like(d.rain)
            for (y, x), val in dep.items():
                arr[y - y0, x - x0] += val
            d.rain += arr
            if not (arr > 0.0).any():
                continue
            occupied = owner[d.x.species_id][y0:y1, x0:x1] != ""
            N_new, founded = dsp.establish(
                arr, d.cache.f_worst[y0:y1, x0:x1], occupied,
                d.vital.establish, ROUND_YEARS,
                self._stream("establish", f"{t}:{iid}"))
            if not founded.any():
                continue
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
        log = self.authority.update(
            views, rng, merge_candidates=candidates)
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
                # new lineage node
                self.instances[iid].x.species_id = delta.target
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
        """One round (spec §4, steps in order)."""
        self._verdict_feed(t)
        s_real = self._population()
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
