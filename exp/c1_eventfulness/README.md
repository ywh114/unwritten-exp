# C1 — eventfulness

## Goal

The cure for the LLM's soap-opera bias: one mechanical roll sets the
*quantity* of notable events in a chronicle interval; the model supplies
only the *content*.  The zero-inflated Poisson sampler is calibrated per
timescale (week / season / year); the conditioned arm feeds the exact
count to the LLM with quiet-interval few-shots ("the barley came in
fine").  The unconditioned arm proves the bias exists.

## API

Library home: `capability.eventfulness` (promoted 2026-07-20 per lab spec §6).

- **`SCALES`** — per-timescale (π, λ) calibration: `"week"`, `"season"`,
  `"year"`.
- **`sample_count(stream, clock, scale, regime)` → int** — one draw from
  the zero-inflated Poisson.  Knuth's algorithm, deterministic index plan.
- **`target_distribution(stream, scale, regime, n)` → list[int]** — n
  draws for reference-distribution comparison.
- **`IntervalChronicle`** — pydantic schema: `notable_events: list[str]`,
  `texture_line: str`.
- **`build_prompt_unconditioned(scale, label)`** /
  **`build_prompt_conditioned(scale, label, k)`** — prompt constructors.
- **`run_arm(client, stream, intervals, *, conditioned)` → ArmReport** —
  runs one arm over all intervals, returns per-interval results + cost log.

## Demo

`uv run python -m exp.c1_eventfulness demo --seed 1 [--replay] [--json]`

Runs both arms over 100 intervals (40 weeks + 35 seasons + 25 years),
200 LLM calls total when recording.  Per-scale ASCII histograms compare
unconditioned vs. conditioned count distributions, and the five checks
prove: obedience ≥ 95%, conditioned matches the sampler's target
distribution (χ² p > 0.01), quiet-is-normal, bias-demonstrated
(unconditioned zero-rate < conditioned), barley-is-fine (≥ 1 quiet
chronicle with genuine texture).

Cost table (tokens-in / cached / out, dollars) is printed per arm and
total.

## Verdict

**works** (2026-07-20).  15 tests: sampler (zero-rate, mean monotonicity,
determinism, regime scaling, Knuth index plan), prompt construction
(exact count, quiet form, few-shots), χ² helper (pooled sampler-vs-self
p > 0.01 over 500k samples, biased distribution fails), stub-transport
arms (obedience smoke test), cassette round-trip (record/replay
identical counts, replay miss raises).  Reviewer fixes: demo mode bug
(never recorded), cost-line field names, quiet-target statistic, χ²
sample-size bug, few-shot message structure.

Measured on the recorded run (200 calls, T1-flash, seed 1):
**obedience 1.000** (T1-flash suffices); unconditioned zero-rate
**0.000** — the model never says "nothing happened" (35/35 seasons and
23/25 years returned exactly 3 events: the soap-opera bias, measured);
conditioned zero-rate **0.410** (target ≈ 0.40); χ² per scale passes.

## Spec-notes

`docs/spec-notes/2026-07-20-c1-eventfulness-calibration.md`: final (π, λ)
constants per scale (untuned from spec starting values), measured bias,
obedience rate, cost.

## Cost (T1-flash, 200 calls, recorded cassette)

| arm | calls | tokens in | cached | out | dollars |
|-----|-------|-----------|--------|-----|---------|
| both (total) | 200 | 65,494 | 50,944 (78%) | 17,174 | **$0.0070** |
