"""K9 — complex: the topological data structure.

Nodes, edges, patches + committed incidence; three-state cover
(unrefined / refined-unobserved / observed); constraint sets over the
cover for latent spatial priors; subdivision (never rewire);
commit-time defect audit; versioned topology (changes are commits,
never edits).  A2 §1 made code.  Pure logic, no LLM.

Promoted from exp/k9_complex (2026-07-21, verdict: works).  The exp/
directory keeps the demo, fixtures, and tests as living documentation.
"""

from kernel.complex.cells import Complex, Edge, Node, Patch
from kernel.complex.cover import CoverState, latent_rot, summon_eligible, transition
from kernel.complex.constraints import (
    AND,
    adjacent_to_edge_kind,
    distance_band,
    evaluate,
    measure,
    sector,
)
from kernel.complex.refine import split_edge, split_patch
from kernel.complex.audit import audit
from kernel.complex.history import ComplexHistory

__all__ = [
    "Complex", "Edge", "Node", "Patch",
    "CoverState", "latent_rot", "summon_eligible", "transition",
    "AND", "adjacent_to_edge_kind", "distance_band", "evaluate",
    "measure", "sector",
    "split_edge", "split_patch", "audit", "ComplexHistory",
]
