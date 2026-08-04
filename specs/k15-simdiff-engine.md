# K15 sim-diff engine (flora rounds) — build spec v1.9

2026-08-04. v1.9 (ticket 0039, owner ruling) supersedes v1.8 in ONE
respect: the genesis mint floor GENESIS_MIN_CELLS is REMOVED — every
proximity blob is mintable however small (§15 entry; prose below that
still names the floor is stale pending the rewrite-era spec cleanup).

2026-08-01. v1.8 (ticket 0012, the curated two-track census,
2026-08-03) supersedes v1.7: genesis seeds the CURATED tree (52
individual-track pins → 134 radiated species; the ad-hoc test list is
gone) PLUS the sim-side FROZEN-BUNDLE REGISTRY — one generic
niche-dweller per authored bundle record (k13 content bundles.toml:
ENVELOPE + polyphyletic ANCHOR-CLADE SET; a bundle is a region ×
physiology archetype standing in for an aggregate of species, NOT a
tree node). §10: after the species mint, each bundle (sorted-label
order) is evaluated once and seeded through the SAME gates (F_worst ≥
GENESIS_F ∩ medium-valid ∩ the K_L gates, no mint floor since
v1.9/ticket 0039, GENESIS_COVER per-component draws from
`k15.genesis` keyed by the bundle sid) — ONE instance per bundle (no clone partition: frozen
lineages cannot diverge), minted OUTSIDE the taxonomy (sid
`bundle.<label>`, never authority.mint). FROZEN BY CONSTRUCTION: the
§4 verdict feed skips bundle instances (no select/mutate/Δg/_refresh),
the §9 commit excludes their iids from the views, the g map, and the
merge candidates (iid-based — dispersal foundlings inherit the bundle
sid), and §10.1's descent never sees them (tree-node iteration); the
authority never tracks them (reflog/tree/_alive stay bundle-free);
they participate in population/dispersal/stress only. Post-sim, 0027
dissolves each into daughters across its anchor clades. §10.1 gains
the SPECKLE SKIP: a broken-off blob whose SEEDED part is below
DESCENT_MIN_BLOB_CELLS // 2 is skipped (ticket 0009 suppression — the
curated census surfaced a 1-cell seeded-part fragment the old
`seeded.any()` check admitted). Measured seed 1: 30/38 bundles seeded
(22 673 cells); genesis 402 species instances (89/134 lineages) + 30
bundles; 20 rounds → 86 lineages + 30 bundles alive, 4 909 instances,
cell richness median 5/max 23, 52 new tree nodes (2 subspecies).
Coverage audit (0012 Task C) findings queued as ticket 0033 — the
headline: narrow-niche habitat-formers (mangrove/kelp/seagrass/
sphagnum/willow) are viable-but-sub-floor, so the sim currently has no
mangrove/kelp/seagrass/bog habitat physics. Fixture re-pins documented
in the tests' v1.4 paragraphs. Fast 155 + slow 5 green.
v1.7 (ticket 0013, the delivery pass, 2026-08-02)
supersedes v1.6; v1.6 (ticket 0018 REBUILD, 2026-08-02, pre-genesis
descent with the earned-g first-commit rank) supersedes the v1.3
design note below it: the adapted fringe returns, but the fragments
now EARN their g (g_end = DES_G_FRAC × n_gen × rate_mult — the v4-era
build minted them at g = 0, which was wrong) and the authority ranks
a fragment at its FIRST commit — classify(g_end, the lineage's g*):
beyond g* → a real SPECIES branch (the tree gains width), below →
SUBSPECIES node; EXEMPT from the cluster floors (they guard emergent
wobble, not earned divergence), PROVIDED the fragment's scalar-only
distance from the orthodox record exceeds the lineage's merge
threshold (else it merges back — no rank: it was not actually
diverged). NO seed_clusters, NO genesis-time tree writes — round 0
does nothing to the tree. The v1.2 baseline (real cladogenesis)
replaces the
wholesale g-promotion with CLUSTER-LEVEL divides: non-orthodox trait
clusters tracked across commits (member-overlap continuity) divide off
as real daughters once stable (CLUSTER_PERSIST_ROUNDS) and
multi-member (CLUSTER_MIN_SIZE) — beyond the lineage's g* as SPECIES
(branching: the tree gains WIDTH), below as SUBSPECIES (first-class
since genesis); the wholesale promotion is narrowed to the stem's own
commit (re-keys the REMAINDER). The cluster graph moves to the
SCALAR-ONLY metric at SUB_D 0.08 (enum flips are same-blob noise at
the lower edge); the isolation Condition input is wired into Δg
(option B: rounds since the instance last touched a same-lineage
sibling, ramped over ISO_RAMP_ROUNDS, fully isolated lineages accrue
g at (1 + ISO_G_GAIN)× — island clones speciate first); clusters are
merge-exempt by construction (scalar d >= SUB_D > MERGE_D), so the
CONSOL governor never resets a persistence clock; `seed_clusters`
makes a pre-seeded round-0 cluster geometry a first-class input
(machinery available; ticket 0018's adapted fragments do NOT register
— the first-commit rank path handles them instead). Measured seed-1
30-round run: see §15.
v1.1 (ticket 0020, DESIGN PIVOT) makes genesis seeding
capacity-aware with SPARSE founders and PARTIAL range coverage: §10
replaces the flat GENESIS_N0 = 0.2 founder density with the
capacity-relative demand D = GENESIS_F0 · K_L(c, L) (settled 0.1) plus
per-component coverage draws (GENESIS_COVER = 0.5) — NO cross-lineage
density budget (the first implementation's budget gate claimed viable
cells first-come-first-served in sorted sid order and budget-dropped
51/150 species: occupancy by name hash instead of fitness; rejected by
the owner). Measured seed-1 genesis: 102 lineages minted (48 unseeded:
4 zero-range + 41 all-sub-floor + 3 all-below-K_EPS), 622 instances,
stacking mean 5.31, realized coverage (minted/viable, per-species
median) 0.29, u p50 1.22 / frac u>1 0.58 at genesis (density
competition left to the rounds by design — see the v1.1 changelog for
the done-means analysis). v0.9 (ticket 0009) added the genesis mint
floor: §10 drops the seeded-range connected components below
GENESIS_MIN_CELLS (32 cells
= the DIFF_MIN_CELLS sliver scale) instead of minting one speckle
instance per fragment — measured seed-1 genesis (final world: the
sand-sheet cold gate 2cc8e76 plus the dune/lake-fetch gates
0d432c5/758ec17) drops 14800 pre-floor components → 1316 instances
(105 lineages; 41 all-sub-floor species go extinct at genesis, plus
the 4 zero-range ones — 45 unseeded in total). v0.8 (ticket 0004)
seeds the radiated tree: §10
genesis
rains every SPECIES node of the committed tree (~150 sids, each with
its own range evaluation, partition and clones — the 35 ORDER nodes
are ancestors, never seeded) instead of the 35 authored presets;
zero-range species are never minted and go extinct at genesis via the
authority's normal extinction pass (register_unseeded, §9). One
adapter evaluation per species: the seeding and the §5.1 cache share
the same factors. v0.7 adopts K13's g currency for the divide side
(ticket 0008 — the owner caught that K15 rounds invented a parallel
speciation currency, genes_distance vs absolute SUB_D/SPECIATION_D,
instead of fauna RFC §1's g): instances accumulate g_since_split per
round in generation time (Δg from the three forces' share table,
forces.py idioms), divides rank by classify(g_since_split, g_star),
and the merge gate moves to a scalar-only L1 metric calibrated on the
measured same-blob noise floor (agent-58, 2026-08-01). v0.6 folds the
packet-colonization redesign (owner ruling
"tentacles, not dots"): §7 dispersal moves from per-source-cell deposit
kernels to a handful of coherent width-carrying packets with one
establishment decision per packet, plus the per-lineage colonization
memory (§7.3). v0.3 folds the stat-settling pass (35 presets × seeds
1-3):
substrate capacity split (§5.1, §6), dormancy-gated worst month (§5.1),
settled knobs (§13), and the moisture-niche authoring scale (§13).
v0.2 folded the critic review (23 findings): the population
math (§6), verdict aggregation (§5.2), cache design (§5.1), the commit
handshake (§9) and the dispersal deposit model (§7) were rewritten.

Builds on: B5 (`biosphere-addendum-b5-flora-stress.md`), the K13/K14/K15
restructure spec-note (2026-07-30), the owner rulings of
2026-07-31 → 2026-08-01 (conversation), the fauna RFC §1 phylogenetics
core (the g currency, restated for flora in the flora RFC), and the
landed code:
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
   **g accumulation (v0.7, fauna RFC §1; isolation v1.2, ticket
   0010):** each instance carries `g_since_split` — genetic distance
   in generations from its lineage's split ancestor. Per round the
   feed accrues `Δg = n_gen · rate_mult · (drift baseline ×
   (1 + ISO_G_GAIN·isolation) + stress-descent share ×
   (1 + STRESS_G_BOOST·stress) + runaway share · ornament fraction +
   enum share)`, where the shares are forces.py's Condition table with
   the ISOLATION input finally wired (v1.2): per instance, rounds
   since the instance last touched/overlapped any same-lineage
   instance (the engine's spatial contact gate, §9), ramped to full
   isolation over ISO_RAMP_ROUNDS; a fully isolated lineage accrues g
   at (1 + ISO_G_GAIN)× the plain clock — the fauna RFC §1 pairwise
   rate (d(A,B) = (g_A − g0) + (g_B − g0): two isolated subpopulations
   diverge at 2× the single-lineage rate). A single-instance lineage
   is never isolated (it IS the whole gene pool). Island clones
   speciate first; the mainland stays cohesive — allopatric tempo.
   `rate_mult` is the lineage's lognormal rate multiplier and the
   ornament fraction is the runaway-consumer axes' share of the
   mutable registry (flower display, fauna RFC §1), both drawn once
   per lineage via pinned `k15.g` streams. Mutation magnitude ramps
   with f(g) (forces.py): each generation's pressure is scaled by
   `step_scale(g) = 1 + g/G_REF` × the leaky steady-tier gate
   (`1 − exp(−(g − G_STEADY_ONSET)/G_STEADY_RAMP)` — steady axes
   effectively frozen at low g), and each pressured scalar axis rolls
   the heavy tail (P_NOVEL_MAX, × NOVELTY_MULT) at p_novel·n_gen/
   G_STEP_REF per round — the occasional striking trait, never a
   uniform rate. Fast lineages (duckweed, n_gen 400) blow past g*
   within a round or two; slow trees take decades of rounds — the
   grass/oak tempo split is emergent (flora RFC).
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

## 7. Dispersal (packet colonization, v0.6)

### 7.1 Emission (per instance, stress-gated)

```
E = occupied_cells · (propagule_count / COUNT_REF) ·
    (1 + EMIT_K · max(mean_s_real, 0)) ^ EMIT_P        (cal: all three)
```
E is in normalized rain units (propagule_count is per-year and COUNT_REF
normalizes; the T years of rain within a round arrive as one integrated
deposit). E splits across channels by the dispersal_channels pmf.

### 7.2 The packet layer (v0.6, replaces the v0.5 per-source-cell kernels)

The v0.5 model deposited rain from every occupied source cell
(SRC_CAP-subsampled) and converted per cell by independent Bernoullis —
measured on seed 1: 120k→550k deposit cells/round, 9–12% of founded
cells isolated speckle, jump foundlings at median 1 cell, ~160
bridge-splits/round of which 80% were slivers < 32 cells. v0.6 replaces
per-cell deposits with a handful of coherent, width-carrying PACKETS
per instance ("tentacles, not dots", owner ruling): 1–8 packets per
channel, each a contiguous blob launched from a frontier cell, with ONE
weighted establishment decision per packet converting the WHOLE blob or
nothing.

- **Packet count per channel**:
  `n_pk = clip(PACKET_BASE + floor(log2(max(1, n_occ) / PACKET_AREA_REF)), 1, PACKET_MAX)`
  (knobs 2 / 32 / 8). The channel share E·pmf(ch) divides equally among
  its packets.
- **Packet origins**: FRONTIER cells only — occupied cells with ≥ 1
  unoccupied 8-neighbor within the window (the window edge qualifies).
  One draw per packet from the per-instance disperse stream's channel
  child (`rng.child("pk:{ch}")` at clock=0, index=k) — never per cell.
- **Shapes** (all rasterized deterministically; no floats enter cell
  selection beyond the pinned draws):
  - **local** — a filled spill blob around the origin frontier cell:
    the v0.5 local semantics (Chebyshev radius 1, radius 2 at local
    share ≥ LOCAL_BIG) rasterized as ONE contiguous blob, the
    instance's own cells excluded.
  - **wind** — a tapered tentacle: the straight integer ray along the
    ORIGIN cell's mean wind vector (Bresenham-style, not a field
    walk), length L = ceil(λ) with λ = WIND_K·speed/√propagule_mass_mg
    (cap WIND_MAX_CELLS); width 2 (ray cell + one perpendicular
    neighbor: column +1 on row-major rays, row +1 on column-major) for
    the first floor(len/2) cells, width 1 for the rest.
  - **water** — the v0.5 D8 downstream walk (marine: monthly-mean
    current field), WATER_MAX_CELLS cap; the walked path carries width
    2 (the perpendicular of the first step's dominant axis) for the
    first floor(len/2) cells, width 1 for the rest.
  - **animal** — a filled Euclidean disk of radius ANIMAL_RADIUS_CELLS
    centered at the origin plus a uniform offset drawn from the animal
    disk table (one draw per packet, clock=1 — the v0.5 animal range
    semantics).
  - **jump** — the episodic landing carries a filled Euclidean disk of
    radius JUMP_DISK_RADIUS (≈ 28 cells; 29 with the landing center)
    instead of a single pixel. The roll is unchanged (P =
    1 − (1 − jump_rate·JUMP_SCALE)^T; on failure the share folds into
    local).

Each packet's cells receive rain uniformly (pk_share / |cells| per
cell, world coordinates, in-grid only). Stochastic draws from
`Stream(seed, "k15.disperse", f"{t}:{instance_id}")` children per
channel (`jump`, `jump_source`, `pk:{channel}`, `establish`); instances
processed in sorted instance_id order. Absorption is unchanged (§3: a
same-lineage cell absorbs into the occupant).

### 7.3 Establishment gate (per packet, v0.6)

ONE weighted decision per packet — the v0.5 per-cell Bernoulli pile is
gone:

```
candidates  = the packet's cells with NO occupying instance of the
              lineage (own cells take rain via absorption but never N)
mean_f      = mean(f_hab^β over candidates)     (row-major sum;
              β = EST_BETA = 1.0; β = 0 = stress-blind fallback)
p_yr        = establish · mean_f
GATE: P = 0 where mean_f < EST_F_MIN            (vanguard at packet
              scale: a packet into a sink region never founds)
P           = 1 − (1 − p_yr)^T                  (§4 single-T policy)
              × MEM_PENALTY when any candidate cell is in the
              lineage's colonization memory
f_hab       = F_worst(c) of L's cached fields   (exactly what the
              v0.5 establish read)
```
The packet founds iff u < P with u ~ Uniform from the "establish"
child (clock=0, index = the per-instance packet counter). On success
the ELIGIBLE cells — unoccupied AND f_hab ≥ EST_F_MIN — found at
N = pk_share / |founded|, clipped to 1 (the vanguard sink cells inside
a packet carry rain but never N: §12.6 is preserved cell-exactly). On
failure nothing founds and the packet's cells are recorded in the
colonization memory. Vanguard accounting (B5) is preserved: sink cells
receive rain every round and never convert; the per-cell gate form of
the gate (`establish`, EST_N0 founder density) is retained in
dispersal.py as the defining kernel of that accounting.

**Colonization memory (v0.6):** per lineage (sid) the engine keeps
`_colon_mem` — attempted target cell → last-attempt round. A FAILED
packet's candidate cells are recorded with the current round; entries
older than MEM_ROUNDS (3) are purged each round (deterministic sorted
iteration). A packet whose candidate cells include a remembered cell is
down-weighted ×MEM_PENALTY (0.25) — a failed target is not re-attempted
at full weight within MEM_ROUNDS rounds.

**Founding (rule B+, owner ruling 2026-08-01, UNCHANGED from v0.4):**
the founding decision keys on GENE FLOW, not geometry:

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
   12-17 cells). **Split hysteresis (v0.4.1):** a fragment at or
   above the floor mints only after the bridge has stayed lost for
   TWO consecutive dressings. Each instance carries an `orphan` cell
   tag (windowed like div): the first dressing that finds a fragment
   disconnected only tags its cells orphan; it mints at a later
   dressing only if it is still disconnected AND at least half its
   cells were already tagged. The tag clears when the cell
   re-bridges into the main component and dies with the cell.
   Slivers below the floor are pre-tagged (their disconnection is
   chronic by construction — hysteresis targets oscillation, not
   chronic disconnection). Orphan tags follow cells through crop,
   rewindow and commit merges; a minted fragment carries its tags,
   a div-split or foundling starts clean. Measured cause breakdown
   (seed 1, r0-r5, cause-classified run): ~63% of bridge splits
   were fragments founded THIS round by sustained-channel landings
   that joined by rule and failed the bridge test in the same
   dressing (join/split oscillation), ~15% transient mortality
   carves, ~22% chronic disconnections — the first two classes are
   absorbed by the grace round, the last mints one round later.
   Components of different instances that touch stay separate.

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
instance_id, traits (WIP genes), mass = Σ_cells N(c). The g
bookkeeping rides as SEPARATE update() arguments (the view is the
interface.py protocol's shape — unchanged): `g_since_split` (per
instance id, generations) and `g_star` (per lineage sid).

**Decisions** (Authority, space-blind — it sees gene views only):
- **Orthodox lineage**: the instance closest to the amended species
  record; ties by established mass, then lowest instance id (the
  interface rule, cited verbatim).
- **Distance**: salience-weighted L1 over mutable scalar axes
  (normalized by axis span) + mismatch indicator over enums, averaged
  — computed pairwise on instance gene views. The CLUSTER graph and
  the orthodox-cluster bookkeeping read the SCALAR-ONLY metric
  (v1.2, ticket 0010 — the full metric's enum contribution is
  same-blob noise (ticket 0008: 15% enum mismatch at equal pressure)
  and would spuriously separate same-blob pairs at the lower edge,
  corrupting the cluster geometry the persistence tracker reasons
  about). The full metric stays for distance-to-record (orthodox) and
  the g-less SPECIATION_D fallback band. Clusters = connected
  components of the scalar-only pairwise graph at SUB_D.
- **Subspecies / Split — real cladogenesis (v1.2, ticket 0010):** the
  divide machinery is CLUSTER-LEVEL and replaces the wholesale sweep.
  Every non-orthodox cluster is tracked across commits
  (`_cluster_state`, member-overlap continuity — a cluster continues
  the lineage's state with the largest member intersection, so rep
  changes and member churn do not reset it) and must be a STABLE
  COMPONENT for CLUSTER_PERSIST_ROUNDS commits with at least
  CLUSTER_MIN_SIZE members before it may divide — the churn floors
  (the v0.7 disease was per-instance g crossings churning hundreds of
  spurious splits per round; a wobble never accumulates the
  persistence). An ELIGIBLE cluster divides off as a real daughter;
  the RANK is the g currency (fauna RFC §1): the cluster
  representative's g_since_split vs the LINEAGE's seeded g* — BELOW
  g* divides as a SUBSPECIES node (the RFC's "fragment below g* =
  subspecies"); BEYOND g* BRANCHES as its own SPECIES node (real
  cladogenesis: the tree gains WIDTH, the remainder stays in the
  parent). Ineligible clusters incubate (KEEP) with their clock
  running. On re-key the instances' g_since_split resets to 0 (the
  split ancestor — fauna RFC §1's d(A,B) = (g_A − g0) + (g_B − g0))
  and the new lineage draws fresh g* / rate multiplier. SPECIATION_D
  is no longer a rounds currency (kept only as the g-less fallback
  for direct authority unit tests; the floors apply there too —
  pre-seeded via `seed_clusters`).
  **Stem promotion (v0.7, narrowed by v1.2):** the LINEAGE's g — the
  orthodox instance's g_since_split (the record's representative,
  "per lineage, scalar g") — crossing the lineage's seeded g*
  re-keys the REMAINDER (instances not already divided off as
  daughters this commit) to ONE new SPECIES node: a dense lineage is
  a continuous trait cloud that never splits at SUB_D (measured on
  seed 1), so the stem still needs its own commit — otherwise its g
  (and the mutation-magnitude ramp) would accumulate without bound.
  One-shot: a SPECIES node is born promoted and never re-promotes
  (its g keeps accumulating and classify stays "species"). Cluster
  divides run BEFORE the promotion, so a fragment crossing g* in the
  same commit branches as a daughter instead of riding it.
  **Pre-seeded geometry (ticket 0018 synergy):** `seed_clusters(sid,
  [...])` registers clusters that were stably diverged BEFORE the sim
  (genesis clones diverged at round 0 by pre-genesis descent — 0018
  design-only today). Seeded clusters are born with full persistence
  credit and divide at the first commit: the round-0 cluster geometry
  is a first-class input, not just sim-emergent structure.
  **CONSOL reconciliation (decided):** clusters are merge-exempt BY
  CONSTRUCTION — a cluster member pair has scalar d >= SUB_D >
  MERGE_D and the merge gate requires both members in the orthodox
  cluster, so the periodic consolidation sweep never touches a
  persisting cluster and can never reset its clock.
