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
    sees it). N and rain are (H,W) float64; rain is the transient
    propagule deposit (spec §3 two-density accounting). div is a bool
    mask tagging the instance's DIVERGENT sub-range (rule B+, spec
    v0.4 §7.3): cells that joined despite failing the verdict gate —
    they count toward the parent's gene pool while incubating and
    split off only when a contiguous divergent region reaches
    DIFF_MIN_CELLS and is still divergent (§8)."""

    x: Instance
    N: np.ndarray
    rain: np.ndarray
    cache: CachedFields
    view: dict
    percap: float
    vital: VitalRates
    div: np.ndarray

    @property
    def cells(self) -> np.ndarray:
        return self.N > 0.0

    @property
    def mass(self) -> float:
        return float(self.N.sum())


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
        record's genes verbatim — mint makes no draws)."""
        seeds = gen.genesis_rain(self.pack, self.sim, self.ctx, self.K,
                                 self.seed)
        for pid in sorted(seeds):
            sid = self._order_sid[pid]
            rng = self._stream("genesis", f"mint:{pid}")
            for i, clone in enumerate(seeds[pid]):
                iid = self._new_instance_id(rng)
                x = self.authority.mint(sid, iid, rng.child(str(i)))
                view = self.sim.derive(x.traits, self.pack)
                self.instances[iid] = Dressed(
                    x=x, N=clone.N.astype(np.float64),
                    rain=np.zeros_like(clone.N, dtype=np.float64),
                    cache=self._evaluate_cache(view, x.traits), view=view,
                    percap=pop.percap_demand(view),
                    vital=self.sim.vital(x.traits, self.pack),
                    div=np.zeros(clone.N.shape, dtype=bool))

    # ── §4 step 1: verdict feed ──────────────────────────────────────

    def _verdict_feed(self, t: int) -> None:
        for iid in sorted(self.instances):
            d = self.instances[iid]
            total = d.mass
            if total <= 0.0:
                continue
            agg = {d.cache.names[r]: float(
                       (d.cache.prov[r] * d.N).sum() / total)
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
        fields (the dispersal emission gate reads mean s_real)."""
        live = [d for d in self.instances.values() if d.mass > 0.0]
        if not live:
            return {}
        N_stack = np.stack([d.N for d in live])
        percap = np.array([d.percap for d in live])
        D = pop.cell_demand(N_stack, percap)
        s_real: dict[str, np.ndarray] = {}
        dead = []
        for d in live:
            K_L = pop.lineage_capacity(self.K, d.cache.U)
            N1, _abandoned = pop.update_instance(
                d.N, d.cache.s_env, D, K_L,
                d.vital.birth, d.vital.death)
            d.N = N1
            s_real[d.x.instance_id] = d.cache.s_env \
                + pop.density_stress(D, K_L)
            if d.mass <= 0.0:
                dead.append(d.x.instance_id)
        for iid in dead:
            self.retired.append(iid)
            del self.instances[iid]
        return s_real

    # ── §4 step 3: dispersal ─────────────────────────────────────────

    def _dispersal(self, t: int, s_real: dict[str, np.ndarray]) -> None:
        # transient rain expires; persistent (seed bank) decays (§7.3)
        for d in self.instances.values():
            d.rain = dsp.decay_rain(d.rain, d.view)
        # occupancy per lineage: cell -> owning instance (§3 invariant)
        owner: dict[str, np.ndarray] = {}
        for d in self.instances.values():
            o = owner.setdefault(d.x.species_id,
                                 np.full(d.N.shape, "", dtype=object))
            o[d.cells] = d.x.instance_id
        deposits: dict[str, np.ndarray] = {
            iid: np.zeros_like(d.N) for iid, d in self.instances.items()}
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
            mean_s = float(s_real.get(iid, d.cache.s_env)[occ].mean())
            E = dsp.emission(n_occ, d.view, mean_s)
            if E <= 0.0:
                continue
            pmf = dict(d.view.get("dispersal_channels") or {})
            rng = self._stream("disperse", f"{t}:{iid}")
            shares = {ch: E * w for ch, w in pmf.items() if w > 0.0}
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
                    srcs = np.argwhere(occ)
                    k = rng.child("jump_source").randrange(len(srcs),
                                                           0, 0)
                    sy, sx = srcs[k]
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
            srcs = np.argwhere(occ)
            n_src = len(srcs)
            n_sel = min(n_src, SRC_CAP)
            sel = srcs[np.linspace(0, n_src - 1, n_sel).astype(int)] \
                if n_sel < n_src else srcs
            for ch in sorted(shares):
                share = shares[ch]
                if ch == "local":
                    dep = dsp.deposit_local(occ, share,
                                            pmf.get("local", 0.0))
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
                    deposits[key][y, x] += val
                    if ch == "jump":
                        jump_cells.setdefault(key, set()).add((y, x))
        # arrival + establishment (§7.3): one vectorized gate call per
        # instance over full grids; occupancy is the same-lineage mask
        for iid in sorted(deposits):
            if iid not in self.instances:
                continue
            d = self.instances[iid]
            arr = deposits[iid]
            d.rain += arr
            if not (arr > 0.0).any():
                continue
            occupied = owner[d.x.species_id] != ""
            N_new, founded = dsp.establish(
                arr, d.cache.f_worst, occupied, d.vital.establish,
                ROUND_YEARS, self._stream("establish", f"{t}:{iid}"))
            if not founded.any():
                continue
            # founding (rule B+, spec v0.4 §7.3)
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
                    if rest[y, x]:
                        mint_region[y, x] = True
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
                    foundlings.append((nid, d.x.species_id,
                                       np.where(frag, N_new, 0.0), fx,
                                       d.cache))
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
            total = d.mass
            w_mean = float((d.cache.s_env * d.N).sum() / total) \
                if total > 0.0 else 0.0
            th = DIFF_D * (1.0 + MOB_K
                           * mobility(d.view, self.wspd, d.cells))
            for frag in gen.connected_components(rem):
                d.N = np.where(frag, np.maximum(d.N, N_new), d.N)
                gap = abs(float(d.cache.s_env[frag].mean()) - w_mean)
                if gap > th:
                    d.div |= frag
        for nid, sid, N0, fx, fcache in foundlings:
            view = self.sim.derive(fx.traits, self.pack)
            # new instances INHERIT the founder's cache — their traits
            # start equal (§5.1); no re-evaluation
            self.instances[nid] = Dressed(
                x=fx, N=N0, rain=np.zeros_like(N0),
                cache=fcache, view=view,
                percap=pop.percap_demand(view),
                vital=self.sim.vital(fx.traits, self.pack),
                div=np.zeros_like(N0, dtype=bool))

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
           handles it. Components of different instances that touch
           stay separate.
        """
        splits: list[Dressed] = []
        for iid in sorted(self.instances):
            d = self.instances[iid]
            d.div &= d.cells
            if d.div.any():
                base = d.cells & ~d.div
                ref_mask = base if base.any() else d.cells
                ref_total = float((d.N * ref_mask).sum())
                if ref_total > 0.0:
                    ref = float(
                        (d.cache.s_env * d.N * ref_mask).sum() / ref_total)
                    th = DIFF_D * (1.0 + MOB_K
                                   * mobility(d.view, self.wspd, d.cells))
                    clear = np.zeros_like(d.div)
                    for frag in gen.connected_components(d.div):
                        if int(frag.sum()) < DIFF_MIN_CELLS:
                            continue
                        gap = abs(float(d.cache.s_env[frag].mean()) - ref)
                        if gap <= th:
                            continue
                        nid = self._new_instance_id(
                            self._stream("divsplit", f"{t}:{iid}"))
                        fx = Instance(species_id=d.x.species_id,
                                      instance_id=nid,
                                      traits=dict(d.x.traits))
                        # the split-off instance is its own gene pool —
                        # it starts with a CLEAN div (its whole range
                        # is "divergent" by definition)
                        splits.append(Dressed(
                            x=fx, N=np.where(frag, d.N, 0.0),
                            rain=np.where(frag, d.rain, 0.0),
                            cache=d.cache, view=d.view, percap=d.percap,
                            vital=d.vital,
                            div=np.zeros_like(d.div)))
                        d.N = np.where(frag, 0.0, d.N)
                        d.rain = np.where(frag, 0.0, d.rain)
                        clear |= frag
                    d.div &= ~clear
            mask = d.cells | (d.rain > 0.0)
            comps = gen.connected_components(mask)
            if len(comps) <= 1:
                continue
            comps.sort(key=lambda m: float(d.N[m].sum()), reverse=True)
            keep = comps[0]
            for frag in comps[1:]:
                if float(d.N[frag].sum()) <= 0.0:
                    continue        # rain-only sink: never an instance
                if int(frag.sum()) < DIFF_MIN_CELLS:
                    continue        # sliver floor: stays with the parent
                nid = self._new_instance_id(
                    self._stream("split", f"{t}:{iid}"))
                fx = Instance(species_id=d.x.species_id,
                              instance_id=nid,
                              traits=dict(d.x.traits))
                Nf = np.where(frag, d.N, 0.0)
                rainf = np.where(frag, d.rain, 0.0)
                splits.append(Dressed(x=fx, N=Nf, rain=rainf,
                                      cache=d.cache, view=d.view,
                                      percap=d.percap, vital=d.vital,
                                      div=np.where(frag, d.div, False)))
                d.N = np.where(keep, d.N, 0.0)
                d.rain = np.where(keep, d.rain, 0.0)
                d.div = np.where(keep, d.div, False)
        for d in splits:
            self.instances[d.x.instance_id] = d

    # ── §4 step 5: commit ────────────────────────────────────────────

    def _merge_candidates(self) -> set[frozenset[str]]:
        """The engine-side spatial-contact gate (§9): same-lineage
        instance pairs whose N>0 cells 8-touch."""
        by_lineage: dict[str, list[Dressed]] = {}
        for d in self.instances.values():
            by_lineage.setdefault(d.x.species_id, []).append(d)
        pairs: set[frozenset[str]] = set()
        for sid, ds in by_lineage.items():
            if len(ds) < 2:
                continue
            for i in range(len(ds)):
                dil = _dilate(ds[i].cells)
                for j in range(i + 1, len(ds)):
                    if (dil & ds[j].cells).any():
                        pairs.add(frozenset((ds[i].x.instance_id,
                                             ds[j].x.instance_id)))
        return pairs

    def _commit(self, t: int) -> ChangeLog:
        views = [self.instances[iid].x.view(self.instances[iid].mass)
                 for iid in sorted(self.instances)]
        rng = self._stream("commit", str(t))
        log = self.authority.update(
            views, rng, merge_candidates=self._merge_candidates())
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
                    dst.N = np.maximum(dst.N, src.N)
                    dst.rain += src.rain
                    dst.div |= src.div
            elif delta.target:
                # SUBSPECIES / SPLIT: the instance continues under the
                # new lineage node
                self.instances[iid].x.species_id = delta.target
        # RE-SYNC: post-commit X is deprecated; re-draw via the log
        for iid in sorted(self.instances):
            fresh = self.authority.redraw(iid)
            if fresh is None:
                continue
            fresh.pressure = self.instances[iid].x.pressure
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
