"""Composable spatial constraint predicates over patches.

Evaluated against the complex + cover.  These are the input type for
latent spatial priors (C5's placement solve).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from kernel.complex.cells import Complex


# ---- constraint objects ------------------------------------------------------

# A constraint is a callable that takes a Complex and returns a set[str] of
# patch ids that satisfy it.


@dataclass(frozen=True)
class _Sector:
    """Patches whose centroid falls in a band of the map extent.

    `direction` is projected from `origin`; a patch qualifies when its
    centroid's scalar projection onto `direction`, normalised by the
    furthest projection of any patch centroid, falls in [lo, hi).
    """
    origin: tuple[float, float]
    direction: tuple[float, float]
    lo: float
    hi: float

    def __call__(self, complex: Complex) -> set[str]:
        dx, dy = self.direction
        ox, oy = self.origin

        # collect all patch centroids
        centroids = _patch_centroids(complex)
        if not centroids:
            return set()

        # normalisation: max scalar projection
        projections = {
            pid: (cx - ox) * dx + (cy - oy) * dy
            for pid, (cx, cy) in centroids.items()
        }
        max_proj = max(abs(v) for v in projections.values()) or 1.0

        result: set[str] = set()
        for pid, proj in projections.items():
            frac = proj / max_proj
            if self.lo <= frac < self.hi:
                result.add(pid)
        return result


@dataclass(frozen=True)
class _AdjacentToEdgeKind:
    """Patches sharing at least one boundary edge of the given kind."""
    kind: str

    def __call__(self, complex: Complex) -> set[str]:
        result: set[str] = set()
        for pid, patch in complex.patches.items():
            for eid in patch.boundary_edges:
                edge = complex.edges.get(eid)
                if edge is not None and edge.kind == self.kind:
                    result.add(pid)
                    break
        return result


@dataclass(frozen=True)
class _DistanceBand:
    """Patches whose graph distance from `node_id` falls in [min_d, max_d)."""
    node_id: str
    min_d: float
    max_d: float

    def __call__(self, complex: Complex) -> set[str]:
        result: set[str] = set()
        for nid in complex.nodes:
            d = complex.graph_distance(self.node_id, nid)
            if self.min_d <= d < self.max_d:
                # all patches bounded by edges incident to this node
                for pid, patch in complex.patches.items():
                    for eid in patch.boundary_edges:
                        edge = complex.edges[eid]
                        if edge.node_a == nid or edge.node_b == nid:
                            result.add(pid)
        return result


@dataclass(frozen=True)
class _AND:
    """Intersection of constraints."""
    constraints: tuple

    def __call__(self, complex: Complex) -> set[str]:
        if not self.constraints:
            return set()
        result = self.constraints[0](complex)
        for c in self.constraints[1:]:
            result &= c(complex)
        return result


# ---- public constructors -----------------------------------------------------


def sector(
    origin: tuple[float, float],
    direction: tuple[float, float],
    fraction: float,
) -> _Sector:
    """Patches in the named fraction band of the map extent.

    `fraction` ∈ (0, 1]; a single float means [0, fraction), so e.g.
    `sector((0,0), (0,1), 0.33)` selects the southern third.
    For the northern third use `fraction=0.33` with the origin at the
    south edge and the full [0, 0.33) band; or wrap with a complement
    later if needed.
    """
    return _Sector(origin, direction, 0.0, fraction)


def adjacent_to_edge_kind(kind: str) -> _AdjacentToEdgeKind:
    """Patches sharing a boundary edge of the given kind."""
    return _AdjacentToEdgeKind(kind)


def distance_band(node_id: str, min_d: float, max_d: float) -> _DistanceBand:
    """Patches in the graph-distance band [min_d, max_d) from a node."""
    return _DistanceBand(node_id, min_d, max_d)


def AND(*constraints: _Sector | _AdjacentToEdgeKind | _DistanceBand | _AND) -> _AND:
    """Intersection of constraints."""
    return _AND(constraints)


# ---- evaluation --------------------------------------------------------------


def evaluate(constraint, complex: Complex) -> set[str]:
    """Evaluate a constraint against the complex → set of patch ids."""
    return constraint(complex)


def measure(complex: Complex, cells: set[str]) -> float:
    """Total measure of a set of patches."""
    return sum(complex.patch_at(cid).measure for cid in cells)


# ---- internal helpers --------------------------------------------------------


def _patch_centroids(complex: Complex) -> dict[str, tuple[float, float]]:
    """Compute each patch's centroid from its boundary-edge polylines.

    Uses the arithmetic mean of all polyline vertices of boundary edges
    as a proxy centroid (exact for convex polygons with known boundary).
    """
    centroids: dict[str, tuple[float, float]] = {}
    for pid, patch in complex.patches.items():
        xs: list[float] = []
        ys: list[float] = []
        for eid in patch.boundary_edges:
            edge = complex.edges[eid]
            for x, y in edge.polyline:
                xs.append(x)
                ys.append(y)
            # also include endpoints
            na = complex.nodes[edge.node_a]
            nb = complex.nodes[edge.node_b]
            xs.extend([na.pos[0], nb.pos[0]])
            ys.extend([na.pos[1], nb.pos[1]])
        if xs:
            centroids[pid] = (float(np.mean(xs)), float(np.mean(ys)))
        else:
            centroids[pid] = (0.0, 0.0)
    return centroids