- **Extinct**: no living instances → record marked extinct (reflog
  entry), branch terminated. Genesis zero-range species (ticket 0004):
  never minted, but the engine registers them with the authority
  (`register_unseeded`) so THIS pass marks them at the first commit —
  same reflog entry, same ghost record.
- **Merge (v1.3, ticket 0028 — per-lineage threshold, immediate
  recombination):** scalar-only L1 distance < the LINEAGE's merge
  threshold AND a spatial-contact gate computed ENGINE-side (the
  engine presents merge candidates only when the instances' cells
  touch — the space-blind Authority never sees cells, critic finding
  5). The threshold is PER-LINEAGE and mutation-tuned (owner design
  2026-08-02, ticket 0028): threshold(sid) = min(MERGE_D_CAP,
  MERGE_D_BASE × (n_gen × rate_mult / MERGE_D_RATE_REF)^MERGE_D_EXP),
  where n_gen is the lineage's per-round generation count
  (gen_time = 2·sqrt(height_m), spec §4 step 1) and rate_mult the
  per-lineage lognormal rate multiplier (fauna RFC §1, drawn once via
  k15.g). The threshold is TIGHT at the reference rate — a differing
  environment diverges past it, so environment acts through the
  GENETIC channel (no environment field); it widens with the mutation
  rate so a fast mutator's own same-environment pieces ("same species,
  same place") still recombine. The engine computes it per commit (per
  lineage, from the max-mass instance's height) and passes it to the
  authority's update() as a per-sid map — the same channel as g_star;
  the authority stays space-blind. Callers that pass no map (unit
  tests) fall back to the fixed MERGE_D. The saturation cap
  (MERGE_D_CAP = 0.05) keeps the gate below the cluster edge (clusters
  are merge-exempt by construction, ticket 0010).
  **Calibration (seed 1, ticket 0028; RE-ANCHORED ticket 0030):** the
  0028 calibration classed "same-env" by |Δ mean s_env| — an aggregate
  that mixes genuinely-different selection vectors (same average
  stress, different per-factor shortfalls — e.g. cold vs dry), so
  both 0028's and 0029's conclusions sat on a contaminated baseline.
  The corrected probe (tmp/k15_calib/corrected_baseline.py) classes
  same-lineage pairs by the per-requirement provenance-vector pdist —
  exactly what select() actually reads — and shows the TRUE same-env
  floor is p50 0.005 at gain 1.0: 0028's median threshold (0.030) was
  anchored ~5× too wide. Re-anchored (0030): MERGE_D_BASE = 0.012 —
  the median-lineage threshold (th p50 0.0108) = 2.0× the clean
  same-env drift p50 (0.0054), the owner's 2–3× band, below the
  ratchet tail (clean d p90 ~0.043 — old same-env pieces past any
  sane threshold by design: drift retention → the 0010 path, not a
  bug). At the settled value (seed 1 r6): clean same-env
  recombination fraction (d < th) 0.62 at pdist<0.02 (vs 0.78 at
  0.030 — the ~38% failures are ratchet-tail pieces, clean d p90
  0.037); cross-env block fraction (d ≥ th) 0.46 at pdist≥0.05 (vs
  0.11 at 0.030 — the discrimination job moved from the gain to the
  tight threshold) and 0.34 at pdist≥0.10 (n=35 — within-lineage
  environment-differentiated pairs are rare at r6, n≈4–44, and
  accumulate later); the r16 fat-blob holds (377 instances /
  per-species p50 2 / max 21 / 8% species >10 vs 251 / 2 / 15 / 2%
  at 0.030 — the count responds ~+50% as recombination tightens).
  Cross-env persistence still rides the contact gate (disjoint
  partitions / remote foundlings never become candidates) +
  cluster/divide machinery. Same-env per-round drift scales linearly
  with n_gen×rate_mult (log-log slope 1.00, n=39).
