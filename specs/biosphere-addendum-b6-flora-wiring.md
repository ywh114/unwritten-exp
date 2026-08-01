# Biosphere addendum B6 — flora wiring (P9)

v0.1 — 2026-08-01 — implementation

Implements the systematic hand-wiring program (owner ruling 2026-08-01)
after the causal audit found ~20 stress-claimed axes read by nothing, 8
dead responder rows, and 4 responder-less factors. The ruling: NO
ad-hoc patching — every flora axis is accounted for in one table, every
stress factor carries its responders, and axes with no env consumer are
annotated (fauna-pending / engine-pending / fire-pending) — a decision,
not a dangling annotation.

Amends `biosphere-addendum-b5-flora-stress.md` (§4 strata, §7 open
questions); consumes B3 (ground), B4 (water column), K11's snow/glacier
products (`c_snow_monthly`, `h_glacier_mask`), and the derived climate
envelope (`flora.derive.effective_climate`, owner ruling 2026-08-01).

## 1. Intent

Stress is the ONLY env→X channel (interface.py: the verdict's
provenance factors), and select() routes each factor to the driftable
traits that answer it. The audit's dead dials were axes that COULD move
under pressure but whose movement was read by nothing — selection was
pushing genes that changed no suitability anywhere, i.e. the pressure
plane was accumulating into a void. The program fixes this by reading
every such axis where its biology lands:

- **Credits** (B6 §2): axes that were pressure:fertility/salinity
  responders with no factor read become GRADED CREDITS in the stratum
  their responder row targeted — mycorrhizal/n_fixation → nutrient
  credits in `pressure:fertility`, halophyte → a salinity-tolerance
  credit in `pressure:salinity`. The responder row and the factor read
  now agree.
- **Vital wiring** (B6 §2): growth_rate / wood_density move the
  PROVISIONAL vital rates (birth/death), which the population layer
  actually consumes — the "pop" consumer label becomes true.
- **Wetness relief** (B6 §2): drip_tips / leaf_margin / a wider
  moisture_breadth / graded waterlogging tolerance relieve the
  saturated-end cost of `pressure:waterlogging` for dry plans.
- **Snow-load + glacier** (B6 §3): two NEW land strata from the K11
  snow products; `snow_adaptation` becomes the graded reliever it was
  authored to be.
