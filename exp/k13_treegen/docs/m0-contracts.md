# M0 — contracts interface (FROZEN)

Implements integration contract **C2** (state) and **C3** (determinism) from
`docs/spec-notes/2026-07-27-k13-v2-integration-contract.md`. Every other
module imports `exp.k13_treegen.model` and `exp.k13_treegen.seeding` and signs
these types. **Do not change this module after M1 starts** — changes here are
schema migrations for every downstream module.

## Types (`model.py`)

- `Rank` — `KINGDOM(0) PHYLUM(1) CLASS(2) ORDER(3) FAMILY(4) GENUS(5)
  SPECIES(6)`; `RANK_PREFIX` = k/p/c/o/f/g/s. The tree is kingdom-rooted
  (single `animalia` root; `plantae` reserved).
- `Quantity` / `QuantityStore` — RFC §11 store `(location, metric) ->
  (value, provenance, round)`. Interface: `set / get / value / accumulate /
  expire`. `location == ""` for non-spatial metrics (all of v2). **Reserved
  empty in v2** so ranges/ghosts/scores/ley-energy land later with no
  migration.
- `NameRecord` — `{binomial, folk=null, history[]}`. M8 seam; `folk` reserved;
  committed only at final round.
- `Provenance` — `{kind: "regular"}` or `{kind: "lifted", source_id, site_id,
  round}`. Ley-lift seam; `regular` in v2.
- `Node` — `path, rank, parent, sid, plan, preset, label, g, gen_time, axes,
  generics, flags, edge_delta, name, provenance, quantities`. `axes` holds
  every plan-scoped `AxisSpec` value (M1); `generics` maps generic →
  realization id; `flags` are committed boolean tags.
- `Tree` — `seed, nodes{path→Node}, meta`; `add` (dup path raises),
  `children`, `roots`, `to_json/from_json`, `dumps` (canonical: sorted keys,
  byte-stable).
- `rebind(generics, generic, realization, permissions, force=False)` — one
  mechanism, two permission levels. Regular rebind checks the plan permission
  table (`permissions: {generic: [realizations]}`) and raises `RebindError` on
  an unknown generic or illegal realization; `force=True` (ley) rebinds across
  plan limits.

## Seeding (`seeding.py`)

One master seed; substream tree mirrors the pipeline DAG; every independent
field gets its own `child(context)` (K1 keys draws by (clock, index) only).
`root_stream(seed)`, `stage_stream(seed, *path)`, `naming_stage(seed, round)`,
and canonical stage paths `STAGE_BACKBONE / STAGE_PINS / STAGE_WEAK_BINDINGS`.
Stage-boundary replay: a stage stream is keyed by (seed, stage-path) alone, so
re-running a later stage from a committed tree is deterministic and
independent of earlier stages.

## Reserved seams (deferred features, no migration later)

quantity store (ranges/flags/ghosts/scores/ley-energy) · `Node.provenance`
(ley lift) · `NameRecord.folk` (folk-name layer) · slots as string enums
(illustration; `plan.anchors` will be added by the illustration layer, not
here — presets are proportions, not anchor coordinates).

## Tests (`test_m0.py`)

Round-trip identity (Node, Tree, Quantity/Name/Provenance); `dumps`
byte-stability; duplicate-path rejection; `children`/`roots` ordering;
quantity `set/get/accumulate/expire`; `rebind` allowed / illegal / unknown /
force; seeding determinism + child independence; a K1-driven random-tree
property test (round-trip). K1-only: no `random`/`uuid`/`time`.
