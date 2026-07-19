# Unwritten Lab — Experiments Repository Specification

**Status:** Draft v0.3 (2026-07-19) — restructured: experiment = one kernel/library, built standalone
**Parent document:** *The Unwritten Engine — Design Specification* v1.0
**Lineage:** Ara (`llmconv`) module recycling per design spec §10.4.
**Repo (provisional name):** `unwritten-lab`.

---

## 1. Purpose

This repo is where the engine's **kernels and libraries get invented**. Each experiment builds *one* library from scratch — the GMM dynamics kernel, the promise ledger, the gossip transport, the backfill pipeline — as a standalone package with its own tests, fixtures, and a tiny CLI demo. No engine, no game world, no MUD is assumed. Where a library needs world state to demonstrate itself, it builds a **fixture** (a few dataclasses in the experiment's own directory), not a dependency on other experiments.

Later phases, out of scope here except as a map (§5): **assembly** (wire the libraries together behind the single-player MUD — the slice demos) and **glue** (the final `unwritten` repo).

The working rules:

1. **Independence.** Experiments are parallel, not sequential. Any of them can be started on day one. The only permitted dependencies are (a) third-party packages, (b) earlier *lab libraries* imported as packages — library stacking is normal and encouraged — never engine scaffolding.
2. **Smallness.** Each experiment is days, not weeks. If a draft grows past that, split the library.
3. **Interface-first.** Every experiment exposes a CLI entry point (`uv run python -m exp.<name> demo --seed 1`) so a coding agent can build, run, and probe it without ceremony. The unified MUD arrives at assembly; per-library CLIs exist now.
4. **Determinism.** Every demo takes `--seed`; LLM experiments take `--replay` with committed cassettes.
5. **Write-backs.** Whatever the implementation teaches about the design goes to `docs/spec-notes/` immediately. These libraries are the design spec's first contact with reality.

---

## 2. Kernel experiments — pure logic, no LLM

Each: what it is / core API sketch / demo / done-when. Sizes: **S** ≤ 2 days, **M** ≤ 4 days.

### K1 — `hashrng` — deterministic content-addressed sampling — S
The foundation stone: `sample(world_seed, entity_id, clock, context_digest) -> float in [0,1)` and stream variants. Same inputs → identical outputs across processes and machines; neighboring entities/clocks → statistically independent streams.
**Demo:** dump streams for two entities over a year of clocks; show bit-identical reruns and χ² uniformity.
**Done when:** reproducibility and independence properties hold under hypothesis tests.

### K2 — `gmm_dynamics` — the position kernel — M
Gaussian mixtures + affine drift + analytic time-skip (OU closed forms), stationary distributions, and time-periodic attractors (schedules: market morning / fields day / tavern night).
API: `evolve(dist, t0, t1, driftfield) -> dist`, `stationary(driftfield) -> dist`, `sample_at(dist, t) -> pos`.
**Demo:** 50 villagers on a toy map; evolve a season forward in one step; ASCII/matplotlib density plots at dawn/noon/night showing schedule-driven motion with zero ticking.
**Done when:** mass conserved to 1e-9 over Δt ∈ minutes…centuries; per-entity eval O(1); the day-cycle visibly works.
**Open question it must answer:** how much "context-dependent drift field" (roads, rivers, walls) survives the closed-form requirement — the affine-drift constraint vs. terrain richness is decided *here*, and the verdict goes to spec-notes.

### K3 — `collapse` — measurement semantics — M (stacks on K1, K2)
Presence Bernoulli over regions, conditional position sampling, "not found here" renormalization, tiered collapse (field → silhouette → identity) with hysteresis, coarse→fine filtration conditioning, refine/coarsen inverse-consistency.
**Demo:** scripted fixture — a crowd field, approach: field integrates to N, collapses to N silhouettes, then named individuals; walk away: re-coarsens to a field still integrating to N; search an empty region: absence renormalizes the distribution.
**Done when:** property tests show filtration never revises (1e5 trials) and refine-then-coarsen = identity + diffusion.
**Spec-note owed:** the demotion policy — timing, re-coarsening anchor (last-position vs. schedule-snap), what a collapsed *individual* becomes on exit. The design spec leaves this blank; this library is where options are tried.

