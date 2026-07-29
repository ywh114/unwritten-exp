# K14 Flora Engine — Contracts

Build plan: `docs/spec-notes/2026-07-29-k14-flora-build-plan.md` (normative
for scope). This file is the module-boundary contract.

## The partition (same as K13, owner rulings 2026-07-29)

- **Traits** are stored and drift-and-commit: children draw an N-σ cloud
  around the parent's committed record. Clade ranks are lineage points,
  not attractors. No convergence requirements at any rank.
- **Derived** parameters are pure functions of the record, recomputed at
  the end of every build/round (`derive.derive_tree`), never drifted.
- **Metadata** (`[niche]` in presets) is content-only — the baseline for
  `derive.effective_climate`, never stored on nodes.
- All randomness from K1 (`kernel/hashrng`) stage-scoped streams
  (`exp/k14_flora/seeding.py`, root persona "k14").
- No hard caps: height/size sanity is a leaky envelope per plan
  (`forces.py` ENVELOPE pattern), constraint rules are sampler legality
  (like fauna's substrate gates), never post-hoc deletion.

## Pass order (this package, then the world-facing layers)

| Stage | Module | Output |
|---|---|---|
| F0 | `backbone.build` | committed flora Tree (world-blind) |
| naming | `naming.assign_names` (K13 engine, flora grade map) | binomials + folk labels |
| derive | `derive.derive_tree` | derived axes on nodes |
| metrics | `metrics.run_checks` | .report (OK / VIOLATIONS) |
| D0 | `world/derived.py` (P6) | `derived.npz` + `derived.k11pack` in `out/world/seed_N/` (+ manifest) |
| stress | `world/stress.py` (P7) | per-species passable/costly/blocked |
| F1 | `world/dispersal.py` (P8) | per-genus range masks + colonization PNG |
| F2/F4 | `world/cover.py` (P9) | per-cell layer cover mix + provisions |

## JSON schema

Same node/tree schema as K13 (`meta.generator = "k14_flora"`,
`meta.version = 1`). Rank meanings per `model.py` docstring. The K13 tree
viewer (`exp/k13_treegen/viewer/tree.html`) reads K14 JSON unchanged.

## Interface mirroring

`content.load_content/merged_pin/merged_preset`,
`backbone.build(seed, pack)`, `derive.derive_tree(nodes, pack)` /
`derive.effective_climate(node, pack)`, `metrics.run_checks(tree, pack)`,
`__main__ generate(seed, pack)` — identical signatures to K13.
