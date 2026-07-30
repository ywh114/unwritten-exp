# B3 Substrate Pass — Research Report

Date: 2026-07-30. Scope: taxonomy completeness (Task 1, pedology reference frame) +
K14/K13 consumer-feature scan (Task 2, repo reading). Read-only; nothing in the repo
was modified. Repo scanned: ywh114/unwritten-exp @ HEAD.

Headline: the 31-class draft is structurally sound but has three factual errors
(andisol values, clay retention, undifferentiated peat) and five empty domains
(permafrost, arid/tropical hardpans, limestone, sodic-vs-saline, benthic process
regimes). Net recommendation: **+10 classes, 1 split, 0 deletions → 41 classes**.
The consumer scan found all four tolerance axes shipped and driftable, the stress
consumer itself **not yet implemented**, and two substrate properties the current
4-column schema cannot express: **penetrability** and **anchoring hardness**.

---

## (a) ADD table

Each row justified by a consumer decision that no existing class can express
(d2 soft-match cannot interpolate these — they are regime breaks, not gradients).

| class | retention | rooting m | sal+ | nutrient | genesis | consumer decision that changes |
|---|---|---|---|---|---|---|
| vertisol (cracking clay) | 0.75 | 1.2 | 0 | 0.70 | phys: smectite shrink-swell, gilgai self-mulching | Seasonal deep cracks gate burrowers and break roots; high retention but poor drainage when wet — waterlogging behavior differs from generic clay. A top-3 USDA order (~2% of land) with iconic crack ecology. |
| gelisol (cryosol) | 0.60 | 0.4 | 0 | 0.30 | mixed: cryoturbation over permafrost cap | Rooting gated by active layer, not texture; saturated-but-frozen paradox drives the tundra/peat split. **Gelisol ≠ gleysol**: gleysol is redox from groundwater, gelisol requires permafrost ≤100 cm + cryoturbation. The biggest hole in the draft. |
| rendzina (calcic leptosol) | 0.30 | 0.4 | 0 | 0.55 | mixed: limestone dissolution + humus | Alkaline skeletal soil selects calcicole flora (heath's ericoid syndrome has its inverse); covers limestone uplands currently forced into scree/ranker. Absorbs chalk (soft-limestone endmember). |
| bog (ombrotrophic peat) | 0.98 | 0.3 | 0 | 0.05 | biotic: rain-fed Sphagnum dome | Rain-fed ⇒ near-zero nutrients + extreme acidity ⇒ specialists only (sundews, ericads). Matches the shipped sphagnum preset (fertility_requirement 0.15, `exp/k14_flora/content/presets/moss_grade/sphagnum.toml:60`) and gives the unused `nutrient_package="carnivore"` state its home substrate. |
| fen (minerotrophic peat) — *rename of old "peat"* | 0.92 | 0.5 | 0 | 0.45 | biotic: groundwater-fed sedge peat | Mineral-fed fens carry sedges/reeds/mesotrophic fauna. Fen-vs-bog is THE classic peatland axis; the old single "peat" row (nutrient 0.20) averaged bog 0.05 and fen 0.45 into a soil that exists nowhere. |
| solonetz (sodic soil) | 0.35 | 0.5 | 0.45 | 0.25 | phys: natric horizon, Na-dispersed clay | Sodic ≠ saline: dispersed clay blocks infiltration and rooting — hostile without a salt crust. Occupies steppe terraces *above* solonchaks; the sal+ axis alone cannot express it. |
| laterite cuirasse (plinthosol) | 0.10 | 0.2 | 0 | 0.10 | phys: plinthite hardens irreversibly on exposure | Iron hardpan gates rooting/burrowing to near-zero across vast tropical peneplains — a real d2-visible break against soft deep ferralsol neighbors. |
| caliche (petrocalcic hardpan) | 0.12 | 0.25 | 0 | 0.20 | phys: pedogenic CaCO₃, semi-arid | The dominant hard substrate of semi-arid belts: roots stop at the pan, water perches above it. Distinct from reg (winnowed surface lag, no pan). |
| tidal flat | 1.0 | 0.15 | 0.5 | 0.55 | phys+biotic: tide-sorted mud/sand, brackish | Intertidal feeding/spawning habitat (waders, flatfish nurseries); sal+ 0.5 encodes the estuarine gradient that marine mud (full sea) and river beds (0) cannot. Globally extensive at 4 km scale. |
| cold seep | 1.0 | 0.3 | sea | 0.85 | biotic: methane chemosynthesis + authigenic carbonate | Stable, passive-margin, methane-fed, carbonate-crusted — a different energy substrate than vent crust (hot sulfide, ephemeral). Same nutrient value would erase a real distinction consumers (chemosynthetic clades, ley themes) can read. |
| abyssal clay (red clay) | 1.0 | 0.2 | sea | 0.10 | phys: pelagic clay, mm/kyr accumulation | Corg 0.1–0.3% vs marine mud's marine-snow richness ⇒ food-starved deep-sea fauna gating; depth-band filler that marine mud would otherwise wrongly enrich. |

### Rejected candidates (L1 detail, not class)

| candidate | verdict | one-liner |
|---|---|---|
| ultisol/acrisol (own row) | reject → extend brown earth note | nutrient interpolates between brown earth 0.65 and ferralsol 0.15 via d2; a third row fragments the temperate class |
| takyir / playa crust | reject | polygon-crust micromorphology inside solonchak/clay cells, sub-cell |
| palsa / permafrost mound | reject | 7–30 m ice-cored peat mounds — three orders below 4 km; gelisol owns permafrost |
| drumlin | reject | landform, not material — it's till; belongs to the relief layer |
| karst pavement | reject | exposed limestone = bedrock outcrop; soil pockets = rendzina; grykes are meter-scale |
| tufa / travertine | reject | point spring deposits, m-scale |
| beach ridges | reject | relict coastal sand + elevation; terrain layer |
| fjord anoxic sediment | reject | marine mud + enclosure/depth modifier |
| seagrass-meadow sediment | reject | biotope tag on marine sand; productivity layer handles meadows |
| glacial-marine diamicton | reject | till on land; iceberg-rafted mix within marine mud/sand offshore |
| brine pool | reject | <1 km point features |
| marine gravel/cobble bed | reject | rocky bottom absorbs high-energy coarse habitat at 4 km; maerl/gravel lags are sub-km |

---

## (b) MERGE / RENAME list for the 31

| action | target | reason |
|---|---|---|
| RENAME | volcanic ash → **andisol (volcanic ash soil)** | it IS an andisol; name it so biome-bias rules and the field guide can cite the order (values also corrected, §c) |
| RENAME | salt pan → **solonchak (salt flat)** | aligns with the WRB salic-horizon group; covers the endorheic pan |
| SPLIT | peat → **fen** (keeps old row's role) + **bog** (new) | fen/bog nutrient split is the defining peatland axis; see §a |
| MERGE | sabkha → into solonchak | coastal vs endorheic evaporites share property vectors (sal 0.8–1.0, barren crust); encode coast-adjacency in the generator, not as a class |
| MERGE | chalk → into rendzina | chalk is the soft-limestone endmember of rendzic parent material; identical vectors |
| MERGE | gypsum dunes → dune sand + gypsum-parent flag | real gypsum dunefields are a planetary anomaly (White Sands ~700 km² is the largest on Earth) fed by an adjacent playa; too rare for a class, great as L1 tint |
| KEEP | kelp-bed rock inside rocky bottom | already covered ("kelp rock" is in its genesis note) |
| KEEP | dune sand / sand sheet / reg as three rows | vectors are close and d2 will blur them, but the most-arid-only spatial gate on dune sand does the separation work; they earn their cells visually |

---

## (c) Property-value corrections to the 31

| row | field | old → new | pedological justification |
|---|---|---|---|
| clay | retention | 0.80 → 0.65 | clay holds high TOTAL water but at a high wilting point — plant-available water capacity peaks in silt/loam, not clay; 0.80 made clay beat alluvium |
| andisol (was volcanic ash) | retention | 0.50 → 0.80 | allophane/imogolite give exceptional water-holding at low bulk density |
| andisol (was volcanic ash) | nutrient | 0.95 → 0.70 | andic definition requires >85% P-retention — allophane fixes phosphate hard; total stocks high, AVAILABLE nutrients capped |
| mollisol | rooting | 1.8 → 2.2 | chernozem mollic epipedons run 1 m+ and prairie roots exceed 2 m; alluvium should not out-root the deepest grassland soil |
| reg / desert pavement | nutrient | 0.25 → 0.15 | lag pavement is winnowed and biologically starved; 0.25 (above coastal sand!) was generous, and lowering separates reg from scree in d2 space |
| ferralsol | nutrient | keep 0.15 | correct: oxic horizons are kaolinitic, CEC-clay <16 cmol/kg, strong P-fixation; most nutrients live in standing biomass, not soil — do NOT "fix" this |
| vent crust | genesis note | → "phys+biotic: hot sulfide chemosynthesis" | symmetry with cold seep; flags chemosynthetic energy for consumers |
| dune/sheet/reg, alluvium, loess, silt, till, outwash, coastal sand, podzol, brown earth, gleysol, mangrove mud, ranker, marine/lake/river rows | — | keep | orderings along each axis are defensible; consumers reading top-3 d2 soft-match are robust to ±0.1 |

The three biggest factual errors in the draft: the andisol values (retention AND
nutrient both wrong, in opposite directions), clay retention 0.80 (confuses total
with plant-available water), and the undifferentiated "peat".

---

## (d) Consumer-features inventory — what the pass MUST serve

### d.0 Status of the consumer (important)

The stress/suitability consumer (`exp/k14_flora/world/stress.py`, stage P7) is
**not yet implemented** — `exp/k14_flora/world/` contains only
`__init__.py, datapack.py, derived.py, test_derived.py`; CONTRACTS.md:30 lists
stress as a planned stage. The build plan
(`docs/spec-notes/2026-07-29-k14-flora-build-plan.md:190-193`) fixes its intended
inputs: *"24-dim month-vector distance + flora extension axes (salinity band,
HAND, growing season, fertility from D0)"*. What exists today:
`derive.effective_climate()` returns exactly 10 keys
(`exp/k14_flora/derive.py:161-171`) — temp/moisture opt+breadth (from preset
`[niche]` metadata) + drought/salinity/waterlogging/fertility/growing_season/shade
tolerances. **No substrate input in that signature yet** — the substrate pass
lands on a greenfield consumer.

### d.1 Species axes available for suitability (exact names + ranges)

All four tolerance axes are **authored traits** (steady tier, `mutation="ratio"`,
they drift), each with `consumers=["stress"]`. None are calculated; the
calculated-axis registry (`derive.py:25-29`) contains no tolerance axis.

| axis | range | defined at | extreme presets (evidence) |
|---|---|---|---|
| `drought_tolerance` | [0.0, 1.0] | `exp/k14_flora/content/axes_core.toml:694-704` | cactus 0.95 (succulent/cactus.toml:60); coral/seagrass/sponge 0.0 |
| `salinity_tolerance` | [0.0, 1.0] | axes_core.toml:705-715 | kelp/coral 0.95 (kelp.toml:58); terrestrial ≈0.05–0.1 |
| `waterlogging_tolerance` | [0.0, 1.0] | axes_core.toml:716-726 (comment: "HAND band") | all aquatics 1.0; reed 0.9, sphagnum 0.9; cactus 0.05 |
| `fertility_requirement` | [0.0, 1.0] | axes_core.toml:727-737 | duckweed/agaric 0.6; lichen 0.1, sphagnum 0.15, heath/cactus 0.2 |
| `growing_season_req` | [0.0, 12.0] mo | axes_core.toml:738-748 | coral 12.0; ice_crown 1.5 |
| `root_depth_m` | [0.01, 30.0] m | axes_core.toml:283-292 (`consumers=["stress"]`) | oak 4.0 (oak.toml:36), conifer 3.0; aquatics/mosses 0.01 — **the rooting-depth gate input** |
| `root_type` | enum {tap, fibrous, adventitious, aerial, holdfast, none} | axes_core.toml:272-282 | holdfast: kelp (kelp.toml:23), barrel_sponge; none: coral, fungi, mosses, lichen |
| `root_special` | enum {none, pneumatophores, stilt, buttress, knee, haustoria} | axes_core.toml:294-303 | all presets "none"; reachable via drift + constraint gates |
| `storage_organ` | enum {none, tuber, bulb, corm, rhizome, succulent_tissue, lignotuber, endosperm} | axes_core.toml:509-518; geophyte set `derive.py:34` | rhizome: reed/sedge/seagrass/waterlily; tuber: carrot |
| `layer` | enum incl. `aquatic_surface`, `aquatic_benthic` | axes_core.toml:85-94; `AQUATIC_LAYERS` at `derive.py:35` | floaters vs benthic aquatics |
| `nutrient_package` | enum {none, xerophyte, hydrophyte, halophyte, carnivore} | axes_core.toml:683-691 | halophyte: kelp/coral/seagrass; **carnivore: zero preset users** |
| `mycorrhizal` / `n_fixation` / `saprotrophy` / `parasitism` / `mycoheterotrophy` | enums | axes_core.toml:306-324, 653-681 | heath ericoid (heath.toml:37); legume rhizobium; agaric litter, bracket white_rot; grave_flower mycoheterotroph |
| `engineer_impact` | [0.0, 1.0] ("peat moss, kelp forest, reef builders") | axes_core.toml:760-768 | coral 0.95, sphagnum 0.9, kelp 0.9 |
| `[niche]` metadata: temp_opt/breadth, moisture_opt/breadth | moisture 0..1 | per-preset; content-only baseline (CONTRACTS.md:13-14; derive.py:160-165) | cactus moisture_opt 0.2; aquatics 0.95; ice_crown temp_opt 2°C |

Existing constraint couplings the substrate pass must respect
(`exp/k14_flora/content/constraints.toml`): `pneumatophores_waterlogging`
requires waterlogging ≥0.7 (:73-79, comment "the waterlogged-anaerobic answer");
`buttress_emergent` requires height ≥20 m AND `root_depth_m` ≤2.0 (:81-88) —
an existing shallow-soil/anchoring coupling; `aquatic_benthic_needs_tolerance`
(:136-144); `c4_warm_open` drought ≥0.4 (:23-26); carnivory gates
`nutrient_carnivore_plans`/`trap_carnivory` (:104-120). Epiphyte accommodation
explicitly deferred (:15).

### d.2 Preset → substrate needs (what the class table must distinguish)

| preset | implied substrate | evidence (under `exp/k14_flora/content/presets/`) |
|---|---|---|
| kelp | hard marine attachment (rock) — holdfast, no penetration | root_type holdfast kelp.toml:23, depth 0.01 :24 |
| seagrass | submerged shallow marine SEDIMENT (sand/mud) — rhizome-rooted | fibrous, depth 0.2 (seagrass.toml:23-24, 43) |
| branching_coral | hard benthic surface, full salinity, year-round warmth | root none :23, sal 0.95 :58, season 12.0 :61, engineer 0.95 :62 |
| barrel_sponge | hard benthic attachment | holdfast barrel_sponge.toml:23 |
| duckweed | still/slow fresh water surface, no substrate contact, eutrophic | layer aquatic_surface :17, fertility 0.6 :61 |
| waterlily | shallow freshwater MUD (rooted rhizome 0.5 m) | depth 0.5 waterlily.toml:24, rhizome :43 |
| reed / sedge | freshwater marsh/fen mud, mildly brackish | waterlog 0.9/0.85, sal 0.3 (reed.toml:59-60, sedge.toml:61-62) |
| sphagnum | acidic bog peat, nutrient-poor | "peat-builder archetype" :1, fertility 0.15 :60, engineer 0.9 :62 |
| heath | acid heath soil | "acid-heath evergreen" :1, mycorrhizal ericoid :37, fertility 0.2 :74 |
| cactus | arid sand/rock, never waterlogged | drought 0.95, waterlog 0.05 (cactus.toml:60-62) |
| stonecrop / lichen.crust | thin rock-mat soil / bare rock | "rock-mat" stonecrop.toml:1, depth 0.05; "crustose rock" crust.toml:1, fertility 0.1 :61 |
| ice_crown | arctic-alpine bare ground, short season | temp_opt 2°C :69, season 1.5 :64; pin "Saxifraga glacialis" pins.toml:202 |
| willow | riparian/wet soil | waterlog 0.8 willow.toml:73 |
| oak/conifer | deep rooted soil | depth 4.0/3.0 (oak.toml:36, conifer.toml:35) |
| agaric / bracket | litter / dead wood — ORGANIC substrates, not mineral soil | saprotrophy litter/white_rot (agaric.toml:58, bracket.toml:56) |
| grave_flower | host fungal network (biotic substrate) | mycoheterotrophy yes grave_flower.toml:58 |

Note the hard-vs-soft seabed contrast (kelp/coral/sponge vs seagrass) is
exactly what rocky bottom vs marine sand/mud must resolve — and nothing in the
current 4-column schema says "hard".

### d.3 World inputs already available (D0, `exp/k14_flora/world/derived.py`)

Read today: deposition/catchment accumulation `h_accumulation` (:363, 382;
`ACC_REF=2000` :69 — the de-ranked old soil_fertility core, :347-350), HAND
waterlogging proxy (:364; `HAND_REF_M=5` :70), `river_speed` product
(:221-231, 455-456), vent field from `p_fault_conv`/`p_fault_dist` (:396-415;
product :471, point lists `vents`/`hot_springs` :472-473), upwelling `r_rise_m`
(:300-301), river-plume `h_discharge`/`h_flow_dir`/`h_river_mask` (:302-314),
wind mixing (:318-321), ice/insolation (:270-281), aquatic class priors incl.
salt lake 0.10 / inland sea 0.40 / delta 0.70 (:99-122), biome priors incl.
rock 0.02 / ice 0.00 (:78-96), lake depth (:380-383), growing season
(:389-393, `GROW_T_C=5` :125), currents (:331-337).

Persisted by K11 (`exp/k11_worldgen/persist.py:87-88`) but NOT yet read by K14:
**`h_salinity`** (g/kg per WATER cell — ocean 35, estuary mixing band, endorheic
lakes to ~220; hydrology.py:756, 952, 1205) — exactly the field the salinity
stress term needs, but it covers water cells only (rivers forced 0 except the
tidal band, hydrology.py:794, 856): **no terrestrial soil-salinity field exists**;
glacier fields `h_glacier_mask/flux/melt/thick_m` (hydrology.py:383-390);
river width `h_width` (:947).

### d.4 Magic classes (ley operators) and their substrate implications

| operator | spec ref | substrate implication |
|---|---|---|
| `LEY-FED` (flora) | `specs/unwritten-flora-engine-rfc.md:97` | "nutrient axes inert; range-locked, **substrate-free**" — needs a per-lineage exemption path from nutrient AND substrate presence, not a class |
| `LEY-FED`/`MANA-FILTER` (fauna) | `specs/unwritten-fauna-engine-rfc.md:105` | same exemption for fauna feeding |
| `PHASE-ROOT` (flora) | flora-rfc.md:100; slot map `specs/biosphere-vocabulary-proposal.md:383` | "roots penetrate any substrate" — bypasses rooting-depth gating and impenetrability per-lineage |
| `LAVA-ADAPT`/`SAND-SWIM`/`ICE-PHASE` (fauna) | fauna-rfc.md:107; permission list vocabulary:368, 379 | "medium extension… heat/substrate tolerance unbounded" — **substrate classes double as locomotor media**; lava, sand, ice must exist as media |
| `SAND-SWIM` regular anchor | vocabulary:109 | non-ley sand-swimmers need a loose-sand class as habitat (penetrability, not retention) |
| `BUOYANT`, `REDUCE [slot]` (flora) | flora-rfc.md:89-90 | substrate-free via vestigial/deleted root slot — exemption mechanism is slot absence |
| `TERRESTRIALIZE`/`AQUATIZE` | flora-rfc.md:91-92 | crosses the soil/seabed boundary — substrate must not hard-block medium-flipped lineages |
| vent field → `LAVA-ADAPT` themes | flora-rfc.md:33 | the heat/substrate signal already has its own D0 product (B2 keeps it separate: b2:147-148) — this is a join, not a column |

### d.5 Fauna (K13) substrate needs

| axis/feature | range/states | file:line | implication |
|---|---|---|---|
| `vertical_stratum` | {fossorial, ground, …, benthic, demersal, pelagic} | `exp/k13_treegen/content/axes_core.toml:219-228` | fossorial needs penetrable sediment; benthic/demersal needs a bottom type — **neither gated by any substrate property yet** |
| stratum redraw gating | base strata always legal | `exp/k13_treegen/forces.py:239-248, 265-286` | fossorial is currently universally available; the substrate pass is the first thing that could make it illegal somewhere |
| fossorial locomotor + digging morphometrics | brachial <80, olecranon 40–60 | plans.toml:25; axes_morphometrics.toml:32, 62-68; mole.toml:13-17, 87; B1 `specs/biosphere-addendum-b1-morphometrics.md:52` | body supports digging; substrate must offer a diggable medium |
| osmoreg generics | {standard, salt_glands, euryhaline} | plans.toml:44, 78, 118 | maps onto the salinity column; euryhaline = full salinity-band exemption |
| K13 `[niche]` + `effective_climate()` | temp + moisture only | `exp/k13_treegen/derive.py:136-178` | **moisture is the ONLY water axis in K13 fauna; no salinity or substrate axis exists yet** |
| `Condition.env` rounds hook | dict of world vars incl. "salinity" | forces.py:101-111; couplings.py:236-239; docs/m6-couplings.md:32 | salinity is a named env var the rounds layer will supply — the substrate salinity field can feed this channel directly |

Provisions boundary: flora provisions (mast/graze/browse/nectar/shelter) are
computed from species mix + trait maps (flora-rfc.md:65; derive.py:9-11, 26-28,
37-45) with **no substrate read**; fauna consumes provisions via niche extension
(fauna-rfc.md:45, 66; vocabulary:238). Substrate reaches fauna only indirectly:
substrate → flora suitability → cover/provisions → fauna.

Negative results (searched, absent): no spawning-substrate/gravel-bed axis in
K13 or the RFCs (the draft's "river gravel bed — spawning" note has **no
consumer yet**); no shell/sand-burrow axes; no bottom-type distinction for
benthic fauna; **pH is not mentioned anywhere** in specs or K13/K14.

### d.6 Productivity boundary (B2 — do not relitigate)

Productivity = carrying capacity, one absolute-scaled number per cell
(`specs/biosphere-addendum-b2-productivity-scale.md:21-24`). Substrate is a
separate derivation pass with its own class map and persisted d2 distances
(:25-30, :44-46). The old `soil_fertility` field is REMOVED — it had no
consumers; `fertility_requirement` is a species trait, not a field consumer
(:78-83); its deposition logic survives only as the abiotic productivity bonus
(:31-34, :67-69). Volcanic ash/vents are a SUBSTRATE signal, not a productivity
input (:147-148).

### d.7 Features needing a substrate PROPERTY beyond retention/rooting/salinity/nutrient

1. **Penetrability / excavatability** (grain size, compaction) — fossorial fauna
   (k13 axes_core.toml:224-228, plans.toml:25), digging morphometrics
   (axes_morphometrics.toml:32, 68), sand-swimming (vocabulary:109,
   fauna-rfc.md:107). No proposed column covers this. *Recommendation: derivable
   per-class as metadata from genesis (like the genesis note), not a new float —
   the class IS the grain-size encoding.*
2. **Anchoring hardness (rock vs sediment)** — holdfast root_type
   (k14 axes_core.toml:277; kelp.toml:23, barrel_sponge.toml:23), crustose
   lichen/stonecrop "rock" archetypes, coral reef-building, PHASE-ROOT's cliffs
   and LEY-FED's "bare rock" (flora-rfc.md:97, 100). Rooting-depth alone can't
   express "no soil at all." *Recommendation: same — a per-class hardness flag
   (metadata), which the proposed hardpan classes (caliche, laterite) then get
   for free.*
3. **Anoxia** — spec language is oxygen, not water: "waterlogged-anaerobic"
   (vocabulary:340; constraints.toml:73), hydrophyte aerenchyma (vocabulary:324),
   fauna hypoxia tolerance (vocabulary:238). Retention≈1 can proxy saturation;
   flag the proxy as intentional.
4. **Heat / ice as medium** — LAVA-ADAPT heat "unbounded" (fauna-rfc.md:107),
   ICE-PHASE (ibid.). Vent field and glacier fields are D0/K11 products — join
   at consumption time, don't add columns.
5. **Terrestrial soil salinity** — `salinity_tolerance` is land-relevant but
   K11 `h_salinity` covers water cells only; the substrate pass must DERIVE soil
   salinity (endorheic basins, coastal spray, arid evaporation) — that's what
   the sal+ column is for; note it has no upstream field to read.
6. **pH** — heath "acid-heath" (heath.toml:1, ericoid :37), sphagnum bog,
   rendzina's calcicole flora all imply pH, but **no spec anywhere requires it**.
   The fen/bog and rendzina classes smuggle pH in as class identity — the right
   call at 4 km; do not add a pH column.
7. **Organic substrates** (litter, dead wood, dung, peat stock) — saprotrophy
   states (axes_core.toml:678; agaric.toml:58) and sphagnum peat-building
   imply organic media; out of scope for a physical substrate pass — belongs to
   the later habitat pass.

---

## (e) Surprises and conceptual gaps

1. **The consumer doesn't exist yet.** `world/stress.py` is unimplemented
   (planned P7, CONTRACTS.md:30). The substrate pass is not slotting into a
   running machine — it is co-designing the consumer's input schema. That is
   license to get the class/property design right now, and it means nothing
   breaks if columns change.
2. **Name collision: `substrate_ok()` is not about substrate.** In
   `exp/k13_treegen/forces.py:251-262` and `exp/k14_flora/CONTRACTS.md:19`,
   "substrate" means ANATOMICAL substrate (a mane needs fur). The physical
   substrate pass should pick a distinct internal name (e.g. `ground`,
   `sediment`) or every future grep will be polluted.
3. **Top-2 vs top-3.** The brief says consumers read top-3 d2 soft-match; B2
   persists top-2 d2 distances for the future substrate map
   (b2-productivity-scale.md:25-30, :44-46). Reconcile before implementing —
   with 41 classes, top-2 vs top-3 changes blend behavior at class boundaries.
4. **K13 fauna has no salinity/substrate axis — only moisture**
   (derive.py:136-178). The fauna RFC's salinity-band/osmoregulation vocabulary
   (vocabulary:157, 238) and the `Condition.env` "salinity" hook
   (forces.py:101-111) are landing points with no axis behind them. Expect a
   fauna-axis gap independent of the substrate pass.
5. **Benthic/demersal strata have no content to bind to.** K13 ships only
   tetrapod/winged_biped/hexapod plans (plans.toml:2); the marine rows of the
   class table currently serve only K14 presets (kelp, coral, seagrass, sponge).
   The benthic substrate design is ahead of its fauna consumers — fine, but
   don't over-fit marine classes to fauna needs that don't exist yet.
6. **The draft's "river gravel bed — spawning" note has no consumer.** No
   spawning-substrate axis exists anywhere (searched K13 + both RFCs). Keep the
   class (flow-sorted beds are real and d2-visible), but the justification
   should be flow-sorting, not spawning.
7. **Registry states with zero preset users anticipate the pass.**
   `root_type="aerial"` (epiphytes — explicitly deferred, constraints.toml:15),
   `nutrient_package="carnivore"`, `root_special="haustoria"`,
   `parasitism=hemi/holo`, `storage_organ="lignotuber"` are all authored but
   unused. Bog (carnivory's classic home) and rendzina are the two ADDs that
   give these states somewhere to live.
8. **Conceptual gap: the 4 floats are all continuous, but several real
   distinctions are categorical** (hard vs soft, penetrable vs not, saline vs
   sodic, mineral vs organic). The schema absorbs them as class identity rather
   than columns — which is correct at 41 classes, but it means the CLASS LIST is
   the real schema. Guard it: every future class proposal must name the consumer
   decision it changes, exactly as this report's ADDs do.
9. **Soil salinity has no upstream field** (d.7.5): the sal+ column must be
   derived inside the pass from aridity/endorheism/coast adjacency. That's the
   one column with no K11/D0 input — budget derivation logic for it.
10. **Calibration humility.** Exact 0–1 floats are opinionated by design; the
    pedologically defensible content is the ORDERING of classes along each axis.
    Consumers reading d2 soft-match are robust to ±0.1 — spend review effort on
    ordering and class membership, not the second decimal.
