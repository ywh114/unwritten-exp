# K13 v2 — integration contract & M1 axis schema

**Status:** design (2026-07-27). Companion to
`2026-07-27-k13-v2-rebuild-plan.md`. The plan defines modules as **vertical**
slices (each self-contained, each rigorously tested). This document supplies
the **horizontal** contracts that cross every module — the shared types, the
seed discipline, and the reserved seams. v1 failed at exactly this layer: its
modules were individually sound and did not compose. The rule: **nail these
three horizontal contracts before any vertical module is built; every module
signs them.**

## 1. Compositionality evaluation

The deliverable composes iff three horizontal contracts are fixed and every
module reads them rather than reinventing per-module knowledge:

- **C1 — the data schema** (`AxisSpec` / `Registry`, §3). The keystone. M5's
  sampler, M6's couplings, M8's naming, and M12's renderer all dispatch on
  per-axis metadata. If M1 doesn't carry it, each downstream module invents
  its own and they drift. *Highest risk.*
- **C2 — the state** (`Tree` / `Node` + quantity store, §4). The accumulating
  object every stage reads and returns, plus the reserved store for deferred
  features (ranges, flags, ghosts, scores, ley provenance).
- **C3 — determinism** (master-seed / substream discipline, §5). Whole-DAG
  byte-identical replay and stage-boundary re-runs.

Vertical modules (M0–M12) are necessary; these three are sufficient for
composition. The end-to-end gate (§6) is the proof.

## 2. Pipeline DAG & handoff types

Stages are pure functions over committed inputs; the `Tree` accumulates; the
`Registry` is built once and read-only thereafter.

```
load_content(dir)            -> ContentPack          [M2/M9]
build_registry(pack)         -> Registry             [M1]   validates content vs schema
build_backbone(seed, reg, pack) -> Tree              [M7]   uses M5 sampler, M6 couplings, M4 pins
name_pass(tree, reg, round=0)-> Tree                 [M8]   tentative; re-run per diffuse round
describe(tree, reg)          -> Tree (+ reports)     [M12]
persist(tree, out)           -> artifacts            [M9]   TOML in, JSON tree + text out
```

Handoff types (defined in M0, imported everywhere):

- `ContentPack` — `{plans, presets, pins, allometry, couplings}` + axis
  references; raw authored TOML, not yet validated.
- `Registry` — `{axes: dict[name -> AxisSpec], plans: dict, salience_order,
  grammar_index}`; the validated, consumer-ready view of the schema.
- `Tree` — `{seed, meta, nodes: dict[path -> Node]}`; canonical JSON via
  `dumps()`.
- `Sampler` (M5) — `draw(parent_value, spec: AxisSpec, stream, dg) -> value`,
  a pure dispatch on `spec.mutation.kind`.
- `Coupling` (M6) — `apply(node, reg, stream) -> None` (in place), covering
  gates / tradeoffs / anticorrelate / bundles / per-world weak bindings.

No stage reaches into another's internals; everything crosses these types.

## 3. C1 — `AxisSpec` (the M1 keystone, complete)

Every axis (B1 knob or flat vocabulary axis) is one record. This is the
contract M5/M6/M8/M12 sign.

```
AxisSpec:
  name: str
  block: morphometrics | patternation | niche | diet | life_history
       | behavior | ecosystem | sex_age_season
  tier: invariant | steady | labile        # three-tier taxonomy
  value_type: scalar | int | enum | bool

  # ── mutation semantics (M5 sampler dispatches on kind) ──
  mutation:
    kind: gaussian | log_gaussian | enum_redraw | ratio | none
    sigma: float          # vary-by-default σ; relative for log_gaussian
    states: [str]         # required iff kind == enum_redraw
    bounds: [lo, hi]      # leaky; required for scalar/int
  clade_steady: bool      # blacklist; true ⇒ kind forced to none
  plan_scope: [plan_id] | "all"

  # ── consumer metadata (what downstream reads) ──
  consumers: [stress | drift | runaway | id | name | tell | pop | draw]
  salience: float         # M8 epithet-selection weight; M12 salient-part pick
  grammar_role: size | covering | grade | diet | part | none   # M12 template slot
  coupling_triggers: [coupling_id]   # M6: movement of this axis fires these

  # ── B1 v0.3 ──
  unit: dimensionless | mass      # lint: only the single mass axis may be 'mass'
  temporal_modifier: none | juvenile_only | seasonal | age_ramped | breeding_male
  sex_linked: bool
```

**M1 validation (tests):** every axis has tier + mutation + unit + ≥1
consumer; `tier == invariant ⇒ mutation.kind == none`; `unit == mass` for
exactly one axis; `kind == enum_redraw ⇒ states non-empty`; scalar/int ⇒
bounds with lo < hi; `plan_scope` non-empty; `temporal_modifier` ≤ 1 per axis;
every `coupling_trigger` resolves to a registered coupling.

