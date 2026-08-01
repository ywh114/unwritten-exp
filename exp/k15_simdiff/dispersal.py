"""K15 engine — spec §7 dispersal (pure functions + named constants).

The round-3 dispersal step of the flora rounds: stress-gated emission
(§7.1), the PACKET colonization layer (§7.2 — a handful of coherent,
width-carrying shapes per instance instead of the v0.5 per-source-cell
deposit rain) and the per-packet establishment gate that converts a
packet into N and founds new instances (§7.3). Pure functions of (state
arrays, the lineage DerivedView, channel shares); the only draws are the
jump roll, the packet origin / animal-center draws and the per-packet
establishment roll, all from the per-(round, instance) K1 Stream the
engine passes (spec §7.2: ``Stream(seed, "k15.disperse",
f"{t}:{instance_id}")`` with a child stream per channel — e.g.
``rng.child("jump")``, ``rng.child("establish")``, ``rng.child("pk:wind")``).
No stream is ever constructed here and every draw address (clock, index)
is pinned, so replay is byte-identical. Never uuid/random/time/np.random.

Cell addressing (resolved): (y, x) INT PAIRS, world coordinates, for
every shape cell list and every establishment candidate (the engine's
D8 downstream pointer is a separate FLAT-index field — spec §5.0 — and
is consumed internally by packet_water_walk). The packet shapes raster
deterministically: no floats enter cell selection beyond the pinned
draws (a wind ray's length is ceil(λ) — an integer — the λ float never
indexes).

The packet model (v0.6, spec §7): per instance per round the emission
budget E splits across the dispersal_channels pmf as before; each
sustained channel's share divides equally among n_pk =
packet_count(n_occ) packets, each packet a contiguous shape launched
from a random FRONTIER cell (occupied cell with an unoccupied
8-neighbor). One weighted establishment decision per packet converts
the WHOLE eligible shape or none of it — colonized ground is blobs, not
speckle. The engine owns absorption (§3: rain landing on a cell already
held by another instance of the same lineage joins the occupant), the
colonization memory (§7.3) and the §7.3 founding split (join vs mint) —
all instance/component state, not kernel math.

Ambiguities resolved (recorded here for the spec log):

- The v0.5 per-source kernels (deposit_local/wind/water/animal) are
  DELETED with the per-cell deposit paths (spec v0.6 §7.2, owner ruling
  "tentacles, not dots"); the packet shapes replace them: a filled
  spill blob (local), a tapered ray (wind), a width-carrying D8/current
  walk (water), a filled disk at a random reachable offset (animal) and
  a filled disk at the jump landing (jump).
- share_E is the CHANNEL budget (E × dispersal_channels pmf weight).
  Every packet of a channel carries pk_share = share_E / n_pk; the
  packet's rain spreads UNIFORMLY over its cells (val = pk_share /
  |cells|) and, on success, its N spreads uniformly over its founded
  cells (N = pk_share / |founded|, clipped to 1). Rain is a normalized
  saturation fraction, not a particle budget.
- Wind lambda_w (the ray LENGTH now, not a decay scale) uses the speed
  of the origin cell's mean vector: L = ceil(WIND_K × hypot(wind_u,
  wind_v) / sqrt(propagule_mass_mg)), capped at WIND_MAX_CELLS. The
  wind ray is a STRAIGHT integer ray (Bresenham-style; direction fixed
  from the origin's vector); the marine current walk RE-READS the field
  at every step (a streamline with dominant-axis single-cell steps).
  Both carry width 2 (the ray cell + one fixed perpendicular neighbor —
  column +1 on row-major rays, row +1 on column-major) for the first
  floor(len/2) walked cells and width 1 for the rest (a tapered
  tentacle).
- The packet establishment decision (spec §7.3): candidates are the
  packet's cells with NO occupying instance of the lineage (own cells
  included in the rain scatter — absorption — but never in N);
  mean_f = mean(f_hab^beta) over the candidates in row-major order
  (deterministic accumulation; beta = EST_BETA, 1.0). The packet founds
  iff u < P with P = packet_probability(mean_f, establish, T,
  in_memory): the §7.3 gate (mean_f < EST_F_MIN → 0), the §4 single-T
  conversion P = 1 − (1 − p_yr)^T with p_yr = establish × mean_f, and a
  ×MEM_PENALTY down-weight when any candidate cell is in the lineage's
  colonization memory (recently failed). On success the eligible cells
  (f_hab >= EST_F_MIN) found at N = pk_share / |founded| — the vanguard
  sink cells inside a packet carry rain but never N.
- maybe_jump returns the (dy, dx) offset only; the caller applies it to
  a randomly chosen FRONTIER cell (its own pinned draw) and folds a
  failed roll (None) into the local channel.
- packet_animal_disk / packet_jump_disk receive the world grid size and
  clip internally (unlike the v0.5 animal stub, whose pinned signature
  carried no grid).
"""

