# K15 sim-diff engine (flora rounds) — build spec v0.4

2026-08-01. v0.3 folds the stat-settling pass (35 presets × seeds 1-3):
substrate capacity split (§5.1, §6), dormancy-gated worst month (§5.1),
settled knobs (§13), and the moisture-niche authoring scale (§13).
v0.2 folded the critic review (23 findings): the population
math (§6), verdict aggregation (§5.2), cache design (§5.1), the commit
handshake (§9) and the dispersal deposit model (§7) were rewritten.

Builds on: B5 (`biosphere-addendum-b5-flora-stress.md`), the K13/K14/K15
restructure spec-note (2026-07-30), the owner rulings of
2026-07-31 → 2026-08-01 (conversation), and the landed code:
`kernel/stress/`, `exp/k15_simdiff/req_flora.py`,
`exp/k15_simdiff/stress_adapter.py` (env side, B5 §8 green),
`exp/k13_treegen/interface.py` (Instance/StressVerdict/KingdomSim/
TreeAuthority protocol), `exp/k13_treegen/flora/sim.py` (FloraSim:
derive/select/mutate/vital).

This document specs the missing piece: the ENGINE — genesis rain,
dressing, dispersal, density rounds, and the TreeAuthority commit.
It pins mechanisms and names every knob; knob VALUES marked (cal) are
settled in the interactive stat-settling pass, not here.

---

## 1. Scope and non-goals

In: flora rounds at anchor resolution (256²) on a STATIC world (v1:
world fields do not evolve across rounds). One kingdom (flora).
Out (later addenda): fauna A-rounds, P9 canopy light field
(`canopy_density` is the provisional basis, already derived), fire
regime, ley/lift sources (channel machinery exists; no world sources),
world evolution, intra-cell spatial structure.

## 2. Settled architecture (recap, normative)

- **X is space-blind.** K13 owns the tree and the organism-side
  interface (`KingdomSim.derive/select/mutate/vital`); it contains no
  cell field names. The sim owns space/time and dresses X into Y
  (an Instance) with range, density and pressure planes.
- **Stress is the only env→X channel.** Competition, productivity and
  (later) predation all arrive through stress — never as direct terms.
  Dispatch classes: `pressure:` / `pull:` / `ley:` / `lift:`.
- **The DerivedView is the seam.** Requirement names are env-defined
  (`req_flora.py`); select() reads, never computes. Every trait the
  engine reads directly rides the view (owner ruling 2026-08-01):
  dispersal_channels (pmf), propagule_mass_mg, propagule_count,
  jump_rate, seed_bank, crown_spread_m — plus the stress axes and
  height_m / woodiness for per-capita demand.
- **Commit is a handshake.** Each round the engine parses the instance
  list into per-instance gene views and hands them to the
  TreeAuthority, which may extend branches / split / register
  subspecies / mark extinct. The spatial state (N, rain, instance↔cell
  assignment) SURVIVES the commit untouched; only genes re-sync from
  the amended records via the changelog (interface RE-SYNC), instance
  ids are stable, merges re-key absorbed instances. Records amend
  gerrit-style with a reflog; names pin only at final commit.
- **Determinism (hard rule).** Every draw from `kernel.hashrng`
  streams keyed by (seed, context, round, id). No uuid, no random, no
  wall-clock. Processing order is pinned: instances in sorted
  instance_id order, cells in row-major order; per-(cell, lineage)
  establishment draws use child contexts in sorted lineage_id order.

## 3. Entities

```
Lineage    a tree record (species or subspecies), K13-side, space-blind
Instance   Y: one SPATIALLY CONTIGUOUS population of one lineage
           (lineage_id, instance_id, cells mask, N per cell,
           traits (WIP genes), pressure plane)
N(c)       established density per cell, [0,1] = share of the cell's
           flora cover this instance holds (NOT a propagule count)
rain(c)    transient propagule deposit per cell per round (cheap;
           the two-density accounting of the B5 amendment), a
           saturation fraction in [0,1) — never part of N until
           establishment converts it
```

