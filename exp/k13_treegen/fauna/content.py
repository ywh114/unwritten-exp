"""M2 — content loader. Assembles the authored TOML content pack into a
validated ``ContentPack``: the merged M1 registry (core + morphometric axes),
plans, presets, pins, and allometry constants.

The loader is the only place that knows the content/ directory layout;
everything downstream consumes ``ContentPack``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from exp.k13_treegen.registry import Registry


@dataclass
class ContentPack:
    """The validated content pack: registry + presets + pins + allometry."""

    registry: Registry
    presets: dict[str, dict] = field(default_factory=dict)  # preset_id -> toml
    pins: list[dict] = field(default_factory=list)          # [[pin]] tables
    allometry: dict = field(default_factory=dict)
    palettes: dict[str, list[str]] = field(default_factory=dict)  # plan -> colors
    budget: dict = field(default_factory=dict)  # pins.toml [budget] table
    couplings: list = field(default_factory=list)  # M6 Rule records
    stems: dict = field(default_factory=dict)  # M8 stems.toml, raw tables

    def preset(self, preset_id: str) -> dict:
        return self.presets[preset_id]

    def preset_body_mass(self, preset_id: str) -> float | None:
        p = self.presets.get(preset_id)
        if not p:
            return None
        v = p.get("axes", {}).get("body_mass")
        return float(v) if isinstance(v, (int, float)) else None


# internal-organ + behavior defaults (RFC §2: every record carries the
# organ layer). Presets override only where interesting. wariness is a
# TRAIT (user ruling: it drifts with no predator pressure — deriving it
# from mass would pin it), default mid.
ORGAN_GENERIC_DEFAULTS = {
    "tetrapod": {"metabolism": "endotherm", "osmoreg": "standard"},
    "winged_biped": {"metabolism": "endotherm", "osmoreg": "standard"},
    "hexapod": {"metabolism": "ectotherm", "osmoreg": "standard"},
}
ORGAN_AXIS_DEFAULTS = {
    "blubber_thickness": 0.0, "radiator_extent": 0.05,
    "cooling_mode": "none", "torpor_mode": "none", "wariness": 0.5,
}


def merged_preset(pack: ContentPack, preset: dict) -> tuple[dict, dict]:
    """(axes, generics) for a preset with organ defaults filled. The ONE
    merge for presets — merged_pin builds on it, so does the backbone's
    order creation."""
    plan = preset.get("preset", {}).get("plan")
    axes = {**ORGAN_AXIS_DEFAULTS, **preset.get("knobs", {}),
            **preset.get("axes", {})}
    generics = {**ORGAN_GENERIC_DEFAULTS.get(plan, {}),
                **preset.get("generics", {})}
    return axes, generics


def merged_pin(pack: ContentPack, pin: dict) -> tuple[dict, dict]:
    """The pin's committed record: merged preset (with organ defaults)
    and pin overrides winning (pin > preset). The ONE merge — preview,
    backbone, and the pin-record metric all use this."""
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
    morph = _load_toml(d / "axes_morphometrics.toml")
    patt = _load_toml(d / "axes_patternation.toml")
    plans = _load_toml(d / "plans.toml")

    axis_defs = {**core.get("axis", {}), **morph.get("axis", {}),
                 **patt.get("axis", {})}
    registry = Registry.from_toml(axis_defs, plans.get("plan", {}))

    presets: dict[str, dict] = {}
    pdir = d / "presets"
    for f in sorted(pdir.rglob("*.toml")):
        pdata = _load_toml(f)
        presets[pdata["preset"]["id"]] = pdata

    pins_toml = _load_toml(d / "pins.toml")
    pins = pins_toml.get("pin", [])
    budget = pins_toml.get("budget", {})
    allometry = _load_toml(d / "allometry.toml")
    palettes = {plan: list(tbl.get("colors", []))
                for plan, tbl in _load_toml(d / "palettes.toml")
                .get("palette", {}).items()}

    from exp.k13_treegen.fauna.couplings import Rule
    couplings = [Rule.from_toml(t) for t in
                 _load_toml(d / "couplings.toml").get("rule", [])]

    stems = {**_load_toml(d / "stems.toml"),
             **_load_toml(d / "stems_authored.toml")}

    pack = ContentPack(registry=registry, presets=presets, pins=pins,
                       allometry=allometry, palettes=palettes, budget=budget,
                       couplings=couplings, stems=stems)
    return pack
