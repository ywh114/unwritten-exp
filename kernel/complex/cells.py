"""Cells and the committed topological complex.

Nodes (0-cells), Edges (1-cells), Patches (2-cells), and the `Complex`
that binds them via incidence relations.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import networkx as nx

from kernel.gmm_dynamics.dynamics import DriftField

# ---- cells -------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    """0-cell: settlement, crossroads, ford, bridge, cave mouth.

    `pos` is Euclidean (x, y); used for spatial queries and the
    nodeless-intersection defect check.
    """
    id: str
    pos: tuple[float, float]


@dataclass(frozen=True)
class Edge:
    """1-cell: road, path, navigable river.

    Arc length s ∈ [0, L].  `polyline` is used ONLY for the
    self-intersection defect check; dynamics (K8) use arc length.
    """
    id: str
    node_a: str
    node_b: str
    length: float
    kind: str          # "road" | "path" | "river"
    quality: float
    polyline: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True)
class Patch:
    """2-cell: a terrain region carrying one OU drift field.

    `boundary_edges` is a tuple of edge ids that enclose the region.
    `measure` is its area-equivalent.
    `parent` is set by subdivision (None for L0 cells).
    """
    id: str
    field: DriftField
    boundary_edges: tuple[str, ...]
    measure: float
    parent: str | None = None


# ---- complex -----------------------------------------------------------------


def _segments_cross(a0, a1, b0, b1):
    """2-D segment-intersection test (orientation-based).

    Returns True when segments (a0,a1) and (b0,b1) cross in the open
    sense (endpoint overlap is NOT a cross).
    """
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1 = orient(a0, a1, b0)
    o2 = orient(a0, a1, b1)
    o3 = orient(b0, b1, a0)
    o4 = orient(b0, b1, a1)

    if o1 == 0.0 or o2 == 0.0 or o3 == 0.0 or o4 == 0.0:
        return False  # endpoint touches — proper intersection only
    return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)


class Complex:
    """Committed topological structure: nodes, edges, patches + incidence.

    Provides neighbours, shared-boundary lookup, and graph-distance BFS.
    """

    __slots__ = ("nodes", "edges", "patches", "_graph")

    def __init__(
        self,
        nodes: list[Node],
        edges: list[Edge],
        patches: list[Patch],
    ) -> None:
        self.nodes: dict[str, Node] = {n.id: n for n in nodes}
        self.edges: dict[str, Edge] = {e.id: e for e in edges}
        self.patches: dict[str, Patch] = {p.id: p for p in patches}
        self._build_graph()

    def _build_graph(self) -> None:
        self._graph = nx.Graph()
        for nid in self.nodes:
            self._graph.add_node(nid)
        for eid, edge in self.edges.items():
            self._graph.add_edge(
                edge.node_a, edge.node_b, weight=edge.length, edge_id=eid,
            )

    # -- incidence queries -----------------------------------------------------

    def neighbors(self, node_id: str) -> list[str]:
        """Adjacent node ids along any edge."""
        return list(self._graph.neighbors(node_id))

    def patch_at(self, patch_id: str) -> Patch:
        return self.patches[patch_id]

    def shared_boundary(self, p1_id: str, p2_id: str) -> set[str]:
        """Edge ids shared by two patches (empty set if not adjacent)."""
        e1 = set(self.patches[p1_id].boundary_edges)
        e2 = set(self.patches[p2_id].boundary_edges)
        return e1 & e2

    def graph_distance(self, a: str, b: str) -> float:
        """Shortest-path length (sum of edge lengths) between nodes, or inf."""
        try:
            return nx.shortest_path_length(self._graph, a, b, weight="weight")
        except nx.NetworkXNoPath:
            return float("inf")

    def degree(self, node_id: str) -> int:
        return self._graph.degree(node_id)

    def nodes_of_edge(self, edge_id: str) -> tuple[str, str]:
        edge = self.edges[edge_id]
        return (edge.node_a, edge.node_b)

    def patch_adjacency(self) -> dict[str, set[str]]:
        """Patch-id -> set of patch-ids sharing a boundary edge."""
        edge_to_patches: dict[str, set[str]] = {}
        for pid, patch in self.patches.items():
            for eid in patch.boundary_edges:
                edge_to_patches.setdefault(eid, set()).add(pid)
        adj: dict[str, set[str]] = {pid: set() for pid in self.patches}
        for eid, pset in edge_to_patches.items():
            for p in pset:
                adj[p] |= pset - {p}
        return adj

    # -- utility ---------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Complex):
            return NotImplemented
        if (
            self.nodes != other.nodes
            or self.edges != other.edges
            or self.patches.keys() != other.patches.keys()
        ):
            return False
        for pid in self.patches:
            sp = self.patches[pid]
            op = other.patches[pid]
            if (
                sp.id != op.id
                or sp.boundary_edges != op.boundary_edges
                or sp.measure != op.measure
                or sp.parent != op.parent
            ):
                return False
            # Compare DriftFields by value (DriftField has no __eq__)
            sf, of = sp.field, op.field
            if (
                not np.allclose(sf.mu, of.mu)
                or not np.allclose(sf.theta, of.theta)
                or not np.allclose(sf.sigma, of.sigma)
            ):
                return False
        return True

    def __repr__(self) -> str:
        return (
            f"Complex(nodes={len(self.nodes)}, edges={len(self.edges)}, "
            f"patches={len(self.patches)})"
        )
