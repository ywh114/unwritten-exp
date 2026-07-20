# Unwritten — Addendum A2: Topology, Movement, Ecology, Items

**Status: draft v0.1 (2026-07-20).** Second addendum to the Unwritten Engine Design Specification. Companion to Addendum A1 (*unwritten-generation-addendum-spec.md*); this document **does not modify A1** — it builds on its staged terrain model (A1 §3) and entity lifecycle (A1 §10), and where it refines A1 statements the refinement is collected in §13. Engine-level throughout; A1's game-type preconditions (§1) are assumed.

Sources: design conversation of 2026-07-20 (normative), grounded against the K1/K2 kernels in this repo — in particular `exp/k2_gmm_dynamics/terrain.py`, whose split-strategy experiment is the empirical basis for §3.

---

## 1. The topological complex

A1 staged terrain into L0/L1/L2. This section states what those layers actually *are*: a **topological complex with metric decorations**.

### 1.1 Cells

- **Nodes (0-cells):** settlements, crossroads, fords, bridges, cave mouths. Route choices and edge terminations happen here.
- **Edges (1-cells):** roads, paths, navigable rivers. Arc-length lines s ∈ [0, L]; movement on them is 1-D (§3).
- **Patches (2-cells):** regions of terrain uniform enough to carry one OU drift field (attractor μ, mean-reversion θ, diffusivity σ) — meadow, forest, slope band, marsh. Patch boundaries are where movement behavior changes.
- **Incidence** is committed: which edges bound which patch, which nodes terminate which edges, which patches share which boundary segment.

The heightfield is render dressing. Movement, gossip, placement, and geographic language are processes **on the complex**; only the renderer needs the metric back. The world is a graph wearing a heightmap, not the reverse.

**Filtration becomes subdivision.** L1 refining L0 = subdividing the complex (splitting patches, adding detail edges) where every fine cell knows its parent. Refinement may subdivide, **never rewire**: a river cannot move, because that changes incidence, not geometry. (Terrain *events* that rewire are legal but tier-3; §7.)

**The consumers all reduce to complex operations.** Route validation is graph reachability (per mobility class, §4). Gossip transport is diffusion on the same edges — K6's contact graph and the route graph are the same object. Trickle flow rates live on edges; discovery hazards live on segments (§6). "Frontier" = subgraph far from observed cells; "near the player" = graph distance; `connectedness` (A1 §4) = node degree; promise scopes over regions are sets of cells.

### 1.2 The three-state cover

Each region of the map is in exactly one state:

1. **Unrefined** — has measure and coarse L0 properties, no committed internal structure. *Summonable.*
2. **Refined-but-unobserved** — structured by generation, never witnessed. *Subdivisible* (summoning into it is legal refinement).
3. **Observed** — collapsed records exist. *Immutable except by events* (§7).

**The latent pool is the unrefined remainder of the cover.** A latent feature's spatial prior is a constraint over the cover ("northern third, near drainage" = unrefined cells in northern patches adjacent to drainage edges; A1 §12's utterance constraints are measurable against it — distance bands are graph distance). Summoning = carving an open set: subdivision into (feature patch, connecting edges, a node where the path meets the road), the z decoding into the new cells' parameters and content (P2). Prime directive, topological form: **an open set is summon-eligible iff it contains no collapse records.**

Consequences:

- **Obligation debt has spatial accounting.** Each latent requires measure; the reserve of unrefined open sets shrinks as the player observes. **Latent rot, crisp:** a latent is rotten when its constraint set no longer intersects any unrefined open set of sufficient measure. Reconciliation: re-derive the constraint set, or discharge the obligation as legend (the fort never existed; the story did, and the story is ledgered).
- **The Zeno dial has geometry.** Promise-dense regions subdivide fine; the frontier is the large open sets of the unrefined cover — few constraints, huge measure, maximal freedom. "Zeno-frozen heartland, dreamlike frontier" is a statement about cell size and cover refinement, not only cadence.
- **Topological defects are auditable at L0 commit time:** dangling edges, isolated patches (zero-ε islands the placement solve must never select), self-intersecting edges without nodes, disconnected components. All mechanically checkable before anything generates.

