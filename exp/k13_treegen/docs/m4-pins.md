# M4 — pins: any-rank radiation/texture controls

Interface doc. Pins are Tier-1 authored anchors: real animals (and a small
budget of invented clades) that the backbone (M7) must place, keep
byte-exact, and radiate around. M4 owns the pin RECORD SCHEMA + content +
lint rules; placing/radiating pins is M7's job.

## Record schema (extensions over the M2 pin table)

```toml
[[pin]]
preset = "tetrapod.deer"      # grade anchor (M2)
label = "horse"               # display/naming anchor (M2)
rank = "species"              # optional, default "species"
radiation = 0                 # optional, default 0
drift = { limb_length_to_trunk = 1.0 }   # optional
knobs/axes/generics/flags     # as in M2
```

- **rank** — where the pin sits in the backbone. Species-rank pins anchor
  one real species (horse, tiger). Higher-rank pins are radiation anchors:
  they pin a CLADE GRADE ("murid rodents" family, "beetles" order), not a
  species. Value must be a `Rank` name from M0 (kingdom..species).
- **radiation** — authored target count of GENERATED species descendants
  under this pin. 0 = texture only. Meaningless on species-rank pins (a
  species does not radiate) → lint error. Targets are honored ~N with
  seeded variance by M7 (test lands there, not here).
- **drift** — directional-drift derivation: signed biases over named axes,
  in units of the axis's own mutation σ (dimensionless, self-scaling —
  consistent with the M1 dimensionless rule). Applied by M7 as a
  directional prior on descendant mutation: "equines = horse-grade but
  more cursorial" → `{ limb_length_to_trunk = 1.0 }`. Drift keys must be
  scalar/int axes — a signed lean on an enum is meaningless (enum redraw is
  directionless). |drift| > 3 is a lint error: past 3σ you are not leaning,
  you are teleporting — author absolute overrides instead. Drift on a
  non-radiating pin is dead content → lint error.
- **flags "invented"** — invented clades (no real-world referent). Budgeted:
  `[budget] invented_max` in pins.toml (default 0). Everyday register is
  real animals (taste bootstrap); invented novelty lives in the critter
  tier, so invented pins must be small-bodied (effective body_mass ≤
  INVENTED_MAX_MASS_KG = 1.0 — rat-sized; players accept a novel rat, not a
  novel elephant).

## Why drift is content, not machinery

The semantic shortcut ("horse but faster") is resolved AT AUTHORING TIME
into concrete signed axes by the content author. The engine carries only
signed biases on named registered axes — no natural-language derivation
layer, no new axis kinds. This keeps M7 dumb and the content reviewable
(the linter can typo-check every drift key).

## Lint rules (registered in lint.py RULES)

- R8 `pin_rank` — rank is a valid M0 Rank name; radiation ≥ 0 integer;
  radiation > 0 requires rank above species.
- R9 `drift` — keys are registered scalar/int axes; numeric values;
  |drift| ≤ 3σ; drift requires radiation > 0.
- R10 `invented_budget` — invented-flagged pins ≤ budget; all invented pins
  small-bodied (≤ 1.0 kg effective).

## Deferred to M7 (backbone integration tests)

- radiation honored (~N descendants, seeded tolerance)
- every pin has relatives (no orphan pins in the built tree)
- authored pin values byte-exact after build (never drifted)
- drift measurably biases descendant direction (existence proof)

## Content delivered

- Texture pins carry rank+radiation (murid rodents f/60, passerine
  songbirds f/80, beetles o/120 — pre-staged in M2).
- `equines` genus pin: horse-grade radiation anchor (radiation 3) with
  cursorial drift — the "horse but faster" demonstrator.
- `coal-rat` invented genus (RFC §4's own example): small-bodied,
  budget-exercising invented clade.
- `[budget] invented_max = 3`.