- **Immediate recombination (v1.3):** merge candidates are processed
  EVERY round (event-driven, contact-gated), and the merge grace is 0
  (MERGE_GRACE — was 5): a same-environment piece recombines at the
  first commit it touches the parent — the range GROWS (one instance,
  fat blob). Genesis stacks (same-lineage instances sharing cells,
  d ≈ 0) collapse at the round-0 commit. The grace's old role —
  exempting genesis siblings until they diverge — is retired: the
  per-lineage threshold does the discriminating.
- **Consolidation (v1.3, KEPT):** the final pass still runs
  periodically — every CONSOL_EVERY-th commit (5) the engine presents
  ALL same-lineage pairs as candidates (the authority still re-checks
  the per-lineage threshold; its greedy survivor absorbs each partner
  in turn, so a complete candidate clique collapses in one update).
  This is the instance-count backstop: measured without it (grace 0,
  contact gate only) the seed-1 r16 instance count is 1341 (per-
  species p50 12, 55% species >10) vs 251 with it (p50 2, 2% >10).
  The join is deliberately not sticky — unbridged distant fragments
  re-split within two dressings (§8 hysteresis), the sawtooth that
  bounds instance count. The contact gate itself is overlap-aware
  since v0.4.2: the shift-grid touch test holds only one instance
  index per cell, so STACKED instances (same lineage, same cell —
  measured up to 1132 layers in one cell at r19) were invisible to it;
  a per-cell layer-count pass adds star-topology candidates per
  overlapped cell.
  **v0.7 merge calibration (retired as a rounds currency):** the fixed
  MERGE_D = 0.045 (same-blob scalar p99 floor ≈ 0.073, contrast pairs
  p90 ≈ 0.057 by r5) is now only the no-map fallback. The rounds gate
  reads the per-lineage threshold (ticket 0028; §13).
- **Names**: interim handles `sid.iNNN`; binomials pin only at final
  commit.

**Re-sync**: lineage bookkeeping (sid, record keys) re-mints from
amended records per the changelog, but a surviving instance KEEPS its
WIP genes and pressure plane (v0.5 owner ruling: sub-SUB_D divergence
ratchets round-over-round; the pre-v0.5 re-mint reset each instance to
the record, capping pairwise same-lineage distance at the one-round
nudge forever — measured 0.0000 instance-vs-record at every round end
over 20 rounds, zero divides); N, rain, instance↔cell assignment and
instance ids survive; merges re-key absorbed instances to the survivor
(their N and rain transfer). v0.7: a divide re-key resets the
instance's g_since_split to 0 (the split ancestor's g0 — fauna RFC
§1's d(A,B) = (g_A − g0) + (g_B − g0)) and the new lineage draws its
own rate multiplier and g* once; foundlings/dressing splits inherit
the founder's g_since_split (same gene pool, shared clock).

## 10. Genesis rain (round 0)

Ticket 0004: genesis seeds the RADIATED TREE — every SPECIES node of
the committed tree (~150 sids on seed 1), not the 35 authored presets.
The 35 ORDER nodes are ancestors, not species: they are never seeded
("for a world to have biodiversity, it must be completely written at
L0" — owner ruling 2026-08-01). Each radiated species is its own
world: own range evaluation, own partition, own clones.

Ticket 0020 (DESIGN PIVOT, owner 2026-08-01): genesis seeds SPARSE
founders with PARTIAL range coverage and NO cross-lineage density
budget. The first implementation (a world-level cumulative density
budget with streaming admission in sorted sid order, an erosion sweep
and relocation) met its done-means but at an unrealistic cost: viable
cells were claimed first-come-first-served, so ~2 lineages filled a
cell and late-sid species found their niche "already occupied" — 51/150
species budget-dropped at genesis, occupancy decided by name hash
instead of fitness. Owner rulings: (1) genesis seeds sparse founders
and lets competition happen inside the sim (where it can become
niche/fitness-aware), not at mint; (2) there is NO need to seed full
viable ranges — partial coverage leaves unseeded habitat for §7
colonization.

1. **One batch, one evaluation per species** (tickets 0004/0020): the
   rain runs in a single call (`genesis.genesis_rain_species`)
   processing species in sorted sid order. Evaluate each species' OWN
   record view (`species_view` — radiated axes, not the authored
   preset record) → the §5.1 reduced fields. ONE adapter evaluation
   per species: the seeding and the engine's per-instance cache are
   built from the SAME evaluation (`genesis_rain_species` returns the
   compact reduced bundle names/F_worst/prov/U; the clones of one
   species share the cache by reference — the bbox optimization).
2. **Sparse capacity-relative founders** (ticket 0020): seed the
   cells with F_worst ≥ GENESIS_F at D = GENESIS_F0 · K_L(c, L) — a
   SMALL fraction (settled 0.1, allowed 0.05–0.15) of the lineage's
   OWN carrying capacity K_L = PROD_CAP_SCALE · K(c) · U_L(c) (the §6
   v0.3 capacity split, reused from population.lineage_capacity —
   never duplicated). Founder abundance is N = D/percap (percap = the
   §6 per-capita demand), floored at N_FLOOR: a high-percap organism
   whose F0·K_L would seed below the §6 extinction floor is clamped to
   it (nothing mints below the floor). With F0 small, utilization
   u ≈ F0 · n_stack stays near (and the density term inside) the cap
   even with heavy stacking — NO mint-time budget; density competition
   is left to the rounds. The old flat GENESIS_N0 = 0.2 density
   ignored per-cell capacity and measured u p50 ≈ 14 (9.13 stacked
   lineages per populated cell). Every species reads its full factor
   product — for freshwater plans that INCLUDES the habitat term (it
   replaces their medium boundary; B5 §4.5).
3. **Mint floor — REMOVED** (v1.9, ticket 0039, owner ruling; this
   step used to drop blobs below GENESIS_MIN_CELLS): every proximity
   blob of the seeded range is minted, however small — speckles can't
   emit propagules and neighbor speckles join into one instance, so
   the floor bought nothing.
4. **Partial coverage** (ticket 0020): per retained (≥ floor)
   component, in the pinned emission order (sorted top-left,
   row-major), an independent keep/drop draw from
   `Stream(seed, "k15.genesis", species_sid)` — component i draws
   `rng.child("cover:{i}")` with keep probability GENESIS_COVER
   (settled 0.5). WHOLE blobs are kept or dropped (never speckled
   cells); unseeded viable cells stay empty for §7 colonization. A
   species whose every drawn component is dropped keeps its single
   largest component unconditionally (ties → first emission order), so
   the coverage draw can NEVER cause extinction — only the
   ticket-0004/0009 paths do (zero range, all-sub-floor). The
   partition's K targets the COVERED range (the cells actually
   minted).
5. **Initial partition** (owner ruling: headstart speciation): per
   species, K = clip(1 + floor(log2(range_cells / PART_AREA_REF)), 1,
   PART_K_MAX) clones TOTAL (cal: PART_AREA_REF, PART_K_MAX=8),
   distributed across the covered components: each component ≥
   PART_MIN_CELLS is split by recursive rng-chosen axis cuts into
   contiguous chunks until the species' K is reached (components <
   PART_MIN_CELLS stay one clone each). Draws from
   `rng.child("comp:{i}")` — content-addressed, so the coverage
   draws' order never matters for the partition draws. Clones are
   sibling lineages from round 0 — subspecies candidates, merge-exempt
   for MERGE_GRACE rounds, free to diverge independently.
