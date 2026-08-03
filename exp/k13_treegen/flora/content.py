"""Flora content loader — mirrors K13 M2. Assembles the authored TOML
content pack into a validated ``ContentPack``: the M1 registry (core
axes + growth-form plans), presets, pins, palettes, constraint rules,
and nomenclature stems.

The loader is the only place that knows the content/ directory layout;
everything downstream consumes ``ContentPack``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from exp.k13_treegen.registry import Registry, ValueType


@dataclass
class ContentPack:
    """The validated flora content pack: registry + presets + pins + ..."""

    registry: Registry
    presets: dict[str, dict] = field(default_factory=dict)  # preset_id -> toml
    pins: list[dict] = field(default_factory=list)          # [[pin]] tables
    bundles: list[dict] = field(default_factory=list)       # [[bundle]] tables
    classes: list[dict] = field(default_factory=list)       # [[class]] tables
    palettes: dict[str, list[str]] = field(default_factory=dict)  # plan -> colors
    constraints: list = field(default_factory=list)         # Rule records
    stems: dict = field(default_factory=dict)  # stems_flora.toml, raw tables
    budget: dict = field(default_factory=dict)  # pins.toml [budget] table
    stress_response: dict[str, list] = field(default_factory=dict)
    # stress_response.toml: req_flora name -> responder rows (sim.select
    # dispatch; loaded the same way as every other authored table)

    def preset(self, preset_id: str) -> dict:
        return self.presets[preset_id]

    def preset_height(self, preset_id: str) -> float | None:
        """The size-axis anchor (flora's preset_body_mass equivalent)."""
        p = self.presets.get(preset_id)
        if not p:
            return None
        v = p.get("axes", {}).get("height_m")
        return float(v) if isinstance(v, (int, float)) else None


def merged_preset(pack: ContentPack, preset: dict) -> tuple[dict, dict]:
    """(axes, generics) for a preset. Flora presets author every axis —
    no organ defaults layer (interface parity with K13's merged_preset).
    The climate envelope is a PURE DERIVED of these axes (owner ruling
    2026-08-01: derive.effective_climate — the presets carry no [niche]
    table anymore)."""
    axes = {**preset.get("knobs", {}), **preset.get("axes", {})}
    generics = dict(preset.get("generics", {}))
    return axes, generics


def merged_pin(pack: ContentPack, pin: dict) -> tuple[dict, dict]:
    """The pin's committed record: merged preset with pin overrides
    winning (pin > preset). The ONE merge — preview, backbone, and the
    pin-record metric all use this."""
    preset = pack.presets[pin["preset"]]
    paxes, pgenerics = merged_preset(pack, preset)
    axes = {**paxes, **pin.get("knobs", {}), **pin.get("axes", {})}
    generics = {**pgenerics, **pin.get("generics", {})}
    return axes, generics


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def load_content(content_dir: str | Path) -> ContentPack:
    """Load and validate the content pack from *content_dir*."""
    d = Path(content_dir)
    core = _load_toml(d / "axes_core.toml")
    plans = _load_toml(d / "plans.toml")

    registry = Registry.from_toml(core.get("axis", {}),
                                  plans.get("plan", {}))

    presets: dict[str, dict] = {}
    pdir = d / "presets"
    for f in sorted(pdir.rglob("*.toml")):
        pdata = _load_toml(f)
        ch = pdata.get("axes", {}).get("dispersal_channels")
        if ch is not None:
            total = sum(float(v) for v in ch.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(
                    f"{f}: dispersal_channels is a pmf and must sum to "
                    f"1.0 (got {total:.4f}) — owner ruling 2026-08-01")
        presets[pdata["preset"]["id"]] = pdata

    pins_toml = _load_toml(d / "pins.toml")
    pins = pins_toml.get("pin", [])
    budget = pins_toml.get("budget", {})
    bundles = _load_toml(d / "bundles.toml").get("bundle", [])
    # bundle-table validation: each bundle is a region x physiology
    # archetype — a real plan, a legal layer, non-empty anchor-clade
    # lists, and an envelope whose known axes are legal (enums are
    # registry states, tolerances numeric in range; unknown axes are
    # carried verbatim — they are not part of the schema).
    seen_bundle_labels: set[str] = set()
    for b in bundles:
        for key in ("label", "covered_region", "plan", "layer", "envelope",
                    "anchor_families", "anchor_genera"):
            assert b.get(key), f"bundles.toml: bundle missing {key!r}: {b!r}"
        assert b["plan"] in registry.plans, \
            f"bundles.toml: {b['label']}: plan {b['plan']!r} not in registry"
        assert b["layer"] in registry.axes["layer"].states, \
            f"bundles.toml: {b['label']}: layer {b['layer']!r} not legal"
        assert isinstance(b["anchor_families"], list) and \
            b["anchor_families"] and \
            all(isinstance(f, str) and f for f in b["anchor_families"]), \
            f"bundles.toml: {b['label']}: anchor_families must be a " \
            f"non-empty list of strings"
        assert isinstance(b["anchor_genera"], list) and b["anchor_genera"] \
            and all(isinstance(g, str) and g for g in b["anchor_genera"]), \
            f"bundles.toml: {b['label']}: anchor_genera must be a " \
            f"non-empty list of strings"
        assert b["label"] not in seen_bundle_labels, \
            f"bundles.toml: duplicate bundle label {b['label']!r}"
        seen_bundle_labels.add(b["label"])
        for ax, v in b["envelope"].items():
            spec = registry.axes.get(ax)
            if spec is None:
                continue  # non-registry axis: carried verbatim
            if spec.value_type is ValueType.ENUM:
                if str(v) == "none" and "none" not in spec.states:
                    continue  # the pre-existing spore/decomposer idiom
                assert str(v) in spec.states, \
                    f"bundles.toml: {b['label']}: {ax}={v!r} not in " \
                    f"registry states"
            elif spec.value_type in (ValueType.SCALAR, ValueType.INT):
                assert isinstance(v, (int, float)), \
                    f"bundles.toml: {b['label']}: {ax}={v!r} not numeric"
                lo, hi = spec.bounds
                assert lo <= float(v) <= hi, \
                    f"bundles.toml: {b['label']}: {ax}={v!r} out of " \
                    f"bounds [{lo}, {hi}]"
            elif spec.value_type is ValueType.WEIGHTED_SET:
                total = sum(float(w) for w in v.values())
                assert abs(total - 1.0) <= 1e-6, \
                    f"bundles.toml: {b['label']}: {ax} is a pmf and must " \
                    f"sum to 1.0 (got {total:.4f})"
    classes = _load_toml(d / "classes.toml").get("class", [])
    # class-table validation (open-catalog gate): every plan in the
    # registry appears in exactly one class; every class names real
    # plans; a class carries a phylum + name.
    seen: set[str] = set()
    for cls in classes:
        assert cls.get("name") and cls.get("phylum") and cls.get("plans"), \
            f"classes.toml: {cls!r} needs name/phylum/plans"
        for pid in cls["plans"]:
            assert pid in registry.plans, \
                f"classes.toml: plan {pid!r} not in the registry"
            assert pid not in seen, \
                f"classes.toml: plan {pid!r} in more than one class"
            seen.add(pid)
    for pid in registry.plans:
        assert pid in seen, \
            f"classes.toml: plan {pid!r} has no class"
    palettes = {plan: list(tbl.get("colors", []))
                for plan, tbl in _load_toml(d / "palettes.toml")
                .get("palette", {}).items()}

    from exp.k13_treegen.flora.constraints import Rule
    constraints = [Rule.from_toml(t) for t in
                   _load_toml(d / "constraints.toml").get("rule", [])]

    stems = _load_toml(d / "stems_flora.toml")

    stress_response: dict[str, list] = {}
    for tbl in _load_toml(d / "stress_response.toml").get("responder", []):
        stress_response[tbl["name"]] = [dict(r) for r in
                                        tbl.get("responders", [])]

    return ContentPack(registry=registry, presets=presets, pins=pins,
                       bundles=bundles, classes=classes, palettes=palettes,
                       constraints=constraints, stems=stems, budget=budget,
                       stress_response=stress_response)
