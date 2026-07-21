# RFC: Game Layer — World Shape, Verbs, and Horizon Decisions

**Status: Draft RFC v0.1 (2026-07-21) · Requests comment, not normative**
**Context:** Unwritten engine; sits above the engine spec and addenda A1/A2. These are *high-level game decisions* — deliberately far ahead of the build order. Nothing here unblocks a kernel; everything here pins dials the engine said were game-level. Where a decision touches engine machinery, the touchpoint is cited.
**Feeds:** future Addendum A3 (game-layer instantiation); the reference-game constants (A1 §18, open question 6).

---

## 1. World template: "the whole world," committed first

Worlds come in predefined template types (city district, dungeon, entire world). **Commit the entire-world template first** — it forces the hard subsystems (drainage, climate, frontier) that smaller templates then inherit for free.

Shape: **flat, rectangular, ocean margins, rim mountain barrier, then void** — literal void: fall off and die.

- The rim is a boundary plate margin all around (the plate pass justifies it); the ocean never drains; no water-cycle counter needed.
- The rim is *observable* — a destination, not an abstraction. Once observed, "nothing beyond" is committed and the exterior forecloses permanently (prime directive). The inexhaustible latent reserve therefore lives **down** (sublevels), not outward.
- Generation pipeline (parameterized, hash-seeded, each pass constraining the next — the pipeline is the filtration): **plates** (kinematic template plates: convergence → ranges, divergence → rift lakes) → **elevation** (plate-conditioned noise) → **hydrology** (flow accumulation → drainage network; rivers consistent by construction) → **climate** (T = f(latitude, altitude); P = f(distance-to-ocean, rain shadow)) → **biomes** (classifier over (T, P, seasonality) + neighbor-coherence smoothing; feeds the fauna RFC's clade affinities).
- **Water:** store terrain height h and water surface w per cell; depth is derived, (w − h)⁺. Standing water is equipotential per connected basin (ocean at global sea level; lakes at outlet-sill height). Equilibrium is never simulated toward — hydraulic timescales are far below gameplay Δt, so water is always *evaluated* at equilibrium. Floods/dam-breaks are events that re-equilibrate instantly at next observation.

## 2. Player verbs: move, act, wait

The entire player interface is three verbs; status management is near-zero.

- **Move** — advances the observation frontier. The measurement verb.
- **Act** — context interaction (talk, take, kill, give, swear). One verb; richness lives in resolution, not in menus. Promotes entities, commits events, authors promises.
- **Wait** — advances Δt. Uniquely dignified here: counters evaluate, heartbeats accumulate, rumors arrive, promises come due. Waiting near something Zeno-watches it; waiting far lets drift accumulate. For an immortal, attention — not time — is the scarce resource.

Status filter: a status counter exists only if the *world* must mechanically query it (interactivity rule applied to the protagonist). Health yes; gold yes; satiety no. Tired/cold/hungry live in the fiction — NPCs remark on them, inns exist — not in bars.

Corollary: MUD-first development stays honest. `go`, `do`, `wait` are the first three CLI commands (lab spec E00 lineage); the full game's player side already exists at the text interface.

## 3. Player identity: an elf

Immortal, Silmarillion in temper. Pins dials, adds no systems:

- Infinite lifespan — the longest-lived promise in the ledger (already load-bearing for the 100-year village and §4's ending).
- Temper as promise lifetime: elven oaths have the longest windows in the world; the graveyard ledger is the protagonist's interiority, and it is queryable.
- Elven senses, if granted, are **instruments, not passive acuity** (starlight sight, true-names) — passive observation bandwidth is priced in ledger growth (A1 §10.4), and passive elven acuity would silently pay that price everywhere.

## 4. The ending: the jump

**The only way to end the game is to jump off the rim.** For an immortal it is the only absorbing state; every other boundary is permeable or round-trippable.

- The jump is the final measurement: a world with no observer is never written again. The save freezes at the moment of the jump; everything past it stays permanently superposed. "Return to behind the computer" is diegetically exact — the player was the measurement apparatus.
- The epilogue is the ledger at time-of-jump: the final state of everything the player ever committed.
- The rim is a real place before it is an exit: rim pilgrims (life-goal promises, stock machinery), religions of the beyond, rumors of what jumpers saw — permanently unresolvable, since no one returns to collapse them; the game's one deliberately undecidable rumor.
- One diegetic confirmation beat at the edge ("the wind says nothing"); the jump is the only interaction that produces no commit — no one remains to bind.

## 5. Language as gossip structure

`knows_language(e, L)` is a durable predicate (player and NPCs alike). Consequences:

- Rumor crossing a language barrier takes an extra effective hop of perturbation and trust decay — translation is a retelling. Language communities become near-components of the gossip network; bilinguals are its cut vertices (translators, traders, border towns are mechanically special).
- Language keys the curated corpora (A1 §8): names, folk labels, and chatter shift audibly at borders.
- Dialects, if wanted: a small hand-authored language tree with clade-conditional variants — the fauna RFC's cladogram trick, one YAML file; mutual intelligibility decays with tree distance.
- The player's elvish is an interrogation instrument: listening in a half-known tongue yields the degraded channel, mechanically.

## 6. Void-creatures

Rare entities appearing near the rim, defined by *exemption* from the axioms: unkillable (outside the hazard model — not high HP, no mortality process), unintelligible to all but the player (no shared `knows_language` with anyone else), and **the world's only inward ε** — the rim boundary leaks inward, nowhere else.

- Player-only intelligibility makes the player the sole bridge node between the void and the rumor graph: their utterances reach NPCs only as the player's testimony — trust-tagged, unverifiable.
- Their speech binds nothing (speech-act firewall holds): when queried, "?" — or cryptic non-sequiturs. They seed only **trust-undecidable** claims: not lies (trust<0), but claims the network has no machinery to evaluate. A new epistemic register, cheap: one template with exemptions, one spawn rule, one dialogue policy.
- Deliberately unresolved: what they are, what they want. Possibly nothing. Possibly editorial commentary. Leave it.

## 7. Non-goals

- Status-management systems, crafting trees, skill sheets — the three-verb loop stands.
- Answering what the void-creatures are, or what jumpers see.
- Water-cycle simulation, tectonic simulation, circulation models — equilibrium and template passes only.
- Anything that adds a fourth verb.

## 8. Open questions

1. Does the jump delete, freeze, or archive the save — and can the ledger be *read* afterward (the graveyard as post-game)?
2. Rim pilgrimage: how do NPCs react to the player jumping (witnesses? a new religion seeded by the event)?
3. Void-creature spawn rate and whether they ever leave the rim's vicinity.
4. How many languages the first world needs (proposal: 3–5, one per major culture, dialects deferred).
5. Whether elven instruments (starlight sight) are starter kit or earned.

## 9. Failure modes to watch

- **Verb creep** — any proposed mechanic that needs a fourth verb is a smell; fold it into act/wait context or reject it.
- **Status creep** — bars accumulating "because RPGs have them"; apply the world-queries-it filter ruthlessly.
- **Rim trivialization** — fast travel to the rim cheapens the ending; the rim should cost a journey, always.
- **Void-creature overuse** — frequency above "rare" collapses the register into a mascot.
