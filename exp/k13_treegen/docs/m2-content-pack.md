# M2 — content pack interface & design tables

Implements the content layer per the rebuild plan. **Grow-as-pins-demand**:
start with what the starting pin set touches, grow TOML as pins demand; the
consistency linter (`lint.py`) keeps partial coverage honest. Authored in
TOML. This doc carries the design tables the content fill executes — the
subagent authors NO judgment, only mechanical transcription against these.

## Taste constraints (from `/srv/http/p/fileshare/pool/taste-bootstrap.md`)

- Everyday register = standard archetypes **as-is**. For a naturalistic fauna
  generator that means **real, recognizable animals** — no invented everyday
  creatures (reads as twee). The novelty budget is spent on majestic seeds
  (ley) and machinery, not on everyday fauna.
- Pins are therefore real animals (horse, wolf, tiger, tapir); "real-exotic"
  flavor sparingly (tapir, anteater, cassowary — all real).
- Imply, don't declare; nothing requiring machinery that doesn't exist.

## Blocks covered (M2)

morphometrics (B1) · niche · diet · life_history · behavior · ecosystem ·
sex_age_season. **Patternation is M3** (separate module). Aquatic plans
(finned, cephalopod, shell, etc.) are deferred — the starting pins are all
tetrapod / winged_biped / hexapod; those plans grow in when fish/invertebrate
pins are added.

## Starting preset set (3 plans)

- **tetrapod** (B1 v0.3 §2, 9 grades): squirrel, boar, cat, weasel_otter,
  deer, bear, mole, rabbit, monkey — **plus `reptile`** (new: crocodile-grade;
  sprawling, long trunk, semi-aquatic — B1 §13.3 herp dials apply).
- **winged_biped** (B1 §3, 9 grades): sparrow, crow, owl, heron, duck, eagle,
  hummingbird, penguin, + bat variant knobs available.
- **hexapod** (B1 §5, 6 grades): ant, butterfly, beetle, dragonfly,
  grasshopper, bee.

## Starting pin set (taste-informed; me-authored)

**Species-rank megafauna pins (~18), by function** (eat / threaten / carry /
see-daily + real-exotic flavor). Pin = species record under the nearest preset
+ overrides. The pin→preset map is FIXED here (no subagent judgment):

| pin | preset | function | salient overrides |
|---|---|---|---|
| horse | tetrapod.deer | carry/ride | toe_count 1, metapodial_proximal 0.9, mass 450 |
| red deer | tetrapod.deer | eat/game | antlers (signal), mass 160 |
| aurochs | tetrapod.deer | eat/game | horns (keratin, permanent), mass 700, trunk deep |
| boar | tetrapod.boar | eat/omnivore | mass 90, tusks, mane_ruff dorsal |
| rabbit | tetrapod.rabbit | small game | mass 2, saltatorial |
| wolf | tetrapod.cat | threaten | fixed claws, round pupil, long snout, pack social, mass 45 |
| brown bear | tetrapod.bear | threaten | mass 300, plantigrade, omnivore |
| tiger | tetrapod.cat | threaten | mass 220, striped (M3), solitary |
| crocodile | tetrapod.reptile | threaten | semi-aquatic, mass 400, osteoderms |
| seal | tetrapod.weasel_otter | coastal | flippers, blubber, mass 100 |
| tapir | tetrapod.deer | exotic | proboscis_grade short, toe_count 4, mass 250 |
| anteater | tetrapod.weasel_otter | exotic | long tongue, fossorial-ish, mass 35 |
| pangolin | tetrapod.mole | exotic | keratin scales, tongue, mass 5 |
| sparrow | winged_biped.sparrow | see-daily | mass 0.03 |
| crow | winged_biped.crow | see-daily | clever [tell], mass 0.5 |
| mallard | winged_biped.duck | see-daily/water | palmate, lamellate beak, mass 1 |
| eagle | winged_biped.eagle | threaten | hooked beak, soaring, mass 5 |
| owl | winged_biped.owl | nocturnal | facial_disc, nocturnal, mass 1 |

**Texture pins (radiation controls, any-rank)** — declare "this branch
radiates"; radiation is an authored param, not dynamics:

