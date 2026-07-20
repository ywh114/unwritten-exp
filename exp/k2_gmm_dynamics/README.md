# K2 — gmm_dynamics

## Goal

The position kernel: 2-D Gaussian mixtures evolved by affine
drift–diffusion (per-axis Ornstein–Uhlenbeck) with analytic time-skip — no
ticking, ever. Time-periodic attractors (market morning / fields day /
tavern night) are piecewise-constant `Schedule`s; one full period is an
affine map per element, so k periods collapse to a closed-form geometric
series and evolving a century costs the same as evolving a minute.

## API

Library home: `kernel.gmm_dynamics` (promoted 2026-07-19 per lab spec §6).

- `GMM(weights, means, covs)` — mixture as numpy arrays (n,), (n,2),
  (n,2,2); `mixture_mean()`, `mixture_cov()`, `normalized()`,
  `total_mass()`. `Gaussian(mean, var)` builds a single component.
- `DriftField(mu, theta, sigma)` — axis-aligned OU field: attractor μ,
  mean-reversion θ ≥ 0, diffusivity σ ≥ 0. θ = 0 is exact pure diffusion.
- `Schedule(period, [(phase_start, DriftField), ...])` — field k applies on
  [τ_k, τ_{k+1}), wrapping at the period.
- `evolve(dist, t0, t1, field_or_schedule) -> GMM` — exact analytic
  time-skip. Under a schedule: partial head segment chain + k full periods
  (closed-form geometric series, guarded at A→1 / e→1) + partial tail.
  O(segments-per-period), independent of Δt. Weights pass through
  unchanged — mass conservation is exact by construction.
- `stationary(field) -> GMM` — mean μ, diagonal P∞ (σ_i²/2θ_i).
  `stationary(schedule, phase) -> GMM` — cyclostationary fixed point of the
  composed period map (m* = (I−A)⁻¹b, P*_ij = q_ij/(1−e_ij)) at phase 0,
  evolved forward to `phase`.
- `sample_at(dist, stream, clock) -> (x, y)` — deterministic sampling from
  a K1 `Stream`: component by `stream.uniform(clock, 0)`, two normals at
  disjoint high indices (2²⁰, 2²⁰+1), x = m + L·z with L = cholesky(P)
  (1e-12·I jitter on LinAlgError).
- `terrain.py` — the open-question experiment (see spec-notes).

## Demo

`uv run python -m exp.k2_gmm_dynamics demo --seed 1 [--json]`

50 villagers on the toy map (market / fields / tavern / home ring), each
with a role-based day schedule. The season (90 days) is crossed in ONE
`evolve` call per villager; ASCII density plots at dawn / noon / night show
the blob over the market at dawn, fields (+merchant market) at noon, and
the home ring at night. Prints mass conservation for Δt = 1 minute …
10,000 years (exactly 0.0 at every scale), a timing line for Δt = 1 minute
vs 1 century (ratio ≈ 2.4×, same order of magnitude — the O(1) claim), and
a PASS/FAIL verdict. Exit code 0 iff all checks pass.

## Verdict

**works** (2026-07-19). Test suite: mass conserved to 1e-9 (measured:
exactly 0.0) over Δt ∈ {1 min, 1 day, 1 year, 1 century, 10⁴ years} for
single fields and schedules; OU exactness vs. 20k-particle Euler–Maruyama
through a multi-segment schedule within MC tolerance; `stationary` (field
and schedule, any phase) is a fixed point of evolve to 1e-9 and long
evolves converge to it; associativity evolve(t0→t1)∘evolve(t1→t2) =
evolve(t0→t2) to 1e-9; 20k samples reproduce mixture moments within MC
tolerance, same stream+clock → identical sample, neighboring clocks
decorrelated (|r| < 0.02); day cycle: 35/38 farmers at the fields at noon,
50/50 villagers home-or-tavern at night; evolve over a century ≈ 2.4× the
cost of over a day (bound 50×); θ = 0 pure diffusion exact, θ → 0 clean
via expm1 forms.

## Spec-notes

Produced: `docs/spec-notes/2026-07-19-k2-drift-field-verdict.md` — how
much context-dependent drift field survives the closed-form requirement.
Compressed verdict:

- **Survives:** piecewise-constant patches with moment-matched component
  splitting at boundaries. Splitting a boundary-straddling Gaussian at the
  patch line, evolving each half under its own field, and recombining cuts
  the relative moment error from 0.19/0.39 (mean/cov, ignoring the
  boundary) to 0.07/0.09, with mass conserved to float tolerance.
  Re-splitting mid-horizon halves the error again at 2× the components —
  accuracy is bought with mixture growth, so a merge policy is mandatory.
- **Does not survive:** spatially continuous drift variation (that IS a
  PDE — no affine closed form), and zero-diffusivity walls as hard
  constraints (not affine). Model walls as patch graphs with boundary
  events instead.
- Error in the split strategy grows with horizon (0.07 → 0.33 mean-rel
  from Δt = 2 to 20) as diffusing mass re-crosses the boundary mid-skip;
  re-splitting is the remedy, merging is the budget.
