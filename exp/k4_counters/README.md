# K4 — counters

## Goal

Analytic state variables — the deliberately trivial library. A counter is
a chain of anchors `(t, value, law, regime)` evaluated at t, never ticked:
`c(t) = f(c(t₀), Δt, regime flags)`. Committed events insert anchors.
This is the ontology rule made code: mechanical consequence + no identity
= counter, and the LLM never invents numbers — it only narrates why a
number moved and commits the event that inserts an anchor.

## API

Library home: `kernel.counters` (promoted 2026-07-19 per lab spec §6).

- Laws (`laws.py`, the entire function library — one page by spec):
  `Logistic(rate, capacity)`, `ExpDecay(rate, floor)`, `Step()`; each
  `value_at(c0, dt, rate_mult=1, cap_mult=1)`. All are exact flows:
  re-anchoring mid-segment changes nothing.
- `Counter(regimes=None)` with `set_anchor(t, value, law, regime, note)`,
  `value_at(t)`, `insert_event(t, delta=, scale=, law=, regime=, note=)`,
  `regime_shift(t, regime, note=)`. Regimes map a name to parameter
  multipliers (`{"harvest": {"rate": 2.0}}`); `""` is the default.
  `note` is provenance — later libraries (promise ledger, collapse log)
  supply it.

## Demo

`uv run python -m exp.k4_counters demo --seed 1 [--json]`

Granary fixture: grain grows logistically across a year with a harvest
regime shift; the granary burns on day 270 (exact 10× step-down anchor);
population is re-anchored at the burn with carrying capacity snapshotted
from post-burn grain — counters couple only at anchor insertion, never
continuously (continuous coupling would break the closed forms). ASCII
chart shows grain recover within the season while population still lags
at year's end. Checks: exact burn step, grain recovery ≥ 75%, population
≤ 50% of pre-burn, dense re-anchoring exact to 1e-9.

## Verdict

**works** (2026-07-19). 15 tests: law endpoints and known values, regime
multipliers (rate ×2 ≡ double time), event steps/deltas/law overrides,
re-anchor consistency to 1e-12, and the spec's done-when — evaluation
exact to float tolerance under fuzzed event sequences (40 random events,
100 continuity re-anchors, 500 probes, worst relative deviation < 1e-9)
— plus the page-limit test on `laws.py` (≤ 72 lines; currently 64).

## Spec-notes

None owed per lab spec §2. Observations for downstream libraries:

- **Coupling discipline:** counters must never reference each other
  continuously — that turns the library into an ODE system and kills the
  closed forms. Snapshot coupling at anchor insertion (the fixture's
  "famine revision") is the entire mechanism, and it is *enough*: the
  demo's lag emerges from a slow rate constant, not from feedback.
- **Who authors the laws:** initial law + parameters + regime table are
  content, authored per location at summon time like any other latent
  content (settles the design-spec §3.3 gap raised in conversation:
  at this coarseness, parameter provenance is a content task, not a
  design hole).
- The anchor chain is the save format (design spec §10.3
  `counters(t₀ anchors)`) — `Counter.anchors` round-trips directly.