from __future__ import annotations

import math

import numpy as np

from kernel.hashrng import Stream

# ── spec §13 knobs (v0.3/v0.6, settled values) ─────────────────────────
COUNT_REF = 1e4             # emission normalization (propagules/yr)
EMIT_K = 1.0                # fugitive emission gain (stress gate)
EMIT_P = 1.0                # fugitive emission power
LOCAL_BIG = 0.5             # local share at/above which the spill is r=2
WIND_K = 1.0                # wind distance scale
WIND_MAX_CELLS = 40         # wind ray length cap (cells)
WATER_LAMBDA = 20.0         # water decay scale (cells) — v0.6: reach
                            # term for the §7.3 mobility gate only (the
                            # water packet no longer decays)
WATER_MAX_CELLS = 40        # water walk length cap (cells)
ANIMAL_RADIUS_CELLS = 5     # animal packet disk radius (cells)
JUMP_SCALE = 1.0            # jump probability scale
JUMP_RADIUS_CELLS = 50      # jump landing roll disk radius (cells)
JUMP_DISK_RADIUS = 3        # v0.6: jump packet blob radius (~28 cells)
RAIN_HALF = 0.5             # rain half-saturation in rain_frac
EST_F_MIN = 0.3             # establishment habitat gate (settled 2026-08-01)
EST_N0 = 0.05               # per-cell founder density (v0.5 gate form)
SEEDBANK_KEEP = 0.5         # persistent-rain carryover decay
# ── spec §13 v0.6 packet knobs ─────────────────────────────────────────
PACKET_BASE = 2             # packet-count baseline (channels)
PACKET_MAX = 8              # packet-count cap per channel
PACKET_AREA_REF = 32        # packet-count reference area (cells)
EST_BETA = 1.0              # establishment habitat power (0 = stress-blind)
MEM_ROUNDS = 3              # colonization-memory retention (rounds)
MEM_PENALTY = 0.25          # remembered-target establishment down-weight


def _disk_offsets(radius: int) -> tuple[tuple[int, int], ...]:
    """Euclidean disk offsets of radius *radius*, center excluded,
    lexicographically sorted — a deterministic draw table (the jump
    roll and the animal center draw index into these). The uniform-draw
    disk of spec §7.2."""
    return tuple(sorted(
        (dy, dx)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dy * dy + dx * dx <= radius * radius and (dy, dx) != (0, 0)))


def _filled_disk_offsets(radius: int) -> tuple[tuple[int, int], ...]:
    """Euclidean disk offsets INCLUDING the center — the packet blob
    rasterization table (a filled disk: every cell of the packet)."""
    return tuple(sorted(
        (dy, dx)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dy * dy + dx * dx <= radius * radius))


_ANIMAL_DISK = _disk_offsets(ANIMAL_RADIUS_CELLS)
_JUMP_DISK = _disk_offsets(JUMP_RADIUS_CELLS)
_FILLED_ANIMAL_DISK = _filled_disk_offsets(ANIMAL_RADIUS_CELLS)
_FILLED_JUMP_DISK = _filled_disk_offsets(JUMP_DISK_RADIUS)


