# The Unwritten Engine — Design Specification

**Status:** Design draft v1.1 (2026-07-19) — consistency pass: "chapter" defined (§6.4), planning tiers/pricing reconciled (§7.1, §7.5), §8.1 protagonist bullet rewritten, living-environment emphasis restored (§5.4, §8.1)
**Title:** Unwritten (the world is *unwritten* until observed)
**Lineage:** Successor architecture to **Ara** (`[a]uto[r]egressive [a]dventure`), a scene-based LLM visual-novel engine. Ara is the special case of this engine where render distance is one room and collapse cadence is every line of dialogue.
**Genre target:** 2D/2.5D ARPG with a high-power protagonist (DF adventure-mode adjacency); the engine itself is genre-general (see §9).

---

## 1. Vision

A single-player open world in which **nothing exists concretely until observed**. Entity positions are probability distributions evolved by drift–diffusion; terrain features are latent state vectors awaiting summoning; history is not simulated but *interpolated on demand* by an LLM orchestrator, constrained by a ledger of promises. The player is a powerful being — a dragon, a demigod — whose senses are the only measurement instrument that matters, and around whom the world continuously condenses out of potentiality.

Design pillars:

1. **Unobserved = unwritten.** No background simulation of narrative. The world has no state beyond (a) measurement records, (b) a promise ledger, (c) analytic counters and distributions. History is generated lazily at measurement time.
2. **Measurement is a game mechanic.** Observation is graduated, instrumented, and costs resources. Information is the core resource; fog of war is superposition; your territory is what you have measured.
3. **Coarse physics, fine gossip.** Simulation depth is proportional to mechanical interactivity. Everything social, economic, and political is *performed* by LLM-driven characters decoding a thin latent state — never mechanistically faked.
4. **Steering is real but bounded.** An LLM orchestrator authors intents and may bias fate within a metered drama budget, under a statistical audit that makes invisible-handedness measurable rather than hoped for.
5. **Cheap enough to actually run.** One cheap frontier API (DeepSeek V4), aggressive prefix caching, batching, and grammar-based template tiers. Target: cents per hour of play (see §7.5).

The architecture reduces to three mechanical functions — **sample, validate, count** — plus an LLM that writes freely inside the slack those functions leave open.

---

## 2. Ontology: what the world *is*

The complete world state at time *t* is a quadruple:

| Component | Contents | Mutated by |
|---|---|---|
| **Promise ledger (active set)** | All currently binding promises (§4) | Assertion, discharge, expiry, suspension, breakage |
| **Wiki / graveyard ledger** | Discharged & expired promises; canon facts with trust scores; narrative prose | Promise discharge; narrative commits |
| **Distributions** | Per-entity parametric position/state distributions (Gaussian mixtures with drift) | Analytic evolution; collapse; heartbeat |
| **Counters** | Bare numeric state variables (population, garrison, stock) as analytic functions of *t* | Evaluated at observation; regime-flag changes |

Plus three indexes: the **collapse log** (every measurement ever taken — the filtration record), the **latent pool** (unsummoned terrain/feature z-vectors with spatial priors), and the **contact graph** (who knows whom, for gossip transport).

There is no tick loop for unobserved reality. Time passes only at measurement. Between measurements, distributions evolve *analytically* (closed-form, evaluated on demand), counters are functions of *t* (evaluated on demand), and narrative does not exist at all — only constraints on its future generation.

### 2.1 The interactivity-proportionality rule

Simulation depth is allocated by one rule: **mechanical interactivity determines what is sim-backed; everything else is performance over coarse latents.**

- Player can take it, burn it, block it, follow it → sim-backed (a counter, a distribution, a promise).
- Player can only hear about it → performed by LLM characters decoding shared latents (regime flags, wiki facts).

Consistency flows through shared latents, never through NPC-to-NPC message passing. When the player intervenes (burns the bridge), the action maps to a latent update and every performer inherits it. This rule deliberately picks the failure mode the system is equipped to catch: over-parameterized coarse sims fail as *uncanny numbers*; coarse latents plus performance fail only as *LLM self-contradiction*, which the promise/wiki/validator machinery exists to catch.

---

## 3. World model

### 3.1 Entities as distributions

Every off-screen entity carries a **parametric position distribution**: a Gaussian mixture (mean, covariance, weights per component) plus a context-dependent **drift field** (roads accelerate, rivers block, walls are zero-diffusivity hard boundaries; home/work/food act as attractors). Evolution is by drift–diffusion (Fokker–Planck), chosen over unitary/Hamiltonian dynamics because:

- Drift–diffusion has **stationary distributions** — long-unobserved entities relax toward plausible equilibria (near food, shelter, work), enabling **analytic time-skip**: on re-observation after Δt, sample from the evolved distribution directly rather than simulating intermediate ticks.
- Diffusion conserves probability mass, which makes measurement bookkeeping exact (§3.4).
- Interference fringes and wave dispersion buy nothing gameplay-wise; diffusion's smoothing matches intuition about "where people probably are."

Evaluation is O(1) per entity per query — closed-form parameter updates, no grid PDE ever solved. Multimodal mixtures represent genuine alternatives ("in the mineshaft *or* the forest").

**Internal state vector.** Beyond position, each entity carries a compact structured internal state: health, disposition, goals (soft promises it is pursuing — Chekhov seeds, §5.2), secrets, and a memory handle (§5.4). Goals planted in observed play become constraints that lazy backfill *resolves* — history is the discharge of previously committed intents.

**Schedules.** Routine life is time-periodic drift (market in the morning, fields by day, tavern at night). Movement is simmed; meaning is performed on demand.

### 3.2 Interactions: mean-field plus event sampling

Joint distributions over N entities are not tracked (the many-body wall). Instead:

