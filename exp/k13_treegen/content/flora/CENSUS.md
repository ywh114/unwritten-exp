# K14 flora census — 0012 INTERIM (individual-track only, 2026-08-02)

**Source of truth:** `tmp/0012-curate-initial-radiation.md` (the ticket;
owner rulings 1–14). **Authority for loading:** `content/flora/pins.toml`
+ `presets/` + `content.py` + `backbone.py` — this doc explains intent,
it does not override the files.

**State (2026-08-02, interim after the bundle-track removal):** 52
individual-track pins; built-tree species **105 / 107 / 109** on seeds
1/2/3 — all well under 200. k13 fast tier green (272 tests).

## 0. Interim status — bundle records RE-AUTHORED; stub scaffold pending

Task A's first pass (commit `0d0e0d6`) authored 34 bundle-track pins as
species-rank tree nodes under single authored genera (e.g.
`temperate-flowers = Senecio vulgaris`). That is the WRONG shape: per
owner rulings 9–14 the bundle is a SIM-SIDE entity that stands in for
an aggregate of similar species pulled from MANY genera/families/orders
— it is not a tree node, and the tree is taxonomy-only (individual
track + stub scaffold). The misinterpreted bundle pins were removed
(`3dbae1c`) and **re-authored 2026-08-02 as `content/flora/bundles.toml`**:
33 `[[bundle]]` records, each an ENVELOPE (superset generalist: body
plan/layer + defining traits + stress tolerance profile, in the shared
sim/tree axes) + a POLYPHYLETIC ANCHOR-CLADE SET (anchor_families +
anchor_genera — the many real clades its members fall under, grounded
in `tmp/flora-composition-report.md` + targeted lookups). Bundles are
content only (not seeded lineages, not tree nodes); the sim-side frozen
niche-dweller is Task B, and 0027 uses the anchor clades to place
daughters post-sim. STILL PENDING: the stub scaffold (authored stubs at
any rank + radiated empty nodes).

**Sandalwood (Santalales) added 2026-08-02:** removing the bundles
tripped the `frozen_axis` metrics gate on seed 2 (tree plan:
`parasitism` frozen at `none` across 29 species, 56 opportunities).
The composition research flags Santalales as glaringly-missing-if-
absent; the fix is the real-world anchor — a hemiparasitic tree
(`tree.sandalwood` preset + `sandalwoods` genus pin, `parasitism =
"hemi"`), which guarantees tree-plan parasitism varies on every seed
and closes the documented order gap.

## 1. The individual track