- **Canopy light** (B6 §3): the engine-side shade pass — `canopy_density`
  (P9's derived) finally reads; `pressure:light` becomes a real land
  factor; height_m is its growth answer.
- **FIRE** is owner-deferred: `bark_thickness_cm`'s cold responder row
  (a dead dial — bark is the FIRE axis) is removed; `fire_strategy`,
  `serotiny`, `bark_thickness_cm` are annotated fire-pending.

No new mechanics beyond the two strata above: everything else is
re-wiring existing fields into existing shapes (B5's one-sided
saturating suits, the derived envelope, the provisional vital model).

## 2. The forward half — every flora axis → its consumer

"Formula location" names the file:line-style anchor (module + function /
constant). Consumers: `stress` = a B5/B6 suitability factor; `engine` =
the K15 round loop (dispersal, density, demography, the shade pass);
`derived` = recomputed at derive time (flora/derive.py); `display` =
id/name/tell/draw only. Axes with NO env consumer are annotated.

| axis | consumer | formula location |
|---|---|---|
| height_m | stress (anchoring need; engine shade `>` escape; snow-load height term) | stress_adapter `_view_from_record`/`_tail_terms`/`_climate_factors`; engine `_canopy_light_factors`; sim.vital gen_time |
| woodiness | stress (anchoring need); derived (canopy_density, provision_shelter); engine (percap) | `_tail_terms`, derive `_derived_canopy_density`/`_palatability`, population.percap_demand |
| wood_density | engine (vital death, inverse — B6 §2) | sim.vital `WOOD_DENSITY_*` |
| growth_rate | engine (vital birth scale — B6 §2) | sim.vital `GROWTH_*` |
| longevity_yr | engine (vital death) | sim.vital `DEATH_LONGEVITY_EXP` |
| shade_tolerance | stress (canopy-light relief — B6 §3) | engine `_canopy_light_factors` |
| pioneer_climax | **engine-pending** (successional dynamics) | — |
| layer | stress (submerged flag; canopy-light exposure coef — B6 §3) | `_view_from_record`, engine `_canopy_light_factors` (`LAYER_LIGHT_COEF`) |
| halle_axes / halle_growth / halle_flowering / halle_branching / halle_orientation | display (id/draw; the Hallé tuple) | derive `_raunkiaer`/silhouette |
| apical_dominance / branch_angle / tier_spacing_m | display (id/draw) | — |
| crown_spread_m | engine (per-capita space demand) | population.percap_demand |
| canopy_density | **derived**; engine (shade pass — B6 §3) | derive `_derived_canopy_density` (P9, now consumed) |
| leaf_shape | derived (canopy_density floor: `none` → cd 0; leaf_color); display | derive `_derived_canopy_density`/`_derived_leaf_color` |
| leaf_size_cm | stress (envelope heat/arid dial; pressure:heat responder) | derive `effective_climate` (`T_LEAF_C`/`P_LEAF`), stress_response `pressure:heat` |
| leaf_persistence | stress (winter_deciduous flag: cold gating, envelope `T_DECID_C`; derived cd evergreen add) | `_view_from_record`, `_climate_factors`, derive `effective_climate`/`_derived_canopy_density` |
| leaf_margin | stress (wetness credit — B6 §2: serrate/toothed) | `_ground_terms` (`LEAF_WET_W`) |
| leaf_compoundness / leaf_arrangement | display (id/tell/draw) | — |
| leaf_color / autumn_color | derived display | derive `_derived_leaf_color`/`_derived_autumn_color` |
| leaf_sla | derived (canopy_density economics; leaf_color) | derive `_derived_canopy_density` (`CD_SLA_*`) |
| leaf_trap | **fauna-pending** (insectivorous prey channel) | — |
| drip_tips | stress (wetness credit — B6 §2) | `_ground_terms` (`DRIP_WET_W`) |
| root_type | stress (holdfast flag) | `_view_from_record`/`_tail_terms` |
| root_depth_m | stress (rooting excess) | `_substrate_suits`/`_tail_terms` (`REQ_ROOTING`) |
| root_spread_m | display (id) — stress claim removed | — |
| root_special | display (id/tell); pneumatophores plan-gated (stress_response comment) | — |
| mycorrhizal | stress (fertility credit — B6 §2) | `_substrate_suits` (`MYC_CREDIT`) |
| n_fixation | stress (fertility credit — B6 §2) | `_substrate_suits` (`NFIX_CREDIT`) |
| flower_symmetry | **fauna-pending** (pollinator display; runaway) | — |
| flower_color | derived display | derive `_derived_flower_color` (B5 §5.2) |
| pigment_pathway / pigment_expression | derived (flower_color); **fauna-pending** (pollinator coupling) | derive `_derived_flower_color` |
| flower_size_mm | derived (provision_nectar); **fauna-pending** | derive `derive_derived` (`NECTAR_SIZE_REF_MM`) |
| inflorescence | display (id/name) | — |
| pollination_syndrome | **fauna-pending** (derived provision_nectar; pollinator coupling) | derive `derive_derived` |
| sexuality | **fauna-pending** (reproduction system) | — |
| fruit_type | derived (provision_mast); **engine/fauna-pending** (dispersal structure) | derive `derive_derived` (`MAST_*`) |
| fruit_size_mm | **engine/fauna-pending** | — |
| fruit_color | **fauna-pending** (seed-disperser signal) | — |
| dispersal_channels | engine (dispersal packets, mobility) | engine `_dispersal`, `mobility` |
| propagule_mass_mg | engine (distance decay; vital fecundity/establish) | dsp kernels, sim.vital |
| propagule_count | engine (emission quantity) | dsp.emission |
| seed_bank | engine (vital establish mult; rain decay) | sim.vital, dsp.decay_rain — verified engine-read, "stress" claim removed |
| serotiny | **fire-pending** (fire-released seed) | — |
| masting_interval_yr | **engine-pending** (mast cycle — future emission modulator) | — |
| jump_rate | engine (jump-packet frequency) | dsp.maybe_jump |
| mechanical_defense / chemical_defense / defense_potency | **fauna-pending** (herbivory; derived palatability → provision_graze/browse) | derive `_palatability` |
| storage_organ | **engine-pending** (storage resilience) | — |
| clonal_spread_m | engine (vital establish mult); derived (clonality_class) | sim.vital, derive `derive_derived` |
| succulence | stress (envelope dials; pressure:water responder; derived cd) | derive `effective_climate`, stress_response `pressure:water` |
| bark_thickness_cm | **fire-pending** (the fire axis; cold responder row REMOVED — dead dial) | — |
| bark_texture | display (id/tell/draw) | — |
| cuticle_thickness | stress (envelope dials; heat/water responders) | derive `effective_climate`, stress_response |
| pubescence | stress (envelope dial; pressure:cold responder) | derive `effective_climate`, stress_response `pressure:cold` |
| leafout_month | stress (cold gating; bloom-frost responder) | `_climate_factors`, stress_response |
| deciduous_trigger | stress (winter/drought flags) | `_view_from_record`, `_climate_factors` |
| bloom_start_month / bloom_length_months | stress (bloom frost) | `_bloom_frost`, stress_response `pressure:bloom_frost` |
| fruit_month | **engine-pending** (seed-release timing) | — |
| synchronous_flowering | **fauna-pending** (pollinator synchrony) | — |
| photosynthesis | stress (C4/CAM cold penalty; envelope dials) | `_climate_factors`, derive `effective_climate` |
| parasitism / mycoheterotrophy / saprotrophy | **engine-pending** (parasitic / mycoheterotrophic / decomposer nutrition) | — |
| nutrient_package | stress (halophyte salinity credit — B6 §2) | `_sal_tol_eff` (ground + water strata) |
| drought_tolerance | stress (water need; envelope dials) | `_ground_terms`, derive `effective_climate` |
| salinity_tolerance | stress (ionic excess; freshwater classification) | `_substrate_suits`/`_water_chemistry`/evaluate |
| waterlogging_tolerance | stress (saturated end; wet-obligate inversion; B6 graded relief) | `_ground_terms` (`WLOG_*`) |
| ph_tolerance | stress (position; split one-sided) | `_ph_suit_split` |
| fertility_requirement | stress (fertility shortfall) | `_substrate_suits` |
| growing_season_req | stress (growing-season term; envelope dial) | `_climate_factors`, derive `effective_climate` |
| fire_strategy | **fire-pending** (owner-deferred; no fire-regime field) | — |
| snow_adaptation | stress (snow-load tolerance — B6 §3; envelope `T_SNOW_C`; glacier exemption) | `_climate_factors`, `_glacier_factor`, derive `effective_climate` |
| engineer_impact | **fauna-pending** (ecosystem engineering: peat/kelp/reef) | — |
| coloniality | **engine-pending** (colony integration) | — |

### Derived axes (recomputed at derive time, never sampled)

| derived | inputs | consumer |
|---|---|---|
| raunkiaer | height_m, layer, longevity_yr, storage_organ, plan | display (life-form key) |
| provision_mast / graze / browse / nectar / shelter | fruit_type, dispersal_channels, layer, defense_potency, chemical_defense, pollination_syndrome, flower_size_mm, height_m, woodiness | **fauna-pending** (food web) |
| clonality_class | clonal_spread_m | display |
| silhouette | halle_* | display |
| flower_color / leaf_color / autumn_color | pigment_*, ph_tolerance, pubescence, cuticle_thickness, leaf_sla, leaf_persistence | display |
| canopy_density | woodiness, leaf_sla, leaf_persistence, succulence, leaf_shape | **engine** (shade pass — B6 §3) |

### Counts (axes; 84 authored + 9 derived)

- **Wired to an env consumer**: 41 axes (a stress factor, the engine,
  or a vital proxy).
- **fauna-pending** (no env consumer; a decision, not dangling): 15 —
  leaf_trap, flower_symmetry, pigment_pathway/expression (coupling
  half), flower_size_mm (coupling half), pollination_syndrome,
  sexuality, fruit_type/size_mm/color, mechanical_defense,
  chemical_defense, defense_potency, synchronous_flowering,
  engineer_impact.
- **fire-pending** (owner-deferred): 3 — fire_strategy, serotiny,
  bark_thickness_cm.
- **engine-pending** (a future engine read): 8 — pioneer_climax,
  masting_interval_yr, storage_organ, fruit_month, parasitism,
  mycoheterotrophy, saprotrophy, coloniality.
- **display-only**: 14 authored (the halle/branch/tier/arrangement/
  compoundness/bark_texture/inflorescence/root_spread_m/root_special
  set) + 3 derived display (flower_color, leaf_color, autumn_color —
  recomputed at derive time, never sampled).
- **River flow-stress**: designed-pending (not built — the water packet
  already rides the flow field; a flow-STRESS stratum is future work).

## 3. The backward half — every stress factor → its responder rows

`stress_response.toml` (select()'s routing table), updated 2026-08-01.
A factor with an EMPTY responder list emits no pressure (the lineage
simply shrinks where unsuitable — interface ruling). Changes vs the
audit: `pressure:cold` drops the dead `bark_thickness_cm` row; every
responder row now answers a factor that actually reads its target.

| factor (env) | responder rows (driftable traits) | read location |
|---|---|---|
| pressure:cold | leaf_persistence→winter_deciduous, deciduous_trigger→winter, growing_season_req↓, leafout_month↑, pubescence↑ | `_climate_factors` (T distance + growing season + C4/CAM + B6 snow-load) |
| pressure:heat | photosynthesis→C4, leaf_size_cm↓, cuticle_thickness↑ | `_climate_factors` (T excess) |
| pressure:bloom_frost | bloom_start_month↑, leafout_month↑, bloom_length_months↓, leaf_persistence→winter_deciduous, deciduous_trigger→winter, phenology→winter_deciduous | `_bloom_frost` |
| pressure:water | drought_tolerance↑, succulence↑, cuticle_thickness↑ | `_ground_terms` (dry end; need = moisture_opt × (1 − drought), B6 mb relief) |
| pressure:waterlogging | waterlogging_tolerance↑ | `_ground_terms` (saturated end; wet-obligate inversion; B6 graded relief + wetness credits) |
| pressure:fertility | fertility_requirement↓, mycorrhizal→{arbuscular,ecto,ericoid,orchid}, n_fixation→{rhizobium,frankia,cyanobacterial} | `_substrate_suits` (best-of-class; B6 symbiosis credits) |
| pressure:ph_low | ph_tolerance↓ | `_ph_suit_split` |
| pressure:ph_high | ph_tolerance↑ | `_ph_suit_split` |
| pressure:salinity | salinity_tolerance↑, nutrient_package→halophyte | `_substrate_suits`/`_water_chemistry` (ionic; B6 halophyte credit) |
| pressure:rooting | root_depth_m↓ | `_substrate_suits`/`_tail_terms` (rooting excess) |
| pressure:anchoring | height_m↓, woodiness↓ | `_tail_terms` (wind-modulated need) |
| pressure:medium | — (plan-level registry data, never drifts) | `_tail_terms` |
| pressure:light | shade_tolerance↑, height_m↑ | adapter: submerged photic term; ENGINE: canopy shade pass (B6 §3) — one name, two env sides, never co-occurring |
| pressure:habitat | salinity_tolerance↓ | `_tail_terms` (freshwater habitat term) |
| pressure:glacier | — (medium-level exclusion, same ruling as pressure:medium) | `_glacier_factor` (B6 §3) |

## 4. T0001 — viable-range restoration (seed 1)

The derived climate envelope (commit c80bbb0) + unit-weight T terms had
collapsed genesis ranges (measured by tmp/k15_range_check.py with the
test_genesis `_seeded_range` idiom): 7 presets at ZERO cells
(tree.palm, succulent.cactus, rosette_mat.stonecrop,
moss_grade.sphagnum, herb_forb.grave_flower, grass_sward.sedge,
floater.duckweed), conifer 4, tussock 13, lichen 47, heath 1.

Restoration, in order (GENESIS_F and the factor product were NOT
softened):

1. **Breadth widening** (flora/derive.py): `B_T_BASE` 6.0 → 20.0,
   `P_B_BASE` 0.08 → 0.26. These move the T-distance and the B6
   moisture relief to the top of their clips — the authored optima are
   back inside the world's temperature range.
2. **Trait re-authors** (only where breadths alone could not restore;
   each documented):
   - `rosette_mat.stonecrop`, `succulent.cactus`: photosynthesis
     CAM → C3 (and the stonecrop pin in pins.toml). CAM's +10 °C
     derived optimum stacks with the succulent dials to 33-34 °C —
     unreachable on this world (summer maxima ≈ 26-28 °C). C3
     re-anchors the authored hot-dry niche (opt ≈ 24-26 °C). The
     CAM↔succulence constraint is untouched (C3 + succulence is legal).
   - `floater.duckweed`, `floating_leaf.ludwigia`:
     leaf_persistence evergreen → winter_deciduous + trigger winter —
     the turion/die-back overwintering of a temperate floater; the
     derived envelope's `T_DECID_C` drop + `B_T_DECID` breadth widen
     the winter side of the thermal band.
   - `moss_grade.sphagnum`: snow_adaptation → cushion_mat, with the
     axis's plan_scope extended to moss_grade. The 0.1 m bog moss is
     snow-blocked from its cold-bog niche without the state; a moss
     cushion IS the cushion_mat state. (The glacier exemption that
     comes with the state — sphagnum bogs at ice margins — is intended.)
3. **Result** (seed 1): 0 zero-cell presets, minimum range 63
   (sphagnum); max 5589 (lichen). Re-pinned the two
   test_genesis_partition_structure assertions to the new landscape
   (yarrow ≥ 3000 cells / k=5, seagrass ≥ 2000 / k=4).

## 5. The B6 credits — shapes and constants

All in stress_adapter.py; one-sided saturating suits, never cutoffs:

- **Fertility credits** (`MYC_CREDIT`/`NFIX_CREDIT`): the effective
  nutrient of every mix class is lifted by the acquired grade
  (arbuscular 0.12 < ecto 0.15; rhizobium/frankia 0.25,
  cyanobacterial 0.15; additive across axes). Feeds `REQ_FERTILITY`
  and the substrate_share (a symbiont-bearing plan genuinely uses more
  of a poor cell).
- **Halophyte credit** (`HALOPHYTE_CREDIT` 0.15): a salinity-tolerance
  GRADE credit, shared by the ground and water strata (the halophyte
  presets are kelp/seagrass/coral/sponge — all water plans).
- **Wetness credits** (`DRIP_WET_W` 0.4 × drip_tips; `LEAF_WET_W` 0.25
  for serrate/toothed margins): relief on the waterlogging EXCESS for
  dry plans (the documented choice: wetness relief rides the saturated
  end, not bloom-frost — frost is a cold signal, not a wetness one).
- **moisture_breadth relief** (`MB_DRY_W` 0.5 / `MB_WET_W` 0.25):
  asymmetric dry > wet relief on the water terms — the derived breadth
  is consumed, mirroring the old climate P-half.
- **waterlogging graded relief** (`WLOG_GRADED_W` 0.5): tolerance below
  the WLOG_INVERT_T cliff now gives partial credit ramping to the
  inversion — the dry dial is no longer dead.
- **Vital wiring** (sim.py): birth × (1 + 0.5 · sat(growth_rate / 1.0));
  death × (1 − 0.3 · sat(wood_density / 1.0)). Documented in sim.vital.

## 6. B6 §3 new strata

- **Snow-load** (folded into pressure:cold, land plans only):
  tol_mm = SNOW_TOL_MM[state] + height_m × 200; f = excess_suit(snow_mm,
  tol_mm, 600). Calibration (2026-08-01): a 1 m herb tolerates ~200 mm
  WE (≈ 2 m of snow) — the insulating-pack regime — while deep-snow
  cells still cost; woody plans escape by height (a 25 m tree: 5000 mm
  + state). The T distance is dormant-gated; the snow LOAD is a real
  winter cost and is not.
- **Glacier** (`pressure:glacier`): a land plan on `h_glacier_mask` is
  ~1 always (MEDIUM_VIOLATION_F, never a verdict); snow_adaptation
  != none exempts (the snow-adapted grade lives at the ice margin).
- **Canopy light** (engine-side, `_canopy_light_factors`): per land
  instance, shade(c) = clip(Σ over instances taller than the reader of
  canopy_density × N_i(c), 0, 1); f_light = clip(1 − LAYER_LIGHT_COEF[layer]
  × shade × (1 − shade_tolerance), 0, 1). The factor enters the verdict
  provenance (selection: pressure:light → shade_tolerance↑, height_m↑)
  AND the demographic F (the engine folds it into the population
  update — the cache is static, the shade is not). Deterministic:
  sorted instances, cumulative planes in sorted-height order.

## 7. Acceptance (seed 1)

1. Every authored preset seeds ≥ 50 cells (tmp/k15_range_check.py:
   min 63, zero zero-cell presets).
2. The fast tier stays green: 389 tests (k13 + k15, `-m "not slow"`).
3. The slow tier: determinism (byte-identical reruns), the
   genesis-partition structure pins (yarrow/seagrass), and the
   divergence milestone (≥ 0.02 pairwise same-lineage genes distance in
   20 rounds) hold on the re-pinned landscape.
4. B6 unit coverage: symbiosis/halophyte/wetness/moisture-breadth/
   waterlogging-grading/snow/glacier strata (test_adapter), vital
   growth_rate/wood_density (test_sim), canopy shade kill/spare/escape
   (test_engine).
5. Determinism hard rule: no uuid/random/wall-clock; draws only from
   kernel.hashrng pinned streams; float accumulation in sorted order.
