# Comprehensive plan — flora finalization and the rewrite

**Status:** APPROVED 2026-08-04, decisions D1–D4 as recorded in §9.
Supersedes the ticket-by-ticket drift of July/August: the open queue
is triaged against this plan (section 8).

## 0. The bottom line (from scratch/note)

k15's goal is to produce a diverse, self-consistent distribution of
thousands of species procedurally. Species are parametric — described
by numbers, not hand-built — for computation, diversity, and display.
Real-world resemblance is emergent, not literal: it exists to give
the player a sense of familiarity and correctness, so exploration
feels like completing an encyclopedia.

Every phase below must earn its place against three lenses (owner
ruling 2026-08-04):

1. **Is it clean?** One mechanism per job; no layers of ad-hoc
   filters bolted onto an intermediate design.
2. **What is its debug surface?** Every feature ships with a way to
   see what it did — a hook, a dump, a query. If a feature cannot
   name its debug surface, it is not designed yet.
3. **Does it serve the bottom line?** If the answer needs more than
   one sentence, defer it.

## 1. The split: what happens to the current engine

The rewrite replaces the k15 simulation engine and the flora content
generation around it. Until it lands, the current engine stays useful
as the **reference implementation**: the baseline whose behavior the
rewrite must reproduce or beat, and the thing we probe while designs
are validated.

Consequence (decision D2 below): no more *feature* work on the
current engine. Cadence/staged rounds (ticket 0019), bundle-breakup
(0027), and metadata persistence (note item 6) are rewrite
requirements, not patches — building them twice is the definition of
unclean. Only three things still touch the current engine:

- the debug tool (ticket 0038) — needed NOW to probe old artifacts;
- the 12-cell patch-floor removal (ticket 0039) — approved small
  genesis naturalness fix;
- one slow-gate re-pin run, so the reference implementation freezes
  fully green.

## 2. Phase 0 — make the current engine legible (small, now)