def _cheb_dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    """Chebyshev dilation of a bool mask by *radius* (8-connectivity,
    the spec §8 convention): radius 1 = the 8 neighbors, radius 2 = the
    5x5 block minus the center — the local kernel's spill rule. Pure
    numpy, no scipy."""
    H, W = mask.shape
    padded = np.pad(mask, radius)
    out = np.zeros_like(mask)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dy == 0 and dx == 0:
                continue
            out |= padded[radius + dy:radius + dy + H,
                          radius + dx:radius + dx + W]
    return out


def _line_ray(y, x, u, v, H, W, max_steps):
    """Integer ray along (u, v), Bresenham-style, deterministic.

    The ray advances ONE cell per step along the DOMINANT axis (the
    larger |component|; ties -> the row axis) in that component's sign;
    the minor axis advances one cell whenever the fractional cross-axis
    accumulation crosses an integer:
        minor_offset(k) = sign(minor) * floor(k * |minor| / |major|)
    so a (u, v) = (3, 1) wind reaches (dy, dx) = (1, 3) after three
    steps. Yields (yy, xx, k) for k = 1..max_steps; both coordinates
    are monotonic, so the first out-of-grid cell ends the ray. A zero
    vector yields nothing."""
    if u == 0.0 and v == 0.0:
        return
    if abs(v) >= abs(u):                      # row-major (ties -> rows)
        yy, xx, err = y, x, 0
        num, den = abs(u), abs(v)             # minor fraction per step
        for k in range(1, max_steps + 1):
            yy += 1 if v >= 0.0 else -1
            err += num
            if err >= den:
                xx += 1 if u >= 0.0 else -1
                err -= den
            if not (0 <= yy < H and 0 <= xx < W):
                break
            yield yy, xx, k
    else:                                     # column-major
        yy, xx, err = y, x, 0
        num, den = abs(v), abs(u)
        for k in range(1, max_steps + 1):
            xx += 1 if u >= 0.0 else -1
            err += num
            if err >= den:
                yy += 1 if v >= 0.0 else -1
                err -= den
            if not (0 <= yy < H and 0 <= xx < W):
                break
            yield yy, xx, k


def _field_walk(y, x, u_field, v_field, H, W, max_steps):
    """Walk a (u, v) vector field cell-to-cell (marine current mode).

    At each step the direction is RE-READ at the current cell and the
    walk advances ONE cell along the dominant axis (the larger
    |component|; ties -> the row axis) in that component's sign. A zero
    vector ends the walk, as does the grid edge. Yields (yy, xx, k) for
    k = 1..max_steps. Deterministic, cheap cardinal stepping."""
    yy, xx = int(y), int(x)
    for k in range(1, max_steps + 1):
        u = float(u_field[yy, xx])
        v = float(v_field[yy, xx])
        if u == 0.0 and v == 0.0:
            break
        if abs(v) >= abs(u):
            yy += 1 if v >= 0.0 else -1
        else:
            xx += 1 if u >= 0.0 else -1
        if not (0 <= yy < H and 0 <= xx < W):
            break
        yield yy, xx, k


# ── §7.1 emission ──────────────────────────────────────────────────────


def emission(n_occupied: int, view: dict, mean_s_real: float) -> float:
    """Spec §7.1:
        E = occupied_cells * (propagule_count / COUNT_REF)
            * (1 + EMIT_K * max(mean_s_real, 0)) ^ EMIT_P
    E is the instance's total per-round rain in normalized units (the T
    years of rain inside a round arrive as one integrated deposit). The
    stress term is a fugitive-emission GATE: only positive stress
    raises emission; negative (opportunity) stress leaves the baseline
    (max(., 0) — stress never suppresses dispersal below the baseline).
    A plan without a propagule_count emits nothing."""
    count = view.get("propagule_count")
    if not isinstance(count, (int, float)) or isinstance(count, bool):
        count = 0.0
    gate = 1.0 + EMIT_K * max(float(mean_s_real), 0.0)
    return max(int(n_occupied), 0) * (float(count) / COUNT_REF) * gate ** EMIT_P