Invariants:
- A cell holds at most ONE instance per lineage. Propagules of lineage
  L landing in a cell already occupied by another instance of L are
  absorbed into the occupant's rain (owner ruling: same-X ranges must
  not diffuse into each other — divergence requires separation).
- Instances are the mutation units: selection (select/mutate) acts per
  instance, cells within an instance share its WIP genes.
- No instance merges during rounds, ever. Merging is a commit-time
  decision (§9).

## 4. Round sequence (round length ROUND_YEARS = 100 (cal))

Per round t, in order:

1. **Verdict feed** — per instance: aggregate the instance's cached
   stress fields (§5) over its cells into one StressVerdict; select()
   → pressure plane; mutate() once per GENERATION (n_gen below), the
   same round pressure re-applied before each call (mutate clears it).
   n_gen = clip(ceil(ROUND_YEARS / gen_time), 1, N_GEN_CAP), with
   gen_time = 2·sqrt(height_m) (the backbone formula) — a duckweed
   drifts per generation, an oak barely per round (interface ruling:
   gen_time decides call frequency).
2. **Population update** — per instance × cell: density term, vital
   update, extinction floor (§6).
3. **Dispersal** — per instance: emission (stress-gated), channel
   deposit kernels, arrival rain; establishment gate converts rain → N
   and founds new instances (§7).
4. **Dressing** — recompute connected components PER INSTANCE over
   that instance's own cells; split instances whose cells disconnected
   (§8). Cross-instance adjacency is ignored by construction.
5. **Commit** — per-instance gene views → TreeAuthority; amend records
   (split/subspecies/extinct/merge); genes re-sync; spatial state
   survives (§9).

**Single T-conversion policy** (critic findings 1/2/12/13): every
per-year rate r (birth, death, stress mortality, establishment)
converts to per-round effect by CONTINUOUS compounding — survival
factors exp(−r·T), event probabilities 1 − (1 − p_yr)^T. No
(1−r)^T discrete compounding (vital() returns rates ≫ 1/yr for
short-generation plans; discrete compounding is invalid there).

## 5. Stress fields

### 5.0 World fields the engine adds to the context

Beyond `stress_adapter.WorldContext` (which it reuses), the engine
loads/derives once per world:
- **Capacity**: terrestrial (annual) and marine/freshwater (monthly →
  annual mean) productivity rasters at anchor (B2: productivity IS
  carrying capacity) from the K14 derived products.
- **Mean wind vector**: annual mean of c_wind_u/v, bilinear-upsampled
  to anchor via k14's `_upsample` (same convention as the adapter's
  storm proxy).
- **Downstream pointer**: a D8 pointer re-derived at anchor from the
  priority-flooded elevation (K11 hydrology function, deterministic) —
  the water channel's routing.
- **Currents**: the persisted monthly current payload (K11 persist
  convention; the adapter's private loader is promoted to a shared
  helper).

### 5.1 Per-instance cached fields (reduced form)

`stress_adapter.evaluate(view, ctx)` returns 13+2 tensors of
(12,H,W) float32 ≈ 47 MB — too large to cache per instance. The engine
caches the REDUCED form the rounds actually read (per (instance_id,
traits-hash), ≈ 3.9 MB):

```
m*(c)            = argmin_m F(c, m)                  (worst month)
F_worst(c)       = F(c, m*(c));  s_env(c) = 1 − 2·F_worst(c)
prov_r(c)        = f_r(c, m*(c))  per requirement r  (the provenance
                   at the cell's worst month — ONE aggregation for
                   both selection and demography, critic finding 6)
U(c)             = substrate_share: Σ_i w_i·Π_r f_r(class_i)
                   over the cell's top-3 ground-mix patches — the
                   CAPACITY split (§6), never a factor of F
                   (owner ruling 2026-08-01: the mix is three
                   physically present patches; the plant fills the
                   best patch to carrying cap, then the next —
                   capacity is split, suitability is best-of-class,
                   parameters are NOT softened)
```