- Each entity evolves in the **mean field** of the others (density fields act as drift/diffusivity sources).
- When two entities' distributions overlap significantly, an **interaction event** is Poisson-sampled (hunt, fight, transaction, courtship) with rates from entity types and internal state. Outcomes commit as promises/facts.

Most social richness is *not* simulated at all — it is performed (§5). The event sampler exists to supply the sparse mechanical skeleton (deaths, injuries, thefts, births as counter deltas) that performance then explains.

### 3.3 Counters

Any quantity with mechanical consequence and no identity is a **counter**: village population, garrison size, grain stock, gold in a chest. Counters are analytic functions evaluated at observation time, *c(t) = f(c(t₀), Δt, regime flags)* — logistic growth toward carrying capacity, exponential decay, step changes from committed events. Counters never "run"; they are evaluated, like the distributions. The LLM never invents counter values; it narrates *why* a counter moved.

### 3.4 Measurement and collapse

The **observation frontier** is the set of regions currently measured by the player: avatar senses (line of sight, hearing), instruments (scrying, familiars, lookout towers in escort/settlement contexts), and hearsay (hearsay is *not* measurement — it is rumor, §5.3).

Collapse of an entity inside a measured region R:

1. Compute *p = P(entity ∈ R)* from its distribution (mass inside R).
2. Bernoulli(*p*) via deterministic hash-seeded sampling (§3.7). If absent: renormalize the distribution outside R (mass conservation) and continue.
3. If present: sample position from the conditional density; instantiate the concrete entity; record the collapse in the collapse log.

**Renormalization rule.** "Not found here" is a measurement outcome: the entity's distribution is renormalized to the complement, and the player *learns the absence*. Entities with diffuse distributions are legitimately hard to find — uncertainty as gameplay.

**Consistency (the filtration invariant).** Measurement is structured as a **filtration**: coarse collapse constrains fine collapse. Coarse attributes (position band, class, count) are sampled first and committed; every finer measurement samples from the distribution *conditioned on all prior coarser outcomes*. Fine measurement adds (name, cargo, history); it may never revise ("actually a knight"). Information only accumulates. The collapse log is therefore a lattice of constraints ordered by granularity, not a flat fact list.

**Graduated measurement (LOD = measurement resolution).** Collapse has tiers, promoted by proximity/attention with **hysteresis** (promote at distance *d*, demote at *d*+ε) and crossfades:

- **Tier 0 (field):** density only. Rendered as crowds/heat-haze; no identities committed.
- **Tier 1 (silhouette):** count, heading, coarse class. No LLM involvement.
- **Tier 2 (identity):** skeleton facts committed — name, class, key attributes — grammar-generated, instant, free.
- **Tier 3 (person):** full LLM individual — history backfill, memory, dialogue.

Tier transitions differ in richness, never in content: finer tiers decode the *same* committed skeleton (single latent, many decoders). Voice is uniform across tiers (short, dry chronicle register); depth shows as *density of entries*, never as a style regime-change — so tier boundaries are illegible to the player.

**Refinement/coarsening inverse-consistency.** Field→individual refinement samples N individuals from a field integrating to N; re-coarsening aggregates them back to a field still integrating to N, with spread increased by elapsed diffusion. Refine-then-coarsen = identity + diffusion. Entropy grows only through diffusion while unobserved, never through sloppy tier transitions.

### 3.5 Heartbeat collapse (the Zeno dial)

Pure laziness fails for important places over long Δt: a single year-long backfill strains eventfulness calibration and arc coherence, and the orchestrator cannot be perfect. So measurement cadence is a per-location dial — the **quantum Zeno effect** used as a design knob:

- **Heartbeat locations** (promise-dense, §4.5): periodic collapse even while unobserved — small, re-anchored, validatable backfill steps (e.g., one in-game week per pass), committed as terse structured records. Error compounds sublinearly because each step re-grounds in validated facts.
- **Sleeping locations** (promise-poor): no heartbeat; free evolution between distant measurements; a single backfill on observation. Frontier lands stay *strange* — weirdness accumulates with unobserved time, matching the change-budget rule (§8.1).

Real observations always supersede the schedule; the heartbeat is a floor on measurement frequency, not a substitute. Heartbeat output folds into the batch queue (§7.3), never a synchronous call. As promises expire (known NPCs die), cadence decays geometrically — the 100-year village (§9.2) needs no cliff-edge flush logic.

### 3.6 Terrain and features: the latent pool

Geographic/political features (ruins, mines, groves, bandit forts, villages) exist pre-instantiation as **latent z-vectors**: a small interpretable parameter vector (age, hostility, water, culture, elevation…), a **coarse spatial prior** ("somewhere in the northern third, near drainage"), and a **narrative role**. Summoning is measurement of the joint (location, state) distribution:

1. **Prime directive check:** the summon region must be unobserved (no covering collapse records). Collapsed terrain is immutable except by sanctioned diegetic change (erosion, disaster, construction), and *future* extension of observed regions is allowed only under causal closure (§9.1).
2. **Placement solve:** candidate sites scored by geological plausibility, distance from current attention, and non-contradiction with observed terrain; best site wins.
3. **Instantiation:** the same z decodes through every interpretation layer — terrain-stamp generator, POI/content generator, wiki entry — so geometry, loot, inhabitants, and chronicle agree by construction (single latent, many decoders).
4. **History backfill:** the feature's implied past is written at summon time, constrained by existing facts, and committed as promises/facts.

Obligations created by narrative ("the bandits came from the northern fort") become latent-pool entries — **obligation debt as first-class inventory**. Latents carry validity windows and are periodically reconciled, else summoning produces anachronisms (the "latent rot" failure mode, §9.4).

**Curated types, parametric z.** Feature *types* are curated with vetted procedural generators; the LLM's creativity flows into parameter selection, naming, and history — never raw geometry. Intent→z is a clean structured-output task; guaranteeing a navigable heightfield is not.

