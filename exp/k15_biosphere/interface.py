"""Kingdom-neutral hook contract for the K15 biosphere rewrite (ticket 0035).

Owner ruling 2026-08-04: flora and fauna share the same general mechanisms —
stress response / backprop onto traits through derived views, biomass density
fields, capacity accounting.  They differ ONLY via kingdom-specific hooks the
general mechanism calls; to the sim both kingdoms present an IDENTICAL
interface.  General mechanisms are therefore written ONCE against
``OrganismHooks`` (this module); ``flora/`` and ``fauna/`` provide hook
implementations — never parallel machinery.

Anticipated hook surface (docstring contract only — implement each as it
lands, no stubs here):
    percap_biomass      (landed)  per-individual dry biomass, kg
    stress_response     kingdom-specific env stress → trait backprop
    dispersal_emission  what this lineage emits to neighbors
    vital_rates         growth / mortality / production rates
    provision           what the organism offers the food web

Downstream contract (owner 2026-08-04): the canonical sim output is the
per-cell, per-lineage BIOMASS DENSITY FIELD, whose first-class consumer is
the game layer: L1 (regional, lazy generation on approach/observation,
promise-constrained) and L2 (chunk render tier) read it to decide spawn
probability, location and amount.  Resolution schema: sim cells are
4 km × 4 km at 256² today; delivery is 1 km × 1 km at 1024²; a post-upscale
diffusion pass is planned and will be functional, not cosmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol


@dataclass
class MassEstimate:
    """Dry per-individual biomass (kg).

    ``total_kg``: dry, incl. belowground; ``agb_kg``: aboveground dry.
    ``proportions``: per-group intermediates (dbh_m, crown_dbh_ratio,
    root_shoot, sward_kg_m2, …) for the future proportion-deviation
    penalty hook (ticket 0035 owner note).
    """

    total_kg: float
    agb_kg: float
    proportions: dict[str, float]


class OrganismHooks(Protocol):
    """Kingdom hook contract — the identical interface both kingdoms present.

    A hook implementation (flora/ or fauna/) exposes one method per landed
    hook; only ``percap_biomass`` is implemented today (see
    ``flora.mass.percap_biomass``, a module-level function with the same
    call signature — lock v1.1).
    """

    def percap_biomass(
        self,
        axes: Mapping[str, float],
        plan: str,
        form: str | None = None,
    ) -> MassEstimate:
        """Per-individual dry biomass (kg) for *plan* given *axes*.

        Signature matches ``flora.mass.percap_biomass`` exactly.
        """
        ...
