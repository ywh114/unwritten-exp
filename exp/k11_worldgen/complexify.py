"""K11 — derive a K9 Complex from the generated raster.

The world is a graph wearing a heightmap (A2 §1.1): generation happens
on the raster, then the route/drainage structure is extracted into the
committed complex — rivers → edges (arc-length polylines), sources,
confluences and outlets → nodes, biome regions → patches.

Rivers are sized: each edge's `quality` carries its mean width class
(1–3 by discharge) along the walked path. Endpoints are sane by
construction — sources are headwaters or lake outlets (carrying the
lake's inflow via through-lake accumulation), sinks are ocean or lake
inlets.

This is L0-sketch fidelity: patches carry empty boundary_edges (their
adjacency is raster-derived at L0 and becomes edge-committed at L1 —
noted in the README spec-notes).
"""

from __future__ import annotations

import numpy as np

from kernel.gmm_dynamics.dynamics import DriftField
from kernel.complex.cells import Complex, Edge, Node, Patch

from exp.k11_worldgen.hydrology import _D8


def _river_nodes(hydro: dict) -> dict[tuple[int, int], str]:
    """Classify special river cells: sources, confluences, outlets."""
    river = hydro["river_mask"]
    direction = hydro["flow_dir"]
    acc = hydro["accumulation"]
    H, W = river.shape
    kinds: dict[tuple[int, int], str] = {}
    for y in range(H):
        for x in range(W):
            if not river[y, x]:
                continue
            upstream = 0
            for dy, dx in _D8:
                ny, nx_ = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx_ < W and river[ny, nx_]:
                    d = direction[ny, nx_]
                    if d >= 0 and (ny + _D8[d][0], nx_ + _D8[d][1]) == (y, x):
                        upstream += 1
            d = direction[y, x]
            down_is_water = False
            if d >= 0:
                ny, nx_ = y + _D8[d][0], x + _D8[d][1]
                down_is_water = hydro["ocean_mask"][ny, nx_] or hydro["lake_mask"][ny, nx_]
            if upstream == 0:
                kinds[(y, x)] = "source"
            elif upstream >= 2:
                kinds[(y, x)] = "confluence"
            if down_is_water or d < 0:
                kinds[(y, x)] = "outlet"
    return kinds


def derive_complex(hydro: dict, biome_map: np.ndarray, biome_names: list[str]) -> Complex:
    """Extract nodes/edges from the river network and patches from biome
    connected components. Deterministic (pure function of the raster)."""
    river = hydro["river_mask"]
    direction = hydro["flow_dir"]
    kinds = _river_nodes(hydro)

    nodes: list[Node] = []
    node_id_of: dict[tuple[int, int], str] = {}
    for i, ((y, x), kind) in enumerate(sorted(kinds.items())):
        nid = f"{kind}:{i:03d}"
        node_id_of[(y, x)] = nid
        nodes.append(Node(id=nid, pos=(float(x), float(y))))

    # edges: walk downstream from each node until the next node.
    # Diagonal steps are expanded through a corner cell (lower w first):
    # two anti-diagonals in one cell would geometrically cross without a
    # node (a raster artifact the K9 audit flags as nodeless_intersection).
    w_surf = hydro["w"]

    def corner(y, x, ny, nx_):
        c1, c2 = (ny, x), (y, nx_)
        return c1 if w_surf[c1] <= w_surf[c2] else c2

    edges: list[Edge] = []
    seen_starts: set[tuple] = set()
    for (sy, sx), kind in sorted(kinds.items()):
        # follow the downstream direction until the next node
        path = [(sy, sx)]
        y, x = sy, sx
        while len(path) <= 2 * river.shape[0] * river.shape[1]:  # cycle guard
            d = direction[y, x]
            if d < 0:
                break
            dy, dx = _D8[d]
            ny, nx_ = y + dy, x + dx
            if not (0 <= ny < river.shape[0] and 0 <= nx_ < river.shape[1]):
                break
            if dy != 0 and dx != 0:
                path.append(corner(y, x, ny, nx_))
            if (ny, nx_) in node_id_of:
                path.append((ny, nx_))
                a = node_id_of[path[0]]
                b = node_id_of[path[-1]]
                if a != b and (a, b) not in seen_starts:
                    seen_starts.add((a, b))
                    pl = tuple((float(px), float(py)) for py, px in path)
                    mean_w = float(np.mean([hydro["width"][py, px]
                                            for py, px in path]))
                    edges.append(Edge(
                        id=f"river:{len(edges):03d}",
                        node_a=a, node_b=b,
                        length=float(len(path) - 1),
                        kind="river", quality=mean_w, polyline=pl,
                    ))
                break
            if not river[ny, nx_]:
                break
            path.append((ny, nx_))
            y, x = ny, nx_

    # patches: 4-connected same-biome components, min size 16
    patches: list[Patch] = []
    H, W = biome_map.shape
    seen = np.zeros_like(biome_map, dtype=bool)
    for sy in range(H):
        for sx in range(W):
            if seen[sy, sx]:
                continue
            biome = biome_map[sy, sx]
            comp = []
            stack = [(sy, sx)]
            while stack:
                y, x = stack.pop()
                if seen[y, x] or biome_map[y, x] != biome:
                    continue
                seen[y, x] = True
                comp.append((y, x))
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    ny, nx_ = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx_ < W and not seen[ny, nx_]:
                        stack.append((ny, nx_))
            if len(comp) < 16:
                continue
            cy = float(np.mean([p[0] for p in comp]))
            cx = float(np.mean([p[1] for p in comp]))
            patches.append(Patch(
                id=f"patch:{biome_names[biome]}:{len(patches):03d}",
                field=DriftField(mu=(cx, cy), theta=(0.1, 0.1), sigma=(1.0, 1.0)),
                boundary_edges=(),
                measure=float(len(comp)),
            ))

    return Complex(nodes, edges, patches)
