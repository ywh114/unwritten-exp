# Biosphere Addendum B10 — occupancy and stress dynamics (rewrite L2/L3 core)

**Status:** owner-ruled 2026-08-04 (design conversation; four rulings
folded in: prodscale f, cap = n=1 limit, strict-zero marginal-benefit
pressure with time-reversal locality, stress-relief-only selection).
**Depends on:** B7 (mass + crown geometry), B8 (capacity accounting —
REFINED here, §5), B9 (the species view + intrinsic stress), plan §5.
**Scope:** the occupancy data model (L2) and the stress/pressure
semantics (L3 core) — designed in ONE pass because the crowding fields
and the pressure semantics co-design each other (the shade step, §4,
only exists if the canopy field carries height structure). Dispersal
mechanics, population bookkeeping detail, speciation/g (L4), staged
activation (L5, ticket 0019) are follow-ons.

## 1. The occupancy data model (L2)

The canonical sim output remains the **per-cell, per-lineage biomass
density field** (standing ruling; the game layer reads it).

Per cell, the occupancy state is:

- **Structural layers with coverage budgets** — geometric, from B7
  crown/footprint geometry: the canopy layer packs
  ~cell_area / crown_area adults regardless of productivity; ground
  cover bounds swards and mats likewise. Coverage budgets are SPACE,
  not productivity.
- **The productivity pool** (B8): cell pool = productivity × X ×
  cell_ha, linear in p, the biomass guardrail. B2 pins the absolute
  scale (unit 1.0 = a productive class; tropical moist forest 2.5;
  terrestrial range ≈ 0–2.5 + bounded bonuses).
- **Substrate demand**: per-lineage demand weighted by the cell's
  substrate mix matching the lineage's preferences (multiplicative —
  "a sward covering all of its preferred substrate has a reasonable
  mass" is the unit-calibration anchor).
- **Crowding fields**, one per shared resource, computed from the
  occupancy state and NOTHING else: the canopy crowding field is
  **height-stratified** (the local canopy height profile — required
  for the shade step, §4); ground-cover and substrate crowding are
  share fields. Every crowding field is a pure, probeable function.

Demand is painted in stage order (the 0019 stages land in L5); each
stage sees the pool/coverage remainder the earlier stages left. L2
owns the accounting; L5 owns the order.

## 2. The three stress families, one paradigm

Every stress is a scalar with provenance, a pure function of (species
view, cell fields, crowding fields) — probeable by nudge-and-recompute
(§4 needs this). Three families, summed through one channel:

- **Environmental** — cell fields vs the view's climate envelope.
  A STATIONARY target: the drought does not fight back, adaptation
  overcomes it, the stress decays as tolerance lands.
- **Intrinsic** — B9 §4 (landed in L1): the view's own proportions,
  plateau-with-cliffs, authored exception bubbles.
- **Competition** — the crowding fields, one stress type per shared
  resource: `competition:canopy` (shade — a function of the lineage's
  height RELATIVE to the local canopy profile), `competition:
  ground_cover`, `competition:substrate`. RECIPROCAL: when lineage A
  adapts to crowd better, B's crowding worsens and B adapts in turn.
  The arms race needs no special machinery — competition types are
  ordinary stress types with trait-wired provenance (canopy → height/
  crown; substrate → roots/substrate preference; phenology → leafout/
  bloom timing), and the arms race is the round loop running: crowding
  recomputed, stress applied, traits drift, crowding recomputed. The
  only true escapes are partitioning (different substrate, stratum,
  phenology) — which is why competition stress is per shared resource,
  or differentiation could not relieve it. Diversity is what an
  endless arms race leaves behind.

## 3. What stress does — exactly two effects

1. **Vital suppression**: birth down, death up — the population
   settles at a LOWER EQUILIBRIUM, not a cap hit, not a kill-switch.
   A stressed lineage persists at reduced density.
2. **Evolutionary pressure with provenance** (§4): trait backprop
   through the responder wiring, the trace recording WHY.

## 4. Pressure semantics (owner rulings 2026-08-04)

- **pressure = stress × marginal relief.** The marginal relief of a
  wired trait move is the local change in the stress per unit trait
  change, PROBED (nudge the trait, recompute the stress, read the
  difference) — stress functions are pure, so this is deterministic
  and cheap. Benefits from traits may be NONLINEAR (height pays
  nothing until the crown clears the canopy shading it); the probe
  feels this because the stress functions carry the real landscape.
