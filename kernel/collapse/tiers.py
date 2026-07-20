"""K3 — tiers and hysteresis ladder.

Tiers govern how the player observes the world, from heat-haze crowd
fields (FIELD) through silhouettes (SILHOUETTE) to named individuals
(IDENTITY).  The `HysteresisLadder` prevents flicker: promote at ≤ d,
demote at ≥ d+ε.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class Tier(IntEnum):
    FIELD = 0
    SILHOUETTE = 1
    IDENTITY = 2


TIER_LABELS = {Tier.FIELD: "field", Tier.SILHOUETTE: "silhouette", Tier.IDENTITY: "identity"}


class HysteresisLadder:
    """Anti-flicker tier selection.

    One `promote_radius` per tier transition: moving closer than `d`
    promotes to the next tier; moving farther than `d + ε` demotes by one
    tier.  Within the hysteresis band [d, d+ε) the tier stays pinned.
    """

    def __init__(self, promote_radius: float, demote_epsilon: float) -> None:
        if promote_radius < 0 or demote_epsilon < 0:
            raise ValueError("radii and epsilon must be non-negative")
        self.promote_radius = float(promote_radius)
        self.demote_epsilon = float(demote_epsilon)

    def tier_for_distance(self, dist: float, current: Tier) -> Tier:
        d = self.promote_radius
        eps = self.demote_epsilon

        if current == Tier.FIELD:
            return Tier.SILHOUETTE if dist <= d else Tier.FIELD
        elif current == Tier.SILHOUETTE:
            if dist <= d:
                return Tier.IDENTITY
            if dist >= d + eps:
                return Tier.FIELD
            return Tier.SILHOUETTE
        else:  # IDENTITY
            if dist >= d + eps:
                return Tier.SILHOUETTE
            return Tier.IDENTITY
