"""Clean and defect-variant L0 fixtures for K9 demo and tests.

Both are deterministic — built the same way every call, with fixed
positions, ids, and fields.  The defect variant adds one dangling edge,
one isolated patch, and one nodeless intersection for the audit demo.
"""

from __future__ import annotations

from kernel.complex.cells import Complex, Edge, Node, Patch
from kernel.gmm_dynamics.dynamics import DriftField


def build_clean_complex() -> Complex:
    """A small L0 complex: 7 nodes, 12 edges, 5 patches.

    Layout (approximate, all coords 0–10):
      ford (0,10) ── river (e0) ── northeast (10,10)
         │                              │
      path (e5)                     path (e1)
         │                              │
      bridge (0,5)                crossroads (10,5)
         │                              │
      path (e4)                     path (e2)
         │                              │
      southwest (0,0) ── river (e3) ── southeast (10,0)

    Plus radial roads from settlement (5,5) to each outer node.
    """
    nodes = [
        Node(id="ford", pos=(0.0, 10.0)),
        Node(id="northeast", pos=(10.0, 10.0)),
        Node(id="crossroads", pos=(10.0, 5.0)),
        Node(id="southeast", pos=(10.0, 0.0)),
        Node(id="southwest", pos=(0.0, 0.0)),
        Node(id="bridge", pos=(0.0, 5.0)),
        Node(id="settlement", pos=(5.0, 5.0)),
    ]

    edges = [
        Edge(
            id="e_road_ford", node_a="settlement", node_b="ford",
            length=7.0710678, kind="road", quality=0.9,
        ),
        Edge(
            id="e_road_ne", node_a="settlement", node_b="northeast",
            length=7.0710678, kind="road", quality=0.9,
        ),
        Edge(
            id="e_road_cross", node_a="settlement", node_b="crossroads",
            length=5.0, kind="road", quality=0.9,
        ),
        Edge(
            id="e_road_se", node_a="settlement", node_b="southeast",
            length=7.0710678, kind="road", quality=0.9,
        ),
        Edge(
            id="e_road_sw", node_a="settlement", node_b="southwest",
            length=7.0710678, kind="road", quality=0.9,
        ),
        Edge(
            id="e_road_bridge", node_a="settlement", node_b="bridge",
            length=5.0, kind="road", quality=0.9,
        ),
        Edge(
            id="e_river_north", node_a="ford", node_b="northeast",
            length=10.0, kind="river", quality=0.6,
            polyline=(
                (0.0, 10.0), (3.0, 9.0), (7.0, 11.0), (10.0, 10.0),
            ),
        ),
        Edge(
            id="e_path_right", node_a="northeast", node_b="crossroads",
            length=5.0, kind="path", quality=0.3,
            polyline=((10.0, 10.0), (10.0, 7.5), (10.0, 5.0)),
        ),
        Edge(
            id="e_path_right_low", node_a="crossroads", node_b="southeast",
            length=5.0, kind="path", quality=0.3,
        ),
        Edge(
            id="e_river_south", node_a="southeast", node_b="southwest",
            length=10.0, kind="river", quality=0.6,
            polyline=(
                (10.0, 0.0), (7.0, 1.0), (3.0, -1.0), (0.0, 0.0),
            ),
        ),
        Edge(
            id="e_path_low", node_a="southwest", node_b="bridge",
            length=5.0, kind="path", quality=0.3,
        ),
        Edge(
            id="e_path_left", node_a="bridge", node_b="ford",
            length=5.0, kind="path", quality=0.3,
            polyline=((0.0, 5.0), (0.0, 7.5), (0.0, 10.0)),
        ),
    ]

    patches = [
        Patch(
            id="north_field",
            field=DriftField(mu=(0.0, 2.0), theta=(0.1, 0.1), sigma=(0.5, 0.5)),
            boundary_edges=("e_road_ford", "e_river_north", "e_road_ne"),
            measure=25.0,
        ),
        Patch(
            id="east_wood",
            field=DriftField(mu=(2.0, 0.0), theta=(0.2, 0.1), sigma=(0.3, 0.3)),
            boundary_edges=("e_road_ne", "e_path_right", "e_road_cross"),
            measure=12.5,
        ),
        Patch(
            id="south_east_wood",
            field=DriftField(mu=(2.0, -1.0), theta=(0.2, 0.1), sigma=(0.3, 0.3)),
            boundary_edges=("e_road_cross", "e_path_right_low", "e_road_se"),
            measure=12.5,
        ),
        Patch(
            id="south_meadow",
            field=DriftField(mu=(0.0, -2.0), theta=(0.2, 0.2), sigma=(0.5, 0.5)),
            boundary_edges=("e_road_se", "e_river_south", "e_road_sw"),
            measure=25.0,
        ),
        Patch(
            id="west_pasture",
            field=DriftField(mu=(-1.0, 0.0), theta=(0.2, 0.2), sigma=(0.4, 0.4)),
            boundary_edges=(
                "e_road_sw", "e_path_low", "e_path_left", "e_road_ford",
            ),
            measure=25.0,
        ),
    ]

    return Complex(nodes=nodes, edges=edges, patches=patches)  # type: ignore[arg-type]


def build_defect_complex() -> Complex:
    """Variant with 3 seeded defect classes for audit demo."""
    # Start from clean, then add defects
    c = build_clean_complex()

    # 1. dangling edge — references non-existent node "ghost" and creates
    #    a degree-1 non-terminus node
    nodes = dict(c.nodes)
    edges = dict(c.edges)
    patches = dict(c.patches)

    # add a node "spur" at (5, 8) that is not a terminus
    nodes["spur"] = Node(id="spur", pos=(5.0, 8.0))

    # add edge from settlement to spur (settlement already has degree > 1,
    # but spur will be degree 1 and non-terminus)
    edges["e_dangle"] = Edge(
        id="e_dangle", node_a="settlement", node_b="ghost_missing",
        length=3.0, kind="path", quality=0.1,
    )

    # 2. isolated patch — no adjacency to others
    patches["isolated_island"] = Patch(
        id="isolated_island",
        field=DriftField(mu=(3.0, 3.0), theta=(0.1, 0.1), sigma=(0.3, 0.3)),
        boundary_edges=(),  # no shared edges — isolated
        measure=5.0,
    )

    # 3. nodeless intersection — add two edges with crossing polylines
    #    that do NOT share a node at the intersection
    edges["e_cross_1"] = Edge(
        id="e_cross_1", node_a="northeast", node_b="southwest",
        length=14.142, kind="path", quality=0.1,
        polyline=(
            (10.0, 10.0), (7.0, 7.0), (3.0, 3.0), (0.0, 0.0),
        ),
    )
    edges["e_cross_2"] = Edge(
        id="e_cross_2", node_a="ford", node_b="southeast",
        length=14.142, kind="path", quality=0.1,
        polyline=(
            (0.0, 10.0), (3.0, 7.0), (7.0, 3.0), (10.0, 0.0),
        ),
    )

    return Complex(
        nodes=list(nodes.values()),
        edges=list(edges.values()),
        patches=list(patches.values()),
    )