# ── §7.2 the packet layer ──────────────────────────────────────────────


def packet_count(n_occupied: int) -> int:
    """Spec §7.2 v0.6 packet count per channel:
        n_pk = clip(PACKET_BASE + floor(log2(max(1, n_occ) /
            PACKET_AREA_REF)), 1, PACKET_MAX)
    A small instance (< 32 cells) emits ONE packet per active channel; a
    huge range saturates at PACKET_MAX. The channel share divides
    equally among its packets."""
    return int(min(PACKET_MAX, max(
        1, PACKET_BASE + math.floor(
            math.log2(max(1, int(n_occupied)) / PACKET_AREA_REF)))))


def frontier_cells(occ: np.ndarray) -> list[tuple[int, int]]:
    """Spec §7.2 v0.6 packet origins: the occupied cells of window *occ*
    with >= 1 unoccupied 8-neighbor (the window edge qualifies — the
    frame is padded, so edge cells see unoccupied padding). Row-major,
    window coordinates; the engine shifts to world coordinates."""
    occ = np.asarray(occ, dtype=bool)
    pad = np.pad(occ, 1)
    has_unocc = _cheb_dilate(~pad, 1)
    ys, xs = np.nonzero(pad & has_unocc)
    return [(int(y - 1), int(x - 1)) for y, x in zip(ys, xs)]


def _dedupe(cells) -> list[tuple[int, int]]:
    """Drop duplicate cells from a shape's raster list, keeping
    first-occurrence order (deterministic — dict insertion order). A
    width-2 tentacle's perpendicular neighbor can coincide with a later
    walked/rayed cell; the shape is a SET of cells, and duplicate cells
    would double the rain/N on that cell."""
    return list(dict.fromkeys(cells))


def packet_local_blob(origin, occ: np.ndarray, y0: int, x0: int, H: int,
                      W: int, local_share: float) -> list[tuple[int, int]]:
    """Spec §7.2 v0.6 local packet: a filled spill blob around the
    origin frontier cell — the Chebyshev disk of radius 1 (radius 2
    when the local channel share >= LOCAL_BIG, the v0.5 spill rule),
    the instance's OWN cells excluded (the spill never lands on the
    parent body). World-coord in-grid cells in raster order (rows then
    columns)."""
    oy, ox = int(origin[0]), int(origin[1])
    r = 2 if float(local_share) >= LOCAL_BIG else 1
    hy, wxc = occ.shape
    cells = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy == 0 and dx == 0:
                continue
            y, x = oy + dy, ox + dx
            if not (0 <= y < H and 0 <= x < W):
                continue
            wy, wx = y - y0, x - x0
            if 0 <= wy < hy and 0 <= wx < wxc and occ[wy, wx]:
                continue
            cells.append((y, x))
    return cells


