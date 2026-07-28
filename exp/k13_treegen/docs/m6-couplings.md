# M6 — couplings (the rules that must measurably fire)

Interface doc. v1's tradeoff computed the identity — a coupling that never
changes output is worse than none. So every M6 rule is a **data record with
an existence proof**: a must-fire case where the rule measurably changes
evolve()'s output versus a no-coupling control, and a must-not-fire case
where it stays silent.

## Rule record (content/couplings.toml — data, not code)

```toml
[[rule]]
id = "size_fecundity"
kind = "tradeoff"          # gate | tradeoff | bundle
status = "active"          # active | dormant
scope = ["all"]            # plan scope
source = "B1 §15 #2 (SEMI-UNIVERSAL)"
# kind-specific fields below
```

Kinds (anticorrelate is a negative-strength tradeoff — one mechanism, the
sign does it):

- **gate** — `trigger = { axis, state }`; while the child's trigger axis
  holds the state, `targets` are pulled GATE_PULL toward their lower bound
  per evolve step. (flight_style is the gate, B1 §3.) Two more trigger
  forms: `{ condition = "stressed" }` (pull scales CONTINUOUSLY with
  Condition.stress — no step threshold, user ruling: processes are leaky,
  only commitments are categorical)
  and **`{ env = name, above|below = x, toward = min|max }` — the rounds
  hook**: `Condition.env` carries named world variables (temperature,
  moisture, salinity, ley proximity for ledger W7); the blind backbone
  passes an empty env and the gate stays silent, the rounds populate it.
  This machinery is REUSED for world evolve — the blind tree-build is the
  first caller with a benign default Condition, not a separate engine.
- **tradeoff** — `a`, `b`, `strength` (signed, in σ units): the two axes
  are LINKED, bidirectionally (user ruling 2026-07-28: knobs and results
  are equal citizens — a coupling co-varies two axes, it does not make
  one cause the other). A Δ in either induces `strength × Δ` in the
  other; both transfers are computed from the un-adjusted deltas so
  there is no same-step feedback. Negative strength = anticorrelate.
- **bundle** — `trigger = { axis, direction, min_z }`; when the parent's
  step in axis exceeds min_z in direction, every effect fires as a
  correlated set (enums forced to a state, scalars shifted by z). Not
  independent draws — one event, one package.

**Dormant** rules are enumerated with a reason (missing axes / deferred
mechanism) and a test asserting they are recorded-but-unbound. The 3
rejected B1 §15 candidates (expensive-tissue, armor↔speed, venom cost) are
confirmed ABSENT by test.

## B1 §15 enumeration → v2 status

| # | rule | status | binding |
|---|---|---|---|
| 1 | domestication package | active bundle | wariness↓ ⇒ ear_posture→pendant, tail_carriage→curled, snout_ratio↓, motif→spotted |
| 2 | offspring size↔number | active tradeoff | body_mass × fecundity, −0.3σ |
| 3 | fast–slow life history | active tradeoff | lifespan_yr × fecundity, −0.4σ |
| 4 | island flightlessness | active gate | flight_style==flightless ⇒ wing knobs → lower bound |
| 5 | cancer suppression | dormant | no suppression/regeneration axes in v2 |
| 6 | sensory modality tradeoff | dormant | no modality axes in v2 (cave bundle lands with them) |
| 7 | melanism↔aggression | dormant | enum↔scalar coupling deferred |
| 8 | ornament cost | active gate | stress ⇒ adapt_weight==0 axes → 0 |
| — | Allen's rule | active tradeoff | temp_opt_c × ear_size_ratio, +0.4σ |
| — | Bergmann's rule | active tradeoff | temp_opt_c × body_mass, −0.3σ |
| — | Gloger's rule | dormant | pigmentation is enum (same deferral as #7) |

## Scope/precedence ruling (user, 2026-07-28)

Climate never touches morphology directly. The world stresses the NICHE
axes (`temp_opt_c`/`moisture_opt` mismatch, via Condition/descent);
morphology follows through symmetric couplings (Allen/Bergmann), and the
reverse direction is equally real — a furrier animal BECOMES cold-suited.
The env-gate hook is reserved for EXOGENOUS effects (ley/magic, W7), not
climate. Selection is painted as directed force + compressed time, never
as simulated culling.

## Per-world weak bindings

`weak_bindings(seed, pack)` — K1-seeded pick of WEAK_BIND_COUNT scalar
axis pairs (same plan scope, both mutable, distinct) with coefficient
±[0.1, 0.3]. Flavor texture per B1 §15's closing note: clade-idiosyncratic,
never learned, different across seeds (tested), deterministic per seed
(tested). Applied like tradeoffs during evolve.

## Integration

`evolve(..., couplings=rules)` runs the coupling pass after per-axis
mutation, before the Node is committed. Effects are recorded in
`edge_delta[axis]["coupling"]` — the audit trail distinguishes forced
movement from force movement.
