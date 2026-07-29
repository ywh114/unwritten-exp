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


def derive_river_complex(hydro: dict) -> tuple[list[Node], list[Edge]]:
    """Extract river nodes/edges from a hydro-style dict (river_mask,
    flow_dir, width, w, ocean_mask, lake_mask). Shared by the annual
    complex (derive_complex) and the monthly networks: the SAME
    extraction machinery runs once per month on that month's mask, so
    seasonal rivers are the same kind of artifact — new seasonal
    sources/confluences/outlets included.

    River polylines stay GRID-TRUE here on purpose: the committed
    complex is the audit-checked artifact, and jittered copies of shared
    corridor cells would drift apart and read as nodeless intersections.
    The cosmetic de-gridding (seeded wiggle against D8 diagonal lock)
    happens at rasterization time — deliver.river_raster."""
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
                    mean_w = float(np.mean([hydro["width"][py, px]
                                            for py, px in path]))
                    # outlet mouth EXTENSION: the polyline must not stop
                    # at the last river cell's corner — carry it one
                    # step into the downstream water cell so the stamp
                    # visibly reaches the waterline (the water mask
                    # clips the underwater part at render)
                    ey_, ex_ = path[-1]
                    if kinds.get((ey_, ex_)) == "outlet":
                        d2 = direction[ey_, ex_]
                        if d2 >= 0:
                            my_, mx_ = ey_ + _D8[d2][0], ex_ + _D8[d2][1]
                            if (0 <= my_ < river.shape[0]
                                    and 0 <= mx_ < river.shape[1]
                                    and (hydro["ocean_mask"][my_, mx_]
                                         or hydro["lake_mask"][my_, mx_])):
                                if d2 in (0, 2, 5, 7):
                                    path.append(corner(ey_, ex_, my_, mx_))
                                path.append((my_, mx_))
                    pl = tuple((float(px), float(py)) for py, px in path)
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
    return nodes, edges


def derive_complex(hydro: dict, biome_map: np.ndarray,
                   biome_names: list[str]) -> tuple[Complex, dict]:
    """Extract nodes/edges from the river network and patches from biome
    connected components. Deterministic (pure function of the raster).

    Returns (Complex, edge_monthly): the month-aware complex and the
    per-edge monthly width classes (12 ints per edge id, 0 = dry that
    month). Without monthly discharge fields (synthetic climates) the
    river part is annual-only and edge_monthly is empty."""
    if ("discharge_monthly" in hydro
            and "river_threshold_monthly" in hydro):
        nodes, edges, edge_monthly = derive_river_complex_m(hydro)
    else:
        nodes, edges = derive_river_complex(hydro)
        edge_monthly = {}

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

    return Complex(nodes, edges, patches), edge_monthly


def _monthly_classes(polyline: tuple, dis_m: np.ndarray,
                     thr_m: np.ndarray, drop_last: bool
                     ) -> tuple[int, ...]:
    """Per-month width class (0-3) for an edge, from the max monthly
    discharge along its own path cells. The shared end-node cell is
    excluded (drop_last) — its discharge belongs to the joined
    downstream, not to this edge alone."""
    cells = [(int(py), int(px)) for px, py in polyline]
    if drop_last and len(cells) > 1:
        cells = cells[:-1]
    out = []
    for m in range(12):
        t = float(thr_m[m])
        if t <= 1e-9:               # no water this month: dry
            out.append(0)
            continue
        dmax = max((float(dis_m[m][y, x]) for y, x in cells), default=0.0)
        out.append(3 if dmax >= 30 * t else
                   2 if dmax >= 6 * t else
                   1 if dmax >= t else 0)
    return tuple(out)


