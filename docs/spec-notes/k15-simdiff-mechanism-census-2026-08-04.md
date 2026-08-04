# K15-simdiff mechanism census — 2026-08-04

Raw material for the `k15_biosphere` rewrite (biosphere-plan-2026-08-04.md
Phase 3 prerequisite). A mechanism-by-mechanism map of the FROZEN
`exp/k15_simdiff/` engine: what every stage consumes, mutates, and draws;
what breaks if it is deleted; and a verdict — LOAD-BEARING / TUNING /
VESTIGIAL-SUSPECT — for each.

Provenance: six read-only explore agents, one per module scope, against
commit d18936d (fast tier 882 green, slow tier 19 green). Orchestrator
spot-checks (verified by hand, not agent-reported):

- `_f_magnitude` (engine.py:1236) has ZERO callers repo-wide — dead. ✓
- `_divide_g` (engine.py:449,1962) is write-only — no reader exists. ✓
- `Dressed.box` is **(y0, y1, x0, x1)** (engine.py:182) and persisted raw
  (persist.py:85), but `tools/artifact_query.py:28,148` decodes it as
  `[x0, x1, y0, y1]` — CONFIRMED mismatch (ticket 0040). Scalar answers
  (cells occupied, mass) are order-independent and stay correct; spatial
  answers (which cells, coexistence sets, connectivity, biome joins) are
  wrong for every non-square window. ✓

Everything else is agent-reported and unverified; treat file:line anchors
as pointers to check, not gospel.

## The spine — round stage order

`Engine.round(t)` (engine.py:1996), exact sequence per round:

1. `_canopy_light_factors()` (:1049) — computed ONCE at round entry
2. `_verdict_feed(t, light)` (:1135) — aggregate → select → g accrual →
   per-generation mutate → `_refresh` (the evolutionary core)
3. `_population(light)` (:1259) — per-round biomass accounting → `s_real`
4. `_dispersal(t, s_real)` (:1322) — emission, packets, founding
5. `_dressing(t)` (:1639) — div deferred split, rain-bridge split
6. `_commit(t)` (:1869) → ChangeLog (merges, divides, extinction)

Genesis (`run()` → `genesis()` :604 when no instances): species rain →
pre-genesis descent → species mint loop → adapted-fragment dress →
bundle seeding → `_cap_seed_demand` → `register_unseeded`.

Determinism: all draws content-addressed under pinned streams
(`k15.g`, `k15.genesis`, `k15.descent`, `k15.disperse`, `k15.found`,
`k15.divsplit`, `k15.split`, `k15.mutate`, `k15.commit`); all instance
iteration sorted by iid; float accumulation pinned sorted. Hygiene is
good throughout — this part of the architecture is worth keeping.

---

## Cross-cutting synthesis (orchestrator)

### The load-bearing core the rewrite must re-implement

In round order: genesis seeding core (`genesis_rain_species` +
`reduced`/`valid_mask`/`demand_field`/`_n_field` + coverage draws +
partition); the verdict feed (g clock, f(g) ramp, per-generation
mutation); the population vital chain (`update_instance`/`vital_update`
+ `lineage_capacity`); the dispersal packet pipeline (emission →
frontier → five channel shapes → one establishment decision per packet)
+ rule-B+ founding; dressing splits; the commit/authority machinery
(salience-weighted distance metric, orthodox-pick + amend ratchet,
cluster-graph persistence divides, merges, extinction pass, drift-
retention re-mint); and `persist.dump`.

### Three architectural diseases the rewrite must design away

1. **Duplicated pipelines that diverge silently.** THREE copies of the
   genesis seeding pipeline exist: the tests-only preset path
   (genesis.py:660 `_rain_for_view`/`genesis_preset`/`genesis_rain`),
   the live species path (genesis.py:760, which inlined a *divergent*
   copy with two extra gates), and the bundle path inlined in
   engine.py:806-822. `reduced`/`valid_mask` were "lifted verbatim" out
   of statpass.py into genesis.py and both copies live on. k13's
   `FloraSim.derive` mirrors `_view_from_record` exactly, kept in sync
   by a comment. Every one of these has already drifted.
2. **Filters compensating for other mechanisms.** The recurring pattern
   behind the owner's "layers of mechanisms for ad-hoc goals" critique:
   `_cap_seed_demand` (post-hoc squeeze because founder N is set
   per-lineage in isolation and stacking is repaired afterwards);
   orphan hysteresis + sliver floor (anti-oscillation patches
   compensating for the join-always founding rule — the docstring
   admits ~63% of bridge splits were same-round oscillation);
   CONSOL_EVERY (instance-count backstop, measured 251→1341 without
   it); colonization memory (retry-damping on the establishment gate);
   the tiered coverage ramp + proximity blobs + fat/strip machinery
   (targeted rescues of named species — mangrove, kelp, willow);
   the B6 relief stack (four flat-weight reliefs on two factors, three
   of them acting on the SAME saturated-end cost, individually
   unidentifiable); `merge_d_threshold` (a twice-recalibrated curve fit
   to seed-1 drift statistics).
3. **Systemic spec-code drift.** The spec's normative text lags the
   code by 2–3 tickets everywhere: tickets 0033 (proximity/fat-strip)
   and 0037 (tiered coverage, seed-demand cap) are absent from §10/§13;
   the v0.5 `establish` path is spec-sanctioned but the engine never
   calls it; §6 says D is U-weighted but the code accumulates plain
   N·percap; docstrings narrate tickets as "pending" that landed long
   ago. Conclusion for the rewrite: the spec cannot be trusted as a
   description of behavior — behavior lives in the code; the rewrite
   spec must be written from this census, and going forward specs carry
   the big picture only (owner note).

### Consolidated vestigial/filter inventory

| Module | Mechanism | Kind | Evidence |
|---|---|---|---|
| engine | `_f_magnitude` :1236 | dead code | zero callers (orchestrator-verified) |
| engine | `_divide_g` :1962 | write-only diagnostic | no reader (orchestrator-verified) |
| engine | `_descent_stats` :681 | write-only | no reader |
| engine | CONSOL_EVERY sweep :1894-1917 | filter-to-hit-target | instance-count backstop; already an experiment knob |
| engine | colonization memory :1328 | retry-damping filter | only down-weights re-attempt probability |
| engine | orphan hysteresis + sliver floor :1726-1740 | anti-oscillation patch | compensates join-always founding |
| engine | `_cap_seed_demand` :849 | post-hoc budget patch | founder formula unchanged, stacking repaired after |
| genesis | `_reduced_bundle` :746 | dead code | never called |
| genesis | preset path (`_rain_for_view`/`genesis_preset`/`genesis_rain`) | tests-only parallel pipeline | diverged: missing K_EPS + K_L gates |
| genesis | `coverage_keep`/`_covered_tiered` :620,637 | rescue filter | absent from spec; fixes one measured 78-cell mangrove defect |
| genesis | PART_MIN_CELLS=20 | dead knob | never binds in the live call graph |
| dispersal | `establish` + RAIN_HALF/EST_N0 :499 | spec-sanctioned dead path | engine drives `packet_probability` instead |
| authority | divergence-round/grace apparatus :550,1058-1064 | tautology filter | MERGE_GRACE=0 → gate always true; residue of retired v0.7 grace |
| authority | `seed_clusters` :609 | unwired machinery | spec itself says "design-only today"; engine does not call it |
| authority | SPECIATION_D / MERGE_D g-less fallbacks | tests-only parallel currency | engine always passes g |
| authority | `g_classify` import :171 | dead import | rank decisions inline the threshold instead |
| stress_adapter | B6 relief stack in `_ground_terms` :916-935 | accretion site | 4 reliefs on 2 factors; fitted to restore collapsed preset ranges |
| stress_adapter | `verdict_at` :1115 | dead production path | only one test calls it; engine inlines compose |
| stress_adapter | `annual_stress`/`worst_stress` :1134-1145 | demo-only | engine re-implements the reduction |
| stress_adapter | unconditional `_bloom_frost`/`_glacier` emission | waste | 12 MB no-op planes per evaluation |
| population | `cell_demand` :51 | dead API | engine accumulates D inline; encodes abandoned N_stack architecture |
| demand+postpass | the whole tree-fill machinery | unwired | zero production callers; consumer ticket 0027 deferred to rewrite |
| persist | `delivery.npz` | unread artifact | no reader repo-wide |
| persist | `TOOLTIP_LINEAGE_MAX`/`RAMP_TERRESTRIAL` | dead constants | — |
| __main__ | `dist_to_ocean` :137 | fossil plumbing | computed, threaded through 5 checks, used by none |

### Provenance gaps (owner note item 6 — what the artifact CANNOT answer)

- Reflog entries carry **no round stamps** and no g/threshold context —
  the persisted log cannot explain WHEN or WHY a divide/merge/extinct
  happened (authority is explicitly round-agnostic; `update()`'s round
  counter escapes only into tie-breaks and the dead grace table).
- `_divide_g` is transient engine state, never persisted.
- Not persisted at all: capacity K(c), stress fields, per-instance
  caches, rain/div/orphan arrays, seed-bank/WIP-cluster state,
  per-round commit counters (console-only). A run cannot be resumed or
  reconstructed mid-history; `rounds/rNNNN.json` (opt-in) is the only
  round stamp anywhere.
- Species binomials are NULL in the k15-amended tree — nomenclature
  never runs there (spec §9 lists name pinning as in-build; code defers
  it "out of scope for v1"; unsettled spec-vs-code).

### Confirmed correctness finds for the rewrite (and 0038)

1. **Box-axis mismatch** (orchestrator-verified, ticket 0040):
   `Dressed.box` y-first vs artifact_query x-first decode. Spatial
   answers of the 0038 tool are wrong; scalar counts are unaffected.
   Rewrite: pin the ordering IN the schema field name.
2. **§6 U-weighted D contradiction**: spec and docstrings say demand is
   U-weighted; the code accumulates plain N·percap. Unverified which is
   intended — decide at spec time, don't inherit by accident.
3. **`pressure:light` name collision** (req_flora.py:53,73): adapter
   photic term and engine canopy shade share one provenance string.
4. **`drought_deciduous` dead in the adapter**: B5 §4.1 promises it,
   no stratum reads it.
5. **b6 axis-table coupling**: addendum edits to axes_core.toml
   silently shift commit geometry via AXIS_METRIC at import time —
   make this coupling explicit in the rewrite.

---

## Per-module reports (agent-written, lightly edited)

### engine.py — the round-loop orchestrator

`Engine.round(t)` at `exp/k15_simdiff/engine.py:1996` — exact sequence per round:

1. `_canopy_light_factors()` (`:1049`) — computed ONCE at round entry, shared by steps 2–3
2. `_verdict_feed(t, light)` (`:1135`) — §5.2 aggregate → select → g accrual → per-generation mutate → `_refresh`
3. `_population(light)` (`:1259`) → returns `s_real` per-instance windows; retires zero-mass instances
4. `_dispersal(t, s_real)` (`:1322`) — emission, packets, founding; mints foundlings
5. `_dressing(t)` (`:1639`) — div deferred split, then rain-bridge split w/ hysteresis
6. `_commit(t)` (`:1869`) → `ChangeLog`

`Engine.run(rounds)` (`:2008`) calls `genesis()` (`:604`) if no instances. Genesis order: rain (delegated `gen.genesis_rain_species`, `:666`) → `_pregenesis_descent` (`:680`) → species mint loop (`:684–718`) → adapted-fragment dress (`:724–730`) → `_seed_bundles` (`:736`) → `_cap_seed_demand` (`:741`) → `authority.register_unseeded` (`:744`).

**State threading:** everything per-instance lives in `Dressed` (`:176`): `N`, `rain`, `div`, `orphan` (all bbox-windowed via `box`), `cache: CachedFields` (`:158`), `view`, `percap`, `vital`, `x: Instance`. Engine-level: `K`, `wind_u/v`, `wspd`, `downstream`, `cur_u/v` (§5.0), g bookkeeping (`_g_since_split`, `_rate_mult`, `_g_star`, `_last_contact`), `_colon_mem`, `_birth_g`, `bundle_sids`, `retired`. `light` dict and `s_real` dict are round-transient handoffs (light: step 1→2,3; s_real: 3→4).

---

## 1. Inventory + verdicts

