"""Subdivision — never rewire.

L1 refining L0 = subdivision where every fine cell knows its parent.
Refinement may subdivide, never rewire: existing edges' endpoints and
existing patches' incidence are immutable.
"""

from __future__ import annotations

from typing import Any

from kernel.complex.cells import Complex, Edge, Node, Patch


# ---- commit shape ------------------------------------------------------------


def _point_on_polyline(pos, polyline, tol: float = 1e-9) -> bool:
    """True when `pos` lies on any segment of the polyline (within tol)."""
    def _on_segment(p, a, b) -> bool:
        cross = (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])
        if abs(cross) > tol:
            return False
        dot = (p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])
        if dot < -tol:
            return False
        sq = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2
        return dot <= sq + tol

    return any(
        _on_segment(pos, polyline[i], polyline[i + 1])
        for i in range(len(polyline) - 1)
    )


def split_patch(
    complex: Complex,
    patch_id: str,
    children: list[tuple[Any, float]],  # (DriftField, measure)
    new_edges: list[Edge],
) -> dict:
    """Subdivide a patch into children + detail edges.

    Returns a commit dict for ComplexHistory.  Children get `parent=patch_id`.
    Child measures must sum to the parent's (tolerance 1e-9).
    New detail edges live inside the parent's boundary.
    """
    parent = complex.patches.get(patch_id)
    if parent is None:
        raise KeyError(f"patch {patch_id!r} not found")

    child_sum = sum(m for _, m in children)
    if abs(child_sum - parent.measure) > 1e-9:
        raise ValueError(
            f"Child measures {child_sum} do not sum to parent measure "
            f"{parent.measure} for patch {patch_id!r}"
        )

    # create child patch ids
    child_patches: list[dict] = []
    for i, (field, meas) in enumerate(children):
        child_patches.append({
            "id": f"{patch_id}.{i}",
            "field_mu": field.mu.tolist(),
            "field_theta": field.theta.tolist(),
            "field_sigma": field.sigma.tolist(),
            "measure": meas,
            "parent": patch_id,
            "boundary_edges": list(parent.boundary_edges),  # default: inherit
        })

    commit: dict = {
        "type": "split_patch",
        "patch_id": patch_id,
        "children": child_patches,
    }

    # New detail edges reference nodes that must already exist in the
    # complex (add them first); anything else would be a rewire.
    existing_nodes = set(complex.nodes)
    for e in new_edges:
        for nid in (e.node_a, e.node_b):
            if nid not in existing_nodes:
                raise ValueError(
                    f"New edge {e.id!r} references node {nid!r} which is "
                    f"not in the complex.  Add the node before splitting."
                )

    commit["new_edges"] = [
        {
            "id": e.id,
            "node_a": e.node_a,
            "node_b": e.node_b,
            "length": e.length,
            "kind": e.kind,
            "quality": e.quality,
            "polyline": list(e.polyline),
        }
        for e in new_edges
    ]

    return commit


def split_edge(
    complex: Complex,
    edge_id: str,
    at_s: float,
    new_node: Node,
) -> dict:
    """Insert a node on an edge, producing two child edges.

    Returns a commit dict.  The new node goes at arc-length s=`at_s`.
    Produces edges `{edge_id}.0` (a → new) and `{edge_id}.1` (new → b).
    """
    edge = complex.edges.get(edge_id)
    if edge is None:
        raise KeyError(f"edge {edge_id!r} not found")

    L = edge.length
    if not 0.0 < at_s < L:
        raise ValueError(
            f"split point at_s={at_s} must be in (0, {L}) for edge {edge_id!r}"
        )

    # The new node must not already be in the complex (or if it is, it's
    # a different semantics — we just require the id to be new).
    if new_node.id in complex.nodes:
        raise ValueError(
            f"Node {new_node.id!r} already exists in the complex"
        )

    # The new node must lie ON the edge's polyline (within tolerance) —
    # the defect audit's node-at-intersection contract depends on it.
    if edge.polyline and not _point_on_polyline(new_node.pos, edge.polyline):
        raise ValueError(
            f"new_node position {new_node.pos} does not lie on edge "
            f"{edge_id!r}'s polyline"
        )

    child_a_length = at_s
    child_b_length = L - at_s

    commit: dict = {
        "type": "split_edge",
        "edge_id": edge_id,
        "at_s": at_s,
        "new_node": {"id": new_node.id, "pos": list(new_node.pos)},
        "child_a": {
            "id": f"{edge_id}.0",
            "node_a": edge.node_a,
            "node_b": new_node.id,
            "length": child_a_length,
            "kind": edge.kind,
            "quality": edge.quality,
            "polyline": list(edge.polyline),  # inherited (approximate)
        },
        "child_b": {
            "id": f"{edge_id}.1",
            "node_a": new_node.id,
            "node_b": edge.node_b,
            "length": child_b_length,
            "kind": edge.kind,
            "quality": edge.quality,
            "polyline": list(edge.polyline),
        },
    }
    return commit
