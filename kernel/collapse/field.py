"""K3 — crowd-field collapse operations.

A *crowd field* is a K2 GMM whose weights are expected entity counts
(Σ w = N, not 1).  Collapse turns field mass into silhouettes, and
silhouettes into named individuals — deterministically, auditably, and
without ever revising a committed fact (filtration invariant).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from kernel.gmm_dynamics.gmm import GMM
from kernel.hashrng import Stream

from kernel.collapse.geometry import Rect, rect_mass
from kernel.collapse.log import CollapseLog, digest_draws
from kernel.collapse.tiers import Tier, TIER_LABELS

# Draw-index plan per silhouette: silhouette i ∈ [0, N) owns indices
# [i * BAND, (i+1) * BAND).  Index 0 = component selection.
_SIL_BAND = 1000
_IDX_PICK = 0           # component-selection uniform
_IDX_NORMAL_BASE = 1    # first pair of normal draws for rejection
_REJECT_CAP = 100

# refine_identity draws at _IDX_REFINE_BASE + (silhouette number parsed from
# the id), so two silhouettes refined at the SAME clock still get independent
# uniforms.  Bands stay below this base for crowds under 1000 silhouettes.
_IDX_REFINE_BASE = 1_000_000

_DEFAULT_SIGMA = 1.0   # per-day diffusion for coarsen

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Silhouette:
    id: str
    position: tuple[float, float]
    component_idx: int


@dataclass(frozen=True)
class Resident:
    id: str
    name: str
    prior: GMM  # typically one component, but the API allows mixtures


@dataclass(frozen=True)
class Identity:
    id: str
    name: str
    position: tuple[float, float]
    silhouette_id: str


# ---------------------------------------------------------------------------
# Crowd-field queries
# ---------------------------------------------------------------------------


def presence_count(field: GMM, rect: Rect) -> float:
    """Expected entity count inside `rect`."""
    total = 0.0
    for k in range(field.n_components):
        total += field.weights[k] * rect_mass(field.means[k], field.covs[k], rect)
    return float(total)


def absence_renormalize(field: GMM, rect: Rect, *,
                        hard_count: bool = True) -> GMM:
    """A search of `rect` found nothing.  Each component's weight is scaled
    by its outside-rect probability.  With `hard_count` the total
    population N is preserved by renormalising."""
    w = np.empty(field.n_components)
    for k in range(field.n_components):
        p = rect_mass(field.means[k], field.covs[k], rect)
        w[k] = field.weights[k] * (1.0 - p)

    total = float(w.sum())
    if total <= 0.0:
        raise ValueError("absence_renormalize: entire mass is inside rect — nothing left")

    if hard_count:
        N = float(field.weights.sum())
        w = w * (N / total)

    return GMM(w, field.means.copy(), field.covs.copy())


# ---------------------------------------------------------------------------
# Collapse: field → silhouettes
# ---------------------------------------------------------------------------


def collapse_field(field: GMM, rect: Rect, stream: Stream, clock: int, *,
                   log: CollapseLog | None = None) -> list[Silhouette]:
    """Coarse collapse — turn expected mass into concrete point silhouettes.

    Returns a deterministic list of `Silhouette` whose count is the
    rounded `presence_count`.  Each silhouette is independently
    rejection-sampled from its chosen component *conditional on the rect*.
    """
    count = int(round(presence_count(field, rect)))
    silhouettes: list[Silhouette] = []

    # pre-compute per-component mass-in-rect (for component selection)
    comp_mass = np.array([rect_mass(field.means[k], field.covs[k], rect)
                          for k in range(field.n_components)])
    comp_mass_total = float(comp_mass.sum())
    if comp_mass_total <= 0.0:
        return silhouettes

    comp_prob = comp_mass / comp_mass_total

    consumed: list[int] = []
    for i in range(count):
        base = i * _SIL_BAND
        sid = f"silhouette:{i:04d}"

        # component selection
        u = stream.uniform(clock, base + _IDX_PICK)
        consumed.append(base + _IDX_PICK)
        cum = 0.0
        chosen = 0
        for k in range(field.n_components):
            cum += comp_prob[k]
            if u <= cum:
                chosen = k
                break

        # rejection-sample the chosen component inside the rect
        m = field.means[chosen]
        c = field.covs[chosen]
        pos, n_attempts = _rejection_sample_gaussian(m, c, rect,
                                                     stream, clock,
                                                     base + _IDX_NORMAL_BASE)
        # u64 indices consumed by the rejection loop (see its docstring)
        for a in range(n_attempts):
            j1 = base + _IDX_NORMAL_BASE + 2 * a      # zx normal-call index
            j2 = j1 + 1                               # zy normal-call index
            consumed.extend((2 * j1, 2 * j1 + 1, 2 * j2, 2 * j2 + 1))
        silhouettes.append(Silhouette(id=sid, position=pos, component_idx=chosen))

    if log is not None:
        log.append(clock=clock, tier=TIER_LABELS[Tier.SILHOUETTE],
                   region_or_entity=str(rect),
                   facts={"count": count},
                   stream_digest=digest_draws(stream, clock, consumed))

    return silhouettes


# ---------------------------------------------------------------------------
# Refine: silhouette → identity
# ---------------------------------------------------------------------------


def refine_identity(sil: Silhouette, residents: list[Resident],
                    stream: Stream, clock: int, *,
                    assigned_ids: set[str] | None = None,
                    log: CollapseLog | None = None) -> Identity:
    """Fine collapse: pick which resident this silhouette *is*.

    Residents are weighted by their prior pdf at the silhouette position.
    Ones with zero density or already assigned are excluded.
    The silhouette's position is **never changed** (coarse commits
    constrain fine collapse).
    """
    if assigned_ids is None:
        assigned_ids = set()

    x, y = sil.position
    weights = np.empty(len(residents))
    for i, r in enumerate(residents):
        if r.id in assigned_ids:
            weights[i] = 0.0
        else:
            w = _gmm_pdf_at(r.prior, x, y)
            weights[i] = w

    total = float(weights.sum())
    if total <= 0.0:
        raise ValueError("no resident with non-zero density at silhouette position")

    prob = weights / total
    try:
        sil_num = int(sil.id.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        sil_num = 0
    refine_idx = _IDX_REFINE_BASE + sil_num
    u = stream.uniform(clock, refine_idx)
    cum = 0.0
    chosen = 0
    for i in range(len(residents)):
        cum += prob[i]
        if u <= cum:
            chosen = i
            break

    r = residents[chosen]
    ident = Identity(id=r.id, name=r.name, position=sil.position,
                     silhouette_id=sil.id)

    if log is not None:
        log.append(clock=clock, tier=TIER_LABELS[Tier.IDENTITY],
                   region_or_entity=sil.id,
                   facts={"name": r.name, "position": list(sil.position)},
                   stream_digest=digest_draws(stream, clock, [refine_idx]))

    return ident


# ---------------------------------------------------------------------------
# Coarsen: silhouettes / identities → crowd field again
# ---------------------------------------------------------------------------


def coarsen(individuals: list[Silhouette | Identity],
            dt: float, sigma: float = _DEFAULT_SIGMA, *,
            policy: str = "last-position",
            schedules: dict[str, object] | None = None) -> GMM:
    """Demotion: turn concrete individuals back into a crowd field.

    Two policies (the spec-note compares them):
      "last-position"  — pin each individual at its exit position with
                         isotropic σ²·dt diffusion.
      "schedule-snap"  — evolve each individual from its exit position
                         under its K2 Schedule (passed via `schedules`).

    Both policies preserve total mass = N.  "last-position" also preserves
    the mixture mean exactly; "schedule-snap" deliberately does NOT — the
    attractor drift pulls mass back toward the day-cycle anchors (that is
    the point of the policy).
    """
    n = len(individuals)
    if n == 0:
        return GMM(np.array([1.0]), np.zeros((1, 2)), np.eye(2) * sigma * sigma * dt)

    means = np.array([list(ind.position) for ind in individuals])
    cov = np.eye(2) * sigma * sigma * dt

    if policy == "schedule-snap" and schedules is not None:
        from kernel.gmm_dynamics.dynamics import evolve
        covs = np.tile(cov[None, :, :], (n, 1, 1))
        for i, ind in enumerate(individuals):
            sched = schedules.get(ind.id if hasattr(ind, 'id') else "")
            if sched is not None:
                g = GMM(np.array([1.0]), means[i:i+1], covs[i:i+1])
                g2 = evolve(g, 0.0, dt, sched)
                means[i] = g2.means[0]
                covs[i] = g2.covs[0]
        return GMM(np.ones(n), means, covs)
    else:
        covs = np.tile(cov[None, :, :], (n, 1, 1))
        return GMM(np.ones(n), means, covs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rejection_sample_gaussian(mean: np.ndarray, cov: np.ndarray, rect: Rect,
                               stream: Stream, clock: int,
                               idx_start: int) -> tuple[tuple[float, float], int]:
    """Draw from N(mean, cov), rejection-sampled to fall inside `rect`.

    Returns (position, attempts_used).  At most _REJECT_CAP attempts; falls
    back to the rect-clamped component mean (counted as cap attempts).
    Attempt a uses normal calls at indices idx_start+2a (zx) and
    idx_start+2a+1 (zy); each Stream.normal(clock, j) call consumes the u64
    draws at indices 2j and 2j+1.
    """
    try:
        lower = np.linalg.cholesky(cov)
    except np.linalg.LinAlgError:
        lower = np.linalg.cholesky(cov + 1e-12 * np.eye(2))

    for attempt in range(_REJECT_CAP):
        zx = stream.normal(clock, idx_start + 2 * attempt)
        zy = stream.normal(clock, idx_start + 2 * attempt + 1)
        x = float(mean[0] + lower[0, 0] * zx + lower[1, 0] * zy)
        y = float(mean[1] + lower[0, 1] * zx + lower[1, 1] * zy)
        if rect.x0 <= x <= rect.x1 and rect.y0 <= y <= rect.y1:
            return (x, y), attempt + 1

    # fallback: clamp component mean to rect
    x = float(max(rect.x0, min(rect.x1, mean[0])))
    y = float(max(rect.y0, min(rect.y1, mean[1])))
    return (x, y), _REJECT_CAP


def _gmm_pdf_at(gmm: GMM, x: float, y: float) -> float:
    """PDF of a GMM at (x,y) — written out, no library call per spec."""
    total = 0.0
    for k in range(gmm.n_components):
        total += gmm.weights[k] * _gaussian_pdf(gmm.means[k], gmm.covs[k], x, y)
    return total


def _gaussian_pdf(mean: np.ndarray, cov: np.ndarray, x: float, y: float) -> float:
    """2-D Gaussian pdf at (x,y) — explicit formula, no linalg det/solve
    inlined for speed in the 1e5-trial filtration test."""
    dx = x - float(mean[0])
    dy = y - float(mean[1])
    a, b = float(cov[0, 0]), float(cov[1, 1])
    c_off = float(cov[0, 1])
    det = a * b - c_off * c_off
    if det <= 0.0:
        return 0.0
    inv_det = 1.0 / det
    # quadratic form: [dx, dy] · P⁻¹ · [dx, dy]ᵀ
    q = inv_det * (dx * dx * b - 2.0 * dx * dy * c_off + dy * dy * a)
    return math.exp(-0.5 * q) / (2.0 * math.pi * math.sqrt(det))
