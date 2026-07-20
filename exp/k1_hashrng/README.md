# K1 — hashrng

## Goal

Deterministic content-addressed sampling: the foundation stone every other
lab library seeds from. `sample(world_seed, entity_id, clock,
context_digest) -> float in [0,1)` plus stream variants. Same inputs →
identical outputs across processes and machines; neighboring
entities/clocks → statistically independent streams.

## API

Library home: `kernel.hashrng` (promoted 2026-07-19 per lab spec §6).

- `stream_key(world_seed, entity_id, context_digest="") -> bytes` — 256-bit
  stream identity (BLAKE2b, RFC 7693; explicit little-endian packing, so
  results are platform- and version-independent).
- `sample(world_seed, entity_id, clock, context_digest="") -> float` —
  one-shot uniform in [0, 1), the spec's canonical signature.
- `Stream(world_seed, entity_id, context_digest="")` — random-access stream
  keyed by `(clock, index)`; no sequential state, so drawing at clock 10⁹
  costs the same as at clock 0 (this is what makes analytic time-skip cheap
  downstream). Methods: `u64`, `uniform`, `uniforms`, `bernoulli(p)`,
  `randrange(n)` (multiply-shift, no modulo bias), `normal()` (Box–Muller),
  `digest(start, stop)` (stream identity for rerun checks).

## Demo

`uv run python -m exp.k1_hashrng demo --seed 1 [--json]`

Dumps a year (365 daily draws) for two entities with stream digests,
re-derives the streams from scratch to prove bit-identical rerun, and runs
a χ² uniformity check over 100k draws from 200 fresh streams. Exit code 0
iff all checks pass.

## Verdict

**works** (2026-07-19). Test suite: reproducibility (same inputs → same
output, random access = sequential, no collisions over 10k entities),
uniformity (χ² p ∈ (0.001, 0.999), single-stream and across-streams),
independence (|Pearson r| < 0.02 for neighboring clocks, neighboring
entities, and same-clock-across-entities), derived distributions
(bernoulli rate, randrange χ², normal moments). No LLM, no dependencies
beyond the stdlib.

## Spec-notes

None owed per lab spec §2. Observations for downstream libraries:

- Keyed-hash counter mode is fast enough that per-draw cost is
  noise (100k draws < 1s); no need for buffered batching in K2/K3.
- `context_digest` is a plain string mixed into key derivation — callers
  (K3 collapse, C2 backfill) should pass a canonical digest of their own
  context records rather than raw text, to keep keys stable.
- `normal()` consumes draw indices in pairs (2i, 2i+1); code mixing
  `uniform(clock, i)` and `normal(clock, i)` at the same clock should use
  disjoint index ranges (e.g. normals in high indices) to avoid
  correlated reuse of the same underlying draws.
