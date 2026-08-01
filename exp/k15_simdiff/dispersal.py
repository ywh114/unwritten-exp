"""K15 engine — spec §7 dispersal (pure functions + named constants).

The round-3 dispersal step of the flora rounds: stress-gated emission
(§7.1), the four deterministic channel deposit kernels (§7.2) and the
establishment gate that converts rain into N and founds new instances
(§7.3). Pure functions of (state arrays, the lineage DerivedView,
channel shares); the only draws are the jump roll and the establishment
Bernoullis, both from the per-(round, instance) K1 Stream the engine
passes (spec §7.2: ``Stream(seed, "k15.disperse", f"{t}:{instance_id}")``
with a child stream per channel — e.g. ``rng.child("jump")``,
``rng.child("establish")``). No stream is ever constructed here and
every draw address (clock, index) is pinned (see maybe_jump /
establish), so replay is byte-identical. Never uuid/random/time/np.random.

Cell addressing (resolved): (y, x) INT PAIRS for every deposit-dict key
and every element of *sources* (the np.argwhere(mask) convention). The
engine's D8 downstream pointer is a separate FLAT-index field (spec
§5.0) and is consumed internally by deposit_water. (Flat ints would
need the grid width to flatten, and the pinned deposit_animal signature
carries no grid, so (y, x) keeps every kernel addressable.)

Deposits are stress-blind and deterministic (spec §7.2, critic finding
15): rain is cheap and abundant, per-propagule draws are a performance
trap. Each kernel returns dict[(y, x), float] of arrival rain;
overlapping deposits from several sources ACCUMULATE on the shared
cell. The engine owns the absorption rule (§3: rain landing on a cell
already held by another instance of the same lineage joins the
occupant's rain) and the §7.3 founding split (join vs mint) — both are
instance/component state, not kernel math.

Ambiguities resolved (recorded here for the spec log):

- share_E is the CHANNEL budget (E x dispersal_channels pmf weight).
  local spreads the whole share uniformly over the UNION neighborhood
  (spec verbatim); wind / water / animal deposit the full share PER
  SOURCE cell along that source's ray / walk / disk (spec verbatim
  d_k = share_E x ...), so a kernel with several sources can deposit
  more than share_E in total — rain is a normalized saturation
  fraction, not a particle budget.
- Wind lambda_w uses the speed of the source cell's mean vector:
  lambda_w = WIND_K x hypot(wind_u, wind_v) / sqrt(propagule_mass_mg).
  The wind ray is a STRAIGHT integer ray (Bresenham-style; direction
  fixed from the source's vector); the marine current walk RE-READS
  the field at every step (a streamline with dominant-axis single-cell
  steps).
- Establishment draw addressing: candidates (rain > 0 and no
  occupancy of an instance of the lineage) in row-major order;
  candidate k draws at (clock=0, index=k). Below-gate candidates draw
  too (p = 0 — deterministically never convert), so the index mapping
  is a stable bijection over the candidate set.
- maybe_jump returns the (dy, dx) offset only; the caller applies it
  to a randomly chosen source cell (its own pinned draw) and folds a
  failed roll (None) into the local channel.
- deposit_animal carries no grid (pinned signature): it returns the
  full disk without clipping; the caller drops out-of-grid keys when
  scattering into the rain field. The other kernels clip internally
  because they receive grid-sized fields.
"""

from __future__ import annotations

import math

import numpy as np

from kernel.hashrng import Stream

# ── spec §13 knobs (v0.3, settled values) ──────────────────────────────
COUNT_REF = 1e4             # emission normalization (propagules/yr)
EMIT_K = 1.0                # fugitive emission gain (stress gate)
EMIT_P = 1.0                # fugitive emission power
LOCAL_BIG = 0.5             # local share at/above which the spill is r=2
WIND_K = 1.0                # wind distance scale
WIND_MAX_CELLS = 40         # wind ray length cap (cells)
WATER_LAMBDA = 20.0         # water decay scale (cells)
WATER_MAX_CELLS = 40        # water walk length cap (cells)
ANIMAL_RADIUS_CELLS = 5     # animal stub disk radius (cells)
JUMP_SCALE = 1.0            # jump probability scale
JUMP_RADIUS_CELLS = 50      # jump disk radius (cells)
RAIN_HALF = 0.5             # rain half-saturation in rain_frac
EST_F_MIN = 0.3             # establishment habitat gate (settled 2026-08-01)
EST_N0 = 0.05               # founder density on conversion
SEEDBANK_KEEP = 0.5         # persistent-rain carryover decay


def _disk_offsets(radius: int) -> tuple[tuple[int, int], ...]:
    """Euclidean disk offsets of radius *radius*, center excluded,
    lexicographically sorted — a deterministic draw table (the jump
    roll indexes into it). The uniform-draw disk of spec §7.2."""
    return tuple(sorted(
        (dy, dx)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dy * dy + dx * dx <= radius * radius and (dy, dx) != (0, 0)))