### K4 — `counters` — analytic state variables — S
The deliberately trivial library: logistic / exp-decay / step + regime multipliers, anchor chains, evaluate-at-*t*, event-inserted anchors.
**Demo:** granary fixture — evaluate grain across a year, insert a "burned" event anchor, watch population lag behind.
**Done when:** evaluation exact to float tolerance under fuzzed event sequences; the full function library fits on one page (if it can't, it's over-parameterized — spec violation).

### K5 — `promise_ledger` — the constraint engine — M
The heart. Record schema (scope/predicate/window/strength/provenance), lifecycle (assert/discharge/expire/suspend/break), authority order, hard-consistency validator, TMS-lite suspension + reconciliation queue, density index, graveyard archival.
**Demo:** scripted fixture — king promises the province to two parties (collider); regime falls and dependent appointments suspend and reconcile; `density()` ranks locations.
**Done when:** scenario suite passes; and the vocabulary sub-question is answered: the *minimal* predicate set covering ~20 canonical political facts without becoming Prolog — the list goes to spec-notes.
**Note:** pure logic. No LLM, no positions, no engine. This is a database with opinions.

### K6 — `gossip_transport` — rumor diffusion, no LLM — S (stacks on networkx)
Contact graph; per-hop content perturbation (mechanical: field drops, mutations, magnitude drift) + trust decay; traceability (walk trust gradients toward source).
**Demo:** inject "the mill burned" at one node of a 50-NPC village graph; print what each node believes after N days, and trace the gradient back to the source.
**Done when:** distortion-vs-distance curves are smooth and tunable; source localizable ≥ 70% within 2 hops. LLM *delivery* of rumors is C3's job, not this one's.

### K7 — `wiki_store` — Ara port — S
Recycle `ara/memory/wiki.py`: trust-annotated recall/write/forget, querier-aware filtering, distance cap; `invented_fact` IDs → UUIDs; temporal validity metadata. Plus graveyard view: render archived facts as dry-register chronicle.
**Demo:** write 30 facts at mixed trust; recall by query/querier; render a chronicle.
**Done when:** ported behaviors match Ara's; new metadata round-trips.

---

## 3. LLM plumbing experiments

### L1 — `llm_client` — the one dependency every LLM experiment shares — S
DeepSeek V4 wrapper: tier routing (T0 grammar / T1 flash / T2 flash-thinking / T3 pro), strict-JSON output with pydantic schemas (Ara retry-with-warning pattern), **cassette record/replay**, per-call token + cost logging.
**Demo:** structured call at each tier; replay from cassette with API off; cost report.
**Done when:** cassettes make CI API-free; cost log schema fixed (everything downstream reads it).

### L2 — `prefix_bench` — cache discipline harness — S (stacks on L1)
Byte-stable digest epochs + the `[system+schemas+digest+intents] → [event tail]` layout; batch-flush policies.
**Demo:** scripted event stream; A/B naive vs. disciplined prefix; report cache-hit rate and $/hour against the design spec §7.5 model.
**Done when:** the discipline is a reusable `PromptBuilder` and the §7.5 envelope is confirmed or revised with real numbers.

---

## 4. LLM capability experiments (fixtures, not engines)

Each builds a *capability* over synthetic fixtures — a village-in-a-dataclass — never over an engine.

### C1 — `eventfulness` — sampled quantity vs. narrated quantity — S (stacks on L1)
The calibrated sampler + prompt pattern that keeps backfill honest: one roll sets the count of notable events (mass at zero); the LLM supplies only content; quiet-years few-shots.
**Demo:** 100 synthetic intervals at week/season/year scales, with and without conditioning; plot generated event counts vs. target distribution.
**Done when:** conditioned output matches target within χ² tolerance; "nothing happened; the barley came in fine" is a normal outcome. Calibration constants go to spec-notes.

### C2 — `backfill` — the lazy-history pipeline — M (stacks on K4, K5, C1, L1)
evaluate counters → sample eventfulness → generate → validate → commit, against a **fixture village**: counters from K4, promise set from K5, 20 NPC cards, Δt = one season.
**Demo:** run the pipeline; print the season's committed facts + chronicle; show validator catching seeded violations (resurrected dead, counter disagreement).
**Done when:** acceptance ≥ 80% within one retry across 50 seeded runs; planted Chekhov-seed promises discharge before new invention.
**Spec-note owed:** what "archaeologically legible" means as a checkable property, not a vibe.

