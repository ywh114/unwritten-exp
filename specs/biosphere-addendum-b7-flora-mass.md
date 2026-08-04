# Biosphere Addendum B7 — Flora per-capita biomass (allometry lock)

Status: LOCKED v1.1, 2026-08-04 (ticket 0035). Amends the k15 engine
spec's percap stub (§6, crown²·(1+woodiness)/25 — replaced, not
adjusted). Implementation: `exp/k15_biosphere/flora/mass.py`; reality
harness: `exp/k15_biosphere/flora/reality.py` (permanent fast-tier
test). Formula lock with every constant and DOI: ticket 0035
(queue/closed after 2026-08-04).

## What this is

One organism's biomass is a PURE DERIVED FUNCTION of its morphology —
never an authored trait (standing owner ruling: derive, don't author).
Currency: kg dry biomass per individual; every estimate splits
aboveground / belowground and exposes its intermediate proportions
(trunk diameter, crown:DBH, root:shoot) so the future
proportion-deviation penalty mechanism (0035 owner note, 0036
cross-ref) can read them.

One formula family per growth-form group; what each means and the
real number it was anchored to:

- **Trees**: crown spread → trunk diameter via a crown:DBH ratio
  (Hemery 2005, k≈18 stand broadleaf; Pretzsch inversion, k≈10
  conifer), then Chave 2014's ρ·D²·H allometry. A 25 m oak with a
  14 m crown weighs ~4.6 t aboveground — the anchor that corrected an
  earlier ~3.1 t misestimate.
- **Shrubs**: crown volume × effective tissue density (anchored: a
  1.5 m sagebrush ≈ 1.9 kg).
- **Herbs/ferns**: (cover × height)^0.75 power (a 0.5 m forb ≈ 7 g).
- **Grasses/swards/runners**: per-AREA standing crop × footprint —
  the owner's "a sward's capacity is the ground it covers" reads
  literally. Pasture anchor 0.3 kg/m² aboveground (Gill 2002).
- **Succulents**: geometric volume → fresh mass → dry fraction
  (a 1 m barrel ≈ 100 kg fresh).
- **Mats (moss/lichen/rosette)**: per-area mat density (Sphagnum
  carpets 0.2–1.5 kg/m²).
- **Kelp**: wet-linear-density × stipe length → dry fraction
  (a 20 m Macrocystis ≈ 1.2 kg dry; bed cross-check 0.4 kg dry/m²).
- **Fungi**: fruitbody size class + mycelial soil term —
  order-of-magnitude only, so fungi are never massless.

Weak links, flagged honestly in the lock: tropical closed-forest
crown:DBH ratio (no clean published value), fruitbody mass-by-class,
grassland root:shoot. The reality harness guards them: eight named
ecosystem cases (oak-beech stand, rainforest, taiga, pasture, kelp
bed, Sphagnum bog, sagebrush steppe, seagrass meadow) must each
compute inside their sourced real-world range — the test suite fails
if a formula edit drifts any of them. All eight pass at lock v1.1.

## Interface (owner ruling 2026-08-04)

Flora and fauna share the sim's general mechanisms; they differ ONLY
through kingdom-specific hooks. The hook contract lives at
`exp/k15_biosphere/interface.py` (MassEstimate + the percap_biomass
signature); `flora/mass.py` is flora's implementation. The canonical
sim output is the per-cell, per-lineage biomass density field — the
game layer's L1 (regional, lazy) and L2 (render tier) read it for
spawn probability, location, amount.

## The capacity conversion contract (feeds Phase 2)

K_L in tonnes = productivity (B2 constructed scale) × substrate share
U × K_BIOMASS_T_PER_HA (ONE natural knob) × cell hectares. Sim cells
are 1600 ha (4 km × 4 km, 256²); the per-hectare definition is
resolution-independent (1024² cells are 100 ha; the planned
post-upscale diffusion is functional, not cosmetic — owner). The
knob's value is set in Phase 2 with the cell-share investigation;
grassland's stock-vs-flow mismatch is a flagged Phase 2 question.