| pin | rank | under preset | radiation |
|---|---|---|---|
| murid rodents | family | tetrapod.squirrel | 60 |
| passerine songbirds | family | winged_biped.sparrow | 80 |
| beetles | order | hexapod.beetle | 120 |

**Invented-clade budget: 0 in the starting set** (all starting pins are real
animals, per taste). Invented clades (2–4, small-bodied) are a later, explicit
addition.

## Tier / mutation assignment rules (mechanical — no judgment)

Apply per axis when converting v1 morphometric knobs:

- **tier=invariant**: plan-defining topology only (rare; most B1 knobs are NOT
  invariant). Body-form class, tagmata layout, shell-coiling presence.
- **tier=steady**: all B1 §§2–12 proportion/index knobs (limb indices, body
  ratios, wing indices, fin ratios). Small drift.
- **tier=labile**: all B1 §13 surface dials + color/pattern. Large drift.
- **unit=mass**: `body_mass` only; every other knob dimensionless.
- **mutation_kind**: indices/ratios with bounds → `ratio` (bounded) or
  `gaussian`; counts (int) → `gaussian`; mass → `log_gaussian`; enums →
  `enum_redraw`; plan-topology → `none`.
- **sigma**: steady ≈ 6% of the bounded range; labile ≈ 12%; enum_redraw
  ignores sigma. (drift_var per clade scales this later — M5.)
- **salience**: 0–1 by how name/epithet-worthy the axis is (mass/size 0.9;
  color/pattern 0.8; salient parts 0.6; deep proportions 0.2).
- **grammar_role**: body_mass→size; covering/skin/fur/feather→covering;
  diet guild→diet; salient named parts (ears, tail, horns, beak, crest)→part;
  body-form/grade→grade; else none.

## allometry.toml (ratio-sanity constants, vocabulary §5)

Damuth herbivore density ∝ M^−0.75 · Lindeman ~10%/trophic level · carnivore
biomass 1–10% of prey · home range ∝ M^~1 · Kleiber BMR ∝ M^0.75 · reference
densities (mouse 10–100/ha, deer 1–10/km², wolf ~1/100–300 km²). As authored
data for C6 counter validation.

## Consistency linter (`lint.py`) — the semantic safety net

Reviewable-data rules over the content pack, each with a planted-violation
test. Catches the v1 bug class (crocodile-on-monkey):

1. diet guild ↔ feeding-organ realization compatible (filter-feeder ⇒
   lamellate/baleen/rakers; grazer ⇒ hypsodont; carnivore ⇒ carnassial/fang).
2. flightless ⇒ no soaring/high-aspect flight knobs set.
3. pin overrides within preset grade magnitude (mass within ×10 of preset;
   a pin can't be 100× its preset).
4. behavior defaults non-contradictory (eusocial ⇒ group_size > 1; obligate
   soarer ⇒ not flightless; nocturnal ⇒ night-adapted sensor).
5. pin→preset plan match (a tetrapod pin under a tetrapod preset).
6. record/quantity anti-creep ("can the player collapse this as an
   individual? no → quantity layer, not a record").

## "N/A" inapplicability literal (user ruling, 2026-07-28)

Inapplicability is pruned IN THE RECORD, not by consumers. A preset marks a
dial `"N/A"` when the feature is absent AND the axis vocabulary cannot
express absence. Dials where 0.0 or "none" already means absent
(proboscis_grade, dorsal_crest_spines, ...) keep real values — N/A is only
for vocabularies that assert a feature with every state
(horn_cover_texture: bare_keratin/velvet/shed asserts a horn; skin_texture:
smooth_moist/granular/warty/keeled is herp skin).

Legality (lint R-na): N/A only on plan-scoped morphometrics dials. An axis
scoped "all" applies to every body (body_mass included, though it sits in
the morphometrics block); core/patternation/niche axes are always
applicable.

Semantics for downstream modules:

- The literal survives end-to-end (resolved Node JSON shows "N/A").
- Mutation (M5) never perturbs an N/A axis; descendants inherit N/A.
- A pin may REACTIVATE: N/A -> real value is a legitimate derivation
  (horned-lizard pin under a hornless grade). Covered by test.

Future (ledger W7): near ley lines the legality envelope relaxes — N/A
reactivation, palette breaches, and >3σ drift become legal without
authoring. Absence is sticky in the base world, leaky near magic.