_ANIMAL_DISK = _disk_offsets(ANIMAL_RADIUS_CELLS)
_JUMP_DISK = _disk_offsets(JUMP_RADIUS_CELLS)


def _as_cells(sources) -> list[tuple[int, int]]:
    """Normalize a *sources* argument to a list of (y, x) int pairs:
    an (N,2) int array (np.argwhere(mask)) or a sequence of 2-tuples;
    a single (y, x) tuple is accepted too."""
    a = np.asarray(sources)
    if a.ndim == 2:
        pass
    elif a.ndim == 1 and a.size == 2:
        a = a.reshape(1, 2)
    else:
        raise ValueError(
            "sources must be (y, x) pairs — an (N,2) array or a single "
            "(y, x) tuple")
    return [(int(y), int(x)) for y, x in a]


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


# ── §7.2 channel deposit kernels ───────────────────────────────────────


def deposit_local(mask, share_E: float, local_share: float
                  ) -> dict[tuple[int, int], float]:
    """Spec §7.2 local: the 8-neighborhood of the instance's cells
    (Chebyshev radius 1; radius 2 when the local channel share >=
    LOCAL_BIG), the instance's OWN cells excluded, the channel share
    spread uniformly over the union target set:
        d = share_E / |targets|   per target cell.
    Target cells outside the grid are dropped (the mask knows the
    grid). Empty mask -> {}."""
    mask = np.asarray(mask, dtype=bool)
    if not mask.any():
        return {}
    radius = 2 if float(local_share) >= LOCAL_BIG else 1
    targets = _cheb_dilate(mask, radius) & ~mask
    cells = np.argwhere(targets)
    if cells.size == 0:
        return {}
    d = float(share_E) / cells.shape[0]
    return {(int(y), int(x)): d for y, x in cells}


def deposit_wind(sources, share_E: float, wind_u, wind_v,
                 view: dict) -> dict[tuple[int, int], float]:
    """Spec §7.2 wind: per source cell, an integer ray along the
    source's mean-annual wind vector; cell k of the ray receives
        d_k = share_E * exp(-k / lambda_w)
        lambda_w = WIND_K * |w(s)| / sqrt(propagule_mass_mg),  k <=
        WIND_MAX_CELLS
    *wind_u / wind_v* are the (H,W) m/s mean-vector fields (spec §5.0);
    |w(s)| is the speed of the source's own mean vector (the ray
    direction is fixed from it — a straight ray, not a field walk). The
    ray stops at the grid edge. A zero vector at the source, or a plan
    with no (positive) propagule mass, emits no wind deposits (lambda_w
    is undefined there)."""
    u = np.asarray(wind_u, dtype=np.float64)
    v = np.asarray(wind_v, dtype=np.float64)
    H, W = u.shape
    mass = view.get("propagule_mass_mg")
    if not isinstance(mass, (int, float)) or isinstance(mass, bool) \
            or mass <= 0.0:
        return {}
    lam_den = math.sqrt(float(mass))
    out: dict[tuple[int, int], float] = {}
    for y, x in _as_cells(sources):
        uu, vv = float(u[y, x]), float(v[y, x])
        speed = math.hypot(uu, vv)
        if speed == 0.0:
            continue
        lam = WIND_K * speed / lam_den
        for yy, xx, k in _line_ray(y, x, uu, vv, H, W, WIND_MAX_CELLS):
            key = (yy, xx)
            out[key] = out.get(key, 0.0) + float(share_E) * math.exp(-k / lam)
    return out


def deposit_water(sources, share_E: float, downstream,
                  currents=None) -> dict[tuple[int, int], float]:
    """Spec §7.2 water: walk the D8 downstream pointer (fresh mode) or
    the monthly-mean current field (marine mode); step k receives
        d_k = share_E * exp(-k / WATER_LAMBDA),  k <= WATER_MAX_CELLS
    *downstream*: (H,W) int array of FLATTENED neighbor indices
    (-1 = outlet, spec §5.0): from each source, follow the pointers cell
    by cell; the walk stops at an outlet (-1), an out-of-range pointer,
    or the step cap (which also bounds any synthetic cycle).
    *currents* (marine): a (2,H,W) mean vector field — [0] = u,
    [1] = v; the walk RE-READS the local vector at every cell and
    advances one cell along its dominant axis (ties -> the row axis; a
    zero vector ends the walk). *currents* is used only when
    *downstream* is None; exactly one mode must be given."""
    if downstream is not None:
        d = np.asarray(downstream)
        H, W = d.shape
        n_cells = H * W
        out: dict[tuple[int, int], float] = {}
        flat = d.ravel()
        for y, x in _as_cells(sources):
            cur = y * W + x
            for k in range(1, WATER_MAX_CELLS + 1):
                cur = int(flat[cur])
                if not 0 <= cur < n_cells:
                    break
                key = divmod(cur, W)
                out[key] = out.get(key, 0.0) + float(share_E) \
                    * math.exp(-k / WATER_LAMBDA)
        return out
    if currents is None:
        raise ValueError("deposit_water needs a downstream pointer or "
                         "a currents field")
    cur = np.asarray(currents)
    if cur.ndim != 3 or cur.shape[0] != 2:
        raise ValueError("currents must be a (2,H,W) mean vector field")
    cu = np.asarray(cur[0], dtype=np.float64)
    cv = np.asarray(cur[1], dtype=np.float64)
    H, W = cu.shape
    out: dict[tuple[int, int], float] = {}
    for y, x in _as_cells(sources):
        for yy, xx, k in _field_walk(y, x, cu, cv, H, W, WATER_MAX_CELLS):
            key = (yy, xx)
            out[key] = out.get(key, 0.0) + float(share_E) * math.exp(-k / WATER_LAMBDA)
    return out


