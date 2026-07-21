# C2 — backfill pipeline

## Goal

The lazy-history pipeline. Given a fixture village (20 NPCs, 3 counters, 6
promises, Δt = one season), the pipeline:

1. evaluates counter anchors (K4),
2. samples eventfulness — how many notable events (C1),
3. calls the LLM (L1 T1-flash) to generate a `SeasonChronicle`,
4. mechanically validates the output (count, no resurrection, counter
   agreement, promise discharge),
5. **on acceptance,** commits the chronicle as wiki facts (K7) and
   discharges/expires promises (K5).

When the LLM output fails validation, the pipeline feeds violations back as
a retry warning. Acceptance requires a valid chronicle within one retry.

## API

Library home: `capability.backfill` (promoted 2026-07-20 per lab spec §6);
`build_village` remains in `exp.c2_backfill.fixtures`.

| function | module | signature |
|---|---|---|
| `backfill()` | `capability.backfill.pipeline` | `(village: Village, t0: float, t1: float, client: LLMClient, stream: Stream, *, max_retries: int = 1) -> BackfillResult` |
| `validate_chronicle()` | `capability.backfill.validate` | `(chronicle: SeasonChronicle, k: int, dead_slugs: set[str], counter_anchors: dict, due_promises: list[Promise]) -> list[str]` |
| `commit_chronicle()` | `capability.backfill.commit` | `(village: Village, chronicle: SeasonChronicle, t0: float, t1: float, due_promises: list[Promise], counter_anchors: dict) -> tuple[list[str], str]` |
| `build_village()` | `exp.c2_backfill.fixtures` | `(seed: int) -> Village` |
| `build_backfill_prompt()` | `capability.backfill.pipeline` | `(village, counter_anchors, due_promises, active_promises, k, dt) -> str` |

Key types from `exp.c2_backfill.schema`: `BackfillEvent`, `CounterNote`,
`SeasonChronicle`, `BackfillResult`.

## Demo

```
uv run python -m exp.c2_backfill demo --seed 1          # live, needs DEEPSEEK_API_KEY
uv run python -m exp.c2_backfill demo --seed 1 --replay # cassette-offline
uv run python -m exp.c2_backfill demo --seed 1 --json   # machine-readable output
```

Four stages:

1. **The season (seed 1):** runs the full pipeline for a single seed, prints
   the committed wiki facts, the chronicle text, counter moves, and cost.
2. **Validator traps:** feeds the validator two deliberately invalid
   chronicles — a resurrection (dead NPC in an event) and a counter
   disagreement (wrong direction) — and confirms both are caught without
   calling the LLM.
3. **Acceptance:** runs 50 seeded villages (seeds 1–50) and reports
   acceptance rate, mean attempts, and most common violation classes.
4. **Archaeological legibility:** reports provenance coverage (every wiki
   fact traces to a named source), counter-explanation coverage (every
   non-flat counter move has a `CounterNote`), and contradiction count
   (duplicate fact IDs).

## Verdict

**50/50 seeds accepted (100%) within one retry.** All 6 demo checks PASS:

| check | result |
|---|---|
| `validator_catches_resurrection` | PASS |
| `validator_catches_counter` | PASS |
| `acceptance_ge_80` | PASS (1.000) |
| `chekhov_discharged` | PASS |
| `no_dead_in_commits` | PASS |
| `legibility` | PASS |

Cost (50 seeds, T1-flash, recorded cassette):
- tokens: 75,650 in / 70,400 cached / 16,126 out
- **$0.0054** total

Tests: 18/18 pass (API-free, stub transport + tmp cassette). Full regression:
217/217 pass. Replay is byte-identical across runs.

## Spec-notes

→ `docs/spec-notes/2026-07-20-c2-archaeological-legibility.md` — defines
"archaeologically legible" as three checkable properties and reports
measurements from the 50-seed run; answers Q-legible.
