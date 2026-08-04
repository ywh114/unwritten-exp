"""Phase 1b reality-check harness for per-capita biomass (ticket 0035).

Scales per-individual masses to landscape fluxes (t/ha or kg/m²) with the
per-case density model, then checks each against the published range locked
in CASES.  Density models (the ``density`` field of each case):

    "closure"              10_000 / footprint individuals per ha (crown closure)
    "full_cover"           1 / footprint individuals per m² (ground fully covered)
    ("cover_fraction", f)  f / footprint individuals per m²
    float                  fixed individuals per m²

Run:  PYTHONPATH=. uv run python -m exp.k15_biosphere.reality
"""

from __future__ import annotations

from exp.k15_biosphere.mass import footprint_m2, percap_biomass

CASES = [
    dict(
        name="oak_beech_stand",
        plan="tree", form="broadleaf",
        axes=dict(height_m=25.0, crown_spread_m=12.0, wood_density=0.6, woodiness=1.0),
        density="closure", basis="agb",
        lo=150.0, hi=400.0, unit="t/ha",
        source="old-growth temperate broadleaf to ~479 t/ha; Chave 2014 AGB at crown closure",
    ),
    dict(
        name="rainforest_stand",
        plan="tree", form="tropical",
        axes=dict(height_m=35.0, crown_spread_m=15.0, wood_density=0.55, woodiness=1.0),
        density="closure", basis="agb",
        lo=200.0, hi=450.0, unit="t/ha",
        source="IPCC Tier-1 ~300 t/ha for tropical rainforest",
    ),
    dict(
        name="taiga_stand",
        plan="tree", form="conifer",
        axes=dict(height_m=18.0, crown_spread_m=3.0, wood_density=0.45, woodiness=1.0),
        density="closure", basis="agb",
        lo=15.0, hi=100.0, unit="t/ha",
        source="IPCC ~50 t/ha for managed boreal conifer",
    ),
    dict(
        name="pasture_sward",
        plan="grass_sward",
        axes=dict(height_m=0.3, crown_spread_m=0.0),
        density="full_cover", basis="agb",
        lo=0.08, hi=0.93, unit="kg/m2",
        source="Gill 2002 peak aboveground standing crop range",
    ),
    dict(
        name="kelp_bed",
        plan="macroalgae_holdfast",
        axes=dict(height_m=20.0, crown_spread_m=0.0),
        density=0.3, basis="total",
        lo=0.1, hi=0.6, unit="kg/m2",
        source="typical giant-kelp bed dry biomass ~0.4 kg/m²",
    ),
    dict(
        name="sphagnum_bog",
        plan="moss_grade",
        axes=dict(height_m=0.1, crown_spread_m=0.0),
        density="full_cover", basis="total",
        lo=0.2, hi=1.5, unit="kg/m2",
        source="Sphagnum carpets 0.2–1.5 kg/m²",
    ),
    dict(
        name="sagebrush_steppe",
        plan="shrub",
        axes=dict(height_m=1.5, crown_spread_m=2.0, woodiness=0.35),
        density=("cover_fraction", 0.3), basis="agb",
        lo=0.08, hi=0.45, unit="kg/m2",
        source="sagebrush steppe at 30% ground cover",
    ),
    dict(
        name="seagrass_meadow",
        plan="runner_meadow",
        axes=dict(height_m=0.8, crown_spread_m=0.0, medium="water"),
        density="full_cover", basis="total",
        lo=0.2, hi=1.5, unit="kg/m2",
        source="Serrano 2016 seagrass totals incl. belowground (folded)",
    ),
]


def _density_per_unit(case: dict, footprint: float) -> float:
    """Individuals per unit area: per m², except "closure" which is per ha."""
    model = case["density"]
    if model == "closure":
        return 10000.0 / footprint
    if model == "full_cover":
        return 1.0 / footprint
    if isinstance(model, tuple) and model[0] == "cover_fraction":
        return model[1] / footprint
    if isinstance(model, (int, float)):
        return float(model)
    raise ValueError(f"unknown density model {model!r} in case {case['name']!r}")


def evaluate() -> list[dict]:
    """Compute every case; returns dicts (name, computed, unit, lo, hi, ok)."""
    results = []
    for case in CASES:
        est = percap_biomass(case["axes"], case["plan"], case.get("form"))
        fp = footprint_m2(case["axes"], case["plan"])
        density = _density_per_unit(case, fp)
        mass_kg = est.total_kg if case["basis"] == "total" else est.agb_kg
        if case["unit"] == "t/ha":
            computed = mass_kg * density / 1000.0
        else:
            computed = mass_kg * density
        ok = case["lo"] <= computed <= case["hi"]
        results.append(
            dict(
                name=case["name"], computed=computed, unit=case["unit"],
                lo=case["lo"], hi=case["hi"], ok=ok,
            )
        )
    return results


def main() -> None:
    print(f"{'case':<18s} {'computed':>10s} {'unit':<5s} "
          f"{'range':>22s}  result")
    for r in evaluate():
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"{r['name']:<18s} {r['computed']:>10.4f} {r['unit']:<5s} "
              f"[{r['lo']:>8.3f}, {r['hi']:>8.3f}] {r['unit']:<5s}  {mark}")


if __name__ == "__main__":
    main()