### 3.7 Deterministic sampling and save/reload

All sampling is hash-seeded: *outcome = H(world_seed, entity_id, clock, context_digest)*. Unobserved states are reproducible for free; saves shrink to *seed + collapse log + promise ledger + wiki* (kilobytes where DF writes gigabytes; the world materializes around the player's history). Identical play reproduces identical collapses; any deviation re-rolls. Scumming requires varying actions, which varies the hash input — accepted consciously (§9.4).

---

## 4. The Promise Engine

The promise engine is the single formalism that unifies: committed facts, speech acts, NPC intents, orchestrator intents, latent obligations, conditional validity, coarse-collapse constraints, prophecies, and rumors. It is named in homage to Burgess's Promise Theory — autonomous agents coordinating by voluntary declarations rather than obligations — though here a promise binds *future commits*, not (only) agent behavior [^2][^3].

### 4.1 Promise record

```
promise {
  id:          uuid
  scope:       entity | location | regime | latent_region
  predicate:   typed claim, e.g. alive(e), located(e, R),
               holds_office(e, o), regime(loc, R),
               summoned(feature z by t)
  window:      valid_from, valid_until | while(condition)
  strength:    hard | soft(temper_cost)
  provenance:  {authority, actor_id, committed_at, trust ∈ [-1, 1]}
  depends_on:  [promise_id | regime_id]     # conditional validity
  status:      active | suspended | discharged | broken | expired
}
```

### 4.2 Authority order and the prime directive

Authority, descending: **measurement > canon** (validated committed fact) **> orchestrator-hard > orchestrator-soft > NPC utterance** (trust-tagged).

- **Measurement is promise-making at hard strength by the world itself.** Coarse collapse commits "a trader is here"; finer collapse must honor it. The filtration invariant is promise consistency under refinement.
- **The prime directive is a provenance rule:** no actor may assert a promise contradicting an active promise of higher authority.
- **Speech-act firewall:** in-character LLMs may only commit *utterances* ("the king promised a province" — binds the king softly, at his honor's strength), never world states. World-state changes flow only through the event/regime machinery. (Recycles Ara's attempt/reply split: reply = words happen; attempt = resolution by machinery.)
- **The drama budget is the currency for breaking soft promises; the audit trail is the broken-promise log** (§6.4). All steering — tempering, fate armor, forced outcomes — is one act with one metric.
- **The wiki is the promise graveyard.** Discharged/expired promises archive as facts; history is the rendered ledger.

### 4.3 Lifecycle and validation

- **Assert:** any actor may propose; the validator checks consistency against the active set (hard promises) and authority. Rejection is silent to the player (the proposal simply never happened).
- **Discharge:** fulfilled by matching commits (the miller's expansion promise discharged by the new mill) — or by the backfill generator resolving it.
- **Expire:** window closes; archives to the graveyard. Expired promises remain backfill *seeds* (§9.2 archaeology).
- **Suspend:** a dependency fails (regime R falls → dependent appointments/laws suspend into a **reconciliation queue**, worked through asynchronously and diegetically paced — "the city adjusts over days"). This is the truth-maintenance layer (TMS-lite), in the lineage of Doyle's JTMS and de Kleer's ATMS: facts are defeasible, tagged with the assumptions they depend on.
- **Break (soft only):** allowed at drama-budget cost; audit-logged with full provenance.

### 4.4 The validator

Mechanical, model-agnostic, cheap. At every commit/collapse, checks:

1. **Hard consistency** — no contradiction of active hard promises (no resurrected dead, no violated filtrations).
2. **Causal reachability** — for changes to previously observed state: the diff must be coverable by events plausible at rate × Δt (change magnitude ∝ absence; §9.1).
3. **Eventfulness budget** — generated history's notable-event count must match the sampled budget (§5.2).
4. **Counter agreement** — narrative implies counter deltas matching the analytic evaluation.
5. **Latent validity** — summons within window, placement within prior.

Validation rejects generations, not worlds: on rejection, regenerate (bounded retries) or fall to template tier.

### 4.5 Promise density = importance

A location's active-promise count *is* its fidelity priority — heartbeat cadence, narrative-queue priority, prefetch weight all read from it. Player attention manufactures promises (every known NPC is a promise), so the attention economy emerges from the ledger rather than hand-tagged flags. Salience-weighted inertia falls out: the more the player invested, the more constrained the location's future. Zeno-frozen heartland; dreamlike frontier.

### 4.6 Plots as promise colliders

A plot is not a script; it is **a set of promises on a collision course**. The king promised you the province and the duke the same province: one promise must break, and the breaking *is* the story, with provenance fields deciding who is betrayed. Orchestrator plotting = authoring promises designed to intersect, then watching resolution through gameplay.

Intent encoding rules:

- **Plan ends and clocks, never means.** Intents specify invariants plus countdowns ("the war reaches the capital by winter"); means are improvised locally from whatever facts exist (envoy dead → news arrives by survivor, letter, rumor).
- **No intent may reference player location or actions.** Any that does is a railroad seed; rejected at authoring.
- **Fate armor requires telegraphing.** A hard promise on an entity's survival must be announced diegetically (prophecy, omen). Budgeted, announced invulnerability is a boss mechanic; silent invulnerability is a rail.

---

## 5. The narrative layer

### 5.1 Lazy backfill pipeline

On any observation of a region with elapsed Δt (return, scrying, interrogating a traveler):

1. **Evaluate** counters at current *t*; evolve distributions analytically.
2. **Sample eventfulness** — one fortune roll sets the *quantity* of notable events for the interval (mass concentrated at zero; §5.2).
3. **Generate** — the LLM backfills the interval: events, discharges of due promises, updated internal states of known NPCs; constrained by the fact anchor, leaked constraints (rumors committed via gossip), active promise set, and the Δt budget. Chekhov-seed resolution is the primary source: history should *resolve what was planted* before inventing anything new.
4. **Validate** (§4.4). Bounded retries; template fallback.
5. **Commit** — new promises asserted, discharged ones archived, counters locked, wiki updated.
6. **Instantiate** — physical state re-materializes; the player walks in.

### 5.2 Eventfulness calibration

LLMs over-dramatize: training data underrepresents boring intervals, so unconditioned backfill turns every revisit into a soap opera. Countermeasure (same cure as Ara's dice-bias fix): the *quantity* of history is measured, not narrated — one roll per interval per location from a calibrated distribution (quiet years the modal outcome), and the LLM supplies only content. Prompts include few-shot examples of genuinely quiet years. "Nothing happened; the barley came in fine" must be a statistically normal outcome.

### 5.3 The gossip network

The contact graph is the **only channel** from the unobserved world (no background simulation exists). Rumors are promises about the past traveling the graph:

- **Transport:** per-hop content perturbation + trust decay (the telephone game, parameterized by graph distance and teller disposition). Cheap: pure graph diffusion, no LLM.
- **Performance:** an NPC relays a rumor at *their* trust level with *their* accumulated errors (recycled: Ara's querier-aware reframing subagent).
- **Verification:** NPCs may fact-check against the wiki (recycled: Ara's per-character `wiki_recall`).
- **Contradictory rumors are unresolved truth**, reconciled only at observation — no hidden state, only measurement records.
- **Injection:** the orchestrator may inject trust<0 rumors as steering; the *player* may lie — identity becomes a wiki entry contested by performance (§9.4).

Detective gameplay falls out: trace a rumor back toward its source by graph distance and trust gradients.

### 5.4 The performance layer

NPCs are LLM instances conditioned on: card (personality, expertise), internal state, memory handle (per-character vector store, recycled from Ara's `CharacterMemory`), retrieved wiki facts, and relevant promises. They never invent world state (speech-act firewall); their dialogue decodes shared latents, so cross-NPC consistency holds without message passing.

Per-NPC LLM treatment is event-driven (observed or predicted-observed interactions only), routed by importance: anonymous background (grammar-only, no tools, no memory — recycled Ara `spawn_anonymous` semantics) → named (memory, wiki recall) → principals (full scratchpads, inner monologue, long-horizon goals).

**Hand-off and overhearing.** In the collapsed region this layer never moves bodies: it writes the goal layer and the reflex layer executes (§8.6) — degradation means the NPC continues its current task, never a frozen puppet. Overheard NPC–NPC conversation is a first-class collapse: eavesdropping backfills the exchange's context (the fence, the feud, three generations of it) and commits it as facts — eavesdropping as worldgen — so observed social life sits high in the generation queue (§7.3).

**Text economics:** the LLM emits compact structured records (facts, refs, two-sentence chronicle lines); templates + the Ara fortune grammars expand meaning into varied prose. LLM as compressor; grammars as decompressor.

---

## 6. The Orchestrator

### 6.1 Role and tools

One orchestrator (the "DM"), event-driven, never per-tick. It consumes world-state snapshots and event streams — never conversational turns; the player is a force in the world, not a dialogue partner. Tool surface (schemas recycled from Ara's dynamic-enum, strict-JSON, retry-with-warning patterns):

- **Fortune suite** (recycled wholesale): roll, distribution sampling, I-Ching omens, inspiration, name/title/ability grammars. All randomness is externalized — LLM token distributions are biased; dice govern.
- **Wiki tools:** recall (trust-annotated, distance-capped), write (importance + trust), forget.
- **Promise tools:** assert intent (soft promise), set clock, summon (latent pool), suspend/reconcile.
- **Journal:** private scratchpad persisting across chapters (recycled Ara orchestrator scratch).

### 6.2 Steering channels

1. **Honest channel (dynamics):** intents compile to drift-field adjustments and z-biases — gentle, distributed pressure visible only statistically. Destiny as a potential field.
2. **Direct channel (measurement):** tempered reweighting of collapse outcomes toward story-worthy results, priced by the drama budget.

**Drama budget.** A metered account: soft-promise breaks and tempering spend from it; it regenerates slowly and smoothly (no cliffs — a budget cliff is a detectable tier boundary). Default posture: sample honestly; spend only where the story pays.

### 6.3 The audit trail

Every collapse decision logs: true distribution, raw sample, orchestrator preference (weights/override), committed outcome, budget before/after. Metrics computed offline:

- **Override/temper rate** per play-hour (budget bookkeeping).
- **Distributional drift** — KL divergence / χ² between empirical outcome frequencies and predicted distributions.
- **Player-correlation test** — an auditor reading the log should be unable to locate the player or their actions from outcome statistics. If raids correlate with finished walls, steering is detectable; the log says by how much.

Steering invisibility is thus a *measured* property, not a hope.

### 6.4 Rhythm

**Chapter.** The validity window of an active intent bundle: a chapter opens when a planning pass commits a set of intents, clocks, and regime flags (§4.6), and closes when they discharge, expire, or a hard event forces replanning. A chapter boundary forces a digest-epoch rewrite (§7.2).

- **Continuous:** event queue (collapses, interactions, gossip injections) → batched orchestrator calls (§7.3).
- **Chapter review** (T2, ~30-minute cadence): check the active intent bundle against recent events — usually a no-op (intents still on-clock).
- **Chapter authoring** (T3, rare — on chapter close): deep-reasoning planning pass — intent authoring, regime-transition decisions, promise-collider design. Runs off the critical path; diegetic delay absorbs latency (the letter arrives tomorrow; the sage finishes translating next week).

---

## 7. LLM systems engineering

The game never waits for text; text catches up with the world. Collapse math is microseconds; narrative is eventually consistent. Diegetic delay absorbs slow generations; graceful degradation means shallow prose, never frozen frames. (API-outage disaster-proofing is explicitly out of scope.)

### 7.1 Model routing

DeepSeek V4 API (OpenAI-compatible), prices as of 2026-07 [^6][^7]:

| Tier | Model | Use |
|---|---|---|
| T0 | No model — fortune grammars/templates | Names, titles, abilities, minor items, anonymous NPCs |
| T1 | `deepseek-v4-flash` (non-thinking) | Routine narration, backfill, gossip performance, classification, reframing |
| T2 | `deepseek-v4-flash` (thinking mode) | Landmark events, regime-transition narration, chapter review (§6.4), complex constraint-heavy generation |
| T3 | `deepseek-v4-pro` | Chapter authoring — intent planning, regime-transition decisions (rare; §6.4) |

V4-Flash: $0.14/1M input cache-miss, $0.0028 cache-hit, $0.28 output; V4-Pro: $0.435/1M input cache-miss, $0.0036 cache-hit, $0.87 output (promo; list $1.74/$3.48); both 1M-token context [^6][^7]. Legacy aliases `deepseek-chat`/`deepseek-reasoner` retire 2026-07-24 — target V4 names directly, toggle thinking in the request [^7].

Rationale: orchestration under constraint needs reasoning; routine narration from structured inputs does not. Shrink the hard task (offline chapter planning, rare) and the frequent task becomes cheap-model-able.

### 7.2 Stable-prefix architecture

DeepSeek caches prompt prefixes automatically; cache-hit input is ~50× cheaper on Flash [^6][^7]. Rules:

- Strict ordering: `[system + schemas + world digest + active intents]` → `[event tail]`. Nothing volatile in the front half. (Ara lesson: separate user messages per source; no merged growing blocks.)
- **Distilled digest epochs:** a fixed-budget world digest (2–4k tokens: canon highlights, active intents, chapter state) rewritten asynchronously every N events or on chapter close (§6.4), and *byte-identical between rewrites*. Fresh retrieval lands in the tail, never the prefix.
- Batch related events into one call — pay the uncached tail once.

### 7.3 Queueing, prefetch, speculation

- **Event queue** with priority from importance (promise density) and observation imminence; flush at natural beats or on critical events.
- **Prefetch oracle:** distributions with mass near the observation frontier, weighted by avatar velocity, give P(observation) over the next N seconds. Continuous ARPG locomotion makes this short-horizon and accurate. Scheduled gatherings (market day) are guaranteed-observation events worth pregenerating.
- **Speculation policy:** precompute only the *modal* branch of high-probability collapses (P(obs) × latency-saved above threshold); template stubs upgrade lazily otherwise. Branch calls share the cached prefix, so a second branch is mostly output tokens — but gating means most branches are never generated at all. **Token spend follows attention**: coarse tiers cost zero tokens; fine collapse with backfill happens only where the player engages.

### 7.4 Structured output

Strict JSON schemas everywhere (recycled Ara pattern: dynamic enums of valid choices — characters, locations, latent-pool entries). Output is compact structured records; prose expansion is template-side. Cap output tokens — they cannot be cached.

### 7.5 Cost model (worked example, V4-Flash rates)

Assume active play: one batched orchestrator call/minute — 4k cached prefix + 500 uncached tail + 300 output:

- cached input: 4000 × $0.0028/1M ≈ $0.000011
- uncached input: 500 × $0.14/1M = $0.00007
- output: 300 × $0.28/1M = $0.000084
- **≈ $0.00017/min ≈ $0.01/hour**

Chapter review (T2, every ~30 min): ~6k cached + 2k uncached in, ~2k out ≈ $0.0009/call ≈ $0.002/hour — usually a no-op. Chapter authoring (T3 Pro, on chapter close): the same shape at Pro rates ≈ $0.0026/call; at a chapter per few hours, under $0.001/hour. Fine-collapse narratives and heartbeat batches fold into the per-minute batch. Order of magnitude: **one to five cents per hour of play**, dominated by output tokens. Budget risk is not price but prefix-stability discipline — monitor hit rate in the dashboard [^6].

---

## 8. The game layer (ARPG)

### 8.1 The powerful protagonist, and why it is the cheap option

The player starts powerful — dragon-tier. This is a cost decision as much as a fantasy:

- **Power licenses coarse-graining by lowering demanded resolution.** The avatar is pointlike — but a being that eats knights whole has no reason to resolve which peasant is unhappy, so the engine is never obligated to resolve it either. Mean-field is the faithful ontology for the masses not because the player *cannot* descend to individuals (peers, rival powers, named heroes get full individual treatment), but because a powerful being rarely *needs* to look closer: fewer tier-3 collapses demanded, fewer promises per capita, less work for the interaction sampler. The savings come from the player's indifference, not from an ontological ban.
- **Physical fidelity follows combat relevance; social fidelity follows audibility.** The army you fight is a density field; the army you *listen to* is a gossip network — camp rumors, soldiers' fear, letters home. Mooks are field elements in combat and people at the campfire. The living environment is the point, not a side system — overheard NPC–NPC life is first-class collapse content (§5.4) and sits high in the generation queue (§7.3).
- **Economies of conserved goods are stable fields.** Prices/stocks diffuse along trade routes and relax after perturbation — a burned granary ripples and equilibrates rather than cascading. Non-conserved quantities (fear, renown, legend) may be supercritical and dramatic, because nothing must balance. A dragon's real economy is fear and fame.
- **Continuous attention:** one avatar, one observation cone, bounded velocity — the prefetch oracle is short-horizon and accurate, and collapse bookkeeping is simple.

### 8.2 Information as infrastructure

Observation is graduated, instrumented, and priced:

- **Instruments as measurement bases:** perception skills, scrying, familiars, purchased maps, lookout towers. Each has a resolution and an error model. Coarse instruments sample the *appearance* distribution — appearance ≠ identity with a tunable error rate, which makes disguise, ambush, and illusion explicit mechanics (mimics are budgeted non-monotonicity, signaled and rare).
- **Tracking is backward diffusion:** a trail is the posterior over *past* position, spreading with age; ranger skill tightens the posterior, weather accelerates diffusion.
- **Deferred measurement as strategy:** the overdue caravan's distribution spreads. Wait (it drifts; maybe it arrives), search (collapse; maybe bad news, but you can respond), or divine (coarse, cheap, imprecise). Uncertainty has option value; deferral has drift cost.
- **Construction as wavefunction engineering:** walls are zero-diffusivity boundaries; penning animals collapses their future positions; chokepoints shape diffusion. Building *is* uncertainty reduction.
- **Change budget:** allowed change magnitude ∝ absence duration (§9.1). Fast travel returning within minutes *must* find an identical village — a free test case.

The unifying image: **your territory is what you have measured.** The collapsed world is exactly your observation history; the orchestrator may only summon beyond your frontier, so the unpatrolled woods are where its z-vectors land.

### 8.3 The fate economy

The orchestrator is statistically invisible but has a diegetic interface:

- **Shrines and sacrifices:** pay to bias drift fields (raise caravan-drift, lower raid-drift) — tempering within budget, so the god is real but bounded; the audit log keeps answered prayers honest.
- **Omens as mandatory telegraphing:** big intents cast shadows first (dreams, bird flights, I-Ching casts — the Ara fortune tool, diegetically at home). Reading omens is a skill; telegraphing is a mechanic, not just a fairness rule.
- **Defiance is endgame:** a being powerful enough to notice the steering can fight it. Drama budget spent *against* the player is felt as fate pushing back — bounded, audit-logged. "Detect the author" is late-game content by design.

### 8.4 Combat and physical interaction

On-screen combat is conventional ARPG within the collapsed region. Against crowds: field-level resolution (wingbeat = area effect; no per-soldier rolls). Against peers: full duels. Anything the player can mechanically interact with (loot, structures, named weapons) is sim-backed per the interactivity rule (§2.1).

### 8.5 What the player does

Build/claim (shape space), hunt/fight (shape the field), observe (shape information), commune (shape fate) — with observe and commune being the systems no colony sim or ARPG currently has. Moment-to-moment play is a conventional ARPG; the novelty is that the map is honest about what you don't know, and the dice have a god you can bribe.

### 8.6 The in-render behavior stack

NPC behavior in the collapsed region is layered; LLM output enters the sim as parameters, never as per-action commands:

1. **Reflex layer (procedural, per-frame):** pathing, collision, flee/fight/startle reflexes, schedule execution — utility AI or small behavior trees. Pure code; reaction latency excludes any model call (a dragon landing nearby needs a response *this frame*).
2. **Goal layer (procedural state, LLM-written):** the NPC's current goal as a drift attractor plus disposition values. LLM deliberation lands as writes to this layer — new goal, changed disposition, a promise to keep — not as motor commands. The LLM writes the mind; the sim moves the body.
3. **Deliberative layer (LLM, async):** fires on events (player speech, witnessed violence, a promise coming due). While it runs, the reflex layer holds: the NPC continues its task, or the grammar tier emits a filler beat. Degraded mode is "keeps doing what it was doing" — never a frozen NPC.

### 8.7 Conversation as an instrument

Conversation is the player's primary information channel and is fully LLM-handled, Ara-style: `reply` for speech, `attempt` for nontrivial acts resolved by the machinery, turn-paced with the world slowed — the one in-render context where request/response latency fits naturally. Rules:

- **Knowledge-bounded answers.** An NPC can only report its own information state: its measurement history (what it has seen), its memory, and imported gossip (with inherited trust decay). No omniscience leaks — asking the wrong person yields honest ignorance. Finding the right person to ask (witnesses, travelers from the right region) is the gameplay of interrogation.
- **Conditioning.** Card + internal state + memory + querier-aware wiki recall (recycled Ara subagent) + active promises touching the NPC + disposition toward the player.
- **Speech-act firewall, both ways (§4.2).** Everything said — by NPC or player — commits as an utterance promise; world state changes only through the machinery. NPC lies are trust<0 utterances; player lies enter the rumor network identically.
- **Hearsay ≠ measurement (§3.4).** Testimony about a remote region adds trust-tagged claims to the player's information state (map annotations: "rumored: dragon sighted, low trust") but does not collapse the region. Interrogation is an instrument with an error model, like scrying — and deception is an instrument returning noise.

---

## 9. Boundary conditions and failure-mode register

Severity: ● high ◐ medium ○ low. Status: D = handled by design, P = patch machinery specified, O = open.

### 9.1 Village revisit (short/medium absence) — ◐ D

Risk: drift–diffusion alone yields "same village, people rearranged"; no history.
Resolution: lazy backfill (§5.1) under the **causal-closure rule** — the prime directive is temporal, not spatial: committed facts are immutable; the future of observed regions is editable iff new commits are causally reachable from old ones. Allowed change ∝ Δt (gravestone after a year: legal; castle after a week: rejected). **Salience-weighted inertia:** re-collapse high-attention NPCs first and conservatively; peripheral faces churn. The world is most fluid exactly where the player wasn't looking.

### 9.2 The 100-year village — ○ D

Promise decay does the work: known NPCs die → promises expire → heartbeat cadence decays geometrically → free evolution. On return, strangeness is *textured*: the discharged ledger survives (graves, legends, the family mark on the ruined mill), so backfill interpolates a century seeded by the archive — strange but **archaeologically legible**. For an immortal protagonist this is the core loop: the player is the longest-lived promise; drift is measured against their canon.

### 9.3 Capital politics — ● P

Attacks three assumptions: mean-field (courts are maximally connected), stability (politics is critical — small inputs flip regimes), reflexivity (beliefs about beliefs). Plus a demigod protagonist violates "no single actor matters" deliberately.
Resolution: politics at the **regime level** (low-dimensional latent: king strong/weak, succession secure/contested…), performed by LLM leaders. Player influence in three priced channels: talk (commits speech-act promises — cheap), rumor injection (trust<0 into the gossip graph — medium), kinetic acts (assassinate/crown — regime transitions, gated, audit-logged). Machinery: **conditional validity + reconciliation queue** (§4.3) for the fact-avalanche; **speech-act firewall** (§4.2); **occupation degradation** — if the dragon crowns itself, the performed world *refuses* (flight, resistance, martyrs): occupation is computationally simpler than legitimate rule and reads as theme. Residual risk: regime revision quality depends on orchestrator competence; mitigated by validation and chapter pacing.

### 9.4 Remaining register

| Case | Risk | Resolution | Status |
|---|---|---|---|
| Save/reload | Determinism enables seed farming | Scumming requires varying actions, which re-keys the hash | ○ D |
| Rendering vs commitment | Crowd of 500 needs visuals without 500 identities | Renderer draws density fields; individuals collapse only on interaction | ◐ D |
| Depowering | Global refinement event; coarse-committed crowds must re-fine | Filtration constrains refinement; flagged as special event; needs prototype test | ● O |
| Latent rot | Stale z-vectors summon anachronisms | Validity windows + periodic latent reconciliation | ◐ P |
| Permanent companion | Unbounded memory growth | Memory stream + reflection/summarization (generative-agents pattern [^1]); long-haul test pending | ◐ D |
| Player lies | Persistent false identity | Identity as wiki entry contested by performance; policy needed | ◐ O |
| Deceived senses | Illusion poisons appearance distributions | Deception as explicit mechanic with cost model and counters | ◐ P |
| Simultaneous frontiers | Scrying A while present in B | Bookkeeping fine; narrative-allocator policy needed | ○ O |
| Eventfulness | LLM drama bias in backfill | Sampled quantity + quiet-years few-shot (§5.2) | ● D/P |
| Rumor vs bug | "Gossip got it wrong" vs "system lost a fact" | Trust-provenance UI: rumors always show provenance class; needs a deliberate presentation policy | ◐ O |

---

## 10. Technical architecture

### 10.1 Modules

```
┌──────────────────────────── KERNEL (no LLM) ───────────────────────────┐
│ sampler:   GMM drift–diffusion, analytic time-skip, hash-seeded RNG    │
│ validator: hard-consistency, reachability, budgets, counter agreement  │
│ counters:  analytic state variables                                    │
│ collapse log / contact graph / latent pool                             │
└─────────────────────────────────────────────────────────────────────────┘
┌──────────────── PROMISE ENGINE ────────────────┐  ┌──────── WIKI ──────┐
│ active ledger, lifecycle, TMS-lite suspension  │  │ graveyard facts,   │
│ density index (importance)                     │  │ trust, vector RAG  │
└─────────────────────────────────────────────────┘  └────────────────────┘
┌──────────── ORCHESTRATOR (LLM service) ────────────┐  ┌─ NARRATIVE ─────┐
│ event queue, batch loop, chapter planner, tools    │  │ backfill worker │
│ drama budget, audit log                            │  │ gossip transport│
└─────────────────────────────────────────────────────┘  │ digest compiler │
┌──────────── GAME CLIENT ───────────────────────────┐  │ perf. layer     │
│ 2D/2.5D renderer (density fields + collapsed ents),│  └─────────────────┘
│ observation frontier, instruments, combat, shrine  │
└─────────────────────────────────────────────────────┘
```

### 10.2 Data flow (two loops)

**Fast loop (no LLM):** input → physics/combat → observation frontier → collapse sampling → render. Frame-budgeted; never blocks.
**Slow loop (LLM, async):** events → queue → prefetch/batch → generate → validate → commit (promises/wiki/counters) → instantiate/prose delivery. Diegetic delay absorbs latency.

### 10.3 Save format

`{world_seed, collapse_log, promise_ledger(active+graveyard), counters(t₀ anchors), latent_pool, wiki_db, audit_log}`. Everything else is derivable.

### 10.4 Recycling from Ara (module mapping)

| Ara module | Becomes | Notes |
|---|---|---|
| `fortune/` (rolls, distributions, I-Ching, grammars) | Sampling/omen/content layer | Lift wholesale; simulation-agnostic |
| `memory/wiki.py` (trust scores, importance, distance cap, querier reframing) | Wiki/graveyard store | Add typed-promise schema + temporal validity metadata; `invented_fact_NNN` IDs → entity-stable UUIDs |
| `world/summarizer.py` (block format: FACT/TRUST/SOURCE, location finalization, keyword prefetch) | Backfill worker + commit message schema | The location-change classifier → terrain-diff commit gate |
| `llm/context.py` (per-entity visibility slices, hidden rules, branch/KV discipline) | Observation-log reader; prefix-stability patterns | Strip to visibility core |
| `world/orchestrator.py` (dynamic enum schemas, strict JSON, retries, fallback, tool loop) | Orchestrator service plumbing | Rebuild loop around event triggers; keep schema/retry patterns |
| `spawn_anonymous` | Degenerate summon (Tier-2 NPCs) | Generalize upward to z-vector summons |
| `memory/knowledge.py` (scratchpads, per-character RAG) | NPC internal state + memory | Goals become Chekhov-seed soft promises |
| `prompts/orchestrator.py` (binding rolls, player-freedom guarantees, invisible steering) | Orchestrator system-prompt lineage | Add promise-tool instructions, intent rules (§4.6), audit logging |

Not recycled: VN surface (sprites, webclient), scene graph / authored plots, per-turn orchestration rhythm.

### 10.5 Genres from the same kernel

Three dials re-skin the engine: **observation frontier** (what can be seen), **promise lifetime** (how long commitments bind), **collapse cadence** (how often the world is measured).

- **Immortal / long timeline:** player as persistent anchor; the graveyard ledger is the content.
- **Farming sim:** tiny map, dense promise lattice (crops, animals, courtships), high cadence, seasons as dominant clocks.
- **Invisible eyeball:** observation as the only verb; attention writes the world; the audit trail is the game's conscience.
- **Ara itself:** one room, cadence = every line of dialogue.

---

## 11. MVP plan

**M0 — Kernel (2–3 wks):** 2D tile map, avatar with observation cone, ~50 entities as GMM distributions, drift–diffusion + analytic time-skip, hash-seeded collapse, collapse log. Success: walk away and return; re-collapse is consistent; demo "not found here" renormalization.

**M1 — Promise engine v1 (2–3 wks):** promise records, hard-only validation, wiki (Chroma) with trust, graveyard archival, density index. Success: coarse-then-fine measurement never contradicts; wiki renders as a readable chronicle.

**M2 — Narrative loop (3–4 wks):** backfill worker (one village), gossip among ~20 NPCs, eventfulness sampling, digest epochs, batch queue, DeepSeek integration. Success: leave for a season; return to a validated, archaeologically legible history; cost within §7.5 envelope.

**M3 — Orchestrator steering (3–4 wks):** intents as soft promises, drift/z-bias channel, tempering + drama budget, audit dashboard (override rate, KL, player-correlation). Success: auditor cannot locate the player from outcome statistics; omens telegraph intents.

**M4 — Game systems (ongoing):** instruments/tracking, shrines, combat field-vs-peer, latent pool + summoning, politics slice (one court, regime latent, conditional validity).

Explicit non-goals for MVP: multiplayer, depowering, illusion systems, full politics.

---

## 12. Open questions

1. Depowering as a global refinement event — does the filtration survive a fidelity ramp of that size, or is it a special-cased apocalypse? (Prototype target M2–M3.)
2. Presentation policy for rumor-vs-bug: how much provenance does the UI expose before it breaks immersion?
3. Illusion/deception cost model and counters — how expensive is lying to instruments?
4. Player-authored history: should the player be able to *write* the wiki (propaganda as endgame), and at what trust authority?
5. Simultaneous-frontier narrative allocation policy.
6. Eventfulness distribution calibration per biome/political temperature — needs playtest data.
7. Promise predicate vocabulary: minimal typed-claim set that covers politics without becoming a logic-programming project.

---

## 13. Prior art and references

- **Generative Agents (Park et al., 2023)** — memory stream + significance-gated reflection + planning; the standard LLM-NPC three-layer; retrieval by recency × importance × relevance. Basis for the companion/memory pipeline and the digest compiler.[^1]
- **Promise Theory (Burgess, 2004–2026)** — autonomous agents coordinating via voluntary promises rather than obligations; agent-as-node, promise-as-edge graphs; namesake and partial formal ancestor of §4.[^2][^3]
- **Truth maintenance (Doyle JTMS 1979; de Kleer ATMS 1986)** — defeasible facts with assumption dependencies; lineage of the suspension/reconciliation machinery.
- **Left 4 Dead AI Director (Booth, Valve)** — emotional-intensity tracking, peaks-and-valleys adaptive pacing; canonical lessons in detectable steering.[^4]
- **Drama-management lineage** — Façade (Mateas & Stern), IPOCL, PaSSAGE player modeling; RimWorld's AI Storyteller as the commercial archetype the orchestrator generalizes; AI-native game framing per a 2026 survey.[^5]
- **Dwarf Fortress** — legends generation as *eager* history (the anti-pattern this design deletes); adventure mode as the ARPG reference; Tarn Adams' observation that players read novels into simple routine-following motivates the schedule layer.
- **DeepSeek V4 API** — pricing/model facts as of 2026-07 (V4-Flash $0.14/$0.0028/$0.28 per 1M miss/hit/out; V4-Pro $0.435/$0.87 promo, list $1.74/$3.48; 1M context; legacy aliases retire 2026-07-24).[^6][^7]
- **Quantum Zeno effect** — frequent measurement inhibits evolution; the heartbeat-cadence knob of §3.5.

---

[^1]: Park, J. S. et al., "Generative Agents: Interactive Simulacra of Human Behavior," arXiv:2304.03442 (2023). https://arxiv.org/abs/2304.03442 — architecture summary per https://zylos.ai/research/2026-04-20-memory-consolidation-ai-agents/ and https://memx.app/glossary/generative-agents/
[^2]: Burgess, M., "Cooperation in Human and Machine Agents: Promise Theory Considerations," arXiv:2604.10505 (2026). https://arxiv.org/pdf/2604.10505
[^3]: Borrill, P., Burgess, M., Dvorkin, M., "A Promise Theory Perspective on Data Networks." https://arxiv.org/pdf/1405.2627
[^4]: Booth, M., "The AI Systems of Left 4 Dead," Valve. https://www.readkong.com/page/the-ai-systems-of-left-4-dead-michael-booth-valve-9664541
[^5]: "AI Native Games: A Survey and Roadmap," arXiv:2607.00527 (2026). https://arxiv.org/html/2607.00527v1
[^6]: DeepSeek API pricing aggregator, verified 2026-07. https://techjacksolutions.com/ai-tools/deepseek/deepseek-pricing/
[^7]: DeepSeek API model/pricing summary, verified 2026-07. https://www.morphllm.com/deepseek-api
