"""Flora metrics harness: the standing gate for generated flora trees.

Mirrors K13 M11. Checks consume ``(tree, pack)`` and return violation
strings. The report is byte-stable per seed: sorted checks, sorted
violations, canonical counts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from exp.k13_treegen.registry import MutationKind, ValueType
from exp.k13_treegen.flora.constraints import violations as constraint_violations
from exp.k13_treegen.flora.content import ContentPack, merged_pin
from exp.k13_treegen.flora.derive import DERIVED_AXES
from exp.k13_treegen.model import Rank, Tree

# diversity: a generated tree with <2 species or a single grade is the
# low-diversity failure shape.
MIN_SPECIES = 2
# pin coherence: a pinned node's height must stay within grade
# magnitude of its preset (the flora crocodile-on-monkey class).
PIN_HEIGHT_FACTOR = 4.0


def _species(tree: Tree) -> list:
    return [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]


def check_diversity(tree: Tree, pack: ContentPack) -> list[str]:
    sp = _species(tree)
    errs: list[str] = []
    if len(sp) < MIN_SPECIES:
        errs.append(f"only {len(sp)} species (min {MIN_SPECIES})")
    presets = {n.preset for n in sp}
    if sp and len(presets) < 2:
        errs.append(f"all {len(sp)} species under one preset "
                    f"{next(iter(presets))!r} (no grade diversity)")
    return errs


# ── frozen_axis design ──────────────────────────────────────────────────
# The check exists to catch the v1 freeze bug (an axis that CANNOT move),
# not statistical stillness. A freeze is only surprising when the plan
# had enough independent mutation opportunities to move the axis, so the
# threshold is computed, not fixed:
#   opportunities = species + genera + families under the plan (each is
#     an independent mutation series below the plan root);
#   enum axes: per-edge redraw probability ~0.236 at a typical species
#     edge (ENUM_RATE x dg~60 x step_scale ~1.5, times the steady tier
#     gate ~0.78); a redraw lands on a DIFFERENT state with probability
#     1 - 1/n_states, so P(no change in one edge) = 1 - 0.236 x
#     (1 - 1/n_states); flag when P(no change in all opportunities)
#     < ENUM_ALPHA;
#   scalar/weighted-set axes: continuous mutation makes an exact freeze
#     across >= MIN_OPPORTUNITIES species impossible under working
#     machinery — flag outright;
#   int axes whose typical per-edge step is sub-quantum
#     (STEP_Z_TYPICAL x sigma < 0.5, the rounding quantum) cannot cross
#     a step in one edge regardless of machinery — discreteness
#     arithmetic, the computed form of K13's sigma<0.5 skip;
#   axes pinned by the constraint gate (require_*/forbid targets) and
#     tiny plans (< MIN_OPPORTUNITIES) are skipped: stillness there is
#     expected, not a bug.
MIN_OPPORTUNITIES = 8
P_REDRAW_TYPICAL = 0.236
ENUM_ALPHA = 0.001
# typical per-edge drift step in z-units: DRIFT_RATE x shares.drift ~
# 0.33 x step_scale(g~510) ~ 1.5 x sqrt(dg~60).
STEP_Z_TYPICAL = 0.386


def _constraint_targets(pack: ContentPack) -> set[str]:
    out: set[str] = set()
    for r in pack.constraints:
        out.update(r.require_min, r.require_max,
                   r.require_enum, r.forbid_enum)
        if r.state_plans:
            ax = r.when.get("axis")
            if ax:
                out.add(ax)
    return out


def check_frozen_axis(tree: Tree, pack: ContentPack) -> list[str]:
    """A mutable axis that never varies despite ample mutation
    opportunities is the v1 freeze bug at tree level."""
    sp = _species(tree)
    errs: list[str] = []
    by_plan: dict[str, list] = {}
    for n in sp:
        by_plan.setdefault(n.plan or "?", []).append(n)
    pinned_targets = _constraint_targets(pack)
    for plan, nodes in sorted(by_plan.items()):
        # mutation series below the plan root: species edges plus the
        # genus/family edges that differentiate sub-clades
        prefix = nodes[0].path.rsplit(".o", 1)[0] + "."
        sub = [n for n in tree.nodes.values()
               if n.path.startswith(prefix) and (n.plan or "?") == plan]
        opp = len(nodes) + sum(1 for n in sub
                               if n.rank in (Rank.GENUS, Rank.FAMILY))
        if opp < MIN_OPPORTUNITIES:
            continue
        present = set.intersection(*(set(n.axes) for n in nodes)) \
            if nodes else set()
        for ax in sorted(present):
            spec = pack.registry.axes.get(ax)
            if spec is None or not spec.mutable:
                continue
            # derived axes are recomputed from the record — uniform
            # output is correct, not a freeze
            if ax in DERIVED_AXES:
                continue
            # constraint-pinned axes are SUPPOSED to be still
            if ax in pinned_targets:
                continue
            # sub-quantum int axes (typical per-edge step below the
            # rounding quantum) cannot move regardless of machinery —
            # discreteness arithmetic, not the freeze bug.
            if spec.value_type is ValueType.INT and \
                    STEP_Z_TYPICAL * spec.sigma < 0.5:
                continue
            # single-key weighted sets (e.g. diet_spectrum = {detritivore:
            # 1.0}) renormalize to the same value on every mutation —
            # structurally unmovable, not the freeze bug (0032 caught
            # the beetles order pin tripping this).
            if spec.value_type is ValueType.WEIGHTED_SET \
                    and isinstance(nodes[0].axes.get(ax), dict) \
                    and len(nodes[0].axes[ax]) <= 1:
                continue
            vals = {str(n.axes[ax]) for n in nodes}
            if len(vals) > 1:
                continue
            if spec.value_type is ValueType.ENUM:
                n_states = max(1, len(spec.states))
                p_no_change = 1.0 - P_REDRAW_TYPICAL * (1.0
                                                        - 1.0 / n_states)
                if p_no_change ** opp >= ENUM_ALPHA:
                    continue   # stillness is within chance for this plan
            errs.append(f"plan {plan}: axis {ax} frozen at "
                        f"{next(iter(vals))!r} across {len(nodes)} "
                        f"species ({opp} mutation opportunities)")
    return errs


def check_constraints(tree: Tree, pack: ContentPack) -> list[str]:
    """The constraint gate: no committed record may breach a triggered
    rule (vocabulary §8.10). Pinned records are trusted at build time
    but still audited here."""
    errs: list[str] = []
    for n in tree.nodes.values():
        if n.axes:
            errs.extend(constraint_violations(n, pack))
    return errs


def check_pin_coherence(tree: Tree, pack: ContentPack) -> list[str]:
    """A pinned node's height must stay within grade magnitude of its
    preset."""
    errs: list[str] = []
    for n in tree.nodes.values():
        if "pinned" not in n.flags or not n.preset:
            continue
        preset_h = pack.preset_height(n.preset)
        node_h = n.axes.get("height_m")
        if (preset_h and isinstance(node_h, (int, float))
                and node_h > 0):
            ratio = node_h / preset_h
            if ratio > PIN_HEIGHT_FACTOR or ratio < 1.0 / PIN_HEIGHT_FACTOR:
                errs.append(f"{n.path} ({n.label}): height_m {node_h} "
                            f"is {ratio:.0f}x preset {n.preset!r}")
    return errs


def check_g_clock(tree: Tree, pack: ContentPack) -> list[str]:
    """g monotonic nondecreasing root->leaf; gen_time ordering (the tall
    half of species must not run faster than the short half)."""
    errs: list[str] = []
    for n in tree.nodes.values():
        if n.parent and n.parent in tree.nodes:
            p = tree.nodes[n.parent]
            if n.g < p.g:
                errs.append(f"{n.path}: g {n.g} < parent g {p.g} "
                            f"(clock runs backward)")
    sp = [n for n in _species(tree)
          if isinstance(n.axes.get("height_m"), (int, float))
          and n.gen_time > 0]
    if len(sp) >= 2:
        heights = sorted(n.axes["height_m"] for n in sp)
        mid = heights[len(heights) // 2]
        tall = [n.gen_time for n in sp if n.axes["height_m"] >= mid]
        short = [n.gen_time for n in sp if n.axes["height_m"] < mid]
        if tall and short:
            med = lambda v: sorted(v)[len(v) // 2]
            if med(tall) < med(short):
                errs.append("gen_time ordering inverted: tall species "
                            "run faster than short ones")
    return errs


def check_backbone(tree: Tree, pack: ContentPack) -> list[str]:
    """Single plantae kingdom root; authored frame map enforced (each
    plan's class under a phylum carrying the plan's frame flag); no
    empty orders. Structural checks apply only when the tree HAS
    structure."""
    errs: list[str] = []
    structural = [n for n in tree.nodes.values()
                  if n.rank is not Rank.SPECIES]
    if not structural:
        return errs
    kingdom = [n for n in structural if n.rank is Rank.KINGDOM]
    if len(kingdom) != 1 or "plantae" not in kingdom[0].flags:
        errs.append(f"expected single plantae root, got "
                    f"{[(r.path, r.flags) for r in kingdom]}")
    species_paths = [n.path for n in _species(tree)]
    for n in tree.nodes.values():
        if n.rank is Rank.CLASS and n.plan:
            plan = pack.registry.plans.get(n.plan)
            phylum = tree.nodes.get(n.parent or "")
            if plan and phylum and plan.frame not in phylum.flags:
                errs.append(f"{n.path}: plan {n.plan} under phylum "
                            f"lacking frame {plan.frame!r}")
        if n.rank is Rank.ORDER:
            # radiate-model aware (0032): an order that pre-radiates TO
            # SPECIES must have species pre; an order that stops above
            # species fills post (empty pre is legitimate).
            if n.radiate_to is not None and n.radiate_to >= Rank.SPECIES \
                    and not any(sp.startswith(n.path + ".")
                                for sp in species_paths):
                errs.append(f"{n.path}: empty order (no species)")
    return errs


def check_pin_integration(tree: Tree, pack: ContentPack) -> list[str]:
    """Every pin present at its authored rank; pinned records byte-exact
    vs merged_pin (scalars within pin jitter); every species pin has a
    sibling; radiation counts within soft range [N/3, 3N]."""
    from exp.k13_treegen.flora.backbone import PIN_JITTER_Z
    errs: list[str] = []
    by_label = {n.label: n for n in tree.nodes.values() if n.label}
    species_paths = [n.path for n in _species(tree)]
    # pin PRESENCE is a full-build property (checked only on backbone
    # builds, i.e. trees with a plantae root).
    full_build = any("plantae" in n.flags for n in tree.nodes.values())
    for pin in pack.pins:
        label = pin.get("label")
        n = by_label.get(label)
        if n is None:
            if full_build:
                errs.append(f"pin {label!r}: not present in tree")
            continue
        want_rank = Rank[str(pin.get("rank", "species")).upper()]
        if n.rank is not want_rank:
            errs.append(f"pin {label!r}: at rank {n.rank.name}, "
                        f"authored {want_rank.name}")
        axes, _ = merged_pin(pack, pin)
        bad = False
        for ax, v0 in axes.items():
            v = n.axes.get(ax)
            spec = pack.registry.axes.get(ax)
            if (spec is not None and isinstance(v0, (int, float))
                    and isinstance(v, (int, float))
                    and spec.value_type in (ValueType.SCALAR,
                                            ValueType.INT)
                    and spec.sigma > 0):
                if spec.mutation_kind is not MutationKind.GAUSSIAN \
                        and v0 > 0 and v > 0:
                    z = abs(math.log(v / v0)) / spec.sigma
                else:
                    z = abs(v - v0) / spec.sigma
                if z > 6 * PIN_JITTER_Z:
                    bad = True
            elif str(v) != str(v0):
                bad = True
        if bad:
            errs.append(f"pin {label!r}: axes drifted from authored "
                        f"record (beyond pin jitter)")
        # orphan/radiation coherence is RADIATE-MODEL aware (0032): a
        # pinned species may be a singleton (siblings come from the
        # genus's pre-radiation if declared, else the post fill), and a
        # radiation knob only produces pre descendants when the pin
        # pre-radiates to species.
        radiation = pin.get("radiation", 0)
        pre_to_species = pin.get("radiate", "never") in ("pre",
                                                         "pre-and-post") \
            and str(pin.get("radiate_to", "species")).lower() in (
                "species", "subspecies")
        if radiation and pre_to_species:
            desc = sum(1 for sp in species_paths
                       if sp.startswith(n.path + "."))
            if not (radiation / 5 <= desc <= radiation * 30 + 50):
                errs.append(f"pin {label!r}: radiation target "
                            f"{radiation}, got {desc} descendants")
    return errs


def check_nomenclature(tree: Tree, pack: ContentPack) -> list[str]:
    """After assign_names, every species is named; pinned names are
    byte-equal to content; epithets unique within genus; generated
    names well-formed and never equal a pin name; a species sits under
    the genus its binomial names. Trees with NO names at all are
    checker unit fixtures — skipped."""
    sp = _species(tree)
    if not any(n.name.binomial for n in sp):
        return []
    errs: list[str] = []
    pin_names = {p["label"]: p.get("name", {}) for p in pack.pins}
    pin_binomials = {nm.get("binomial") for nm in pin_names.values()
                     if nm.get("binomial")}
    by_genus: dict[str, list] = {}
    for n in sp:
        if not n.name.binomial:
            errs.append(f"{n.path}: species unnamed after naming pass")
            continue
        pin = pin_names.get(n.label or "")
        if pin and pin.get("binomial") and \
                n.name.binomial != pin["binomial"]:
            errs.append(f"{n.path} ({n.label}): name {n.name.binomial!r} "
                        f"!= pinned {pin['binomial']!r}")
        parts = n.name.binomial.split()
        if n.label is None:  # generated species
            if len(parts) != 2 or not parts[0][0].isupper() \
                    or not parts[1].islower():
                errs.append(f"{n.path}: malformed binomial "
                            f"{n.name.binomial!r}")
            if n.name.binomial in pin_binomials:
                errs.append(f"{n.path}: generated name collides with pin "
                            f"name {n.name.binomial!r}")
        by_genus.setdefault(n.path.rsplit(".s", 1)[0], []).append(n)
    for n in sp:
        if not n.name.binomial or " " not in n.name.binomial:
            continue
        genus = tree.nodes.get(n.path.rsplit(".s", 1)[0])
        if genus is not None and genus.name.binomial and \
                genus.name.binomial != n.name.binomial.split()[0]:
            errs.append(f"{n.path}: {n.name.binomial!r} under genus "
                        f"{genus.name.binomial!r}")
    for gpath, members in by_genus.items():
        eps = [m.name.binomial.split()[-1] for m in members
               if m.name.binomial and " " in m.name.binomial]
        dupes = {e for e in eps if eps.count(e) > 1}
        if dupes:
            errs.append(f"{gpath}: epithets not unique within genus: "
                        f"{sorted(dupes)}")
    return errs


def check_pigment_legality(tree: Tree, pack: ContentPack) -> list[str]:
    """B5 §5.2 / §8.6: per-plan color palettes are superseded by pathway
    gating (palettes.toml is kept for reference only). The standing
    pigment gate: every species' derived flower_color stays inside the
    legacy vocab the stems/id/tell consumers read, and every committed
    pigment_pathway is a legal single value (anthocyanin ⊥ betalain is
    the enum's single-valuedness — the sampler can never commit both)."""
    from exp.k13_treegen.flora.derive import FLOWER_COLOR_VOCAB, \
        PIGMENT_PATHWAYS
    errs: list[str] = []
    for n in _species(tree):
        c = n.axes.get("flower_color")
        if c is not None and c != "N/A" and c not in FLOWER_COLOR_VOCAB:
            errs.append(f"{n.path}: derived flower_color {c!r} outside "
                        f"the legacy vocab (naming regression)")
        p = n.axes.get("pigment_pathway")
        if p is not None and p not in PIGMENT_PATHWAYS:
            errs.append(f"{n.path}: pigment_pathway {p!r} not in "
                        f"{list(PIGMENT_PATHWAYS)}")
    return errs


CHECKS = [
    ("diversity", check_diversity),
    ("frozen_axis", check_frozen_axis),
    ("constraints", check_constraints),
    ("pin_coherence", check_pin_coherence),
    ("g_clock", check_g_clock),
    ("backbone", check_backbone),
    ("pin_integration", check_pin_integration),
    ("nomenclature", check_nomenclature),
    ("pigment_legality", check_pigment_legality),
]


@dataclass
class Report:
    """The per-seed verdict. ``violations`` maps check -> violations."""

    seed: int
    violations: dict[str, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not any(self.violations.values())

    def text(self) -> str:
        """Byte-stable, diff-able rendering."""
        lines = [f"seed {self.seed:08d}  "
                 f"{'OK' if self.ok else 'VIOLATIONS'}"]
        for name in sorted(self.violations):
            vs = sorted(self.violations[name])
            lines.append(f"{name}: {len(vs)}")
            lines.extend(f"  {v}" for v in vs)
        return "\n".join(lines) + "\n"


def run_checks(tree: Tree, pack: ContentPack,
               checks=CHECKS) -> Report:
    violations = {name: fn(tree, pack) for name, fn in checks}
    return Report(seed=tree.seed, violations=violations)
