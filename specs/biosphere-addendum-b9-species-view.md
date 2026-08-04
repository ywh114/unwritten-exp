# Biosphere Addendum B9 — the species view (rewrite layer L1)

**Status:** owner-ruled 2026-08-04 (design briefing + three rulings, this session).
**Depends on:** B7 (flora mass), B8 (capacity accounting), the k15-simdiff
mechanism census (2026-08-04), and the k13 machinery map (agent-9 report, same day).
**Layer:** L1 of the rewrite (plan §5) — the species description. Everything
above L1 reads the view this layer produces and computes nothing itself.

## 1. What L1 is

A species is stored as a flat record of trait values (axes + generics, sid,
g/gen_time, plan/preset refs). L1 turns that record into the **derived view**:
climate envelope, morphology, per-individual biomass (B7 plugs in here), food
provisions, dispersal equipment, display colors, intrinsic stress (§4). One
canonical assembler function; every other layer — occupancy (L2), dynamics
(L3), the game layer's spawn decisions — reads the view. Nothing else derives.

The view is **computed on read, never stored** in the record. The k13 habit
of writing derived values back into `node.axes` (and then guarding the
sampler with `DERIVED_AXES` so it doesn't "evolve" a computed value) dies.
Memoization (stdlib `functools.cache` or plain dict keyed by species/round)
is an implementation detail, applied only where profiling asks.

## 2. Absorbed from k13 (settled design, ported with adaptation)

- **Axis registry** (`k13_treegen/registry.py`): AxisSpec/PlanSpec schema and
  validation — the rent audit (every axis names a consumer), vary-by-default
  (mutable axis must declare sigma), single-size-axis lint, plan permission
  tables. Port as-is; add the L2 biomass/occupancy consumers to the closed
  consumer vocabulary.
- **Species record shape** (`model.py`): flat axes + generics, sid, g,
  gen_time, plan/preset refs. Minus in-place derived writes (§1).
- **Climate envelope** (`flora/derive.py:effective_climate`): pure function,
  traits → envelope + tolerance passthroughs; missing axes read neutral.
- **Mechanical deriveds** (raunkiaer, provision map, clonality class,
  silhouette, pigment-pathway colors): absorb the logic, rebuild the shape —
  view fields, not record writes.
- **Constraint gate** (`flora/constraints.py` + `constraints.toml`):
  data-driven `when → require/forbid` rules, snap-not-delete with an audit
  trail. Remains the legality final word for any mutation path. Note: the
  gate holds thresholds and set memberships only — no proportion rules exist
  anywhere today (census finding); §4 is why that matters.
- **Content pack loading** (plans/presets/pins/bundles/classes).

## 3. Rebuilt / left behind

- **Rebuilt: the canonical view assembler.** Today the derived view exists
  twice — `FloraSim.derive` (k13) and `stress_adapter._view_from_record`
  (k15) are key-for-key copies kept in sync by comments, with `ANCHOR_REF_M`
  literally defined twice. L1 has exactly one assembler; the mirror dies.
  The full ~20-key vocabulary is carried over (owner ruling: pruning is
  easier than adding — adding needs wiring).
- **Rebuilt later (L3): vital rates** (current ones provisional by their own
  docstring) and stress-response routing (the responder *table* is content;
  the select/mutate machinery belongs to dynamics).
- **Left behind:** the k15-era perf patches (`_AxisPlan`, `_toward_map`,
  frozenset trigger caches) — Python-profile artifacts on a wrong-shaped hot
  path; AGENTS.md §6 discounts Python-limited cost.

## 4. Intrinsic stress — proportion-deviation penalties (owner ruling)

L1 owns proportion penalties, not the sim. The derived view carries an
**intrinsic stress** field: graded mechanical costs computed from the
species' own exposed proportions (B7's `MassEstimate.proportions`: dbh,
crown ratio, root-shoot, sward density, …) against viable envelopes.

- **Graded, not gated.** A 200 m cactus with a 55 cm crown is not illegal;
  it is chronically self-stressed. The constraint gate (§2) stays what it is.
