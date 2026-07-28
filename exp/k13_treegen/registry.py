"""M1 — axis registry (integration contract C1, the keystone).

Every axis (a B1 morphometric knob or a flat vocabulary axis) is one
``AxisSpec``. The ``Registry`` is the validated, consumer-ready view of the
schema; M5's sampler, M6's couplings, M8's naming, and M12's renderer all
dispatch on per-axis metadata held here. **If a future consumer needs new
per-axis data, it is added to ``AxisSpec`` once — never per module.**

Three-tier taxonomy (user ruling): ``invariant`` (plan topology — change it
and you changed the plan, not the species) → ``steady`` (proportions, small
drift) → ``labile`` (ears, tail, ornaments, color; large drift).

Vary-by-default with a clade-steady blacklist (the v1 freeze-bug fix, stated
as a schema rule): every axis that is neither ``invariant`` nor
``clade_steady`` MUST carry a real mutation kind with positive sigma. A
frozen non-steady axis is a validation error, so the bug cannot recur.

Size convention (B1 v0.3 §1): mass is the single size axis; every other knob
is dimensionless. The ``unit`` lint enforces exactly one ``mass`` axis.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Tier(str, Enum):
    INVARIANT = "invariant"   # plan topology; sampler must not touch
    STEADY = "steady"         # proportions / limb indices; small drift
    LABILE = "labile"         # ears, tail, ornaments, color; large drift


class ValueType(str, Enum):
    SCALAR = "scalar"
    INT = "int"
    ENUM = "enum"
    BOOL = "bool"
    WEIGHTED_SET = "weighted_set"  # map state -> weight (~1 sum); e.g. diet


class MutationKind(str, Enum):
    GAUSSIAN = "gaussian"          # additive N(0, sigma)
    LOG_GAUSSIAN = "log_gaussian"  # multiplicative on a positive axis (mass)
    ENUM_REDRAW = "enum_redraw"    # uniform draw over `states`
    RATIO = "ratio"                # bounded ratio; gaussian then leaky-clamp
    WEIGHT_REDRAW = "weight_redraw"  # perturb set weights, renormalize
    NONE = "none"                  # fixed (invariant / clade-steady)


class Unit(str, Enum):
    DIMENSIONLESS = "dimensionless"
    MASS = "mass"                  # exactly one axis registry-wide


class TemporalModifier(str, Enum):
    NONE = "none"
    JUVENILE_ONLY = "juvenile_only"
    SEASONAL = "seasonal"
    AGE_RAMPED = "age_ramped"
    BREEDING_MALE = "breeding_male"


class GrammarRole(str, Enum):
    SIZE = "size"
    COVERING = "covering"
    GRADE = "grade"
    DIET = "diet"
    PART = "part"
    NONE = "none"


class Block(str, Enum):
    MORPHOMETRICS = "morphometrics"
    PATTERNATION = "patternation"
    NICHE = "niche"
    DIET = "diet"
    LIFE_HISTORY = "life_history"
    BEHAVIOR = "behavior"
    ECOSYSTEM = "ecosystem"
    SEX_AGE_SEASON = "sex_age_season"


VALID_CONSUMERS = {"stress", "drift", "runaway", "id", "name", "tell",
                   "pop", "draw"}


class RegistryError(Exception):
    """The registry failed validation."""


@dataclass
class AxisSpec:
    """One axis. See module docstring for the contract each field signs."""

    name: str
    block: Block
    tier: Tier
    value_type: ValueType
    mutation_kind: MutationKind = MutationKind.NONE
    sigma: float = 0.0
    states: list[str] = field(default_factory=list)
    bounds: tuple[float, float] | None = None     # leaky; scalar/int only
    clade_steady: bool = False
    plan_scope: list[str] | str = "all"           # plan ids, or "all"
    consumers: set[str] = field(default_factory=set)
    salience: float = 0.0                          # M8 epithet / M12 part pick
    grammar_role: GrammarRole = GrammarRole.NONE
    coupling_triggers: list[str] = field(default_factory=list)
    unit: Unit = Unit.DIMENSIONLESS
    temporal_modifier: TemporalModifier = TemporalModifier.NONE
    sex_linked: bool = False
    adapt_weight: float | None = None   # M5: 0=decorative .. 1=adaptive
    # RESERVED (rounds layer): functional effect vector, e.g.
    # {thermal: 0.8, camouflage: -0.6, warning: 0.9}. Parsed and shape-
    # validated, consumed by NOTHING yet — the hook for "knobs give stat
    # bonuses/debuffs" (user 2026-07-28; rounds spec-note §7).
    effects: dict[str, float] | None = None

    # ──  construction  ────────────────────────────────────────────────

    @classmethod
    def from_toml(cls, name: str, t: dict) -> "AxisSpec":
        bounds = t.get("bounds")
        return cls(
            name=name,
            block=Block(t.get("block", "morphometrics")),
            tier=Tier(t["tier"]),
            value_type=ValueType(t["value_type"]),
            mutation_kind=MutationKind(t.get("mutation", "none")),
            sigma=float(t.get("sigma", 0.0)),
            states=list(t.get("states", [])),
            bounds=(float(bounds[0]), float(bounds[1])) if bounds else None,
            clade_steady=bool(t.get("clade_steady", False)),
            plan_scope=t.get("plan_scope", "all"),
            consumers=set(t.get("consumers", [])),
            salience=float(t.get("salience", 0.0)),
            grammar_role=GrammarRole(t.get("grammar_role", "none")),
            coupling_triggers=list(t.get("coupling_triggers", [])),
            unit=Unit(t.get("unit", "dimensionless")),
            temporal_modifier=TemporalModifier(
                t.get("temporal_modifier", "none")),
            sex_linked=bool(t.get("sex_linked", False)),
            adapt_weight=(float(t["adapt_weight"])
                          if "adapt_weight" in t else None),
            effects=(dict(t["effects"]) if "effects" in t else None),
        )

    # ──  queries  ────────────────────────────────────────────────────

    @property
    def mutable(self) -> bool:
        """True if the sampler may move this axis."""
        return (not self.clade_steady and self.tier is not Tier.INVARIANT
                and self.mutation_kind is not MutationKind.NONE)

    def applies_to(self, plan: str) -> bool:
        return self.plan_scope == "all" or plan in self.plan_scope

    # ──  validation  ─────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return a list of error strings (empty == valid)."""
        errs: list[str] = []
        n = self.name
        if not self.consumers:
            errs.append(f"{n}: must name >=1 consumer (rent audit)")
        bad = self.consumers - VALID_CONSUMERS
        if bad:
            errs.append(f"{n}: unknown consumers {sorted(bad)}")
        if self.tier is Tier.INVARIANT and \
                self.mutation_kind is not MutationKind.NONE:
            errs.append(f"{n}: invariant axis must have mutation=none "
                        f"(change it and you changed the plan, not species)")
        if self.clade_steady and self.mutation_kind is not MutationKind.NONE:
            errs.append(f"{n}: clade_steady blacklist forces mutation=none")
        # the freeze-bug fix: a mutable axis must actually move
        if self.mutable:
            if self.mutation_kind in (MutationKind.GAUSSIAN,
                                      MutationKind.LOG_GAUSSIAN,
                                      MutationKind.RATIO,
                                      MutationKind.WEIGHT_REDRAW) and \
                    self.sigma <= 0:
                errs.append(f"{n}: mutable axis must have sigma>0 "
                            f"(vary-by-default; freeze bug)")
            if self.mutation_kind in (MutationKind.ENUM_REDRAW,
                                      MutationKind.WEIGHT_REDRAW) and \
                    not self.states:
                errs.append(f"{n}: {self.mutation_kind.value} requires "
                            f"non-empty states")
        if self.value_type is ValueType.ENUM and self.mutation_kind not in \
                (MutationKind.ENUM_REDRAW, MutationKind.NONE):
            errs.append(f"{n}: enum value_type needs mutation "
                        f"enum_redraw or none")
        if self.value_type is ValueType.WEIGHTED_SET and \
                self.mutation_kind not in (MutationKind.WEIGHT_REDRAW,
                                           MutationKind.NONE):
            errs.append(f"{n}: weighted_set value_type needs mutation "
                        f"weight_redraw or none")
        if self.value_type in (ValueType.SCALAR, ValueType.INT):
            if self.bounds is None:
                errs.append(f"{n}: scalar/int axis needs bounds")
            elif not (self.bounds[0] < self.bounds[1]):
                errs.append(f"{n}: bounds must have lo<hi")
        if self.mutation_kind is MutationKind.LOG_GAUSSIAN and \
                self.bounds is not None and self.bounds[0] <= 0:
            errs.append(f"{n}: log_gaussian axis must be strictly positive")
        scope = self.plan_scope
        if scope != "all" and not scope:
            errs.append(f"{n}: plan_scope must be 'all' or non-empty")
        if self.salience < 0:
            errs.append(f"{n}: salience must be >=0")
        if self.adapt_weight is not None and \
                not (0.0 <= self.adapt_weight <= 1.0):
            errs.append(f"{n}: adapt_weight must be in [0,1] "
                        f"(0=decorative, 1=adaptive)")
        if self.effects is not None:
            for k, v in self.effects.items():
                if not k or not isinstance(v, (int, float)):
                    errs.append(f"{n}: effects must map channel names to "
                                f"numbers (bad entry {k!r}: {v!r})")
        return errs


