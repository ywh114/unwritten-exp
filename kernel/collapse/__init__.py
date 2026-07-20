"""K3 — collapse: measurement semantics.

Crowd fields (K2 GMMs with expected-count weights) collapse through
tiers — field → silhouettes → identities — deterministically and
auditably, under the filtration invariant: coarse collapse commits facts
that every finer collapse must honour.  Coarsening relaxes individuals
back into distributions on exit (demotion policy: schedule-snap for
scheduled entities, last-position for transients — see
docs/spec-notes/2026-07-19-k3-demotion-policy.md).

Promoted from exp/k3_collapse (2026-07-19, verdict: works).  The exp/
directory keeps the demo, fixtures, and tests as living documentation.
"""

from kernel.collapse.field import (
    Silhouette,
    Resident,
    Identity,
    presence_count,
    absence_renormalize,
    collapse_field,
    refine_identity,
    coarsen,
)
from kernel.collapse.geometry import Rect, rect_mass
from kernel.collapse.tiers import Tier, TIER_LABELS, HysteresisLadder
from kernel.collapse.log import CollapseLog, CollapseRecord, digest_draws

__all__ = [
    "Silhouette", "Resident", "Identity",
    "Rect", "rect_mass",
    "presence_count", "absence_renormalize",
    "collapse_field", "refine_identity", "coarsen",
    "Tier", "TIER_LABELS", "HysteresisLadder",
    "CollapseLog", "CollapseRecord", "digest_draws",
]
