"""K14 naming glue — the K13 M8 nomenclature engine with the flora
plan->suffix-grade map and the k14 stream persona. Everything else
(salience, synonym chains, context stems, guaranteed naming) is the
shared engine.
"""

from __future__ import annotations

from exp.k13_treegen.nomenclature import NameContext  # noqa: F401
from exp.k13_treegen.nomenclature import assign_names as _assign
from exp.k14_flora.seeding import naming_stage

# plan -> genus_suffix table grades (stems_flora.toml authors tree /
# herb / grass / water / fungus grade tables with parallel genders).
PLAN_SUFFIX_GRADE = {
    "tree": ["tree"],
    "shrub": ["tree", "herb"],
    "herb_forb": ["herb"],
    "grass_sward": ["grass"],
    "rosette_mat": ["herb"],
    "succulent": ["herb"],
    "fern_grade": ["herb"],
    "moss_grade": ["herb"],
    "runner_meadow": ["water", "grass"],
    "floating_leaf": ["water"],
    "floater": ["water"],
    "macroalgae_holdfast": ["water"],
    "coral_grade": ["water"],
    "sponge_grade": ["water"],
    "fungus": ["fungus"],
    "lichen": ["fungus"],
}


def assign_names(tree, pack, seed: int, context: NameContext | None = None,
                 round: int = 0) -> None:
    """One naming pass over the flora tree (round 0 = the blind build)."""
    _assign(tree, pack, seed, context=context, round=round,
            plan_grades=PLAN_SUFFIX_GRADE,
            stage_stream=naming_stage(seed, round))
