# M1 — axis registry interface (FROZEN keystone)

Implements integration contract **C1** from
`docs/spec-notes/2026-07-27-k13-v2-integration-contract.md`. This is the
schema every other module signs: M5's sampler dispatches on `mutation_kind`,
M6 fires on `coupling_triggers`, M8 orders by `salience`, M12 fills template
slots by `grammar_role`. **New per-axis data is added to `AxisSpec` here,
once — never per module.**

## `AxisSpec` (`registry.py`)

One record per axis (B1 knob or flat vocabulary axis):

| field | type | meaning |
|---|---|---|
| `name` | str | axis id |
| `block` | Block | morphometrics / patternation / niche / diet / life_history / behavior / ecosystem / sex_age_season |
| `tier` | Tier | **invariant** (plan topology) / **steady** (proportions) / **labile** (ears, tail, color) |
| `value_type` | ValueType | scalar / int / enum / bool |
| `mutation_kind` | MutationKind | gaussian / log_gaussian / enum_redraw / ratio / none — M5 dispatches on this |
| `sigma` | float | vary-by-default σ (relative for log_gaussian) |
| `states` | [str] | required for enum_redraw |
| `bounds` | (lo, hi) | leaky; scalar/int |
| `clade_steady` | bool | blacklist; forces mutation=none |
| `plan_scope` | [plan_id] \| "all" | which plans the axis applies to |
| `consumers` | {stress,drift,runaway,id,name,tell,pop,draw} | rent payers; ≥1 required |
| `salience` | float ≥0 | M8 epithet weight; M12 salient-part pick |
| `grammar_role` | GrammarRole | size/covering/grade/diet/part/none — M12 template slot |
| `coupling_triggers` | [coupling_id] | M6: movement fires these |
| `unit` | Unit | dimensionless / mass (exactly one mass axis registry-wide) |
| `temporal_modifier` | TemporalModifier | ≤1 of none/juvenile_only/seasonal/age_ramped/breeding_male (B1 §14) |
| `sex_linked` | bool | B1 §14 orthogonal flag |

`AxisSpec.mutable` = not clade_steady, not invariant, mutation ≠ none.

## Validation rules (`AxisSpec.validate` + `Registry.validate`)

- ≥1 consumer; consumers from the valid set.
- **invariant ⇒ mutation=none** (change it and you changed the plan).
- **clade_steady ⇒ mutation=none** (blacklist).
- **freeze-bug fix:** a mutable gaussian/log_gaussian/ratio axis must have
  `sigma > 0`; a frozen non-steady axis is an error.
- enum_redraw ⇒ non-empty `states`; enum value_type ⇒ mutation enum_redraw/none.
- scalar/int ⇒ bounds with lo<hi; log_gaussian ⇒ strictly positive.
- `plan_scope` = "all" or non-empty, and must reference loaded plans.
- **exactly one `unit=mass` axis** (B1 v0.3 size convention).
- `coupling_triggers` resolve against a provided coupling-id set (M6).

## `Registry`

`from_toml(axis_defs, plan_defs, coupling_ids)` / `load(path)` — builds and
validates, raising `RegistryError` on any violation. Queries: `axis(name)`,
`applicable_axes(plan)`, `mass_axis()`, `salience_order(plan)`,
`grammar_index()`, `plan_permissions(plan)` (the M0 `rebind` permission
table). `PlanSpec` carries a plan's medium, slots (string enums), and
generic→realization permission table.

## Axis TOML format (authored by M2)

```toml
[axis.body_mass]
block = "morphometrics"; tier = "steady"; value_type = "scalar"
mutation = "log_gaussian"; sigma = 0.3; bounds = [0.001, 1e5]
unit = "mass"; plan_scope = "all"
consumers = ["stress", "pop", "name"]; salience = 0.9; grammar_role = "size"

[axis.foot_posture]
block = "morphometrics"; tier = "steady"; value_type = "enum"
mutation = "enum_redraw"; states = ["plantigrade","digitigrade","unguligrade"]
plan_scope = ["tetrapod"]; consumers = ["draw","stress","tell","name"]
salience = 0.5; grammar_role = "grade"
```

## Tests (`test_m1.py`)

Each validation rule has a positive and a negative (planted-violation) case;
the mass-axis lint (zero/two mass axes fail); plan_scope filtering;
salience_order/grammar_index; TOML loader round-trip; rebind integration via
`plan_permissions`; K1-only source audit.

## Reserved: `effects` (rounds hook, user 2026-07-28)

`AxisSpec.effects` — optional functional effect vector
(`{thermal: 0.8, camouflage: -0.6, warning: 0.9}`), the multidimensional
generalization of `adapt_weight`. Parsed and shape-validated, consumed by
NOTHING in v2. The rounds layer computes stress against it; see the rounds
spec-note §7. Knob audit for effect semantics is owed (user caveat: the
authored knobs have not been checked for this yet).
