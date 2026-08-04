"""Flora constraint rules (vocabulary §8.10): the legality gate.

Port of the settled k13 gate (``exp/k13_treegen/flora/constraints.py``)
for the K15 biosphere rewrite (ticket 0043; spec B9 §2).  Data-driven,
enforced at sampling time inside the same evolve edge — the gate pattern:
a trigger fires, the required axes snap into compliance, and the snap is
audited.  Never post-hoc deletion, never a hard cap: a constraint states
that one trait COMBINATION is not a thing (CAM without water storage, red
wind-pollinated flowers), so the offending dial is pulled to the
threshold, not deleted.

Rule semantics (constraints.toml):
    when = { axis = X, state = S | [S, ...] }   trigger: enum in state(s)
    when = { axis = X, above = f }              trigger: scalar above f
    when.plans = [plan, ...]      rule SCOPE: the rule fires only on
        these plans (spinescence_aridity is a land-plant rule)
    state_plans = [plan, ...]     trigger-state LEGALITY: the trigger
        state is only a thing on these plans — off-plan it snaps back
        to the parent's prior value (a lichen cannot redraw its way
        into buttress roots; the "aerial wolf" class)
    require_min  = { A = f }      scalar A pulled up to >= f
    require_max  = { A = f }      scalar A pulled down to <= f
    require_enum = { A = [states] }  enum A kept if legal, else first
        LEGAL candidate (palette-filtered for color axes — the bird-
        syndrome rule may not paint a moss red when the moss palette
        forbids it; no legal candidate -> the trigger itself snaps back)
    forbid_enum  = { A = [states] }  enum A kept if legal, else the
        parent's prior value (if legal), else the first non-forbidden
        state (palette-filtered the same way)

enforce() is idempotent: a second run over the same child is a no-op.
violations() re-checks the committed record (metrics gate — pinned
records are trusted at build time but still audited here).

Adaptations from k13 (B9 §2, §3):
- The audit trail is a RETURN VALUE, not an edge_delta write —
  SpeciesRecord carries no edge_delta by design (B9 §1).  enforce()
  returns one ``{rule_id: {axis: [old, new]}}`` entry per fired rule
  that actually snapped a dial — the exact content k13 stashed under
  ``edge_delta["constraint"][rule.id]``.
- violations() messages carry no node-path prefix (the k15 record has
  no path — path/rank are other layers' business).
- The k15-era trigger precompute (frozenset caches, ticket 0023) is
  left behind (B9 §3): Rule holds the authored tables only and the gate
  parses ``when`` per call.  Correctness and clarity only — this is
  not a hot path in the rewrite (AGENTS.md §6).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from exp.k15_biosphere.record import SpeciesRecord
from exp.k15_biosphere.registry import Registry

# enum axes whose snap candidates are palette-filtered (mirrors the
# sampler legality in k13 forces._legal_states).
PALETTE_AXES = ("flower_color",)

Snap = dict[str, list[object]]   # axis -> [old, new]: the dial and its move
Audit = list[dict[str, Snap]]    # enforce() result: [{rule_id: {axis: snap}}]


@dataclass(frozen=True)
class Rule:
    """One authored legality rule.  Frozen: rules are content, loaded
    once at pack build and shared read-only by every gate call."""

    id: str
    when: dict = field(default_factory=dict)
    state_plans: tuple = ()
    require_min: dict = field(default_factory=dict)
    require_max: dict = field(default_factory=dict)
    require_enum: dict = field(default_factory=dict)
    forbid_enum: dict = field(default_factory=dict)

    @classmethod
    def from_toml(cls, t: dict) -> "Rule":
        return cls(id=t["id"], when=dict(t.get("when", {})),
                   state_plans=tuple(t.get("state_plans", [])),
                   require_min=dict(t.get("require_min", {})),
                   require_max=dict(t.get("require_max", {})),
                   require_enum=dict(t.get("require_enum", {})),
                   forbid_enum=dict(t.get("forbid_enum", {})))


@dataclass
class ConstraintPack:
    """The gate's read surface: rules + the registry/palette lookups the
    snap machinery needs.

    The 0041 ContentPack deliberately does not carry rules or palettes
    (its loader scoped them to this ticket — a parallel ticket owns
    content.py); this small pack is the composition point.  enforce()/
    violations() duck-type on ``constraints``/``registry``/``palettes``,
    so a ContentPack that later grows those fields works unchanged.
    """

    registry: Registry
    constraints: list[Rule] = field(default_factory=list)
    palettes: dict[str, list[str]] = field(default_factory=dict)  # plan -> colors


def load_rules(path: str | Path) -> list[Rule]:
    """Load the ``[[rule]]`` tables of a constraints.toml, read IN PLACE
    from the k13 content dir (``exp/k13_treegen/content/flora/`` — content
    is shared data, never copied)."""
    data = tomllib.loads(Path(path).read_text())
    return [Rule.from_toml(t) for t in data.get("rule", [])]


def load_palettes(path: str | Path) -> dict[str, list[str]]:
    """Load palettes.toml's ``[palette.<plan>]`` color lists — the
    color-axis snap filter used by ``_candidates``."""
    tbl = tomllib.loads(Path(path).read_text()).get("palette", {})
    return {plan: list(t.get("colors", [])) for plan, t in tbl.items()}


def _when_states(when: dict) -> list[str]:
    """The trigger states of a ``when`` table as a list of strings
    (empty when the trigger is the scalar ``above`` form)."""
    states = when.get("state")
    if states is None:
        return []
    if isinstance(states, list):
        return [str(s) for s in states]
    return [str(states)]


def triggered(rule: Rule, axes: dict, plan: str | None = None) -> bool:
    """The when-table trigger gate: does *rule* fire on this record?"""
    scope = rule.when.get("plans")
    if scope is not None and plan is not None and plan not in scope:
        return False
    ax = rule.when.get("axis")
    if ax is None:
        return False
    v = axes.get(ax)
    if v is None:
        return False
    states = rule.when.get("state")
    if states is not None:
        if isinstance(states, list):
            return str(v) in states
        return str(v) == str(states)
    above = rule.when.get("above")
    if above is not None:
        return isinstance(v, (int, float)) and v > above
    return False


def _candidates(node_plan: str | None, pack: ConstraintPack, axis: str,
                states: list[str]) -> list[str]:
    """Snap candidates, palette-filtered for color axes."""
    if axis in PALETTE_AXES and node_plan:
        palette = pack.palettes.get(node_plan)
        if palette:
            states = [s for s in states if s in palette]
    return states


def _snap_back(rule: Rule, parent: SpeciesRecord | None,
               child: SpeciesRecord, pack: ConstraintPack,
               snaps: Snap) -> None:
    """Off-plan trigger state: revert the trigger axis to the parent's
    prior value (else the first registry state that differs)."""
    ax = rule.when["axis"]
    cur = child.axes.get(ax)
    prior = parent.axes.get(ax) if parent is not None else None
    bad = _when_states(rule.when)
    if prior is not None and str(prior) not in bad:
        child.axes[ax] = prior
        snaps[ax] = [cur, prior]
    else:
        spec = pack.registry.axes.get(ax)
        legal = [s for s in (spec.states if spec else []) if s not in bad]
        if legal:
            child.axes[ax] = legal[0]
            snaps[ax] = [cur, legal[0]]


def _require_errors(rule: Rule, axes: dict) -> list[str]:
    """Requirement breaches on a triggered record (no mutation)."""
    errs: list[str] = []
    for a, lo in rule.require_min.items():
        v = axes.get(a)
        if isinstance(v, (int, float)) and v < lo:
            errs.append(f"{rule.id}: {a} {v} < require_min {lo}")
    for a, hi in rule.require_max.items():
        v = axes.get(a)
        if isinstance(v, (int, float)) and v > hi:
            errs.append(f"{rule.id}: {a} {v} > require_max {hi}")
    for a, states in rule.require_enum.items():
        v = axes.get(a)
        if v is not None and str(v) not in states:
            errs.append(f"{rule.id}: {a} {v!r} not in {states}")
    for a, states in rule.forbid_enum.items():
        v = axes.get(a)
        if v is not None and str(v) in states:
            errs.append(f"{rule.id}: {a} {v!r} forbidden {states}")
    return errs


def violations(record: SpeciesRecord, pack: ConstraintPack) -> list[str]:
    """All constraint breaches on one committed record (metrics gate).

    No ``node.path`` prefix in the messages — the k15 record has no
    path by design.
    """
    errs: list[str] = []
    for rule in pack.constraints:
        if not triggered(rule, record.axes, record.plan):
            continue
        if rule.state_plans and record.plan not in rule.state_plans:
            errs.append(f"{rule.id}: trigger state illegal on plan "
                        f"{record.plan!r} (state_plans)")
            continue
        errs.extend(_require_errors(rule, record.axes))
    return errs


def enforce(parent: SpeciesRecord | None, child: SpeciesRecord,
            pack: ConstraintPack) -> Audit:
    """Snap the child's record into compliance for every triggered rule.

    Called per evolve edge, after the size envelope (legality is the
    final word).  The audit trail is the RETURN VALUE (SpeciesRecord
    carries no edge_delta by design, B9 §1): one ``{rule.id: {axis:
    [old, new]}}`` entry per fired rule that actually snapped a dial —
    the exact content k13 stashed under
    ``edge_delta["constraint"][rule.id]``.  A rule that fired but had
    nothing to snap records nothing.  Idempotent: a second run over the
    same record returns [] and changes nothing.
    """
    audit: Audit = []
    for rule in pack.constraints:
        if not triggered(rule, child.axes, child.plan):
            continue
        snaps: Snap = {}
        if rule.state_plans and child.plan not in rule.state_plans:
            _snap_back(rule, parent, child, pack, snaps)
            if snaps:
                audit.append({rule.id: snaps})
            continue
        for a, lo in rule.require_min.items():
            v = child.axes.get(a)
            if isinstance(v, (int, float)) and v < lo:
                child.axes[a] = lo
                snaps[a] = [v, lo]
        for a, hi in rule.require_max.items():
            v = child.axes.get(a)
            if isinstance(v, (int, float)) and v > hi:
                child.axes[a] = hi
                snaps[a] = [v, hi]
        for a, states in rule.require_enum.items():
            v = child.axes.get(a)
            if v is not None and str(v) not in states:
                cand = _candidates(child.plan, pack, a, list(states))
                if cand:
                    child.axes[a] = cand[0]
                    snaps[a] = [v, cand[0]]
                else:
                    # no legal way to satisfy the combination on this
                    # plan: the trigger itself was the illegal part
                    _snap_back(rule, parent, child, pack, snaps)
                    break
        else:
            for a, states in rule.forbid_enum.items():
                v = child.axes.get(a)
                if v is None or str(v) not in states:
                    continue
                prior = parent.axes.get(a) if parent is not None else None
                if prior is not None and str(prior) not in states:
                    child.axes[a] = prior
                    snaps[a] = [v, prior]
                    continue
                spec = pack.registry.axes.get(a)
                legal = _candidates(
                    child.plan, pack, a,
                    [s for s in (spec.states if spec else [])
                     if s not in states])
                if legal:
                    child.axes[a] = legal[0]
                    snaps[a] = [v, legal[0]]
                else:
                    _snap_back(rule, parent, child, pack, snaps)
                    break
        if snaps:
            audit.append({rule.id: snaps})
    return audit
