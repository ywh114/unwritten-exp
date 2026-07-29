# Constraint solver design — levels, records, and the unwritten (2026-07-28)

**Status:** design note from the Overpass-QL brainstorm (user discussion,
2026-07-28). The game needs an Overpass QL-like constraint solver; the
open question was at what LOD level (L0/L1/L2) it lives. Answer: above
the levels, over located records — and the interesting half is what it
answers when the world hasn't decided yet.

## 1. The solver sits above the levels

Overpass QL works because OSM has ONE data model (nodes/ways/relations
with tags). Our levels have three: L0 dense raster fields, L1/L2 chunk
structures + entities, quantity-layer records. Picking a level means
picking a model and losing the rest. The unifying substrate already
exists: **everything in the engine is a located record** (a value, at a
place, at a resolution, committed).

- Dense raster fields = dense located records.
- Rivers/lakes/peaks/marks = sparse located records (geometry + tags).
- Entities/structures (L1/L2, humanoids) = sparse tagged records.
- Chunk summaries (L1/L2 projected upward) = chunk-resolution records.

The cell↔chunk↔pixel hierarchy makes spatial joins arithmetic
(containment is a merge join, not a search).

**Level is query-planner metadata, not a design choice.** A query
compiles to the coarsest tier that carries all its fields
(`biome == taiga & elev_m > 2000` runs at L0); spatial relations over
fine structure (`creek within 50m`) force drill-down into finer tiers —
and find answers only where such records have been committed. Overpass's
`around` is the same move: geometric work only where demanded.

The L0 raster tier exists today: `exp/k11_worldgen/mapserver.py`'s
constraint grammar (comparisons + `& | !` parens over delivered-res
fields) is the seed syntax. The K11 map viewer is its demo.

## 2. The ontology: present, absent, unwritten

Correction chain from the discussion (user, increasingly sharp):

1. ~~Truth layer has the full record set.~~
2. ~~Minor structures have counters (quantity layer estimates).~~
3. **Minor structures may not even have counters.** Gen-time commits only
   the major layer (cities, paths, ports, named structures). A village's
   interior is simply *unwritten* — no records, no counts, nothing.

So the query semantics are **three-valued**, and the third value is the
one the engine already knows (K7's trust-undecidable register):

- **present** — committed records (exact answer).
- **absent** — committed emptiness (exact answer: known zero).
- **unwritten** — the question is not yet decidable. Not SQL NULL
  ("unknown value") — the world itself hasn't decided.

Aggregates over mixed territory return bounded answers ("3 committed +
unwritten remainder"), never silent pretend-precision.

## 3. Query-vs-generate duality

When gameplay needs an answer the world hasn't earned, that's not a
query — it's a **generation act**. The same machinery (fields +
constraints + spatial relations) is the oracle that mints
constraint-consistent records on demand ("an inn here, near a road, not
in the river"). Afterwards the query has a committed answer, and the
promise ledger records the obligation the answer created.

One solver, two modes; the unwritten state tells you which mode you're
in. A game system that can't act on a bounded answer must force the
generation act first — never weaken the answer.

This is C2 backfill pointed at space instead of time: backfill generates
a past consistent with everything committed since; spatial refinement
generates a present consistent with everything committed around. Same
discipline, same consistency requirement, same engine underneath.

## 4. Two namespaces

Even over committed records, an Overpass question has two scopes:

- **World scope** — everything committed (by any process).
- **Observer scope** — what a given observer (player, NPC, faction) has
  committed through measurement/gossip: bounded, possibly wrong,
  possibly stale. OSM's answers are public record; ours are perspectival.

Structure records carry commitment provenance (world / which observer)
so the planner can scope. The knowledge layer is the gossip system's
spatial face (K6).

The zoom/measurement principle closes the loop: fine detail only exists
where it was committed — so a solver over committed records
automatically sees exactly as much fine detail as the world has earned.

## 5. Sequencing and open questions

- **Now**: L0 raster tier (built). Sparse-structure tier prototypes on
  what L0 already has (marks, river polylines, lake masks) — cheap,
  present, and the same shape as future humanoid structures.
- **With L1/L2**: structure-record schema (geometry, tags, resolution,
  commitment provenance). Pin the two-namespace rule BEFORE records
  accrete — retrofitting provenance onto a query engine is painful.
- **Deferred to L1**: whether `near`/`along` relations are computed
  geometrically at query time (lean: yes, with chunk-local caching) or
  pre-materialized as adjacency records on commit (stale-on-change).
- **Rejected alternatives**: L0-only with upward summary projections
  (commits the projection schema too early — summaries become just
  another record type, added lazily); per-level solvers with a shared
  grammar (cross-level queries become second-class forever); full
  federation now (speculative machinery for levels that don't exist).
