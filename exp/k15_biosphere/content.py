"""Flora content pack loader for the K15 biosphere rewrite (ticket 0041;
spec B9 §2).

Reads the settled flora content pack IN PLACE from the k13 treegen
content directory (``exp/k13_treegen/content/flora/`` — content is shared
data, never copied) and validates it against the ported registry
(``exp/k15_biosphere/registry.py``): the axis registry (axes_core.toml's
84 axes + plans.toml's 14 plans), presets/ (29 files), pins.toml,
bundles.toml, classes.toml.

The loader is the only place that knows the content/ directory layout;
everything downstream consumes ``ContentPack``.  Ported from the k13
loader (``exp/k13_treegen/flora/content.py``) and adapted: validation
raises ``ContentError`` (never bare asserts — asserts vanish under
``-O``), and only the tables above are in this ticket's scope — palettes,
constraint rules, stems, stress_response, and the stub scaffold belong to
later tickets' content.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from exp.k15_biosphere.registry import Registry, ValueType


class ContentError(Exception):
    """The content pack failed validation."""


@dataclass
class ContentPack:
    """The validated flora content pack: registry + presets + pins + ..."""

    registry: Registry
    presets: dict[str, dict] = field(default_factory=dict)  # preset_id -> toml
    pins: list[dict] = field(default_factory=list)          # [[pin]] tables
    bundles: list[dict] = field(default_factory=list)       # [[bundle]] tables
    classes: list[dict] = field(default_factory=list)       # [[class]] tables

    def preset(self, preset_id: str) -> dict:
        return self.presets[preset_id]


def merged_preset(preset: dict) -> tuple[dict, dict]:
    """(axes, generics) for a preset. Flora presets author every axis —
    no organ defaults layer. The climate envelope is a PURE DERIVED of
    these axes (B9 §2: derive.effective_climate — presets carry no
    [niche] table)."""
    axes = {**preset.get("knobs", {}), **preset.get("axes", {})}
    generics = dict(preset.get("generics", {}))
    return axes, generics


def merged_pin(pack: ContentPack, pin: dict) -> tuple[dict, dict]:
    """The pin's committed record: merged preset with pin overrides
    winning (pin > preset). The ONE merge — every consumer of a pin's
    committed traits uses this."""
    preset = pack.presets[pin["preset"]]
    paxes, pgenerics = merged_preset(preset)
    axes = {**paxes, **pin.get("knobs", {}), **pin.get("axes", {})}
    generics = {**pgenerics, **pin.get("generics", {})}
    return axes, generics


def _load_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def _content_error(path: str, msg: str) -> ContentError:
    return ContentError(f"{path}: {msg}")


def load_content(content_dir: str | Path) -> ContentPack:
    """Load and validate the flora content pack from *content_dir*."""
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
                raise _content_error(
                    str(f), "dispersal_channels is a pmf and must sum to "
                    f"1.0 (got {total:.4f}) — owner ruling 2026-08-01")
        try:
            pid = pdata["preset"]["id"]
        except KeyError:
            raise _content_error(
                str(f), "preset table missing id") from None
        presets[pid] = pdata

    pins = _load_toml(d / "pins.toml").get("pin", [])

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
            if not b.get(key):
                raise _content_error(
                    "bundles.toml", f"bundle missing {key!r}: {b!r}")
        if b["plan"] not in registry.plans:
            raise _content_error(
                "bundles.toml", f"{b['label']}: plan {b['plan']!r} "
                "not in registry")
        if b["layer"] not in registry.axes["layer"].states:
            raise _content_error(
                "bundles.toml", f"{b['label']}: layer {b['layer']!r} "
                "not legal")
        if not (isinstance(b["anchor_families"], list)
                and b["anchor_families"]
                and all(isinstance(f, str) and f
                        for f in b["anchor_families"])):
            raise _content_error(
                "bundles.toml", f"{b['label']}: anchor_families must be a "
                "non-empty list of strings")
        if not (isinstance(b["anchor_genera"], list) and b["anchor_genera"]
                and all(isinstance(g, str) and g
                        for g in b["anchor_genera"])):
            raise _content_error(
                "bundles.toml", f"{b['label']}: anchor_genera must be a "
                "non-empty list of strings")
        if b["label"] in seen_bundle_labels:
            raise _content_error(
                "bundles.toml", f"duplicate bundle label {b['label']!r}")
        seen_bundle_labels.add(b["label"])
        for ax, v in b["envelope"].items():
            spec = registry.axes.get(ax)
            if spec is None:
                continue  # non-registry axis: carried verbatim
            if spec.value_type is ValueType.ENUM:
                if str(v) == "none" and "none" not in spec.states:
                    continue  # the pre-existing spore/decomposer idiom
                if str(v) not in spec.states:
                    raise _content_error(
                        "bundles.toml", f"{b['label']}: {ax}={v!r} not in "
                        "registry states")
            elif spec.value_type in (ValueType.SCALAR, ValueType.INT):
                if not isinstance(v, (int, float)):
                    raise _content_error(
                        "bundles.toml", f"{b['label']}: {ax}={v!r} not "
                        "numeric")
                lo, hi = spec.bounds
                if not (lo <= float(v) <= hi):
                    raise _content_error(
                        "bundles.toml", f"{b['label']}: {ax}={v!r} out of "
                        f"bounds [{lo}, {hi}]")
            elif spec.value_type is ValueType.WEIGHTED_SET:
                total = sum(float(w) for w in v.values())
                if abs(total - 1.0) > 1e-6:
                    raise _content_error(
                        "bundles.toml", f"{b['label']}: {ax} is a pmf and "
                        f"must sum to 1.0 (got {total:.4f})")

    classes = _load_toml(d / "classes.toml").get("class", [])
    # class-table validation (open-catalog gate): every plan in the
    # registry appears in exactly one class; every class names real
    # plans; a class carries a phylum + name.
    seen: set[str] = set()
    for cls in classes:
        if not (cls.get("name") and cls.get("phylum") and cls.get("plans")):
            raise _content_error(
                "classes.toml", f"{cls!r} needs name/phylum/plans")
        for pid in cls["plans"]:
            if pid not in registry.plans:
                raise _content_error(
                    "classes.toml", f"plan {pid!r} not in the registry")
            if pid in seen:
                raise _content_error(
                    "classes.toml", f"plan {pid!r} in more than one class")
            seen.add(pid)
    for pid in registry.plans:
        if pid not in seen:
            raise _content_error(
                "classes.toml", f"plan {pid!r} has no class")

    return ContentPack(registry=registry, presets=presets, pins=pins,
                       bundles=bundles, classes=classes)
