# K9 — complex — the topological data structure

## Goal

Implement A2 §1's topological complex — nodes (0-cells), edges (1-cells with
arc-length parametrization), patches (2-cells carrying one DriftField each),
plus incidence relations.  Layer on the three-state cover, composable spatial
constraint predicates, subdivision that never rewires, a commit-time defect
audit, and append-only versioning that makes changes commits, never edits.

Pure logic, no LLM.  Deterministic — no random, uuid, or wall-clock.

## API

Library home: `kernel/complex` (promoted 2026-07-21 per lab spec §6).

### cells — nodes, edges, patches, incidence

- **`Node(id, pos)`** — 0-cell: settlement, crossroads, ford, bridge, cave mouth.
- **`Edge(id, node_a, node_b, length, kind, quality, polyline)`** — 1-cell.
  `polyline` is used *only* for the self-intersection defect check; dynamics
  (K8's business) use arc length.
- **`Patch(id, field: DriftField, boundary_edges, measure, parent)`** — 2-cell.
  `parent` is set by subdivision.
- **`Complex(nodes, edges, patches)`** — the committed structure.
  - `neighbors(node_id)` → adjacent node ids.
  - `patch_at(patch_id)` → Patch.
  - `shared_boundary(p1, p2)` → set of shared edge ids.
  - `graph_distance(a, b)` → BFS shortest-path length over nodes+edges.
  - `degree(node_id)` → edge degree of a node.
  - `patch_adjacency()` → patch-id → set of adjacent patch ids.

### cover — three-state cover and the prime directive

- **`CoverState`** enum: `UNREFINED` (summonable), `REFINED_UNOBSERVED`
  (subdivisible), `OBSERVED` (terminal — immutable except by events).
- **`transition(before, after)`** — validate; raises ValueError on illegal step.
- **`summon_eligible(cells, cover) → bool`** — true iff no cell in the set is
  `OBSERVED` (A2 §1.2 prime directive, topological form).
- **`latent_rot(constraint_cells, cover, min_measure, complex) → bool`** —
  true when unrefined measure in the constraint set drops below `min_measure`
  (A2 §1.2 crisp latent rot).

### constraints — composable spatial predicates (C5 input)

- **`sector(origin, direction, fraction)`** — patches whose centroid falls in
  the named fraction band of the map extent.
- **`adjacent_to_edge_kind(kind)`** — patches sharing a boundary edge of the
  given kind ("river" = drainage-adjacent).
- **`distance_band(node_id, min_d, max_d)`** — graph-distance band from a node.
- **`AND(*constraints)`** — intersection.
- **`evaluate(constraint, complex) → set[str]`** — patch ids.
- **`measure(complex, cells) → float`** — total measure of a patch set.

### refine — subdivision, never rewire

- **`split_patch(complex, patch_id, children, new_edges) → commit`** —
  children get `parent=patch_id`; child measures must sum to parent's (1e-9).
  New detail edges live inside the parent's boundary.
- **`split_edge(complex, edge_id, at_s, new_node) → commit`** — inserts a node
  on an edge, producing two child edges.

Existing edges' endpoints and existing patches' incidence are immutable.

### audit — commit-time defect check

- **`audit(complex) → list[str]`** — one string per defect:
  *dangling_edge* (missing endpoint or degree-1 non-terminus),
  *isolated_patch* (unreachable via adjacency),
  *nodeless_intersection* (crossing polylines without a shared node),
  *disconnected_component* (each beyond the first).

### history — append-only versioning

- **`ComplexHistory(initial)`** — append-only commit log.
  - `add(commit)` — append.
  - `at(version) → Complex` — reconstruct (0 = initial).
  - `at_latest() → Complex` — latest version.

Reconstruction equals replaying the commit log from the initial complex.

## Demo

`uv run python -m exp.k9_complex demo --seed 1 [--json]`

Six stages over the clean + defect fixtures:

1. **Audit** — defect variant yields dangling, isolated, nodeless, and
   disconnected-component defects; clean fixture yields none.
2. **Subdivision** — split `east_wood` into 3 children + a detail edge;
   parentage and measure conservation confirmed; original edge endpoints
   preserved (no rewire).
3. **Cover walk** — UNREFINED → REFINED_UNOBSERVED → OBSERVED on one patch;
   illegal reverse and OBSERVED→anything transitions rejected.
4. **Summon-eligibility** — set overlapping OBSERVED cell → ineligible;
   unrefined-only set → eligible.
5. **Latent rot** — "northern third AND adjacent to river" constraint;
   observing the one qualifying patch flips rot from false to true.
6. **Versioning** — `at(0) == initial`, `at(latest)` matches replay,
   children present, parent removed.

Twice with `--json` → byte-identical output.  Exit 0 iff all checks pass.

## Verdict

**works** (2026-07-21).  25 tests: incidence integrity (neighbors,
shared-boundary, graph-distance), subdivision (parentage, measure
conservation enforced, child fields distinct), never-rewire,
split-edge (child lengths sum, degree-2 new node, out-of-range rejected),
cover (3 legal × 6 illegal enumerated), summon-eligibility, latent rot
(flips exactly when unrefined measure < min), audit (each defect class
caught; clean fixture clean; crossing polylines fire but proper
node-shared crossings don't), versioning (at(0) == initial, at(latest)
correct, reconstruction == replay), determinism (fixture identity, audit
identity, demo JSON byte-identical across two runs).

Repo-wide: 239 pass, 3 deselected (slow-marked, expected).

## Spec-notes

### Numbering collision
Per A2 §11 (newer = overwrite, applied 2026-07-21): K9 = complex (the
topological data structure).  The earlier ledger proposal (K8 topo_complex,
K9 worldgen) is superseded.  K8 is now **route dynamics** (edge
first-passage, bridge sampler, competing leak hazards, node flow rates).

### What K8 (route dynamics) consumes from this library
- Edges carry arc length; polyline is used only for the self-intersection
  defect check — dynamics use arc-length parametrization exclusively.
- `graph_distance(a, b)` provides the BFS shortest-path metric for
  route validation and distance-band constraints.
- Permeability fields per boundary (ε values) are not yet represented on
  edges — those will be added as edge decorations in K8.

### What C5 (latent summon) consumes from this library
- **Constraint sets**: `sector`, `adjacent_to_edge_kind`, `distance_band`,
  `AND` — composable spatial predicates that evaluate to patch-id sets
  against the complex.  C5's placement solve targets constraint cells on
  the complex.
- **`summon_eligible(cells, cover)`**: the prime directive in topological
  form — placement is rejected if the constraint set contains any OBSERVED
  cell.
- **`latent_rot(constraint_cells, cover, min_measure, complex)`**: crisp
  latent rot — when the unrefined measure in the constraint set drops below
  threshold, the latent obligation must be discharged or reconciled.

### Implementation notes
- `DriftField` from `kernel/gmm_dynamics` is referenced, not reimplemented.
  It lacks `__eq__`, so `Complex.__eq__` compares fields by `np.allclose` on
  mu/theta/sigma arrays.
- `Node`, `Edge`, `Patch` are frozen dataclasses; `Complex` is mutable
  internally (graph) but presents an immutable logical view at each version.
- `nodeless_intersection` uses orientation-based segment-intersection;
  endpoint-touching pairs are not flagged (only proper crossings count).
- The defect variant's `spur` node is disconnected (no edges incident to
  it), which produces a `disconnected_component` defect — this is
  intentional and verified by the audit demo.