### Data structures & geometry helpers
| Mechanism | Anchor | Consumes / mutates | Verdict |
|---|---|---|---|
| `CachedFields` | `:158` | reduced §5.1 stress planes (f_worst, s_env, prov, names, U) + cached traits/view | LOAD-BEARING — every stage reads the cache |
| `Dressed` + `rewindow` | `:176`, `:219` | per-instance spatial state | LOAD-BEARING |
| `_embed/_mask_box/_union_box/_dressed_box/_crop/_overlap_view` | `:232–291` | bbox window algebra | LOAD-BEARING (pure infrastructure; the bbox memory optimization) |
| `_dilate` | `:2033` | 8-neighborhood dilation | LOAD-BEARING (founding closures) |

### §5.0 world fields (module-level, init-time)
- `mean_wind` (`:297`) — consumes `ctx.wind_u/v_raw`; returns (H,W) f64 means. Called once from `__init__:419`. Draws: none. Removal breaks wind packets (`:1429`) and `mobility`. **LOAD-BEARING**. Smell: reaches into `sa._upsample` (private, `:311`).
- `downstream_pointer` (`:317`) — reuses persisted `h_flow_dir` or re-derives via K11 `priority_flood`/`flow_direction`. Feeds water packets (`:1433`). **LOAD-BEARING**.
- `mean_currents` (`:344`) — marine water-walk currents (`:1435`). Falls back to `sa._currents_payload` private loader (`:352`). **LOAD-BEARING** (marine only); drift flag below.
- `mobility(view, wspd, cells)` (`:360`) — sustained-channel mobility scalar; jump excluded. Called only at `:1560` and `:1682` for the DIFF threshold `TH = DIFF_D·(1 + MOB_K·mob)`. Mutates nothing. **TUNING** — shapes the divergence gate threshold; structurally the gate works with MOB_K=0, but it is spec'd (rule B+ §7.3) and stat-pass-calibrated, so removal changes speciation behavior materially.

### Engine init & ids
- `Engine.__init__` (`:390`) — loads pack, ctx, tree, authority, K, §5.0 fields; precomputes `_ornament_frac` (`:462`), `_scalar_axes` (`:467`), `_steady_axes`/`_immutable_axes` (`:474–477`). Experiment knobs `consol_every`/`merge_grace` (`:401–404`). **LOAD-BEARING**.
- `_new_instance_id` (`:503`) — iid from stream + monotone counter. Draws: caller's stream. **LOAD-BEARING** (determinism).
- `_stream` (`:507`) — `Stream(seed, "k15.<stage>", key)`. **LOAD-BEARING**.
- `_seed_lineage`/`_lineage` (`:510`, `:521`) — per-sid rate_mult + g* draws, stream `k15.g` key=sid, content-addressed. **LOAD-BEARING** (g currency).
- `_isolation` (`:529`) — rounds since `_last_contact`, ramped `/ISO_RAMP_ROUNDS`; 0 for single-instance lineages. Draw-free. Feeds Δg at `:1184`. **LOAD-BEARING** (allopatric tempo, ticket 0010).

### §5.1 cache
- `_cache_from_factors` (`:549`), `_cache_from_bundle` (`:571`), `_evaluate_cache` (`:588`) — build the reduced cache; callers: genesis mint (`:708`), bundles (`:835`), descent (`:1017`), `_refresh`. **LOAD-BEARING**; the factors/bundle split is a one-evaluate-per-species performance idiom.
- `_refresh` (`:592`) — re-derive view/vital/percap; re-evaluate cache only if `genes_distance ≥ RE_EVAL_D` (`:599`). Called only from the verdict feed tail (`:1234`). **LOAD-BEARING**; the RE_EVAL_D gate itself is **TUNING** (performance/memoization threshold).