### C3 — `performance` — NPC delivery layer — S (stacks on K6, K7, L1)
Card + internal state + trust-tagged facts + querier context → in-character utterance; knowledge-bounded answers (honest ignorance); same rumor told differently at different trust.
**Demo:** three NPCs deliver K6's rumor at three trust levels; an interrogated NPC with no relevant knowledge says so.
**Done when:** delivery never leaks facts outside the NPC's information state (validator-checked).

### C4 — `orchestrator_core` — queue, budget, audit — M (stacks on K5, L1, L2)
The DM as a library: event queue + batch loop, intent records (soft promises; ends-and-clocks-never-means; no player references — rejected at authoring), drama budget with smooth regen, tempering operations, and the audit log + metrics (override rate, KL/χ², player-correlation).
**Demo:** a *mock* event source (scripted JSON stream) drives the loop; steering on; audit report shows spends and the player-correlation statistic computed on outcomes.
**Done when:** audit metrics work in both regimes — ≈ 0.5 AUC at budget, rising when overspent. The mock source is a fixture; the real frontier arrives at assembly.

### C5 — `latent_summon` — z-vectors and placement — M (stacks on L1)
Curated feature types (ruin, mine, bandit fort) with parametric z; intent→z structured output; placement solve on a toy grid (priors, plausibility scoring, prime-directive check vs. an observed-region set); validity windows.
**Demo:** "bandits came from a northern fort" creates pool debt; summon into unobserved north; the same z decodes to terrain stamp, POI facts, and wiki entry — all three agree.
**Done when:** zero prime-directive violations across 200 seeded summons; decoder agreement validated.

---

## 5. After the kernels: the map forward

Not this repo's phase, stated so the libraries aim at the right targets:

- **Assembly** (`unwritten-lab`, later milestone): wire the libraries behind the single-player MUD — frontier, avatar, game world, and the slice demos ("walk away and return," "market day," "the hundred-year village," "the overdue caravan"). This is where the modules meet a world for the first time; integration bugs live here.
- **Glue** (the `unwritten` repo): productionize the assembled whole — fast loop / slow loop per design spec §10.2, renderer decision, game systems.

Assembly targets each library should keep in mind: deterministic seeds end-to-end, JSON-inspectable state, cost logging on every LLM call, and interfaces that don't presume who's calling (engine, MUD, or test).

---

## 6. Repo layout

```
unwritten_lab/
├── kernel/                        # promoted libraries live here when done
│   ├── hashrng/  gmm_dynamics/  collapse/  counters/
│   ├── promise_ledger/  gossip_transport/  wiki_store/
├── llm/                           # llm_client, prefix_bench promoted here
├── capability/                    # eventfulness, backfill, performance,
│                                  # orchestrator_core, latent_summon promoted here
├── exp/
│   ├── k1_hashrng/
│   │   ├── README.md            # goal, API sketch, demo, verdict, spec-notes produced
│   │   ├── __main__.py          # `python -m exp.k1_hashrng demo --seed 1`
│   │   ├── fixtures.py          # its own tiny world, if it needs one
│   │   └── test_*.py
│   └── … one directory per experiment, same shape
├── docs/
│   ├── spec-notes/              # dated amendments for the design spec
│   └── ara-mapping.md
└── tests/                         # cross-library invariants (once libraries stack)
```

Promotion rule: an experiment's code moves from `exp/<name>/` to its permanent package home (`kernel/`, `llm/`, `capability/`) when its README verdict is "works" and its API is documented. The `exp/` directory keeps the demo and fixtures as living documentation.

## 7. Conventions

- One README per experiment: **goal / API / demo / verdict / spec-notes**. Five sections, no more.
- Every experiment: `--seed`, `--json`, and (if LLM) `--replay` with committed cassettes.
- LLM experiments report tokens-in/cached/out and dollars in their README.
- Ara-recycled code carries `# ARA: <module>` provenance comments.
- Suggested start order for a solo builder (not a dependency order): K1 → K2 → K5 → L1, then whatever is most interesting — K5 and L1 unblock the most followers.
- License: match final project (TBD).
