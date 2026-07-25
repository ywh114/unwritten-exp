"""K11 — plates and elevation.

A many-dots Voronoi partition (fine cells) is computed first, with the
dot-distance comparison evaluated at domain-warped coordinates — every
downstream boundary (plate edges, faults, coastlines) is a natural curve,
never a Voronoi straight line. Fine cells touching the map border are
reserved for ocean BEFORE any gluing (the only guaranteed ocean buffer);
interior fine cells glue into a handful of macro plates by seeded region
growth on longest shared borders.

Elevation = per-plate base height (each macro plate draws continental —
above sea level — or oceanic — below, so marine basins emerge inside
the map) + fault signatures by crustal-type pair + fbm relief. The
ocean floor has its own relief. Coasts: the pre-detail base is pulled
down (land side) and pushed up (sea side) toward the waterline FIRST,
and below-sea cells are then reshaped into a real continental-shelf
profile by distance to the provisional coastline (0 -> ~200 m over the
shelf width, break, steep rise into the plate base), then land/sea
detailing is mixed by elevation relative to sea level —
above-sea cells are always fully land-textured, so island arcs on
oceanic plates are never flat plateaus.

Plates are kinematic templates (game-layer RFC §1): equilibrium passes
only, never tectonic simulation.
"""

from __future__ import annotations

import math

import numpy as np

from kernel.hashrng import Stream

from exp.k11_worldgen.raster import distance_to_mask, fbm, nearest_values


def _z(field: np.ndarray) -> np.ndarray:
    """z-standardize: raw fbm clusters tightly around its mean, so fields
    used for warping/modulation are centered and scaled to unit std."""
    return (field - field.mean()) / (field.std() + 1e-9)


def _smooth(field: np.ndarray, rounds: int = 4) -> np.ndarray:
    """Separable 3x3 box smoothing, edge-padded."""
    out = field
    for _ in range(rounds):
        p = np.pad(out, 1, mode="edge")
        out = sum(p[dy:dy + out.shape[0], dx:dx + out.shape[1]]
                  for dy in range(3) for dx in range(3)) / 9.0
    return out


