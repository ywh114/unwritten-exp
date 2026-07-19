# Unwritten

Lazy-world ARPG engine: unobserved world state is stored as probability distributions and latent vectors; concrete state and history are generated at measurement time by an LLM orchestrator constrained by a promise ledger.

Warning - this entire repo is LLM generated, just an attempt at a proof of concept.

[![xkcd #827](https://imgs.xkcd.com/comics/my_business_idea.png)](https://xkcd.com/827/)

## Overview

- Single-player 2D/2.5D ARPG with a high-power protagonist.
- **Off-screen entities:** Gaussian-mixture position distributions with drift–diffusion evolution and analytic time-skip. No per-tick simulation of unobserved entities.
- **Off-screen terrain/features:** latent z-vectors with spatial priors, instantiated ("summoned") only into unobserved regions.
- **History:** generated lazily on observation by an LLM, constrained by committed facts and a change budget proportional to elapsed time; mechanically validated before commit.
- **Consistency:** measurement is a filtration — coarse collapse constrains fine collapse. All narrative constraints (facts, speech acts, NPC/orchestrator intents, rumors) are unified as promises: `(scope, predicate, window, strength, provenance)`.
- **Steering:** orchestrator intents compile to drift fields and sampling tempering, spending a metered drama budget; every deviation from a raw sample is audit-logged for statistical review.

## Architecture

Three mechanical functions — sample, validate, count — plus LLM generation in the slack they leave.

| Component | Function |
|---|---|
| Kernel | GMM drift–diffusion, hash-seeded sampling, analytic counters, collapse log |
| Promise engine | Constraint ledger, validation, suspension/reconciliation (TMS-style), density index driving per-location fidelity |
| Wiki | Discharged-promise archive; trust-scored facts; vector retrieval |
| Orchestrator (LLM) | Event-driven; batched calls; intent authoring; narrative backfill; drama budget + audit log |
| Game client | Renderer (density fields + collapsed entities), observation frontier, instruments, combat |

## Status

Design-first; code lands incrementally. Full spec: [`docs/design-specification.md`](docs/design-specification.md).

- **M0 — Kernel:** GMM drift–diffusion, analytic time-skip, hash-seeded collapse, collapse log.
- **M1 — Promise engine:** promise records, hard validation, wiki graveyard, density index.
- **M2 — Narrative loop:** lazy backfill, gossip network, eventfulness calibration, batching/caching.
- **M3 — Steering:** intents as soft promises, drama budget, audit dashboard.
- **M4 — Game systems:** instruments/tracking, shrines/omens, latent-pool summoning, politics slice.

## Lineage

Successor to [Ara](https://github.com/ywh114/llmconv) (`[a]uto[r]egressive [a]dventure`, an LLM visual-novel engine). Recycled modules: fortune tools (dice, distributions, name/title/ability grammars), trust-scored wiki store, scene summarizer, per-entity context visibility. Ara corresponds to the special case: render distance = one room, collapse cadence = one dialogue line.

## Tech

- Python 3.12
- DeepSeek V4 API — automatic prefix caching; stable-prefix prompt layout; batched event calls; grammar/template tier for zero-model content. Cost target: <$0.05/hr of play (spec §7.5).
- ChromaDB — wiki/graveyard vector store
- Renderer: TBD

## License

TBD.