The worst month is the worst GROWING month: months below GROW_T_C are
dormant for non-submerged plans — no T-distance, moisture-uptake or
waterlogging cost on those months (a taiga winter is not niche
distance; frozen ground does not waterlog roots). Submerged plans read
the annual bottom temperature and carry no dormancy.

Re-evaluation: after each round's mutate(), if the instance's view
drifted ≥ RE_EVAL_D (cal; the §9 distance metric) from the cached
fields' view, recompute. New instances inherit the founder's cache
(their traits start equal).

### 5.2 Verdict aggregation (instance → one verdict)

Per instance, per requirement r: prov_r = Σ_cells N(c)·prov_r(c) /
Σ_cells N(c) — density-weighted over established cells. The verdict is
`kernel.stress.compose(aggregated provenance)` (F = product,
s = 1 − 2F). An instance whose cells all hit the extinction floor this
round is retired before the next round's feed, so the feed never sees
an empty instance.

## 6. Population update (per instance × cell)

Per-capita demand and cell capacity:

```
percap   = crown_spread_m² · (1 + woodiness) / BIOMASS_REF   (cal)
D(c)     = Σ_instances N_i(c) · percap_i          (cell demand)
K(c)     = PROD_CAP_SCALE · annual_mean productivity(c)      (cal)
K_L(c)   = K(c) · U_L(c)    per-lineage capacity: the substrate
           share U from the §5.1 cache splits the cell's capacity
           BETWEEN lineages by where each can actually root —
           a heath and a calcicole on the same podzol-over-rendzina
           cell draw on different patches, not one shared pool
           (owner ruling 2026-08-01). Water plans: U = 1.
s_dens   = DENS_C · D_L(c) / K_L(c)    (the B5 capacity-denominator form:
           dimensionless, self-limiting, implements competition via
           productivity; clip to DENS_CAP; K_L(c) ≤ K_EPS with D > 0 →
           s_dens = DENS_CAP. D_L sums over instances sharing L's
           usable patches — v1: all instances in the cell, U-weighted
           by the SAME U_L; the per-pair patch overlap refinement is
           deferred)
s_real   = s_env(c) + s_dens(c)      (s_env from the §5.1 cache)
```

Vital update (B5: positive stress suppresses growth, negative stress
boosts it, mortality scales with max(s, 0); continuous compounding per
the §4 policy):

```
bscale   = clip(1 − s_real, 0, 1 + VIG_K)     (cal: VIG_K)
growth   = birth · bscale
mort     = death + DIE_K · max(s_real, 0)     (cal: DIE_K, per year)
N'       = clip(N · exp((growth − mort) · T), 0, 1)
```

- **Extinction floor**: N < N_FLOOR (cal) → cell abandoned (N = 0;
  rain keeps flowing). An instance with no cells is retired.
- **Design constraint** (calibration target): sustained s_real ≈ 0.3
  must give density half-life ≥ 5 rounds, so pressure adaptation gets
  rounds to climb: exp(−DIE_K·0.3·T·5) ≥ 0.5 → DIE_K ≲ 0.0028.
  (Continuous form; the v0.1 default violated its own constraint.)
- Negative s_real is opportunity, never immortality: it raises growth
  through bscale, it never lowers mort below the baseline vital rate.

## 7. Dispersal

### 7.1 Emission (per instance, stress-gated)

```
E = occupied_cells · (propagule_count / COUNT_REF) ·
    (1 + EMIT_K · max(mean_s_real, 0)) ^ EMIT_P        (cal: all three)
```
E is in normalized rain units (propagule_count is per-year and COUNT_REF
normalizes; the T years of rain within a round arrive as one integrated
deposit). E splits across channels by the dispersal_channels pmf.

