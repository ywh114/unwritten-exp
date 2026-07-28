# K13 — rounds, fragmentation, and food-web design (user, 2026-07-27)

Design record for the sim/diffuse rounds that follow the world-blind backbone
(out of K13 v2 scope, but the principles constrain the backbone's schema).
Settled in conversation; folded here so it isn't lost.

## 1. Abiotic-first principle

Early rounds apply **abiotic stress only** (temp, moisture, salinity, HAND,
elevation, growing season). Behavior specifics and predator/prey relations are
**assigned in later rounds**, so the first rounds run with none of that
pressure. Refinement: `diet_guild` and behavior axes are still *committed on
the clade* from the start (steady, from the preset) because flora provisions
couple to them — they are clade traits early, selection pressures later.

## 2. Diet is a spectrum, not a label

A single `diet_guild` enum is wrong; the "omnivore" state was the tell.
Omnivory is the default. Diet is a **weighted mixture over guilds**
(`diet_spectrum: {guild: weight}`, ~1 sum, dominated by 1–2 for specialists —
a brown bear is grazer + frugivore + piscivore + carnivore). **This is a
registry keystone change: `diet_guild` becomes `diet_spectrum`
(WEIGHTED_SET).** Audit other hard enums the same way — candidates that are
really sets: `vertical_stratum` (birds = aerial + ground + canopy; monkeys =
canopy + ground), `media` (dual-medium: seal feeds in water, hauls out on
land; RFC §4). Enums that stay single: `activity_period` (cathemeral covers
multi), `flight_style` (dominant mode), `reproductive_mode`, morphometric
form enums.

## 3. Round schedule (user's, with improvements)

1. Plants (abiotic-dispersal/pollination grade only — no animal vectors yet).
2. Insects + small herbivores (low counter values).
3. Plants, coupled (animal vectors now exist).
4. Megafauna (reads *accumulated* provisions from rounds 1–3).
5. Plants, coupled + **one seeded disturbance** (fire/flood/storm; ley lifts
   count locally) — forces pioneer→climax succession texture.
6. Remaining animals + predators.
7. **Speciation round** (dump-and-adapt: isolation + pressure crosses g\*).
Each introduction round ends with a fragmentation check. Unified by trophic
role/size — **no separate aquatic thread** (medium is a niche axis, not a
thread; cross-medium species just span media).

## 4. Fragmentation: reachable ≠ connected

The core failure to avoid: geodesic diffusion is *deterministic reachability*
— if any path exists around an obstacle, the species gets there and everything
goes panmictic. A probabilistic *crossing* filter is no better: once crossed,
the corridor is path-connected and the blob is one range again. **Fragmentation
must be defined on migrant rate, not path topology.**

- **Range (presence)** = reachability — where the species shows up, gated by
  hard barriers + the probabilistic *timing* of colonization.
- **Lineage fragments** = a second field, thresholded on **effective migrants
  per generation** through the connecting habitat (corridor length × mobility
  × corridor cost). Split where it drops below **~1 migrant/generation**
  (classic pop-gen rule: 1/gen keeps populations homogenized).

A long costly corridor is path-connected but <1 migrant/gen → vicariance
*despite* connection. This is continuous (cline → clean isolate), not a binary
gate. The three fragmentation modes fall out of the rate:
- **Hard barrier** → 0 migrants/gen → clean vicariance; recolonization only
  via rare long jumps (founder, bottlenecked).
- **Long costly corridor** → path-connected but <1 migrant/gen → vicariance
  despite connection.
- **Short/easy connection** → >1 migrant/gen → panmictic.

**Two isolation sources:** vicariance (a connected range newly split — needs
prior connection) and founder (a rare long jump across a barrier — the
**sweepstakes channel**, jump rate a clade axis; makes barriers semi-permeable:
impermeable to diffusion, permeable to rare jumps). After a jump, the founder
is cut off by the very barrier it crossed → isolated → diverges. Both read
differently in the tree (deep shared history vs bottleneck signature).

**Mobility is the speciation dial**, not a nuisance: high mobility → wide
ranges + high connectivity → few weedy species; low mobility → small ranges +
poor connectivity → high endemism. Resolution caveat: at 1 km², L0 vicariance
is driven by *coarse* features (straits, ranges, desert bands, drainage
basins); fine fragmentation is L1/L2.

## 5. Barriers: three-class threshold, species-relative

Per Flora RFC §3 / Fauna RFC §3, the stress field thresholds into
**passable / costly / blocked**, and "blocked" unifies three species-relative
kinds: **stress-blocked** (climate), **food-blocked** (provisions absent for a
specialist — vocabulary §4.3 flora-provision dependencies), **physically-
blocked** (strait to a non-flier, waterfall to upstream fish). "Costly" is the
semi-permeable filter; suitability tapers into refugia (soft edges).
Fragmentation can thus arise along provision gradients, not just geography.

## 6. Food web: derived, not seeded

Build from heuristics + a little seeded randomness, mostly *derived*:
- **Diet-spectrum → provision map** (vocabulary §10): each guild maps to a
  provision (grazer→sward, browser→browse, frugivore→mast, granivore→seed,
  nectarivore→nectar, insectivore→insect counters, piscivore→fish,
  carnivore→prey counters). A consumer draws *weighted* edges to every
  provision in its spectrum, strength ∝ weight × availability.
- **Realized co-occurrence** from the dispersal rounds (what's actually there).
- **Body-mass prey window** as a *clade prior*, not a rule: per-clade
  `prey_size_ratio` (lognormal around the clade mode) with a **social-hunting
  multiplier** for pack predators. The 0.1–1× default is the solitary-jawed-
  predator case; exceptions (pack hunters, swallow-whole snakes, filter
  feeders, deep-sea) are carried by the clade parameter.
Keep it directed and acyclic (trophic levels consistent); store as a quantity
layer, committed records only where pinned/observed.

## 7. Effect vectors: knobs give stat bonuses/debuffs (user, 2026-07-28)

Each axis (or axis value) maps to a **functional effect vector** —
`{thermal: +0.8, camouflage: −0.6, warning: +0.9, display: +0.7}` — the
honest generalization of M1's scalar `adapt_weight` (the scalar is just
the vector's magnitude). This is also where the fauna RFC's "no drift-only
axes" demand formally lands ("ear size is thermal, albedo is thermal,
camouflage is predation" is an effect vocabulary already).

Principles:

- **Couplings fall out of effects.** Tensions like camouflage-vs-warning
  or ornament cost are *computed* from the effect mapping, not authored as
  M6 rules. Curated couplings survive only where effects can't express the
  documented biology (domestication package, fast–slow life history).
- **Selection is painted** (M6 precedence ruling): stress = niche/effect
  mismatch against the local environment; descent pulls axes whose effect
  vector would reduce the mismatch. No culling simulation.
- **Camouflage is environment-relative.** A color has no intrinsic camo
  value, only camo against a background. v1 of the channel: `camo_{biome}`
  — biome-class background palettes from the world's biome map, matched
  against the species' palette colors (cheap, rough). Upgrade path: sample
  the actual plant-round vegetation colors in the species' range (same
  interface, higher fidelity).
- **Schema hook landed**: `AxisSpec.effects` is reserved — parsed and
  shape-validated, consumed by nothing yet.

Open caveat (user): the ~116 authored knobs have NOT been audited for how
well they carry effect semantics. The first effects-consuming task is an
audit pass assigning effect vectors per axis; knob-quality gaps surface
there and feed back into content.
