# Biosphere Addendum B8 — Biomass capacity accounting (Phase 2 lock)

Status: LOCKED v1, 2026-08-04 (owner rulings in-line). Foundation
layer for the rewrite's L2 occupancy. Supersedes k15 engine spec §6's
accounting where they conflict (the frozen engine keeps its own).
Evidence: `scratch/phase2_capacity_probe.py` run on the seed-1
artifact with B7 allometry (the probe, its numbers, and the 200 m
cactus are summarized at the bottom).

## The two-level accounting (owner ruling 2026-08-04)

Capacity is checked at TWO levels, both in tonnes of dry biomass:

1. **The cell pool** — the physical bound on the whole stack:
   `C(c) = productivity(c) · X · cell_ha`, with **X = 400 t/ha per
   productivity unit** (provisional; revisit with ticket 0019 — it may
   need readjustment or become moot). Per-hectare by definition, so it
   survives the resolution change (1600 ha cells at 256², 100 ha at
   1024²; the post-upscale diffusion will be functional, not cosmetic).
2. **The lineage cap** — every lineage's demand in a cell stays BELOW
   the cell pool (an oak forest does not physically take the whole
   cell — ticket 0019's staged rounds need the headroom). Structured
   by SUBSTRATE: the species fills its favorable substrate class until
   it hits its own cap, then SPILLS into the next class at reduced
   suitability (the B3 substrate-share machinery, reused).

**The lineage cap is NOT a simple fraction of the cell pool** (owner
ruling, the emergence requirement): a high-productivity cell A and a
slightly poorer cell B should carry the SAME oak biomass, but A's
understory richer than B's. A fraction-of-pool cap would scale the
oak with productivity and kill the contrast. So the lineage cap needs
a component that saturates against productivity — the dominant's
biomass is set by its own biology (crown geometry, light, substrate
extent), while the RESIDUAL (pool − Σpresent) is what the understory
claims, and the residual scales with the pool. Exact functional form:
set at L2 implementation against this A/B acceptance case.

**Mixing term: TBD** (owner, verbatim "I haven't thought of yet, but
this can be tuned"): the lineage cap is not entirely cell-blind —
who else is present influences the cap through a mixing term to be
designed. Flagged open design point for L2, not blocking.

## What the probe measured (seed 1, old engine, B7 tonnes)

- Today's cells: median species holds ~20% of cell biomass; the top
  species per cell holds median 75%; 36% of occupied cells are >90%
  single-species (partly artifact, see below).
- Forest biomes land in real standing-crop ranges (temperate
  broadleaf mean 225 t/ha vs real 150–400; tropical moist 249 vs
  200–450; taiga 105 vs 15–100) — the B7 allometry scales to the map.
- X selection table (median cell fill / cells over capacity):
  X=100 → 131%/58%; X=200 → 65%/37%; X=400 → 33%/19%. X=400 puts
  real forests mid-range inside capacity with headroom for the sim
  to paint (owner note: genesis mints well below capacity).
- The outlier: one species held 92% of world biomass — a 200 m
  cactus with a 55 cm crown (succulent.cactus at the height_m axis
  ceiling). The formula is sane at sane proportions (12 m saguaro →
  ~5 t fresh ✓); the monster is the PROPORTION-DEVIATION PENALTY's
  job (0035 owner note), landing with L1 morphology in the rewrite.
  This specimen is that mechanism's documented motivation.

## Flags for later layers

- **Grassland stock-vs-flow**: a standing-biomass conversion grants
  grassland cells far more capacity than grassland standing crop
  (0.55 prior × 400 = 220 t/ha vs real 0.8–9.3). The resolution is
  turnover/layering — dynamics, Phase 3 L3 — not a second knob here.
- **Understory/layering**: canopy layers compete for light, not just
  tonnes; the pool bounds bulk, the light axis (B6) stratifies it.
  L2/L3 design input, noted by the owner in the ruling.
