"""Flora master-seed / substream discipline — mirrors K13 seeding (contract
C3) with its own root persona, so flora draws never alias fauna draws.
"""

from kernel.hashrng import Stream

# Root persona for the whole flora tree-gen. Everything descends from this.
_ROOT_ENTITY = "k14"


def root_stream(seed: int) -> Stream:
    """The master stream for one flora tree-gen run."""
    return Stream(seed, _ROOT_ENTITY)


def stage_stream(seed: int, *path: str) -> Stream:
    """A stage substream, e.g. ``stage_stream(seed, "backbone")`` — keyed
    by (seed, "k14", path), deterministic and independent of every other
    stage."""
    s = root_stream(seed)
    for p in path:
        s = s.child(p)
    return s


def naming_stage(seed: int, round: int) -> Stream:
    """The nomenclature stream for one diffuse round (re-run per round)."""
    return stage_stream(seed, "naming", "round", str(round))
