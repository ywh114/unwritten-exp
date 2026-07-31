"""K15 engine — spec §6 population update (pure functions + constants).

The rounds' density term, vital update and extinction floor: every knob
is a named module constant (spec §13), every function is pure and
numpy-vectorized per cell; the engine loops per instance (Python loop —
instance counts are small, house style) and passes the per-instance N
field, the SHARED cell demand D(c), the per-lineage capacity K_L(c),
the cached env stress s_env(c) and the vital rates.

Single T-conversion policy (spec §4): per-year rates convert to the
per-round effect by CONTINUOUS compounding — the vital update is
N' = N · exp((growth − mort) · ROUND_YEARS), never (1 + rate)^T.

Spec §6 design constraint (self-check; also unit-tested): sustained
s_real = 0.3 must give density half-life ≥ 5 rounds at DIE_K = 0.002,
T = ROUND_YEARS = 100.  With only the stress-mortality term live,
N' = N · exp(−DIE_K·0.3·T) per round, so the half-life is
    n = ln 2 / (DIE_K · 0.3 · T) = ln 2 / (0.002 · 0.3 · 100) ≈ 11.6
rounds ≥ 5.  (The v0.1 default violated its own constraint; the
continuous form above is the settled one — v0.2 critic finding.)
"""

from __future__ import annotations

import math

import numpy as np

# ── spec §13 knobs (v0.3, settled values) ──────────────────────────────
ROUND_YEARS = 100.0     # years per round (the T in exp(·T))
BIOMASS_REF = 25.0      # per-capita demand normalization (m²·wood)
PROD_CAP_SCALE = 1.0    # productivity → capacity scale
DENS_C = 0.5            # density-term coefficient
DENS_CAP = 2.0          # density-term clip
K_EPS = 1e-6            # capacity below this counts as none
VIG_K = 0.5             # vigor → bscale cap (1 + VIG_K)
DIE_K = 0.002           # stress mortality (/yr; §6 half-life constraint)
N_FLOOR = 0.01          # cell extinction floor


def percap_demand(view: dict) -> float:
    """Per-capita space demand (spec §6): crown_spread_m² · (1 +
    woodiness) / BIOMASS_REF. Reads the DerivedView keys the adapter
    exposes (crown_spread_m, woodiness); a plan without a crown carries
    no space demand (missing/None keys → 0)."""
    crown = float(view.get("crown_spread_m") or 0.0)
    wood = float(view.get("woodiness") or 0.0)
    return crown * crown * (1.0 + wood) / BIOMASS_REF


def cell_demand(N_stack: np.ndarray, percap: np.ndarray) -> np.ndarray:
    """Cell demand D(c) = Σ_instances N_i(c)·percap_i (spec §6).

    *N_stack*: (I,H,W) — the engine's stack of per-instance N fields;
    *percap*: (I,) — per-instance percap_demand values. Returns (H,W)
    float64. Per-cell vectorized; the per-instance loop is the caller's."""
    return np.einsum("ihw,i->hw", N_stack, percap)


def lineage_capacity(productivity: np.ndarray, U) -> np.ndarray:
    """Per-lineage capacity K_L(c) = PROD_CAP_SCALE · productivity(c) ·
    U_L(c) — the §5.1 substrate share U splits the cell's capacity
    BETWEEN lineages by where each can actually root (spec §6 v0.3
    owner ruling; water plans pass U = 1, the whole cell's capacity).

    *productivity* is the RAW annual productivity raster (pre-scale:
    PROD_CAP_SCALE is applied here, the stat-pass convention)."""
    return PROD_CAP_SCALE * np.asarray(productivity) \
        * np.asarray(U, dtype=np.float64)


def density_stress(D, K_L) -> np.ndarray:
    """Density term (spec §6): s_dens = clip(DENS_C · D / K_L, 0,
    DENS_CAP), with K_L ≤ K_EPS and D > 0 → DENS_CAP (no usable
    capacity: the cell is saturated for this lineage). D is the v1
    SHARED cell demand — all instances in the cell, weighted by the
    same U_L; the per-pair patch-overlap refinement is deferred.
    Vectorized; returns float64."""
    D = np.asarray(D, dtype=np.float64)
    K_L = np.asarray(K_L, dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(D > 0.0, DENS_C * D / np.maximum(K_L, K_EPS), 0.0)
    s = np.clip(s, 0.0, DENS_CAP)
    return np.where((K_L <= K_EPS) & (D > 0.0), DENS_CAP, s)


def bscale(s_real) -> np.ndarray:
    """Growth gate bscale = clip(1 − s_real, 0, 1 + VIG_K) (spec §6).
    Negative s_real is opportunity, never immortality: it raises growth
    through bscale but never lowers mort below the baseline rate (the
    baseline lives in vital_update's mort term, not here). Vectorized."""
    return np.clip(1.0 - np.asarray(s_real, dtype=np.float64),
                   0.0, 1.0 + VIG_K)


def vital_update(N, s_env, D, K_L, birth: float, death: float) -> np.ndarray:
    """One (instance, cell) vital update (spec §6): density term from
    the shared cell demand D and the per-lineage capacity K_L, then the
    continuous-compounding update
        s_real = s_env + s_dens
        growth = birth · clip(1 − s_real, 0, 1 + VIG_K)
        mort   = death + DIE_K · max(s_real, 0)
        N'     = clip(N · exp((growth − mort) · T), 0, 1)
    All fields per cell ((H,W) or broadcastable), float64 in/out. The
    extinction floor is a separate step (extinction_floor / update_instance)."""
    s_real = np.asarray(s_env, dtype=np.float64) + density_stress(D, K_L)
    growth = birth * bscale(s_real)
    mort = death + DIE_K * np.maximum(s_real, 0.0)
    N1 = np.clip(np.asarray(N, dtype=np.float64)
                 * np.exp((growth - mort) * ROUND_YEARS), 0.0, 1.0)
    return N1


def extinction_floor(N1) -> tuple[np.ndarray, np.ndarray]:
    """Extinction floor (spec §6): N < N_FLOOR → cell abandoned (N = 0;
    rain keeps flowing). Returns (N_clean, abandoned) — *abandoned* is
    the per-cell bool mask of cells dropped THIS round; an instance
    whose cells all hit the floor is retired (the engine checks
    ``not abandoned.any()`` / all cells zero — the floor itself only
    reports the mask)."""
    N1 = np.asarray(N1, dtype=np.float64)
    abandoned = N1 < N_FLOOR
    return np.where(abandoned, 0.0, N1), abandoned


def update_instance(N, s_env, D, K_L, birth: float, death: float,
                    ) -> tuple[np.ndarray, np.ndarray]:
    """The full §6 per-instance × cell update in one call: density term,
    vital update, extinction floor. Returns (N_next, abandoned) — see
    vital_update and extinction_floor."""
    N1 = vital_update(N, s_env, D, K_L, birth, death)
    return extinction_floor(N1)


def density_half_life_rounds(s_real: float = 0.3) -> float:
    """Rounds to halve N under sustained stress-only mortality
    (spec §6 design constraint): ln 2 / (DIE_K · s_real · T)."""
    return math.log(2.0) / (DIE_K * s_real * ROUND_YEARS)