def packet_wind_ray(origin, wind_u, wind_v, view: dict
                    ) -> list[tuple[int, int]]:
    """Spec §7.2 v0.6 wind packet: a tapered tentacle — the integer ray
    along the wind vector AT THE ORIGIN CELL (the source's own mean
    vector; a straight Bresenham-style ray, not a field walk), length
    L = ceil(lambda) with lambda = WIND_K * speed / sqrt(propagule_mass_mg)
    capped at WIND_MAX_CELLS. Width 2 (the ray cell plus ONE fixed
    perpendicular neighbor: column +1 on row-major rays, row +1 on
    column-major) for the first floor(len/2) walked cells, width 1 for
    the rest (a tapered tentacle). Zero wind at the origin, or a plan
    with no positive propagule mass, emits no cells. In-grid cells
    only."""
    u = np.asarray(wind_u, dtype=np.float64)
    v = np.asarray(wind_v, dtype=np.float64)
    H, W = u.shape
    mass = view.get("propagule_mass_mg")
    if not isinstance(mass, (int, float)) or isinstance(mass, bool) \
            or mass <= 0.0:
        return []
    oy, ox = int(origin[0]), int(origin[1])
    uu, vv = float(u[oy, ox]), float(v[oy, ox])
    speed = math.hypot(uu, vv)
    if speed == 0.0:
        return []
    lam = WIND_K * speed / math.sqrt(float(mass))
    L = max(1, min(WIND_MAX_CELLS, int(math.ceil(lam))))
    row_major = abs(vv) >= abs(uu)
    perp = (0, 1) if row_major else (1, 0)
    walked = [(yy, xx) for yy, xx, _k in _line_ray(oy, ox, uu, vv, H, W, L)]
    cells = []
    half = len(walked) // 2
    for i, (yy, xx) in enumerate(walked):
        cells.append((yy, xx))
        if i < half:
            py, px = yy + perp[0], xx + perp[1]
            if 0 <= py < H and 0 <= px < W:
                cells.append((py, px))
    return _dedupe(cells)


def packet_water_walk(origin, downstream, currents=None
                      ) -> list[tuple[int, int]]:
    """Spec §7.2 v0.6 water packet: walk the D8 downstream pointer
    (fresh mode) or the monthly-mean current field (marine mode) as the
    v0.5 kernel did — downstream: follow the flattened neighbor indices
    cell by cell, stop at an outlet (-1), an out-of-range pointer or the
    WATER_MAX_CELLS cap (which also bounds any synthetic cycle);
    currents: re-read the local vector at every cell, dominant-axis
    steps, a zero vector ends the walk. The walked path carries width 2
    (walked cell + one perpendicular neighbor: orthogonal to the
    dominant axis of the walk's first step — row-major steps gain a
    column neighbor, column-major gain a row neighbor) for the first
    floor(len/2) cells, width 1 for the rest. In-grid cells only.
    *downstream* and *currents* are mutually exclusive; exactly one must
    be given (a ValueError otherwise, matching the v0.5 contract)."""
    if downstream is not None:
        d = np.asarray(downstream)
        H, W = d.shape
        n_cells = H * W
        flat = d.ravel()
        oy, ox = int(origin[0]), int(origin[1])
        cur = oy * W + ox
        walked = []
        for _k in range(1, WATER_MAX_CELLS + 1):
            cur = int(flat[cur])
            if not 0 <= cur < n_cells:
                break
            walked.append(divmod(cur, W))
    elif currents is not None:
        cu = np.asarray(currents[0], dtype=np.float64)
        cv = np.asarray(currents[1], dtype=np.float64)
        H, W = cu.shape
        walked = [(yy, xx) for yy, xx, _k in _field_walk(
            int(origin[0]), int(origin[1]), cu, cv, H, W, WATER_MAX_CELLS)]
    else:
        raise ValueError("packet_water_walk needs a downstream pointer "
                         "or a currents field")
    # the width neighbor is orthogonal to the walk's dominant axis of
    # the FIRST step (row-major steps -> column +1, column-major ->
    # row +1 — the same convention as the wind ray), so a +x walk
    # carries its width on the row axis and the width never degenerates
    # onto the next walked cell. A single-cell walk falls back to
    # column +1.
    perp = (0, 1)
    if len(walked) >= 2:
        dy = walked[1][0] - walked[0][0]
        dx = walked[1][1] - walked[0][1]
        if abs(dx) > abs(dy):
            perp = (1, 0)
    cells = []
    half = len(walked) // 2
    for i, (yy, xx) in enumerate(walked):
        cells.append((yy, xx))
        if i < half:
            py, px = yy + perp[0], xx + perp[1]
            if 0 <= py < H and 0 <= px < W:
                cells.append((py, px))
    return _dedupe(cells)