### 7.2 Channel deposit kernels (deterministic; arrival stress-blind)

Only the jump roll and the establishment Bernoullis are stochastic —
the deposits themselves are deterministic kernels (rain is cheap and
abundant; per-propagule draws are a performance trap and an
implementation-divergence hazard, critic finding 15). Per channel,
target cells get deposit d(c) ∈ [0,1) (saturation fraction):

- **local** — the 8-neighborhood (radius 2 for local share ≥
  LOCAL_BIG (cal)): d = share_E, spread uniformly.
- **wind** — a ray along the source cell's mean annual wind vector:
  d_k = share_E · exp(−k / λ_w) for k = 1..WIND_MAX_CELLS (cal),
  λ_w = WIND_K · mean_speed_ms / sqrt(propagule_mass_mg) (cal: WIND_K).
- **water** — walk the §5.0 downstream pointer (fresh) or the
  monthly-mean current field (marine): d_k = share_E · exp(−k /
  WATER_LAMBDA) for k = 1..WATER_MAX_CELLS (cal: both).
- **animal** — v1 stub (no fauna): uniform disk,
  ANIMAL_RADIUS_CELLS (cal, default 5).
- **jump** — episodic (the pmf share is the packet size; jump_rate is
  the frequency, resolving the v0.1 doubling): per round, roll
  P = 1 − (1 − jump_rate·JUMP_SCALE)^T (cal); on success ONE uniform
  cell within JUMP_RADIUS_CELLS (cal, default 50) takes the jump
  share; on failure the share is redistributed to local.
  (jump_rate rides the DerivedView — v0.1 omitted it.)

Stochastic draws from `Stream(seed, "k15.disperse", f"{t}:{instance_id}")
children per channel; instances processed in sorted instance_id order.

### 7.3 Establishment gate (rain → N, founding)

Per cell with rain of lineage L (and no occupying instance of L):

```
rain_frac = d(c) / (d(c) + RAIN_HALF)              (cal: RAIN_HALF —
            the propagule_count trait enters HERE: sparse rain in a
            marginal cell converts slowly, saturated rain surely)