**0a. The debug tool (0038).** One command-line tool that answers
*any* question the persisted artifact can answer. Not a stats script
with a fixed menu: it loads a run's output (species densities, the
amended species tree, the event log) and answers compositional
questions first — "how many species share at least 30% of this
species' cells?", "which biomes does it occupy and with whom?" —
plus identity ("what is this species — name, salient features"),
range (cell count, substrate mix, connectedness, patch sizes), and
tuning questions ("what fraction of a cell's capacity does one
species typically hold?" — note item 2a). Built against the current
artifact schema; the rewrite keeps that schema family, so the tool
survives. Debug surface: it *is* the debug surface — its own test
suite runs canned questions against a seed-1 artifact.

**0b. The patch-floor removal (0039).** The 12-cell minimum that
drops tiny genesis patches goes away entirely (the neighbor-joining
that makes speckles cheap was verified universal). Debug surface:
the before/after delta reported through tool 0038 (speckle instance
count, occupancy change).

**0c. Slow-gate re-pin.** One background slow run to re-pin the four
tests the sessile-fauna deletion moved (list in commit 894b538).
After this, the current engine is frozen green.

Optional, cheap: stamp round numbers into the current event log
(today "which species split at which round" is only recoverable by
counting entries in order). A few lines; makes old runs
interrogable during validation. Include unless you say no.

## 3. Phase 1 — finalize flora's design: morphology and mass

The note: "We should properly finalize flora before starting. What
flora needs: Morphology and mass." Finalize means the DESIGN is
locked and reality-checked — not plumbed into the dying engine.

**1a. Real allometry research (ticket 0035).** For every growth
form — trees, shrubs, herbs, grasses, kelps, mosses, fungi — a
formula that computes one organism's biomass from the axes the
species description already carries (height, crown spread, wood
density, body plan). No new authored mass number: mass is DERIVED
from morphology, by standing owner ruling. Sources cited before any
formula is written.

**1b. Standalone reality check (note item 4).** A small harness that
feeds real organisms' dimensions into the formulas and compares
against real-world figures: an oak stand's tonnes per hectare, a
grass sward's ground cover versus its biomass, a kelp bed's density.
If the numbers are wrong, the formulas are wrong — caught here, not
inside a simulation. Debug surface: the harness itself prints
expected-vs-computed per case; it stays as a permanent test of the
formulas.

**1c. Lock the formulas in a spec section** (short, big-picture:
what each formula means and what real numbers it was anchored to —
not a code dump). Tickets 0035 and 0031 close into this; the
mass-is-biomass plumbing lands ONCE, in the rewrite (decision D1).

## 4. Phase 2 — the biomass/coverage design (note: "serious thinking")
**DELIVERED 2026-08-04 as addendum B8
(specs/biosphere-addendum-b8-capacity-accounting.md): two-level
accounting (cell pool at X=400 t/ha per productivity unit,
provisional; lineage cap < pool, substrate-structured with spill,
NOT a simple fraction — the A/B understory emergence case is the
acceptance test; mixing term TBD). Probe evidence + the 200 m
cactus (proportion-guard motivation) recorded in B8.**

The note's demand: biomasses must make sense and tune with NATURAL
knobs — never per-species fiddling. A grass sward's capacity is
limited by the ground it can cover; a tree's by the light its crown
intercepts. The pieces exist; the design must make them one honest
system:

- The world provides per-cell productivity (from k11, unchanged).
- Each species' share of a cell comes from what substrate it can
  root in (already so) — but the percap demand weight (today:
  crown² × (1+woodiness), a stub) becomes the Phase-1 biomass, so
  "cell demand" literally becomes "biomass present", and capacity
  pressure becomes physical crowding.
- Investigate with tool 0038 on current artifacts BEFORE designing:
  what share of a cell one species typically holds (2a), how close
  the biggest species sit to 100% — an oak taking a whole cell is
  as unrealistic as it sounds.

Deliverable: one spec section — the accounting, its knobs (few,
physical: productivity, substrate, crown geometry), and the real
numbers it reproduces. This is the foundation layer of the rewrite,
which is why it gets its own phase and its own reality check.

## 5. Phase 3 — the rewrite, layer by layer

In-repo (decision D3), as a new module beside k11–k15 — named
**`exp/k15_biosphere/`** by the owner (D4): flora and fauna on equal
footing from day one, with clean
modular splits where they differ (sessile fauna comes home here,
discovered by the fuzzy finder — the query-by-description facility —
not by special cases).

Order follows the note's rule: most-important first, and each layer
is written so that correcting a LOWER layer never makes a HIGHER
layer's parameters lose meaning. That means the layers go bottom-up:

- **L1 — the species description.** Parametric species → derived
  view (morphology, biomass from Phase 1, stress tolerances). The
  single source every other layer reads. Debug hook: `describe
  <species>` prints the full derived view in human terms — this is
  also "what IS this species" for the encyclopedia feel.
- **L2 — occupancy.** Biomass/coverage accounting from Phase 2;
  cells, capacity, demand. Debug hook: the per-cell balance sheet —
  who holds what share and why, for any cell.
- **L3 — dynamics.** Population change, stress verdicts, dispersal.
  Debug hook: single-instance trace — one species' round-by-round
  ledger of births, deaths, stress causes, propagules sent/received.
  (Today's engine has nothing like this; it is the single biggest
  debugging gap.)
- **L4 — evolution.** Speciation, merging, the generation-distance
  currency (the `g` machinery from the specs — reused as research,
  rewritten as code). Debug hook: the event ledger gains round
  stamps and full provenance — note item 6 is BUILT IN here, not
  patched on: which species got subspecies at which round, what
  bundle broke into what, answerable by reading a field.
- **L5 — orchestration.** Rounds, staged seeding, freezing. Ticket
  0019's requirements land here as designed, not retrofitted:
  different kinds seeded in separate rounds (first round = important
  flora individuals + sessile fauna); a freeze that stops an
  instance's own dynamics INCLUDING propagation while its downstream
  effects (shade, occupancy, demand) stay live that round;
  deterministic unfreeze triggers. Debug hook: the round report —
  per stage and per round, who ran, who was frozen, and why.
- **L6 — the artifact.** One deterministic output per run; schema
  compatible with tool 0038, so the debug story is identical for old
  and new runs — which is also how the rewrite proves it reproduces
  the reference implementation where it should.

Tests are filed fast/slow AT WRITING TIME (note's pain point), each
layer's tests inside its module. Content — actual trees, grasses,
flowers, deep-sea sessiles — stays the LOWEST priority per the note:
scaffolding first, content drops in once the hooks show the
scaffolding is natural.

## 6. Phase 4 — validation, then content

Rewrite validation is comparative: same world, same seed, old vs
new, judged through tool 0038 — diversity, coexistence structure,
range naturalness, biomass realism. Only when the scaffolding
passes those eyes does content authoring resume (and the deleted
coral/sponge set returns, fauna-side, through the fuzzy finder).

When k15_biosphere is done, `exp/k15_simdiff/` and the orphaned
`exp/k15_descent/` are REMOVED (owner ruling, D4).

## 7. Cross-cutting cleanups

- **Specs:** this document sits on top; the addendum pile gets one
  pass — superseded material is marked, not silently kept (the
  sessile-fauna supersession is the template). Future specs stay
  big-picture; implementation detail lives in code and tickets.
- **Queue:** section 8 below.
- **Subagent friction (note's pain point):** each rewrite layer is a
  clean module boundary = a safe subagent assignment with a named
  debug hook to prove its work. The "tens of minutes in a quagmire"
  problem is treated as a design flaw of the codebase, fixed by the
  rewrite's structure, not by tougher subagents.

## 8. Queue triage (executed 2026-08-04)

| Ticket | Read | Proposed disposition |
|---|---|---|
| 0005 relaxation cadence | cadence is rewrite L5 | close → design info into 0019 note |
| 0007 content debt | content is Phase 4 / lowest priority | close → one-line content ledger in this spec |
| 0014 sim at 128² | scale target for the rewrite | close → target into Phase 4 criteria |
| 0019 cadence/staged | rewrite requirement, already annotated | keep open as rewrite L5 spec input |
| 0021 sim parallelization | rewrite performance concern | close → note into L5/L6 |
| 0026 layer-partitioned capacity | folds into Phase 2 accounting | close → design info into Phase 2 spec |
| 0027 rare species final pass | bundle breakup = rewrite L4/L5 | close → goal into L4 provenance requirement |
| 0031 mass = biomass | implemented once, in rewrite | close → folded into Phase 1/2 |
| 0033 coverage audit followups | verify via 0038 in Phase 0; rest folds | close after 0038 lands |
| 0035 allometry research | the Phase 1 driver | keep open, becomes Phase 1 |
| 0036 fauna stress/morphology | fauna-era design constraint | keep open, tagged rewrite-era |
| 0038 debug tool | Phase 0 | keep open |
| 0039 patch-floor removal | Phase 0 | keep open |

Closures carry their design information into this document or the
tickets that survive — nothing is just deleted (note's ruling).

## 9. Decisions (owner, 2026-08-04)

- **D1 — ONCE.** Research and reality-check now (Phase 1); the
  mass-is-biomass plumbing is implemented only in the rewrite.
- **D2 — YES.** The current engine freezes after Phase 0; 0019/0027/
  note-6 are rewrite requirements, not patches.
- **D3 — NEW MODULE** in this repo.
- **D4 — `k15_biosphere`.** When the rewrite is done, remove
  `exp/k15_simdiff/` and the orphaned `exp/k15_descent/`.

## 10. First concrete steps (in flight since 2026-08-04)

1. Ticket 0038 (debug tool) — briefed to a subagent with the
   artifact schema and the question classes above.
2. Ticket 0039 + the slow-gate re-pin run, in parallel.
3. Ticket 0035 research begins (subagent-friendly: sources first,
   formulas second).
4. The queue triage of section 8 executes as approved.
