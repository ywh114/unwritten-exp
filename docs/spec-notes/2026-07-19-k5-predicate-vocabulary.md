# 2026-07-19 — K5 verdict: the minimal predicate vocabulary

**Amends:** design spec (promise formalism); answers the open question
attached to lab spec §2 K5.
**Source:** `kernel/promise_ledger/predicates.py`; the 20-fact test in
`exp/k5_promise_ledger/test_promise_ledger.py`.

## Question

The promise ledger unifies all narrative constraints — canon facts, NPC
speech acts, orchestrator intents — as predicates on the world. How many
predicate *kinds* are enough? Too few and the world flattens; too many
and the conflict checker becomes a theorem prover. The spec asks for the
*minimal* set covering ~20 canonical political facts.

## Answer: 10 kinds

| # | Kind        | Signature                      | Example facts                                     |
|---|-------------|--------------------------------|---------------------------------------------------|
| 1 | `OWNS`      | entity owns resource           | merchant owns granary; dragon owns hoard           |
| 2 | `CONTROLS`  | entity controls region         | baron controls fief; council controls free city    |
| 3 | `IS`        | entity has status (detail)     | king IS dead; prince IS heir; duke IS banished     |
| 4 | `FEALTY`    | vassal owes fealty to liege    | vassal fealty liege; knight fealty order           |
| 5 | `HOSTILE`   | faction hostile to another     | kingdom_a hostile kingdom_b                        |
| 6 | `ALLIED`    | faction allied to another      | elves allied humans                                |
| 7 | `LOCATED`   | entity located in region       | wizard located tower; army located pass            |
| 8 | `DISPUTED`  | region is disputed             | borderlands disputed; throne disputed              |
| 9 | `BOUND`     | entity bound by oath (detail)  | queen bound king [marriage]; clans bound [truce]   |
| 10| `HOLDS`     | entity holds title (detail)    | marshal holds army [commander]; abbot holds abbey  |

These 10 parameterised forms cover 20+ distinct canonical facts; the
`detail` qualifier on `IS`, `BOUND`, and `HOLDS` gives extensibility
without adding kinds (new statuses, oath types, and titles are strings).

### Why 10 and not fewer

Seven kinds require subject + object and are irreducible — no two describe
the same relation.  Three (`IS`, `BOUND`, `HOLDS`) carry a free `detail`
field covering statuses / oath-types / titles; combining them into one
kind would require the conflict checker to parse detail strings, which is
exactly the "becoming Prolog" danger the spec warns against.

### Why not more

Each additional kind adds potential conflict rules (the checker is
O(kinds²) in the worst case). The 10-kind set already covers the king's-
court scenario and the ~20 canonical facts; expanding it further should
only happen when a new kind enables a *mechanically new* conflict (not
just a narrative one).

## Design-rule settled

The predicate vocabulary is closed under this set. New predicates are
instantiated by setting `detail`, not by adding kinds. The orchestrator
(LLM) supplies the detail strings from its structured-output schema; the
ledger treats them as opaque tags except for a handful of reserved values
("dead", "banished") that trigger conflict rules.

## Recommendation for the engine spec

Adopt the 10-kind vocabulary and the `detail`-extensibility rule.
Document that `IS` with detail "dead" and "banished" are mechanically
significant (they trigger conflict rules); all other details are
narrative content, mechanically opaque.
