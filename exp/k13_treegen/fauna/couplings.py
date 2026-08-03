"""M6 — couplings engine (docs/m6-couplings.md).

Rules are data records (content/couplings.toml); this module is the only
interpreter. Every active rule has an existence proof in test_m6.py — a
coupling that never measurably changes output is the v1 identity-tradeoff
bug and fails its test.

Kinds: gate (trigger state legalizes a pull toward bounds), tradeoff
(signed σ-transfer; negative strength = anticorrelate), bundle (one
trigger event fires a correlated effect set). Per-world weak bindings are
K1-seeded arbitrary scalar pairs (B1 §15 flavor note).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from exp.k13_treegen.fauna.content import ContentPack
from exp.k13_treegen.forces import Condition, adapt_weight, _clip
from exp.k13_treegen.model import Node
from exp.k13_treegen.registry import ValueType
from exp.k13_treegen.fauna.seeding import STAGE_WEAK_BINDINGS, stage_stream
from kernel.hashrng import Stream

# gate: fraction of the way to the lower bound per gated evolve step.
GATE_PULL = 0.3
# ornament cost: pull per stressed evolve step, scaled CONTINUOUSLY by
# condition.stress (user ruling: no step thresholds on continuous
# variables — pull = ORNAMENT_PULL x stress).
ORNAMENT_PULL = 0.2
# weak bindings: per-world count and coefficient range (flavor only —
# B1 §15: the curated rules are the ones worth learning).
WEAK_BIND_COUNT = 3
WEAK_BIND_LO = 0.1
WEAK_BIND_HI = 0.3

VALID_KINDS = {"gate", "tradeoff", "bundle"}


@dataclass(frozen=True)
class WeakBinding:
    a: str
    b: str
    coeff: float


@dataclass
class Rule:
    id: str
    kind: str
    status: str
    scope: list[str]
    source: str
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_toml(cls, t: dict) -> "Rule":
        scope = t.get("scope", ["all"])
        return cls(id=t["id"], kind=t["kind"], status=t.get("status",
                                                            "active"),
                   scope=[scope] if isinstance(scope, str) else list(scope),
                   source=t.get("source", ""), raw=t)

    def applies_to(self, plan: str | None) -> bool:
        return "all" in self.scope or (plan is not None
                                       and plan in self.scope)


def validate_couplings(pack: ContentPack) -> list[str]:
    """Structural validation of the rule records (lint-class)."""
    errs: list[str] = []
    for r in pack.couplings:
        if r.kind not in VALID_KINDS:
            errs.append(f"rule {r.id}: unknown kind {r.kind!r}")
        if r.status == "dormant":
            if not r.raw.get("dormant_reason"):
                errs.append(f"rule {r.id}: dormant without a reason")
            continue
        def need_axis(name, where):
            if name not in pack.registry.axes:
                errs.append(f"rule {r.id}: {where} {name!r} not registered")
        if r.kind == "tradeoff":
            need_axis(r.raw.get("a"), "a")
            need_axis(r.raw.get("b"), "b")
            if not isinstance(r.raw.get("strength"), (int, float)):
                errs.append(f"rule {r.id}: tradeoff needs numeric strength")
        elif r.kind == "gate":
            trig = r.raw.get("trigger", {})
            if "axis" in trig:
                need_axis(trig["axis"], "trigger.axis")
            elif "env" in trig:
                if "above" not in trig and "below" not in trig:
                    errs.append(f"rule {r.id}: env gate needs above/below")
            elif trig.get("condition") != "stressed":
                errs.append(f"rule {r.id}: gate trigger must name axis, "
                            f"env, or condition")
            if trig.get("toward", "min") not in ("min", "max", "zero"):
                errs.append(f"rule {r.id}: toward must be min|max|zero")
            for t in r.raw.get("targets", []):
                need_axis(t, "target")
        elif r.kind == "bundle":
            trig = r.raw.get("trigger", {})
            need_axis(trig.get("axis"), "trigger.axis")
            for eff in r.raw.get("effect", []):
                need_axis(eff.get("axis"), "effect.axis")
    return errs


# ──  per-world weak bindings  ─────────────────────────────────────────────


def weak_bindings(seed: int, pack: ContentPack) -> list[WeakBinding]:
    """K1-seeded arbitrary scalar pairs with small coefficients — clade
    texture (B1 §15 closing note). Deterministic per seed, differs across
    seeds."""
    eligible = sorted(
        n for n, a in pack.registry.axes.items()
        if a.mutable and a.value_type is ValueType.SCALAR and a.sigma > 0)
    s = stage_stream(seed, *STAGE_WEAK_BINDINGS)
    out: list[WeakBinding] = []
    for i in range(WEAK_BIND_COUNT):
        a = eligible[s.randrange(len(eligible), 0, 2 * i)]
        b = eligible[s.randrange(len(eligible), 0, 2 * i + 1)]
        if a == b:
            b = eligible[(eligible.index(a) + 1) % len(eligible)]
        coeff = WEAK_BIND_LO + (WEAK_BIND_HI - WEAK_BIND_LO) * s.uniform(1, i)
        if s.bernoulli(0.5, 2, i):
            coeff = -coeff
        out.append(WeakBinding(a, b, coeff))
    return out


# ──  the coupling pass  ───────────────────────────────────────────────────


def _z(delta: float, sigma: float) -> float:
    return delta / sigma if sigma > 0 else 0.0


def _z_own(spec, parent_v: float, child_v: float) -> float:
    """σ-distance of a parent→child step in the axis's OWN space: log for
    multiplicative axes, raw for additive ones. Raw-unit transfer on a
    log_gaussian axis reads a beetle's +2x mass step as ~0 σ and a
    whale's as +40 σ (and applied backwards it shoved beetles by whole
    KILOGRAMS — the 0.1 g .. 6 kg 'beetle' explosion)."""
    import math
    if spec.sigma <= 0:
        return 0.0
    if spec.mutation_kind.value != "gaussian" and parent_v > 0 \
            and child_v > 0:
        return (math.log(child_v) - math.log(parent_v)) / spec.sigma
    return (child_v - parent_v) / spec.sigma


def _apply_z(spec, v: float, z: float) -> float:
    """The inverse of _z_own: apply a σ-transfer in the axis's own
    space, then clip to authored bounds."""
    import math
    if spec.mutation_kind.value != "gaussian" and v > 0:
        return _clip(v * math.exp(z * spec.sigma), spec)
    return _clip(v + z * spec.sigma, spec)


def _sigma(pack: ContentPack, axis: str) -> float:
    spec = pack.registry.axes.get(axis)
    return spec.sigma if spec is not None else 0.0


def _scalar_axes(rule_targets, child: Node, pack: ContentPack):
    for t in rule_targets:
        v = child.axes.get(t)
        spec = pack.registry.axes.get(t)
        if (spec is not None and spec.value_type is ValueType.SCALAR
                and isinstance(v, (int, float))):
            yield t, float(v), spec


def apply_couplings(parent: Node, child: Node, pack: ContentPack,
                    condition: Condition, stream: Stream,
                    weak: list[WeakBinding] | None = None) -> None:
    """Run active rules (+ weak bindings) against the parent→child step,
    mutating child.axes and recording forced movement in edge_delta."""

    def record(axis: str, amount: float) -> None:
        d = child.edge_delta.setdefault(
            axis, {"drift": 0.0, "descent": 0.0, "runaway": 0.0})
        d["coupling"] = d.get("coupling", 0.0) + amount

    def tradeoff(a: str, b: str, strength: float) -> None:
        """Signed σ-transfer in BOTH directions (user ruling: knobs and
        results are equal citizens — a coupling links two axes, it does
        not make one cause the other). Both transfers are computed from
        the un-adjusted deltas, then applied, so no same-step feedback.
        σ is measured/applied in each axis's OWN space (log for
        multiplicative axes)."""
        induced: dict[str, float] = {}
        for x, y in ((a, b), (b, a)):
            px, cx = parent.axes.get(x), child.axes.get(x)
            if not all(isinstance(v, (int, float)) for v in (px, cx)):
                continue
            xspec = pack.registry.axes.get(x)
            if xspec is None:
                continue
            zx = _z_own(xspec, float(px), float(cx))
            if zx != 0.0:
                induced[y] = induced.get(y, 0.0) + strength * zx
        for y, zy in induced.items():
            spec = pack.registry.axes.get(y)
            if isinstance(child.axes.get(y), (int, float)) and spec:
                child.axes[y] = _apply_z(spec, float(child.axes[y]), zy)
                record(y, zy)

    for rule in pack.couplings:
        if rule.status != "active" or not rule.applies_to(child.plan):
            continue
        raw = rule.raw
        if rule.kind == "tradeoff":
            tradeoff(raw["a"], raw["b"], float(raw["strength"]))
        elif rule.kind == "gate":
            trig = raw.get("trigger", {})
            toward = trig.get("toward", "min")
            if "axis" in trig:
                state = trig.get("state")
                held_by_parent = parent.axes.get(trig["axis"]) == state
                if not held_by_parent and \
                        child.axes.get(trig["axis"]) != state:
                    continue
                # the gate MAINTAINS itself: a parent holding the gated
                # state re-asserts it on the child (Dollo — a flightless
                # clade does not re-evolve flight; the first blind build
                # caught a penguin lineage redrawing 'hovering').
                if held_by_parent and child.axes.get(trig["axis"]) != state:
                    child.axes[trig["axis"]] = state
                    record(trig["axis"], 1.0)
                pull = GATE_PULL
            elif "env" in trig:
                # world-conditioned gate (rounds hook): absent env data
                # means the gate stays silent (world-blind default).
                v = condition.env.get(trig["env"])
                if v is None:
                    continue
                if "below" in trig and not v < float(trig["below"]):
                    continue
                if "above" in trig and not v > float(trig["above"]):
                    continue
                pull = GATE_PULL
            elif trig.get("condition") == "stressed":
                if condition.stress <= 0.0:
                    continue
                pull, toward = ORNAMENT_PULL * condition.stress, "zero"
            else:
                continue
            for t, v, spec in _scalar_axes(raw.get("targets", []), child,
                                           pack):
                lo = spec.bounds[0] if spec.bounds else 0.0
                hi = spec.bounds[1] if spec.bounds else 0.0
                floor = {"min": lo, "max": hi, "zero": 0.0}[toward]
                new = v - pull * (v - floor)
                child.axes[t] = new
                record(t, _z(new - v, spec.sigma))
        elif rule.kind == "bundle":
            trig = raw.get("trigger", {})
            axis, direction = trig.get("axis"), int(trig.get("direction", 1))
            pv, cv = parent.axes.get(axis), child.axes.get(axis)
            if not all(isinstance(v, (int, float)) for v in (pv, cv)):
                continue
            tspec = pack.registry.axes.get(axis)
            z = _z_own(tspec, float(pv), float(cv)) if tspec else 0.0
            if direction * z < float(trig.get("min_z", 0.5)):
                continue
            # one event, correlated set: every effect fires together
            for eff in raw.get("effect", []):
                eax = eff["axis"]
                if "state" in eff:
                    child.axes[eax] = eff["state"]
                    record(eax, 1.0)
                elif "z" in eff:
                    v = child.axes.get(eax)
                    espec = pack.registry.axes.get(eax)
                    if isinstance(v, (int, float)) and espec:
                        child.axes[eax] = _apply_z(
                            espec, float(v), float(eff["z"]))
                        record(eax, float(eff["z"]))

    for wb in weak or []:
        tradeoff(wb.a, wb.b, wb.coeff)
