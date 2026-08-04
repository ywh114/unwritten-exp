"""K15 — spec §10.1 pre-genesis descent (ticket 0018).

The tail treatment: before the engine mints a species' genesis clones,
a per-species pinned roll decides whether the species "gets"
adaptation at all (most don't). If it does, the species' HARSH blobs
— the marginal tail of its viable range (high-s_env cells, plus the
clamp-bound freak-tail residual K_L < N_FLOOR·percap) — each get an
independent pinned break-off roll; a broken blob's SEEDED part (blob
∩ the species' clones) becomes a NEW INSTANCE of the SAME lineage
whose traits are descended (mutated over the engine's generation
budget) against the seeded cells' own conditions.

The descent modifies the SEEDED component ONLY (owner ruling
2026-08-02): the adapted instance covers the carved-out seeded part —
minted at founder density with the ADAPTED percap — and unseeded
harsh cells (the coverage drops; the gate's clamp residual) STAY
unseeded for §7 colonization. A blob with no seeded cells is skipped
entirely (no instance). The v3 build's "minting fresh" on unseeded
cells was rejected as contradicting the partial-coverage design.
Consequence: gate-excluded clamp cells (K_L < N_FLOOR·percap) are
never descent candidates — the eligibility gate IS the whole
freak-tail handling until a real substrate-fit (U or percap) lever
exists (none wired today: nothing pressures crown_spread_m/woodiness,
and U is not trait-pressureable; the v3 "lifted 0" was structural,
not a tuning miss).

The descent is simulation-free by construction (owner ruling
2026-08-02): the blob cells' per-requirement provenance comes from the
genesis §5.1 reduced bundle (``prov`` at the worst month, ``F_worst``,
``U``) — NOT from ``stress_adapter.evaluate`` — and the ONLY adapter
evaluate is the one per ADAPTED INSTANCE (its amended view, for its
own cache). The pressure plane is computed ONCE (compose →
FloraSim.select, the §5.2 aggregation over the instance's cells — the
blob's seeded part) and re-applied before each of the n_gen mutate
calls — no re-eval inside the loop, no steady-tier gate, no novel
tail (rounds phenomena; this is the ticket's "clean adaptation
signal").

g-earning (the rebuild's fix — the v4 build minted fragments at
g = 0, which was wrong): the fragment's g_since_split at mint is
``g_end = DES_G_FRAC · n_gen · rate_mult`` — its n_gen descent
generations × the lineage's rate multiplier (fauna RFC §1, drawn once
via k15.g), scaled by DES_G_FRAC = 3.0, the fast-tail head-start: the
tree's fast lineages (tempo p90 ≈ 187 on seed 1) clear the MEDIAN
lineage g* (500 generations) — new SPECIES candidates at the first
commit; slow trees (tempo p50 ≈ 52) stay far below the minimum g* —
SUBSPECIES candidates. Normal clones stay g = 0; the species record's
traits are NEVER modified.

Determinism (hard rule): every draw rides the species' pinned
``Stream(seed, "k15.descent", sid)`` — child streams are content-
addressed ("adapt" for the species roll, "break:{i}" per blob in the
pinned connected-components emission order, "mint:{i}" for the
instance id, "mutate:{iid}:{gen}" per generation), so draw order never
matters and the k15.genesis sequence is never perturbed. No uuid, no
random, no wall-clock reads.

Scope (owner rulings 2026-08-02): the adapted instances are ordinary
same-lineage instances to the commit machinery. NO seed_clusters, NO
genesis-time tree writes — round 0 does nothing to the tree. The
authority ranks a fragment minted with birth-g at its FIRST commit
(classify(g_end, lineage g*): ≥ g* → new SPECIES node, < g* →
SUBSPECIES node; exempt from the cluster floors, provided its
scalar-only trait distance from the orthodox record exceeds the
lineage's merge threshold — else it merges back into the parent, no
rank). The species record's traits are NEVER modified.
"""

from __future__ import annotations

import math