p_yr      = establish · f_hab · (1 − occupancy) · rain_frac
P_round   = 1 − (1 − p_yr) ^ T
f_hab     = F_worst(c) of L's cached fields
GATE: establishment only where f_hab ≥ EST_F_MIN (settled: 0.3)
```
On success: N_seed = EST_N0 (cal). **Vanguard accounting** (B5): cells
below EST_F_MIN are sinks — rain arrives every round and never
converts; rain cells are reported but never count as established
range. Transient rain expires each round (replaced); seed_bank
"persistent" rain carries over with a SEEDBANK_KEEP (cal) decay.
Over T = 100 years a SUITABLE cell is colonized near-certainly — the
vanguard model lives in the floor and the rain_frac slope, not in
denying colonization (critic finding 13's semantics, resolved).

**Founding (rule B+, owner ruling 2026-08-01, supersedes the v0.3
"mint on any non-component establishment"):** the old rule minted a
new instance per non-contiguous fragment — measured on seed 1 round 0:
1173 mints from 1122 genesis instances, median fragment 1 cell, p90 7
cells (instance count doubled per round). Rule B+ instead keys the
decision on GENE FLOW, not geometry:

1. **Contiguous spill joins unconditionally.** Founded cells
   8-connected to the founder through founded cells are physical
   contact — env-gating them would block over half of normal range
   expansion (measured: contiguous-join verdict gaps p50 0.26).
2. **Jump landings mint** (episodic, no sustained flow). Same-round
   kernel-connected landings mint as ONE (vicinity absorption: the
   minted region is the closure from jump-seeded cells through the
   remaining founded cells, one instance per fragment). X-clones
   carrying the founder's CURRENT WIP genes.
3. **Sustained-channel remote landings ALWAYS join** — local/wind/
   water/animal rain is sustained gene flow, so ranges may be
   non-contiguous, bridged by the round's rain. The VERDICT GATE
   decides whether they join cleanly or incubate:
   `gap = |mean s_env(frag) − density-weighted mean s_env(founder)|`
   vs `TH = DIFF_D · (1 + MOB_K · mobility)`, where mobility =
   sustained-channel pmf × kernel reach (jump excluded). The gate
   compares VERDICTS, not environments: a generalist's flat stress
   response passes over large env distances (lichen median gap 0.07 at
   env_d 0.3–0.5), a specialist fails on small ones (seagrass 0.31,
   barrel sponge 0.35) — stat pass of 2026-08-01, seed 1.
4. **Failed-gate cells incubate as a tagged divergent sub-range
   (div).** They count toward the parent's N and gene pool like any
   other region; they are NOT minted as instances. See §8 for the
   deferred split. Slivers therefore never mint (DIFF_MIN_CELLS floor).

## 8. Dressing (between rounds)

Per instance, two split triggers in order (critic finding 16 still
holds: computation is per-instance, never per-lineage):

1. **Divergent deferred split (rule B+):** a contiguous divergent
   sub-range (div) of at least DIFF_MIN_CELLS cells that is STILL
   verdict-divergent (same gap/TH as §7.3, reference = the instance's
   non-divergent region) breaks off as its own instance with the
   current WIP genes and a clean div. Below the floor, or back inside
   the threshold, it keeps incubating. Dead div cells are cleared each
   round. This is the blob-growth path: a divergent landing accumulates
   cells and rain while kernel-connected, and speciates only once it
   is a sizable population, never a sliver.
2. **Rain-bridge connectivity:** components are computed over the
   instance's N > 0 cells UNION this round's rain field — two
   populated regions stay ONE instance while the instance's own rain
   bridges them (sustained gene flow), and split (fresh instance_id,
   same WIP genes, div share carried) when the bridge is lost. NOT
   plain 8-connectivity of N. Rain-only fragments (sinks carrying no
   N) never split off. **Sliver floor (rule B+, symmetric with the
   founding rule):** a disconnected fragment below DIFF_MIN_CELLS
   stays dressed to the parent — it may re-bridge next round, and if
   it diverges the div machinery handles it (measured 2026-08-01:
   unfloored dressing splits ran 228-600/round with median fragment
   12-17 cells). Components of different instances that touch stay
   separate.

## 9. Commit (TreeAuthority bridge)

**Build dependency (critic finding 4, stated plainly):** the
TreeAuthority exists only as a Protocol (interface.py) and a test
FakeTree — model.Tree has no mint/update/redraw/reflog machinery.
This engine builds `authority.py`: a concrete TreeAuthority against
model.Tree implementing update/mint/redraw, the reflog (append-only
journal alongside the tree JSON), and final-commit name pinning
(K13 nomenclature). That build is part of this work item, not a
prerequisite.

**Parse** (engine → Authority): one InstanceView PER INSTANCE
(critic finding 9 — not a per-lineage aggregate): species_id,
instance_id, traits (WIP genes), mass = Σ_cells N(c).

**Decisions** (Authority, space-blind — it sees gene views only):
- **Orthodox lineage**: the instance closest to the amended species
  record; ties by established mass, then lowest instance id (the
  interface rule, cited verbatim).
- **Distance**: salience-weighted L1 over mutable scalar axes
  (normalized by axis span) + mismatch indicator over enums, averaged
  — computed pairwise on instance gene views. Clusters = connected
  components of the pairwise graph at SUB_D.
- **Subspecies**: a cluster at distance ∈ [SUB_D, SPECIATION_D) from
  the orthodox cluster — a real tree divide, registered, not too
  common (owner ruling). (cal: SUB_D, SPECIATION_D.)
- **Split (speciation)**: distance ≥ SPECIATION_D — the hard
  reproductive barrier; new record, parent linked, reflog entry.
- **Extinct**: no living instances → record marked extinct (reflog
  entry), branch terminated.
- **Merge**: distance < MERGE_D (cal), AND a spatial-contact gate
  computed ENGINE-side (the engine presents merge candidates only when
  the instances' cells touch — the space-blind Authority never sees
  cells, critic finding 5), AND rounds_since_divergence ≥ MERGE_GRACE
  (cal, default 5) — the grace exempts genesis siblings from instant
  re-merge (critic finding 10). Re-merge only when REALLY similar
  (owner ruling); the FINAL pass (end of run) joins all
  non-differentiated instances of a lineage back into one record.
- **Names**: interim handles `sid.iNNN`; binomials pin only at final
  commit.

**Re-sync**: genes re-minted from amended records per the changelog;
N, rain, instance↔cell assignment and instance ids survive; merges
re-key absorbed instances to the survivor (their N and rain transfer).

## 10. Genesis rain (round 0)

1. `preset_view` for each of the 35 authored presets → cached reduced
   fields (§5.1; the adapter's existing acceptance path).
2. Seed cells with F_worst ≥ GENESIS_F (settled: 0.5) at
   N = GENESIS_N0 (cal, default 0.2). Every preset reads its full
   factor product — for freshwater plans that INCLUDES the habitat
   term (it replaces their medium boundary; B5 §4.5).
3. **Initial partition** (owner ruling: headstart speciation): per
   preset, K = clip(1 + floor(log2(range_cells / PART_AREA_REF)), 1,
   PART_K_MAX) clones TOTAL (cal: PART_AREA_REF, PART_K_MAX=8),
   distributed across the preset's connected components: each
   component ≥ PART_MIN_CELLS is split by recursive rng-chosen axis
   cuts into contiguous chunks until the preset's K is reached
   (components < PART_MIN_CELLS stay one clone each).
   Draws from `Stream(seed, "k15.genesis", preset_id)`. Clones are
   sibling lineages from round 0 — subspecies candidates, merge-exempt
   for MERGE_GRACE rounds, free to diverge independently.

## 11. Module layout

```
exp/k15_simdiff/
  req_flora.py        (landed)      stress_adapter.py   (landed)
  engine.py           round loop + context wiring (§4, §5.0)
  genesis.py          §10           dispersal.py        §7
  population.py       §6            authority.py        §9 (+reflog)
  test_engine.py      §12           __main__.py         extend: rounds demo
