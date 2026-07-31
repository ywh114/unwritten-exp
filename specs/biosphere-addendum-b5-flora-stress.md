# Biosphere addendum B5 — flora stress (P7)

v0.1 — 2026-07-30 — proposal

Amends the flora RFC (§2 derived products, §7 pass order); supersedes
the P7 paragraph of `docs/spec-notes/2026-07-29-k14-flora-build-plan.md`;
syncs `biosphere-addendum-b3-substrate-ground.md` §Consumers (stale
"no new axes" header, fire/shade deferrals); consumes B2 (productivity),
B3 (ground), B4 (water column, `water_ph`).

## 1. Intent (owner ruling 2026-07-30)

**Stress is a driver, not a filter — and it is SIGNED.** The pass
produces a continuous environmental stress per (taxon, cell, month)
on **[−1, +1]**: s > 0 costs (1 = lethal), s = 0 is the viability
breakeven, s < 0 is VIGOR (−1 = every axis optimal; the good end
keeps its gradient — "acceptable" and "ideal" do not both read 0).
It issues NO verdicts — no passable/costly/blocked masks (this
supersedes the build plan's P7 wording). Downstream consumers read
vital rates from it:

- **P8 dispersal**: the movement kernels (wind, water, local scatter,
  rare jumps) are stress-BLIND — wind doesn't know the map. Stress
  acts AFTER arrival, on establishment and survival, never on
  movement (water-riding upstream-of-waterfall rules are P8's own
  geodesic constraints, not stress).
- **Two-density accounting** (why there is no sink bleed):
  ESTABLISHED density — the persistent cloud, the drawn range —
  grows where s < 0 (toward the productivity carrying capacity,
  where P9 enters) and shrinks where s > 0. PROPAGULE RAIN — kernel
  arrivals — is cheap: production is effectively unlimited at L0
  granularity, so rain dying in a hostile cell costs the parent
  nothing and accumulates nothing. The VANGUARD is the leading edge
  where rain establishes at s ≈ 0: a small pioneer population that
  hangs on, ADAPTS (local trait drift lowers its s over rounds), and
  either founders a real population or flickers out — never a
  standing population bleeding into a sink.
- **Rounds (population)**: growth rate scales with max(−s, 0),
  mortality with max(s, 0); the same stress is the selection pressure
  that adapts the local population. A taxon with high stress
  everywhere is not illegal; it is rare, marginal, or adapting. No
  paper-taxon gates in `evolve`.
- **Density (internal) stress**: crowding is a ROUND-TIME term on the
  same scale, not a P7 input (P7 is a pure function of record ×
  world; density is state the rounds own):
  `s_realized = s_env + c · (total demand / N)`, N = the cell's
  productivity carrying capacity. Per-capita growth ∝ −s_realized.
  Equilibrium: every resident's realized growth hits zero together,
  so CLOSE suitabilities coexist at a ratio (the weaker is squeezed,
  not excluded — its shrinking density relieves the crowding that
  was killing it) and only LARGE margins take over. Competition "via
  productivity" is literal: N is the density term's denominator. The
  constant c lives in the rounds/P9 spec.
- **P9 competition**: enters through the density term above (P9's
  `suit` is −s). P7 itself never reads the productivity fields.

The one near-absolute: the **medium boundary** (a land plan on an
ocean cell, a submerged plan on dry land) costs ≈ 1 always, modulo the
B3 magic-class exemptions (LEY-FED, PHASE-ROOT, BUOYANT, mangrove
dual-domain). This is a very high cost, still not a deletion.

**Stat settling is dev-time, not engine machinery.** Writing P7 will
expose mis-authored preset stats; we eyeball the 35 presets' stress
maps and hand-fix. No audit reports, no expectation tags, no
realized-niche fitting, no viability gates (an earlier brainstorm
proposed these; rejected as circular and against authored-traits
discipline).

## 2. The primitive and its form

`s_env(record, cell, month) → [−1, +1]` — a pure, vectorized function
(build plan decision 2). Rounds integrate over 12 months and add the
density term (§1); the game queries one date. **No per-taxon state is
persisted**: the function
evaluates lazily over the persisted world components (§3) and the
species record. This makes storage flat in taxon count (150 species ≈
3–5 s; the ~10³-species radiated tree ≈ 30 s, batchable by plan-shared
terms), keeps the game able to reconstruct everything, and makes
determinism trivial (no persisted per-taxon state to desync; K1 draws
live in the rounds, not here).

**Resolution**: anchor (256²). The RFC §8 budget forbids per-taxon
evaluation at delivery res (~100× over); delivery res is masks and
display, via the existing upsample/pointwise-rederive convention.

**Placement** (owner ruling 2026-07-30): the stress MATH is
organism-agnostic and lives in `kernel/stress/` (shared by flora and
fauna — not under any tree experiment). The adapter (load world
components, evaluate per record) lives in K15 sim-diff, which also
owns dispersal/cover/rounds; K14 (`k14_worldprod`) keeps only the
world-side component products of §3. This supersedes the build plan's
`world/stress.py` module path.

## 3. World inputs (all existing products)

Climate (K11, monthly): `c_T_monthly`, `c_P_monthly`, growing season,
flood pulse (D0), `h_salinity` (water cells), HAND, insolation implicit
in T (no separate light field at L0).

Ground (B3, anchor): the full 42-class d2 vector. **Reduced once per
world** (RFC §8 rule 2) to effective-property rasters via the
consume-time softmax over −d2 dotted with the class property rows:
`eff_retention`, `eff_nutrient`, `eff_rooting_m`, `eff_sal_add` (None
underwater → the water's own `h_salinity`), `eff_hard`, `eff_loose`.
Plus the already-persisted `ground_ph` and B4's `water_ph` (which is
delivery-res; the anchor variant derives the same way from the anchor
mix — `mix_ph` is pointwise).

Ground pH vs water pH by plan medium: land plans read `ground_ph`,
water plans read `water_ph`; mangrove-grade reads both (dual-domain).

## 4. The stress function

Each stratum yields a suitability `f ∈ [0, 1]` (1 = optimal, 0 =
lethal); strata multiply, and the emitted stress is signed:

```
F = Π_strata f_stratum          F ∈ [0, 1]
s_env = 1 − 2·F                 s ∈ [−1, +1]
```

The product keeps Liebig tail-dominance (one failed non-compensable →
F ≈ 0 → s ≈ +1) AND the good end's gradient (F near 1 only when every
axis is near-optimal → s → −1); s = 0 is the breakeven the vanguard
sits at. The additive climate distance below reads `f = 1 − s_clim`;
the one-sided ground/tail terms read `f = 1 − sat(term)`.

