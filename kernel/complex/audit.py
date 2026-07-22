"""Commit-time defect audit over the topological complex.

Mechanically checkable before anything generates (A2 §1.2).
Returns a list of human-readable defect strings; empty list = clean.
"""

from __future__ import annotations

import networkx as nx

from kernel.complex.cells import Complex, _segments_cross


# ---- terminus nodes ----------------------------------------------------------

# Node ids that are legitimate termini (settlements, fords, bridges, cave mouths
# are allowed to be degree-1; everything else must be degree ≥ 2). River
# sources and outlets are termini by construction (K11 worldgen).
# For the fixture we treat any node whose id contains one of these keywords
# as a legitimate terminus.
_TERMINUS_KEYWORDS = ("settlement", "ford", "bridge", "cave", "crossing",
                      "source", "outlet")


def _is_terminus(node_id: str) -> bool:
    return any(kw in node_id.lower() for kw in _TERMINUS_KEYWORDS)


# ---- audit -------------------------------------------------------------------


def audit(complex: Complex) -> list[str]:
    """Mechanical defect audit of the committed complex.

    Returns one string per defect (may be empty if clean).
    """
    defects: list[str] = []

    # 1. dangling edges
    for eid, edge in complex.edges.items():
        for nid in (edge.node_a, edge.node_b):
            if nid not in complex.nodes:
                defects.append(f"dangling_edge: {eid} references missing node {nid}")
        if edge.node_a in complex.nodes and edge.node_b in complex.nodes:
            for nid in (edge.node_a, edge.node_b):
                deg = complex.degree(nid)
                if deg == 1 and not _is_terminus(nid):
                    defects.append(
                        f"dangling_edge: degree-1 non-terminus node {nid} "
                        f"(edge {eid})"
                    )

    # 2. isolated patches — unreachable from the rest via edge/boundary adjacency.
    # Skipped when no patch commits any boundary edges (e.g. L0 worldgen,
    # where patch adjacency is raster-derived and not yet edge-committed).
    adj = complex.patch_adjacency()
    if any(adj.values()):
        visited: set[str] = set()
        start = next(iter(adj))
        stack = [start]
        while stack:
            pid = stack.pop()
            if pid in visited:
                continue
            visited.add(pid)
            stack.extend(adj.get(pid, set()) - visited)
        for pid in adj:
            if pid not in visited:
                defects.append(
                    f"isolated_patch: {pid} is unreachable via "
                    f"edge/boundary adjacency"
                )

    # 3. nodeless intersections — two edges whose polylines cross without a
    #    node at the intersection
    edge_list = list(complex.edges.values())
    for i in range(len(edge_list)):
        for j in range(i + 1, len(edge_list)):
            ei = edge_list[i]
            ej = edge_list[j]
            poly_i = ei.polyline
            poly_j = ej.polyline
            if not poly_i or not poly_j:
                continue

            # check every segment pair
            for si in range(len(poly_i) - 1):
                a0, a1 = poly_i[si], poly_i[si + 1]
                for sj in range(len(poly_j) - 1):
                    b0, b1 = poly_j[sj], poly_j[sj + 1]
                    if _segments_cross(a0, a1, b0, b1):
                        # they cross — check if there's a node at the
                        # intersection (i.e., the edges share an endpoint
                        # node that lies on the crossing segments)
                        shared_nodes = {ei.node_a, ei.node_b} & {ej.node_a, ej.node_b}
                        is_proper_node = False
                        for nid in shared_nodes:
                            npos = complex.nodes[nid].pos
                            # check if node position is one of the segment
                            # endpoints
                            if (npos == a0 or npos == a1) and (
                                npos == b0 or npos == b1
                            ):
                                is_proper_node = True
                                break
                        if not is_proper_node:
                            defects.append(
                                f"nodeless_intersection: edges {ei.id} and "
                                f"{ej.id} cross without a shared node at "
                                f"the intersection"
                            )

    # 4. disconnected components — report each beyond the first
    comps = list(nx.connected_components(complex._graph))
    if len(comps) > 1:
        for comp in comps[1:]:
            node_ids = sorted(comp)
            defects.append(
                f"disconnected_component: nodes {node_ids}"
            )

    return defects
