# Unwritten — Generation Addendum

**Status: draft v0.1 (2026-07-20).** Addendum A1 to the Unwritten Engine Design Specification ("engine spec") and the Unwritten Lab Experiments Repository Specification ("lab spec"). Engine-level throughout: this document commits the *game type* and the *generative substrates*, not a game. Where a mechanism here contradicts or refines the engine spec, the amendment is stated explicitly and collected in §17; parent documents are not edited by this addendum.

Sources: design conversation of 2026-07-20 (normative; user corrections override earlier text, including the engine spec where noted), grounded against `unwritten-engine-design-specification.md` and `unwritten-lab-experiments-repo-spec.md` in this repo.

---

## 1. Type commitment and preconditions

The engine spec is deliberately game-agnostic; every unresolved parameter in it (cull boundaries, cadence, observation bandwidth) kept slipping because the answer depends on the game's shape. This addendum fixes the shape. The commitment is a set of **preconditions the engine may rely on**, stated so that a different game type would know exactly which mechanisms it invalidates:

1. **Render model.** DF-like top-down tile/sprite render. Distant render is low-bandwidth: a far sprite conveys *class, position, activity* — never individuating identity. This precondition is load-bearing for §10 (observation bandwidth) and therefore for the entire culling economy.
2. **Tick model.** Tick-based simulation with real-time render; conventional frame loop in-render with zero LLM involvement (engine spec §10.2, unchanged).
3. **Scale class.** A world where walking matters: one contiguous region of tens of kilometers, settlements at village/town/capital scales, a frontier beyond them. Map size is a dial; the *class* is committed.
4. **Population class.** Hundreds of entities visible at most; thousands latent. Named-entity capacity in the low hundreds; anonymous mass unbounded because it is sampled, not stored (§10).
5. **Protagonist.** Pointlike avatar (one observation cone, bounded velocity — the license for simple collapse bookkeeping and an accurate prefetch oracle), powerful (the license for coarse-graining: power lowers the *demanded* resolution, per the lab spec's D1 amendment).

**Mechanic selection (the irreversible decision):** the world is made of three generative substrates — **terrain, structures, entities**. Not ecology-first, not physics-first. Staged terrain generation (§3), structure templates (§4), and the entity lifecycle (§10) are downstream of this choice. Features (§5) are terrain-adjacent; population is a decoder of feature latents (§6).

**What stays open:** numbers. Entity capacity, chunk size, trickle rates, cadence constants remain dials — but dials *within a committed machine*, expressed as bounded ranges with tradeoffs noted, not as unresolved design questions.

**Belonging test** (for future edits): if removing the DF-like assumption breaks a mechanism, it lives in this addendum; if a mechanism survives any game type, it is main-spec material that happens to be written here.

---

## 2. Design principles (the spine)

Five principles unify everything below. They are stated once here and referenced throughout.

- **P1 — Generator parameters are a steering surface; every steering act is a promise.** The orchestrator never pokes a parameter silently. Biasing worldgen, coining a structure template, placing a feature — all are recorded in the promise ledger with provenance, so the audit trail (engine spec §6.3) covers *why the world looks like this* with the same machinery that covers plot steering.
- **P2 — Single latent, many decoders.** Consistency by construction, never by reconciliation. One z decodes terrain stamp, structures, population, wiki entry, and chronicle (extended from engine spec §3.6).
- **P3 — Delivery is measurement; in-transit state is distribution.** Rumors on the graph, travelers on the roads, unrendered NPCs: all distributions. The moment content reaches a witness — overheard, spoken, seen at individuating range — it crystallizes and commits.
- **P4 — Curated types, parametric z.** The LLM's creativity flows into parameter selection, naming, and history — never raw geometry, never raw semantics. Extended: LLM creativity flows into *selection and assignment*, never open invention (§8).
- **P5 — Entropy comes from curated corpora, never from the LLM's prior.** Anywhere culturally textured content is needed (names, taverns, dishes, slang, heraldry), the entropy source is a precurated corpus sampled hash-deterministically; the LLM is a constraint-satisfier over a presented subset, not a generator (§8).

---

## 3. Staged terrain generation

**Problem.** Procedural worldgen must be biasable by the orchestrator (P1), deterministic and replay-safe (engine spec §3.7), checkable against geographic claims made in conversation (§12), and consistent across chunk boundaries. Per-chunk generation with per-chunk parameters satisfies none of the last two: a constraint like "two days north, past the river" spans chunks and cannot be seen by a chunk-local generator.

**Design.** Three layers, each a collapse tier bound by the filtration invariant (coarse commits bind fine collapse — the engine spec's measurement semantics applied to terrain):

- **L0 — global sketch. Committed at world creation.** Whole map, low resolution: coarse heightfield, drainage networks, climate/biome zones, mountain ranges, and the **route graph** (roads as edges, not geometry). Cheap because coarse. This is the layer the orchestrator's worldgen parameters (altitude, climate, biome, population density…) primarily bias, and it is the layer geographic claims are checked against from day one.
- **L1 — regional. Lazy, promise-constrained.** Generated on approach or observation; must refine L0. Utterance constraints and location promises land here as obligations the generator must satisfy (§12).
- **L2 — chunk detail. Render tier.** Purely local; inherits L1.

**Authority rule.** Committed promises outrank parameter bias wherever they conflict. Bias is a soft steering channel; promises are the hard substrate. If the ledger demands a northern river, the northern region's climate parameters change — retroactively but legally, because that terrain was never observed (prime directive, engine spec §4.2).

**Determinism.** Generation is `outcome = H(world_seed, region_id, constraint_digest)`, where the constraint digest covers the active promise set touching that region. Generation is therefore constraint-dependent and order-dependent — safely: constraints change only through ledger commits, and the save format (seed + collapse log + promise ledger + wiki, engine spec §3.7) replays commits in order.

**Cost acknowledged honestly.** L0 freezes gross geography at world creation, slightly dimming the "frontier stays strange" aesthetic — the frontier's *shape* becomes known to the engine early. Accepted: only at sketch fidelity, only to the engine (never the player), and all dreamlike weirdness lives in L1/L2, untouched. In exchange the world is globally consistent *by construction*, which is exactly what faithful geographic conversation (§12) stands on.

**Chunk boundaries.** Dissolved, not managed: rivers, ranges, roads, and cross-chunk constraints live at L0/L1; L2 chunks inherit. Heartbeat cadence is entity/feature-anchored, never chunk-anchored — a promise-dense village straddling a chunk boundary gets one cadence, read by the chunk generator (amends the engine spec's spatial phrasing in §3.5).

---

## 4. Structures and paths

**Structures.** Fully procedural buildings are rejected (P4): no good generators, no validation surface. Instead, **presets with parameters** — a curated library of structure types, each a small interpretable parameter vector and a vetted procedural generator (the §3.6 "curated types" rule applied to buildings).

**The template registry is world-state.** The orchestrator may modify parameters and *save* a template for reuse ("border-fort, war-torn variant"). Saved templates are versioned, content-addressed, and **promise-backable**: coining one is a ledger act (P1), and reusing one is validated against the active ledger — if the world changed since the template was coined (latent rot, engine spec §9.4), reuse is flagged for reconciliation. An orchestrator-coined template is a narrative fact; it can be referenced, contradicted, and discharged like any other.

**Paths are two-level.**

1. **Connectivity lives at L0's route graph** — which structures *should* be reachable. This level is promise-addressable: "there is a trade road between X and Y" is a location promise constraining the graph, authorable by orchestrator or NPC utterance (§12).
2. **Geometry is generated per-edge at L1/L2** — procedurally, constrained by terrain.

`connectedness` is a first-class structure parameter (a fort on a spur road reads differently from a fort at a crossroads), feeding both the route-graph prior and the gossip network's contact rates (roads are the contact graph's edges made literal, §6, §11).

---

## 5. Features and tilesets

**Core tileset: fixed and closed.** Rock, soil, water, ice, magma, vegetation classes — a small curated vocabulary. Rationale: the simulation kernels (mean-field dynamics, counters, hazard model) need a closed vocabulary to reason over; an open tileset makes terrain render-only.

**Orchestrator-created tiles are derived types.** The whole game is DSL-moddable in principle (user requirement), bounded by one rule: a new tile must **compile down to a property vector over the core ontology** (physical properties, affordances, hazard contributions). Tiles that compile are first-class — simulable, validatable. Tiles that don't are **cosmetic-only**, stated explicitly at authoring time, never silently. This is the tile instance of P4.

**Latent pool, amended.** The engine spec's latent z-vectors (§3.6: interpretable parameter vector, coarse spatial prior, narrative role) gain one field family: **utterance constraints** — hard fields in the spatial prior derived from everything ever *said* about the feature (§12). Placement solve scores candidate sites against the accumulated intersection of all utterance constraints plus observed terrain. Prime directive check and validity windows are unchanged.

---

## 6. Entity generation

**Population is a decoder, not a generator.** The strongest structural move in this addendum: a settlement's roster decodes from the *same feature latent* as its terrain stamp, structures, and chronicle (P2). Add `population, wealth, occupations` to the village z's parameter vector; the mill has a miller because one z says so — no cross-system reconciliation. Density, climate, and terrain inputs are read off L0/L1, so population follows geography by construction.

**Bundled and free entities.**

- **Bundled NPCs** are conditioned on a feature latent: villagers in villages, cityfolk in cities, monsters in forests (user's enumeration, adopted). Their routines, houses, and roles decode with the settlement.
- **Free NPCs** (adventurers, wanderers, merchants) are conditioned on the **route graph**: they live on L0's roads. This makes them the gossip network's edges *animated* — the contact graph's transport layer walking around in render (§11).

**Groups are first-class entities.** Family, household, adventurer band: a group gets `scope: group` in the promise ledger (extends engine spec §4.1's scope enum) and its own promise records. Membership is a predicate with a window, which plugs group lifecycle into the decay model (§9): child grows up → `member_of` expires and a new household latent spawns; party disbands → group promise discharges to the graveyard as backfill texture ("the Broken Oaths used to winter here"). Mutable allegiance (an adventurer leaves the band to follow the player) is a committed event updating the vector, checked by causal reachability like any other change.

**Routines are the interface layer.** Parameterized schedules (occupation, wealth, season) executed by the reflex layer in-render and by the mean-field offscreen. Routines exist because of *measurement*: collapse commits "a trader is here at noon," which must be a plausible sample from the trader's routine distribution. Routines are what makes the analytic sim and the render agree.

**Labor division (user requirement, extended).** DF/RimWorld demonstrate heuristic AI suffices for bodies. The division:

- **Code (heuristic):** per-frame reflexes, pathing, schedule execution, utility AI, combat. Bodies.
- **LLM:** (a) **biasing** — intent→z parameter selection; (b) **switching** — fidelity routing across anonymous/named/principal tiers; (c) **resolution** — collapse and backfill generation; (d) **social-graph authoring** — the content of relationships: feuds, debts, grudges with texture. Heuristics *execute* a feud; they cannot invent one worth having. (e) **promise authoring** — NPC intents as promise records; the LLM writes them, the machinery enforces them. (f) **name assignment** — under corpus constraint (§8).
- **The ledger remembers.** The line to hold: the LLM writes minds and histories; heuristics move bodies; the ledger is the only memory.

**Caution — audit for downstream reach.** Entity parameters are not cosmetic: lifespan feeds the hazard model (§9), which feeds promise decay, which feeds Zeno cadence, which is the entire village-persistence mechanism. Race and population parameters are audited for downstream effects on hazard and cadence, not just render stats.

---

## 7. Races and monsters

**Races: curated parameterized library, committed upfront.** Race is a decoder-side template: physiology, lifespan (a hazard-model input — see §6 caution), stat distributions, culture priors, name corpus reference (§8). A diverse library is authored before launch; there is no way around predefinition (user requirement), and none is needed.

**Orchestrator-coined races: rare, frontier-only.** A coined race is a new point in race parameter space that must compile to the core ontology (the §5 derived-type rule). The frontier-only restriction is load-bearing, not merely practical: a new people inserted anywhere observed violates the prime directive (retroactive geography of populations), while a new people at the frontier is the latent pool working as designed — and the gossip network telegraphs them for free ("traders speak of feathered folk past the southern wastes") long before arrival. By the time the player arrives, the race has a rumored history, which is better than any generated one.

**Exception — the chimera template (user requirement).** Custom monsters *want* variety, and rare species are fine, because monsters have the inverted promise lifecycle: an NPC accrues promises; a monster's narrative purpose is to be *discharged*, typically within minutes of observation. Low persistence means low consistency obligation. So: one maximally inclusive `chimera` race — morphology knobs, hazard profile, behavior-tree parameters, resistances, loot — compiling to the core ontology, covering the long tail the curated library shouldn't bother with.

Two constraints:

1. **Rumor-constrained knobs.** A monster mentioned in gossip is a latent obligation; the chimera's knobs are set by the *rumor* (with its accumulated per-hop perturbations), not freely. The telephone game decides what the thing is before the summon does.
2. **Graduation path.** A knob-monster that *survives* — evades the player, gets named, accrues promises — crosses into personhood and inherits the full entity machinery. The dragon of engine spec §9.3 is exactly a graduated monster. Monsters that won't die become people; treat this as one of the best story generators in the system, not a bug.

---

## 8. Naming and cultural texture

**Problem.** LLM name generation is unusable even at high temperature (user requirement, endorsed): the bias is in the model's *prior*, not the sampling. Training data concentrates fantasy naming on one Anglo-Celtic aesthetic; the output is genre slop at any temperature.

**Design (user proposal, adopted and generalized — P5).**

- **Precurated namelists are the entropy source.** Large, tiered by culture/region/era, part of the race library (§7).
- **The subset draw is hash-seeded.** `subset = H(world_seed, culture_id, naming_context)` — deterministic, replay-safe (K1). Regional naming texture falls out of the sampling: villages in one culture share phonotactics; regions genuinely differ.
- **Three tiers.** (a) *Grammar tier:* a phonotactic model (trigram/Markov) trained per curated list generates novel-but-native names for the anonymous mass at zero token cost — DF's language-files approach. (b) *List-direct:* named NPCs draw from the corpus. (c) *LLM-as-assigner:* principals only — the sampled subset is presented as must-incorporate inspiration, and the LLM selects and adapts for narrative weight (which name fits a miserly miller versus a war widow). **The LLM never invents a syllable.**

**Names are references, not text.** A name is a corpus ID committed to the ledger at summon. Gossip perturbs *reference-to-reference* (the telephone game swaps "Old Fenwick" for a similar corpus entry) rather than regenerating strings — distortion stays legible, and names cannot converge toward the LLM's mode as they travel.

**Generalization.** The rule applies anywhere culturally textured content is wanted: tavern names, dishes, slang, heraldry. Curated corpus + sampled-subset constraint, never open generation.

---

## 9. Promise semantics amendments

These amend engine spec §4; collected in §17.

**9.1 Predicate decay classes — carried by the type schema, never decided procedurally.** The predicate vocabulary is small and curated (`alive`, `located`, `holds_office`, `knows`, `owes`, `member_of`… — a dozen types, matching the lab spec's minimal-vocabulary finding). Each type's *schema* declares its decay class, authored once:

- **Permanent** — identity (name, face), death. Never decays; filtration floor.
- **Durable** — office, relationships, debts. Long windows, renewable by heartbeat.
- **Ephemeral** — location, current activity. Short windows; true *as of observation*.

New predicate types proposed at runtime default to the most conservative class until curated. There is no per-instance classification problem: the LLM instantiates predicates of a type; it never picks a class.

**9.2 The `active → prior` transition ("last-known" semantics).** An ephemeral predicate commits a fact at time *t*, then degrades from *constraint* to *prior*: it biases sampling (the miller is probably near the mill) but no longer constrains validation (the miller may be at market). This requires extending the status enum (`active | suspended | discharged | broken | expired`) with `prior`. Without it, ephemeral predicates are either absurdly strong (Zeno-frozen at the mill) or silently wrong.

**9.3 Density metric weighted by predicate, not entity.** Promise density (engine spec §4.5) weights by predicate count and class: permanent and durable predicates drive heartbeat cadence; priors drive backfill texture only. Fixes the face-in-the-crowd overvaluation: a glimpse commits one ephemeral predicate that becomes a prior within days and stops paying fidelity rent almost immediately; the miller you bargained with carries twenty live predicates.

**9.4 `alive(e)` is special: an absorbing hazard process, not a windowed predicate.** Offscreen death is a hard requirement — a living NPC must be able to collapse to a corpse or a grave, naturally. Resolution:

- **As-of-t semantics.** `alive(e)` commits "alive at observation time," not an invariant. Death afterward is a state transition, not a contradiction; the prime directive forbids *retroactive* contradiction only.
- **Mortality is a hazard process.** Population-level mortality rates are conditioned on age, occupation, race lifespan (§7), and regime counters (war, plague, famine) — the K4/mean-field machinery. Offscreen death is a deterministic hashrng sample against the hazard over Δt. No LLM decides the miller dies; the demographics do, reproducibly.
- **Correlated sampling.** Independent per-entity rolls produce uncanny results (half the village dead in a quiet year). Hazards couple through the counters: a plague year raises rates *together*, so deaths arrive in legible clusters with a shared cause — backfill writes one story ("the fever winter"), not eight coincidences.
- **Telegraphing.** The gossip network seeds illness rumors before death commits ("the miller is ailing" — one soft predicate, one gossip entry), so arriving at a grave reads as causal sequence, not arbitrary reroll. The §4.6 principle applied to mortality: announced is a mechanic, silent is a rail.
- **The grave is the collapse record.** Return backfill commits `dead(e, t, cause)` + `located(grave(e), churchyard)`; the discharged promise archives as archaeology (§9.2 of the engine spec, the family mark on the ruined mill).
- **Cadence controls death granularity, never immunity.** A promise-dense NPC's hazard is evaluated in small heartbeat steps — no jump from "healthy at observation" to "long dead" without intermediate commits; the validator's causal-reachability check forces pacing and cause. A sleeping NPC's death is sampled in one step and needs only demographic plausibility. The familiar village loses people *slowly, with reasons, rumor preceding*; the frontier village can be a ghost town on return.

**9.5 Village persistence, stated honestly.** Persistence and legible decay emerge from the ledger (§4.5, §3.5). Dramatic change to still-important places does **not** emerge — promises constrain; they never command change. Large delta enters only through authored doors: promise collision (§4.6), sanctioned diegetic events (disaster, war, construction), or promise expiry followed by free evolution. This is a coherent position — change is always earned — but it is stated here explicitly rather than assumed emergent.

---

## 10. Entity lifecycle, culling, and observation

**10.1 The committed/sampled split.** The operative distinction is not "important vs. unimportant" — it is **committed vs. sampled**. Sampled entities are render-instantiated draws from population distributions; nothing about them exists in the ledger. Committed (promoted) entities have ledger entries. Everything below follows.

**10.2 Four-state lifecycle.**

```
sampled ──(player interaction)──► promoted ──(leaves relevance)──► latent traveler ──► graveyard
   │                                  │
   └── cullable, discardable          └── never deleted except through the death machinery (§9.4)
```

- **Sampled → promoted:** on *interaction* only (speech, trade, combat, being followed). Promotion *captures* the entity's current derived state — appearance, position, routine phase — into the ledger, so continuity across the promotion boundary is exact: the promoted NPC keeps the face the player already saw.
- **Promoted → latent traveler:** when a ledgered entity wanders off or the player leaves, it demotes to a z-vector plus a route-graph position — bytes. Trickle-eligible, gossip-eligible, resurface-eligible. **Demotion, never deletion**: the player may hold the entity's promises ("I'll be in the capital by winter" has a window), and deleting a promise-bearer corrupts the ledger.
- **Latent traveler → graveyard:** only via the death machinery.

**10.3 Culling (user question — answered: yes, it works).** Barely-encountered entities collapse back to a population number on exiting render distance; no wavefunction needed, because nothing individual was ever asserted. The coarse commit is population-level ("market crowd, ~40"); the forty faces were a sample; the sample is discarded; the counter stands — filtration honored. Two provisions: (a) **pin within scene occupancy** — no reshuffling while the player stands in the market; cull boundary is chunk exit plus a short scene cache for "back at the stall thirty seconds later"; (b) promotion removes an entity from the cullable set forever.

**10.4 Why distant sight commits nothing (user correction, adopted).** In a DF-like render, a distant sprite conveys *class, position, activity* — never individuating identity (type commitment §1, precondition 1). Individuation never entered the player's head, so there is nothing to be inconsistent with: the cull is nearly free, and no content-addressed appearance machinery is needed at distance. What little the sprite *does* convey is already deterministic — class/position/activity are the routine schedule executing, derived from roles and counters. The information-theoretic rule: **required persistence ∝ what the render channel conveys.** Identity is born at the distance it becomes visible; in a sprite game, that is interaction range, where promotion happens anyway.

**Render bandwidth is the ledger-growth dial.** Cheaper distant render ⇒ more of the world stays uncommitted and cullable. Richer distant rendering (distinctive silhouettes, heraldry at range, telescope items, scrying) adds commitment surface — *observation instruments create facts* and are priced as such (aligns with engine spec §8.2, information as infrastructure). Every pixel of distant individuation costs ledger.

**10.5 Trickle at the render border (user requirements 2–4).** Entities enter render through the border by diffusion — the route graph animated:

- **Important travelers are promise-driven** (the messenger, the adventurer band): their motion is driven by their promises and they appear in the trickle with purpose.
- **Passive trickle** (farmers, peddlers, pilgrims) is sampled from L0 route-graph flow rates: road class, season, nearby settlement sizes, war/plague counters pushing refugees.
- **Conservation applies to counters, not samples.** Anonymous trickle is a statistical rendering of flow, not a transfer of ledgered individuals; sampling a peddler does not decrement the origin settlement. Conservation bites only at promotion, which is a ledger transfer (departed Millbrook, arrived capital) — and the promoted population obeys demographic balance automatically because it *is* the population, viewed individually, drained by the same hazard/emigration model. Entity count cannot grow unboundedly: only promotion consumes ledger, promotion is player-gated, and death/emigration drains it.

**10.6 "Nobody comes from nowhere" (hard invariant).** On promotion, backfill assigns an origin by constrained sampling — direction of travel, road, goods carried, speech register → a household latent in some settlement, near or far, or a group affiliation (adventurer band, merchant caravan, monster of the nearest feature latent). One z-vector, one wiki stub; cheap. This is what makes the trickle detective-compatible: every face is a thread that leads somewhere, and §8.7's knowledge-boundedness extends to geography.

---

## 11. Gossip insertion into render

**Model (P3).** Rumor in transit is a distribution riding the contact graph (K6: per-hop perturbation, trust decay). Delivery is measurement: the moment a rumor reaches a witness, its specific claims crystallize and commit.

**Transport is render-independent and entity-anchored.** While a settlement is unrendered, rumors hop into its NPCs' information states as trust-tagged claims. At chunk stream-in, gossip is already in the conditioning (engine spec §8.7's "imported gossip with inherited trust decay"): the miller materializes with his rumor inventory — same latent, many decoders. No injection step at render time.

**Four delivery channels, four fidelity tiers.**

1. **Conversation** (§8.7): the NPC relays at *their* trust level with *their* accumulated errors; knowledge-bounded.
2. **Overhearing** (§5.4): NPC–NPC exchange is a first-class collapse — eavesdropping as worldgen. The exchange's context backfills and commits at the moment of overhearing; before delivery the rumor was a perturbed distribution, after delivery it is fact-of-record that *these NPCs said these words*.
3. **Goal-layer writes** (§8.6): rumor changes disposition without dialogue — the dragon rumor lands, shutters close, the north road empties. The player infers the rumor from behavior; information enters render at zero tokens.
4. **Ambient tier:** anonymous NPCs emit rumor-flavored barks via template expansion of one structured record. Cheap texture.

**Pacing is a queue problem, not a trigger problem.** Deliveries are salience-scored into the batch queue (§7.3), capped by the eventfulness budget — a scene can only carry so much news before it reads as exposition dump. NPCs predicted to be talked to get prefetch weight.

**No silent reconciliation.** Contradictory rumors stay contradictory in render: each NPC's version derives from *their own receipt path* (graph distance, teller chain), so disagreement is structural, not scripted. The implementation trap to forbid by name: conditioning multiple NPCs on a shared "current rumor state," which silently collapses the contradiction and kills the detective gameplay (triangulating trust gradients) that contradiction exists to provide.

---

## 12. Geographic faithfulness in conversation

**Principle.** The LLM never asserts geography. It renders geographic facts from a queried subgraph, and every novel spatial claim it speaks becomes a promise, not a fact.

**Three knowledge fidelities.** An NPC's geographic knowledge is a subgraph of the spatial store, filtered by what they could know:

- **Measured fidelity** — lived surroundings, from their measurement history. Precise; validator-checked.
- **Experienced fidelity** — places they have been. Coarse-grained but correct relations.
- **Rumored fidelity** — everything else, arriving through the contact graph with trust decay *and spatial distortion*: K6's per-hop perturbation applies to place as well as content. Different NPCs point slightly different directions to the same latent fort; the player triangulates; map annotations ("rumored: fort, NE, low trust") fall out of §8.7's hearsay handling.

**Closed relation vocabulary.** Geographic claims use typed relations (`north_of`, `across_river_from`, `adjacent_road`, `travel_days`) over feature IDs. Collapsed-terrain claims are checked mechanically against committed geometry; rejection is silent (the line never happens).

**Utterance constraints mint into latent priors.** When conversation creates a geographic obligation ("the bandits came from a northern fort, two days off, past the river"), the specifics land as hard fields in the latent pool entry's spatial prior (§5): sector, drainage-relative constraints, distance band from the utterance location. The placement solve (§3.6) scores candidate sites against the accumulated intersection of *all* utterance constraints from every NPC who ever mentioned the place, plus observed terrain. Faithfulness is enforced at summon time, not utterance time: the NPC's words are cheap; the ledger guarantees the world eventually makes them true.

**Route claims are validated.** Directions within committed space ("follow the road past the ford") are checked by an actual pathfinding query against the deepest committed layer (L0's route graph suffices at sketch fidelity) before the utterance is allowed. If no such path exists, the NPC gives vaguer directions or is wrong *in character* — wrongness is legal when chosen, never when accidental. Route claims touching latent corridors attach a promise to the corridor so its eventual L1 collapse honors the claim; hearsay stays hearsay — the player walking the route is the measurement.

---

## 13. Fidelity spikes

**Problem (user-stated, adopted).** In-render behavior is heuristic; offscreen history is LLM-narrated. The render will always be poorer than the chronicle. This is unavoidable; the design response is to make it true-on-purpose rather than concealed.

**Density is compression.** The chronicle is rich *because* it is compressed — a year of village life backfills to three sentences (the fever winter, the miller's feud, the bridge raid); lived at 1:1, that year is weather, porridge, and a four-month glare. The asymmetry is not LLM-vs-heuristic but *narrative time vs. lived time*. The render's quietness is the correct texture of the present tense.

**The render is the substrate for agency.** A render as rich as the backfill — NPCs autonomously betraying each other in view — would make the player an audience member in a system built against railroads. The heuristic world's *stability* is what makes player action legible: when something happens in render, the player caused it, chose it, or can intervene. Calm baseline is the canvas agency is painted on.

**The dial turns both ways.** The eventfulness budget (§5.2) throttles backfill richness as well as guaranteeing some; the gap is *tuned*, not suffered. The chronicle is calibrated down until the residual gap reads as "the texture of the present" rather than "the render is broken."

**Aftermath routines: the render's real fidelity budget.** The actual failure mode is tone mismatch — villagers placidly hoeing three days after the committed bridge raid. Heuristics cannot generate excitement, but they can *perform consequences*: reflex/goal-layer presets parameterized by recent committed events (mourning, rebuilding, watchfulness, refugees on the road). The spec line: **eventfulness lives in the ledger and the rumor network; the render's job is reactivity, not generation.** The player experiences a world that is quiet around them, loud about things, and always visibly marked by what happened — which is also what real life feels like.

---

## 14. Ontology

| Exists | Form | Mutated by |
|---|---|---|
| L0 global sketch | coarse committed layers + route graph | world creation; orchestrator param bias (promise-logged) |
| L1 regional terrain | generated on observation | L0 filtration + active promises |
| Structure template registry | versioned, content-addressed records | orchestrator (promise-logged), validation on reuse |
| Latent pool entries | z-vector + spatial prior + narrative role + utterance constraints + validity window | utterance, orchestrator, placement solve |
| Entity states | sampled / promoted / latent traveler / graveyard | interaction, demotion, death machinery |
| Predicate store | typed schema with decay class per type | commits, windows, `active→prior` decay, hazard sampling |
| Hazard model | counter-conditioned mortality/emigration rates | counters, race templates |
| Name corpora | curated lists + per-culture phonotactic models | authoring only |
| Gossip information states | per-entity trust-tagged claims | K6 transport, delivery-as-measurement |

| Does **not** exist | Why |
|---|---|
| Free LLM naming or open cultural-texture generation | training-prior bias; P5 |
| Per-instance decay-class decisions | class lives in the predicate type schema |
| LLM-authored race/geometry/raw semantics | P4; derived types must compile to core ontology |
| Background simulation of unobserved places | engine spec, unchanged — heartbeat is measurement, not simulation |
| Deletion of promoted entities | ledger integrity; demotion only, death only via hazard machinery |
| NPC omniscience about geography | knowledge-boundedness extends to place |
| Chunk-anchored cadence or promise counting | cadence is entity/feature-anchored |

---

## 15. Invariants

1. **Terrain filtration:** L1 refines L0; L2 refines L1; no fine layer contradicts a coarser commit.
2. **Promise > bias:** active promises outrank orchestrator parameter bias in every generator.
3. **Replay:** `outcome = H(seed, region/entity, time, constraint_digest)`; all constraint change flows through the ledger.
4. **Nobody comes from nowhere:** every promoted entity has an origin decodable to a latent.
5. **No unmeasured death of the observed:** `alive(e)` as-of-t; offscreen death only via the hazard process, telegraphed ∝ promise density, recorded as grave/corpse collapse.
6. **Delivery commits; transit distributes:** content reaching a witness crystallizes; content in motion may remain contradictory forever until observed.
7. **Persistence ∝ channel bandwidth:** nothing persists that the render could not convey.
8. **Conservation at the counters:** samples are free; promoted entities are conserved transfers.
9. **Curated or conservative:** any uncatalogued type (predicate, tile, race) defaults to the most restrictive class until curated.

---

## 16. Failure-mode register additions

Severity: ● high ◐ medium ○ low.

| Mode | Severity | Handling |
|---|---|---|
| Template rot — reused structure template contradicts intervening ledger | ◐ | latent-rot machinery extended: version check + reconciliation queue at reuse (§4) |
| Tone mismatch — render placid under loud recent backfill | ● | aftermath routines (§13); eventfulness budget tunes both directions |
| Uncanny death clusters — independent hazard rolls decimate a village | ◐ | correlated sampling through counters (§9.4) |
| Silent rumor convergence in render | ◐ | per-NPC receipt-path conditioning; shared "rumor state" conditioning forbidden (§11) |
| Promise-bearer deletion corrupts ledger | ● | deletion forbidden; demotion to latent traveler only (§10.2) |
| Constraint-infeasible geography — utterance intersection is empty | ◐ | placement solve relaxes soft constraints in provenance order, logs relaxation as orchestrator steering (P1 audit) |
| Chimera inflation — knob-monsters crowding out curated content | ○ | rumor-constrained knobs; rarity budgeted like fate armor (telegraphed, drama-budget priced) |
| Reference-game drift — game-type preconditions erode under feature pressure (rich distant render) | ◐ | bandwidth priced as commitment surface; §1 preconditions re-reviewed on any render-feature addition |

---

## 17. Amendments to parent documents (stated, not applied)

Engine spec:

1. §4.1 promise record: add `group` to scope enum (§6); extend status enum with `prior` (§9.2).
2. §4.5 density metric: weight by predicate count/class, not entity count (§9.3).
3. §3.5: heartbeat cadence is entity/feature-anchored; "as promises expire" gains the decay-class mechanism (§9.1–9.2); `alive` singled out as hazard process (§9.4).
4. §3.6 latent pool: add utterance-constraint fields to the spatial prior (§5, §12).
5. §9.1/§9.2: unchanged in substance; §9.5 of this addendum states their honesty clause (dramatic change is authored).
6. §8.2: render bandwidth formally priced as commitment surface (§10.4).

Lab spec — new experiments implied (none specified here; to be scheduled with the assembly phase):

- `worldgen_layers` — L0/L1/L2 pipeline with filtration and constraint-digest determinism (stacks on K1).
- `hazard_mortality` — counter-conditioned, correlated death sampling + telegraphing (stacks on K4, K6).
- `promotion_cull` — the four-state lifecycle, capture-on-promotion, conservation at counters (stacks on K1, K2, K5).
- `namelist` — corpus + phonotactic tiers + hash-seeded subset draw (stacks on K1).
- `structure_templates` — preset registry, versioning, reuse validation (stacks on K5).
- `geo_faith` — knowledge-fidelity subgraphs, utterance-constraint minting, route validation (stacks on K5, K6, L1).

---

## 18. Open questions

1. **Route-graph fidelity at L0.** How much path structure must the sketch commit (roads only, or fords/bridges/passes)? More commitment enables earlier route validation; less preserves L1 freedom. Resolve in `worldgen_layers`.
2. **Window defaults per decay class.** Durable and ephemeral windows need first values parameterized by age/regime stability; calibration is a lab task.
3. **Group promise semantics.** Which predicates may have `scope: group`, and how does group-level heartbeat interact with member-level cadence?
4. **Constraint relaxation order.** §16's infeasible-geography fix needs a principled order over which soft constraints yield first.
5. **Aftermath-routine vocabulary.** How many presets (mourning, rebuilding, watchfulness, refugee flow) cover the event space before diminishing returns; authored content task.
6. **Reference-game constants.** The dials of §1 need first values: chunk size, entity capacities, trickle rates, heartbeat constants — to be fixed when the vertical slice is scoped.