### 4.1 Climate stratum (monthly, compensable — fauna §3 shape)

Weighted saturating distance of the month's (T, P) from the `[niche]`
metadata baseline (`temp_opt_c`/`temp_breadth_c`,
`moisture_opt`/`moisture_breadth` — content-only, never drifted):

```
s_clim(m) = Σ_i w_i · sat(|env_i(m) − opt_i| / breadth_i)   i ∈ {T, P}
```

- Tolerance TRAITS widen breadths: `drought_tolerance` widens the
  moisture breadth (asymmetric: more slack on the dry side);
  `growing_season_req` adds a saturating term against the D0 growing
  season length.
- **Phenology gates which months count**: `winter_deciduous` → cold
  stress only in leaf-on months (from `leafout_month`);
  `drought_deciduous` → drought stress relaxed in the dry season;
  evergreen → year-round. Bloom-month frost (bloom window from
  `bloom_start_month`/`bloom_length_months` vs that month's T) is an
  extra cost term — costly, never lethal.
- `photosynthesis` path interacts with cold: C4/CAM carry a cold
  penalty term, C3 none.

### 4.2 Ground stratum (annual, one-sided saturating terms)

Each is a one-sided `sat()` against the effective properties of §3:

| term | env side | trait side | note |
|---|---|---|---|
| water availability | monthly P × `eff_retention` | moisture need, `drought_tolerance` | marries 4.1's P term to the soil |
| waterlogging | `eff_retention` ≈ 1, low HAND | `waterlogging_tolerance` | high tolerance INVERTS to a requirement (mangrove/wetland grades) |
| fertility | `eff_nutrient` | `fertility_requirement` | low requirement on rich soil is not penalized |
| pH | `ground_ph` / `water_ph` (by medium) | `ph_tolerance` (§5.1) | the calcicole/calcifuge split |
| salinity | `eff_sal_add` / `h_salinity` | `salinity_tolerance` | underwater rows read the water |

### 4.3 Tail terms (steep; cost → ≈1, never a verdict)

- **Rooting**: `root_depth_m` vs `eff_rooting_m` — saturating excess,
  not a cutoff.
- **Anchoring**: need CALCULATED from `height_m` × `woodiness` (K13
  ruling: calculable axes are calculated) vs `eff_hard` for holdfast
  plans (kelp, sponge) and exposed-site trees.
- **Medium boundary**: land plan on water cell and vice versa ≈ 1
  always; mangrove dual-domain reads both sides; B3 exemptions apply.
- **Submerged light**: submerged aquatic plans read B4 `photic_depth`
  vs column depth — a seagrass below the photic zone costs ≈ 1.

### 4.4 Deferred terms

- **Fire** (`fire_strategy`): no fire-regime world field exists
  anywhere; fire is the A2 fauna round's regime. P7 does not consume
  this axis. (Revisit post-A2.)
- **Shade** (`shade_tolerance`): no canopy exists before P9. P7's
  light term is insolation/photic only; shade as COMPETITION is P9's
  layered capacity.
- **Light on land**: v1 has no separate insolation product; T carries
  the latitudinal signal. Flag, don't build.

## 5. Content changes

### 5.1 New axis: `ph_tolerance`

The calcicole/calcifuge split — a first-order niche axis the set was
missing (B3 §Consumers already names it; this defines it).

```toml
[axis.ph_tolerance]
block = "niche"
tier = "steady"
value_type = "scalar"
mutation = "ratio"
sigma = 0.1
bounds = [0.0, 1.0]       # POSITION: 0 → obligate calcifuge (opt ≈ pH 4),
                          # 1 → obligate calcicole (opt ≈ pH 9)
plan_scope = "all"
consumers = ["stress"]
salience = 0.2
```

Position, not width: pH optimum = 4.0 + 5.0 × value (spanning the
world's clip), breadth fixed ±1.0 pH unit, one-sided saturating
distance outside. Position must DRIFT so radiation can move lineages
across the split — this is why it is a trait and not `[niche]`
metadata (metadata never drifts; descendants of a calcifuge would be
locked forever). The name keeps B3's `ph_tolerance` for spec
continuity. Generalist/specialist breadth variation: open question
(§7), v1 fixed.

### 5.2 Pigment chemistry replaces authored `flower_color`

(owner ruling 2026-07-30 — `flower_color` demotes from drifted trait
to DERIVED)

Record gains:

- `pigment_pathway` — **order-rank invariant** enum: `none` /
  `anthocyanin` / `carotenoid` / `betalain`. Legality constraint:
  anthocyanin ⊥ betalain (mutually exclusive in real biochemistry —
  sampler legality, the house pattern, like CAM↔succulence). Slots
  into the build plan's order tuple "chemistry" slot.
- `pigment_expression` — **labile scalar** [0, 1]. The new drift
  substrate for runaway and F3 pollinator coupling (was: the
  `flower_color` enum).

`flower_color` becomes a DERIVED named bucket, computed at derive time
from pathway × expression × `ph_tolerance` position:

- `none` or expression ≈ 0 → white / green / dull (wind set)
- anthocyanin: hue slides with pH optimum — acid → red/pink,
  neutral → purple, alkaline → blue (hydrangea logic); expression
  scales saturation (white ↔ deep)
- carotenoid: yellow/orange/red, pH-stable
- betalain: red/yellow, pH-stable, NEVER blue/purple

Consumers are untouched: naming stems (`stems_flora.toml` color pools),
id, tell all read the derived `flower_color` exactly as before — F0
naming stays world-blind (ph position is a record property; no world
needed, which is why range-mean or per-cell color was rejected:
naming precedes dispersal, each stage commits).

**Superseded**: `palettes.toml` per-plan color legality → pathway
gating (wind-pollinated dull set = `none`/low expression). The
35-preset migration is mechanical (authored color → nearest
pathway + expression): oak `green` → `none`, iris blue → anthocyanin
high-expression alkaline-leaning, etc.

**F3 coupling**: bee-blind red falls out — bee syndrome × high
anthocyanin expression in the red zone is penalized, bird syndrome
rewarded. UV flavonol co-pigmentation (bee-visible guides): reserved
as a second expression scalar; hook named, NOT built in v1.

**Per-cell pH shift** (a hydrangea population bluing on acid soil) is
a P9 RENDERING rule over the cover map, not a P7 product and not a
record property.

## 6. Persistence, budget, determinism

- Persisted: nothing per-taxon. The world components of §3 are already
  on disk (`world.npz`, `derived.npz`); the ground property reduction
  is 7 anchor rasters, computed once per world, persistable as part of
  the D0 products (game-loadable, per decision 2's shared-precompute
  clause).
- Budget: ~10 axis terms × 65k cells × 12 months ≈ 10⁷ elementwise
  ops per taxon — tens of ms vectorized; climate stratum batched
  across taxa (all share the 12 monthly world fields).
- Determinism: pure functions of (world dump, record). No draws.

## 7. Open questions

1. `ph_tolerance` breadth: fixed ±1.0 v1 — key off a generalist flag
   later, or leave?
2. Climate weights `w_T`/`w_P` per plan: one global pair v1, or
   plan-level overrides already?
3. Waterlogging inversion (high tolerance → requirement): does the
   same inversion apply to drought for obligate-aquatic-leaning land
   plans, or is waterlogging special?
4. Insolation: does P7 need a real light field before P9 (montane
   shading exists in K11?), or does T suffice through v1?

## 8. Acceptance (seed 1)

1. Determinism: identical rerun, identical stress values; the same
   primitive callable with month = m for arbitrary m.
2. Mangrove-grade: lowest stress in the high-HAND coastal band —
   graded, not binary.
3. Xeric-grade: high stress in wetland cells (fen/bog/gleysol
   dominant), low in its arid band.
4. Kelp-grade: low stress only on hard, shallow, photic bottom
   (`eff_hard` ∧ bathymetry < `photic_depth`); deep soft bottom ≈ 1.
5. A calcifuge-authored preset scores lower stress on podzol/bog cells
   than on rendzina/caliche cells; a freshwater taxon in bog-blackwater
   (low `water_ph`) cells scores per its `ph_tolerance` position.
6. Pigments: anthocyanin ⊥ betalain rejected at sampling; derived
   `flower_color` matches the legacy enum's consumers (stems, id, tell)
   with no naming regressions on the 35 presets.
7. Budget: full 150-species annual evaluation ≤ 5 s on seed 1.
8. Signed scale: an every-axis-near-optimal cell for a given taxon
   reads s < 0 (vigor gradient preserved — a merely acceptable cell
   reads closer to 0); the breakeven s = 0 separates establishment
   from decline in the rounds contract.
