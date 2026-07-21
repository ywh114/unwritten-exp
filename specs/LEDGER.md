# Unwritten — Ledger

**The one mutable document.** Base specs are immutable; addenda amend by
reference; RFCs are proposals until adopted; spec-notes are lab
write-backs. This file is the unified index of what is decided, what is
pending, and what is next.

**Update rule:** this ledger is updated in the SAME commit as the work it
records. An experiment is not done until its row flips; a document is not
adopted until its fold-state row moves. A missing ledger update means the
task is incomplete.

## Precedence

1. **Base specs** (engine v1.1, lab v0.4) — immutable foundation.
2. **Addenda** (A1, A2, …) — normative on adoption; amend parents by
   reference. Their "amendments stated, not applied" sections are the
   amendment queue tracked below.
3. **RFCs** — proposals; become normative only when folded into an
   addendum.
4. **Spec-notes** (`docs/spec-notes/`) — implementation verdicts from the
   lab; folded into the next addendum (or engine-spec revision).

Latest normative document wins. A conflict this rule cannot resolve is
itself an open question (table 4).

## 1. Document registry

| document | status | amends / feeds | fold state |
|---|---|---|---|
| `unwritten-engine-design-specification.md` v1.1 | base | amended by A1 §17, A2 §11, spec-notes K2/K3/K5 | amendments unapplied |
| `unwritten-lab-experiments-repo-spec.md` v0.4 | base | experiment list extended by RFCs (C6…) | current |
| `unwritten-generation-addendum-spec.md` (A1) v0.1 | normative-draft | amends engine spec (§17 queue); open questions §18 | adopted 2026-07-20 |
| `unwritten-addendum-a2-topology-items-ecology.md` (A2) | normative-draft | amends engine spec (§11 queue); open questions §12 | adopted 2026-07-20 |
| `rfc-fauna-generator.md` v0.1 | proposal | feeds experiment C6; refines A2 §4 | under review |
| `rfc-game-layer.md` v0.1 | proposal | feeds future Addendum A3; answers A1 §18 q6 partially | under review |
| `docs/spec-notes/2026-07-19-k2-drift-field-verdict.md` | write-back, final | amends engine spec §3.1 drift-field language | unfurled → fold queue |
| `docs/spec-notes/2026-07-19-k3-demotion-policy.md` | write-back, final | amends engine spec §3.4 (demotion) | unfurled → fold queue |
| `docs/spec-notes/2026-07-19-k5-predicate-vocabulary.md` | write-back, final | settles promise predicate vocabulary | unfurled → fold queue |

## 2. Work items

Status pipeline: `pending → spec-written → implemented → verified → promoted`.

| id | item | source | status |
|---|---|---|---|
| K1 | hashrng | lab spec §2 | **promoted** (`kernel/hashrng.py`) |
| K2 | gmm_dynamics | lab spec §2 | **promoted** (`kernel/gmm_dynamics/`) |
| K3 | collapse | lab spec §2 | **promoted** (`kernel/collapse/`) |
| K4 | counters | lab spec §2 | **promoted** (`kernel/counters/`) |
| K5 | promise_ledger | lab spec §2 | **promoted** (`kernel/promise_ledger/`) |
| K6 | gossip_transport | lab spec §2 | **promoted** (`kernel/gossip_transport/`) |
| K7 | wiki_store (Ara port) | lab spec §2 | **promoted** (`kernel/wiki_store/`) |
| L1 | llm_client | lab spec §3 | **promoted** (`llm/llm_client/`) |
| L2 | prefix_bench | lab spec §3 | **promoted** (`llm/prefix_bench/`) — §7.5 envelope confirmed |
| C1 | eventfulness | lab spec §4 | implemented (stacks on L1) |
| C2 | backfill | lab spec §4 | **promoted** (`capability/backfill/`) — acceptance 50/50 |
| C3 | performance | lab spec §4 | pending (stacks on K6, K7, L1) |
| C4 | orchestrator_core | lab spec §4 | pending (stacks on K5, L1, L2) |
| C5 | latent_summon | lab spec §4 | pending (stacks on L1; A1 §5 amends its z-schema) |
| C6 | ecology counters + fauna table | rfc-fauna-generator §4 | **blocked**: RFC not yet adopted; spec unwritten |
| W1 | fold K2/K3/K5 spec-notes + A1 §17/A2 §11 queues into engine spec v1.2 or A3 | this ledger | pending |
| W2 | adopt/reject rfc-fauna-generator (unblocks C6) | rfc | pending user decision |
| W3 | adopt/reject rfc-game-layer (feeds A3) | rfc | pending user decision |
| W4 | commit specs/ move (staged 2026-07-20) | repo | **done** (commit 03afc0b) |
| W5 | C2 backfill stress tests: harder prompts (larger k, more dead NPCs, contradictory counter anchors) to make the validator fail live, not just on seeded traps | user 2026-07-20 ("save for later, but not much later") | pending |

### Addendum-implied candidates (lab addendum B1, not yet registered)

| id | item | source | status |
|---|---|---|---|
| K8 | topo_complex: cells, cover, mobility classes, on-graph traffic (converges with K2 spec-note's patch-graph verdict) | A2 §1–3 | proposed — near-term |
| K10 | structure_registry: presets+params, content-addressed, promise-backable | A1 §4 | proposed — near-term |
| K9 | worldgen_l0: staged terrain pipeline (plates→hydrology→climate→biomes) | A1 §3, game-layer RFC §1 | proposed — **deferred** (high-level, per user 2026-07-21) |
| K11 | naming_corpora: curated-corpus hash-seeded naming. **Custom simple implementation — NOT an Ara lift** (Ara just samples a downloaded name list); details unimportant | A1 §8, P5 | proposed — **deferred** (high-level, per user 2026-07-21) |

## 3. Open questions

| id | question | source | owner | state |
|---|---|---|---|---|
| Q-drift | affine drift vs. terrain richness | lab spec K2 | K2 | **answered** → spec-note K2 (patch splitting; no continuous drift, no hard walls) |
| Q-demote | demotion policy (timing, anchor, tier-3 target) | lab spec K3 | K3 | **answered** → spec-note K3 (schedule-snap vs last-position) |
| Q-vocab | minimal predicate set for politics | lab spec K5 | K5 | **answered** → spec-note K5 (10 kinds + detail extensibility) |
| Q-counters | who authors counter laws/parameters | design conversations | K4 | **answered** → K4 README (content task at summon time) |
| Q-legible | "archaeologically legible" as checkable property | lab spec C2 | C2 | **answered** → spec-note C2 |
| Q-A1 | A1 §18 open questions (incl. reference-game constants) | A1 §18 | A3 / game-layer RFC | partially answered by rfc-game-layer; rest open |
| Q-A2 | A2 §12 open questions | A2 §12 | unassigned | open |
| Q-fauna | rfc-fauna-generator §7 (5 questions: root cap, mosaic prob, folk labels, re-recognition, promotion trigger) | rfc | C6 / user | open, gated on W2 |
| Q-game | rfc-game-layer open items | rfc | A3 / user | open, gated on W3 |

## 4. Conflict log

Empty. (Any disagreement between normative documents that precedence
rules can't settle lands here as a dated entry with an owner.)