def deposit_animal(sources, share_E: float
                   ) -> dict[tuple[int, int], float]:
    """Spec §7.2 animal (v1 stub, no fauna): per source cell, the
    channel share spread uniformly over the Euclidean disk of radius
    ANIMAL_RADIUS_CELLS around the source, the source cell itself
    excluded (deposits never land on the instance's own cells — the
    local kernel's rule):
        d = share_E / |disk|   per disk cell.
    NO grid clipping: the stub's pinned signature carries no grid, so it
    cannot know H or W — the keys are the full disk (out-of-grid cells
    included, negative coordinates possible) and the CALLER (the
    engine, which knows the grid) drops out-of-grid keys when
    scattering into the rain field. Overlapping disks accumulate."""
    out: dict[tuple[int, int], float] = {}
    d = float(share_E) / len(_ANIMAL_DISK)
    for y, x in _as_cells(sources):
        for dy, dx in _ANIMAL_DISK:
            key = (y + dy, x + dx)
            out[key] = out.get(key, 0.0) + d
    return out


def maybe_jump(view: dict, T: float, rng: Stream
               ) -> tuple[int, int] | None:
    """Spec §7.2 jump: the per-round roll
        P = 1 - (1 - jump_rate * JUMP_SCALE) ^ T
    (the per-year rate clipped to [0, 1] — a rate > 1/yr surely jumps
    this round; single T-conversion policy, spec §4). On success the
    uniform (dy, dx) offset of ONE cell within JUMP_RADIUS_CELLS of a
    source cell (the Euclidean jump disk) is returned; the CALLER
    applies it to a randomly chosen source cell (its own pinned draw —
    e.g. a child stream or a distinct index) and deposits the jump
    share there, clipping out-of-grid offsets. On failure (None) the
    caller folds the jump share into the local channel (spec verbatim).

    Draw addressing (pinned): roll at (clock=0, index=0), disk offset
    at (clock=0, index=1)."""
    jr = view.get("jump_rate")
    if not isinstance(jr, (int, float)) or isinstance(jr, bool):
        jr = 0.0
    P = 1.0 - (1.0 - min(max(float(jr) * JUMP_SCALE, 0.0), 1.0)) ** T
    if not rng.bernoulli(P, 0, 0):
        return None
    return _JUMP_DISK[rng.randrange(len(_JUMP_DISK), 0, 1)]


# ── §7.3 establishment gate ────────────────────────────────────────────


def round_probability(p_yr, T: float):
    """The spec §4 single T-conversion policy: a per-year probability
    p_yr becomes the per-round event probability
        P = 1 - (1 - p_yr) ^ T
    (continuous compounding; never the invalid (1 - p)^T discrete form
    — spec §4 critic findings 1/2/12/13). p_yr is clipped to [0, 1].
    Scalar or vectorized over p_yr."""
    p = np.clip(np.asarray(p_yr, dtype=np.float64), 0.0, 1.0)
    return 1.0 - (1.0 - p) ** T


def establish(rain, f_hab, occupancy, establish_rate: float, T: float,
              rng: Stream) -> tuple[np.ndarray, np.ndarray]:
    """Spec §7.3 establishment gate: per cell with rain of the lineage
    and no occupying instance of the lineage (the one-instance-per-
    lineage-per-cell invariant, §3 — *occupancy* = 1 where ANY instance
    of this lineage holds the cell; other lineages never block):
        rain_frac = d / (d + RAIN_HALF)
        p_yr      = establish_rate * f_hab * (1 - occupancy) * rain_frac
        P_round   = 1 - (1 - p_yr) ^ T
        GATE: P_round = 0 where f_hab < EST_F_MIN (settled 0.3)
    On success the cell gets N = EST_N0. Returns (N_new, founded_mask):
    N_new is EST_N0 on the founded cells and 0 elsewhere (founded cells
    were unoccupied, so their N was 0); founded_mask marks every cell
    where rain converted — whether a founded cell JOINS the founder's
    instance or MINTS a new one (X-cloning, owner ruling) is the
    engine's component-connectivity decision, not kernel math.

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
