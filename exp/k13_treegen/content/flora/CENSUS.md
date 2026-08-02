# K14 flora census — 0012 Task A (two-track, <200 lineages)

**Source of truth:** `tmp/0012-curate-initial-radiation.md` (the ticket;
owner rulings 1–8), `tmp/flora-composition-report.md` §1–§4 (research
foundation), `specs/unwritten-flora-engine-rfc.md` §5, the biosphere
vocabulary proposal. **Authority for loading:** `content/flora/pins.toml`
+ `presets/` + `content.py` + `backbone.py` — this doc explains intent,
it does not override the files.

**State (2026-08-02):** 85 authored pins — **51 individual-track + 34
bundle-track**. Built tree species (the lineage count genesis seeds):
**179 / 190 / 190** on seeds 1/2/3 — all < 200. k13 fast tier green
(275 tests), metrics gate clean on seeds 1–3.

## 1. The two tracks

- **Individual-track** (51 pins): habitat-defining physics — canopy /
  sward / holdfast / mat / peat via `layer` + `engineer_impact`, high
  expected cover (0012 ruling 4: "the oaks, other trees, swards,
  bushes, kelps"). These lineages mutate, adapt, and cladogenize
  normally (0010). Genus-rank pins radiate 1–2 species; a few
  landmarks are species-rank. No `bundle` flag.
- **Bundle-track** (34 pins): everything else rides as ARCHETYPE
  BUNDLES — authored superset generalists cut by REGION × PHYSIOLOGY
  (ruling 6): one (plan, layer), wider tolerance breadths, central
  optima in the biome core, archetypal enums (categorical, never
  averaged), generous `propagule_count` (a guild's seed rain, ruling
  8's working direction). Each is marked `bundle = true` +
  `covered_region = "..."` (both plain data fields; `content.py`
  exposes them via `is_bundle()` / `bundle_region()`; the engine reads
  neither). A bundle is ONE sim lineage, frozen post-Task-B (Δg = 0,
  no select/mutate/divide) and differentiated post-sim by 0027 into
  generated daughters minted as sibling species under its genus.
- **Disjoint partition:** an individual-track species is never also a
  bundle member — the two tracks' binomial genera are disjoint (no oak
  inside a woodland bundle). Enforced by `test_census.py`.
- **Clade spread:** bundles whose `covered_region` names the same
  biome window are spread across binomial genera/families — no clade
  clones (ruling: "a variety of families and genera that would fit
  the bill"). See §4.

## 2. Prune list — what the ad-hoc census dropped, and why

The old census was 35 presets / 24 pins / ~150 species, with the
sister-cluster pathology (genus-pin radiations 3–6 each minting near-
identical sibling species, e.g. five pines, six oaks, six brambles,
five mushrooms — the 0012 opening complaint). The re-curation:

| Dropped | Why |
|---|---|
| yarrow, wild carrot, sword-iris, thread-leaf chive, thistle pins | not habitat-definers — ordinary meadow/forb design space now inside the `temperate-flowers` / `mediterranean-forbs` / `wet-meadow-herbs` bundles. Their presets were repurposed (`herb_forb.asterid` keeps the composite-head grade) or deleted. |
| grave-flower preset (kept as a species pin) | the plant survives as a RARE individual-track archetype (`Monotropa uniflora`, mycoheterotroph) — the RFC §6 "one rarity" pin; the old separate order merged into `herb_forb.forb`. |
| tree.birch preset (merged into tree.oak) | Fagaceae+Betulaceae both ride the Fagales order; `birches`/`alders`/`beeches` are separate genus pins under it. Order-rank taxonomy now matches the clade, not the growth habit. |
| fungus.bracket, moss_grade.cushion, floating_leaf.ludwigia, rosette_mat.ice_crown presets (merged) | archetype grades folded into the surviving order of the same plan (`fungus.agaric`, `moss_grade.sphagnum`, `floating_leaf.waterlily`, `rosette_mat.stonecrop`); the pins/axes that mattered moved onto the survivor. |
| radiation 3–6 genus pins → radiation 0–2 | the sister-cluster pathology itself: oaks now = 2 pinned species + 1–2 relatives instead of 6 near-clones; every other genus radiates 1–2. |
| crowberries (Empetrum), figs (Ficus) pins | count trim; tundra already has Vaccinium / Betula nana / Carex / Sphagnum + three bundles; tropical moist keeps Shorea + palms as canopy anchors. |
| bamboo pin (order kept) | the order survives with its generated background species — bamboo is a token archetype, not a census lineage. |
| poplar, maple, fir, arbutus, hazel (never authored) | dropped at design time: temperate/boreal canopy already has oak+beech+birch+spruce+pine+larch; med is basin-only per ruling (Cistaceae/Lamiaceae/Oleaceae/evergreen Fagaceae — Arbutus/Ericaceae excluded by the ruling's family list). |
| ludwigia / sword-plant pins | not habitat-definers; marsh marginals now `marsh-marginals` bundle (Sagittaria). |

**Why the survivors keep their nodes:** every retained lineage carries
habitat-defining physics — a canopy/sward/holdfast/peat/mat former with
authored `engineer_impact` (oak 0.6, kelp 0.9, sphagnum 0.9, bracken
0.5, reed 0.6, tussock 0.4, marram 0.7, mangrove 0.8…) or an explicit
substrate anchor (Saxifraga/Sedum/lichen → scree+bedrock; Salicornia/
Salsola/Spartina → saline; Sphagnum → bog). The rest rides bundles.

## 3. Individual track — picks by biome (report §4 table)

Operational boundary per pick: canopy/sward/holdfast/mat physics +
high expected cover. ~2–4 habitat-forming genera per biome.

| Biome | Individual-track picks (genus — family) | Why (one line) |
|---|---|---|
| Tropical moist | Shorea (Dipterocarpaceae), Cocos palm (Arecaceae) | emergent canopy + subcanopy monocot, buttress/stilt physics |
| Tropical dry | Ceiba (Malvaceae), Acacia (Fabaceae) | drought-deciduous canopy; legume savanna tree |
| Tropical conifer | Pinus (Pinaceae) | N-hemisphere pine/pine-oak expression (ruling #3; `pines` envelope is warm-tolerant) |
| Tropical grassland (savanna) | Andropogon (Poaceae) + Acacia | sward-former + scattered Fabaceae tree (the savanna ruling) |
| Mangrove (tropical coast) | Rhizophora (Rhizophoraceae), Avicennia (Acanthaceae) | stilt-root / pneumatophore tidal forest, engineer 0.8 |
| Temperate broadleaf | Quercus (Fagaceae), Fagus, Betula, Alnus | oak/beech/birch canopy + alder riparian; the Fagales order |
| Temperate conifer | Pinus, Picea, Larix (Pinaceae) | pine/spruce/larch conifer canopy |
| Boreal taiga | Picea, Larix, Betula (hardwood pioneer) | taiga canopy trio |
| Temperate grassland | Festuca (Poaceae) | sward-former |
| Flooded grassland | Phragmites (Poaceae), Typha (Typhaceae), Carex (Cyperaceae) | reed belt, bulrush, sedge — the emergent grade |
| Montane grassland | Festuca + alpine-grasses bundle (Calamagrostis) | alpine-meadow expression (ruling #2) |
| Tundra | Vaccinium, Calluna, Empetrum-dropped (Ericaceae), Betula nana (Betulaceae), Carex, Sphagnum | dwarf-shrub + tussock + moss mat |
| Mediterranean scrub | Quercus ilex (evergreen Fagaceae), Cistus (Cistaceae), Salvia (Lamiaceae), Phillyrea (Oleaceae) | basin/maquis-only per ruling #1; no chaparral/fynbos |
| Desert (hot) | Carnegiea (Cactaceae), Agave (Asparagaceae), Larrea (Zygophyllaceae), Prosopis (Fabaceae) | columnar succulent, rosette monocarp, creosote shrub, phreatophyte tree |
| Desert (cold) | Artemisia (Asteraceae), Salsola (Amaranthaceae) | sagebrush + saltbush xeric shrubs |
| Riparian (alluvium) | Salix (Salicaceae), Alnus (Betulaceae) | willow/alder river-corridor canopy |
| Bog/fen | Sphagnum (Sphagnaceae) | peat-former, engineer 0.9 — the bog anchor |
| Salt marsh / saline | Spartina (Poaceae), Salicornia (Amaranthaceae), Salsola | cordgrass sward, samphire, saltbush |
| Scree / bedrock | Saxifraga (Saxifragaceae), Sedum (Crassulaceae), Lecanora lichen, Silene cushion | chasmophytes + first colonist + glacier-margin form |
| Freshwater | Nymphaea (Nymphaeaceae), Phragmites, Typha, Carex | floating-leaf + emergent + littoral |
| Marine | Macrocystis (Laminariales), Zostera (Zosteraceae) | kelp-forest canopy + seagrass meadow |
| Forest floor (rare) | Monotropa (Ericaceae) | mycoheterotroph rarity pin |
| Tokens | Pteridium, Sphagnum-moss, Agaricus, Trametes, Acropora, Xestospongia | mat-former + ecological tokens |

## 4. Bundle track — covered region + clade spread

All 34 bundles are species-rank pins under their authored binomial
genus (daughters mint as siblings — coverage floor 4). Envelope
construction: tolerance breadth wider than any single species, optima
central to the biome core, enums archetypal (one dispersal idiom, one
leaf/pigment idiom per bundle — never an average), `propagule_count`
10⁴–10⁶ (guild seed rain).

| Bundle | Genus — family | (plan, layer) | covered_region (biome window) |
|---|---|---|---|
| temperate-flowers | Senecio — Asteraceae | (herb_forb, sward) | temperate broadleaf + grassland understory |
| alpine-meadow-flowers | Senecio — Asteraceae | (herb_forb, sward) | montane grassland (alpine meadow) |
| temperate-woodland-herbs | Convallaria — Asparagaceae | (herb_forb, ground) | temperate broadleaf forest floor |
| temperate-forest-shrubs | Rosa — Rosaceae | (shrub, shrub) | temperate woodland/scrub margins |
| temperate-forest-ferns | Dryopteris — Dryopteridaceae | (fern_grade, ground) | temperate forest floor |
| wet-meadow-herbs | Ranunculus — Ranunculaceae | (herb_forb, sward) | riparian alluvium + wet meadows |
| floodplain-grasses | Echinochloa — Poaceae | (grass_sward, sward) | flooded-grassland margins + alluvium |
| marsh-marginals | Sagittaria — Alismataceae | (floating_leaf, aquatic_surface) | freshwater marsh/lake margins |
| free-floating-aquatics | Lemna — Lemnaceae | (floater, aquatic_surface) | lentic freshwater surface |
| freshwater-submerged-meadows | Potamogeton — Potamogetonaceae | (runner_meadow, aquatic_benthic) | freshwater lakes/rivers |
| flooded-grasses | Cyperus — Cyperaceae | (grass_sward, sward) | tropical flooded grassland |
| steppe-herbs | Astragalus — Fabaceae | (herb_forb, sward) | temperate steppe/prairie |
| alpine-grasses | Calamagrostis — Poaceae | (grass_sward, sward) | montane grassland (alpine meadow) |
| alpine-cushions | Arenaria — Caryophyllaceae | (rosette_mat, ground) | alpine fell-field + glacier-margin rubble |
| boreal-forest-herbs | Pyrola — Ericaceae | (herb_forb, ground) | boreal taiga forest floor |
| taiga-moss-mats | Pleurozium — Hylocomiaceae | (moss_grade, ground) | boreal taiga + tundra ground |
| tundra-herbs | Draba — Brassicaceae | (herb_forb, ground) | tundra + fell-field + dry scree |
| tundra-lichen-mats | Cladonia — Cladoniaceae | (lichen, ground) | tundra + taiga ground |
| bog-heath | Andromeda — Ericaceae | (shrub, ground) | bog/fen peat + heath |
| fen-sedges | Eriophorum — Cyperaceae | (grass_sward, sward) | bog/fen tussocks |
| bog-carnivores | Drosera — Droseraceae | (rosette_mat, ground) | bog/fen + wet heath |
| mediterranean-forbs | Erysimum — Brassicaceae | (herb_forb, sward) | med basin (maquis/garrigue) understory |
| desert-annuals | Camissonia — Onagraceae | (herb_forb, ground) | hot desert ephemeral washes |
| cold-desert-grasses | Oryzopsis — Poaceae | (grass_sward, sward) | cold desert + steppe margin |
| coastal-herbs | Limonium — Plumbaginaceae | (herb_forb, ground) | salt marsh + tidal flat |
| tropical-forest-floor-herbs | Zingiber — Zingiberaceae | (herb_forb, ground) | tropical moist forest floor |
| tropical-understory-shrubs | Psychotria — Rubiaceae | (shrub, subcanopy) | tropical moist understory |
| tropical-vines | Ipomoea — Convolvulaceae | (herb_forb, sward) | tropical forest edges/clearings |
| tropical-epiphytes | Dendrobium — Orchidaceae | (herb_forb, **epiphyte**) | tropical moist canopy perches (the epiphyte layer flag, ruling #9) |
| mangrove-associates | Lumnitzera — Combretaceae | (tree, canopy) | tropical coast mangrove fringe |
| mangrove-palms | Nypa — Arecaceae | (tree, canopy) | tropical coast tidal estuaries |
| rock-ferns | Asplenium — Aspleniaceae | (fern_grade, ground) | scree + bedrock-outcrop crevices |
| forest-mycorrhizal-fungi | Amanita — Amanitaceae | (fungus, ground) | temperate + boreal forests (oak/pine partners) |

**Clade spread within co-window bundles** (families per window):
- temperate window: Asteraceae (Senecio) / Asparagaceae (Convallaria) /
  Rosaceae (Rosa) / Dryopteridaceae (Dryopteris) / Poaceae (Echinochloa
  via alluvium, Calamagrostis via alpine) / Ranunculaceae — no two
  bundles in one family share the same window.
- bog/fen window: Ericaceae (Andromeda) / Cyperaceae (Eriophorum) /
  Droseraceae (Drosera) + individual Sphagnum (Sphagnaceae).
- saline window: Plumbaginaceae (Limonium) / Amaranthaceae (Salsola,
  Salicornia) / Poaceae (Spartina) + macroalgae (Fucus).
- tropical window: Zingiberaceae / Rubiaceae / Convolvulaceae /
  Orchidaceae / Combretaceae / Arecaceae + individual Dipterocarpaceae,
  Arecaceae, Fabaceae.
- The one congeneric pair is deliberate: `Senecio` hosts temperate +
  alpine-meadow flowers — different windows, same family, matching the
  real genus's range (the congeneric-flock pattern, report §2).

## 5. Substrate floor (seeded level, authoring responsibility)

The two-axis resolution: bog/fen, alluvium, solonchak/tidal-flat/
coastal-sand, scree/bedrock-outcrop, and till/outwash are SUBSTRATE
rows inside existing biomes — no biome-list change. Seeded lineages
(individual + bundle pins) per class:

| Substrate | Seeded lineages (≥2–3 required) |
|---|---|
| bog / fen | Sphagnum (ind), Vaccinium (ind), bog-heath, fen-sedges, bog-carnivores |
| alluvium (riparian) | Salix (ind), Alnus (ind), wet-meadow-herbs, floodplain-grasses, marsh-marginals |
| solonchak / tidal flat | Salicornia (ind), Salsola (ind), Spartina (ind), coastal-herbs |
| coastal sand | Ammophila (ind), Salsola (ind), coastal-herbs, intertidal-algae (rock) |
| scree / bedrock outcrop | Saxifraga (ind), Sedum (ind), Lecanora (ind), rock-ferns, tundra-herbs, tundra-lichen-mats |
| till / outwash (glacier retreat) | Silene cushion (ind), alpine-cushions, tundra-herbs, crust-lichen (ind), Salix (flexible) |
| glacier MASK (NOT a substrate) | nothing roots on it except snow-adaptation margin forms: Silene (cushion_mat), alpine-cushions (cushion_mat), Salix (flexible), conifers (conical_shed) — the REQ_GLACIER margin set |

The Task C audit (a later task) evaluates these on seed 1 with the
same viability function genesis uses; this census is authored so no
obvious hole exists.

## 6. Open-catalog entry format (owner ruling 7)

The census is an OPEN catalog: adding a species or bundle is a
one-block change in `pins.toml` (+ a preset only if you need a new
order-level archetype). `test_census.py` is the entry gate — a new
entry must keep it green. Do NOT touch `backbone.py`, `derive.py`, or
the sim to add content.

**A. Add an individual-track species** (a habitat-former):
```toml
[[pin]]
preset = "tree.oak"            # an existing preset of the right plan;
                               # create a preset file only for a new order archetype
label = "chestnuts"            # unique label (used as the node label + name commit)
name = { binomial = "Castanea", folk = "chestnut" }   # genus pin: ONE word
rank = "genus"                 # "genus" (radiates) or "species" (single lineage)
radiation = 1                  # 0-2; genus-rank only. Keep small — every radiated
                               # species counts toward the <200 budget.
axes = { height_m = 22.0, fruit_type = "nut", engineer_impact = 0.6, ... }
                               # overrides on top of the preset record; enums must be
                               # registry states ("none" allowed on spore plans)
flags = ["pinned"]
note = "one-line operational-boundary justification"
```
Rules: keep radiation ≤ 2 (budget + the sister-cluster lesson); a
species-rank pin gets 1–2 generated relatives automatically (sibling
requirement); the built-tree species count must stay < 200 on seeds
1–3 (check `test_built_tree_under_200_lineages`).

**B. Add a bundle** (archetype superset generalist):
```toml
[[pin]]
preset = "herb_forb.forb"      # any existing preset of the right (plan, layer)
label = "boreal-peatland-shrubs"
name = { binomial = "Chamaedaphne calyculata", folk = "boreal peatland shrubs" }
rank = "species"
bundle = true                  # THE bundle flag — species-rank + this flag
covered_region = "boreal bog/fen margins; waterlogged peat"   # region x substrate note
axes = { ... }                 # ONE (plan, layer): wider tolerance breadths than any
                               # single species, CENTRAL optima in the biome core,
                               # archetypal enums (never averaged), generous
                               # propagule_count (guild seed rain)
```
Rules: species-rank only, no `radiation`, no `parent_pin`; binomial
genus must NOT collide with any individual-track genus (disjoint
partition); co-window bundles must not share a genus (clade spread);
`covered_region` is required; the flag shape is validated by
`test_bundle_flag_shape`.

**C. Remove or prune** a lineage: delete its `[[pin]]` block. If its
genus then has no remaining pins anywhere, the order it rode may still
carry background species — no further cleanup needed.

## 7. Open questions / gaps (for the owner / Task B–D)

1. **`engineer_impact` exists** (ecosystem block, B6 table) — no schema
   gap there. But it has no stress consumer yet ("engine-pending");
   the census authors it as the habitat-physics marker regardless.
2. **Epiphyte layer flag**: `layer` gained a new enum state
   `"epiphyte"` in `axes_core.toml` (content-level) to express the
   ticket's epiphyte ruling on the tropical-moist anchor
   (`tropical-epiphytes` bundle). Nothing else reads it yet — k15's
   layer-partitioned capacity (0026) must decide how epiphytes sit in
   the canopy layer.
3. **Mangrove waterlogging ceiling**: the `aquatic_layer` constraint
   fires at waterlogging > 0.85 and demands an aquatic layer — a land
   canopy cannot author full waterlogging. Mangroves are capped at 0.8
   (content workaround). If real mangrove physics wants > 0.85, the
   rule needs a land-plan exemption (content decision, not engine).
4. **`snow_adaptation` plan_scope** = ["tree","shrub","moss_grade"]
   omits rosette_mat — the alpine cushion / moss-campion
   glacier-margin forms author `cushion_mat` on rosette_mat against
   the scope (pinned records are trusted, so it works; the scope
   should admit rosette_mat if the sampler should gate it too).
5. **No vine / epiphyte plan**: "tropical vines" and epiphytes ride
   `herb_forb` (support `herbaceous_stem`); a dedicated vine plan is a
   vocabulary-round item (vocab §7.1 lists vine/epiphyte as
   second-round-only). The ticket's example bundle names work as
   authored; the growth form itself is a 0027+ item.
6. **Dwarf birch duplication**: `Betula nana` sits under its own
   `Betula` genus in `shrub.betulaceae` while the tree birches pin
   lives in the Fagales order — the schema cannot express one genus
   spanning two growth-form plans, so the real-world single Betula
   clade is scaffolded as two. Cosmetic; noted for the viewer.
7. **Budget headroom**: 179/190/190 — seeds 2–3 run ~11 species hotter
   than seed 1 (radiation round-off). ~10 pins of headroom remain; new
   entries should prefer bundle-track (1 + ~1.5 relatives) over a new
   order (~2.5 total) when possible.
8. **k15 re-pins / tests**: the census changes node ordering and sids —
   k15 genesis pins and tests WILL break (Task D scope; expected per
   the ticket).