import numpy as np

from exp.k13_treegen.interface import StressVerdict
from exp.k15_simdiff import genesis as gen
from exp.k15_simdiff import population as pop
from kernel.hashrng import Stream
from kernel.stress.stress import compose

# ── spec §13 knobs (ticket 0018; (cal) = calibrated on seed 1) ─────────
# The species' chance at adaptation — ONE pinned roll per species.
# "Most species don't get it" (owner 2026-08-02): 0.1 → ~10/102
# species on seed 1.
P_ADAPT = 0.1
# Each harsh blob's independent chance of being broken off into a new
# adapted instance. Small by design (cal): at S_ENV_TAIL the seed-1
# tail holds ~25 blobs ≥ DESCENT_MIN_BLOB_CELLS per mintable species,
# so 0.2 keeps the adapted-instance count (and its per-instance
# evaluate cost) inside the single-digit-seconds genesis target.
P_BREAKOFF = 0.2
# The marginal tail threshold on the s_env scale: cells with s_env ≥
# S_ENV_TAIL are within 0.15 of the viability breakeven (F_worst ∈
# [0.5, 0.575]) — the range-expanding fringe. Calibrated on seed 1
# (see the design-as-built note).
S_ENV_TAIL = -0.15
# Blobs below this many cells are never broken off (fringe speckle).
# The harsh tail is a thin fringe by nature (the genesis mint floor
# this once sat below — GENESIS_MIN_CELLS — was removed by ticket
# 0039; the descent floor is now independent). Cal: 8 = meaningful-
# cluster scale.
DESCENT_MIN_BLOB_CELLS = 8
# The g-earning scale (the rebuild's fix): g_end = DES_G_FRAC ×
# n_gen × rate_mult. Settled 3.0 — the FAST-tail head-start: the
# tree's fast lineages (n_gen × rate_mult p90 ≈ 187, seed 1) × 3 ≈
# 560 clears the MEDIAN g* (500), so fast lineages rank as new SPECIES
# at the first commit, while the median tempo (p50 ≈ 52) × 3 ≈ 156
# stays below the MINIMUM g* (160.7) — slow trees land far below, as
# SUBSPECIES candidates. One round of sim at the benign clock would be
# 1.1 (the rounds' per-generation Δg = drift 1.0 + enum 0.05 + runaway
# × ornament share; the harsh blob's composed stress s ≈ 0 — the
# marginal tail is not "stressed" in the composed sense), but the
# fragment must rank at its FIRST commit, so its earned g is the
# head-start equivalent: ~3 rounds of sim time at the lineage's tempo
# (the fast tail crosses the median g* in ~3 rounds). Knob to scale;
# measured split at 3.0 (seed 1, 26 fragments): 5 above / 21 below
# the lineage g* — both ranks fire at r1.
DES_G_FRAC = 3.0


def stream(seed: int, sid: str) -> Stream:
    """The species' pinned descent stream (spec §10.1)."""
    return Stream(seed, "k15.descent", sid)


def species_adapts(seed: int, sid: str) -> bool:
    """The ONE pinned per-species roll (owner 2026-08-02): the species'
    chance at adaptation. Content-addressed child "adapt" — the roll is
    a pure function of (seed, sid)."""
    return stream(seed, sid).child("adapt").bernoulli(P_ADAPT, 0)


def blob_breaks_off(seed: int, sid: str, i: int) -> bool:
    """The per-blob pinned roll (owner 2026-08-02: "each blob has a
    pinned chance of being broken off"), blob i in the pinned
    connected-components emission order."""
    return stream(seed, sid).child(f"break:{i}").bernoulli(P_BREAKOFF, 0)