@dataclass
class PlanSpec:
    """A body plan: legal generic->realization bindings (the rebind
    permission table, M0) + slot list (string enums) + medium."""

    id: str
    medium: str = "land"
    magic_only: bool = False
    slots: list[str] = field(default_factory=list)
    generics: dict[str, list[str]] = field(default_factory=dict)
    phylum: str = ""            # M7 frame map: taxonomic phylum anchor
    frame: str = ""             # inner_frame | outer_frame

    @classmethod
    def from_toml(cls, pid: str, t: dict) -> "PlanSpec":
        return cls(id=pid, medium=t.get("medium", "land"),
                   magic_only=bool(t.get("magic_only", False)),
                   slots=list(t.get("slots", [])),
                   generics={g: list(r) for g, r in
                             t.get("generics", {}).items()},
                   phylum=t.get("phylum", ""),
                   frame=t.get("frame", ""))

    def permissions(self) -> dict[str, list[str]]:
        """The rebind permission table for ``model.rebind``."""
        return self.generics


@dataclass
class Registry:
    """The validated, consumer-ready schema. Built once, read-only after."""

    axes: dict[str, AxisSpec] = field(default_factory=dict)
    plans: dict[str, PlanSpec] = field(default_factory=dict)

    # ──  construction  ────────────────────────────────────────────────

    @classmethod
    def from_toml(cls, axis_defs: dict, plan_defs: dict | None = None,
                  coupling_ids: set[str] | None = None) -> "Registry":
        """Build from parsed TOML tables.

        *axis_defs*: ``{axis_name: table}`` (the ``[axis.*]`` section).
        *plan_defs*: ``{plan_id: table}`` (the ``[plan.*]`` section).
        *coupling_ids*: if given, ``coupling_triggers`` must resolve here.
        """
        reg = cls()
        for name, t in axis_defs.items():
            reg.axes[name] = AxisSpec.from_toml(name, t)
        for pid, t in (plan_defs or {}).items():
            reg.plans[pid] = PlanSpec.from_toml(pid, t)
        errs = reg.validate(coupling_ids)
        if errs:
            raise RegistryError("registry validation failed:\n  " +
                                "\n  ".join(errs))
        return reg

    @classmethod
    def load(cls, path: str | Path,
             coupling_ids: set[str] | None = None) -> "Registry":
        """Load ``[axis.*]`` and ``[plan.*]`` tables from one TOML file."""
        data = tomllib.loads(Path(path).read_text())
        return cls.from_toml(data.get("axis", {}), data.get("plan", {}),
                             coupling_ids)

    # ──  queries  ────────────────────────────────────────────────────

    def axis(self, name: str) -> AxisSpec:
        return self.axes[name]

    def applicable_axes(self, plan: str) -> list[AxisSpec]:
        return [a for a in self.axes.values() if a.applies_to(plan)]

    def mass_axis(self) -> str | None:
        masses = [a.name for a in self.axes.values()
                  if a.unit is Unit.MASS]
        return masses[0] if masses else None

    def salience_order(self, plan: str | None = None) -> list[AxisSpec]:
        """Axes ordered by descending salience (M8 epithet selection)."""
        axes = (self.applicable_axes(plan) if plan
                else list(self.axes.values()))
        return sorted(axes, key=lambda a: (-a.salience, a.name))

    def grammar_index(self) -> dict[GrammarRole, list[str]]:
        """grammar_role -> axis names (M12 description template slots)."""
        idx: dict[GrammarRole, list[str]] = {}
        for a in self.axes.values():
            idx.setdefault(a.grammar_role, []).append(a.name)
        return idx

    def plan_permissions(self, plan: str) -> dict[str, list[str]]:
        p = self.plans.get(plan)
        return p.permissions() if p else {}

    # ──  validation  ─────────────────────────────────────────────────

    def validate(self, coupling_ids: set[str] | None = None) -> list[str]:
        errs: list[str] = []
        for a in self.axes.values():
            errs.extend(a.validate())
            if coupling_ids is not None:
                for cid in a.coupling_triggers:
                    if cid not in coupling_ids:
                        errs.append(f"{a.name}: coupling_trigger {cid!r} "
                                    f"not registered")
            # plan_scope must reference known plans (if plans are loaded)
            if self.plans and a.plan_scope != "all":
                unknown = set(a.plan_scope) - set(self.plans)
                if unknown:
                    errs.append(f"{a.name}: plan_scope references unknown "
                                f"plans {sorted(unknown)}")
        # exactly one mass axis (B1 v0.3 size convention)
        masses = [a.name for a in self.axes.values() if a.unit is Unit.MASS]
        if len(masses) == 0:
            errs.append("registry: exactly one axis must have unit=mass "
                        "(size convention); found none")
        elif len(masses) > 1:
            errs.append(f"registry: exactly one mass axis allowed; found "
                        f"{sorted(masses)}")
        return errs