6. **Extinction paths** (ticket 0004): a species with no mintable
   cells — zero range (the only unseeded bucket since v1.9/ticket
   0039) — is NEVER minted; the engine registers it with the authority
   (`TreeAuthority.register_unseeded`) so the §9 extinction pass marks
   it extinct at the first commit — reflog entry, branch terminated,
   the record stays as a ghost.

Measured genesis state (seed 1, ticket 0020, DESIGN PIVOT): 622
instances across 102 lineages (of 150 species — 48 unseeded: 4
zero-range + 41 all-sub-floor + 3 all-below-K_EPS), 80046 minted
(cell, lineage) pairs over 15065 populated cells (stacking mean 5.31,
max 30), clone blob sizes p50 59 / mean 129 / min 32 (no speckle),
per-lineage partition disjoint, realized coverage (minted/viable
cells, per-species median) 0.29 (0.55 by retained-blob cells — the
sub-floor speckle dilutes the viable-cell metric). Utilization at
genesis: u p50 1.22 / frac u>1 0.58 (max ~4e5 — the tiny-K_L pairs,
clamped to the N_FLOOR floor) — the sparse founders are born under
noticeable density competition BY DESIGN (the owner's "u ≈ F0 ·
n_stack" model assumes equal substrate shares; on seed-1 data the
median pair's U is ~1/12 of its cell's total ΣU, so u = F0·ΣU/U_j
stays ~1.2 at F0=0.1 — see the v1.1 changelog; the pre-0020 done-means
u targets are unreachable without a density gate).

### 10.1 Pre-genesis descent — the adapted fringe (ticket 0018; owner
model 2026-08-02, binding; REBUILT 2026-08-02 with the earned-g
first-commit rank — the v4-era build notes are superseded by the
g-earning + rank rulings where they conflict)

1. Genesis: random distribution (UNCHANGED — sparse founders, partial
   coverage, partition; the existing genesis stays as-is).
2. Per species, ONE pinned roll from `Stream(seed, "k15.descent",
   sid)` (`P_ADAPT`): the species' chance at adaptation. Most species
   don't get it.
3. If harsh cells/blobs exist for that species (the marginal tail:
   s_env ≥ S_ENV_TAIL of the species' viable range; connected
   components = blobs ≥ DESCENT_MIN_BLOB_CELLS), each blob has a
   pinned chance (`P_BREAKOFF`) of being broken off into a NEW
   INSTANCE (same lineage sid, new instance id, normal engine
   instance — NOT a species node at genesis, NOT seed_clusters) whose
   traits are **adapted** toward those cells' conditions by the
   descent.
   - The descent modifies the SEEDED component ONLY (owner ruling
     2026-08-02): the new instance covers the blob's SEEDED part
     (blob ∩ the species' clone union); that part is carved out of
     the owning parent clone's range in place (a clone emptied
     entirely is not minted — no zero-mass parent), and the
     instance's N is minted over it at founder demand with the
     ADAPTED percap.
   - A broken blob with NO seeded cells is skipped entirely — no
     instance. Unseeded harsh cells (the coverage drops, or the
     eligibility gate's freak-tail residual) STAY unseeded — partial
     coverage (ticket 0020) deliberately leaves them for §7
     colonization, and the descent must not override that.
4. **g-earning (the rebuild's fix — the v4-era build minted fragments
   at g = 0, which was wrong):** the fragment's `g_since_split` at
   mint is `g_end = DES_G_FRAC × n_gen × rate_mult` — its n_gen
   descent generations × the lineage's rate multiplier (fauna RFC §1,
   drawn once via pinned k15.g; content-addressed, so the descent
   reading it before the mint loop changes nothing), on the rounds'
   generation-time g scale. DES_G_FRAC = 3.0 (cal): the fast-tail
   head-start — the tree's fast lineages (tempo n_gen×rate_mult p90 ≈
   187, seed 1) × 3 ≈ 560 clear the MEDIAN g* (500), so fast lineages
   rank as new SPECIES at the first commit; the median tempo (p50 ≈
   52) × 3 ≈ 156 stays below the MINIMUM g* (160.7) — slow trees land
   far below, SUBSPECIES candidates. Normal clones stay g = 0; the
   species record's traits are NEVER modified.
5. **Rank at the first commit (the rebuild's rank path):** the
   authority ranks a fragment minted with birth-g at its FIRST commit
   — `classify(g_end, the LINEAGE's g*)`: beyond g* → a real SPECIES
   node (a branch: the tree gains width), below → SUBSPECIES node.
   EXEMPT from the cluster floors (CLUSTER_MIN_SIZE /
   CLUSTER_PERSIST_ROUNDS — those guard emergent wobble, not earned
   divergence), PROVIDED the fragment's scalar-only trait distance
   from the orthodox record EXCEEDS the lineage's merge threshold
   (the commit-time per-lineage threshold, §9 — else it merges back
   into the parent immediately: no rank; it was not actually
   diverged). A fragment that IS the orthodox (its lineage's other
   instances were all carved off) keeps — it is the lineage's
   continuity; the normal amend ratchets the record toward it and the
   normal stem-promotion path speciates it later. The engine passes
   birth-g per instance to `authority.update()` (the same channel as
   g_star / merge_d), ONE-SHOT at the fragments' first commit. NO
   seed_clusters, NO genesis-time tree writes — round 0 does nothing
   to the tree.

Hard constraints (owner rulings, 2026-08-02):

- **Simulation-free, practically free**: NO `stress_adapter.evaluate`
  calls inside the descent loop — the blob cells' per-requirement
  provenance is already in the genesis §5.1 reduced cache (`prov` at
  the worst month, `F_worst`, `U`). ONE evaluate per ADAPTED INSTANCE
  (its amended view) for its own cache — that's it. Wall target:
  single-digit seconds added to genesis (not minutes).
- **Eligibility gate IS the whole freak-tail handling**: `K_L >=
  N_FLOOR·percap` in the genesis seeding mask (one-line, toggleable
  `GENESIS_K_L_GATE`, default True) drops the clamp-bound freak-tail
  residual (u ≈ 1e5 artifact). The descent is seeded-only (above), so
  gate-excluded clamp cells are never candidates — there is NO rescue
  arm until a real substrate-fit (U or percap) lever exists (none
  wired today: nothing pressures crown_spread_m/woodiness, and U is
  not trait-pressureable).
- **Determinism**: all draws via pinned `k15.descent` streams (per
  species; content-addressed children per blob/draw); the k15.genesis
  draw sequence is never perturbed (separate stage). P_ADAPT = 0 +
  gate off ⇒ the pass is a no-op and genesis is byte-identical to
  HEAD.
- Per-species AND per-blob rolls as the owner's sentence reads (species
  gate, then each blob independently). Roll probabilities are named
  module constants (`descent.P_ADAPT`, `descent.P_BREAKOFF`).
- Descent mechanics: aggregate the blob's cached provenance into one
  verdict (compose → `FloraSim.select` → pressure plane), mutate the
  new instance's traits for a small generation budget (n_gen =
  clip(ceil(ROUND_YEARS/gen_time), 1, N_GEN_CAP), gen_time =
  2·sqrt(height_m) — the engine idiom, from the RECORD view's height)
  against the fixed pressure, NO re-eval inside the loop, NO
  steady-tier gate / novel tail (rounds phenomena; this is the
  ticket's "clean adaptation signal"). The species record's traits
  are NOT modified.

As built (clone @ 2c4513f + the rebuild, `exp/k15_descent/descent.py`
+ `engine._pregenesis_descent` + `authority._process_group` step 0):

- **Roll scheme**: species gate `P_ADAPT = 0.1` (content-addressed
  child "adapt"); per blob `P_BREAKOFF = 0.2` (child "break:{i}", in
  the pinned connected-components emission order). Blob i's instance
  id draws `rng.child("mint:{i}")`; the descent's per-generation
  mutate streams are `rng.child("mutate:{iid}:{gen}")` — every draw
  content-addressed, so draw order never matters.
- **Blob definition**: `ok_ungated ∧ (s_env ≥ S_ENV_TAIL ∨ K_L <
  N_FLOOR·percap)` — the marginal band of the viable range (s_env ≥
  S_ENV_TAIL = −0.15: F_worst ∈ [0.5, 0.575]) UNION the clamp-bound
  freak-tail residual (the gate's drop set — gate-excluded cells are
  never candidates; the gate IS the whole freak-tail handling);
  connected components (8-connectivity) ≥ DESCENT_MIN_BLOB_CELLS = 8.
- **g-earning**: `g_end = DES_G_FRAC × n_gen × rate_mult` with
  `DES_G_FRAC = 3.0`; the engine mints the fragment at
  `_g_since_split[iid] = g_end` and hands `_birth_g[iid] = g_end` to
  `authority.update()` at the first commit (cleared after — a
  fragment ranks exactly once).
- **Rank path**: `authority._process_group` step 0 — before the
  cluster graph, each birth-g instance (sorted instance id) is
  classified: rec_merge[i] ≥ thresh → `_divide` (SPECIES if
  birth-g > g*, else SUBSPECIES), else MERGE into the orthodox
  parent. Ranked/merged members are excluded from the cluster
  adjacency (the persistence tracker never re-sees them as emergent
  geometry). Runs before the amend; the SPECIES rank is born promoted
  (never re-promotes).
- **Seeded-only mint**: the adapted instance is minted over the
  blob's SEEDED part only — N = `_n_field(seeded, K_L, percap_a)` at
  founder demand with the ADAPTED percap, box from the seeded mask,
  verdict/pressure from the seeded cells' cached prov.
- **Parent surgery**: the seeded part is zeroed from the owning
  clone's range in place; a clone emptied entirely is not minted. A
  broken blob with no seeded cells is skipped entirely.
- **Empty roll ⇒ byte-identical**: P_ADAPT = 0 + gate off ⇒ genesis
  byte-identical to HEAD (verified on the clone).

Measured (seed 1, clone @ 2c4513f + the rebuild, 2026-08-02):
14/102 species rolled in, 26 adapted instances from 356 harsh blobs
(42 break-off blobs skipped — no seeded cells). Genesis wall:
gate-only ≈ 7.9 s → gate + descent ≈ 8.7–9.3 s (+0.9 s — the 26
per-adapted-instance evaluates; absolute walls on this shared box are
load-noisy, the deltas are not). r1 fragment fates: 5 SPECIES (birth-g
beyond the lineage g*), 7 SUBSPECIES, 11 merged back (scalar distance
below the lineage's commit-time merge threshold — not actually
diverged), 3 dead in round 1 (the first-round extinction wave, never
committed); no fragment is KEEP except a sole-survivor. Distinctness:
ranked fragments' scalar distance to record med 0.0078 (range
0.0045–0.0222) — each cleared its lineage's commit-time threshold by
construction. 10-round speciation vs the P_ADAPT = 0 control (both
gate on): branches 50 vs 47 (+3), subspecies 47 vs 33 (+14), total
divides +17; living lineages 102 → 107 (peak 112 at r3, never below
the 102 start) vs the control's monotone fall 102 → 94. Ranked
fragment persistence: 9/12 ranked lineages still alive at r10, 1
descendant divide from a ranked lineage. Determinism: genesis + 3
rounds double run byte-identical (836 instances); P_ADAPT = 0 + gate
off byte-identical to HEAD (772 instances, digest `cmp` clean).