- **Strict zero.** Zero marginal relief → zero pull. A deep-understory
  tree is NOT pulled toward height (an evolutionary leap with no
  benefit in the middle); it adapts toward shade tolerance and
  low-energy survival, which pay immediately. A tree one meter below
  the canopy top feels the step and is dragged through. Emergent
  lineages are born at gaps and edges, not by grinding.
- **Low stress → no pull** (this was never written down; recorded
  here): in a low-stress environment there is NO selection pressure
  toward any niche. Stress relief is the only currency selection
  spends.
- **Selection force only.** Marginal-benefit pressure modulates the
  selection force; drift and runaway stay UNDIRECTED. Valley
  crossings are theirs alone.
- **Time-reversal locality.** Evolution is after-the-fact history
  (closed-form, no ticks): moves may be temporally nonlocal —
  compressed generations, big steps — but every trajectory must
  decompose into locally motivated steps: non-decreasing benefit
  (selection) or neutrality (drift). A tree shooting up through a
  flat-benefit zone fails time-reversal (reversed, every intermediate
  step is unmotivated); a tree at the canopy step shooting through
  passes.

Note the unification: B9's plateau-with-cliffs intrinsic curve is
already marginal-benefit-shaped (flat inside the envelope — moving
buys nothing, no pull, drift dominates, no carcinisation; steep
outside — every step back pays). §4 is the general principle, derived
from the benefit landscape everywhere instead of hand-shaped per case.

## 5. The cap, derived (refines B8)

The lineage cap is the **n=1 limit of the crowding equilibrium**: a
lone lineage grows until its OWN crowding suppresses net growth to
zero. The cap is not a separate guardrail — it is the monoculture
solution of the same crowding function, so no guardrail can ever
disagree with the mechanism. Owner's prodscale f —
`f(p) = 5/4 − 4^(−p)` for p<1, `f(p) = 39/40 + p/40` for p≥1,
anchored f(1)=1 — is the CALIBRATION TARGET the crowding function is
shaped against at n=1. Against the real B2 scale: f(2.5) ≈ 1.04,
f(0.75) ≈ 0.90 — a rainforest canopy lineage cap is ~16% above a
temperate one while the cell pool is 3.3× larger; productivity buys
lineage count, never lineage size. The cell pool stays linear in p
(the biomass guardrail; headroom for staged rounds, 0019). The
scale knob L (lineage cap at unit productivity) starts at ≈ 0.5–0.75
of the cell pool at p=1 (Phase-2 probe: top-species per-cell median
share 75%) and is the one tuning knob.

The four owner quadrants fall out of f + stress-as-limiter, no
quadrant logic anywhere: high-p favorable → many lineages near unit
cap (rainforest: typical tree density, more species); high-p
unfavorable → few tolerant lineages capped near unit, pool headroom
unused as pure potential; low-p favorable → f falls slower than the
pool, the pool binds, near-monoculture (intended); low-p unfavorable
→ sparse mix of niche dwellers.

## 6. Acceptance cases (the L2/L3 test contract)

1. **A/B emergence**: cells A (rich) and B (poor) hold the SAME oak
   biomass (the lineage cap is nearly productivity-flat above unit);
   A's canopy leaves a large pool remainder → rich understory, B's
   canopy nearly exhausts the pool → barren forest. Emergent from the
   remainder + stage order, no understory penalty.
2. **Rainforest ≈ temperate**: a moist tropical cell and a temperate
   broadleaf cell pack ROUGHLY EQUAL adult canopy stems (crown packing
   is geometric); the tropical cell carries more saplings (productivity
   feeds turnover) and more canopy lineages, each holding fewer adults.
3. **Low-p favorable monoculture**: one well-adapted lineage settles
   at its DERIVED cap; the pool excludes competitors.
4. **The shade trap**: a lineage under a high canopy is pulled toward
   shade tolerance / low-energy survival, NOT height (zero marginal
   relief → zero pull); a lineage just below the canopy top is pulled
   through the step (strong marginal relief). Trajectories satisfy
   time-reversal locality.

## 7. Deferred

Dispersal mechanics and population bookkeeping detail (L3 remainder);
speciation, merging, the g currency (L4); staged activation, freezing
(L5, ticket 0019); the artifact (L6). Bubble DATA wiring into content
(0042 note). Migrating any constraints.toml threshold to intrinsic
stress (owner's call, not now).