### Genesis (§10)
- `genesis()` (`:604`) — orchestrates; mints via `authority.mint` (`:703`) on stream `k15.genesis` key `mint:{sid}` (`:690`); shares one view/cache per species by reference (`:704–710`). **LOAD-BEARING**.
- `_seed_bundles()` (`:755`) — frozen generic niche-dwellers, sid `bundle.<label>`, minted OUTSIDE the authority (`Instance(...)` direct, `:830`); stream `Stream(seed,"k15.genesis",sid)` (`:819`). Participates only via population/dispersal/stress. **LOAD-BEARING for world composition but structurally self-contained** — spec v1.8 mechanism; removal changes only competitive density, nothing in tree/commit machinery reads bundles (they are actively excluded everywhere: `:1142`, `:1785`, `:1874–1884`).
- `_cap_seed_demand()` (`:849`) — ticket 0037 per-cell ΣD ≤ K·GENESIS_S proportional squeeze, floor-clamped, exempts `_birth_g` fragments (`:887`,`:897`). Draw-free. **TUNING — vestigial-suspect-adjacent**: a post-hoc budget patch layered on top of the unchanged founder formula (its own docstring: "Raw founder demand … computed as before; NEW: … scale ALL of them down"). It exists because per-species rain can't see cross-lineage stacking; the rewrite should fold it into the founder formula, not keep a second pass.
- `_pregenesis_descent()` (`:907`) — §10.1 adapted fringe: `desc.species_adapts`/`blob_breaks_off` rolls on `k15.descent`, speckle floor `DESCENT_MIN_BLOB_CELLS//2` (`:1001`), `desc.descend` mutate loop (`:1012`), ONE evaluate per fragment (`:1017`), mints at earned `g_end` into `_g_since_split`/`_birth_g` (`:1040–1041`), carves parent clones in place (`:1027–1031`). Mutates `rain` CloneSeeds; returns adapted seeds + stats. **LOAD-BEARING per spec §10.1** (P_ADAPT=0 makes it a no-op, so it's also a gated mechanism). The speckle floor is an anti-speckle patch (ticket 0009) — **TUNING** filter inside a load-bearing mechanism.

### Round step 0 — canopy light (B6 §3)
- `_canopy_light_factors()` (`:1049`) — descending-height sweep; per land reader `f_light` windows (`out[iid]`); sorted-iid float accumulation pinned (`:1115`). Consumes all instances' N/cd/height; returns dict read by feed (`:1161`) and population (`:1285`,`:1306`). **LOAD-BEARING** (shade changes both selection and demography). Height-sweep rewrite (ticket 0022) is perf, not mechanism.

### Round step 1 — verdict feed
- `_verdict_feed(t, light)` (`:1135`) — per sorted iid, skipping bundles (`:1142`) and zero-mass (`:1148`): N-weighted provenance aggregation (`:1151–1154`) + `f_light` into `agg[REQ_LIGHT]` (`:1163`) → `compose` → `sim.select` (`:1166`); n_gen from `gen_time=2√height` capped at N_GEN_CAP (`:1168–1170`); **Δg accrual** (`:1187–1193`); f(g) ramp: `step_scale`, leaky steady gate (`:1206`), novelty tail p_round (`:1208`) rolled on stream `k15.g` key `novel:{t}:{iid}` (`:1211`); per-generation pressure re-application + `sim.mutate` on stream `k15.mutate` key `{t}:{iid}:{gen}` (`:1232–1233`); `_refresh` (`:1234`). Mutates: `x.traits`, `x.pressure`, `_g_since_split`, view/cache. **LOAD-BEARING — the evolutionary core.**
- `_f_magnitude(name, g)` (`:1236`) — docstring: "single-source formulation for tests". Grep: **zero callers anywhere in repo** (the feed inlines the math at `:1224–1229`). **VESTIGIAL — dead code.**

### Round step 2 — population
- `_population(light)` (`:1259`) — world demand grid D (`:1278–1280`), per instance: `s_env_eff` with f_light fold (`:1287–1289`), delegated `pop.update_instance` (`:1291`), rewindow, builds `s_real` (+ `pop.density_stress`, `:1311–1314`), retires dead iids (`:1315–1317`). **LOAD-BEARING**. Delegates all math to `population.py`.

### Round step 3 — dispersal
- `_dispersal(t, s_real)` (`:1322`) — sub-stages in order:
  - rain decay via `dsp.decay_rain` (`:1325`)
  - **colonization memory purge** (`:1328–1332`) — drops entries older than `dsp.MEM_ROUNDS`. Written in `_scatter_packet` (`:1624`,`:1630`); read via `in_mem` flag (`:1619`) which only down-weights packet probability. Tests read `_colon_mem` (`test_engine.py:449,460`). **TUNING / VESTIGIAL-SUSPECT** — a retry-damping filter layered on the establishment gate; spec'd (§7.3 v0.6) but it's exactly the "filter to shape behavior" archetype; removal changes only re-attempt rates.
  - owner int-grids per lineage (`:1339–1348`) — infrastructure, perf-rewritten (ticket 0022).
  - emission gate `E = dsp.emission(n_occ, view, mean_s)` (`:1370`) — stress-gated; **LOAD-BEARING**.
  - jump channel (`:1389–1409`): `dsp.maybe_jump`, failure redistributes share to local; streams `jump`, `jump_source`.
  - sustained channel packet loop (`:1413–1449`): `dsp.packet_count`, one frontier origin draw per packet, channel shapes delegated (`packet_local_blob/wind_ray/water_walk/animal_disk`); stream `k15.disperse` key `{t}:{iid}`, child `pk:{ch}`.
  - `_scatter_packet` (`:1578`) — absorption into `deposits` (§3 occupancy invariant, `:1604–1614`), ONE establishment decision per packet (`dsp.packet_probability`, draw `establish` child at index pk_n, `:1622`), EST_F_MIN vanguard filter (`:1626–1627`), colon-mem writes on failure, `n_new` founding. **LOAD-BEARING**.
  - arrival + founding (`:1456–1566`), three rules: (1) contiguous spill join unconditional (`:1487–1495`); (2) jump landings mint fragments with closure-through-founded (`:1505–1541`), stream `k15.found`; (3) sustained remote landings join, verdict gate tags `div` when `gap > DIFF_D·(1+MOB_K·mobility)` (`:1552–1566`). Foundlings dressed at `:1567–1576` inheriting founder cache. **LOAD-BEARING** (rule B+ founding is the speciation supply line); the mobility-scaled threshold is **TUNING** within it.
  - `_founded_new` (`:1359`,`:1479`) — transient diagnostic read by tests/stat harness (`test_engine.py:397`). **Diagnostics** — removable without simulation change.

### Round step 4 — dressing
- `_dressing(t)` (`:1639`) — per sorted iid:
  - div deferred split (`:1673–1715`): div ∩ cells, reference = non-div mass-weighted s_env, same gap/TH gate, `DIFF_MIN_CELLS` floor, mints via stream `k15.divsplit`. **LOAD-BEARING** mechanism containing a **TUNING** floor.
  - rain-bridge connectivity split (`:1716–1763`): components over `cells | rain>0`; rain-only sinks never split (`:1724`); **sliver floor** pre-tags orphan (`:1726–1732`); **orphan hysteresis** — mints only if ≥half the fragment was already tagged (`:1734–1740`); splits via stream `k15.split`. Bridge mechanism **LOAD-BEARING**; sliver floor + hysteresis are **TUNING / VESTIGIAL-SUSPECT** — the docstring itself admits they exist to absorb measured oscillation ("~63% of bridge splits were same-round … oscillating join/split"), i.e. filters compensating for the join-always rule three steps earlier.
  - `_last_contact[nid] = t` for all minted fragments (`:1532`,`:1696`,`:1747`) — feeds `_isolation`. **LOAD-BEARING** bookkeeping.

### Round step 5 — commit
- `_merge_thresholds()` (`:1769`) — per-lineage merge gate via `auth.merge_d_threshold(rate_mult, n_gen)`; rep = max-mass, tie lowest iid. **LOAD-BEARING** (ticket 0028/0030 gate); threshold values are calibrated (**TUNING** constants, structurally required).
- `_merge_candidates()` (`:1801`) — vectorized touch (4 forward shifts) + overlap star-topology pass (`:1849–1866`). Feeds commit AND `_last_contact` (`:1890–1893`) → isolation → Δg. **LOAD-BEARING**.
- `_commit(t)` (`:1869`) — bundle exclusion (`:1874–1884`); **CONSOL_EVERY periodic complete-pair sweep** (`:1894–1917`): every same-lineage pair a candidate every `consol_every` rounds. Docstring: "the instance-count backstop … without it the seed-1 r16 count is 1341 vs 251 with it". **VESTIGIAL-SUSPECT / TUNING** — an explicit population-control filter compensating for the merge machinery's throughput; ticket 0028 already re-scoped it to an experiment knob (`consol_every` ctor arg). The authority still applies threshold+grace, so it's safe to remove structurally; it's kept to hit an instance-count target.
- `authority.update(...)` call (`:1921–1926`) — passes views, g maps, thresholds, grace, one-shot `birth_g`; `_birth_g.clear()` (`:1932`). **LOAD-BEARING**.
- merge re-sync (`:1937–1950`) — N/rain/div/orphan transfer to survivor. **LOAD-BEARING**.
- re-key (`:1951–1966`) — sid switch, g clock reset, `_divide_g[iid]` recorded (`:1962`). `_divide_g`: grep finds **no reader in the repo** (docstring claims "the measurement harness reads it" — no such reader exists in repo; possibly scratch scripts). **VESTIGIAL-SUSPECT** diagnostic.
- drift-retention re-mint (`:1976–1991`) — `authority.redraw`, WIP genes kept (owner ruling "keep WIP"). **LOAD-BEARING** (without it, sub-SUB_D divergence is wiped each round — measured).

### Digest
- `state_json()` (`:2015`) — acceptance digest, read by `persist.py:280`, `test_engine.py`, `tools/artifact_query.py`. **Diagnostics/acceptance** — not simulation.

---

## 2. Determinism stream census

| Stream key | Site |
|---|---|
| `k15.g` : `{sid}`, `novel:{t}:{iid}` | `:517`, `:1211` |
| `k15.genesis` : `mint:{sid}`, bundle sid | `:690`, `:819` |
| `k15.descent` (via desc module) | `:963` |
| `k15.disperse` : `{t}:{iid}` (+`jump`/`jump_source`/`pk:{ch}`/`establish`) | `:1374`, `:1622` |
| `k15.found` / `k15.divsplit` / `k15.split` : `{t}:{iid}` | `:1523`, `:1692`, `:1743` |
| `k15.mutate` : `{t}:{iid}:{gen}` | `:1233` |
| `k15.commit` : `{t}` | `:1880` |

All instance iteration sorted by iid; float accumulations pinned sorted. `time.perf_counter` used only for progress prints (`:652–660`) — no draws.

## 3. Spec drift flags (flag only)

- `mean_currents` (`:352`) still calls `sa._currents_payload` (private) — spec §5.0 says "the adapter's private loader is **promoted to a shared helper**". Never promoted. Same private reach at `sa._upsample` (`:311`) and `sa.K11_OUT` (`:352`).
- Genesis docstring (`:633–642`) narrates ticket-0039 re-measurement as "pending" and retains the 22/123 unseeded breakdown prose; spec v1.9 declares prose naming the mint floor stale. Code matches v1.9 (no floor); docs lag.
- `_canopy_light_factors` shade accumulation includes water-medium instances as *casters* (`:1077–1082`) while readers exclude them (`:1105`); b6 §3 prose says "per LAND instance" without addressing casters — ambiguous, verify in rewrite.
- `_cap_seed_demand`'s exemption of `_birth_g` fragments (`:887`) is documented in code as a "documented exemption" but I found no matching sentence in spec §10.1 — verify.
- No other order/gate contradictions found: round order, §5.2 aggregation, §8 hysteresis/sliver floor, §9 contact-gate/consol split, §13 knob values all match spec v1.9 text I read (§4, §5, §8, §9, §13).

---

## Summary (5 lines)

1. Three most load-bearing: the **verdict feed** (`:1135` — g clock, f(g) ramp, per-generation mutation), the **dispersal packet/founding machinery** (`:1322`+`:1578` — emission, establishment gate, rule-B+ founding/minting), and the **commit bridge** (`:1869`+`:1801` — contact gate, per-lineage merge thresholds, drift-retention re-mint).
2. Population update (`:1259`) and dressing splits (`:1639`) are the next tier — core but heavily delegated/filtered.
3. Dead/outright vestigial: `_f_magnitude` (`:1236`, zero callers), `_divide_g` (`:1962`, no in-repo reader), `_descent_stats` (`:681`, write-only).
4. Top "filter layered on to hit a target" suspects: **CONSOL_EVERY sweep** (`:1894–1917`, instance-count backstop, already an experiment knob), **colonization memory** (`:1328`, retry-damping filter), **orphan hysteresis + sliver floor** (`:1726–1740`, anti-oscillation patches compensating for the join-always founding rule), and **_cap_seed_demand** (`:849`, post-hoc squeeze over an unchanged founder formula).
5. Spec drift is minor: unpromoted private adapter helpers (`:311`,`:352`), stale ticket-0039 genesis prose, and the undocumented birth-g cap exemption; round order and all §13 knob values match spec v1.9.

---

### genesis.py + dispersal.py — seeding and dispersal

| mechanism | anchor | verdict |
|---|---|---|
| knob block (GENESIS_F, F0, COVER, COVER_MIN_R/MAX_R, PART_*, PROX_R, STRIP_MAX, K_L_GATE, FRESH_MASK_MIN, _CUT_REJECT_MAX) | genesis.py:107-181 | mixed (see per-mechanism) |
| `CloneSeed` dataclass (cells mask + N field) | genesis.py:184-202 | LOAD-BEARING |
| `load_capacity` | genesis.py:208 | LOAD-BEARING |
| `reduced` (worst-month §5.1) | genesis.py:230 | LOAD-BEARING |
| `valid_mask` (medium mask) | genesis.py:248 | LOAD-BEARING |
| `partition_k` | genesis.py:269 | TUNING |
| `connected_components` | genesis.py:279 | LOAD-BEARING |
| `proximity_components` | genesis.py:347 | LOAD-BEARING (tuning-knobbed, fix-born) |
| `_cut` | genesis.py:385 | LOAD-BEARING (partition internal) |
| `_partition` | genesis.py:421 | LOAD-BEARING |
| `_clone_units` (fat/strip split) | genesis.py:471 | TUNING |
| `_partition_range` | genesis.py:505 | LOAD-BEARING |
| `lineage_capacity` (re-export of pop) | genesis.py:566 | LOAD-BEARING |
| `demand_field` | genesis.py:574 | LOAD-BEARING |
| `_n_field` | genesis.py:586 | LOAD-BEARING |
| `_covered_components` (base keep/drop) | genesis.py:597 | LOAD-BEARING |
| `coverage_keep` (tiered ramp) | genesis.py:620 | VESTIGIAL-SUSPECT |
| `_covered_tiered` | genesis.py:637 | VESTIGIAL-SUSPECT |
| `_rain_for_view` (shared core, preset path) | genesis.py:660 | VESTIGIAL-SUSPECT (tests-only, diverged) |
| `genesis_preset` | genesis.py:710 | VESTIGIAL-SUSPECT (tests-only) |
| `genesis_rain` (preset aggregate) | genesis.py:727 | VESTIGIAL-SUSPECT (tests-only) |
| `_reduced_bundle` | genesis.py:746 | VESTIGIAL (dead code) |
| `genesis_rain_species` (engine's round-0) | genesis.py:760 | LOAD-BEARING |

### Per-mechanism detail (genesis)

- **`genesis_rain_species`** genesis.py:760 — Consumes: pack, WorldContext, seed, K field, species nodes. Returns `{sid: (clones, range_cells, bundle)}`; the bundle (names/F_worst/prov/U) feeds the engine's §5.1 cache. Streams: `Stream(seed, "k15.genesis", sid)` (genesis.py:861), children `cover:{i}` (:614), `comp:{i}` (:559); `_cut` draws at `(clock=cut, index=2a/2a+1)` (:404-412). Calls: `sa.species_view`, `sa.evaluate`, `reduced`, `valid_mask`, `proximity_components`, `_covered_tiered`, `partition_k`, `_partition_range`, `_n_field`, `pop.percap_demand/lineage_capacity`. Called by engine.py:666. Blast radius: deleting it deletes the sim's entire initial state. **LOAD-BEARING.**
- **Seeding mask with two extra gates** genesis.py:841-844 — `(F_worst ≥ GENESIS_F) & valid_mask & (K_L > pop.K_EPS)`, plus toggleable `GENESIS_K_L_GATE` (`K_L ≥ N_FLOOR·percap`, :843-844). No draws. The K_L gate is spec §10.1's declared "whole freak-tail handling" — **TUNING** (one-line toggle); K_EPS gate is the §6 density guard — TUNING.
- **`demand_field` / `_n_field`** genesis.py:574, 586 — D = max(F0·K_L, N_FLOOR·percap); N = D/percap. Pure, no draws. Consumed by engine descent (engine.py:1022) and bundle seeding (engine.py:822) too. **LOAD-BEARING** — founder abundances are the sim's initial mass; the N_FLOOR clamp is a floor, not a filter.
- **`_covered_components`** genesis.py:597 — partial coverage keep/drop per blob from `rng.child("cover:{i}")`, largest-blob unconditional retry (:615-616). Spec §10 step 4, ticket 0020 design pivot (leave habitat for §7 colonization). **LOAD-BEARING** (changes initial occupancy ~50%).
- **`coverage_keep` / `_covered_tiered`** genesis.py:620, 637 — tiered ramp on top of the base draw: R<200 no draw, 200-400 ramp 1.0→0.5, >400 flat. Consumes blob sizes only. Called by both rain paths and engine bundle seeding (engine.py:820). **VESTIGIAL-SUSPECT** — layered on to fix one measured defect (a 78-cell mangrove losing its larger blob, comment :132-133); it is NOT in the spec (§10 step 4 still says flat GENESIS_COVER; §13 knob table lacks MIN_R/MAX_R; no changelog entry for ticket 0037). Structurally removable: delete → every species draws at flat 0.5.
- **`partition_k` / `_partition` / `_partition_range` / `_cut` / `_clone_units`** genesis.py:269, 421, 505, 385, 471 — headstart speciation: K = clip(1+⌊log2(range/200)⌋,1,8) clones over clone units; fat 8-components ≥32 split by recursive rng axis cuts (`comp:{i}` streams), strips (sub-32, proximity-regrouped) stay one possibly-disconnected clone each. **LOAD-BEARING** (clone geometry = round-0 sibling lineages, the speciation substrate); `_clone_units`' fat/strip boundary (GENESIS_STRIP_MAX=32, :164) and GENESIS_PROX_R=2 (:155) are **TUNING** knobs born from the ticket-0033 strip-habitat fix. Note: PART_MIN_CELLS=20 (:144) is effectively dead in the live call graph — `_partition` is only reached on single fat components ≥32, so its initial-component floor never binds (only direct test calls exercise it).
- **`connected_components`** genesis.py:279 — row-run union-find, pinned emission order. Reused by engine founding/dressing (engine.py:1519, 1562, 1685, 1718) and descent (:975). **LOAD-BEARING.**
- **`proximity_components`** genesis.py:347 — r-dilate (reuses `dispersal._cheb_dilate`) → components → intersect back. No draws. Grouping unit for coverage draws and strips in both seeding paths + engine bundles. **LOAD-BEARING** structurally, but flag: it was layered on (ticket 0033 §1) specifically to make mangrove/kelp/willow mintable — a targeted rescue, radius 2 pure tuning.
- **`reduced` / `valid_mask`** genesis.py:230, 248 — worst-month aggregation and medium mask (freshwater floor FRESH_MASK_MIN :177). Reused by engine bundle seeding (:806, :811). **LOAD-BEARING.**
- **`load_capacity`** genesis.py:208 — reads K14 `derived.npz`, mean-pools 1024→256. Called by engine.py:415 and conftest.py:24. **LOAD-BEARING** (the K anchor all capacity derives from); artifact-loader, not a filter.
- **`_rain_for_view` / `genesis_preset` / `genesis_rain`** genesis.py:660, 710, 727 — the pre-ticket-0004 preset path. Called ONLY by test_genesis.py. Diverged from the species path: no K_EPS gate, no K_L gate (compare :689-691 vs :841-844). **VESTIGIAL-SUSPECT** — kept as "tests' partition ground truth" but it's a second, subtly different seeding pipeline the sim never runs.
- **`_reduced_bundle`** genesis.py:746 — **VESTIGIAL, dead code**: never called; `genesis_rain_species` builds the bundle inline (:848-851) and only its docstring (:822) names it.

## dispersal.py — INVENTORY

| mechanism | anchor | verdict |
|---|---|---|
| knob block (COUNT_REF…MEM_PENALTY) | dispersal.py:90-114 | mixed |
| `_disk_offsets` / `_filled_disk_offsets` + tables `_ANIMAL_DISK`/`_JUMP_DISK`/`_FILLED_*` | dispersal.py:117-142 | LOAD-BEARING (draw tables) |
| `_cheb_dilate` | dispersal.py:145 | LOAD-BEARING (also genesis's dilation source) |
| `_line_ray` / `_field_walk` | dispersal.py:162, 202 | LOAD-BEARING (rasterizers) |
| `emission` (§7.1) | dispersal.py:228 | LOAD-BEARING |
| `packet_count` | dispersal.py:248 | TUNING |
| `frontier_cells` | dispersal.py:260 | LOAD-BEARING |
| `_dedupe` | dispersal.py:272 | LOAD-BEARING (internal) |
| `packet_local_blob` / `packet_wind_ray` / `packet_water_walk` / `packet_animal_disk` / `packet_jump_disk` | dispersal.py:281, 307, 347, 407, 418 | LOAD-BEARING |
| `maybe_jump` | dispersal.py:428 | LOAD-BEARING |
| `round_probability` (§4 T-policy) | dispersal.py:456 | LOAD-BEARING |
| `packet_mean_f` / `packet_probability` (§7.3 gate) | dispersal.py:467, 483 | LOAD-BEARING |
| `establish` (v0.5 per-cell gate) | dispersal.py:499 | VESTIGIAL-SUSPECT |
| `decay_rain` (seed bank) | dispersal.py:545 | LOAD-BEARING |

### Per-mechanism detail (dispersal)

All dispersal functions are pure; the only draws are through the caller-supplied per-`(round, instance)` stream (`Stream(seed, "k15.disperse", f"{t}:{iid}")`, built at engine.py:1374). Draw addresses: `maybe_jump` — bernoulli (0,0), disk index (0,1) (dispersal.py:448-450); `establish` — per-candidate bernoulli (0,k) (:539); the packet-gate `u` is drawn engine-side from `rng.child("establish")` at (0, pk_n) (engine.py:1622); origin/animal draws engine-side from `pk:{ch}` children (engine.py:1396, 1422, 1440).

- **`emission`** dispersal.py:228 — E from n_occ, propagule_count, mean_s_real (stress gate `max(s,0)`). Called engine.py:1370. Everything downstream scales by E. **LOAD-BEARING.**
- **`packet_count`** dispersal.py:248 — clip(2+⌊log2(n_occ/32)⌋,1,8). Called engine.py:1415. **TUNING** — shapes granularity only.
- **`frontier_cells`** dispersal.py:260 — occupied cells with an unoccupied 8-neighbor; packet origins. Called engine.py:1379. Also the basis of the ticket-0039 floor-removal rationale. **LOAD-BEARING.**
- **five packet shapes** — local spill (radius 1/2 by LOCAL_BIG :290), wind tapered ray (length from origin wind vector / √propagule_mass, cap 40, :331-343), water walk (D8 pointer or current field, cap 40, :362-404), animal filled disk r=5, jump filled disk r=3. Each called from engine.py:1424-1444 (jump at :1403). **LOAD-BEARING** — they ARE v0.6 dispersal ("tentacles, not dots"). Knobs WIND_K/WIND_MAX_CELLS/LOCAL_BIG/radii are TUNING.
- **`maybe_jump`** dispersal.py:428 — P = 1−(1−jump_rate·JUMP_SCALE)^T roll + uniform offset from `_JUMP_DISK`. Called engine.py:1390; failure folds share into local (engine-side, :1392-1394). **LOAD-BEARING.**
- **`packet_mean_f` / `packet_probability`** dispersal.py:467, 483 — mean(f_hab^β) sorted-order sum; gate P=0 below EST_F_MIN; §4 T-conversion; ×MEM_PENALTY on memory hit. Called engine.py:1618-1621. **LOAD-BEARING** — the single founding decision per packet.
- **`round_probability`** dispersal.py:456 — 1−(1−p)^T. Used by packet_probability and establish. **LOAD-BEARING** (the §4 policy primitive).
- **`decay_rain`** dispersal.py:545 — persistent seed_bank ×SEEDBANK_KEEP else zero. Called engine.py:1325. **LOAD-BEARING** (only cross-round rain state).
- **`establish`** dispersal.py:499 — the v0.5 per-cell gate (rain_frac = d/(d+RAIN_HALF), p_yr = rate·f·rain_frac, EST_N0 founders). **Never called by the engine** (engine drives packet_probability); only test_dispersal.py:460-509 exercises it. **VESTIGIAL-SUSPECT** — retained verbatim "as the defining kernel of the vanguard accounting" per spec §7.3 (spec line 464-465), so spec-sanctioned dead weight; RAIN_HALF (:104) and EST_N0 (:106) exist only for it. Note the v0.5 and v0.6 forms disagree structurally: v0.5 modulates p by rain_frac; the packet path ignores rain magnitude in P entirely (rain only sets founded N).
- **`WATER_LAMBDA`** dispersal.py:96 — v0.6 demoted to "mobility-gate reach term only", read once at engine.py:376. **TUNING**; a v0.5 decay remnant kept alive by one consumer.

## CALL SHAPE (one-liners)

- engine `_genesis` → `gen.genesis_rain_species` (engine.py:666); `_seed_bundles` → gen primitives inline (engine.py:806-822, a third copy of the pipeline); `_pregenesis_descent` → `gen.connected_components`, `gen._n_field`, `gen.lineage_capacity`, `gen.valid_mask` (engine.py:971-1022).
- engine `_dispersal` → `dsp.decay_rain` → `dsp.emission` → `dsp.frontier_cells` → `dsp.maybe_jump`/`dsp.packet_*` shapes → `_scatter_packet` → `dsp.packet_mean_f`/`dsp.packet_probability` (engine.py:1322-1449, 1618-1635); colonization memory and founding (rule B+) live engine-side, not in dispersal.py.
- tests only → `genesis_preset`/`genesis_rain`/`_rain_for_view`/`partition_k` direct, `dsp.establish`.

## REMOVAL BLAST RADIUS (highlights)

- Delete `genesis_rain_species` or `reduced`/`valid_mask`/`demand_field` → no round-0 world; descent + bundle seeding also break (they reuse the same primitives). Sim cannot start.
- Delete `_covered_tiered` ramp → two call sites (genesis.py:696, engine.py:820) revert to flat 0.5 draws; byte-level output changes but structure intact.
- Delete `establish` (+RAIN_HALF/EST_N0) → engine unaffected; ~6 tests in test_dispersal.py:446-509 break. Zero sim-output impact.
- Delete `_rain_for_view`/`genesis_preset`/`genesis_rain`/`_reduced_bundle` → engine unaffected; test_genesis.py breaks. Zero sim-output impact.
- Delete `proximity_components` → genesis blob stage, strips, and engine bundle seeding all break; but replacing it with plain `connected_components` is a one-line-per-site change (it was exactly that before ticket 0033).

## SPEC DRIFT (flag only)

1. **Mint floor removal is clean in code.** No `GENESIS_MIN_CELLS` logic remains — only a historical comment (genesis.py:145-146) and a test comment (test_genesis.py:625). `_clone_units` drops nothing (:486-491 comment matches behavior: sub-32 residual → strips, never dropped). `_rain_for_view` (:692-696) and `genesis_rain_species` (:857-859) mint every proximity blob. Matches spec v1.9 §10 step 3 (line 776-780). ✓
2. **Ticket 0037 tiered coverage is absent from the spec.** Code: `coverage_keep`/`GENESIS_COVER_MIN_R/MAX_R` (genesis.py:127-141, 620-654). Spec §10 step 4 (line 781-793) still specifies flat GENESIS_COVER=0.5; §13 knob table (line 1071) lacks the ramp knobs; §15 changelog has no 0037 entry. Also stale "(≥ floor)" wording in §10 step 4 line 781 — acknowledged stale by the v1.9 header (line 5-6).
3. **Ticket 0033 §1 (proximity blobs, fat/strip) is absent from the spec's normative §10.** Spec step 5 (lines 794-804) still describes the pre-0033 partition (components ≥ PART_MIN_CELLS split, PART_MIN_CELLS=20 in knob table line 1077); code splits at GENESIS_STRIP_MAX=32 (genesis.py:164, 496) and strips never split. GENESIS_PROX_R / GENESIS_STRIP_MAX are not in the §13 knob table. Spec header line 36 says 0033 was merely "queued".
4. **Module-header doc drift**: genesis.py:57-66 claims both entry points "share one seed+partition core (`_rain_for_view`)" — `genesis_rain_species` does NOT call it; it inlines a divergent copy with two extra gates (:841-844). Three copies of the seeding pipeline exist (genesis.py:660, genesis.py:829-873, engine.py:806-822).
5. **Dead code**: `_reduced_bundle` (genesis.py:746) never called; PART_MIN_CELLS never binds in the live call graph.
6. **`establish` retention is spec-sanctioned** (spec line 462-465), so not drift — but its EST_N0/RAIN_HALF knobs (§13 line 1066-1067, marked "v0.5 gate form") describe a path the engine never executes.
7. B6 addendum notes river flow-stress as "designed-pending (not built — the water packet…)" (biosphere-addendum-b6-flora-wiring.md:165) — a known gap adjacent to the water packet, not contradicted by code.

## Summary (5 lines)

- Most load-bearing: (1) `genesis_rain_species` + its mask/demand core (`reduced`, `valid_mask`, `demand_field`/`_n_field`) — the entire initial world state; (2) `connected_components`/`proximity_components`/`_partition_range` — instance geometry at mint AND the engine's founding/dressing primitive; (3) the dispersal packet pipeline (`emission` → `frontier_cells` → five shapes → `packet_mean_f`/`packet_probability`) — the only range-expansion mechanism.
- Top vestigial suspects: (1) `establish` + RAIN_HALF/EST_N0 — the v0.5 per-cell gate, engine never calls it, spec-sanctioned dead weight; (2) the whole preset path (`_rain_for_view`/`genesis_preset`/`genesis_rain`) — tests-only, silently diverged from the species path (missing K_EPS + K_L gates); (3) `_reduced_bundle` — literally dead.
- Strong "filter layered to hit a target" candidates for the rewrite to scrutinize: the ticket-0037 tiered coverage ramp (`coverage_keep`, undocumented in spec) and the ticket-0033 proximity-blob/fat-strip machinery (GENESIS_PROX_R=2, GENESIS_STRIP_MAX=32) — both targeted rescues of named species (mangrove/kelp), both absent from the spec's normative text.
- Structurally load-bearing but knob-heavy (TUNING): GENESIS_F/GENESIS_F0/GENESIS_COVER, partition_k constants, packet_count, GENESIS_K_L_GATE, MEM_PENALTY/MEM_ROUNDS.
- Determinism hygiene is good throughout: all genesis draws content-addressed under `k15.genesis` (`cover:{i}`, `comp:{i}`, cut clock/index); dispersal constructs no streams and pins every (clock, index).

---

### authority.py — taxonomy, speciation, commit

**Module knobs** (all `authority.py`):
- `SUB_D=0.08` (:177), `SPECIATION_D=0.35` (:189), `MERGE_D=0.045` (:194), `MERGE_D_BASE=0.012` (:201), `MERGE_D_RATE_REF=28.0` (:228), `MERGE_D_EXP=1.0` (:231), `MERGE_D_CAP=0.05` (:235), `MERGE_GRACE=0` (:243), `CLUSTER_PERSIST_ROUNDS=3` (:277), `CLUSTER_MIN_SIZE=2` (:280), `GENERIC_SALIENCE=0.4` (:281), `DEFAULT_SALIENCE=0.2` (:282), `_NON_GENE_KEYS` (:286)

**Metric layer**:
- `AxisMetric` dataclass (:292), `_ClusterState` dataclass (:307)
- `_load_axis_metric` / `AXIS_METRIC` (:338–363) — import-time TOML table build
- `_term` (:366), `genes_distance` (:386), `_group_distances` (:417–502, vectorized O(n²))

**`TreeAuthority`** (:508):
- `__init__` (:522) incl. `_merge_metric` scalar-only subset (:531–533)
- `mint` (:558), `redraw` (:579), `register_unseeded` (:597), `seed_clusters` (:609)
- `update` (:637–751) — commit orchestration + extinction pass (:739–745)
- `_process_group` (:755–1108), internal stages:
  - S0 earned-g first-commit rank (`birth_g`, ticket 0018) (:841–882)
  - S1 cluster graph, connected components @ SUB_D (:884–917)
  - S2 orthodox pick + gerrit amend (:810–814, :919–930)
  - S3 persistence-tracked cluster divides (ticket 0010) (:952–995)
  - S4 stem g-promotion of remainder (ticket 0008) (:997–1030)
  - S5 merges (:1032–1089)
  - S6 KEEP fill (:1091) + cluster-state prune (:1099–1108)
- `_track_cluster` (:1110), `_divide` (:1139), `_amend` (:1173)

## 2–4. PER MECHANISM (consumes → mutates/returns → streams → callers → blast radius)

| Mechanism | Consumes | Mutates/Returns | RNG stream | Called by / calls | Removal blast radius |
|---|---|---|---|---|---|
| `AXIS_METRIC`+`_term`+`genes_distance` (:338–414) | axes_core.toml, two gene mappings | distance float | none | `_group_distances`, engine cache gate (`engine.py:599` RE_EVAL_D), tests | Fatal: every commit decision and the engine's re-derive gate key off it |
| `_group_distances` (:417) | group traits + record | (n,n)+(n,) matrices | none | `_process_group` (:805–808) | Perf-only wrapper around `genes_distance`; deleting = O(n²) Python loop returns, same semantics |
| `_merge_metric` (:531) | AXIS_METRIC scalars | scalar-only sub-table | none | `_process_group` (cluster graph, merge gate, birth-g gate) | Cluster geometry + merge gate revert to full metric; enum noise re-enters (the ticket-0008/0010 bug returns) |
| `merge_d_threshold` (:253) | rate_mult, n_gen | per-sid threshold | none | engine `_merge_thresholds` (`engine.py:1798`) only | Merge gate falls back to fixed `MERGE_D`; recombination dynamics change (counts, fat-blob shape) |
| `mint` (:558) | tree node | `_instance_lineage`, `_alive`; returns Instance | none (rng for protocol shape) | engine genesis (:703, :1006), tests | Genesis impossible |
| `redraw` (:579) | `_instance_lineage`, tree | returns Instance/None | none | engine re-sync (`engine.py:1977`) | Post-commit re-sync breaks |
| `register_unseeded` (:597) | sid list | `_alive` | none | engine genesis (:744) | Zero-range species stay alive-but-empty ghosts; extinction count wrong |
| `seed_clusters` (:609) | sid→clusters | `_cluster_state` (born_round=-1, full credit) | none | **tests only** — engine explicitly does NOT call it (`engine.py:678`) | Nothing in rounds; tests using the g-less fallback path break |
| `update` (:637) | views, merge_candidates, g maps, merge_d, birth_g | all commit state; returns ChangeLog | rng threaded to `_divide` only | engine `_commit` (`engine.py:1921`, stream `"commit"`, ctx `str(t)`); tests | The commit itself; everything |
| S0 birth-g rank (:841) | `birth_g`, `g_star`, `rec_merge`, thresh | `_divide` calls, deltas, `_promoted`, reflog | via `_divide` | `_process_group` | 0018 descent fragments lose first-commit rank; they fall into emergent-cluster machinery (floors would delay them 3 commits) |
| S1 cluster graph (:884) | `dist_merge`, SUB_D | adjacency, clusters | none | `_process_group` | No divide geometry at all — only stem promotion remains |
| S2 orthodox+amend (:810, :919) | `rec`, masses | record genes (gerrit), reflog "amend", orthodox KEEP delta | none | `_process_group` → `_amend` | The record stops tracking its population; the ratchet dies |
| S3 persistence divides (:952) + `_track_cluster` (:1110) | clusters, `_cluster_state`, g/gs, floors | `_cluster_state`, `_divide`, `_promoted`, deltas, `_divergence_round` | via `_divide` | `_process_group` | No real cladogenesis; tree never gains width except stem promotion; speciation counts collapse |
| S4 stem promotion (:997) | orthodox g vs g*, `_promoted` | `_divide` SPECIES node, re-key remainder, `_promoted` | via `_divide` | `_process_group` | Dense lineages' g accumulates unbounded (the mutation-magnitude ramp runs away — the exact problem it was patched in for) |
| S5 merges (:1032) | candidates, `dist_merge`, thresh, grace, `_divergence_round` | deltas MERGE, `_instance_lineage`, reflog | none | `_process_group` | Instance count explodes (measured 251→1341 at r16 without consolidation); no recombination |
| extinction pass (:739) | `_alive` vs `alive_now` | reflog "extinct", `_alive`, `_cluster_state` prune | none | `update` | Extinct lineages linger as live; reflog/state wrong |
| `_divide` (:1139) | parent node, rep traits, instance ids | tree node, `_sid_path`, reflog split/subspecies | `rng.child("k15.commit.{prefix}{parent.sid}:{iid0}")`, one `u64` | S0/S3/S4 | Tree never grows |
| `_amend` (:1173) | node, traits | node axes/generics in place | none | S2 | Record frozen at genesis values |

**Determinism streams**: the authority draws in exactly ONE place — `_divide` (:1153–1155), a child of the engine's `k15.commit` stream keyed by rank prefix + parent sid + first instance id, drawing one `u64` for the new sid. Everything else is draw-free bookkeeping (stated at :840, :1121). Note the docstring's own latent-nondeterminism repair: `_group_distances` sorts weighted_set categories where `genes_distance` iterated a Python set (:431–435).

## 5. VERDICTS

**LOAD-BEARING**
- `genes_distance`/`_group_distances`/`_term`/`AXIS_METRIC` — the distance currency; every gate reads it, plus the engine's RE_EVAL_D cache gate.
- S2 orthodox pick + gerrit `_amend` — the record ratchet; the tree's only channel for tracking population drift.
- S1+S3 cluster graph + persistence divides — the only source of tree WIDTH (real cladogenesis).
- `_divide`, `mint`/`redraw`, extinction pass, S5 merges (instance-count backstop, measured 5× blowup without it).
- S4 stem promotion — a patch (dense clouds never reach SUB_D) but now structurally load-bearing: removing it unbounds g and the mutation ramp.

**TUNING**
- `SUB_D`, `CLUSTER_PERSIST_ROUNDS`, `CLUSTER_MIN_SIZE` — churn-floor knobs; the floors are a governor bolted on after the "v0.7 disease" (hundreds of spurious splits/round). Structurally removable; numbers collapse without them.
- `merge_d_threshold` + `MERGE_D_BASE/REF/EXP/CAP` — a twice-recalibrated (0028→0030) curve fit to seed-1 drift statistics. Pure knob-shaping.
- `GENERIC_SALIENCE`/`DEFAULT_SALIENCE` — weighting guesses for unrated keys.

**VESTIGIAL-SUSPECT**
- `_divergence_round` + grace gate (:1058–1064): `MERGE_GRACE=0` and the engine passes its own `merge_grace` which defaults to 0 — `grace_v >= 0` is always true. An entire tracking table (:550, :792, :1030) maintained to service a filter that never fires. Residue of the retired v0.7 5-round grace.
- `SPECIATION_D` + the g-less fallback band (:189, :853–858, :976–981): engine always passes g; live only in unit tests. A parallel rank currency the rounds never read.
- `MERGE_D` fixed fallback (:194): same shape — only no-map callers (tests) see it.
- `seed_clusters` (:609): spec itself says "0018 design-only today" (spec §9 line 621); engine comment "NO seed_clusters" (`engine.py:678`). Shipped machinery with zero production callers; the birth-g path (S0) does the actual 0018 work.
- `g_classify` import (:171): **dead import** — rank decisions inline `b_g > star` comparisons instead of calling `classify`.
- `MERGE_GRACE` constant + `merge_grace` parameter: kept "for callers that pass none" — i.e., tests.

## 6. PROVENANCE: recorded vs NOT

Reflog records: `amend` (sid, orthodox iid, full before/after gene dicts — :924), `split`/`subspecies` (new sid, parent sid, sorted instances, full genes — :1167), `merge` (sid, absorbed iid, survivor — :880, :1087), `extinct` (sid — :741).

NOT recorded (gaps a rewrite must decide on):
- **No round stamp on any reflog entry** (explicit: "the authority is round-agnostic (reflog entries carry no round)" :119) — event ordering is positional only.
- No g values, no thresholds/grace actually applied, no cluster-persistence state, no rejected merge candidates, no KEEP decisions, no record of which instance became orthodox except implicitly in `amend`.
- `update()` bumps `self._round` (:684) but the number escapes only into `born_round` tie-breaks and the (dead) grace table.
- Engine-side `_divide_g` (`engine.py:1962`) is the transient g diagnostic — it is *not* in the persisted reflog; persisted decision record (persist.py:300) is therefore not sufficient to replay divide ranks.

## 7. SPEC DRIFT (flagged only)

- `authority.py:7` — module docstring: "the engine … `exp/k15_simdiff/engine.py` (not yet landed)". Landed long ago; stale doc.
- Spec §9 (:556) lists "final-commit name pinning (K13 nomenclature)" as **part of this build**; code defers it ("out of scope for v1", :1147–1148, :146–147) and §14's deferred list does not carry it. Spec vs code unsettled; binomials are never pinned.
- `g_classify` (:171) imported from `k13_treegen.forces` but never called — the code re-implements classify's threshold inline instead of using the spec'd forces idiom (spec §9 :593–596 cites the fauna RFC currency).
- Docstring :131 claims "the reflog already rides along with the tree JSON" for replay — persist.py writes `tree.json` and `reflog.json` as separate files (persist.py:300–302). Cosmetic drift, but the replay-restore claim is looser than reality.
- `_divergence_round`/grace machinery contradicts the spec's own v1.3 ruling ("the grace's old role … is retired", spec §9 :688–690): spec retired it, code still maintains the full tracking apparatus.
- b-addenda b1–b6: no direct contradiction of commit mechanics found (b6 is trait-wiring; its axis-table changes flow into `AXIS_METRIC` via axes_core.toml at import, silently shifting commit geometry — a coupling the rewrite should make explicit, not drift per se).

## Summary (5 lines)

1. Three most load-bearing: (a) the salience-weighted distance metric (`genes_distance`/`_group_distances`, :386/:417) — every gate and the engine's cache re-eval read it; (b) the orthodox-pick + gerrit amend ratchet (:810, :919–930) — the record's only drift channel; (c) the cluster-graph + persistence-floor divide path (:884, :952) — the sole source of tree width.
2. Stem g-promotion (:997) is a measured-defect patch now load-bearing: removal unbounds g and the mutation ramp.
3. Top vestigial suspect: the divergence-round/grace apparatus (:550, :1058–1064) — `MERGE_GRACE=0` makes the gate a tautology; pure residue of the retired v0.7 grace.
4. Second-tier suspects: `seed_clusters` (zero production callers; spec admits "design-only"), `SPECIATION_D`/`MERGE_D` g-less fallbacks (tests only), and the dead `g_classify` import (:171).
5. Biggest provenance gap for the rewrite: reflog entries carry no round stamps and no g/threshold context — persisted reflog cannot explain *why* a divide ranked as it did.

---

### stress_adapter.py + req_flora.py — the stress channel

Scope: env side of the B5/B6 stress channel. The whole module is **draw-free**: no `kernel.hashrng.Stream` is imported or used anywhere in either file — every output is a pure function of (K11/K14 dumps, record axes, constants). Determinism is structural (recompute-never-downsample + bit-for-bit verification against persisted rasters), not stream-pinned.

## 1–5. Inventory, mechanism-by-mechanism

### A. Vocabulary — `req_flora.py` (117 lines, zero code beyond constants)

- `REQ_COLD/HEAT/BLOOM_FROST` (climate, req_flora.py:23–26), `REQ_WATER/WATERLOGGING/FERTILITY/PH_LOW/PH_HIGH/SALINITY` (ground, :36–47), `REQ_ROOTING/ANCHORING/MEDIUM/SUBMERGED_LIGHT` (tails, :50–53), `REQ_FRESH_HABITAT` (:56), `REQ_GLACIER` (:63), `REQ_LIGHT` (:73), `V1_FLORA` (:75–80).
- Consumes: nothing. Mutates: nothing. Streams: none.
- Call shape: imported by `stress_adapter.py:116`, `engine.py:56` (`REQ_LIGHT`), `__init__.py:11` (re-export), tests, `__main__.py:232`. The **organism side** (`k13_treegen/flora/sim.py` `select()`) dispatches on these strings — the file is a contract, not a mechanism.
- Blast radius: deleting a name breaks `stress_adapter` emission, `engine._verdict_feed` (REQ_LIGHT), and `flora/sim.py` routing simultaneously. The docstring block at :82–117 (DerivedView key list) is the de-facto interface spec between k13 derive and k15 adapter.
- Verdict: **LOAD-BEARING** (contract). Smell: `REQ_SUBMERGED_LIGHT` and `REQ_LIGHT` are the *same string* `"pressure:light"` (req_flora.py:53 vs :73) — two mechanisms (adapter photic term vs engine canopy shade) share one provenance name, papered over by a "never co-occur" comment (:70–72).

### B. World loading — `stress_adapter.py`

**`WorldContext` (:335–390)** — pure-data holder of ~35 anchor-res (256²) fields; consumed by `evaluate` and by the engine's §5.0 world fields (`wind_u/v_raw`, `flow_dir`, `w_elev`, `ocean_mask`, `currents_u/v` cached here so the engine doesn't re-open `world.npz` — :435–444, :557–564). Verdict: **LOAD-BEARING**.

**`load_world(seed)` (:408–565)** — loads K11 dump + K14 products; re-derives at anchor: ground top-3 mix via `_ground_anchor_mix` (:393–405, re-runs the deterministic B3 pass because the mix isn't persisted), verified bit-for-bit against persisted `ground_eff_*` (:490–497, raises on drift); moisture via `_moisture.build_moisture` (:501–505); water pH pointwise (:507–526); column depth / photic / bottom temp with the fresh-vs-marine split (:528–556); wind storm proxy with bilinear upsample (:456–469).
- Callers: `engine.py:411`, `statpass.py:270`, `conftest.py:30`, genesis/tests. Calls: k14 `moisture/water/ground/derived`, `artifact_require`.
- Blast radius: everything — no ctx, no stress, no engine.
- Verdict: **LOAD-BEARING**. The re-derive-and-verify pattern is expensive but is the determinism spine.

**`_ensure_snow_glacier` (:568–582)** — lazy idempotent attach of `snow_mm`/`glacier` from the K11 dump; the B6 strata self-provision instead of depending on `load_world`. Verdict: **LOAD-BEARING** for B6 strata; structurally a bolt-on (self-provisioning idiom, :573–575 admits the ctx-builder "is shared with another line of work").

**`_currents_payload` (:585–593)** — try/except currents loader with annual-mean fallback; feeds engine §5.0, not stress. Verdict: TUNING (engine convenience cache).

### C. View construction

**`_view_from_record` (:599–657)**, **`species_view` (:660–664)**, **`preset_view` (:667–673)** — build the DerivedView from axes: `effective_climate` (k13 derive) + plan descriptors + B6 wiring keys + engine dispersal keys threaded through unused by stress (:646–655).
- Callers: genesis.py:721,835; statpass.py:144; engine via `FloraSim.derive` mirror (`k13_treegen/flora/sim.py:142–144` keeps `ANCHOR_REF_M` in sync by comment, not import — a sync-by-convention hazard).
- Blast radius: every evaluation path; also duplicated logic — `FloraSim.derive` mirrors this function exactly, so two sources of truth exist for one view.
- Verdict: **LOAD-BEARING**, but the k13/k15 mirror duplication is a rewrite target.

### D. Strata (each emits (12,H,W) factors)

**`_climate_factors` (:679–765)** — REQ_COLD/REQ_HEAT split one-sided T factors over the *derived* envelope. Stacked gates inside one factor: (i) submerged→annual bottom temp (:702–706); (ii) winter-deciduous leaf-on gating (:710–712); (iii) growing-season dormancy below `GROW_T_C` (:713–719); (iv) growing-season-length shortfall folded in (:723–729); (v) C4/CAM cold penalty, itself dormancy-gated (:731–739); (vi) B6 snow-load excess, *ungated*, folded into REQ_COLD (:741–757). Six mechanisms emit ONE provenance name — selection (`select()`) cannot tell snow burial from cold from short season.
- Blast radius: deleting any sub-term silently raises fitness of taiga/tundra/boreal lineages; the slow-gate landscape pins would move. This is the densest threshold-feeding-threshold site in scope.
- Verdict: core T-distance **LOAD-BEARING**; sub-terms (iv) growing-season and (vi) snow-load are **TUNING** (both are calibration-fitted: SNOW_TOL/SNOW_REF "calibration (2026-08-01, seed-1 landscape pass)" :274–280 — fitted to keep authored ranges alive, the classic ad-hoc signature); (v) C4/CAM penalty **TUNING**.

**`_bloom_frost` (:768–782)** — cost-only (f ≥ 1−0.5) frost in bloom window. Emitted **unconditionally** (`evaluate` :1088) even for plans with no bloom traits (returns all-ones — 12 MB of no-op float32 per evaluation). Verdict: **VESTIGIAL-SUSPECT** in effect (bounded at 50% cost of one factor, "never lethal", gated to authored bloom months) and wastefully always-on.

**`_ph_suit_split` (:785–793)** — split one-sided pH (low×high = dist_suit exactly; split exists purely so `select()` can sign its response). Verdict: **LOAD-BEARING** (provenance routing), zero effect on F.

**`_sal_tol_eff` (:796–805)** — B6 halophyte grade credit. Verdict: **TUNING** — a flat +0.15 credit; the comment (:800) admits it exists because "a pressure:salinity responder [had] no factor read" — i.e., wired to justify a responder row, not because the world model needed it.

**`_substrate_suits` (:808–864)** — per-class (3,H,W) suits for rooting/fertility/pH/salinity; includes B6 fertility credits (mycorrhizal/n_fixation, :834–841) and dual-medium pH/salinity min/max folds (:846–849, :855–856). Best-of-class max is taken by callers. Verdict: **LOAD-BEARING** (best-of-class is the owner-ruled substrate semantics); the MYC/NFIX credits are **TUNING** (same "responder with no read" provenance, :830–833).

**`_ground_terms` (:867–956)** — water/waterlogging monthly factors + best-of-class reduction. Stacked layers: (i) moisture need = `moisture_opt × (1−drought_tolerance)` (:877–880); (ii) wet-obligate inversion at `WLOG_INVERT_T=0.7` cliff, switching both terms to `fresh_availability` (:883–892); (iii) dry-plan waterlogging excess (:899–901); (iv) **four additive reliefs stacked on the cost side**: moisture_breadth dry/wet (`MB_DRY_W/MB_WET_W`), graded waterlogging ramp to the cliff (`WLOG_GRADED_W`), drip_tips, leaf_margin (:916–935); (v) dormancy gating (:940–943). Four separate relief mechanisms all soften the same two factors — this is the single clearest accretion site in scope.
- Verdict: base water/waterlogging **LOAD-BEARING**; the relief stack **VESTIGIAL-SUSPECT** — each relief is a flat weight fitted under B6's "every responder needs a read" program (B6 spec §4's "viable-range restoration" frames them as fixes for ranges that collapsed); three of the four act on the *same* saturated-end cost, so their individual contributions are unidentifiable.

**`_water_chemistry` (:959–987)** — water-medium pH/salinity against `water_ph`/`sal_water`. Verdict: **LOAD-BEARING** (only chemistry read for aquatic plans).

**`_tail_terms` (:990–1045)** — rooting best-of-class (:1000–1002); anchoring: holdfast→`eff_hard`, land trees→`(1−eff_hard)` with wind-storm modulation of the *need* (:1004–1021); medium boundary `1e-3` (:1023–1038); freshwater habitat term replacing the boundary (:1023–1026); submerged light vs photic/column depth (:1040–1044). Verdict: medium boundary + freshwater habitat + submerged light **LOAD-BEARING** (they define where plans can exist at all); anchoring wind modulation **TUNING**; rooting **TUNING** (saturating cost, rarely binding).

**`_glacier_factor` (:1048–1061)** — glacier exclusion `1e-3`, snow-adapted exempt; emitted unconditionally (:1094). Verdict: **TUNING** — B6-added exclusion; effect is real only on glacier cells.

### E. Composition & reduction

**`evaluate(view, ctx)` (:1067–1112)** — assembles all strata, `F = Π factors`, `s_env = 1−2F`, plus `substrate_share` U = Σ wᵢ·Π fᵣ(classᵢ) (:1104–1111) exported as capacity metadata. ~14 factors × (12,H,W) f32 per call. Callers: engine.py:589,805; genesis.py:722,836; statpass.py:145; tests; `__main__`. Verdict: **LOAD-BEARING** — the single entry point of the whole channel. Note: U's per-class product includes the rooting suit while F's rooting is best-of-class — an undocumented asymmetry.

**`verdict_at` (:1115–1128)** — materializes a `StressVerdict` at one (cell,month). Callers: **only `test_adapter.py:599`**. The engine never uses it — it reduces factors itself (`engine._cache_from_factors` :549–569) and composes via `kernel.stress.compose` in `_verdict_feed` (engine.py:1164). Verdict: **VESTIGIAL-SUSPECT** — a dead production path kept alive by one test; duplicates the compose logic the engine inlines.

**`annual_stress` (:1134–1137)** / **`worst_stress` (:1140–1145)** — 12→(H,W) reductions. Callers: only `__main__.py:160,182,207` (the acceptance/demo driver). The engine's real reduction (worst-month argmin + provenance at that month) lives in `engine._cache_from_factors`. Verdict: **TUNING** (demo-only helpers; the load-bearing worst-month reduction was re-implemented in the engine rather than reused from here — duplicated logic).

## 6. Spec drift flags (flag only)

- **`drought_deciduous` is dead in the adapter.** B5 §4.1 (spec line 162): "drought_deciduous → drought stress relaxed in the dry season". The view carries it (stress_adapter.py:626) but *no stratum reads it* — `_ground_terms` never references it. Either unimplemented spec or dead view key.
- **Engine spec §5.1 stale tensor count**: k15-simdiff-engine.md:286 says `evaluate` returns "13+2 tensors"; `V1_FLORA` now has 15 names and `evaluate` emits 14 factors + F + s_env (+substrate_share) after B6 added glacier etc.
- **`kernel/stress.climate_suit` (the compensable T–P additive form, B5 §4.1's "fauna §3 shape") is unused by the adapter** — referenced only by `test_stress.py`. The adapter re-implements climate as split one-sided products. Spec text was amended to match (B5:144–154), so the drift is the orphan kernel function, not behavior.
- **REQ_LIGHT/REQ_SUBMERGED_LIGHT name collision** (req_flora.py:53,73): one provenance string, two emitters (adapter photic, engine shade) — spec-sanctioned via comment but exactly the kind of aliasing a rewrite should not inherit.
- B5 §4.5's "capped at 0.8" for implicit freshwater habitat is enforced inside `moisture.build_moisture`, not here — adapter reads the field raw; fine, but the cap is invisible from this scope.

## Summary (5 lines)

1. Most load-bearing: `evaluate` (the F=Πf, s=1−2F composition every round reads), `load_world`/`WorldContext` (the anchor-res world the whole engine is pinned to), and the base water/waterlogging + medium/habitat terms that define where plans can exist.
2. Also load-bearing as contract: `req_flora.py` — k13 `select()` routes on these exact strings; renaming breaks the organism side silently.
3. Top vestigial suspect: the B6 relief stack in `_ground_terms` (moisture_breadth/graded-wlog/drip-tips/leaf-margin — four flat-weight reliefs on two factors, fitted to restore collapsed preset ranges).
4. Next suspects: `verdict_at` (test-only dead path), `annual_stress`/`worst_stress` (demo-only; engine re-implements reduction), unconditional `_bloom_frost`/`_glacier` emission, and the seed-1-calibrated snow-load constants in `_climate_factors`.
5. Confirmed drift for the rewrite: `drought_deciduous` unread (B5 §4.1 promises it), stale "13+2" count in engine §5.1, and the `pressure:light` name collision — all flag-only per instructions.

---

### demand.py + population.py + statpass.py + postpass.py — capacity accounting

Scope files: `exp/k15_simdiff/demand.py` (261), `population.py` (143), `statpass.py` (324), `postpass.py` (105). All paths relative to `/home/ywh/desktop/ai/unwritten-exp/repo`.

---

## 1. population.py — the §6 density/vital core (spec-faithful)

Module constants `population.py:29-38` — `ROUND_YEARS, BIOMASS_REF, PROD_CAP_SCALE, DENS_C, DENS_CAP, K_EPS, VIG_K, DIE_K, N_FLOOR`. Pure, numpy-vectorized, **no draws** (no Stream anywhere).

| Mechanism | Anchor | Consumes → returns | Called by |
|---|---|---|---|
| `percap_demand(view)` | `population.py:41` | DerivedView `crown_spread_m`, `woodiness` → scalar per-cap demand `crown²(1+wood)/BIOMASS_REF`; missing keys → 0 | `engine.py:597,706,809,969,1018,1573`; `genesis.py:704,839`; `test_engine.py:121`; `k15_descent` indirectly |
| `cell_demand(N_stack, percap)` | `population.py:51` | (I,H,W) stack × (I,) percap → (H,W) D via einsum | **tests only** (`test_population.py:49`) |
| `lineage_capacity(productivity, U)` | `population.py:60` | raw productivity raster × substrate share U → K_L = `PROD_CAP_SCALE·K·U` (water plans U=1) | `genesis.py:566-571` (re-export wrapper, "never duplicated"), `engine.py:808,971,1290,1313`; `test_genesis.py:448,686`; `k15_descent/descent.py:77` |
| `density_stress(D, K_L)` | `population.py:72` | shared D, K_L → `clip(DENS_C·D/max(K_L,K_EPS),0,DENS_CAP)`; K_L≤K_EPS & D>0 → DENS_CAP | `vital_update` (`:106`); `engine.py:1313` (s_real dict for dispersal); tests |
| `bscale(s_real)` | `population.py:87` | s_real → `clip(1−s_real, 0, 1+VIG_K)` growth gate | only `vital_update` (`:107`) + tests |
| `vital_update(N, s_env, D, K_L, birth, death)` | `population.py:96` | s_real = s_env + s_dens; `N' = clip(N·exp(clip((growth−mort)·T,±50)),0,1)`; mort = death + DIE_K·max(s_real,0) | `update_instance` (`:136`) + tests |
| `extinction_floor(N1)` | `population.py:119` | N < N_FLOOR → 0; returns (N_clean, abandoned mask) | `update_instance` + tests |
| `update_instance(...)` | `population.py:131` | vital_update + extinction_floor in one call | `engine.py:1291` (the rounds' §6 step); tests |
| `density_half_life_rounds(s=0.3)` | `population.py:140` | ln2/(DIE_K·s·T) — §6 design-constraint self-check | **tests only** (`test_population.py:143`) |

**Production D(c) is computed in the engine, not here**: `engine.py:1278-1280` accumulates `D[ws] += d.N * d.percap` over live instances (sorted-agnostic float += on disjoint windows), then per instance `K_L = lineage_capacity(self.K[ws], d.cache.U[ws])` (`:1290`) and `update_instance` (`:1291-1293`). The resulting per-instance `s_real` dict (`:1311-1314`) feeds §7 dispersal emission gating. Retired instances (`mass ≤ 0`, `:1295-1296,1315-1317`) flow to `self.retired` → `persist.py` density.json / state.json. Downstream readers of the outputs: dispersal (s_real), `_cap_seed_demand` (N·percap, `engine.py:890`), persist (N fields), test tiers.

### Verdicts (population.py)
- `percap_demand` — **LOAD-BEARING** as a slot (it IS the demand currency: genesis founder N = D/percap, rounds D accumulation, seed cap, descent), but its *formula* is a declared stub: biosphere plan §4 (`biosphere-plan-2026-08-04.md:115-119`) says "the percap demand weight (today: crown² × (1+woodiness), a stub) becomes the Phase-1 biomass". Keep the interface, replace the body in the rewrite.
- `lineage_capacity`, `density_stress`, `vital_update`, `bscale`, `extinction_floor`, `update_instance` — **LOAD-BEARING**. This chain is the entire per-round biomass accounting and exactly implements spec §6 (`k15-simdiff-engine.md:327-369`).
- `cell_demand` — **VESTIGIAL-SUSPECT**: production never calls it; the engine re-implements D accumulation inline (`engine.py:1278-1280`). It encodes an (I,H,W) N_stack architecture the engine abandoned (the AGENTS.md memory rule forbids materializing that stack anyway). Only `test_population.py:42-57` keeps it alive.
- `density_half_life_rounds` — **TUNING**: calibration self-check, tests only; zero sim impact if deleted.
- Constants — **TUNING** knobs, all spec §13-settled; structurally removable, numerically load-bearing.

---

## 2. statpass.py — pre-engine calibration harness (standalone CLI)

No production import. `genesis.py:78-80,234` explicitly states `reduced`/`valid_mask` were *lifted verbatim* out of statpass because "statpass.py is a calibration harness and is never imported". Runs as `python -m exp.k15_simdiff.statpass` (`statpass.py:27`). No draws (deterministic stress stack).

| Mechanism | Anchor | Consumes → returns | Called by |
|---|---|---|---|
| `reduced(factors)` | `statpass.py:74` | adapter factor stack → m*(c), F_worst(c), per-requirement provenance | `analyze_preset` (`:147`); duplicated in `genesis.py:230` |
| `valid_mask(view, ctx)` | `statpass.py:89` | medium/salinity → (H,W) bool; freshwater mask via `FRESH_MASK_MIN` | `analyze_preset` (`:149`); duplicated in `genesis.py:248` |
| `capacity_anchor(seed, ctx)` | `statpass.py:106` | k14 `derived.npz` productivity products, mean-pooled 1024→256 → K(c) raster | `report` (`:271`) |
| `preset_traits` | `statpass.py:127` | pack preset → merged traits dict | `analyze_preset` (`:176`) |
| `partition_k(range_cells)` | `statpass.py:133` | spec §10 verbatim `clip(1+floor(log2(range/200)),1,8)` | `analyze_preset` (`:217`) |
| `analyze_preset(...)` | `statpass.py:142` | full per-preset row: genesis/colonizable cell counts vs `GENESIS_F=0.5`/`EST_F_MIN=0.3`, biome mix, binding constraint, vital rates, density-term equilibrium N* (`:188-191`), flags (NO_RANGE/TINY_RANGE/GENERALIST/VITAL_INVERSION/PERSIST_FAIL, `:194-204`) | `report` (`:274`) |
| `knob_checks(rows)` | `statpass.py:239` | DIE_K half-life ≥5, no-range counts, vital inversions, persist-fails | `report` (`:284`) |
| `report(seed)` / `_fmt_row` / `main` | `statpass.py:267,287,302` | per-seed JSON/console calibration report | CLI only |

Removal blast radius: **nothing in the sim**. Deleting it removes the calibration regression reference; its two load-bearing derivations (`reduced`, `valid_mask`) already live on as copies in genesis.py.

Verdict — **TUNING** (the whole module). It exists to settle the (cal) knobs. Two structural smells:
- **Drift-by-duplication**: its knob block (`statpass.py:48-61`) shadows `population.py:30-38` + `genesis.py:107` constants. Values currently agree (GENESIS_F 0.5, BIOMASS_REF 25, DENS_C 0.5, DIE_K 0.002, N_FLOOR 0.01), but the docstring's own plan ("when the engine lands they move to its module constants", `:22-24`) was only half-executed — the copies were never collapsed. The `knobs` report dict (`:276-283`) even omits `DENS_CAP`.
- Its equilibrium-N* check (`:188-191`) is the analytic shadow of `density_stress`'s fixed point — a calibration formula, not sim machinery.

Spec check: `partition_k` matches §10.5 (`k15-simdiff-engine.md:794-796`); `GENESIS_F`/`EST_F_MIN` match §13 (`:1067,1071`). No contradiction — the module is the *source* of the "(cal, stat-pass settled)" annotations.

---

## 3. demand.py + postpass.py — post-sim tree-fill machinery (tickets 0032/0034)

**Critical wiring fact: nothing in production calls either module.** `run_post` is imported only by `test_postpass.py:28`; `demand` only by `postpass.py:23` and tests. `__main__.py`, `engine.py`, `persist.py` never invoke the post pass — persisted trees (`persist.py:292`) therefore never contain demand-created nodes. Spec §11 module layout (`k15-simdiff-engine.md:985-1002`) does **not list** demand.py or postpass.py. Ticket 0027 (the pass's intended consumer, "bundle differentiation + rare plops") was closed 2026-08-04 with "folds into the rewrite" (`queue/closed/0027:1-4`).

### demand.py inventory

| Mechanism | Anchor | Consumes → returns | Stream draws |
|---|---|---|---|
| `soft_cap(x)` | `demand.py:56` | tanh squash above `CAP_ONSET` (treebuilder shape) | none |
| `decode_factor(stream)` | `demand.py:65` | heavy-tailed radiation factor `soft_cap(DECODE_MEDIAN·exp(RADIATION_TAIL_SIGMA·z))` | `stream.normal(0)` |
| `_draw` / `_daughter_axes` | `demand.py:73,81` | type envelope → daughter axes; pool entries drawn, scalars jittered ±`DAUGHTER_JITTER=0.02` EXCEPT the 6 stress-interface axes (`:88-90`) and `height_m` | children `"jit"`, `f"f{ax}"`, `stream.randrange` |
| `_next_index` / `_committed_genus_names` | `demand.py:103,115` | deterministic child indexing / name-collision seed set | none |
| `_set_gen_time` | `demand.py:123` | gen_time from `height_m` via k13 backbone coeff/exp | none |
| `_species_node` | `demand.py:135` | one SPECIES Node: axes via `_daughter_axes`, g = `host.g + 60.0·exp(0.3·z)` (`:143`), `radiate="never"` | `sstream.normal(0)`, `u64` sid |
| `_demand_family` | `demand.py:152` | FAMILY host → G=round(magnitude) genera (k13-composed names, `DG_FAMILY_MEDIAN·exp(DG_SIGMA·z)` g, terminal) × per-genus `decode_factor` species | children `f"g{k}"`, `"factor"`, `"name"`, `f"s{s}"` |
| `demand(pack, type_spec, magnitude, hosts, stream, ...)` | `demand.py:204` | rank dispatch: GENUS → `max(1, round(magnitude·exp(MAGNITUDE_SIGMA·z)))` species round-robin over hosts; FAMILY → `_demand_family`; higher ranks refused (`:235`); returns STAGING SET | caller-passed stream + `stream.normal(0)`, children `f"s{k}"` |

### postpass.py inventory

| Mechanism | Anchor | Consumes → returns |
|---|---|---|
| `_post_eligible` | `postpass.py:32` | tree → sorted nodes with `radiate in ("post","pre-and-post")` |
| `_node_envelope` / `_bundle_spec` / `_bundle_base` / `_anchor_hosts` | `:38,46,55,68` | type envelopes: node-self (default completion) vs bundle envelope over plan base; hosts = post-eligible anchor genera |
| `run_post(tree, pack, seed)` | `postpass.py:79` | `Stream(seed,"k15.post")`; loop 1 default completion (`decode_factor` per node, children `fill{i}`/`fill{i}d`); loop 2 bundle demands at `BUNDLE_MAGNITUDE=50` (`:29`) over anchors (children `bundle{j}`); shared `next_idx`/`used` across demands; returns staging set — **caller commits, and no caller exists** |

Verdicts:
- `demand` + `run_post` — **VESTIGIAL-SUSPECT (unwired machinery, not an ad-hoc filter)**: precisely why — (a) zero production call sites, outputs go nowhere (no commit path, persist never sees them); (b) its only consumer ticket (0027) was explicitly deferred to the k15_biosphere rewrite; (c) the k15 spec v1.9 doesn't acknowledge the modules. The mechanism itself is owner-settled design (0032/0034), so the rewrite should harvest the *semantics* (rank-aware fill, pool draws + jitter, terminal genera, shared `next_idx`/`used` determinism protocol), but the code is currently a loaded gun with no trigger.
- `BUNDLE_MAGNITUDE = 50` (`postpass.py:29`) — **TUNING**, and self-declared placeholder: "0027's differentiation will size per-bundle from the sim outcome; this is the mechanism's default."
- `MAGNITUDE_SIGMA`, `DAUGHTER_JITTER` (`demand.py:47,49`) — **TUNING** knobs shaping scatter only.
- `soft_cap`/`decode_factor` — deliberate copies of treebuilder idioms ("same shape as the treebuilder's", `:57-68`) — duplication-by-design for the byte-compat contract (0034); in the rewrite these should collapse to one implementation.

Spec-drift flags (demand/postpass):
- `postpass.py:15` docstring claims "pinned k15.post / **k15.demand** streams" — no `k15.demand` stream is ever created; demand draws from children of the caller's `k15.post` stream. Doc drift only.
- `demand.py:143`: species-edge g increment `60.0·exp(0.3·z)` — inlined magic numbers; spec §13 names `G_STEP_REF = 100` as "species-edge dg scale" (`k15-simdiff-engine.md:1089`) for the rounds. Different contexts (post-fill vs rounds), but the 60 vs 100 mismatch is undocumented.
- Absence from spec §11 module layout (noted above) — flag, not fix.

---

## 4. Spec-drift flags in the capacity chain

- **U-weighting of D**: spec §6 (`k15-simdiff-engine.md:341-347`) and `population.py:74-77` both say D sums instances "U-weighted by the SAME U_L", but neither `cell_demand` (`:57`, plain einsum) nor the engine's inline accumulation (`engine.py:1278-1280`, plain `N·percap`) applies any U weight. The code implements `s_dens = DENS_C·D_unweighted/(K·U_L)`; if D were U_L-weighted the U_L would cancel. Either the spec/docstring sentence is stale or the implementation diverged — flag only.
- Otherwise population.py matches §6 exactly (percap formula `:332`, K/K_L `:334-335`, clip/K_EPS rule `:343`, bscale/mort/exp form `:356-359`, extinction floor `:362-363`, half-life constraint `:364-366`).
- `engine._cap_seed_demand` (ticket 0037, `engine.py:849-903`, `GENESIS_S=0.5` at `engine.py:136`) — the per-cell total-demand proportional squeeze at mint — is the most "layered-on filter" mechanism *adjacent* to this scope: it re-reads `percap`/`N` after the fact to repair over-stacked minting, exempts descent fragments by construction (`:874-878`), and deliberately lets floor-clamped cells overshoot the cap. It's in engine.py not my scope, but any rewrite of the demand accounting must reckon with it: it exists because founder N is set per-lineage in isolation (`genesis.demand_field`) and the stacking is patched up afterwards.

---

## Summary (5 lines)

1. **Most load-bearing #1**: `population.vital_update`/`update_instance` chain (`population.py:96-137`, driven from `engine.py:1290-1293`) — the entire per-round biomass/capacity dynamics; spec-exact §6.
2. **#2**: `lineage_capacity` + the K_L = PROD_CAP_SCALE·K·U substrate-share split (`population.py:60-69`) — the per-cell capacity contract shared by genesis, descent, and rounds; deleting it breaks every seeding and every round.
3. **#3**: `percap_demand` (`population.py:41-48`) — the demand currency interface (load-bearing slot), though its crown²×(1+wood) formula is an owner-declared stub scheduled for Phase-1 biomass replacement.
4. **Top vestigial suspects**: `demand.py`+`postpass.py` wholesale — fully implemented 0032/0034 tree-fill machinery with zero production callers and no spec §11 listing (outputs unreachable); and `population.cell_demand` — a dead N_stack-era API superseded by the engine's inline D accumulation, alive only in tests.
5. **Watch items for the rewrite**: the spec-vs-code "U-weighted D" contradiction (§6 vs `engine.py:1278-1280`); statpass's duplicated (cal) knob block that was never collapsed into population/genesis; and the adjacent ticket-0037 `_cap_seed_demand` post-hoc squeeze — the clearest instance of the owner's "layered filters for ad-hoc goals" critique touching this scope.

---

### persist.py + __main__.py — artifact and driver

Per-seed dir `exp/k15_simdiff/out/seed_NNNNNNNN/` (gitignored, `repo/.gitignore:29`):

| file | writer (file:line) | contents |
|---|---|---|
| `density.json` | persist.py:271-277 | `{meta: {schema:"k15.density/1", world:[H,W], rounds, dtypes:{N:"f8",mask:"u1"}}, instances:[{iid, sid, box:[y0,y1,x0,x1] (exclusive, engine convention engine.py:182), N: windowed f64 row-major flat list, mask: u1 (N>0) flat list}]}` — sorted iid, full-precision floats |
| `state.json` | persist.py:280-290 | `eng.state_json()` (engine.py:2015-2030: `{seed, instances:{iid:{sid,cells,mass:round9,rain:round9,traits}}, retired:[iid], reflog:count}`) **plus** `experiment, k15_version(=1), commit (git HEAD — only checkout-dependent line), rounds, world, lineages` |
| `tree.json` | persist.py:294-298 | k13-schema amended tree; meta mutated in place: `delivered_by, rounds, amended:true` |
| `reflog.json` | persist.py:301-302 | full authority decision list; entries `{event, sid, ...details}` — **no round stamps** (authority.py:741,880,924,1087,1167) |
| `delivery.npz` | persist.py:230-234 | `sim_density` 1024² f32, `richness_hi` 1024² u2, `richness_anchor` 256² u2, `lineages_idx` 256² u2 |
| `delivery.k11pack` | persist.py:240-257 | 3 layers: `sim_density` (q8, percentile-99.5 scale, RAMP_DENSITY), `species_richness` (q8, max scale, RAMP_RICHNESS), `lineages` (`kind:"list"`, u2 idx → deduped sorted sid tuples); meta `{generator, pack, seed, rounds}` |
| `rounds/rNNNN.json` | round_snapshot, persist.py:92-105 | opt-in (`--per-round` only): same instance-record schema as density.json + `{round: t}` — the **only** round stamp anywhere |
| `manifest.json` | write_manifest, exp/artifacts.py:191-205 | `{inputs:[stamp(k11,seed), stamp(flora,seed)], created_commit, note}` — no timestamps |

**NOT persisted per round:** reflog round stamps; per-round density (off by default); per-round commit-outcome counters (console-only, `__main__.py:384-391`); capacity K(c), stress fields, per-instance caches, rain/div/orphan arrays, seed-bank/WIP-cluster state, wall times. A run cannot be resumed or reconstructed mid-history from the dump — it is an end-of-run snapshot plus decision log.

## Census

### persist.py

- **`out_dir(seed)`** :68 — path helper. Called by `round_snapshot`, `dump`. Streams: none. Removal: trivial. LOAD-BEARING (convention anchor, registered in exp/artifacts.py:78).
- **`_instance_records(eng)`** :73 — engine instances → sorted windowed JSON records. Called by `round_snapshot`, `dump`. Streams: none. Removal breaks density.json + rounds/. LOAD-BEARING — the core sim-output serializer.
- **`round_snapshot(eng,t)`** :92 — optional per-round density dump. Called only by `__main__.py:383` under `--per-round`. No downstream reader anywhere. Removal: loses a debug aid. VESTIGIAL-SUSPECT (off by default, unconsumed; exists to debug rounds, not to deliver).
- **`_bilinear_up(a,factor)`** :111 — deterministic 4× bilinear upscale. Called by `_hires_density` (2×/instance), `_deliver` (richness). Display-only. TUNING (delivery cosmetics; k14 de-blocking idiom).
- **`_settle_hi(a,mask,passes=2)`** :134 — 3×3 masked box blur ×2 at 1024². Called only by `_hires_density`. TUNING — a pure smoothing filter layered on the upscale to make the display map look settled; structurally removable, only changes pixels.
- **`_hires_density(eng)`** :152 — per-instance upscale + mask re-threshold (>0.5) + settle, summed into one running 1024² plane. TUNING (display-only by owner decision; never feeds a sim round).
- **`_anchor_fields(eng)`** :174 — 256² richness u2, deduped lineages table + per-cell u2 idx, by-sid groups. Called by `_deliver`. Feeds both delivery products. TUNING (viewer overlay), though it's the only richness computation in the dump.
- **`_deliver(eng,rounds,out)`** :218 — writes delivery.npz + delivery.k11pack. Callers: `dump` only. Blast radius: `delivery.k11pack` is read by `exp/k11_worldgen/viewer/test_k15pack.mjs:27` (+ pytest wrapper `test_k15pack.py`); **`delivery.npz` has no reader in the repo** — grep finds only the writer. Verdict: k11pack TUNING; **delivery.npz VESTIGIAL-SUSPECT** (a display artifact with zero consumers; `_hires_density`'s expensive output is duplicated q8-quantized into the pack anyway).
- **`dump(eng,rounds)`** :263 — the 6-step dump above. Caller: `__main__.run_rounds`:398 only (never called from tests). Downstream readers: `tools/artifact_query.py` (state/density/tree/reflog/manifest) + `tests/test_artifact_query.py`. LOAD-BEARING — the engine's only persistence; without it K15 "dies with the process" (spec v1.7). Note: **mutates `eng.authority.tree.meta` in place** (:295-297) — a persistence pass with an in-memory side effect.
- **Dead code:** `TOOLTIP_LINEAGE_MAX` (:59) defined, never used — the tooltip table is uncapped; `RAMP_TERRESTRIAL` imported (:51), never used. Both VESTIGIAL.

### __main__.py

- **Band/preset constants** (:78-111) + **`_RESOLUTIONS`** (:113-134): named acceptance thresholds and print-only ambiguity notes. TUNING knobs; `_RESOLUTIONS` is documentation emitted with the report.
- **`dist_to_ocean(ctx)`** :137 — O(max(H,W)) dilation loop; result passed as `dist_ocean` into all five `check_*` fns — **none of them use the parameter**. VESTIGIAL-SUSPECT: leftover from the pre-2026-08-01-ruling mangrove band (B5 §8.2 spec text still says "high-HAND coastal band"; the code now bands on `fresh_availability ≥ 0.6`, making ocean distance irrelevant). Pure wasted compute plus dead plumbing.
- **`check_mangrove/xeric/kelp/calcifuge/signed_scale`** (:153-278): B5 §8.2-8.5/8.8 acceptance checks on authored presets via `evaluate`/`worst_stress`/`annual_stress`. Callers: `run()`. They consume the stress adapter, return (ok, detail), mutate nothing. TUNING — acceptance scaffolding: hard-coded thresholds (`w_mean>0.8`, `gap>0.3`, `h_mean<0.25`, …) that pin adapter behavior only through the human-run CLI, not pytest.
- **`check_determinism`** :281 — double full 150-species eval, `np.array_equal`. TUNING/gate (duplicated in pytest).
- **`run(seed)`** :294 — adapter acceptance driver: loads content/world/tree, asserts 150 species, budget timing (B5 §8.7), runs checks, prints. No draws, no streams (`time.perf_counter` for walls only, never persisted). LOAD-BEARING as the §8 acceptance entry point, display-only otherwise.
- **`run_rounds(seed,rounds,do_dump,per_round)`** :351 — the engine run driver: `Engine(seed)` → `genesis` → `eng.round(t)` loop with console table (instances/lineages/mass/cells/commit outcomes) → `persist.dump`. Streams: none itself (engine owns all `kernel.hashrng` draws). LOAD-BEARING — the only path from engine to artifact.
- **`main()`** :405 — argparse (`--seed/--rounds/--no-dump/--per-round`), dispatches run vs run_rounds. LOAD-BEARING (CLI).

**Determinism streams in scope: none.** Both files are draw-free pure functions of engine state / world dumps; every `kernel.hashrng.Stream` lives in engine/genesis/dispersal/authority.

## Spec drift flags (flag-only)

1. **density.json `box` ordering inconsistency (cross-module, spec-silent).** Writer is y-first: engine.py:182 `box = (y0,y1,x0,x1)`, persist.py:165 unpacks `y0,y1,x0,x1`, persists raw (:85). Reader `tools/artifact_query.py:28,148` (and its "independent" test decode `tests/test_artifact_query.py:65,71`) assumes `[x0,x1,y0,y1]` — transposed and using window height as row width. World is square (256²), so it stays in-bounds and tests (which share the wrong convention) pass; range/coexist cell sets are silently wrong for the 339/343 non-square windows. The spec (§12.10, v1.7 changelog) never pins the ordering. For the rewrite: pick one, document it in the schema field.
2. **B5 §8.2 spec text stale** — spec says "high-HAND coastal band"; code banded on `fresh_availability ≥ MARSH_FRESH` per the 2026-08-01 ruling recorded only in code comments (`__main__.py:73-77,156-158`). `dist_to_ocean` is the fossil of the spec-text version.
3. **B5 §8.6 (pigments) absent from the driver** — docstring numbering jumps (5)→(7) with no note of where §8.6 is gated.
4. **§12.10 whole-dir byte-identical `cmp`/`diff -r` gate is not automated** — no test or script performs it; the slow gate (`test_engine.py:1128-1141`) compares only `state_json()` digests. Spec §12.10/changelog v1.7 describe the dir-cmp as "the determinism gate"; `delivery.npz`/`delivery.k11pack` byte-determinism is unpinned (and `state.json` embeds the git commit, so the dir is only identical within a checkout).
5. World is 256² anchor, not 1024² (density.json meta `world:[256,256]`); 1024² exists only in the display pass.

## Summary (5 lines)

- Load-bearing #1: `dump()` (persist.py:263) — the engine's only persistence; artifact_query and the rewrite's raw material hang off it.
- Load-bearing #2: `_instance_records` (persist.py:73) — the windowed N+mask serializer that defines the density schema.
- Load-bearing #3: `run_rounds` (`__main__.py:351`) — sole genesis→rounds→dump driver; everything else in scope is display or acceptance scaffolding.
- Top vestigial suspects: `dist_to_ocean` (computed, threaded through 5 checks, used by none — fossil of the pre-ruling mangrove band), `delivery.npz` (written, never read), dead `TOOLTIP_LINEAGE_MAX`/`RAMP_TERRESTRIAL`, and opt-in `round_snapshot` (no consumers).
- Biggest correctness find for the rewrite: the y-first vs x-first `box` mismatch between persist.py and artifact_query.py — silent, test-masked, and spec-silent.