## 11. Module layout

```
exp/k15_simdiff/
  req_flora.py        (landed)      stress_adapter.py   (landed)
  engine.py           round loop + context wiring (§4, §5.0, §10.1 hook)
  genesis.py          §10           dispersal.py        §7
  population.py       §6            authority.py        §9 (+reflog,
                                                     §10.1 rank step 0)
  test_engine.py      §12           __main__.py         extend: rounds demo
  persist.py          §12/0013      the delivery dump — per-instance
                                    density fields, amended tree, reflog,
                                    high-res display pass + viewer pack
                                    (exp/k15_simdiff/out/seed_NNNNNNNN/)
exp/k15_descent/
  descent.py          §10.1         (ticket 0018: the adapted fringe +
                                    g-earning; P_ADAPT/P_BREAKOFF/
                                    S_ENV_TAIL/DESCENT_MIN_BLOB_CELLS/
                                    DES_G_FRAC)
```
Pure functions + named module constants throughout (house style);
numpy-vectorized per-cell updates, per-instance Python loops (instance
counts are small).

## 12. Acceptance (the §8-style gate, `__main__ --seed 1`)

1. **Determinism**: two full runs (R = 20 rounds) byte-identical JSON.
2. **Range tracking**: occupied cells' mean s_env < unoccupied cells'
   for every lineage alive at R (reported per lineage).
3. **Genesis partition diverges / real cladogenesis**: ≥ 1 clone pair
   of one species registers subspecies-or-split within R rounds, and
   at least one SPLIT is a BRANCH (a subset of the lineage re-keyed —
   a real daughter) so the living lineage count GROWS at some point
   over the run (the v0.8 wholesale promotion never grew it; v1.2's
   cluster-level divide does). Subspecies fires at least once
   (reported with sid, round, cluster size, persistence).
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
8. **Performance**: genesis (150 species evals, ticket 0004) + 20
   rounds ≤ 60 s wall; cache ≤ REDUCED_CACHE_MB (3.9 MB) per live
   instance.
9. **Hard-rule audit**: no uuid/random/time; every stream traces to K1
   (grep + a runtime guard in test_engine).
10. **Delivery (ticket 0013)**: the rounds demo writes the dump under
    `exp/k15_simdiff/out/seed_NNNNNNNN/` — per-instance density fields
    (bbox + mask + N, windowed), the amended tree (k13 schema,
    post-rounds), the authority reflog; two runs at the same
    (seed, rounds) are byte-identical (`cmp` the whole dump dir —
    sorted iteration, fixed dtypes, no timestamps in payloads). The
    viewer datapack (`delivery.k11pack`) renders the species-richness /
    lineages-present overlay; the high-res (1024²) density pass is
    display-only (edge-aware upscale + settlement diffusion, never
    fed back into a sim round).

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
| PACKET_BASE / PACKET_AREA_REF / PACKET_MAX | 7.2 | 2 / 32 / 8 | packet count baseline / ref area / cap |
| LOCAL_BIG | 7.2 | 0.5 | local share for radius-2 spill |
| WIND_K / WIND_MAX_CELLS | 7.2 | 1.0 / 40 | wind distance scale / ray-length cap |
| WATER_LAMBDA / WATER_MAX_CELLS | 7.2 | 20 / 40 | water decay scale (v0.6: mobility reach only) / walk cap |
| ANIMAL_RADIUS_CELLS | 7.2 | 5 | animal packet disk radius |
| JUMP_SCALE / JUMP_RADIUS_CELLS | 7.2 | 1.0 / 50 | jump prob scale / landing roll radius |
| JUMP_DISK_RADIUS | 7.2 | 3 | v0.6 jump packet blob radius (~28 cells) |
| RAIN_HALF | 7.3 | 0.5 | rain half-saturation (per-cell gate form) |
| EST_F_MIN / EST_N0 | 7.3 | **0.3 (settled)** / 0.05 | establishment gate floor / per-cell founder density (v0.5 gate form) |
| EST_BETA | 7.3 | 1.0 | packet habitat power (0 = stress-blind) |
| MEM_ROUNDS / MEM_PENALTY | 7.3 | 3 / 0.25 | colonization memory retention / down-weight |
| SEEDBANK_KEEP | 7.3 | 0.5 | persistent rain carryover |
| GENESIS_F / GENESIS_F0 / GENESIS_COVER | 10 | **0.5 (settled)** / **0.1 (ticket 0020)** / **0.5 (ticket 0020)** | genesis threshold / capacity-relative sparse founder demand fraction / per-component coverage keep probability (partial range coverage) |
| ~~GENESIS_MIN_CELLS~~ | — | REMOVED (ticket 0039, v1.9) | the genesis mint floor is gone — every proximity blob mints however small; see §15 v1.9 |
| GENESIS_K_L_GATE | 10.1 | **True (ticket 0018)** | eligibility gate — seed only where K_L ≥ N_FLOOR·percap (the whole freak-tail handling: the descent is seeded-only, so gate-excluded clamp cells are never candidates; toggleable — off + P_ADAPT=0 ⇒ genesis byte-identical to HEAD) |
| P_ADAPT / P_BREAKOFF | 10.1 | **0.1 / 0.2 (ticket 0018, cal)** | species' chance at adaptation (ONE pinned roll per species) / per-harsh-blob break-off probability |
| S_ENV_TAIL / DESCENT_MIN_BLOB_CELLS | 10.1 | **−0.15 / 8 (ticket 0018, cal)** | marginal-tail threshold on s_env (F_worst ∈ [0.5, 0.575]) / minimum harsh-blob cells to break off |
| DES_G_FRAC | 10.1 | **3.0 (ticket 0018 rebuild, cal)** | g-earning scale: g_end = DES_G_FRAC × n_gen × rate_mult — the fast-tail head-start (fast lineages clear the median g* 500; slow trees stay below the min g* 160) |
| PART_AREA_REF / PART_K_MAX / PART_MIN_CELLS | 10 | 200 / 8 / 20 | partition knobs |
| RE_EVAL_D | 5.1 | 0.15 | cache invalidation distance |
| DIFF_D / MOB_K | 7.3 | **0.2 (cal)** / 1.0 | verdict-gate base / mobility gain |
| DIFF_MIN_CELLS | 8 | **32 (cal)** | divergent sub-range split floor |
| SUB_D / MERGE_D / MERGE_GRACE | 9 | **0.08 (v1.2, scalar-only)** / **0.045 (FALLBACK only, v1.3)** / **0 (v1.3, immediate)** | commit cluster edge on the scalar-only metric / fixed merge-gate fallback for no-map update() calls (the rounds read the per-lineage threshold) / rounds since divergence before a merge is legal |
| MERGE_D_BASE / MERGE_D_RATE_REF / MERGE_D_EXP / MERGE_D_CAP | 9 | **0.012 (cal, ticket 0030)** / **28 (seed-1 median n_gen×rate_mult)** / **1.0 (fitted drift slope)** / **0.05** | per-lineage threshold anchor / rate-product reference (threshold(median lineage) = base) / exponent / saturation cap (below the cluster edge); re-anchored 0030 on the corrected provenance-vector baseline (0028's 0.03 was ~5× the true same-env floor) — th p50 0.0108 = 2.0× the clean drift p50 (0.0054), the 2–3× band |
| CLUSTER_PERSIST_ROUNDS / CLUSTER_MIN_SIZE | 9 | **3 (ticket 0010)** / **2 (ticket 0010)** | cluster stability floor (consecutive commits, member-overlap continuity) / min members for a divide-eligible cluster — the v0.7-disease churn control |
| SPECIATION_D | 9 | 0.35 | g-less FALLBACK divide rank (authority unit tests only; NOT a rounds currency since v0.7) |
| CONSOL_EVERY | 9 | **5 (kept, ticket 0028)** | full-lineage consolidation period (rounds); 0 disables the sweep |
| DG_DRIFT_BASE | 4 | 1.0 | g drift baseline (generation-distance per generation) |
| DG_ENUM_SHARE | 4 | 0.05 | g contribution of enum redraws (per generation) |
| ISO_G_GAIN / ISO_RAMP_ROUNDS | 4 | **1.0 / 2 (ticket 0010)** | Δg base multiplier at full isolation (1.0 = 2× at iso 1 — the RFC §1 pairwise 2× divergence rate) / rounds without gene flow to full isolation |
| G_STEP_REF | 4 | 100 | species-edge dg scale: rounds' novel-tail rate = p_novel·n_gen/G_STEP_REF per axis |
| STRESS_G_BOOST / G_STEADY_ONSET / G_STEADY_RAMP / G_REF / G_NOVEL / P_NOVEL_MAX / NOVELTY_MULT | 4 | forces.py | the g-clock and f(g) ramp constants (referenced, never duplicated) |
| SELECT_GAIN | 4 | **1.0 (reverted, ticket 0030)** | the flora `select()` provenance→pressure gain (flora/sim.py: scales the verdict shortfall×row-weight mapping; stress function, mortality, NUDGE_RATE untouched; 1.0 = bit-identical HEAD) — 0029's "2.0 empirical optimum" was an AGGREGATE artifact of the \|Δ mean s_env\| same-env class (corrected provenance-vector baseline: gain 2.0 raises the clean drift band 0.005→0.0177 AND erodes the per-lineage threshold via the taller-lineage→halved-n_gen channel → 56% vs 22% clean-pair recombination failure); reverted to 1.0 — the discrimination job sits on the 0030 tight threshold; the knob stays for experiments; see §15 v1.4/v1.5 |
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

- **v1.9** (2026-08-04, ticket 0039 — owner ruling): the genesis mint
  floor GENESIS_MIN_CELLS is REMOVED entirely, in both roles (the
  blob-level floor in the species rain AND the engine's bundle
  seeding; the inside-blob island drop in _clone_units). Every
  proximity blob is mintable however small. Rationale (owner note
  item 1a): speckle instances can't emit propagules anyway (emission
  comes from occupied frontier cells) and neighbor speckles already
  join into one instance via the proximity join — the floor bought
  nothing. Measured seed 1: 94 → 107 species minted, 59,465 → 67,587
  cells occupied, sub-12 instances 4 → 1,739 (dominated by in-blob
  strip units minting single-instance). The ticket-0004 unseeded
  bucket is now zero-range ONLY. Descending prose that still names
  the floor is stale pending the rewrite-era spec cleanup
  (biosphere-plan-2026-08-04.md §7).