---

## 2. Movement on the complex

Two regimes, both analytic, no ticks. Grounded in K2 as built (`kernel/gmm_dynamics`: per-axis OU, analytic time-skip, exact mass conservation, cyclostationary schedules).

### 2.1 On-graph traffic (the default)

Roads exist because terrain funnels movement; most traffic is canalized. On an edge, position is 1-D arc length; drift v is directional and purpose-biased; σ is small (roads suppress wandering — that is what roads are *for*).

- **Traversal is an event, not a simulation.** Drifted Brownian first-passage time is inverse-Gaussian in closed form (mean L/v, shape from σ). Entering an edge: sample arrival time via hashrng. At the node: sample next edge from flow rates. O(1) per traveler, deterministic, replay-safe.
- **Edge parameters are terrain-derived:** v and σ computed from road class, integrated slope (from the L0 heightfield), season counter, regime flags. A mountain pass in winter has a fatter first-passage tail; the overdue-caravan posterior *is* this object.
- **Winding roads are invisible to the model.** Arc-length parametrization means curvature never enters the dynamics; an endpoint attractor (OU mean-reversion toward s = L) behaves exactly correctly; stationary distribution piles up at the village. The one caveat is **Euclidean self-proximity**: on switchbacks, distant-in-s points are near in space. Dynamics unaffected; leakage placement (§2.3) and re-absorption must use *nearest segment*, not leaked-from one. Shortcuts (leaked entity cutting the corner, arriving faster than road-followers) are physically correct and allowed — the "I know a shortcut" mechanic, emergent. Pathology guard: a self-intersecting road requires a node at the intersection, else traffic crosses a crossroads without the option to turn (defect class, §1.2).
- **Mid-edge events need the bridge sampler.** `bridge_at(edge, s0, t)` — the 1-D Brownian-bridge distribution, closed form — for ambushes, meetings, and "position of the traveler at time t."

### 2.2 Off-graph diffusion (the exception)

Free 2-D movement uses K2's patch machinery. K2's open-question experiment (`exp/k2_gmm_dynamics/terrain.py`) already settled the mechanics: multi-patch dynamics are not affine (no single-Gaussian closed form), and the validated fix is the **split strategy** — split components at patch boundaries into truncated pieces, moment-match each, evolve each under its own patch's field, recombine. Accuracy is bought with mixture growth, so **a merge policy is mandatory**: cap components, merge by moment-matching, mass-preserving. This merge policy is new kernel work (**K2b**), scheduled in §12.

### 2.3 Boundaries: permeability, never reflection

Every boundary has a permeability **ε ≥ 0**, a leak hazard per unit time per unit mass near the boundary. Each evolve transfers an ε·Δt-proportional mass fraction across — a *transfer*, so K2's exact mass conservation survives. The ladder is machine-readable and committed at L0/L1: castle wall ε ≈ 0 (never zero — siege tunnels, the gate guard's cousin), river small except at fords, forest edge large. A **gate is a localized high-ε boundary segment**; the gate list is what route validation pathfinds over.

**Path leakage.** Entities bleed off roads: a traversal is a race between arrival (inverse-Gaussian) and leak events (exponential, rate λ per unit distance). Closed-form competing hazards; sample the minimum. Leak wins → transition edge→patch at the leak point's local frame; the entity diffuses off-road and re-absorbs patch→edge via proximity hazard. **λ is purpose-conditioned:** king's messenger λ ≈ 0; forager high; lost traveler *growing* with time since last certain location. Messengers, hunters, and overdue caravans from one parameter.

**Conservation form:** leaks never create or destroy mass — everything is a transfer between regimes, every transition a hashrng-sampled event on a disjoint stream index.

---

## 3. Mobility classes

A curated, closed set of locomotion templates; every diffusing thing carries exactly one. A class is:

1. **A filtered view of the complex** — which patches it may occupy, which edges traverse, which boundaries cross at what ε-multiplier. One complex, N class-views:
   - *fish:* the water subgraph; land boundaries ε = 0 for them (leaky only diegetically, via flood events);
   - *birds:* the maximal subgraph, ε ≈ 1 nearly everywhere — the great connectors, seed- and omen-carriers;
   - *carts:* road-class edges above a quality threshold; **λ = 0** — a cart off-road is an *event* (broken axle, bogged), never a diffusion outcome; this is why caravans are trackable;
   - *foot:* the default view — most patches, all walkable edges, moderate ε multipliers;
   - *mounted:* edge-faster, patch-restricted.
2. **A parameter table** — (v, σ, θ, λ) per patch/edge type. Curated numbers; the LLM never touches locomotion.

Consequences:

- **Mounts are class switches.** On horseback you are faster but topologically *poorer* — regions exit your accessible subgraph; dismounting switches class, the horse waits at the boundary as a promoted entity.
- **Class-aware route validation** (refines A1 §12): the pathfinding check runs on the speaker's assumed class view, so "take the cart round by the north road — on foot the pass is quicker" is mechanically sayable.
- **Tracking is class inference.** Backward diffusion conditioned by class: cart ruts imply an edge-bound process; a trail crossing the river away from fords narrows the class to swimmer or flier. Class hypothesis is the first thing tracking resolves.
- **Ecology and traffic share one table** (§5): a species = habitat + diet + mobility class, all curated.