```
Pure functions + named module constants throughout (house style);
numpy-vectorized per-cell updates, per-instance Python loops (instance
counts are small).

## 12. Acceptance (the §8-style gate, `__main__ --seed 1`)

1. **Determinism**: two full runs (R = 20 rounds) byte-identical JSON.
2. **Range tracking**: occupied cells' mean s_env < unoccupied cells'
   for every lineage alive at R (reported per lineage).
3. **Genesis partition diverges**: ≥ 1 clone pair of one preset
   registers subspecies-or-split within R rounds (island vs mainland
   isolation; MERGE_GRACE honored).
4. **Extinction**: a fixture lineage boxed into a lethal refugium
   (planted at s_env ≈ 1 by the test, not genesis) is extinct within
   5 rounds — possible because bscale → 0 (critic finding 1).
5. **Coexistence**: two fixtures with close suitability in one cell
   coexist (both N > N_FLOOR at R); with a large suitability margin
   the better-suited ends with ≥ TAKEOVER_RATIO (cal) of the cell.
6. **Vanguard gate**: a sink cell (f_hab < EST_F_MIN) receives rain
   every round and never establishes (rain > 0, N = 0 throughout).
7. **Wind dispersal is directional**: wind-channel deposits land
   downwind of source (signed projection test on seed 1's mean field).
8. **Performance**: genesis (35 evals) + 20 rounds ≤ 60 s wall; cache
   ≤ REDUCED_CACHE_MB (3.9 MB) per live instance.
9. **Hard-rule audit**: no uuid/random/time; every stream traces to K1
   (grep + a runtime guard in test_engine).

## 13. Knob table (all module constants; (cal) = stat-pass settled)

| knob | § | default | meaning |
|---|---|---|---|
| ROUND_YEARS | 4 | 100 | years per round |
| N_GEN_CAP | 4 | 400 | mutate calls per round cap |
| BIOMASS_REF | 6 | 25.0 | demand normalization (m²·wood) |
| PROD_CAP_SCALE | 6 | 1.0 | productivity → capacity scale |
| DENS_C / DENS_CAP / K_EPS | 6 | 0.5 / 2.0 / 1e-6 | density term |
| VIG_K | 6 | 0.5 | vigor → bscale cap (1 + VIG_K) |
| DIE_K | 6 | 0.002 /yr | stress mortality (§6 constraint) |
| N_FLOOR | 6 | 0.01 | cell extinction floor |
| COUNT_REF | 7.1 | 1e4 | emission normalization (count/yr) |
| EMIT_K / EMIT_P | 7.1 | 1.0 / 1.0 | fugitive emission gain/power |
| LOCAL_BIG | 7.2 | 0.5 | local share for radius-2 spill |
| WIND_K / WIND_MAX_CELLS | 7.2 | 1.0 / 40 | wind distance scale/cap |
| WATER_LAMBDA / WATER_MAX_CELLS | 7.2 | 20 / 40 | water decay/cap |
| ANIMAL_RADIUS_CELLS | 7.2 | 5 | animal stub radius |
| JUMP_SCALE / JUMP_RADIUS_CELLS | 7.2 | 1.0 / 50 | jump prob scale/radius |
| RAIN_HALF | 7.3 | 0.5 | rain half-saturation |
| EST_F_MIN / EST_N0 | 7.3 | **0.3 (settled)** / 0.05 | gate floor / founder density |
| SEEDBANK_KEEP | 7.3 | 0.5 | persistent rain carryover |
| GENESIS_F / GENESIS_N0 | 10 | **0.5 (settled)** / 0.2 | genesis threshold/density |
| PART_AREA_REF / PART_K_MAX / PART_MIN_CELLS | 10 | 200 / 8 / 20 | partition knobs |
| RE_EVAL_D | 5.1 | 0.15 | cache invalidation distance |
| DIFF_D / MOB_K | 7.3 | **0.2 (cal)** / 1.0 | verdict-gate base / mobility gain |
| DIFF_MIN_CELLS | 8 | **32 (cal)** | divergent sub-range split floor |
| SUB_D / SPECIATION_D / MERGE_D / MERGE_GRACE | 9 | 0.1 / 0.35 / 0.05 / 5 | commit distances/grace |
| TAKEOVER_RATIO | 12 | 0.8 | acceptance 5 |

**Content authoring conventions** (stat-pass E, 2026-08-01):
- `[niche] moisture_opt/breadth` are positions on the normalized
  `c_P_monthly` scale (mm/month = p × 400; world land median ≈ 0.11,
  rainforest ≈ 0.44, hot desert ≈ 0.04). Author against the measured
  per-biome medians — opt ≈ target-biome annual median, breadth ≈
  covers the seasonal swing to the worst month. NOT an intuitive
  0..1 wetness (that mis-anchored the first 35 presets by 2-5×).
- `[niche] temp_opt_c` compares against the GROWING-SEASON monthly
  field only (winter is dormancy-gated); breadth needs to cover the
  growing-season spread, not the annual range.
- `ph_tolerance` is a POSITION: optimum = 4.0 + 5.0 × axis. The
  world's ocean sits at pH ≈ 7.9 (axis ≈ 0.78), not 8.25.
- Marine plans (`medium = "water"`) skip the moisture niche term
  entirely; wet-obligate land plans (waterlogging_tolerance ≥ 0.7)
  read fresh_availability for both water terms, so their moisture
  niche should be broad.

## 14. Explicitly deferred (with homes)

- Snow stratum env-side (axis `snow_adaptation` landed) → B6 candidate.
- Submergence (needs an L0 flood-duration field) → L1.
- ley:/lift: sources (machinery landed) → ley-system addendum (W7).
- P9 canopy light field (`canopy_density` provisional) → flora P9 spec.
- Fauna rounds → post-flora-round addendum (B6-style), then the fauna
  KingdomSim adapter mirrors FloraSim.
- Animal dispersal vector (real frugivores) → fauna rounds.

## 15. Changelog

- **v0.4** (2026-08-01): rule B+ founding/differentiation (owner
  ruling after the seed-1 stat pass) — §7.3 founding keyed on gene
  flow instead of geometry: contiguous spill joins unconditionally,
  jump landings mint (vicinity absorption), sustained-channel remote
  landings always join with a VERDICT gate (TH = DIFF_D·(1 +
  MOB_K·mobility), verdict not environment — generalists pass,
  specialists incubate); failed-gate cells incubate as a tagged
  divergent sub-range (div) and split only at DIFF_MIN_CELLS (sliver
  suppression); §8 rain-bridge connectivity (components over N ∪ rain,
  loss of the bridge splits, rain-only sinks never mint). Knobs
  calibrated on seed-1 round-0 founding data (old rule: 1173 mints,
  median 1 cell; DIFF_D=0.2 leaves 6 gate-failing fragments, all < 32
  cells). Fixes the unbounded instance growth (1122 → 2427 → 4950)
  measured with the v0.3 rule.
- **v0.3** (2026-08-01): stat-settling pass folded (35 presets × seeds
  1-3, `statpass.py`) — §5.1 cache gains the substrate_share U(c)
  capacity plane (REDUCED_CACHE_MB 3.7→3.9); §6 K(c) → K_L(c) = K·U_L
  per-lineage capacity split (owner ruling: the top-3 ground mix is
  three physically present patches — best-of-class suitability,
  split capacity, no parameter softening); §5.1 worst month defined as
  worst GROWING month (T/moisture-uptake/waterlogging costs
  dormant-gated below GROW_T_C; submerged plans read annual bottom
  temperature, no dormancy); §13 GENESIS_F settled 0.6→0.5, EST_F_MIN
  0.35→0.3 (home-biome cells pay ~0.25-0.5 worst-month dry-season
  suit by design); §13 content authoring conventions (c_P moisture
  scale, growing-season temperature, pH position, marine/wet plan
  moisture handling). Adapter-side outcomes of the same pass:
  wet-obligate land plans read fresh_availability for both water
  terms; rooting moved to the tail terms; K14 ground class table
  deepened (alluvium/loess/ferralsol rooting 4.0 m). Post-pass state:
  0/35 NO_RANGE on seed 1, 4/35 (arid) on seed 2, 2/35 on seed 3 —
  all remaining gaps genuine world content.
- **v0.2** (2026-08-01): critic review folded — §6 rewritten (B5
  capacity-denominator density term replacing the per-instance
  denominator that ruled out equilibrium; bscale suppresses growth
  under positive stress; continuous compounding replaces the invalid
  (1−r)^T for rates > 1/yr); §4 single T-conversion policy; mutate
  per-generation (n_gen); §5.1 reduced per-instance cache replacing
  the 47 MB per-lineage full tensors; §5.2 one worst-month aggregation
  for selection and demography; §5.0 engine world fields (productivity,
  mean wind, downstream pointer, currents); §7 deterministic deposit
  kernels + rain_frac (propagule_count made live) + EST_F_MIN floor
  (vanguard semantics) + jump_rate into the view; §8 per-instance
  components (no-merge ruling honored); §9 per-instance parse,
  interface orthodox rule, engine-side contact gate, MERGE_GRACE,
  TreeAuthority build dependency stated, spatial state survives
  re-sync; §10 K-clones-total wording + named stream; DIE_K default
  made consistent with its own constraint.