**Consumer guarantee:** M5 never special-cases an axis name — it dispatches on
`mutation.kind`. M8 selects epithets from axes ordered by `salience` among
those accessible at backbone time. M12 fills its template by `grammar_role`.
M6 fires on `coupling_triggers`. If a future consumer needs new per-axis data,
it is added here, once, not per module.

## 4. C2 — `Tree` / `Node` + reserved quantity store

`Node` (committed record):
```
path, rank, parent, sid, plan, preset, label,
g, gen_time,
axes: dict[name -> value],      # all AxisSpec values, plan-scoped
generics: dict[generic -> realization],
flags: list[str],
edge_delta: dict,
provenance: "regular" | {lifted: {source_id, site_id, round}},  # reserved; "regular" in v2
quantities: dict[(location, metric) -> (value, prov, round)],   # RFC §11 store; empty in v2
```

**Quantity store (the critical reservation).** RFC §11's state architecture is
records + quantity layers: `(subject, location, metric) -> (value, provenance,
round)`, one interface (`get/set/accumulate/expire`). Flags are 0/1
quantities; new mechanics are new keys, no migrations. v2 is world-blind so the
store is empty, but the field + interface exist now so **ranges, ghost ranges,
flags, scores, and ley-energy terms land later without a schema migration.**
This is the single most important deferred seam.

**Other reserved seams:**
- **Range prior:** `Node.axes` carries the niche vector; future range fields
  are quantity layers keyed `(species_id, patch, "presence")` with the niche
  vector as prior. No range code in v2; the prior is committed.
- **Ley lift:** `generics` carry rebind permissions (M0); `provenance`
  reserves the lift record. No lift code in v2.
- **Folk names:** name record (M8) = `{binomial, folk: null, history: [...]}`;
  `folk` reserved null until the folk layer.
- **Illustration (honest):** slots stay string enums. Presets are knob
  *proportions*, NOT anchor coordinates — do not claim they double as drawing
  parameterization. Reserve `plan.anchors` (empty in v2); anchor placement is
  separate tune-once-per-plan work (RFC §10.5). Grade points feed proportions
  only.

## 5. C3 — master-seed / substream discipline

One master seed; the substream tree mirrors the pipeline DAG. Every
independent random field gets its own `child(context)` (K1 conflict-log
lesson: same stream + same coordinates = identical draws).

```
Stream(seed, "k13")
  .child("backbone")
    .child(f"phylum.{frame}").child(f"class.{plan}").child(f"order.{preset}")
      .child(f"family.{i}").child(f"genus.{j}").child(f"species.{k}")
  .child("pins")
  .child("couplings.weakbind")        # per-world seeded weak bindings
  .child(f"naming.round.{r}")         # stage-boundary replayable
```

**Guarantees (tests):** whole-DAG re-run byte-identical; re-running
`naming.round.r` from a committed tree is deterministic independent of
backbone draws (stage-boundary replay, RFC §7); per-world weak bindings differ
across seeds.

## 6. End-to-end integration gate

`test_integration.py` — runs after all modules; the composition proof. Over
seeds {1, 2, 3}:

1. Whole-DAG re-run byte-identical.
2. Tree invariants: single `animalia` root; strict rank order; g monotonic
   root→leaf; unique paths/sids.
3. **Freeze check (whole tree):** no axis is constant across all species of an
   order unless `clade_steady` or `tier == invariant` — the v1 bug, checked at
   composition scale, not per module.
4. Diversity metrics within tolerance (M11): median sister distance ≈ σ;
   within-order variance ≫ 0; between-order > within-order.
5. Couplings compliant whole-tree; the 3 rejected rules absent.
6. Every species has a tentative name (well-formed, within-genus unique) and a
   description that parses and matches the record.
7. **Planted-violation seed:** corrupted content (crocodile-on-monkey, a
   frozen labile axis, an absolute-unit knob) must fail the gate.

## 7. Build-order consequence

M1's `AxisSpec` (§3) and M0's `Node`/quantity store (§4) are specified **first
and frozen** — they are the contracts every other module doc references. No
vertical module doc (`docs/mN-*.md`) is written until it can cite these two
verbatim. The seed discipline (§5) is fixed alongside M0.

## 8. Storage ruling (user, 2026-07-28)

**TOML is for configuration only** (the authored content pack: axes, presets,
pins, palettes, allometry, plans). **Persisted/generated data is JSON** — the
committed tree dump (`Node.to_json`), quantity store, reports — with **NPZ
reserved for dense arrays** if a module ever produces them (the K11 worldgen
pattern). No TOML output, no JSON config. M9's "TOML content in, JSON tree
out" is the same ruling restated.