class Plates:
    """Fine Voronoi partition glued into macro plates over the grid.

    Attributes:
        fine_id: (H, W) fine-cell id per raster cell.
        macro_id: (H, W) macro-plate id per raster cell, -1 for ocean.
        is_ocean: (H, W) bool — border-ring fine cells (reserved).
        fault_dist: (H, W) distance to the nearest inter-plate boundary.
        fault_conv: (H, W) signed convergence of the nearest boundary
            (>0 convergent), carried outward by nearest_values.
        fault_kind: (H, W) crustal-type pair of the nearest boundary
            (0 = continent-continent, 1 = mixed, 2 = ocean-ocean).
        fault_sub: (H, W) plate id of the subducting side (-1 =
            symmetric); oceanic always subducts under continental.
        boundary_dist / convergence: back-compat aliases.
        n: number of macro plates. n_fine: number of fine cells.
    """

    def __init__(self, stream: Stream, shape: tuple[int, int],
                 n_dots: int = 80, n_plates: int = 12) -> None:
        h, w = shape

        # -- fine partition: jittered-grid dots
        side = math.ceil(math.sqrt(n_dots))
        dots: list[tuple[float, float]] = []
        i = 0
        for gy in range(side):
            for gx in range(side):
                cx = (gx + 0.5 + 0.7 * (stream.uniform(10 + i, 0) - 0.5)) * w / side
                cy = (gy + 0.5 + 0.7 * (stream.uniform(10 + i, 1) - 0.5)) * h / side
                dots.append((cx, cy))
                i += 1
        self.dots = dots
        self.n_fine = len(dots)
        yy, xx = np.mgrid[0:h, 0:w].astype(float)
        # domain-warped assignment: cells compare dot distances at displaced
        # coordinates, so EVERY downstream boundary (plate edges, faults,
        # coastlines, biome patch outlines) is a natural curve instead of a
        # Voronoi straight line
        warp_amp = min(h, w) / 20.0
        wx = _z(fbm(stream.child("warp.x"), shape, base_cell=min(h, w) // 8, octaves=3)) * warp_amp
        wy = _z(fbm(stream.child("warp.y"), shape, base_cell=min(h, w) // 8, octaves=3)) * warp_amp
        xw, yw = xx + wx, yy + wy
        fine = np.zeros((h, w), dtype=int)
        best = np.full((h, w), np.inf)
        for p, (cx, cy) in enumerate(dots):
            d2 = (xw - cx) ** 2 + (yw - cy) ** 2
            closer = d2 < best
            fine[closer] = p
            best[closer] = d2[closer]
        self.fine_id = fine

        # -- border fine cells are reserved for ocean — as ELEVATION, not
        # plate membership: rim cells glue into macro
        # plates along with everything else; the reservation only forces
        # their base height down. Plates then span land and sea like real
        # tectonic plates.
        ocean_fine = (set(fine[0, :]) | set(fine[-1, :])
                      | set(fine[:, 0]) | set(fine[:, -1]))
        self.ocean_fine = ocean_fine
        self.is_ocean = np.isin(fine, list(ocean_fine))
        interior = sorted(range(self.n_fine))  # all cells participate

        # -- shared-border lengths between fine cells
        shared: dict[tuple[int, int], int] = {}
        for a, b in ((fine[:, :-1].ravel(), fine[:, 1:].ravel()),
                     (fine[:-1, :].ravel(), fine[1:, :].ravel())):
            for fa, fb in zip(a, b):
                if fa != fb:
                    key = (min(fa, fb), max(fa, fb))
                    shared[key] = shared.get(key, 0) + 1
        neighbors: dict[int, list[tuple[int, int]]] = {}
        for (fa, fb), length in shared.items():
            neighbors.setdefault(fa, []).append((fb, length))
            neighbors.setdefault(fb, []).append((fa, length))

        # -- glue interior cells into macro plates: spread seeds, then
        # greedy growth by longest shared border (almost-convex plates)
        n_plates = min(n_plates, len(interior))
        seeds = [min(interior, key=lambda f: (dots[f][0] - w / 2) ** 2
                     + (dots[f][1] - h / 2) ** 2)]
        while len(seeds) < n_plates:
            seeds.append(max(
                (f for f in interior if f not in seeds),
                key=lambda f: (min((dots[f][0] - dots[s][0]) ** 2
                                   + (dots[f][1] - dots[s][1]) ** 2
                                   for s in seeds), -f)))
        macro_of_fine: dict[int, int] = {}
        import heapq
        frontier: list[tuple[int, int, int]] = []  # (-shared, fine, macro)
        for m, f in enumerate(seeds):
            macro_of_fine[f] = m
            for nb, length in neighbors.get(f, []):
                heapq.heappush(frontier, (-length, nb, m))
        while frontier:
            neg_len, f, m = heapq.heappop(frontier)
            if f in macro_of_fine:
                continue
            macro_of_fine[f] = m
            for nb, length in neighbors.get(f, []):
                if nb not in macro_of_fine:
                    heapq.heappush(frontier, (-length, nb, m))
        # stragglers: fine cells unreachable from seeds (shouldn't happen
        # on a connected partition, but guard anyway)
        for f in interior:
            if f not in macro_of_fine:
                macro_of_fine[f] = max(macro_of_fine.values(), default=-1) + 1

        self.n = max(macro_of_fine.values()) + 1 if macro_of_fine else 0
        lut = np.full(self.n_fine, -1, dtype=int)
        for f, m in macro_of_fine.items():
            lut[f] = m
        self.macro_id = lut[fine]
        self._defragment(shape)

        # -- macro centroids + velocities
        self.velocities: list[tuple[float, float]] = []
        self.centroids: list[tuple[float, float]] = []
        for m in range(self.n):
            cells = self.macro_id == m
            if cells.any():
                self.centroids.append((float(xx[cells].mean()), float(yy[cells].mean())))
            else:  # plate fully folded away by defragmentation
                self.centroids.append((0.0, 0.0))
            ang = 2 * math.pi * stream.uniform(70 + m, 0)
            speed = 0.5 + stream.uniform(70 + m, 1)
            self.velocities.append((speed * math.cos(ang), speed * math.sin(ang)))

        # -- oceanic vs continental macro plates (emergent interior seas):
        # the border ring is the only GUARANTEED ocean; interior plates
        # draw their own fate, so marine basins appear inside the map.
        # Hygiene: at least two continental plates (or a seed could draw
        # an all-sea world with no land faults at all).
        self.oceanic: set[int] = set()
        draws = [(stream.uniform(80 + m, 0), m) for m in range(self.n)]
        oceanic = {m for u, m in draws if u < 0.28}
        if len(oceanic) > self.n - 2:
            keep = {m for _, m in sorted(draws)[: self.n - 2]}
            oceanic &= keep
        # two-sided hygiene: at least two continental
        # plates (above), and at most a third oceanic — with ~10 plates
        # the 0.28 draw is high-variance and an uncapped draw can sink
        # 75%+ of the map. Strongest (lowest-u) draws win.
        max_oceanic = max(2, self.n // 3)
        if len(oceanic) > max_oceanic:
            oceanic = {m for _, m in sorted(
                (u, m) for u, m in draws if m in oceanic)[:max_oceanic]}
        # area hygiene: the count cap is not enough — one mega-plate can
        # sink most of the map. Demote the smallest oceanic plates until
        # oceanic crust covers at most 55% of the cells.
        counts = np.bincount(self.macro_id[self.macro_id >= 0].ravel(),
                             minlength=self.n)
        total = int(counts.sum())
        while oceanic:
            share = sum(int(counts[m]) for m in oceanic) / total
            if share <= 0.55:
                break
            oceanic.remove(min(oceanic, key=lambda m: (int(counts[m]), m)))
        self.oceanic = oceanic
        self.plate_base: list[float] = []
        for m in range(self.n):
            if m in self.oceanic:  # oceanic plate: base below sea level
                self.plate_base.append(0.16 + 0.06 * stream.uniform(80 + m, 1))
            else:                  # continental plate: above sea level, mild deltas
                self.plate_base.append(0.52 + 0.08 * (stream.uniform(80 + m, 1) - 0.5))
        self.is_sea_plate = np.isin(self.macro_id, list(self.oceanic))

        # -- per-fine-cell bias: real plates are not all land or all water
        #. Mild local variance everywhere, plus
        # occasional strong draws: sea pockets inside continental plates,
        # island arcs inside oceanic ones.
        macro_of_fine_arr = lut
        self.fine_bias = np.zeros(self.n_fine)
        self.sea_pocket_fine: set[int] = set()
        self.island_fine: set[int] = set()
        for f in range(self.n_fine):
            u1 = stream.uniform(200 + f, 0)
            u2 = stream.uniform(200 + f, 1)
            bias = 0.16 * (u1 - 0.5)
            if macro_of_fine_arr[f] in self.oceanic:
                if u2 > 0.88:  # island arc
                    bias += 0.35
                    self.island_fine.add(f)
            else:
                if u2 < 0.10:  # sea pocket
                    bias -= 0.24
                    self.sea_pocket_fine.add(f)
            self.fine_bias[f] = bias
        self.is_sea_pocket = np.isin(self.fine_id, list(self.sea_pocket_fine))

        # -- faults: ALL inter-plate boundaries with signed convergence,
        # crustal-type pair (CC/OC/OO), and subducting side. Real fault
        # behavior depends on the crustal types of BOTH sides — mixed
        # margins are where Andes/Japan-type terrain happens, and same-
        # type-only faults would miss them entirely.
        (self.fault_dist, self.fault_conv, self.fault_kind,
         self.fault_sub) = self._all_faults(shape)
        # back-compat aliases (tests, older consumers)
        self.boundary_dist = self.fault_dist
        self.convergence = self.fault_conv

    def _defragment(self, shape: tuple[int, int]) -> None:
        """Fold small plate fragments into the neighboring plate with the
        longest shared border. Domain-warped fine cells can split into
        pieces; gluing assigns the pieces as exclaves — fold them into
        their neighbors instead (keeps plates almost convex)."""
        h, w = shape
        for _ in range(4):
            mid = self.macro_id
            sizes = {m: int((mid == m).sum()) for m in range(self.n)}
            seen = np.zeros((h, w), dtype=bool)
            changed = False
            for sy in range(h):
                for sx in range(w):
                    m0 = mid[sy, sx]
                    if m0 < 0 or seen[sy, sx]:
                        continue
                    comp, stack = [], [(sy, sx)]
                    borders: dict[int, int] = {}
                    while stack:
                        y, x = stack.pop()
                        if seen[y, x] or mid[y, x] != m0:
                            continue
                        seen[y, x] = True
                        comp.append((y, x))
                        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                            ny, nx_ = y + dy, x + dx
                            if 0 <= ny < h and 0 <= nx_ < w:
                                nm = mid[ny, nx_]
                                if nm == m0 and not seen[ny, nx_]:
                                    stack.append((ny, nx_))
                                elif nm >= 0 and nm != m0:
                                    borders[nm] = borders.get(nm, 0) + 1
                    if borders and len(comp) < max(24, 0.25 * sizes[m0]):
                        new_m = max(borders.items(), key=lambda kv: (kv[1], -kv[0]))[0]
                        for y, x in comp:
                            mid[y, x] = new_m
                        changed = True
            if not changed:
                break

        # enclave plates: a plate bordering exactly ONE
        # other plate is fully surrounded — never 'mostly convex'. Fold it
        # into that neighbor; repeat (folding can cascade).
        while self.n > 2:
            mid = self.macro_id
            pairs: set[tuple[int, int]] = set()
            for a, b in ((mid[:, :-1], mid[:, 1:]), (mid[:-1, :], mid[1:, :])):
                m = a != b
                pairs |= set(zip(a[m].tolist(), b[m].tolist()))
            neigh: dict[int, set[int]] = {}
            for x, y in pairs:
                if x >= 0 and y >= 0:
                    neigh.setdefault(x, set()).add(y)
                    neigh.setdefault(y, set()).add(x)
            sizes = {m: int((mid == m).sum()) for m in range(self.n)}
            folded = False
            for m in range(self.n):
                if sizes[m] == 0 or len(neigh.get(m, ())) != 1:
                    continue
                k = next(iter(neigh[m]))
                # deterministic mutual-fold guard: smaller folds into larger
                if (sizes[k], -k) > (sizes[m], -m):
                    mid[mid == m] = k
                    folded = True
            if not folded:
                break

        # compact relabeling so folded-away plates don't linger downstream
        uniq = sorted(int(m) for m in np.unique(self.macro_id) if m >= 0)
        remap = np.full(self.n, -1)
        for new, old in enumerate(uniq):
            remap[old] = new
        self.macro_id = remap[self.macro_id]
        self.n = len(uniq)

    def _all_faults(self, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Every inter-plate boundary with signed convergence, crustal-
        type pair, and subducting side, carried outward by nearest_values.

        Returns (dist, conv, kind, sub):
          dist: distance to the nearest boundary cell
          conv: signed convergence of that boundary (+ convergent)
          kind: 0 = continent-continent, 1 = continent-ocean (mixed),
                2 = ocean-ocean
          sub:  plate id of the subducting side (-1 = symmetric).
                Oceanic crust always subducts under continental; at
                ocean-ocean boundaries the plate moving more INTO the
                other subducts.
        """
        h, w = shape
        mid = self.macro_id
        sea_lut = np.zeros(self.n, dtype=bool)
        for m in self.oceanic:
            sea_lut[m] = True

        meta: dict[tuple[int, int], tuple[float, int, int]] = {}
        pairs: set[tuple[int, int]] = set()
        for a, b in ((mid[:, :-1], mid[:, 1:]), (mid[:-1, :], mid[1:, :])):
            m = (a != b) & (a >= 0) & (b >= 0)
            pairs |= set(zip(a[m].tolist(), b[m].tolist()))
        for a, b in {(min(x, y), max(x, y)) for x, y in pairs}:
            ca, cb = self.centroids[a], self.centroids[b]
            dx_, dy_ = cb[0] - ca[0], cb[1] - ca[1]
            norm = math.hypot(dx_, dy_) or 1.0
            va, vb = self.velocities[a], self.velocities[b]
            conv = ((vb[0] - va[0]) * dx_ / norm
                    + (vb[1] - va[1]) * dy_ / norm)
            oa, ob = sea_lut[a], sea_lut[b]
            kind = 2 if (oa and ob) else (0 if not (oa or ob) else 1)
            sub = -1
            if conv > 0:
                if oa != ob:
                    sub = a if oa else b        # oceanic dives under continental
                elif oa and ob:
                    toward_a = va[0] * dx_ / norm + va[1] * dy_ / norm
                    toward_b = -(vb[0] * dx_ / norm + vb[1] * dy_ / norm)
                    sub = a if toward_a >= toward_b else b
            meta[(a, b)] = (conv, kind, sub)

        boundary = np.zeros((h, w), dtype=bool)
        conv_cell = np.zeros((h, w))
        kind_cell = np.zeros((h, w))
        sub_cell = np.full((h, w), -1.0)
        for y, x in zip(*np.where(mid[:, :-1] != mid[:, 1:])):
            for yy, xx in ((y, x), (y, x + 1)):
                a, b = mid[y, x], mid[y, x + 1]
                if a < 0 or b < 0:
                    continue
                conv, kind, sub = meta[(min(a, b), max(a, b))]
                boundary[yy, xx] = True
                conv_cell[yy, xx] = conv
                kind_cell[yy, xx] = kind
                sub_cell[yy, xx] = sub
        for y, x in zip(*np.where(mid[:-1, :] != mid[1:, :])):
            for yy, xx in ((y, x), (y + 1, x)):
                a, b = mid[y, x], mid[y + 1, x]
                if a < 0 or b < 0:
                    continue
                conv, kind, sub = meta[(min(a, b), max(a, b))]
                boundary[yy, xx] = True
                conv_cell[yy, xx] = conv
                kind_cell[yy, xx] = kind
                sub_cell[yy, xx] = sub

        dist, conv_f = nearest_values(boundary, conv_cell)
        _, kind_f = nearest_values(boundary, kind_cell)
        _, sub_f = nearest_values(boundary, sub_cell)
        return dist, conv_f, kind_f, sub_f


def build_elevation(stream: Stream, shape: tuple[int, int],
                    sea_level: float = 0.35, n_dots: int = 80,
                    n_plates: int = 12) -> tuple[np.ndarray, Plates]:
    """Elevation in [0, 1]: per-plate base heights (continental or
    oceanic tendency) + shelf pull-down/push-up + fault signatures by
    crustal-type pair (CC orogen/rift, OC trench + coastal range, OO
    trench + island arc / ridge) + surface noise mixed by position
    relative to sea level (rough in sparse patches on land, textured
    abyss with seamounts)."""
    h, w = shape
    plates = Plates(stream, shape, n_dots=n_dots, n_plates=n_plates)

    noise = fbm(stream.child("relief"), shape, base_cell=min(h, w) // 24, octaves=6)
    # the abyss noise is domain-warped: value noise interpolates a
    # LATTICE, and on a flat seafloor its fundamental octave reads as
    # soft axis-aligned squares. Offsetting the sample points by a
    # low-frequency field (~1/3 of a lattice cell) bends the iso-bands.
    from exp.k11_worldgen.climate import _bilinear
    floor_raw = fbm(stream.child("abyss"), shape, base_cell=min(h, w) // 12, octaves=6)
    wamp = (min(h, w) // 12) * 0.7
    warp_x = (fbm(stream.child("abyss.wx"), shape, base_cell=min(h, w) // 6, octaves=2) - 0.5) * wamp
    warp_y = (fbm(stream.child("abyss.wy"), shape, base_cell=min(h, w) // 6, octaves=2) - 0.5) * wamp
    gy, gx = np.mgrid[0:h, 0:w].astype(float)
    floor_noise = _bilinear(floor_raw, gx + warp_x, gy + warp_y)

    # per-plate base heights + per-fine-cell bias (sea pockets, island
    # arcs); the reserved border ring sits at abyssal level regardless of
    # its plate's tendency. Box-smoothed so transitions grade — then
    # RE-HARDENED, because the smoothing bleeds continental base into
    # ring cells and would otherwise let land creep into the reserved
    # zone.
    base_lut = np.array(plates.plate_base)
    base = base_lut[plates.macro_id] + plates.fine_bias[plates.fine_id]
    base[plates.is_ocean] = 0.12
    base = _smooth(base, rounds=3)
    base[plates.is_ocean] = 0.12

    # coasts FIRST: the base converges to the
    # waterline from BOTH sides — land sinks to the shore, the sea
    # floor rises onto the shelf
    sea_mask = plates.is_ocean | plates.is_sea_plate | plates.is_sea_pocket
    shelf_w = max(4.0, min(h, w) / 32.0)
    waterline = sea_level - 0.04
    t_land = np.clip(distance_to_mask(sea_mask) / shelf_w, 0.0, 1.0)
    t_sea = np.clip(distance_to_mask(~sea_mask) / shelf_w, 0.0, 1.0)
    t = np.where(sea_mask, t_sea, t_land)
    t = t * t * (3 - 2 * t)
    base = waterline + (base - waterline) * t

    # continental shelf: Earth shelves run 0 -> ~200 m over 40-130 km
    # before the break plunges to the abyss (shelves are ~7% of ocean
    # area; the bare converge-to-waterline above starts the coast at
    # ~460 m and reaches the 2600 m plate base within ~30 km — ~1%).
    # Reshape every below-sea cell by distance to the provisional
    # COASTLINE (not the plate boundary — the ramp above drowns some
    # plate-land cells): 15 m at the shore (stays below sea level, so
    # ocean connectivity and the rim guarantees are untouched) rising
    # to 200 m at the break, then blending into the existing deep base
    # over the rise. Fault signatures come AFTER this, so trenches
    # still carve narrow active-margin shelves (Peru/Chile style).
    from exp.k11_worldgen.units import DEPTH_MAX_M
    shelf_break_w = max(5.0, min(h, w) / 22.0)   # ~46 km shelf proper
    shelf_rise_w = max(3.0, min(h, w) / 42.0)    # steep break -> rise
    # shelf width is a FIELD, not a constant: a low-frequency seeded
    # multiplier so no two coasts match, compressed near active
    # (convergent OC/OO) margins where the trench crowds the shore
    shelf_noise = fbm(stream.child("shelf.w"), shape,
                      base_cell=min(h, w) // 8, octaves=2)
    width_mult = 0.3 + 1.7 * shelf_noise
    conv_near = (np.clip(plates.fault_conv / 1.5, -1.0, 1.0)
                 * np.exp(-0.5 * (plates.fault_dist / 8.0) ** 2))
    width_mult = width_mult * np.clip(1.0 - 0.8 * np.maximum(conv_near, 0.0),
                                      0.25, None)
    landish = base >= sea_level
    d_coast = distance_to_mask(landish)
    below = base < sea_level
    d_shelf = (d_coast - 1.0) / (shelf_break_w * width_mult)
    shelf_m = 15.0 + 185.0 * np.clip(d_shelf, 0.0, 1.0) ** 0.7
    t_r = np.clip((d_coast - 1.0 - shelf_break_w * width_mult)
                  / shelf_rise_w, 0.0, 1.0)
    t_r = t_r * t_r * (3.0 - 2.0 * t_r)
    deep_m = (sea_level - base) / sea_level * DEPTH_MAX_M
    depth_m = shelf_m * (1.0 - t_r) + deep_m * t_r
    base = np.where(below, sea_level - depth_m * sea_level / DEPTH_MAX_M,
                    base)

    # enclosed below-sea basins (not connected to the border ocean) are
    # inland seas / dry depressions, not abyss: real inland seas are far
    # shallower than open ocean (a few hundred meters; Caspian ~1 km max
    # against 4 km abyssal plains), so their floors are compressed
    # toward the waterline BEFORE fault signatures — deep rifts inside
    # them (Baikal/Tanganyika) then keep their full tectonic depth.
    from exp.k11_worldgen.hydrology import connected_ocean
    enclosed = (base < sea_level) & ~connected_ocean(base, sea_level)
    base[enclosed] = sea_level - (sea_level - base[enclosed]) * 0.35

    # ---- fault signatures by crustal-type pair ----
    band = max(2.0, min(h, w) / 85.0)
    warp = _z(fbm(stream.child("fault.warp"), shape, base_cell=min(h, w) // 16, octaves=3)) * band * 0.8
    along = np.clip(0.55 + 0.30 * _z(fbm(stream.child("fault.along"), shape, base_cell=min(h, w) // 12, octaves=3)),
                    0.05, 1.0)
    d = plates.fault_dist + warp
    c = np.clip(plates.fault_conv / 1.5, -1.0, 1.0) * along
    convergent = c > 0
    kind = plates.fault_kind
    on_sub = plates.macro_id == plates.fault_sub  # on the subducting side
    own_oceanic = plates.is_sea_plate
    g = lambda x, s: np.exp(-0.5 * (x / s) ** 2)

    sig = np.zeros((h, w))
    # continent-continent: broad symmetric uplift on convergence
    # (strong draws make 5.5-7 km ranges — the asymptotic cap above
    # 1.0 lets them leak through instead of piling at a ceiling);
    # divergence rifts at 0.35x — a full-strength rift gouges floors to
    # ~-1800 m, far beyond real dry rift basins (Dead Sea ~-430 m);
    # damped, enclosed rift floors land in the shallow-hundreds below
    # sea level (and deep ones become rift LAKES, Baikal-style, via
    # the water balance).
    sig += (kind == 0) * (0.55 * g(d, band) * np.where(c > 0, c, 0.35 * c))
    # ocean-ocean convergent: trench on the subducting side, volcanic
    # ISLAND ARC on the overriding side (displaced, segmented by `along`,
    # strong enough for crests to breach — Japan/Aleutians)
    oo_c = (kind == 2) & convergent
    sig += (oo_c & on_sub) * (-0.22 * g(d, band * 0.7) * c)
    sig += (oo_c & ~on_sub) * (0.24 * g(d - 4.0, band) * c)
    # ocean-ocean divergent: mid-ocean ridge (stays below sea level)
    sig += ((kind == 2) & ~convergent) * (0.12 * g(d, band) * (-c))
    # continent-ocean convergent (Andes): trench just offshore, coastal
    # range displaced inland
    oc_c = (kind == 1) & convergent
    sig += (oc_c & own_oceanic) * (-0.20 * g(d - 2.0, band * 0.7) * c)
    sig += (oc_c & ~own_oceanic) * (0.35 * g(d - 5.0, band) * c)
    # continent-ocean divergent: rifted margin, gentle
    sig += ((kind == 1) & ~convergent) * (-0.05 * g(d, band) * (-c))
    # the reserved border ring is the guaranteed ocean buffer — no
    # tectonic signature may lift it (it sits outside the map's scope)
    sig[plates.is_ocean] = 0.0
    base = base + sig

    # surface detail, mixed by POSITION relative to sea level — faults
    # included in the base, so island arcs rising above sea level get
    # land texture. Land roughness comes in sparse patches (the
    # low-frequency `rough` mask, quadratic so rough areas are rare);
    # the abyss is textured too, plus sparse seamounts.
    # Land noise is zero-centered with an ASYMMETRIC profile: the
    # positive side runs at full amplitude while the subtractive side is
    # damped 4x. Some downward range is needed at all because purely
    # additive noise pins the world's lowest land at exactly sea level —
    # with centered noise, rift and sea-pocket floors can fall below sea
    # level, and basins that then fail the hydrology water balance stay
    # as DRY below-sea depressions (Death Valley style). The damping
    # keeps those depressions in the real-world range: actual dry
    # basins bottom out around -430 m (Dead Sea), not kilometers.
    rough = _z(fbm(stream.child("rough"), shape, base_cell=min(h, w) // 6, octaves=3))
    rough_amp = 0.45 + 0.275 * np.clip(rough, 0.0, 2.0) ** 2
    smt = _z(fbm(stream.child("seamount"), shape, base_cell=min(h, w) // 8, octaves=3))
    seamount = 0.15 * np.clip(smt - 1.6, 0.0, None) ** 2
    grain = 0.45 * rough_amp * (
        np.maximum(noise - 0.5, 0.0) + 0.25 * np.minimum(noise - 0.5, 0.0))
    detail_land = 0.10 + grain

    ramp = 0.08
    mix = np.clip((base - (sea_level - ramp)) / ramp, 0.0, 1.0)
    # below-sea cells always take the SEA recipe: the shelf profile
    # sits inside the land-grain ramp, and the land detail's +0.10
    # emergence offset would push the whole shelf above the waterline.
    # Sea texture is depth-aware — shelves are wave-swept sediment
    # flats, the abyss carries the relief.
    mix = np.where(base < sea_level, 0.0, mix)
    deep_m = (sea_level - base) / sea_level * DEPTH_MAX_M
    tex = np.clip(deep_m / 800.0, 0.15, 1.0)
    detail_sea = (0.15 * floor_noise + seamount - 0.04) * tex
    elev = base + mix * detail_land + (1.0 - mix) * detail_sea
    # enclosed below-sea basins (not connected to the border ocean) are
    # continental crust sitting low — lake beds, dry Death-Valley floors
    # — not abyss. Abyssal texture is several times quieter than land
    # relief, which leaves such basins reading as un-noised flats; give
    # them the land grain instead, without the +0.10 emergence offset so
    # they stay below sea level.
    from exp.k11_worldgen.hydrology import connected_ocean
    enclosed = (base < sea_level) & ~connected_ocean(base, sea_level)
    elev = np.where(enclosed, base + grain, elev)
    # soft compression above the cap: peaks keep relief and never plane
    # off. The asymptote sits ABOVE the 1.0 normalization (leaky
    # ceiling, not a hard one — exceptional collision draws push past
    # 6 km while the median collision stays well below), and the final
    # clip only trims what leaks past the normalization bound.
    cap = 0.85
    over = elev > cap
    elev = np.where(over, cap + 0.35 * (1.0 - np.exp(-(elev - cap) / 0.35)), elev)
    # the reserved border ring is the guaranteed ocean buffer: its base
    # is pinned down and faults may not lift it, but surface detail
    # (seamounts) could still breach the surface inside it, and islands
    # in adjacent fine cells can settle within a pixel or two of the
    # edge — land must never kiss the map edge. Two layers: a smooth
    # taper pulls the outermost 2 anchor cells below the surface
    # (absolute void margin), and the whole reserved ring is
    # hard-submerged against breaching seamounts.
    floor = sea_level - 0.02
    gy, gx = np.mgrid[0:h, 0:w]
    dist = np.minimum(np.minimum(gy, h - 1 - gy), np.minimum(gx, w - 1 - gx))
    t = np.clip(dist / 2.0, 0.0, 1.0)
    t = t * t * (3 - 2 * t)
    elev = np.where(elev > floor, floor + (elev - floor) * t, elev)
    elev = np.where(plates.is_ocean, np.minimum(elev, floor), elev)
    # distribution reshape: median LAND sat at ~2.1-2.7 km — a plateau
    # planet. Compress the above-sea MIDDLE with a monotonic power
    # curve (t^2): lowlands broaden toward an Earth-like ~1 km median
    # while the high tail keeps 4-5 km peaks (t^2: 2.4 km -> ~1 km,
    # 4 km -> 2.7 km, 5.5 km -> 4.9 km). Monotonic, so flow topology,
    # fill levels and drainage are provably untouched; only gradients
    # and altitude-dependent downstreams (lapse, biome altitude gates)
    # shift — which is the point.
    t_land = np.clip((elev - sea_level) / (1.0 - sea_level), 0.0, 1.0)
    elev = np.where(elev > sea_level,
                    sea_level + (1.0 - sea_level) * t_land ** 2.0, elev)
    return np.clip(elev, 0.0, 1.0), plates


# -- volcanoes --------------------------------------------------------------
# Cones sit on convergent faults, their density scaled by LOCAL fault
# activity (convergence normalized per world): busy subduction zones
# sprout arcs, quiet margins stay quiet. Sizes draw small-heavy —
# tiny undersea cones included, most never breach; a deep wide crater
# on a small sea cone reads as a caldera ring-island. No kind labels:
# the forms emerge from the draws.
_VOLC_RATE = 0.03           # cone probability per fault cell at full activity
_VOLC_MIN_SEP = 12          # cells (~50 km at 4 km/cell)
_VOLC_H_M = (300.0, 4500.0)     # summit height above the LOCAL base, meters
_VOLC_R_CELLS = (1.5, 6.0)      # cone sigma, cells (~6-24 km)


def build_volcanoes(stream: Stream, plates: "Plates", elev: np.ndarray,
                    sea_level: float,
                    cell_km: float = 4.0) -> tuple[np.ndarray, list]:
    """Stamp volcanic cones on convergent faults. Runs right after
    build_elevation, BEFORE carve/hydrology, so rivers route around the
    cones and crater depressions can pond. Returns the modified
    elevation and the metadata list [(y, x, height_m)]."""
    from exp.k11_worldgen.units import ELEV_MAX_M
    H, W = elev.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    conv = plates.fault_conv
    cand = ((plates.fault_dist <= 2) & (conv > 0)
            # the border ring's fine cells are RESERVED for ocean (the
            # only guaranteed buffer) — a cone there would stamp land
            # into the forbidden rim
            & ~plates.is_ocean)
    if not cand.any():
        return elev, []
    ys, xs = np.where(cand)
    n_c = len(ys)
    c90 = float(np.percentile(conv[cand], 90.0)) + 1e-9
    act = np.clip(conv[ys, xs] / c90, 0.0, 1.0)
    u_act = np.array([stream.uniform(0, 300 + i) for i in range(n_c)])
    sel = np.where(u_act < _VOLC_RATE * act)[0]
    # busiest faults first, greedy spacing
    sel = sel[np.argsort(-act[sel])]
    picked: list[tuple[int, int]] = []
    for k in sel:
        y, x = int(ys[k]), int(xs[k])
        if all((y - py) ** 2 + (x - px) ** 2 >= _VOLC_MIN_SEP ** 2
               for py, px in picked):
            picked.append((y, x))
    elev = elev.copy()
    volcanoes = []
    for i, (y, x) in enumerate(picked):
        u1 = stream.uniform(0, 400 + 4 * i)
        u2 = stream.uniform(0, 401 + 4 * i)
        u3 = stream.uniform(0, 402 + 4 * i)
        u4 = stream.uniform(0, 403 + 4 * i)
        # small-heavy sizes: tiny cones are common, 4 km giants rare
        h_m = _VOLC_H_M[0] + (_VOLC_H_M[1] - _VOLC_H_M[0]) * u1 ** 2
        sigma = (_VOLC_R_CELLS[0] + (_VOLC_R_CELLS[1] - _VOLC_R_CELLS[0])
                 * u2)
        # crater: shallow dip on big shields, deep wide caldera on some
        # (on a tiny sea cone the rim breaches and the flooded center
        # reads as a ring island)
        crater_f = 0.15 + 0.55 * u3
        crater_w = 0.2 + 0.3 * u4
        # meters -> normalized elevation units (see marks._m_above)
        dh = h_m / ELEV_MAX_M * (1.0 - sea_level)
        r2 = (yy - y) ** 2 + (xx - x) ** 2
        cone = dh * np.exp(-0.5 * r2 / sigma ** 2)
        crater = (crater_f * dh
                  * np.exp(-0.5 * r2 / (crater_w * sigma) ** 2))
        elev = elev + cone - crater
        volcanoes.append((y, x, float(h_m)))
    return np.clip(elev, 0.0, 1.0), volcanoes