- **v1.7** (2026-08-02, ticket 0013 — the delivery pass): K15 stops
  dying with the process. `persist.py` writes the per-run dump under
  `exp/k15_simdiff/out/seed_NNNNNNNN/` (k11/k14 convention, registered
  as the "k15" artifact generator): `density.json` (per-instance
  WINDOWED density fields — bbox + N f8 + mask u1, sorted instance
  ids; optional per-round snapshots under `rounds/rNNNN.json` with
  `--per-round`), `tree.json` (the amended tree — the SAME schema k13
  delivers, post-rounds, meta amended with delivered_by/rounds),
  `reflog.json` (the full authority decision record), `state.json`
  (the acceptance digest + run provenance), `delivery.npz` +
  `delivery.k11pack` (the viewer overlay: species richness, the
  lineages-present tooltip layer, and the high-res display pass).
  The high-res half (owner addendum 2026-08-01; display-only by
  default): each final-round instance density field upscaled to 1024²
  with edge-aware interpolation (bilinear field + interpolated-mask
  re-threshold — the k14 display-map de-blocking idiom, NOT raw 4x
  blocks) plus a settlement diffusion at delivery res (3x3 box
  average restricted to the instance's own hi-res mask), streamed
  into ONE running plane (never a per-lineage stack); display-only —
  nothing feeds back into a sim round. Viewer: `map.html` gains a
  `kind: "list"` layer (the lineages-present tooltip row); the k15
  pack is exercised by `viewer/test_k15pack.mjs` (+ pytest wrapper
  `exp/k11_worldgen/test_k15pack.py`, SKIPs when the pack is absent).
  Determinism gate: two full `--rounds 8` runs — `diff -r` on the
  whole dump dir is empty (byte-identical, incl. the binary pack/npz).
  Fast tier: 479 passed + the k14 datapack E2E (14/14) unaffected.
  Re-pins: none (the dump is additive; no existing test pins it).

- **v1.6** (2026-08-02, ticket 0018 REBUILD — pre-genesis descent
  with the earned-g first-commit rank): the adapted fringe returns
  (spec §10.1; v4-era P_ADAPT = 0.1 / P_BREAKOFF = 0.2 / S_ENV_TAIL =
  −0.15 / DESCENT_MIN_BLOB_CELLS = 8 / GENESIS_K_L_GATE = True, the
  seeded-only scope, cache-only sim-free descent, ONE evaluate per
  adapted instance — all preserved from the v4-era design), with the
  v4-era build's TWO fixes:
  1. **g-earning**: a fragment is minted at `_g_since_split = g_end =
     DES_G_FRAC × n_gen × rate_mult` (its descent generations × the
     lineage's rate multiplier, on the rounds' generation-time g
     scale) — the v4-era build minted fragments at g = 0, which was
     wrong (they could never rank by g). DES_G_FRAC settled 3.0: the
     fast-tail head-start — fast lineages (tempo p90 ≈ 187) clear the
     median g* (500); slow trees (tempo p50 ≈ 52) stay below the
     minimum g* (160.7). Normal clones stay g = 0; the species record
     is untouched.
  2. **First-commit rank**: the authority ranks a fragment minted
     with birth-g at its FIRST commit — `classify(g_end, the
     lineage's g*)`: beyond g* → a new SPECIES node (a real branch),
     below → SUBSPECIES node. EXEMPT from the cluster floors
     (CLUSTER_MIN_SIZE / CLUSTER_PERSIST_ROUNDS guard emergent
     wobble, not earned divergence), PROVIDED the fragment's
     scalar-only distance from the orthodox record EXCEEDS the
     lineage's merge threshold (else it merges back into the parent —
     no rank: it was not actually diverged). The engine passes
     birth-g per instance to `authority.update()` (the g_star /
     merge_d channel), one-shot at the fragments' first commit. NO
     seed_clusters, NO genesis-time tree writes — round 0 does
     nothing to the tree. The rank path is `_process_group` step 0
     (before the cluster graph); it coexists with the 0010 cluster
     path unchanged — handled members are excluded from the cluster
     adjacency, so the persistence tracker never re-sees them.
  Measured (seed 1, clone @ 2c4513f + the rebuild): 14/102 species
  rolled in, 26 adapted instances (356 harsh blobs; 42 break-off
  blobs skipped — no seeded cells); genesis wall gate-only ≈ 7.9 s →
  gate + descent ≈ 8.7–9.3 s (+0.9 s). r1 fragment fates: 5 SPECIES
  / 7 SUBSPECIES / 11 merged back / 3 dead in round 1 (no fragment is
  KEEP except a sole-survivor). 10-round speciation vs the P_ADAPT =
  0 control: branches 50 vs 47 (+3), subspecies 47 vs 33 (+14),
  living lineages 102 → 107 (peak 112, never below the start) vs the
  control's fall to 94; 9/12 ranked fragment lineages alive at r10, 1
  descendant divide. Determinism: genesis + 3 rounds double run
  byte-identical; P_ADAPT = 0 + gate off byte-identical to HEAD.
  Fast tier: 405 passed (401 + 4 new authority first-commit-rank
  tests). Re-pins (slow tier, measured): speckle floor →
  DESCENT_MIN_BLOB_CELLS // 2 (realized post-descent min 7);
  max_round_divides < 1000 (10-round max 206; the v4-era 20-round max
  with the fringe was 705).
- **v1.5** (2026-08-02, ticket 0030, threshold re-anchor + gain
  revert): both 0028's and 0029's calibrations sat on a CONTAMINATED
  same-env baseline — the |Δ mean s_env| class mixes genuinely-
  different selection vectors (same average stress, different
  per-factor shortfalls — e.g. cold vs dry). The corrected probe
  (tmp/k15_calib/corrected_baseline.py, seed 1 r6, pairs classed by
  the N-weighted per-requirement provenance-vector pdist — exactly
  what select() reads) shows the TRUE same-env floor is p50 0.005 at
  gain 1.0: 0028's median threshold (0.030) anchored ~5× too wide,
  and gain 2.0 is COUNTERPRODUCTIVE — it raises the clean same-env
  band (0.005 → 0.0177) AND erodes the per-lineage threshold (th p50
  0.026 → 0.0133 via the taller-lineage → halved-n_gen channel), so
  56% of clean same-env pairs fail to recombine vs 22% at gain 1.0
  (the 0029 "empirical optimum" was an aggregate-level artifact).
  Changes: SELECT_GAIN reverted 2.0 → 1.0 (1.0 × shortfall × weight
  == shortfall × weight, IEEE-exact — the knob stays for
  experiments); MERGE_D_BASE re-anchored 0.03 → 0.012 (the per-
  lineage form, exponent and cap untouched). Sweep (seed 1, gain
  1.0, r6 fractions + r16 instance distributions):

  | base | th p50 (× drift p50) | RECOMB d<th @ pdist<0.02 | BLOCK d≥th @ pdist≥0.05 / ≥0.10 | r16 instances / p50 / max / %>10 |
  |---|---|---|---|---|
  | 0.030 (0028) | 0.0261 (5.2×) | 0.78 (n=211) | 0.11 (n=395) / 0.00 (n=4) | 251 / 2 / 15 / 2% |
  | 0.015 | 0.0079 (1.3×) | 0.65 (n=294) | 0.51 (n=620) / 0.61 (n=33) | 373 / 2 / 19 / 9% |
  | **0.012 (settled)** | **0.0108 (2.0×)** | **0.62 (n=333)** | **0.46 (n=528) / 0.34 (n=35)** | **377 / 2 / 21 / 8%** |
  | 0.010 | 0.0073 (1.3×) | 0.61 (n=555) | 0.61 (n=809) / 0.68 (n=44) | 472 / 2 / 34 / 14% |

  Settled MERGE_D_BASE = **0.012**: the median-lineage threshold
  (th p50 0.0108) = 2.0× the clean same-env drift p50 (0.0054) —
  the owner's 2–3× band (0.03 sat at 5.2×, 0.015/0.010 at 1.3×,
  too tight for the median lineage's fresh pieces) and below the
  ratchet tail (clean d p90 ~0.043 — old same-env pieces past any
  sane threshold by design: drift retention → the 0010 path, not a
  bug). Clean same-env recombination holds (0.62 — the ~38%
  failures are ratchet-tail pieces at clean d p90 0.037), cross-env
  blocking quadruples vs the 0028 baseline (0.11 → 0.46 at pdist≥0.05;
  the pdist≥0.10 class is small at r6, n≈35, and within-lineage
  environment-differentiated pairs accumulate later), and the r16
  fat-blob ~1–10 model holds (377 instances / p50 2 / max 21 / 8%
  species >10 vs 251 / 2 / 15 / 2% at 0.030 — the count responds
  +50% as recombination tightens; 0.010 starts to stretch it: 472 /
  max 34 / 14%). 0010 path at the settled values (20 rounds, the
  slow gate's own print): branches 66 / subspecies 4 / lineage
  102 → 97 plateau / max divides/round 135 (the 0028 reference
  62 / 38 / 102→97 — the tighter threshold shifts divides toward
  branches and away from the late subspecies burst; all divide
  asserts hold); full-run acceptance: 20 rounds, 285 instances /
  97 lineages, range-tracking margins all negative; determinism:
  gain 1.0 + base 0.03 byte-identical to 0028's HEAD (state-digest
  sha256 2212bbd8…, r16, 251
  instances/98 lineages both sides), settled values byte-identical
  double run (sha256 21adcf7b…, r16, 377/96) plus the slow gate's
  own 20-round double-run; gates: fast 401 green (45s) with ZERO
  re-pins, slow gates 5 passed (0:03:47) with ZERO re-pins
  (first-merge ≤ r1, plateau, range-tracking, churn bound all hold).
