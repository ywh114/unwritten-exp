# K13 Flora Tree — Contracts

Build plan: `docs/spec-notes/2026-07-29-k14-flora-build-plan.md` (normative
for scope). This file is the module-boundary contract of the flora tree
(the flora half of the unified K13 tree-of-life engine; the world-facing
layers live in `exp/k14_worldprod/`).

## The partition (same as K13 fauna, owner rulings 2026-07-29)

- **Traits** are stored and drift-and-commit: children draw an N-σ cloud
  around the parent's committed record. Clade ranks are lineage points,
  not attractors. No convergence requirements at any rank.
- **Derived** parameters are pure functions of the record, recomputed at
  the end of every build/round (`derive.derive_tree`), never drifted.
- **Metadata** (`[niche]` in presets) is content-only — the baseline for
  `derive.effective_climate`, never stored on nodes.
- All randomness from K1 (`kernel/hashrng`) stage-scoped streams
  (`exp/k13_treegen/flora/seeding.py`, root persona "k14").
- No hard caps: height/size sanity is a leaky envelope per plan
  (`forces.py` ENVELOPE pattern), constraint rules are sampler legality
  (like fauna's substrate gates), never post-hoc deletion.

## Pass order (the flora tree)

| Stage | Module | Output |
|---|---|---|
| F0 | `backbone.build` | committed flora Tree (world-blind) |
| naming | `naming.assign_names` (K13 engine, flora grade map) | binomials + folk labels |
| derive | `derive.derive_tree` | derived axes on nodes |
| metrics | `metrics.run_checks` | .report (OK / VIOLATIONS) |

## JSON schema

Same node/tree schema as K13 fauna (`meta.generator = "k13_flora"`,
`meta.version = 2`). Rank meanings per the `exp.k13_treegen.model`
docstring. The K13 tree viewer (`exp/k13_treegen/viewer/tree.html`)
reads flora JSON unchanged.

## Interface mirroring

`content.load_content/merged_pin/merged_preset`,
`backbone.build(seed, pack)`, `derive.derive_tree(nodes, pack)` /
`derive.effective_climate(node, pack)`, `metrics.run_checks(tree, pack)`,
`__main__ generate(seed, pack)` — identical signatures to K13 fauna.