def harsh_mask(F_worst, valid, K_L, percap) -> np.ndarray:
    """The species' harsh tail (spec §10.1): the marginal band of the
    viable range (s_env ≥ S_ENV_TAIL) UNION the clamp-bound freak-tail
    residual (K_L < N_FLOOR·percap — the eligibility gate's drop set).
    The viable range is the UNGATED one (F_worst ≥ GENESIS_F ∩
    medium-valid ∩ K_L > K_EPS), so the gate-dropped cells stay in the
    mask; the engine clips each blob to the SEEDED component (owner
    ruling 2026-08-02: the descent modifies the seeded component
    only), so the gate IS the whole freak-tail handling — clamp cells
    are never candidates."""
    s_env = 1.0 - 2.0 * np.asarray(F_worst, dtype=np.float64)
    ok = ((np.asarray(F_worst, dtype=np.float64) >= gen.GENESIS_F)
          & valid & (np.asarray(K_L, dtype=np.float64) > pop.K_EPS))
    clamp = np.asarray(K_L, dtype=np.float64) < pop.N_FLOOR * percap
    return ok & ((s_env >= S_ENV_TAIL) | clamp)


def descent_n_gen(height: float) -> int:
    """The generation budget (spec §4 step 1 idiom verbatim):
    n_gen = clip(ceil(ROUND_YEARS / gen_time), 1, N_GEN_CAP) with
    gen_time = 2·sqrt(height_m) — the flora generation clock. A
    duckweed drifts per generation, an oak barely per round.
    N_GEN_CAP is engine.py's constant (400); importing it would cycle
    (the engine imports this module), so the literal is duplicated —
    keep in sync."""
    gen_time = 2.0 * math.sqrt(max(float(height), 1e-6))
    return int(min(400, max(1, math.ceil(pop.ROUND_YEARS / gen_time))))


def g_end(n_gen: int, rate_mult: float) -> float:
    """The fragment's earned g (the rebuild's fix — the v4 build minted
    fragments at g = 0): ``DES_G_FRAC × n_gen × rate_mult`` — how much
    it descended (its descent generations) × the lineage's rate
    multiplier, on the rounds' generation-time g scale (mirror the
    rounds' Δg magnitude; DES_G_FRAC = 1.1, the benign baseline). The
    engine's ``_pregenesis_descent`` mints the fragment with
    ``_g_since_split[iid] = g_end`` and reports it as the fragment's
    birth-g so the authority can classify it at the first commit.
    Normal clones stay g = 0."""
    return DES_G_FRAC * n_gen * rate_mult


def blob_verdict(bundle: dict, blob: np.ndarray, K_L: np.ndarray,
                 percap: float) -> StressVerdict:
    """The blob's ONE verdict (spec §10.1): the §5.2 aggregation over
    the blob's own cells — per requirement r, prov_r weighted by the
    parent founder density N(c) = max(F0·K_L(c), N_FLOOR·percap)/
    percap (the population that was there), the same density-weighted
    aggregation the round feed uses — then compose. NO adapter
    evaluate: the provenance is the genesis §5.1 bundle (``prov`` at
    the worst month, ``F_worst``, ``U``)."""
    Nw = gen._n_field(blob, K_L, percap).astype(np.float64)
    total = float(Nw.sum())
    agg = {bundle["names"][r]: float(
               (bundle["prov"][r] * Nw).sum() / total)
           for r in range(len(bundle["names"]))}
    res = compose(agg)
    return StressVerdict(s=res.s, provenance=res.factors)


def descend(sim, x, pressure: dict, rng: Stream, iid: str,
            ng: int) -> None:
    """The trait descent (spec §10.1): *ng* generations of mutate
    against the FIXED pressure plane — the same plane re-applied
    before each call (mutate clears it), no re-eval inside the loop,
    no steady-tier gate, no novel tail (rounds phenomena). Per-
    (instance, generation) pinned stream ``rng.child("mutate:{iid}:
    {gen}")`` — the only draws are the discrete-trait switches inside
    ``sim.mutate``. ``x`` is the new instance (record traits, fresh
    dict from ``authority.mint``); the species record is untouched."""
    for g in range(ng):
        x.pressure = dict(pressure)
        sim.mutate(x, rng.child(f"mutate:{iid}:{g}"))
