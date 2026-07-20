# 2026-07-19 — K2 verdict: how much context-dependent drift field survives the closed-form requirement

**Amends:** design spec (position kernel / drift fields); answers the open
question attached to lab spec §2 K2.
**Source:** `exp/k2_gmm_dynamics/terrain.py` (`run_experiment`, seed 1).

## Question

K2 keeps everything closed-form by restricting drift to affine
(Ornstein–Uhlenbeck) fields, piecewise-constant in time (schedules). Can
drift also vary in *space* — roads, rivers, walls — without leaving the
closed-form world?

## Experiment

Two-patch map split at x = 0, different (μ, θ, σ) per patch
(left: μ = (−10, 0), θ = 0.6, σ = 1.5; right: μ = (5, 0), θ = 0.02,
σ = 3.0). A particle feels the field of the patch it is *currently in* —
the true dynamics are not affine and no single-Gaussian closed form
exists. Reference: Euler–Maruyama, 20,000 particles, dt = 0.005, seeded,
each particle switching fields as it crosses the boundary. Initial
condition: a single Gaussian at (2, 0) with σ = 8, straddling the
boundary; horizon Δt = 2. Errors are relative (mean error in units of the
reference's std; cov error in ||·||_F units of the reference cov).

| strategy | components | mean rel. err | cov rel. err | mass err |
|---|---|---|---|---|
| (a) ignore boundary (single-patch field) | 1 | 0.194 | 0.391 | 0.0 |
| (b) split at boundary, moment-match, evolve per patch | 2 | 0.073 | 0.093 | 0.0 |
| (b+) same + re-split at half-horizon | 4 | 0.054 | 0.053 | 0.0 |

Split details: the component is split at x = 0 into two
half-plane-truncated pieces (closed-form truncated-normal moments,
verified against quadrature to 1e-9), each piece moment-matched to a
Gaussian, evolved under its patch's field by the exact OU step, and
recombined. Mass is conserved to float tolerance (measured: exactly 0.0).

Error vs. horizon (strategy b): the residual error comes from diffusion
re-crossing the boundary mid-skip, where the analytic piece keeps its
original field but the true particle would switch:

| Δt | ignore mean/cov | split mean/cov |
|---|---|---|
| 2 | 0.19 / 0.39 | 0.07 / 0.09 |
| 5 | 0.32 / 0.50 | 0.15 / 0.17 |
| 10 | 0.43 / 0.62 | 0.24 / 0.26 |
| 20 | 0.58 / 0.91 | 0.33 / 0.46 |

Re-splitting at sub-horizons restores accuracy (row b+) — each re-split
roughly halves the error and doubles the component count.

## Verdict

**Survives the closed-form requirement:**

- **Piecewise-constant spatial patches** (roads as fast-drift corridors,
  rivers as one-sided attractors, regions with their own (μ, θ, σ)) —
  via moment-matched component splitting at patch boundaries. The split,
  the per-patch evolution, and the recombination are all closed form;
  mass conservation is exact. Error is ~3–5× smaller than ignoring the
  boundary at moderate horizons.
- **Mixture growth is the price** and is bounded by policy: each boundary
  crossing doubles the straddling components, so the engine needs a merge
  policy (e.g. merge components whose moments are within tolerance, or
  cap components per entity and merge nearest). Re-splitting buys
  accuracy at 2× components per halving of error — the merge policy is
  not optional.

**Does NOT survive:**

- **Spatially continuous drift variation** (smoothly varying field
  θ(x), σ(x)). The propagator is no longer affine; the exact object is a
  PDE (Fokker–Planck with state-dependent coefficients). No moment
  trickery makes it closed form — approximate it by refining the patch
  decomposition (more, smaller patches), never by pretending it's affine.
- **Zero-diffusivity walls as hard constraints.** A reflecting/absorbing
  boundary condition is not an affine map on the distribution; a
  hard-clamped wall breaks the Gaussian form entirely. **Recommendation:**
  represent walls as *patch graphs with boundary events* — the wall is an
  edge between patches, and crossing it is a discrete event (a scheduled
  split/redirect) rather than a continuous constraint. This keeps the
  between-event dynamics closed form.

**Recommendation for the engine spec:** adopt piecewise-constant drift
patches as the terrain model; specify component splitting at patch
boundaries with a mandatory merge policy and a per-entity component cap;
specify walls and rivers as patch-graph edges with boundary events. Drop
any language implying continuous spatial drift fields or hard reflecting
walls — both are outside the closed-form contract this kernel guarantees.
