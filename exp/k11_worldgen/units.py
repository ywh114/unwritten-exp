"""K11 — units: the fixed mapping from normalized pipeline fields to
physical quantities.

The pipeline produces normalized fields (temperature 0..1,
precipitation 0..1, elevation 0..1 around a sea level).  This module
is the ONLY place those become metric values; classifiers downstream
(biomes, later ecology) are written against real-world parameters
(degC, mm/month, meters).  The mapping itself is never a tuning knob:
if a world needs a different biome mix, adjust the generation
gradients/variation, never the units.
"""

from __future__ import annotations

import numpy as np

# temperature: 0.0 -> -30 degC, 1.0 -> +35 degC (per-month values)
T_MIN_C, T_MAX_C = -30.0, 35.0
# precipitation: 0.0 -> 0 mm/month, 1.0 -> 400 mm/month
P_MAX_MM = 400.0
# elevation: sea level -> 0 m, normalized 1.0 -> +6000 m,
# normalized 0.0 (deepest ocean) -> -6000 m; linear per segment.
# Abyssal plains run 4-5 km, trenches 6-11 km in reality — 6000 m
# keeps generated trench floors in the Mariana neighborhood instead
# of capping them shallow.
ELEV_MAX_M, DEPTH_MAX_M = 6000.0, 6000.0


# salinity: grams per kg (practical salinity). Open ocean 35,
# fresh < 1, brackish 1..30, hypersaline terminals up to ~340 (Dead Sea)
SALINITY_OCEAN_GKG = 35.0


def temp_c(t_norm: np.ndarray) -> np.ndarray:
    return t_norm * (T_MAX_C - T_MIN_C) + T_MIN_C


def precip_mm(p_norm: np.ndarray) -> np.ndarray:
    return p_norm * P_MAX_MM


def elev_m(e_norm: np.ndarray, sea_level: float) -> np.ndarray:
    """Meters relative to sea level (negative below)."""
    above = (e_norm - sea_level) / (1.0 - sea_level) * ELEV_MAX_M
    below = (e_norm - sea_level) / sea_level * DEPTH_MAX_M
    return np.where(e_norm >= sea_level, above, below)


def alt_m(e_norm: np.ndarray, sea_level: float) -> np.ndarray:
    """Meters above sea level, clipped at 0 (terrain altitude)."""
    return np.maximum(elev_m(e_norm, sea_level), 0.0)


def hand_m(hand_norm: np.ndarray, sea_level: float) -> np.ndarray:
    """Height above nearest drainage, meters."""
    return hand_norm / (1.0 - sea_level) * ELEV_MAX_M
