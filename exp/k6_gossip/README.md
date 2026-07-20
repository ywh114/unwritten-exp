# K6 — gossip_transport

## Goal

Mechanical rumor diffusion over a contact graph — the ONLY channel from
the unobserved world (design spec §5.3).  Rumors are structured records
that degrade per hop (field drops, mutations, magnitude drift) while
trust decays exponentially.  Traceability works backwards along trust
gradients, WITHOUT storing who-told-whom.  LLM *delivery* of rumors is
explicitly out of scope (that's C3's job).

## API

Library home: `exp.k6_gossip` (not yet promoted; lab spec §6 gate is the
reviewer's call).

- **`Rumor(subject, event, location, day, magnitude)`** — immutable
  structured event record.  `event_class` property canonicalises
  mutation pairs so they compete for the same belief slot.
- **`Belief(rumor, trust, heard_day)`** — a node's held version.
- **`perturb(rumor, stream, clock, idx_base, q_drop, q_mut, sigma_drift)`**
  — one hop of mechanical degradation.
- **`GossipParams(p_tell, tau, q_drop, q_mut, sigma_drift)`** —
  tunable diffusion constants.
- **`GossipNetwork(graph, params, world_seed)`** —
  - `inject(node, rumor, trust)` — seed a ground-truth belief.
  - `propagate(days, clock0=0)` — forward-simulate simultaneous daily tells.
  - `belief(node)` / `believers()` — query current state.
  - `trace_source(node)` — walk the trust gradient to predict the origin
    (no stored teller chain).
  - `localization_rate(true_source)` — fraction of believers whose
    predicted source is within 2 graph hops of truth.

## Demo

`uv run python -m exp.k6_gossip demo --seed 1 [--json]`

Injects "the mill burned @ riverside mill, magnitude 1.0" at node 0 of a
50-NPC Watts–Strogatz contact graph (seeded via K1), propagates 7 days,
then prints:

1. **Distortion-vs-distance curve**: believers, mean trust, mean dropped
   fields per rumor, mean |magnitude − 1.0|, bucketed by graph distance
   from source (0, 1, 2, 3+).
2. **Sample beliefs** at increasing distances (shows mutation "collapsed"
   and drifted magnitudes).
3. **Traceback**: localization_rate; a few example traces.
4. **A/B comparison**: same graph with τ halved; trust-by-bucket side by
   side.

Checks: believers > 30, trust non-increasing across distance, loc_rate
≥ 0.70, halved-τ run has strictly lower trust at distance ≥ 2.

## Verdict

**works** (2026-07-19).  15 tests: determinism (same seed → identical,
seed+1 → differs), perturbation laws (drop-all, mutate, verbatim,
magnitude clamp [0.1, 3.0] under σ=2 × 1000 chains), exact trust on
path graph (τ**d), simultaneity (1 edge/day on path with p_tell=1),
update rule (higher trust wins, lower trust tell doesn't replace,
contradictory mutation replaces), traceability (≥ 70% over 20 fixture
seeds, ≥ 90% on noiseless balanced tree), tunability (τ halved → lower
trust at distance ≥ 2; σ_drift doubled → larger magnitude error).

## Spec-notes

### Default constants (calibration)

These defaults are the first measured calibration of the design spec
§5.3 parameters, determined from the 50-NPC fixture at seed 1 after 7
propagation days:

| parameter | default | effect at distance 2 after 7 days |
|-----------|---------|-----------------------------------|
| `p_tell`  | 0.5     | ~50 believers out of 50 nodes     |
| `tau`     | 0.85    | trust decays to ~0.72 at dist 2, ~0.57 at dist 3+ |
| `q_drop`  | 0.10    | ~0.35 mean dropped details at dist 3+ |
| `q_mut`   | 0.05    | ~1 mutated belief among dist-1 nodes |
| `sigma_drift` | 0.10 | ~0.20 mean |mag−1| at dist 3+ |

The distortion-vs-distance curves are smooth (mean trust strictly
decreasing across buckets, mean dropped fields and magnitude error
strictly increasing).  Halving `tau` compresses the trust curve as
expected; doubling `sigma_drift` widens magnitude errors as expected.
The tunability is confirmed.

### Out of scope (stated for later experimenters)

LLM phrasing/delivery of rumors (→ C3 `performance`), querier-aware
reframing, wiki fact-checking, rumor injection by orchestrator or
player (`soft_orchestrator` provenance in K5).  This library moves
structured records; it never writes prose.
