# 2026-07-19 — K3 verdict: demotion policy

**Amends:** design spec §3.4 (hysteresis / demotion — the four
undetailed items from the design conversations).
**Source:** `exp/k3_collapse/field.py` `coarsen()` function; measured
on the 12-resident village-square fixture with `seed=1`.

## Question

When an individual exits the render distance it is demoted from a
concrete person back into a crowd-field component.  The demotion policy
decides *what seeds that component* — the design spec explicitly
leaves this blank and delegates the decision to K3.

Two policies are compared here:

- **(a) last-position anchor** — pin the individual at its exit position
  with fresh isotropic diffusion σ²·dt.
- **(b) schedule-snap** — evolve the individual forward from its exit
  position under its day-cycle `Schedule` (K2 time-periodic attractors:
  market morning → fields day → tavern night → home), then place a
  diffusion-spread component at the resulting position.

## Experiment

The 12-resident village-square fixture from the K3 demo is collapsed
to 12 identities (seed 1).  After "walk away for 12 hours" (dt = 0.5
days, σ = 1.0 / √day), each policy produces a crowd field.

Schedule-snap uses a proper 4-segment day-cycle `Schedule` per resident
(period 1 day: home [0, 0.25) → market (60, 55) [0.25, 0.5) → fields
(15, 80) [0.5, 0.75) → tavern (85, 60) [0.75, 1.0); θ = 3.0/day,
σ = 1.0; "home" = each resident's prior mean).  Reproduction:
`tmp/k3_demotion_numbers.py` (throwaway script, git-ignored).

**Measured numbers** (seed 1, dt = 0.5 d, exit mixture mean = (58.3, 26.9)):

| metric                            | last-position     | schedule-snap        |
|-----------------------------------|-------------------|----------------------|
| total mass                        | 12.0 (exact)      | 12.0 (exact)         |
| mixture mean                      | (58.33, 26.93) — preserved exactly (shift 0.00) | (57.88, 43.98) — pulled 17.1 toward the day-cycle anchors |
| mixture cov trace                 | 1132.1            | 195.9 (5.8× tighter) |
| mass in market rect at dawn       | 2.0 / 12          | 5.0 / 12             |
| mass in fields rect at dawn       | 0.0               | 0.0 (correct: morning is market, not fields) |

Read: last-position leaves 12 smears around the exit points and learns
nothing from the elapsed half-day; schedule-snap pulls the population
back onto the day-cycle — at dawn the market rect holds 5 of 12 instead
of 2, the mean has moved 17 units anchor-ward, and positional
uncertainty is ~6× smaller because OU reversion (σ²/(2θ) asymptote)
compresses spread instead of accumulating it.  The mean shift is not a
filtration violation: positions committed at SILHOUETTE/IDENTITY tier
live on the collapse log; the coarsened field is a *representation*,
not a fact — and the schedule itself is part of the entity's committed
skeleton, so honouring it is mandatory, not optional.

## Verdict

**Recommendation for the engine:**

1. **Entities with committed schedules** (residents with a known daily
   routine) **MUST** use schedule-snap.  The schedule is part of the
   entity's committed skeleton (identity facts on the collapse log);
   the demotion anchor must honour it.  Otherwise the entity
   "forgets" its routine on walk-away, which contradicts the
   filtration guarantee that *facts never un-commit*.

2. **Entities without a schedule** (transient silhouettes, strangers
   at the market who were never refined to identity) use
   last-position.  There is no committed schedule to violate, and
   pure diffusion is the least-presumptive re-coarsening.

3. **The re-coarsening anchor is `sigma` and `dt`** — the demotion
   adds σ²·dt isotropic diffusion to each component.  `sigma` is a
   world constant (how fast an unobserved person's location
   diffuses); `dt` is wall-clock time since exit.  This replaces the
   design spec's unspecified "relaxation" with a concrete, testable
   parameter.

This answers all four undetailed design-spec items:
1. *Demotion timing beyond the ε rule:* instant at d+ε — no grace
   bubble (the hysteresis ε is the grace bubble).
2. *The re-coarsening anchor:* schedule-snap for scheduled entities,
   last-position for unscheduled.
3. *Tier-3 → what:* a single-component Gaussian conditioned on the
   committed identity facts, with isotropic diffusion spread.
4. *In-flight interactions:* out of scope for K3 (see K5 for
   promise-based interruption / reflex-layer behaviour).

## Design-spec amendment target

- §3.4 (hysteresis / demotion): replace "Unwritten" with this policy.
- §3.1 (schedules machinery): connect to re-coarsening anchor.
- §8.6 (reflex layer): in-flight demotion defers to the promise ledger
  (K5) for interrupt semantics.
