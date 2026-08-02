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

from exp.k13_treegen.registry import Registry


@dataclass
class ContentPack:
    """The validated flora content pack: registry + presets + pins + ..."""

    registry: Registry
    presets: dict[str, dict] = field(default_factory=dict)  # preset_id -> toml
    pins: list[dict] = field(default_factory=list)          # [[pin]] tables
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


def is_bundle(pin: dict) -> bool:
    """Content-level bundle-track flag (0012 Task A). A bundle is an
    authored archetype SUPERSET generalist (one plan+layer, wide
    tolerances, central optima, archetypal enums) — frozen in the sim
    and differentiated post-sim by 0027. The flag is a plain data field
    on the [[pin]] table (`bundle = true`); the machinery ignores it
    except where a caller asks. Absence (or false) = individual track."""
    return bool(pin.get("bundle"))


def bundle_region(pin: dict) -> str | None:
    """The bundle's covered-region note (free text; a coverage-audit
    input, never read by the engine)."""
    return pin.get("covered_region")


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
                       palettes=palettes, constraints=constraints,
                       stems=stems, budget=budget,
                       stress_response=stress_response)