def packet_animal_disk(center, H: int, W: int) -> list[tuple[int, int]]:
    """Spec §7.2 v0.6 animal packet: the FILLED Euclidean disk of radius
    ANIMAL_RADIUS_CELLS (center included) around the packet's disk
    center — the origin frontier cell plus a uniform offset drawn by the
    engine from _ANIMAL_DISK (one draw per packet, the v0.5 animal range
    semantics). In-grid cells only."""
    cy, cx = int(center[0]), int(center[1])
    return [(cy + dy, cx + dx) for dy, dx in _FILLED_ANIMAL_DISK
            if 0 <= cy + dy < H and 0 <= cx + dx < W]


def packet_jump_disk(center, H: int, W: int) -> list[tuple[int, int]]:
    """Spec §7.2 v0.6 jump packet: the filled Euclidean disk of radius
    JUMP_DISK_RADIUS (~28 cells; 29 with the landing center) around the
    jump landing — replaces the v0.5 single-pixel landing. In-grid cells
    only."""
    cy, cx = int(center[0]), int(center[1])
    return [(cy + dy, cx + dx) for dy, dx in _FILLED_JUMP_DISK
            if 0 <= cy + dy < H and 0 <= cx + dx < W]


def maybe_jump(view: dict, T: float, rng: Stream
               ) -> tuple[int, int] | None:
    """Spec §7.2 jump: the per-round roll
        P = 1 - (1 - jump_rate * JUMP_SCALE) ^ T
    (the per-year rate clipped to [0, 1] — a rate > 1/yr surely jumps
    this round; single T-conversion policy, spec §4). On success the
    uniform (dy, dx) offset of ONE cell within JUMP_RADIUS_CELLS of a
    source cell (the Euclidean jump disk) is returned; the CALLER
    applies it to a randomly chosen FRONTIER cell (its own pinned draw —
    e.g. a child stream or a distinct index) and deposits the jump
    share there as a filled disk, clipping out-of-grid offsets. On
    failure (None) the caller folds the jump share into the local
    channel (spec verbatim).

    Draw addressing (pinned): roll at (clock=0, index=0), disk offset
    at (clock=0, index=1)."""
    jr = view.get("jump_rate")
    if not isinstance(jr, (int, float)) or isinstance(jr, bool):
        jr = 0.0
    P = 1.0 - (1.0 - min(max(float(jr) * JUMP_SCALE, 0.0), 1.0)) ** T
    if not rng.bernoulli(P, 0, 0):
        return None
    return _JUMP_DISK[rng.randrange(len(_JUMP_DISK), 0, 1)]


# ── §7.3 establishment gate (per-packet form) ──────────────────────────


def round_probability(p_yr, T: float):
    """The spec §4 single T-conversion policy: a per-year probability
    p_yr becomes the per-round event probability
        P = 1 - (1 - p_yr) ^ T
    (continuous compounding; never the invalid (1 - p)^T discrete form
    — spec §4 critic findings 1/2/12/13). p_yr is clipped to [0, 1].
    Scalar or vectorized over p_yr."""
    p = np.clip(np.asarray(p_yr, dtype=np.float64), 0.0, 1.0)
    return 1.0 - (1.0 - p) ** T


def packet_mean_f(f_hab, cells, beta: float = EST_BETA) -> float:
    """Spec §7.3 v0.6: mean(f_hab^beta) over the packet's candidate
    cells — the packet-level establishment habitat. *f_hab* is the
    world-grid suitability field (the engine's cache.f_worst — exactly
    what the v0.5 establish read); *cells* are world (y, x) pairs. Cells
    are summed in sorted (row-major) order — the hard-rule: deterministic
    float accumulation. beta = 0 makes the packet stress-blind
    (mean of 1s = 1)."""
    vals = [float(f_hab[y, x]) for y, x in sorted(cells)]
    if not vals:
        return 0.0
    if beta != 1.0:
        vals = [v ** beta for v in vals]
    return sum(vals) / len(vals)