Habitat-defining physics — canopy / sward / holdfast / mat / peat via
`layer` + `engineer_impact`, high expected cover (0012 ruling 4: "the
oaks, other trees, swards, bushes, kelps"). These lineages mutate,
adapt, and cladogenize normally (0010). Genus-rank pins radiate 1–2
species; a few landmarks are species-rank. 52 pins ≈ 105–109 seeded
species (pins + radiations + relatives + background).

## 2. Prune list — what the ad-hoc census dropped, and why

The old census was 35 presets / 24 pins / ~150 species, with the
sister-cluster pathology (genus-pin radiations 3–6 each minting near-
identical sibling species — the 0012 opening complaint). The re-
curation (Task A first pass, still in force for the individual track):

| Dropped | Why |
|---|---|
| yarrow, wild carrot, sword-iris, thread-leaf chive, thistle pins | not habitat-definers — ordinary meadow/forb design space; their presets were repurposed (`herb_forb.asterid` keeps the composite-head grade) or deleted. |
| grave-flower preset (kept as a species pin) | the plant survives as a RARE individual-track archetype (`Monotropa uniflora`, mycoheterotroph) — the RFC §6 "one rarity" pin. |
| tree.birch preset (merged into tree.oak) | Fagaceae+Betulaceae both ride the Fagales order; birches/alders/beeches are separate genus pins under it. |
| fungus.bracket, moss_grade.cushion, floating_leaf.ludwigia, rosette_mat.ice_crown presets (merged) | archetype grades folded into the surviving order of the same plan. |
| radiation 3–6 genus pins → radiation 0–2 | the sister-cluster pathology itself: oaks now = 2 pinned species + 1–2 relatives. |
| crowberries (Empetrum), figs (Ficus) pins | count trim; tundra already has Vaccinium / Betula nana / Carex / Sphagnum. |
| bamboo pin (order kept) | the order survives with its generated background species. |
| poplar, maple, fir, arbutus, hazel (never authored) | temperate/boreal canopy already has oak+beech+birch+spruce+pine+larch; med is basin-only per ruling. |
| ludwigia / sword-plant pins | not habitat-definers. |
| **34 bundle-track pins (2026-08-02)** | misinterpreted as species-rank tree nodes; removed per rulings 9–14 (see §0). |

**Why the survivors keep their nodes:** every retained lineage carries
habitat-defining physics — a canopy/sward/holdfast/peat/mat former with
authored `engineer_impact` or an explicit substrate anchor.

## 3. Individual-track picks by biome

Operational boundary per pick: canopy/sward/holdfast/mat physics + high
expected cover. ~2–4 habitat-forming genera per biome.

| Biome | Individual-track picks (genus — family) | Why (one line) |
|---|---|---|
| Tropical moist | Shorea (Dipterocarpaceae), Cocos palm (Arecaceae) | emergent canopy + subcanopy monocot |
| Tropical dry | Ceiba (Malvaceae), Acacia (Fabaceae) | drought-deciduous canopy; legume savanna tree |
| Tropical conifer | Pinus (Pinaceae) | N-hemisphere pine/pine-oak expression |
| Tropical grassland (savanna) | Andropogon (Poaceae) + Acacia | sward-former + scattered Fabaceae tree |
| Mangrove (tropical coast) | Rhizophora (Rhizophoraceae), Avicennia (Acanthaceae) | stilt-root / pneumatophore tidal forest |
| Temperate broadleaf | Quercus (Fagaceae), Fagus, Betula, Alnus | oak/beech/birch canopy + alder riparian |
| Temperate conifer | Pinus, Picea, Larix (Pinaceae) | pine/spruce/larch conifer canopy |
| Boreal taiga | Picea, Larix, Betula (hardwood pioneer) | taiga canopy trio |
| Temperate grassland | Festuca (Poaceae) | sward-former |
| Flooded grassland | Phragmites (Poaceae), Typha (Typhaceae), Carex (Cyperaceae) | reed belt, bulrush, sedge |
| Montane grassland | Festuca | alpine-meadow expression |
| Tundra | Vaccinium, Calluna, Betula nana (Betulaceae), Carex, Sphagnum | dwarf-shrub + tussock + moss mat |
| Mediterranean scrub | Quercus ilex, Cistus (Cistaceae), Salvia (Lamiaceae), Phillyrea (Oleaceae) | basin/maquis-only per ruling |
| Desert (hot) | Carnegiea (Cactaceae), Agave (Asparagaceae), Larrea (Zygophyllaceae), Prosopis (Fabaceae) | columnar succulent, rosette monocarp, creosote shrub, phreatophyte |
| Desert (cold) | Artemisia (Asteraceae), Salsola (Amaranthaceae) | sagebrush + saltbush |
| Riparian (alluvium) | Salix (Salicaceae), Alnus (Betulaceae) | willow/alder river-corridor canopy |
| Bog/fen | Sphagnum (Sphagnaceae) | peat-former, engineer 0.9 |
| Salt marsh / saline | Spartina (Poaceae), Salicornia (Amaranthaceae), Salsola | cordgrass sward, samphire, saltbush |
| Scree / bedrock | Saxifraga (Saxifragaceae), Sedum (Crassulaceae), Lecanora lichen, Silene cushion | chasmophytes + first colonist + glacier-margin form |
| Freshwater | Nymphaea (Nymphaeaceae), Phragmites, Typha, Carex | floating-leaf + emergent + littoral |
| Marine | Macrocystis (Laminariales), Zostera (Zosteraceae) | kelp-forest canopy + seagrass meadow |
| Forest floor (rare) | Monotropa (Ericaceae) | mycoheterotroph rarity pin |
| Santalales (rare) | Santalum (Santalaceae) | hemiparasitic tree — closes the report's glaring order gap + the tree-plan parasitism freeze |

## 4. Coverage floor (seeded level — individual track)

The Task C audit evaluates these on seed 1 with the same viability
function genesis uses; the content is authored so no obvious hole
exists. Rows that previously leaned on bundle pins are back to the
individual track only; the substrate-floor test (`test_census.py`)
currently passes on all rows with individual lineages alone.

## 5. Open-catalog entry format (owner ruling 7) — individual track

Adding a species is a one-block change in `pins.toml` (+ a preset only
for a new order archetype). `test_census.py` is the entry gate — a new
entry must keep it green. Do NOT touch `backbone.py`, `derive.py`, or
the sim to add content.

```toml
[[pin]]
preset = "tree.oak"            # an existing preset of the right plan;
                               # create a preset file only for a new order archetype
label = "chestnuts"            # unique label (node label + name commit)
name = { binomial = "Castanea", folk = "chestnut" }   # genus pin: ONE word
rank = "genus"                 # "genus" (radiates) or "species" (single lineage)
radiation = 1                  # 0-2; genus-rank only. Keep small — every radiated
                               # species counts toward the <200 budget.
axes = { height_m = 22.0, fruit_type = "nut", engineer_impact = 0.6, ... }
                               # overrides on top of the preset record; enums must be
                               # registry states
flags = ["pinned"]
note = "one-line operational-boundary justification"
```

Rules: keep radiation ≤ 2 (budget + the sister-cluster lesson); the
built-tree species count must stay < 200 on seeds 1–3
(`test_built_tree_under_200_lineages`).

## 6. Open questions (for the rework / owner)

1. **`engineer_impact`** exists but has no stress consumer yet
   (engine-pending); authored as the habitat-physics marker regardless.
2. **Epiphyte layer flag**: `layer` gained an enum state `"epiphyte"`
   (content-level, for the tropical-moist epiphyte archetype) — nothing
   reads it yet; 0026 must decide how epiphytes sit in the canopy.
3. **Mangrove waterlogging ceiling**: `aquatic_layer` constraint fires
   at waterlogging > 0.85 — mangroves capped at 0.8 (content
   workaround).
4. **`snow_adaptation` plan_scope** omits `rosette_mat` — the alpine
   cushion glacier-margin forms author `cushion_mat` against the scope
   (pinned records trusted).
5. **No vine / epiphyte plan**: they ride `herb_forb`; a dedicated vine
   plan is a vocabulary-round item.
6. **Dwarf birch duplication**: `Betula nana` sits under its own
   `Betula` genus in `shrub.betulaceae` while the tree birches pin
   lives in Fagales — the schema cannot share one genus across two
   growth-form plans.
7. **k15 re-pins**: the census changes node ordering and sids — k15
   genesis pins and tests break (Task D scope).