The class set is closed (first values: foot, mounted, cart, hoofed-herd, predator, fish, bird — plus monster variants via chimera). New classes are schema-level additions requiring the full table (A1's "curated or conservative" invariant).

---

## 4. Ecology

**Requirement (user):** many critters, biome-correct, ecologically correct. The architecture's answer: populations are counters and fields; individuals are samples.

**Species library: curated, never LLM-invented.** LLM wildlife generation converges to charismatic megafauna (wolves and eagles; never the voles that constitute an ecology) — the naming problem (A1 §8, P5) in faunal form. So: a curated species library, parameterized (size, diet, social unit, activity pattern, habitat requirements, wariness, mobility class), organized into **biome ecology packs** — species tables with abundance weights encoding the pyramid: per wolf, dozens of deer, hundreds of rodents. Biome-correctness is structural: a patch decodes fauna from its biome, suitability modulated by its own terrain z (water, elevation, vegetation).

**Populations: patch-resident counters with food-web coupling.** Per patch, per species: a counter. The web is a small directed graph per biome; the enforced rule is **ratio sanity** — predator biomass bounded by prey biomass, all bounded by habitat carrying capacity — checked at commit time, no ODE integration. Regime events (harsh winter, disease, overhunting) commit as anchors. Player consequence is mechanical where touched: hunting decrements; overhunting crashes prey, then predators *with a lag*; the gossip network carries "game's gone scarce in the western woods" — ecology audible in the tavern before it is visible in the field.

**Herds: mobile densities on schedules.** The aggregate that moves is the herd/pack/flock — a few GMM densities per patch. **Migration is a K2 Schedule:** seasonal periodic attractors (summer/winter range), cyclostationary fixed point, a century of migration in O(segments-per-period). Herds cross patches through the same permeability machinery as everything else; shared fords are where herds, travelers, and ambush predators coincide.

**Individuals: samples at the render boundary.** A distant deer sprite conveys class and activity (graze morning, water at dusk — one more schedule). Kill it: counter decrements. Examine it: species parameters. Nothing ledgered. Promotion is rare and special: the white stag, the man-eater — an animal that gets named accrues promises and graduates into the entity machinery via the chimera path (A1 §7). "A wolf pack gone bold in the hills" is a rumor-constrained latent obligation, placed in an unrefined open set, discharged by hunting.

**Wired interactions:** predators as encounter hazards conditioned on density × party strength (same shape as item discovery, §6); livestock as settlement counters predators decrement (events → gossip → shepherd-vs-hunter feuds); disease as counter events coupling into the NPC mortality hazard (A1 §9.4).

**Excluded:** individual-level simulation of the mass; LLM species invention; trophic dynamics beyond ratio rules + regime events (a wolf counter of 3.7 is the uncanny-numbers failure).

---

## 5. Items

Items are the stress test of the ontology: the one thing routinely crossing every boundary (render distance, ownership, death, skipped centuries).

### 5.1 The individuation threshold

Bulk is counters; identity is entities (engine spec §2.1). Grain, ore, arrows, coin: counters — no identity, no ledger. An object becomes an *item* when identity carries gameplay: it can be named, gifted, stolen, forged, sworn over, mourned. The threshold is a game-type dial; the rule — **nothing gets an identity until identity carries gameplay** — is invariant.

### 5.2 Tiers

- **Sampled** — merchant stock, bandit swords: drawn at render from curated item types (parametric z: material, quality, maker-culture, age), culled freely.
- **Promoted** — anything taken into inventory or named in a promise. **The inventory exception:** promoted items travel with their bearer across chunk exits precisely because they are ledgered. Promotion captures current derived state (A1 §10). Promotion is gated harder than entity promotion — *acquisition or promise-naming*, not mere contact; else every shop transaction ledgerizes the stock.
- **Latent** — dropped, buried, lost, loot-in-a-ruin: z + location promise, deterministically resurfaced. Treasure in an unsummoned feature decodes from the feature latent (P2).
- **Legendary** — the chimera analog for objects: a maximally inclusive template (material, form, powers, curse, maker) whose knobs are set by *rumor* (utterance constraints: "a blade buried with the old king"). Graduation applies: a sampled sword that accrues story is promoted in place and can climb to legendary.

### 5.3 Provenance is the identity

An item's promise history — maker, transfers, oaths, blood — *is* the item; each transfer a cheap promise record; the chain is its wiki spine. Payoffs: (a) **items outlive people** — grave goods, inheritance, the family mark on the ruined mill; for an immortal protagonist the inventory is autobiography; a dragon's hoard is a museum of discharged promises. (b) **Detective gameplay** — stolen goods carry provenance; "where did you get this" is a query; item references travel gossip corpus-anchored like names (A1 §8). (c) **Forgery is structured** — a fake provenance is a trust<0 promise chain, countered by appraisal and maker's-mark registries.

**Decay classes apply to objects.** Perishables are counters (food rots as a rate). Durables are permanent predicates. *Condition* (sharp, strung, intact) is ephemeral — decaying to prior, so "my father's axe" is findable after thirty years but its state is a sample.

### 5.4 Two canonical rulings

**Kill, loot, leave.** The kill commits at the victim's fidelity (named NPC: full commit; anonymous bandit: coarse, "a bandit died here" — combat alone does not promote, else every mook costs ledger forever). Loot splits: *ledgered* items demote to latent with `located(item, corpse_site)` (ephemeral; decays to prior; over long Δt backfill may commit scavenging, the scavenger origin-sampled per nobody-comes-from-nowhere); *sampled* inventory was never committed and culls with the chunk — the player perceived class ("a sword"), not identity (A1 §10.4). The corpse demotes; over time, archaeology. **Uncommitted loot evaporates with the render, legally.**

**Drop legendary, leave.** The drop is a measurement (`located(item, X)`, hard, as-of-t). The item is never cullable and **anchors its own heartbeat** — promise density follows the object. **Discovery is a hazard process**: traffic flow on the segment × concealment × item salience, sampled deterministically over Δt. Return soon: there. Return in a year: the item has had a *history* — finder origin-sampled, "found on the north road" appended to its chain, and the handoff is gossip-worthy, so K6 telegraphs it; the likely player experience is hearing a rumor about *your* sword two towns later. You did not lose an item; you planted a quest. Corollary: safe storage requires legible counters to obscurity — caches, vaults, promise-bearing guardians (discovery hazard ≈ 0) — or the mechanic reads as the world stealing. Telegraphing applies to object permanence.

### 5.5 Excluded

Per-item physics (items move as bearer state or location promises); durability numbers except where mechanically queryable (a sword that can break mid-fight earns the counter; a chair does not); LLM-invented item semantics (stats compile to the core ontology or the item is cosmetic-only — the A1 §5 tile rule).

---

## 6. Terrain change

Filtration forbids rewiring *generation* (§1.1); terrain change is not generation but **events**, classified by what they touch:

1. **In-cell parameter change — the default, always legal.** Same cell, new decoration. Wildfire is the showcase: forest patch → burnt patch (new OU field, new ecology pack, fuel counter consumed, regrowth as counter dynamics). Spread is a diffusing process on the complex — percolating across boundaries at a fire-permeability ε (high across open forest, low across rivers): the same leak machinery as goats and rumors. Most terrain change is tier 1: fire, flood, deforestation, seasonal shifts.
2. **Subdivision — legal in unobserved interior; event-committed in observed regions.** New road, new structure: refinement. In observed regions it is construction, passing causal reachability (a road after a year: legal; overnight: rejected).
3. **Rewiring — rare, event-committed, validated, telegraphed, fate-budget priced.** New river course, collapsed bridge, meteor crater. Allowed (engine spec §3.6 already sanctions erosion, disaster, construction) with diegetic provenance and telegraphing; the meteor is the most expensive entry in the event catalog and had better be prophesied (§4.6: announced is a mechanic, silent is a rail).

**Invariant: changes are commits, never edits.** The ledger records topology versions; the complex at time t is reconstructible; backfill can ask "what did this look like then." History only accumulates — even the apocalypse is additive.

---

## 7. Sublevels

Discrete **z-sheets**: the world is an interior-disjoint union of 2-D complexes (surface, cave-1, cave-2, sky-island…), each an ordinary complex, plus **vertical edges** connecting nodes across sheets (cave mouth, stair, shaft, flight route). No continuous z — the DF lesson; discrete levels keep everything analytic.

- **Mobility classes filter vertical edges.** Birds cross flight-edges (floating islands are in their subgraph); carts never do; swimmers use water-shafts. Floating islands are naturally isolated — disconnected components for pedestrians — so a people of the sky islands is frontier-by-topology, no special casing.
- **Caves are sparse complexes** — mostly edge-graph with few patches. Cheap, and dark: observation bandwidth in unlit caves ≈ 0, so cave interiors are natural latent space (A1 §10.4); the bandit fort in the caves stays uncommitted longer, legally.
- **Gossip and traffic flow through vertical edges** with the same trust decay and flow rates; the rumor of the under-city climbs the mine shaft like any other hop.
- **Vertical edges are the fragile structure.** Sublevel terrain change is mostly rewiring vertical connectivity: the tunnel collapse severs an edge; the meteor's crater *creates* one (surface sheet to cave sheet — the meteor literally opens a dungeon). Rule: within a sheet, the §6 tiers apply; **between sheets, everything is a vertical-edge event, always tier 3.**
- **Reconciliation rule:** vertical-edge changes must be checked against promises on *both* sheets. Collapsing the only tunnel while a promise says "the refugees flee below by winter" is a promise collision and must be authored as one (someone engineered the collapse), never an unexamined hazard roll.

---

## 8. Ontology additions

| Exists | Form | Mutated by |
|---|---|---|
| Topological complex | committed cells + incidence, versioned | L0/L1 commit, subdivision, tier-3 events |
| Mobility class table | curated views + parameter tables | authoring only |
| Species library / biome packs | curated templates, abundance weights | authoring only |
| Population counters (fauna) | per patch per species, ratio-constrained | hazard/regime events, hunting |
| Herd densities | GMM + seasonal Schedules | evolve, leak/absorb |
| Item provenance chains | promise records per transfer | acquisition, gift, theft, discovery |
| Vertical edge set | cross-sheet node pairs | tier-3 events only |

| Does **not** exist | Why |
|---|---|
| Individual simulation of faunal mass | counters + samples; render individuates on approach only |
| LLM-invented species / locomotion parameters | P4/P5; curated libraries |
| Zero-permeability boundaries (except class-relative, e.g. fish/land) | "always somewhat leaky, even if minimally" (user requirement) |
| Item physics simulation | bearer state or location promises only |
| Continuous z | discrete sheets; analytics over geometry |
| Retroactive topology edits | commits, never edits |

---

## 9. Invariants (additions)

10. **Refinement subdivides; only events rewire.** Filtration on the complex, plus the three-tier event rule.
11. **ε > 0 everywhere a class may cross.** No perfectly sealed anything; seals are ε ≈ 0, never 0.
12. **Everything mobile has exactly one mobility class**; all movement is on that class's filtered view.
13. **Ratio sanity:** predator biomass ≤ prey biomass ≤ habitat capacity, checked at every population commit.
14. **Identity threshold:** bulk stays counter; nothing is an item until identity carries gameplay.
15. **Ledgered objects are never culled**; they demote, persist, and accrue provenance. Uncommitted samples evaporate freely.
16. **Topology is versioned:** the complex at any t is reconstructible from the ledger.
17. **Vertical-edge changes reconcile both sheets' promise sets before committing.**

---

## 10. Failure-mode register additions

| Mode | Severity | Handling |
|---|---|---|
| Mixture explosion in off-graph diffusion | ◐ | K2b merge policy: component cap + moment-matching merges (§2.2) |
| Euclidean self-proximity on switchbacks corrupting leak/absorb placement | ◐ | nearest-segment rule; self-intersection requires a node (§2.1) |
| Topological defects (dangling edge, isolated patch, node-less crossing) | ● | L0 commit-time audit (§1.2) |
| Shop-transaction ledger bloat | ◐ | item promotion gated on acquisition/promise-naming, not contact (§5.2) |
| "The world stole my stuff" — unpriced discovery hazard | ◐ | storage counters legible; guardian promises drop hazard ≈ 0 (§5.4) |
| Charismatic-megafauna bias in any LLM-touched fauna text | ○ | abundance anchored to curated pack weights; LLM narrates, never composes (§4) |
| Unexamined vertical-edge collapse breaking cross-sheet promises | ● | both-sheets reconciliation rule (§7) |
| Untelegraphed tier-3 terrain events reading as rails | ◐ | telegraphing + fate-budget pricing (§6) |

---

## 11. Amendments stated (not applied)

To A1: §3 gains the complex as its formal substrate (§1 here); §10.5's trickle gains edge-flow derivation and mobility classes; §12's route validation becomes class-aware; the failure register merges §10 above. To the engine spec: §3.6's "sanctioned diegetic change" gains the three-tier event taxonomy (§6 here). To the lab spec, new kernel work:

- **K2b — merge policy** for split-strategy GMMs (component cap, moment-matched merges, mass-preserving).
- **K8 — route dynamics**: edge first-passage (inverse-Gaussian), bridge sampler, competing leak hazards, node flow rates.
- **K9 — complex**: the topological data structure, subdivision/refinement, commit-time defect audit, versioning.
- **C6 — ecology counters**: biome packs, ratio-sanity validation, migration schedules (stacks on K2, K4).
- **C7 — item ledger**: promotion gates, provenance chains, discovery hazard (stacks on K5).

---

## 12. Open questions

1. **Merge-policy parameters** (K2b): component cap and merge threshold; accuracy-vs-growth trade measured against the K2 reference harness.
2. **First-passage + leakage numerics:** competing-hazard sampling (IG vs. exponential) needs exactness tests; discretization of λ per unit distance vs. per unit time.
3. **Mobility class count:** seven proposed; the table's per-terrain parameterization is a content task with a completeness audit.
4. **Ecology counter granularity:** per-species-per-patch vs. guild-level aggregation for large maps; ratio-sanity tolerance bands.
5. **Item promotion UX boundary:** which player actions count as "examination" (and thus promotion) — inspect verb, pick-up, equip? Affects ledger growth rate directly.
6. **Sheet count and naming:** how many z-sheets the reference game needs (surface + one cave level + one sky level?); sheet-scoped vs. global counters.
