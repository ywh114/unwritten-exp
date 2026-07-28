"""M11 — metrics harness: the standing gate for generated trees.

Distinct from ``lint.py``: lint checks AUTHORED content, metrics checks
GENERATED output. A checker that cannot fail is decorative — every check
has a planted-violation meta-test in test_m11.py.

Checks consume ``(tree, pack)`` and return violation strings. The report is
byte-stable per seed: sorted checks, sorted violations, canonical counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from exp.k13_treegen.content import ContentPack
from exp.k13_treegen.lint import ACTIVE_FLIGHT, PIN_MASS_FACTOR
from exp.k13_treegen.model import Rank, Tree
from exp.k13_treegen.registry import ValueType

# diversity: a generated tree with <2 species or a single grade is the
# low-diversity failure shape (skeleton threshold; the real census lands
# with M7).
MIN_SPECIES = 2


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


def check_frozen_axis(tree: Tree, pack: ContentPack) -> list[str]:
    """A mutable axis that never varies across same-plan species is the v1
    freeze bug at tree level."""
    sp = _species(tree)
    errs: list[str] = []
    by_plan: dict[str, list] = {}
    for n in sp:
        by_plan.setdefault(n.plan or "?", []).append(n)
    for plan, nodes in sorted(by_plan.items()):
        if len(nodes) < 2:
            continue
        present = set.intersection(*(set(n.axes) for n in nodes)) \
            if nodes else set()
        for ax in sorted(present):
            spec = pack.registry.axes.get(ax)
            if spec is None or not spec.mutable:
                continue
            # sub-quantum int axes (sigma < one step) cannot move under
            # gentle gaussian mutation regardless of machinery — that is
            # discreteness arithmetic, not the v1 whitelisting bug this
            # check exists to catch.
            if spec.value_type is ValueType.INT and spec.sigma < 0.5:
                continue
            vals = {str(n.axes[ax]) for n in nodes}
            if len(vals) <= 1:
                errs.append(f"plan {plan}: axis {ax} frozen at "
                            f"{next(iter(vals))!r} across {len(nodes)} "
                            f"species")
    return errs


def check_coupling_breach(tree: Tree, pack: ContentPack) -> list[str]:
    """Committed-record coherence: a flightless preset must never carry an
    active-flight flight_style in the tree."""
    errs: list[str] = []
    for n in tree.nodes.values():
        if not n.preset:
            continue
        p = pack.presets.get(n.preset)
        if not p:
            continue
        preset_fs = p.get("knobs", {}).get("flight_style")
        node_fs = n.axes.get("flight_style")
        if preset_fs == "flightless" and node_fs in ACTIVE_FLIGHT:
            errs.append(f"{n.path}: flightless preset {n.preset!r} "
                        f"committed to active flight {node_fs!r}")
    return errs


def check_pin_coherence(tree: Tree, pack: ContentPack) -> list[str]:
    """Crocodile-on-monkey class: a pinned node's mass must stay within
    grade magnitude of its preset."""
    errs: list[str] = []
    for n in tree.nodes.values():
        if "pinned" not in n.flags or not n.preset:
            continue
        preset_mass = pack.preset_body_mass(n.preset)
        node_mass = n.axes.get("body_mass")
        if (preset_mass and isinstance(node_mass, (int, float))
                and node_mass > 0):
            ratio = node_mass / preset_mass
            if ratio > PIN_MASS_FACTOR or ratio < 1.0 / PIN_MASS_FACTOR:
                errs.append(f"{n.path} ({n.label}): body_mass {node_mass} "
                            f"is {ratio:.0f}x preset {n.preset!r}")
    return errs


def check_g_clock(tree: Tree, pack: ContentPack) -> list[str]:
    """M5: g monotonic nondecreasing root->leaf; gen_time ordering
    (the heavy half of species must not run faster than the light half)."""
    errs: list[str] = []
    for n in tree.nodes.values():
        if n.parent and n.parent in tree.nodes:
            p = tree.nodes[n.parent]
            if n.g < p.g:
                errs.append(f"{n.path}: g {n.g} < parent g {p.g} "
                            f"(clock runs backward)")
    sp = [n for n in _species(tree)
          if isinstance(n.axes.get("body_mass"), (int, float))
          and n.gen_time > 0]
    if len(sp) >= 2:
        masses = sorted(n.axes["body_mass"] for n in sp)
        mid = masses[len(masses) // 2]
        heavy = [n.gen_time for n in sp if n.axes["body_mass"] >= mid]
        light = [n.gen_time for n in sp if n.axes["body_mass"] < mid]
        if heavy and light:
            med = lambda v: sorted(v)[len(v) // 2]
            if med(heavy) < med(light):
                errs.append("gen_time ordering inverted: heavy species "
                            "run faster than light ones")
    return errs


def check_backbone(tree: Tree, pack: ContentPack) -> list[str]:
    """M7: single animalia kingdom root; authored frame map enforced
    (each plan's class under a phylum carrying the plan's frame flag);
    no empty orders. Structural checks apply only when the tree HAS
    structure (species-only synthetic trees are checker unit fixtures)."""
    errs: list[str] = []
    structural = [n for n in tree.nodes.values()
                  if n.rank is not Rank.SPECIES]
    if not structural:
        return errs
    kingdom = [n for n in structural if n.rank is Rank.KINGDOM]
    if len(kingdom) != 1 or "animalia" not in kingdom[0].flags:
        errs.append(f"expected single animalia root, got "
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
            if not any(sp.startswith(n.path + ".") for sp in species_paths):
                errs.append(f"{n.path}: empty order (no species)")
    return errs


def check_pin_integration(tree: Tree, pack: ContentPack) -> list[str]:
    """M7/M4: every pin present at its authored rank; pinned records
    byte-exact vs merged_pin; every species pin has a sibling; radiation
    counts within soft range [N/3, 3N]."""
    from exp.k13_treegen.content import merged_pin
    errs: list[str] = []
    by_label = {n.label: n for n in tree.nodes.values() if n.label}
    species_paths = [n.path for n in _species(tree)]
    # pin PRESENCE is a full-build property (checked only on backbone
    # builds, i.e. trees with an animalia root); correctness of present
    # pins is checked always.
    full_build = any("animalia" in n.flags for n in tree.nodes.values())
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
        axes, generics = merged_pin(pack, pin)
        if {k: str(v) for k, v in n.axes.items()} != \
                {k: str(v) for k, v in axes.items()}:
            errs.append(f"pin {label!r}: axes drifted from authored "
                        f"record (must be byte-exact)")
        if n.rank is Rank.SPECIES:
            siblings = [sp for sp in species_paths
                        if sp.rsplit(".s", 1)[0] ==
                        n.path.rsplit(".s", 1)[0] and sp != n.path]
            if not siblings:
                errs.append(f"pin {label!r}: orphan species (no sibling "
                            f"in its genus)")
        radiation = pin.get("radiation", 0)
        if radiation:
            desc = sum(1 for sp in species_paths
                       if sp.startswith(n.path + "."))
            if not (radiation / 3 <= desc <= radiation * 3):
                errs.append(f"pin {label!r}: radiation target "
                            f"{radiation}, got {desc} descendants")
    return errs


def check_nomenclature(tree: Tree, pack: ContentPack) -> list[str]:
    """M8: after assign_names, every species is named; pinned names are
    byte-equal to content; epithets unique within genus (cross-genus
    repeats allowed); generated names well-formed and never equal a pin
    name. Trees with NO names at all are checker unit fixtures — skipped
    (naming is a separate pass)."""
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
    for gpath, members in by_genus.items():
        eps = [m.name.binomial.split()[-1] for m in members
               if m.name.binomial and " " in m.name.binomial]
        dupes = {e for e in eps if eps.count(e) > 1}
        if dupes:
            errs.append(f"{gpath}: epithets not unique within genus: "
                        f"{sorted(dupes)}")
    return errs


def check_palette_legality(tree: Tree, pack: ContentPack) -> list[str]:
    """M3 at tree level: the SAMPLER must respect palettes too — no
    generated species outside its plan palette (+ preset extras)."""
    errs: list[str] = []
    color_axes = ("base_color", "belly_color", "accent_color")
    for n in _species(tree):
        legal = pack.palettes.get(n.plan or "", [])
        preset = pack.presets.get(n.preset or "", {})
        legal = legal + list(preset.get("preset", {})
                             .get("palette_extra", []))
        for ax in color_axes:
            c = n.axes.get(ax)
            if c is not None and c != "N/A" and c not in legal:
                errs.append(f"{n.path}: {ax} {c!r} outside {n.plan} "
                            f"palette (sampler legality)")
    return errs


CHECKS = [
    ("diversity", check_diversity),
    ("frozen_axis", check_frozen_axis),
    ("coupling_breach", check_coupling_breach),
    ("pin_coherence", check_pin_coherence),
    ("g_clock", check_g_clock),
    ("backbone", check_backbone),
    ("pin_integration", check_pin_integration),
    ("nomenclature", check_nomenclature),
    ("palette_legality", check_palette_legality),
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