- **v1.4** (2026-08-02, ticket 0029, select-pressure gain — settled
  SELECT_GAIN = 2.0): adds the `SELECT_GAIN` lever — the flora
  `select()` provenance→pressure gain (`flora/sim.py`, applied at the
  verdict shortfall×row-weight mapping; the env→suitability stress
  function, mortality, and NUDGE_RATE are untouched per the owner's
  constraint). Gain 1.0 is bit-identical to HEAD (probe JSON
  byte-compared). Calibrated on seed 1 (work clone tmp/k15_gain,
  probe_0029_calib.py — the 0028 methodology: per-round scalar-only
  distance on same-lineage pairs, same-env |Δ mean s_env|<0.05 vs
  cross-env ≥0.15, cumulative d p50/p90, per-pair lineage threshold):
  swept gains 1.0/1.5/2.0/3.0/5.0 over r0–r5 plus 15-round runs at
  1.0/2.0. Result: the bands do NOT separate by cross/same p50 SEP at
  any gain (~0.9–1.5 through r15; transient peak 2.3 at gain 1.0 r6) —
  same-lineage pairs within the |Δ s_env|<0.05 class carry a real
  selection component (per-factor shortfalls differ cell to cell), so
  the gain amplifies same-env divergence nearly 1:1 with cross-env.
  BUT the gain does grow the ADAPTIVE component where it counts, at the
  per-lineage THRESHOLD: gain 2.0 is the empirical optimum — the
  cross-env minus same-env frac_d≥threshold margin turns consistently
  positive in the r4–r8 window (+0.03 to +0.08, four of five rounds
  ≥ +0.05 vs ±0.03 noise at gain 1.0), i.e. the merge threshold
  discriminates cross-env from same-env exactly in the window where
  the steady-tier gate opens. Where the gate bites: the adaptive burst
  is suppressed through r5 (fraction g>200 13% → 46% r0→r5, gate_mean
  0.24; g>400 ~16% — the steady axes move at ~0.4–0.6× only for the
  top decile), fires in the r6–r8 window (the discrimination above),
  then washes out by r9+ as lineages grow tall, n_gen falls and the
  per-lineage threshold erodes (th_p50 0.026 at r5 → 0.005–0.015 by
  r14 even at gain 1.0). Gains ≥3 break the model: faster adaptation
  makes lineages taller (gen_time p50 3.9 → 7.8 yr at gain 5.0),
  halving n_gen and collapsing the 0028 threshold (th_p50 0.006–0.018
  at gain ≥2 r5), same-env recombination fails (same-env frac_d≥th 0.33
  → 0.74–0.90) and instances explode (281 → 717 at r5, gain 3.0).
  Settled: SELECT_GAIN = **2.0** — re-measured at it: per-species
  instances r16 p50 2 / max 14 / 97% ≤10 (0028 baseline 2 / 15 / 98% —
  the fat-blob model holds; 251 → 310 instances, +24% cross-env
  persistence, +2 live lineages), the 0010 path intact (64 branches /
  78 subspecies / 20 rounds vs 62 / 38), determinism byte-identical
  double run (slow gate), fast tier 138 green with ZERO re-pins, slow
  gates green with zero re-pins (the §12.3 first-merge ≤ round 1, the
  plateau, the range-tracking and churn bounds all hold at 2.0).
  Remaining limitation (owner-anticipated): this is an early-rate
  lever, not a steady-state separator — SEP stays ~1.2–1.5, the
  steady-state blocking still rides the contact gate + clusters;
  follow-up candidates: same/cross classes on the verdict-pressure
  vector instead of mean s_env, or pricing the gen_time feedback into
  the 0028 threshold.
- **v1.3** (2026-08-02, ticket 0028, immediate recombination +
  mutation-tuned threshold): the consolidation machinery is corrected
  to the owner's design. §9: (a) the fixed MERGE_D = 0.045 merge gate
  becomes a PER-LINEAGE threshold = min(MERGE_D_CAP, MERGE_D_BASE ×
  (n_gen × rate_mult / MERGE_D_RATE_REF)^MERGE_D_EXP) — tight at the
  reference rate (a differing environment diverges past it, so
  environment acts through the genetic channel, no environment field)
  and widened with the species' inherent mutation rate (fast mutators
  drift apart quickly; their own same-environment pieces would cross a
  fixed tight threshold and never recombine). The engine computes it
  per commit (per lineage, from the max-mass instance's height —
  gen_time = 2·sqrt(height_m) — and the lineage's rate_mult, fauna
  RFC §1) and passes it to the authority's update() as a per-sid map,
  the same channel as g_star; the authority falls back to the fixed
  MERGE_D for no-map calls (unit tests). (b) Merge candidates are
  processed EVERY round (event-driven, contact-gated) with
  MERGE_GRACE = 0 — same-environment pieces recombine immediately
  (the genesis stacks collapse at the round-0 commit; the range
  grows); the round-4 CONSOL sweep is kept as the instance-count
  backstop (measured without it: seed-1 r16 1341 instances / per-
  species p50 12 / 55% species >10 vs 251 / p50 2 / 2% with it). (c)
  The merge metric is unchanged: scalar-only trait distance, no
  environment field. Calibrated on seed 1 (work clone tmp/k15_consol):
  the same-env and cross-env drift bands OVERLAP (cross-env divergence
  only ~1.2-1.3x same-env, not separable per round — the threshold
  sits at the same-env band: median lineage 0.030 vs same-env
  cumulative age-4 p50 0.012 / p75 0.023; cross-env persistence rides
  the contact gate + cluster/divide machinery); same-env per-round
  drift scales linearly with n_gen×rate_mult (log-log slope 1.00).
  Instance distribution at r16: baseline 3876 instances / per-species
  p50 20 / max 595 / 66% species >10 -> v1.3 251 / p50 2 / max 15 /
  2% — the owner's ~1-10 per species with fat blobs. Divides still
  fire (62 real branches and 38 subspecies over the 20-round slow
  gate — the 0010 path is intact; non-touching clones are unaffected
  by merges; the lineage count plateaus at its trough, 102 -> 97,
  instead of the v1.2 recovery — the re-pinned genesis-diverges
  assert). Determinism:
  byte-identical double run (slow gate re-pinned); the §12.3 grace
  assert becomes the immediate-recombination assert (first merge ≤
  round 1); fast-tier fixtures re-pinned to the new schedule (the
  round-4 consolidation, the immediate stacked merge, the canopy
  window, the sweep-free drift-retention pair). Owner intent recorded
  verbatim in tmp/tickets/open/0028-consolidation-recombination.md.
