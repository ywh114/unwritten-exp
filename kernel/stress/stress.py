"""kernel/stress — organism-agnostic environmental stress math (B5 §2/§4).

The shared core of the entity/environment boundary. Per-requirement
suitabilities f in [0, 1] (1 = optimal, 0 = lethal) compose by
MULTIPLICATION into F; the emitted stress is SIGNED,
s = 1 - 2F in [-1, +1]: +1 lethal, 0 the viability breakeven (where
the vanguard sits), -1 maximal vigor (the good end keeps its
gradient — "acceptable" and "ideal" do not both read 0). The product
keeps Liebig tail-dominance: one failed non-compensable requirement
takes F to ~0.

The factor vector IS the provenance. Requirement names are ENV-defined
(the "pressure:"/"pull:"/"ley:"/"lift:" dispatch prefixes are a
contract-level convention — see exp/k13_treegen/interface.py); this
package neither defines nor interprets them. Organism-side selection
reads the vector; it never computes it.

Nothing here knows what a species, a cell, or a biome is — adapters
(K15 sim-diff) supply requirements and read results. Monthly
integration into rounds is rounds-side, not here. No RNG, no state,
no I/O: pure functions, numpy-vectorized, safe on scalars and arrays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

# ──  primitives  ──────────────────────────────────────────────────────


def sat(x):
    """Saturating clip to [0, 1]."""
    return np.clip(x, 0.0, 1.0)


def dist_suit(env, opt, breadth, weight: float = 1.0):
    """Two-sided saturating distance (B5 §4.1 shape): 1 at the optimum,
    1 - weight at |env - opt| = breadth, saturated beyond. Tolerance
    traits act by WIDENING breadth, never by moving the world's env."""
    return 1.0 - weight * sat(np.abs(env - opt) / breadth)


def shortfall_suit(value, need, ref: float = 1.0):
    """One-sided shortfall: 1 while value >= need, saturating cost as
    value drops below need (water availability vs moisture need,
    fertility vs requirement)."""
    return 1.0 - sat((need - value) / ref)


def excess_suit(value, limit, ref: float = 1.0):
    """One-sided excess: 1 while value <= limit, saturating cost above
    (waterlogging for dry plans, rooting-depth excess, salinity)."""
    return 1.0 - sat((value - limit) / ref)


def invert(f):
    """Tolerance INVERTED to a requirement (B5 §4.2 waterlogging for
    mangrove/wetland grades: the saturated end becomes what the plan
    NEEDS, dry ground the cost)."""
    return 1.0 - f


# ──  climate stratum (monthly, compensable)  ──────────────────────────

# Global default pair (B5 §7 settled Q2: per-plan [niche] metadata may
# override; the pair only shapes T<->P compensability — breadths carry
# sensitivity).
W_T_DEFAULT = 0.5
W_P_DEFAULT = 0.5


def climate_suit(t_c, p_mm, opt_t: float, breadth_t: float,
                 opt_p: float, breadth_p: float,
                 w_t: float = W_T_DEFAULT, w_p: float = W_P_DEFAULT):
    """Monthly climate suitability: 1 - (w_T·sat(dT/B_T) + w_P·sat(dP/B_P))
    clipped to [0, 1]. t_c/p_mm are the month's fields (any shape);
    opts/breadths are record-side scalars. Phenology gating (which
    months count for which plan) is adapter logic, not here."""
    return sat(1.0 - (w_t * sat(np.abs(t_c - opt_t) / breadth_t)
                      + w_p * sat(np.abs(p_mm - opt_p) / breadth_p)))


# ──  composition  ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class StressResult:
    """One composed verdict: the signed stress, the suitability product,
    and the factor vector (provenance). factors maps requirement name
    -> suitability in [0, 1]; F is their product; s = 1 - 2F."""

    s: float
    F: float
    factors: Mapping[str, float] = field(default_factory=dict)


def compose(factors: Mapping[str, float]) -> StressResult:
    """Multiply per-requirement suitabilities into F and emit the
    signed stress. An empty factor vector means "nothing is wrong
    anywhere" -> F = 1 -> s = -1 (maximal vigor)."""
    F = 1.0
    for f in factors.values():
        F *= f
    return StressResult(s=1.0 - 2.0 * F, F=F, factors=dict(factors))
