"""Three-state cover over the complex.

Every patch (2-cell) is in exactly one of:
  UNREFINED — coarse L0 properties only; summonable.
  REFINED_UNOBSERVED — structured, never witnessed; subdivisible.
  OBSERVED — collapse records exist; terminal (immutable except by events).
"""

from __future__ import annotations

from enum import Enum, auto

from kernel.complex.cells import Complex


class CoverState(Enum):
    UNREFINED = auto()
    REFINED_UNOBSERVED = auto()
    OBSERVED = auto()


# Legal transition table — any pair not in this set raises.
_LEGAL_TRANSITIONS: set[tuple[CoverState, CoverState]] = {
    (CoverState.UNREFINED, CoverState.REFINED_UNOBSERVED),
    (CoverState.REFINED_UNOBSERVED, CoverState.OBSERVED),
    (CoverState.UNREFINED, CoverState.OBSERVED),
}


def transition(before: CoverState, after: CoverState) -> None:
    """Validate a state transition; raise ValueError if illegal.

    OBSERVED → anything is always illegal (terminal state).
    """
    if (before, after) not in _LEGAL_TRANSITIONS:
        raise ValueError(
            f"Illegal cover transition: {before.name} → {after.name}"
        )


# ---- topological forms of the prime directive --------------------------------


def summon_eligible(cells: set[str], cover: dict[str, CoverState]) -> bool:
    """A2 §1.2 prime directive, topological form.

    An open set is summon-eligible iff it contains no OBSERVED cells.
    """
    for cid in cells:
        if cover.get(cid) is CoverState.OBSERVED:
            return False
    return True


def latent_rot(
    constraint_cells: set[str],
    cover: dict[str, CoverState],
    min_measure: float,
    complex: Complex,
) -> bool:
    """A2 §1.2 crisp latent rot.

    True when the constraint set no longer intersects any UNREFINED open
    set of sufficient measure — the remaining unrefined measure in the set
    has dropped below `min_measure`.
    """
    unrefined_measure = 0.0
    for cid in constraint_cells:
        if cover.get(cid) is CoverState.UNREFINED:
            patch = complex.patch_at(cid)
            unrefined_measure += patch.measure
    return unrefined_measure < min_measure
