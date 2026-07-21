# 2026-07-20 — C1 verdict: eventfulness calibration

**Amends:** engine spec §5.2 (eventfulness calibration) — confirms the
sampled-quantity design with measured numbers; supplies the calibration
constants.
**Source:** `exp/c1_eventfulness` recorded run, seed 1, 200 calls at
T1-flash (`deepseek-v4-flash`, thinking disabled).

## Measured bias (the reason C1 exists)

The unconditioned arm ("write the chronicle for this {scale}") **never
returned a quiet interval: zero-rate 0.000 across all 100 intervals**,
and the count distribution was degenerate — 35/35 seasons and 23/25
years returned *exactly 3 events*. The model does not have a "quiet"
mode; it has a "three things happened" mode. Any backfill pipeline
that asks the LLM how much happened will get soap opera.

## Conditioning works

The conditioned arm (exact-k prompt + quiet few-shots, counts rolled by
the K1 sampler):

- **Obedience 1.000** — every conditioned chronicle returned exactly the
  requested count. **T1-flash suffices; no thinking tier needed.**
- Conditioned zero-rate **0.410** vs. sampler pooled P(0) ≈ 0.40.
- χ² per scale vs. target distribution: passes at p > 0.01 for
  week/season/year.
- Quiet outcomes are well-formed: k=0 yields an empty event list plus a
  genuine texture line ("The village settled into its rhythms.").

## Calibration constants (final — untuned from spec starting values)

| scale | π (P(non-quiet)) | λ (Poisson rate) | P(0) | mean |
|---|---|---|---|---|
| week | 0.35 | 0.7 | 0.65 | ≈ 0.60 |
| season | 0.60 | 1.0 | 0.40 | ≈ 1.20 |
| year | 0.85 | 1.3 | 0.15 | ≈ 1.96 |

No tuning was needed: conditioning works at these values. They are now
the engine's reference calibration (amend §5.2's "mass concentrated at
zero" with this table). Regime multiplier scales π and λ (war, famine);
clamp π at 0.99.

## Cost (200 calls, recorded cassette)

65,494 tokens in / 50,944 cached (78%) / 17,174 out — **$0.0070**.
The few-shot/shared system prefix caches well under the L2 discipline.
