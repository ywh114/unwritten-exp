"""Flora constraint rules (vocabulary §8.10): the legality gate.

Data-driven, enforced at sampling time inside the same evolve edge (the
gate pattern — trigger fires, required axes snap into compliance, the
snap is recorded in ``edge_delta`` under the "constraint" force key).
Never post-hoc deletion, never a hard cap: a constraint states that one
trait COMBINATION is not a thing (CAM without water storage, red
wind-pollinated flowers), so the offending dial is pulled to the
threshold, not deleted.

Rule semantics (constraints.toml):
    when = { axis = X, state = S | [S, ...] }   trigger: enum in state(s)
    when = { axis = X, above = f }              trigger: scalar above f
    when.plans = [plan, ...]      rule SCOPE: the rule fires only on
        these plans (spinescence_aridity is a land-plant rule; a sponge's
        spicules are none of its business)
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
"""

from __future__ import annotations

from dataclasses import dataclass, field

# enum axes whose snap candidates are palette-filtered (mirrors the
# sampler legality in k13 forces._legal_states).
PALETTE_AXES = ("flower_color",)


@dataclass(frozen=True)
class Rule:
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


def _trigger_states(rule: Rule) -> list[str] | None:
    s = rule.when.get("state")
    if s is None:
        return None
    return [str(x) for x in s] if isinstance(s, list) else [str(s)]


def triggered(rule: Rule, axes: dict, plan: str | None = None) -> bool:
    scope = rule.when.get("plans")
    if scope and plan is not None and plan not in scope:
        return False
    ax = rule.when.get("axis")
    if ax is None:
        return False
    v = axes.get(ax)
    if v is None:
        return False
    states = _trigger_states(rule)
    if states is not None:
        return str(v) in states
    if "above" in rule.when:
        return isinstance(v, (int, float)) and v > rule.when["above"]
    return False


def _candidates(node_plan: str | None, pack, axis: str,
                states: list[str]) -> list[str]:
    """Snap candidates, palette-filtered for color axes."""
    if axis in PALETTE_AXES and node_plan:
        palette = pack.palettes.get(node_plan)
        if palette:
            states = [s for s in states if s in palette]
    return states


def _snap_back(rule: Rule, parent, child, pack, snaps: dict) -> None:
    """Off-plan trigger state: revert the trigger axis to the parent's
    prior value (else the first registry state that differs)."""
    ax = rule.when["axis"]
    cur = child.axes.get(ax)
    prior = parent.axes.get(ax) if parent is not None else None
    bad = _trigger_states(rule) or []
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


def violations(node, pack) -> list[str]:
    """All constraint breaches on one committed node (metrics gate)."""
    errs: list[str] = []
    for rule in pack.constraints:
        if not triggered(rule, node.axes, node.plan):
            continue
        if rule.state_plans and node.plan not in rule.state_plans:
            errs.append(f"{node.path}: {rule.id}: trigger state illegal "
                        f"on plan {node.plan!r} (state_plans)")
            continue
        errs.extend(f"{node.path}: {e}"
                    for e in _require_errors(rule, node.axes))
    return errs


def enforce(parent, child, pack) -> None:
    """Snap the child's record into compliance for every triggered rule.

    Called per evolve edge, after the size envelope (legality is the
    final word). Snaps are recorded in edge_delta under the "constraint"
    force key so the provenance trail shows the gate fired.
    """
    for rule in pack.constraints:
        if not triggered(rule, child.axes, child.plan):
            continue
        snaps: dict = {}
        if rule.state_plans and child.plan not in rule.state_plans:
            _snap_back(rule, parent, child, pack, snaps)
            if snaps:
                child.edge_delta.setdefault("constraint",
                                            {})[rule.id] = snaps
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
            child.edge_delta.setdefault("constraint", {})[rule.id] = snaps