def derive_river_complex_m(hydro: dict) -> tuple[list, list, dict]:
    """The month-aware river complex: ONE network.

    Base (annual) edges come from derive_river_complex and each
    carries a per-month width class from its own monthly discharge —
    edges change class by month, never location. Seasonal water
    (cells clearing a month's discharge threshold OUTSIDE the base
    network) is extracted into seasonal edges with the same node
    vocabulary: a segment that touches the base network joins it —
    splitting the base edge at a new confluence node when the join is
    mid-edge — and a segment that dies on dry land floats (seasonal
    outlet). Floating is allowed; contradicting the base network is
    not: seasonal cells are by construction exactly the cells the base
    network does not use, and every join is a node.

    Also writes the per-cell monthly products (river_width_monthly,
    river_monthly, river_perm) back into hydro — derived from the
    edge state, not from independent per-cell thresholds.
    """
    river = hydro["river_mask"]
    direction = hydro["flow_dir"]
    lake, ocean = hydro["lake_mask"], hydro["ocean_mask"]
    dis_m = hydro["discharge_monthly"]
    thr_m = hydro["river_threshold_monthly"]
    H, W = river.shape

    nodes, edges = derive_river_complex(hydro)
    node_id_of = {(int(n.pos[1]), int(n.pos[0])): n.id for n in nodes}
    # next free index per node kind. Base ids use the GLOBAL extraction
    # index (sparse per kind — outlet:005, outlet:023, ...), so the
    # next free id must come from the max existing suffix, never from
    # a per-kind COUNT (which collides and silently overwrites nodes
    # in the Complex's id-keyed dict)
    kind_next: dict[str, int] = {}
    for n in nodes:
        kind, num = n.id.split(":")
        kind_next[kind] = max(kind_next.get(kind, 0), int(num) + 1)

    edge_monthly: dict[str, tuple[int, ...]] = {}
    for e in edges:
        edge_monthly[e.id] = _monthly_classes(e.polyline, dis_m, thr_m,
                                              drop_last=True)

    cell_on_edge: dict[tuple[int, int], list[tuple[str, int]]] = {}
    for e in edges:
        for idx, (px, py) in enumerate(e.polyline):
            cell_on_edge.setdefault((int(py), int(px)), []).append((e.id, idx))

    w_surf = hydro["w"]

    def corner(y, x, ny, nx_):
        c1, c2 = (ny, x), (y, nx_)
        return c1 if w_surf[c1] <= w_surf[c2] else c2

    def ensure_node(y, x, kind):
        if (y, x) in node_id_of:
            return node_id_of[(y, x)]
        nid = f"{kind}:{kind_next.get(kind, 0):03d}"
        kind_next[kind] = kind_next.get(kind, 0) + 1
        nodes.append(Node(id=nid, pos=(float(x), float(y))))
        node_id_of[(y, x)] = nid
        return nid

    split_n = 0

    def ensure_join_node(y, x):
        """Node at a base-river cell: the existing node, or a new
        confluence splitting the base edge passing through it."""
        if (y, x) in node_id_of:
            return node_id_of[(y, x)]
        nid = ensure_node(y, x, "confluence")
        nonlocal split_n
        for eid, idx in list(cell_on_edge.get((y, x), [])):
            ei = next(i for i, e_ in enumerate(edges) if e_.id == eid)
            e = edges[ei]
            if idx <= 0 or idx >= len(e.polyline) - 1:
                continue
            e1 = Edge(id=e.id, node_a=e.node_a, node_b=nid,
                      length=float(idx), kind=e.kind, quality=e.quality,
                      polyline=e.polyline[:idx + 1])
            e2id = f"river:split{split_n:03d}"
            split_n += 1
            e2 = Edge(id=e2id, node_a=nid, node_b=e.node_b,
                      length=float(len(e.polyline) - idx - 1),
                      kind=e.kind, quality=e.quality,
                      polyline=e.polyline[idx:])
            edges[ei] = e1
            edges.append(e2)
            edge_monthly[e1.id] = _monthly_classes(
                e1.polyline, dis_m, thr_m, drop_last=True)
            edge_monthly[e2id] = _monthly_classes(
                e2.polyline, dis_m, thr_m, drop_last=True)
            for i, (px, py) in enumerate(e.polyline):
                cell = (int(py), int(px))
                cell_on_edge[cell] = [hh for hh in
                                      cell_on_edge.get(cell, [])
                                      if hh[0] != eid]
            for i, (px, py) in enumerate(e1.polyline):
                cell_on_edge.setdefault((int(py), int(px)),
                                        []).append((e1.id, i))
            for i, (px, py) in enumerate(e2.polyline):
                cell_on_edge.setdefault((int(py), int(px)),
                                        []).append((e2id, i))
        return nid

    # ---- seasonal candidates: any month clears the threshold off-base
    seasonal_any = np.zeros((H, W), dtype=bool)
    for m in range(12):
        if thr_m[m] > 1e-9:
            seasonal_any |= (dis_m[m] >= thr_m[m])
    seasonal_any &= ~river & ~lake & ~ocean

    # seasonal node classification (same vocabulary as _river_nodes;
    # a cell whose downstream is BASE river is not a node — the join
    # node lives on the base cell)
    snodes: dict[tuple[int, int], str] = {}
    ys, xs = np.nonzero(seasonal_any)
    for y, x in zip(ys.tolist(), xs.tolist()):
        up = 0
        for dy, dx in _D8:
            ny, nx_ = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx_ < W and seasonal_any[ny, nx_]:
                d = direction[ny, nx_]
                if d >= 0 and (ny + _D8[d][0], nx_ + _D8[d][1]) == (y, x):
                    up += 1
        d = direction[y, x]
        if up == 0:
            snodes[(y, x)] = "source"
        elif up >= 2:
            snodes[(y, x)] = "confluence"
        if d < 0:
            snodes[(y, x)] = "outlet"
        else:
            ny, nx_ = y + _D8[d][0], x + _D8[d][1]
            if not seasonal_any[ny, nx_] and not river[ny, nx_]:
                snodes[(y, x)] = "outlet"

    # ---- walk seasonal segments downstream (same walk as the base
    # extraction): end at a seasonal node, JOIN the base network, or
    # die floating (seasonal outlet)
    seen_starts: set[tuple] = set()
    for (sy, sx), kind in sorted(snodes.items()):
        path = [(sy, sx)]
        y, x = sy, sx
        join_cell = end_cell = None
        floating = False
        extended_water = False
        while len(path) <= 2 * H * W:
            d = direction[y, x]
            if d < 0:
                floating = True
                break
            dy, dx = _D8[d]
            ny, nx_ = y + dy, x + dx
            if not (0 <= ny < H and 0 <= nx_ < W):
                floating = True
                break
            step = [corner(y, x, ny, nx_)] if (dy and dx) else []
            if river[ny, nx_]:
                path += step + [(ny, nx_)]
                join_cell = (ny, nx_)
                break
            if (ny, nx_) in snodes:
                path += step + [(ny, nx_)]
                end_cell = (ny, nx_)
                break
            if not seasonal_any[ny, nx_]:
                if lake[ny, nx_] or ocean[ny, nx_]:
                    # seasonal mouth: extend into the receiving water
                    # cell so the stamp reaches the waterline
                    path += step + [(ny, nx_)]
                    extended_water = True
                floating = True
                break
            path += step + [(ny, nx_)]
            y, x = ny, nx_
        if len(path) < 2:
            continue                    # isolated cell: sub-L0, no edge
        a = ensure_node(sy, sx, kind)
        if join_cell is not None:
            b = ensure_join_node(*join_cell)
            drop_last = True
        elif end_cell is not None:
            b = ensure_node(*end_cell, snodes[end_cell])
            drop_last = True
        elif floating:
            b = ensure_node(y, x, "outlet")
            drop_last = extended_water  # the appended water cell's
                                        # inflow is not this edge's
        else:
            continue                    # cycle guard tripped
        if a == b or (a, b) in seen_starts:
            continue
        seen_starts.add((a, b))
        pl = tuple((float(px), float(py)) for py, px in path)
        eid = f"river:seas{len(seen_starts):03d}"
        classes = _monthly_classes(pl, dis_m, thr_m, drop_last=drop_last)
        edge_monthly[eid] = classes
        edges.append(Edge(
            id=eid, node_a=a, node_b=b, length=float(len(path) - 1),
            kind="river_seasonal", quality=float(max(classes)),
            polyline=pl))

    # ---- per-cell monthly products, FROM the edge state
    width_m = np.zeros((12, H, W), dtype=np.int8)
    for e in edges:
        classes = edge_monthly[e.id]
        for m in range(12):
            c = classes[m]
            if c:
                for px, py in e.polyline:
                    y, x = int(py), int(px)
                    # mouth-extended edges include the receiving water
                    # cell — the planes never mark water as river
                    if lake[y, x] or ocean[y, x]:
                        continue
                    if c > width_m[m, y, x]:
                        width_m[m, y, x] = c
    hydro["river_width_monthly"] = width_m
    hydro["river_monthly"] = width_m > 0
    hydro["river_perm"] = (width_m > 0).all(axis=0)
    return nodes, edges, edge_monthly
