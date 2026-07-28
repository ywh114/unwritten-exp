# M3 — patternation (color & pattern) design

Implements the color/pattern layer per the rebuild plan. Grounded in a
4-agent research survey (motif geometry, region markings, age/season/sex,
functional palettes). This doc fixes the grammar target and the v2 scope.

## Grammar target (three orthogonal layers + modifier stack)

Pattern = **Palette × Geometry × Region**, transformed by **Modifiers**:

- **Palette** — mechanism-typed colors (`melanin` / `carotenoid` /
  `structural` / `other-pigment`). Per-clade availability: mammals melanin
  only {black, dark brown, gray, rufous, tan, cream, white}; birds +carotenoid
  (diet reds/yellows) +structural (all blues, iridescents — no blue pigment);
  fish/reptiles/amphibians/insects full gamut incl. structural blue/green.
  Gloger/habitat tint (warm-humid→dark, arid→pale, cold→white) is a
  stress-descent coupling (rounds), not free variation. Aposematic override
  (defended → black+yellow/red/white) trumps crypsis.
- **Geometry (motif)** — spots→rosettes→blotches→stripes→labyrinths→bands are
  ONE reaction-diffusion continuum (wavelength, anisotropy, coalescence,
  coverage, orderliness, contrast, edge sharpness), NOT separate types.
  Separate mechanisms: piebald, mottle/disruptive, marginal markings.
  **Murray's domain law**: region size ÷ λ selects the mode (1-D region →
  bands only; tapered → spots at base, bands at tip) — "striped animal can't
  have a spotted tail" falls out as a constraint.
- **Region (per-bodypart markings)** — independent elements layered on a base,
  anchored to body zones (eye-stripes, dorsal stripes, rump patches, ocelli,
  tail tips). **DEFERRED — see below.**
- **Modifiers (age/season/sex)** — transformations on the base, precedence
  `natal > seasonal swap > sex overlay > age-ramp`. Age gates sex; season can
  cancel sex (eclipse). Mechanisms: juvenile overlay removed / natal swap /
  step-ramp staged plumage / true ramp; seasonal molt swap (with pinned
  regions); sex overlay / palette swap / condition ramp. Uses B1 §14
  temporal-modifier machinery.

## v2 scope (lighter core — parts/slots deferred)

Parts/slots as full records are deferred (scope rulings). The region-anchored
markings layer depends on a body-region vocabulary that overlaps the §2.2
slot anchors (`head.crown`, `dorsal.mid`, `tail.tip`). **Committing to two
region vocabularies would be a bug**, so the markings layer defers WITH
parts/slots: when both are built together, ONE shared region/anchor
vocabulary is finalized to serve anatomy + patternation. (Joint deferred
decision — recorded here so it isn't made twice, inconsistently.)

v2 core therefore = **Palette + base motif + modifiers**, NO region markings:

- **Palette axes** — `base_color`, `belly_color`, `accent_color` (enums from
  the clade palette; mechanism-typed). Clade-steady backbone, species labile.
- **Base motif** — `pattern_motif` enum of canonical continuum points
  {uniform, countershaded, spotted, striped, banded, rosette, mottled,
  saddled} + `pattern_coverage` and `pattern_contrast` (ratio scalars).
  Motif type clade-steady; coverage/contrast labile.
- **Modifier axes** — `dichromatism` (already registered), `pattern_juvenile`
  (enum: none/spotted/striped/natal-coat — overlay removed at molt),
  `seasonal_molt` (enum: none/winter-white/breeding-alternate — swap with
  pinned regions).

Sisters differ via palette colors, motif type, coverage/contrast, and the
modifier tags — a spotted fawn lost at molt, a white winter coat, a red vs
brown base, male ornamentation. Believable color variation without needing
the bodypart model.

## Reserved (M3-extensions, no record-shape change)

- Region-anchored markings set (per-bodypart) — lands with parts/slots on the
  shared region vocabulary.
- Continuous Turing parameters (wavelength/anisotropy/coalescence as scalars)
  replacing the motif enum.
- Gloger/habitat tint as a live coupling (rounds).
- Mimicry links: `mimicry_ring_id` (Müllerian) / `batesian_mimic_of` (directed
  edge), resolved post-backbone with co-occurrence.

## Archetype catalog (from research — feeds content + future markings layer)

Canonical motif continuum points and the recurring markings (for the deferred
region layer): eye-stripe/mask, supercilium, dorsal stripe, dorsolateral
stripe pair, flank spots/rosettes, saddle, rump patch, tail rings/tip/flag,
ocellus (eyespot), wing bars, speculum, countershading. Per-clade palettes:
mammal melanin set; bird +carotenoid {red, orange, yellow} +structural
{blue, iridescent green/violet}; herp/fish/insect full gamut. Aposematic set
{black+yellow, black+red, black+white} for defended species.

## Delivered (M3 v2)

- `content/axes_patternation.toml` — 8 axes: base/belly/accent color (enum,
  labile), pattern_motif (8-state enum, steady), pattern_coverage/contrast
  (ratio scalars), pattern_juvenile (none/spotted/striped/natal_coat),
  seasonal_molt (none/winter_white/breeding_alternate/eclipse).
- `content/palettes.toml` — per-plan legal colors: tetrapod = melanin range
  + herp dark_green + tiger orange; winged_biped/hexapod = full incl.
  carotenoids and structural. Presets may widen the plan palette for their
  grade via `[preset] palette_extra` — the reptile grade carries the full
  herp gamut (red/orange/yellow/blue/green/iridescent); mammal grades stay
  melanin-only. Sloth algae-green is a documented exclusion (ecological
  tint, not pigment).
- All 24 presets author the full patternation set (no vary-on-expose);
  pins demonstrate overrides (tiger orange/striped, tapir saddled +
  natal_coat, wolf gray).
- Lint rule R7 (`palette`): preset/pin colors must be in the plan palette,
  with planted-violation tests (blue mammal, iridescent wolf accent,
  missing palette). Suite: 74 green.
- Sampler legality (found by M8's named build): enum redraws draw from
  palette-legal states, not the full state list — enforced in
  `forces._legal_states` and gated tree-level by the
  `palette_legality` metrics checker (71 violations before the fix, 0
  after).