- **Plateau-with-cliffs, not a bowl (owner ruling 2026-08-04).** The penalty
  curve is essentially flat across the viable envelope — at most a very weak
  leakage so grossly different body plans are not *perfectly* equal — and
  rises sharply only when proportions are very bad. A smooth gradient
  everywhere would hill-climb every lineage toward the same optimal body
  plan (carcinisation) and kill diversity; inside the envelope, drift and
  the ordinary forces must dominate.
- **Many intrinsic stress types, each an ordinary scalar (owner ruling
  2026-08-04).** Intrinsic stress is not one thing and not a new
  mechanism: it is a family of stress types — mechanical support (canopy
  vs trunk), energetics (size vs storage), and successors — each a scalar
  stress exactly like drought or cold, each flowing through the existing
  **stress → derived → trait** paradigm. The only novelty is what the
  stress reads: the organism's own proportions, exposed through the
  derived view (stresses never touch raw axes), instead of the cell's
  environmental fields. Each type carries its own plateau-with-cliffs
  curve, its own vital cost, and its own responder wiring onto traits —
  toward the nearest envelope edge, never a point optimum. Environmental
  stressors reuse the same derived quantities (wind reads the support
  proportions, nutrition the storage proportions), so the bookkeeping is
  computed once in the view and read by every stressor, intrinsic or
  environmental.
- **One channel.** L3 sums intrinsic stress (from the view) and environmental
  stress (from the cell) through the same stress machinery — to the sim, a
  self-stressed cactus looks exactly like a droughted oak, differing only in
  provenance. The sim never special-cases proportions.
- **Authored exception bubbles (owner ruling 2026-08-04).** The viable
  envelope per stress type is default region ∪ authored exception
  bubbles: a pin whose proportions lie outside the default envelope
  (giraffe, parasitic flower-only plants) carries an authored bubble —
  center = the pinned proportions, radius per stress type — as part of
  its content record. Bubbles are AUTHORING, never generated: the
  sampler cannot mint them, so monsters cannot be laundered through
  self-granted exemptions. Descendants inherit the bubble; drift inside
  it is free (the clade radiates around the pinned form), drift beyond
  its edge meets the normal cliff. Bubbles are per stress type and
  independent (a support bubble implies no storage bubble).
- **Equal footing.** Fauna exposes the identical field from its morphology
  hook (fauna's morphometrics axes are the same kind of proportion knobs).
- **Acceptance case:** the B8-probe cactus (`succulent.cactus` at the
  height ceiling holding 92% of world biomass) must accrue decisive
  intrinsic stress through this channel alone.

## 5. Nomenclature (owner ruling 2026-08-04)

The naming engine (`nomenclature.assign_names`) works but was never wired
into the round loop — k15 divides carry NULL binomials, which blocks the
owner's "what IS this species" goal. Ruling: **the naming pass runs once, at
the final round**, over the committed tree; intermediate debugging reads the
final artifact and uses the final names. L1's only obligation is to keep the
record fields the naming pass reads (salient axes, genus context). Naming
stays its own module.

## 6. Debug hook

`describe <species>` — prints the full derived view in human terms: what it
is (binomial, plan, salient traits), its climate envelope, its mass and
proportions, its intrinsic stress and why, what it offers and how it
disperses. This is the encyclopedia entry and the note-3a "what is this
species" answer in one.

## 7. Interface discipline (standing rulings, restated)

The assembler is written once against `OrganismHooks`
(`k15_biosphere/interface.py`); flora/fauna differ only inside hook
implementations. The per-cell per-lineage biomass density field remains the
canonical sim output; the derived view is what the game layer (engine L1/L2)
reads for spawn probability, location, and amount.

## 8. Acceptance invariants (test contract, fast tier unless marked)

- One assembler: no second derive path exists in `k15_biosphere`.
- Views are pure: assembling a view never mutates the record; two assemblies
  of the same record are equal.
- Registry validation rejects: a mutable axis without sigma, a consumer
  outside the closed vocabulary, a second size axis.
- The full carried-over key set is present in every flora view.
- Intrinsic stress: zero for in-envelope proportions; strictly increasing
  with deviation; decisive for the cactus acceptance case.
- Constraint gate: idempotent; snaps audited; never deletes.
- `describe` output contains the binomial slot, mass, and every intrinsic
  stress term with its cause.
