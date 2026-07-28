# M5 — clock & forces (world-blind sampler)

Interface doc. M5 turns a parent Node into a descendant Node: the g-clock,
the three forces, and the speciation gate. World-blind per the rebuild
plan: no ecogeographic coupling — stress/population arrive as a
`Condition` parameter from the caller (rounds pass real values; the
backbone passes benign defaults).

## The clock

- **g is in generations.** `gen_time_years(mass_kg) = GT_COEFF × mass^0.25`
  (standard generation-time allometry; constants in allometry.toml
  `[life_history]` — mouse ~0.4 yr, deer ~3 yr, whale-grade ~18 yr).
- **Per-lineage rate multiplier** ~ lognormal(0, σ_RATE) drawn once per
  lineage from its K1 substream — fast radiators AND living fossils (both
  tails, tested).
- **Stress raises g accrual**: `Δg_eff = Δg_base × (1 + STRESS_G_BOOST ×
  condition.stress)` — stressed lineages run more generations under
  selection per unit time. Sign-tested.
- **g\* speciation gate**: per-clade seeded cutoff, lognormal around
  G_STAR_MEDIAN generations (seeded variance = radiation tempo).
  `classify(g_since_split, g_star)` → species beyond, subspecies below.
  Boundary-tested both sides.

## Mutation magnitude ∝ f(g) — the novelty tail

- `step_scale(g) = 1 + g / G_REF` (leaky linear, no cap).
- **Tier ramp (leaky, no hard unlock)**: labile axes move at any g; steady
  axes are scaled by `1 − exp(−max(0, g − G_STEADY_ONSET)/G_STEADY_RAMP)` —
  effectively frozen at low g, smoothly open at high g (the planted test:
  low-g lineages never move steady axes, high-g lineages do). Invariant
  and clade-steady axes never move.
- **Heavy tail**: per-step jump probability `p_novel(g) = P_NOVEL_MAX ×
  (1 − exp(−g / G_NOVEL))` — a leaky 10% asymptote, so the tail stays a
  TAIL even at deep g (uncapped, every deep-g step went novel and
  selection could never win — the M7 convergence test caught this).
- **N/A is sticky**: N/A axes are never perturbed (M2 semantics).

## The three forces (per evolve step of Δg generations)

Every axis carries `adapt_weight` ∈ [0,1] (M1 schema addition; TOML
override, block-default otherwise). It is the force selector: weight 1 =
pure adaptive, 0 = pure decorative. RFC §4: "the weight spectrum decides
which force dominates."

1. **Drift** — seeded random direction, magnitude σ × step_scale(g) × √Δg,
   mean 0. Applies to every mutable axis.
2. **Stress descent** — exponential approach toward the clade center
   (world-blind stand-in for descending the stress gradient; rounds supply
   real gradients): `Δ = (c − x)(1 − exp(−Δg × DESCENT_RATE))`, only on
   adapt_weight > 0 axes, scaled by weight.
3. **Runaway** — per-clade seeded constant direction r ∈ {−1,+1} on
   decorative axes (adapt_weight == 0) only: `Δ = r × σ × RUNAWAY_RATE ×
   Δg`. Predictable within a clade, arbitrary between.

Share ratios from `Condition(stress, isolation)`: raw weights
`descent = 2·stress`, `drift = (1 + 2·isolation)(1 − stress)`,
`runaway = 0.3`, normalized. Large+stressed → descent-dominated (drift
quiets — selection is nearly the only force); small isolate →
drift-dominated; benign → slow mixed. Matches RFC §4's table.

Per mutation kind: gaussian/log_gaussian as above (log space for the
latter); ratio = multiplicative exp(step); enum_redraw = redraw with
probability `1 − exp(−Δg × ENUM_RATE × step_scale)` (directionless — drift
only); weighted_set = jitter weights ∝ step, renormalize.

`edge_delta` records the per-axis force decomposition
`{axis: {drift, descent, runaway}}` — the attribution tests read this, and
it is the audit trail v1 lacked.

## API

```python
evolve(parent, pack, stream, dg_base, condition,
       clade_center=None, runaway_dir=None) -> Node
gen_time_years(mass_kg, rate_mult) -> float
rate_multiplier(stream) -> float          # lognormal, both tails
g_star(stream) -> float                   # per-clade speciation cutoff
classify(g_since_split, g_star) -> Rank   # species / subspecies boundary
share_ratios(condition) -> Shares
```

## Metrics checkers added (M11 registry)

- `g_clock` — g monotonic nondecreasing root→leaf; gen_time ordering
  (megafauna lineage > small lineage). Planted: inverted g flagged.
- The remaining M5 acceptance (sister distance ≈ σ, between > within,
  attribution) is tested directly on `evolve` in test_m5.py; tree-level
  versions land with M7's real trees.
