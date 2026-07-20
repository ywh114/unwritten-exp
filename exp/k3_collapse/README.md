# K3 — collapse

## Goal

Measurement semantics: turn K2 probability distributions into concrete,
committed facts through graduated, deterministic, hysteresis-gated
collapse — and later relax concrete individuals back into distributions
when they leave the observation frontier (coarsening).

Delivers the filtration invariant (design spec §3.4): coarse collapse
commits facts that every finer collapse must honour.  Information only
accumulates; it never revises.

## API

Library home: `kernel.collapse` (promoted 2026-07-19 per lab spec §6).

- **`Rect(x0, y0, x1, y1)`** — axis-aligned region.
- **`rect_mass(mean, cov, rect) -> float`** — exact probability of a 2-D
  Gaussian component inside a rect (bivariate-normal CDF via 64-point
  Gauss–Legendre quadrature; error < 1e-12).
- `Tier(IntEnum)`: `FIELD=0`, `SILHOUETTE=1`, `IDENTITY=2`.
  `HysteresisLadder(promote_radius, demote_epsilon)` —
  `tier_for_distance(dist, current) -> Tier`.
- **Crowd-field operations** (`field.py`):
  - `presence_count(field, rect) -> float`
  - `absence_renormalize(field, rect, *, hard_count=True) -> GMM`
  - `collapse_field(field, rect, stream, clock) -> list[Silhouette]`
  - `refine_identity(silhouette, residents, stream, clock, *,
    assigned_ids) -> Identity`
  - `coarsen(individuals, dt, sigma, *, policy, schedules) -> GMM`
- **`CollapseLog()`** — append-only audit trail; each record's
  `stream_digest` is a SHA-256 over the exact K1 draws the operation
  consumed (`digest_draws`), so changed draws are detectable.

## Demo

`uv run python -m exp.k3_collapse demo --seed 1 [--json]`

Six stages over a 12-person village-square fixture:
1. **Far:** presence_count ≈ 12.0
2. **Approach mid:** field → 12 silhouettes; ASCII map (60×25) with
   component means (`#`) and silhouette digits.
3. **Approach near:** silhouettes → 12 identities; ASCII map with
   initials; two outside-prior residents (Nina, Oscar) never assigned;
   positions unchanged from stage 2.
4. **Walk away:** coarsen under both last-position and schedule-snap
   policies; total mass = 12, mixture mean preserved.
5. **Search empty / partial rect:** empty rect → identity operation;
   partial rect → component reweighting with hard-count renorm.
6. **Hysteresis:** distance series oscillating around the boundary
   without flicker.

## Verdict

**works** (2026-07-19).  17 tests: rect_mass exactness (ρ=0 closed form
to 1e-10, vs 200k MC to 1.5e-3, total-plane ≈ 1.0), presence/absence
conservation (hard-count renorm, soft-count shrink, zero-mass protection),
collapse determinism (same seed → identical, seed+1 → different),
**filtration invariant 1e5 trials** (position unchanged, prior density
nonzero, no double-assignment, zero failures), refine→coarsen =
identity+diffusion to 1e-9, hysteresis anti-flicker, identity conditioning
(outside prior never assigned over 1000 trials, no double-assignment over
500), and K2 integration (evolve-then-collapse consistent).

## Spec-notes

`docs/spec-notes/2026-07-19-k3-demotion-policy.md` answers all four
undetailed design-spec items (§3.4):
- Schedule-snap for entities with committed routines; last-position
  for transient silhouettes.
- Re-coarsening anchor is σ²·dt isotropic diffusion.
- Demotion is instant at d+ε (hysteresis ε is the grace bubble).
