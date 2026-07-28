"""M0 — master-seed / substream discipline (integration contract C3).

One master seed; the substream tree mirrors the pipeline DAG. Every
independent random field gets its OWN ``child(context)`` — K1 draws are keyed
by (clock, index) only, so two fields drawn from the same stream at the same
coordinates are identical (kernel/hashrng conflict-log lesson).

Stage-boundary replay: re-running a later stage (e.g. ``naming.round.r``) from
a committed tree is deterministic and independent of earlier stages' draws,
because each stage stream is keyed by (seed, stage-path) alone.
"""

from __future__ import annotations

from kernel.hashrng import Stream

# Root persona for the whole tree-gen. Everything descends from this.
_ROOT_ENTITY = "k13"


def root_stream(seed: int) -> Stream:
    """The master stream for one tree-gen run."""
    return Stream(seed, _ROOT_ENTITY)


def stage_stream(seed: int, *path: str) -> Stream:
    """A stage substream, e.g. ``stage_stream(seed, "naming", "round", "0")``.

    Chains ``child()`` along *path* from the root, so the stream is keyed by
    (seed, "naming|round|0") — deterministic and independent of every other
    stage. Modules build their lineage substreams beneath a stage stream.
    """
    s = root_stream(seed)
    for p in path:
        s = s.child(p)
    return s


# Canonical stage paths (documentation + convenience). The backbone builds its
# phylum/class/order/family/genus/species substreams beneath "backbone"; pins,
# per-world weak bindings, and each naming round get their own top-level stage.
STAGE_BACKBONE = ("backbone",)
STAGE_PINS = ("pins",)
STAGE_WEAK_BINDINGS = ("couplings", "weakbind")


def naming_stage(seed: int, round: int) -> Stream:
    """The nomenclature stream for one diffuse round (re-run per round)."""
    return stage_stream(seed, "naming", "round", str(round))