def packet_probability(mean_f: float, establish_rate: float, T: float,
                       in_memory: bool = False) -> float:
    """Spec §7.3 v0.6: the per-packet founding probability
        p_yr = establish_rate x mean_f      (vanguard gate: mean_f <
                                                EST_F_MIN -> 0)
        P    = 1 - (1 - p_yr) ^ T            (the §4 single-T policy)
    down-weighted x MEM_PENALTY when the packet's candidate cells
    include a recently-failed target (colonization memory, spec §7.3)."""
    if mean_f < EST_F_MIN:
        return 0.0
    P = round_probability(float(establish_rate) * float(mean_f), T)
    if in_memory:
        P *= MEM_PENALTY
    return P


def establish(rain, f_hab, occupancy, establish_rate: float, T: float,
              rng: Stream) -> tuple[np.ndarray, np.ndarray]:
    """Spec §7.3 establishment gate, PER-CELL form — retained verbatim
    as the vanguard semantics' defining kernel (sink cells below
    EST_F_MIN never convert); the v0.6 engine drives founding through
    the per-PACKET gate (packet_probability) instead. Per cell with
    rain of the lineage and no occupying instance of the lineage (the
    one-instance-per-lineage-per-cell invariant, §3 — *occupancy* = 1
    where ANY instance of this lineage holds the cell; other lineages
    never block):
        rain_frac = d / (d + RAIN_HALF)
        p_yr      = establish_rate * f_hab * (1 - occupancy) * rain_frac
        P_round   = 1 - (1 - p_yr) ^ T
        GATE: P_round = 0 where f_hab < EST_F_MIN (settled 0.3)
    On success the cell gets N = EST_N0. Returns (N_new, founded_mask):
    N_new is EST_N0 on the founded cells and 0 elsewhere; founded_mask
    marks every cell where rain converted — whether a founded cell JOINS
    the founder's instance or MINTS a new one (X-cloning, owner ruling)
    is the engine's component-connectivity decision, not kernel math.

    Vanguard accounting (B5): cells below the gate are sinks — rain
    arrives every round and never converts; they draw too (p = 0,
    deterministically never convert), so the index mapping below is a
    stable bijection. Draw addressing (pinned): candidates (rain > 0 &
    ~occupancy) in row-major order; candidate k draws at
    (clock=0, index=k)."""
    rain = np.asarray(rain, dtype=np.float64)
    f_hab = np.asarray(f_hab, dtype=np.float64)
    occupancy = np.asarray(occupancy, dtype=bool)
    cand = (rain > 0.0) & ~occupancy
    idxs = np.flatnonzero(cand)                     # row-major pinned order
    rain_frac = rain / (rain + RAIN_HALF)
    p_yr = float(establish_rate) * f_hab * rain_frac
    p_yr = np.where(f_hab >= EST_F_MIN, p_yr, 0.0)  # the §7.3 gate
    P = round_probability(p_yr, T)
    N_new = np.zeros(rain.shape, dtype=np.float64)
    founded = np.zeros(rain.shape, dtype=bool)
    N_flat, P_flat, found_flat = N_new.ravel(), P.ravel(), founded.ravel()
    for k, idx in enumerate(idxs):
        i = int(idx)
        if rng.bernoulli(float(P_flat[i]), 0, k):
            N_flat[i] = EST_N0
            found_flat[i] = True
    return N_new, founded


def decay_rain(rain, view: dict) -> np.ndarray:
    """Seed bank (spec §7.3): rain carryover into the NEXT round.
    Cells of a lineage with the "persistent" seed_bank trait carry
    their rain over with the SEEDBANK_KEEP decay; transient rain (or no
    seed_bank trait) EXPIRES each round — the field is replaced by the
    next round's fresh deposits (vanguard sink cells therefore refill
    every round). Pure function of (rain, view)."""
    rain = np.asarray(rain, dtype=np.float64)
    if str(view.get("seed_bank") or "").lower() == "persistent":
        return SEEDBANK_KEEP * rain
    return np.zeros_like(rain)