- **v1.2** (2026-08-01, ticket 0010, real cladogenesis): the divide
  machinery moves from the wholesale g-promotion to CLUSTER-LEVEL
  divides. §9: (a) the cluster graph reads the SCALAR-ONLY metric at
  SUB_D 0.08 (the full metric's enum contribution would spuriously
  separate same-blob pairs at the lower edge; the full metric stays
  for distance-to-record and the g-less SPECIATION_D fallback);
  (b) every non-orthodox cluster is tracked across commits
  (member-overlap continuity — rep changes and member churn don't
  reset it) and must be a stable component for CLUSTER_PERSIST_ROUNDS
  (3) with ≥ CLUSTER_MIN_SIZE (2) members before it may divide — the
  v0.7-disease churn control (per-instance g crossings churned
  hundreds of spurious splits/round); (c) an eligible cluster divides
  off as a real daughter: below the lineage's g* as SUBSPECIES,
  beyond g* BRANCHES as its own SPECIES node (the old rule — beyond-g*
  fragments rode the wholesale promotion, a relabeling that never grew
  the lineage count — is gone); (d) the wholesale promotion is
  narrowed to the STEM's own commit: the orthodox crossing g* re-keys
  the REMAINDER (cluster divides run first, so a same-commit crossing
  fragment branches instead of riding it); (e) clusters are
  merge-exempt BY CONSTRUCTION (scalar d ≥ SUB_D > MERGE_D and the
  in-orthodox gate), so the CONSOL governor can never reset a
  persistence clock; (f) `seed_clusters` registers a pre-seeded
  round-0 cluster geometry with full persistence credit (ticket 0018
  synergy — pre-genesis per-clone descent, design-only today).
  §4: the forces.py Condition ISOLATION input is wired into Δg —
  rounds since the instance last touched a same-lineage sibling
  (the engine's spatial contact gate), ramped over ISO_RAMP_ROUNDS;
  a fully isolated lineage accrues g at (1 + ISO_G_GAIN)× (ISO_G_GAIN
  = 1.0: the fauna RFC §1 pairwise 2× divergence rate); single-instance
  lineages are never isolated. Island clones speciate first (allopatric
  tempo); the genesis partition clones are their natural first
  subspecies (option E falls out). Measured seed-1 30-round run (see
  tmp/k15_clado scratch): baseline — lineage count 100 → 91 (0
  subspecies ever, ~118 divides all wholesale promotions, tree SPECIES
  nodes 150 → 219 depth-only); v1.2 — lineage count 102 → 99 with a
  back-half RECOVERY 92 → 99 (branches outpacing die-outs; ~97 real
  daughter species over the run, promotions down to ~31 — fragments
  branch instead of riding), subspecies fires 74× (rounds 19/23/27,
  all from one slow lineage's clones — below-g* clusters), splits/round
  max 464 (one-off promotion waves, not sustained churn; the v0.7
  disease was 100s of spurious splits EVERY round), merges 11674
  (sane), tree SPECIES nodes 150 → 229 (width AND depth).
- **v1.1** (2026-08-01, ticket 0020, DESIGN PIVOT): sparse founders +
  partial coverage, NO density budget. The v1.0 budget gate (batch
  rain with a world-level cumulative density field, streaming
  admission while cum + D ≤ GENESIS_BETA · K_L in pinned sid order,
  one erosion sweep, relocation-or-drop) met its done-means (u p50
  0.76, frac u>1 = 0, 54/150 lineages) but was rejected on realism:
  viable cells were claimed first-come-first-served in sorted sid
  order, so ~2 lineages filled a cell and late-sid species found their
  niche "already occupied" — 51/150 species budget-dropped at genesis,
  occupancy decided by name hash instead of fitness. Pivot: §10 seeds
  every viable (cell, lineage) pair at the capacity-relative sparse
  demand D = GENESIS_F0 · K_L (F0 settled 0.1 within 0.05–0.15; K_L
  reused from population.lineage_capacity; N = D/percap floored at
  N_FLOOR — the clamp stays) and applies PARTIAL coverage: per
  retained proximity blob (no size floor since v1.9/ticket 0039), a
  keep/drop draw from
  `Stream(seed, "k15.genesis", sid).child("cover:{i}")` with keep
  probability GENESIS_COVER (settled 0.5) — whole blobs kept or
  dropped, never speckled cells; a species whose every drawn component
  is dropped keeps its single largest component unconditionally, so
  the coverage draw never causes extinction (only the ticket-0004/
  0009 paths drop species: zero range, all-sub-floor). The budget,
  erosion sweep and relocation are REMOVED; competition is left to the
  rounds. Measured genesis (seed 1): 102/150 lineages minted (48
  unseeded: 4 zero-range + 41 all-sub-floor + 3 all-below-K_EPS — no
  occupancy lockout), 622 instances, 80046 pairs over 15065 populated
  cells (stacking mean 5.31 / max 30), clone blobs p50 59 / mean 129 /
  min 32 (no speckle), per-lineage partition disjoint, realized
  coverage (minted/viable, per-species median) 0.29 (0.55 by
  retained-blob cells — the sub-floor speckle dilutes the viable-cell
  metric). **Utilization at genesis: u p50 1.22 / frac u>1 0.58**
  (max ~4e5: the tiny-K_L pairs clamped to the N_FLOOR floor) — the
  done-means u targets (p50 < 1, frac < 0.1) are NOT reached. The
  owner's "u ≈ F0 · n_stack" model assumes equal substrate shares; on
  seed-1 data the median pair's U is ~1/12 of its cell's total ΣU
  (U p50 0.33 over pairs, ΣU ≈ 4 per populated cell), so u = F0 ·
  ΣU/U_j stays ~1.2 at F0 = 0.1 and frac u>1 ≈ 0.58 — and NO (F0,
  COVER) in the allowed ranges reaches frac u>1 < 0.1 (measured
  frontier: F0 0.05/COVER 0.3 → 0.31; F0 0.03/COVER 0.15 → 0.145;
  the clamp alone forces 13% of pairs above F0·K_L). Reaching the u
  done-means requires either a density gate (rejected) or an owner
  ruling that density competition at birth is intended (the pivot's
  stated rationale); the structural invariants — lineage survival,
  blob floor, disjointness, no speckle, determinism — all hold.
  Determinism: coverage draws are pinned child streams, byte-identical
  double run (622 instances). Fast tier green in the clone;
  test_genesis.py re-pinned for the covered ranges (the pre-coverage
  retained pins yarrow 3267 / seagrass 1722 hold) + new slow
  test_genesis_species_sparse_founders.
- **v0.9** (2026-08-01, ticket 0009): the genesis mint floor — §10
  drops the seeded-range connected components below GENESIS_MIN_CELLS
  (32 cells, the DIFF_MIN_CELLS sliver scale) before the partition:
  speckle colonies are never minted as established instances (option
  (a); §7 dispersal can re-find those cells), and K targets the
  RETAINED range (the cells actually minted). Measured genesis (seed
  1, final world — the cold gate 2cc8e76 and the dune/lake-fetch gates
  0d432c5/758ec17 reclassified thousands of seed-1 cells, moving the
  mint 1316 → 1333 → 1316 instances): 14800 pre-floor components →
  1316 instances across 105 lineages (vs 146 pre-floor — 41 species
  whose every component is sub-floor are never minted and take the
  ticket-0004 zero-range extinction path, 45 unseeded in total
  including the 4 zero-range), clones/lineage median 11 / p90 24 /
  max 35; K ≤ 8 never exceeds the retained component count on seed 1,
  so the one-clone-per-component floor still governs (the partition
  dominates only for species with fewer than K fat blobs). Round
  times: genesis ~7 s (vs ~19 s v0.8), r0 ~9–11 s (vs ~45 s) rising
  to ~15–27 s as dispersal grows the instance count (r19: ~3500
  instances, ~90 lineages — see the v0.9 measured trajectory) — the
  §9 CONSOL sawtooth bounds the steady state in the same band as v0.8
  (r4 max 4606 → r29 2142). Determinism unchanged: the floor adds no
  draws (the
  component scan is deterministic; the drop happens before any rng
  consumption), so same-seed runs remain byte-identical — the mint
  stream addressing is unchanged except that dropped components never
  reach the partition (re-pinned fixtures in test_genesis.py).
- **v0.8** (2026-08-01, ticket 0004): genesis seeds the radiated tree
  — §10 now rains every SPECIES node of the committed tree (~150 sids)
  instead of the 35 authored presets: each species gets its own range
  evaluation (its OWN radiated view, not the authored preset record),
  partition and clones; the 35 ORDER nodes are ancestors, never seeded
  ("completely written at L0"). One adapter evaluation per species —
  `genesis.genesis_species` returns the full evaluated factors and the
  engine builds its §5.1 cache from the SAME evaluation (the
  pre-ticket 2-evaluations-per-preset pattern is gone). Zero-range
  species are never minted: `TreeAuthority.register_unseeded` puts
  them in the authority's alive set so the normal update() extinction
  pass marks them extinct at the first commit (reflog entry, ghost
  record) — measured 4/150 on seed 1. Measured genesis (seed 1):
  14751 instances across 146 lineages in ~19 s (vs 3584 across 35
  order lineages in ~7 s pre-ticket); instance count decays 14751 →
  ~10k by r1 as the many small founders die or consolidate, and the
  §9 CONSOL sawtooth bounds the steady state from round 9 on.
  Determinism unchanged: species processed in sorted sid order, all
  draws on pinned k15 streams (the mint/partition streams are now
  keyed by species sid instead of preset id — byte-identical
  re-runs); two full runs remain byte-identical (the §12.1 gate
  re-pinned on the new digest). The §12.8 cache budget is unchanged
  (per-species shared caches, same ~3.9 MB reduced form).
  Companion fix (same ticket, same boundary): §9's merge-candidate
  handling now BUCKETS the same-lineage candidate pairs per species
  once in update() — the pre-bucket code re-sorted and scanned the
  FULL candidate set inside every group's _process_group
  (O(groups × pairs)), which blew up the CONSOL commit at the
  radiated tree's lineage counts (measured ~394 s at commit round 4,
  seed 1; ~30 s after — behavior identical, verified by the
  authority unit tests and the byte-identical two-run gate).
  Measured round times with the fix (seed 1, ticket 0004): ~40-45 s
  steady (verdict feed dominates), CONSOL commits ~30 s; instance
  count decays 14751 → ~7-9k through r8, with the first effective
  consolidation (MERGE_GRACE clears at commit round 5) at r9.
- **v0.7** (2026-08-01, ticket 0008): the g currency replaces the
  trait-distance speciation thresholds — fauna RFC §1's generation-
  time clock, three forces, and per-clade seeded g*, restated for
  flora (flora RFC). §4 verdict feed: instances carry g_since_split,
  accruing Δg = n_gen·rate_mult·(drift baseline + descent share·(1 +
  STRESS_G_BOOST·stress) + runaway share·ornament fraction + enum
  share) per round (forces.py Condition shares, isolation 0); lineage
  rate multiplier and g* drawn once via pinned k15.g streams; the
  mutation magnitude ramps with f(g) (step_scale × leaky steady-tier
  gate × the novel heavy tail, forces.py constants referenced not
  duplicated). §9: divide rank = classify(rep g_since_split, lineage
  g_star) for trait clusters AND a g-PROMOTION for the crossing
  cohort (instances past g* re-key to a new species node, grouped by
  trait connectivity at SUB_D — the divide trigger for the rounds,
  since a dense lineage is a continuous trait cloud that never splits
  at SUB_D on seed 1; one-shot per species node); SPECIATION_D
  demoted to the g-less authority-test fallback. The merge gate
  moves to a scalar-only L1 metric (enum/generic axes and weighted_set
  TV excluded — enum flips are measured same-blob noise) with
  MERGE_D = 0.045, calibrated on agent-58's scalar-only same-blob p99
  floor (≈0.073) and contrast p90 (≈0.057): same-blob pairs below the
  floor merge harmlessly while diverging pairs escape the CONSOL
  sweep (which erases the incipient cohort under the diluted full
  metric — 7232 contrast pairs at r5 → 0 alive at r25 pre-v0.7).
  Determinism preserved: all new draws ride k15.g streams; two full
  runs remain byte-identical. Measured (seed 1, tmp/k15_gcheck.py, 30
  rounds): the g-promotion fires on the emergent tempo — the fast
  lineages (duckweed/lichen-grade, n_gen 400) promote wholesale in
  rounds 0–6 (divide-time g ≈ 300–900 vs their seeded g*), the
  grass-grade lineages at ~r8–10 (the "~9 rounds" anchor), stragglers
  at r13–23, and the slow trees never cross g* within 30 rounds —
  their first divide lands beyond r30 (tempo split by design). Each
  promotion re-keys the whole gene pool to ONE species node (the
  instance-delta counts run 4–754); the old lineage's record stays as
  the ghost ancestor and is marked extinct. Turnover (item d): no
  die-out knob change was needed — the live lineage count holds at 35
  across all 30 rounds (each promotion is balanced one-for-one by the
  ancestor's extinction), no subspecies accumulate (zero SUBSPECIES
  divides fired on seed 1 — below-g* trait clusters never form in the
  continuous clouds), and the instance count is bounded by the CONSOL
  sawtooth (4606 max at r4 → 2142 at r29).
- **v0.6** (2026-08-01): packet colonization (owner ruling "tentacles,
  not dots", after the seed-1 dispersal stat pass: 120k→550k deposit
  cells/round, 9–12% isolated founded speckle, jump foundlings at
  median 1 cell, ~160 bridge-splits/round with 80% slivers < 32 cells).
  §7.2 replaces the per-source-cell deposit kernels (deposit_local/
  wind/water/animal and the SRC_CAP subsampling DELETED) with 1–8
  coherent packets per channel — filled spill blobs (local), tapered
  width-carrying rays (wind: length = ceil(λ), λ = WIND_K·speed/√mass),
  width-carrying D8/current walks (water), filled disks at a random
  reachable offset (animal) and a filled ~28-cell disk at the jump
  landing — each launched from a random FRONTIER cell (one pinned draw
  per packet, never per cell). §7.3 moves establishment to ONE weighted
  decision per packet (mean(f_hab^β) over the packet's unoccupied
  cells × establish, the EST_F_MIN gate, the §4 single-T conversion, ×
  MEM_PENALTY on remembered targets); the whole eligible blob founds at
  N = share/|founded| or nothing does. The per-cell gate form
  (`establish`, EST_N0, RAIN_HALF) is retained as the vanguard
  accounting's defining kernel; the per-cell EST_F_MIN gate keeps
  §12.6 (sink cells rain but never establish) cell-exactly. New
  per-lineage colonization memory (`_colon_mem`, MEM_ROUNDS=3): failed
  targets are remembered and down-weighted, purged deterministically
  each round. Rule B+ founding/dressing/commit are untouched. Measured
  (seed 1, 12 rounds): founded cells drop from 120k–550k to ~1.4–5.8k/
  round, isolated-founded fraction 1–4% (vanguard-gate carve-outs at
  suitability cliffs; 0 on fully viable ground), instance count settles
  at ~300–370 by r10–r11 (the consolidation sawtooth) vs 1135–1478,
  jump foundlings born at median 4–14 cells on the full world (28 on a
  clean meadow — the disk is carved by overlap with the emitter's own
  founded rays/blobs), mints+divisions fall from ~250–300 to ~30–150
  per round, round time 15–25s → 2–9s.
- **v0.5** (2026-08-01): §9 drift retention (owner ruling "keep WIP")
  — the commit re-sync keeps each surviving instance's WIP genes and
  pressure plane instead of re-minting from the record; sub-SUB_D
  divergence now ratchets (measured pairwise +0.00025/round between
  two same-lineage instances in contrasting cells vs. a hard cap at
  the one-round nudge pre-v0.5). Note distance-to-record stays 0 for
  the orthodox instance by construction (the commit amends the record
  to it, gerrit-style) — retention is only observable pairwise. This
  resolves the §12.3 divide-half blocker carried from v0.4.
- **v0.4.2** (2026-08-01): §9 consolidation (owner ruling) — the
  "final pass" joins also run periodically (CONSOL_EVERY=5 commits,
  complete same-lineage candidate pairs; authority still gates
  MERGE_D/MERGE_GRACE) as the instance-count governor; contact gate
  overlap-aware (star-topology candidates per overlapped cell — the
  shift grid was blind to same-cell stacking, measured 1132 layers in
  one cell at r19). Known unmet item carried from v0.4: §12.3's
  divide half — commit re-mint wipes sub-SUB_D divergence (measured
  max instance-vs-record drift 0.0000 at every round end over 20
  rounds); pending the drift-retention design ruling.
- **v0.4.1** (2026-08-01): §8 split hysteresis (owner ruling: more
  species and interleaved fauna rounds will multiply instance counts,
  so the rain-bridge split requires persistence) — a fragment mints
  only after two consecutive disconnected dressings (orphan cell tag;
  slivers pre-tagged). Cause-classified diagnostic (seed 1, r0-r5):
  63% of splits were same-round join/split oscillation, 15% transient
  mortality carves, 22% chronic — hysteresis absorbs the first two.
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
