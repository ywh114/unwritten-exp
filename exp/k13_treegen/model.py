"""M0 — record model and state contracts (integration contract C2).

This module is FROZEN once M1 starts: every other module imports these types
and signs them. It defines the ``Tree``/``Node`` records, the RFC §11
quantity-layer store (reserved so ranges/flags/ghosts/scores/ley-energy land
later with no schema migration), the reserved name record (M8 seam) and
lineage provenance (ley-lift seam), and the generic-rebind primitive (one
mechanism, two permission levels).

Slots are coordinate-less string enums (parts/slots as full records are
deferred to the illustration layer); generics map generic -> realization id.

Post-freeze amendment (2026-07-31): Rank.SUBSPECIES added below SPECIES for
the sim era — a real, committed divide that is deliberately rare (see
interface.py: the parse's narrow-band rule).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import IntEnum


class Rank(IntEnum):
    KINGDOM = 0
    PHYLUM = 1
    CLASS = 2
    ORDER = 3
    FAMILY = 4
    GENUS = 5
    SPECIES = 6
    SUBSPECIES = 7        # sim-era divide (see interface.py): real but rare


RANK_PREFIX = {
    Rank.KINGDOM: "k",
    Rank.PHYLUM: "p",
    Rank.CLASS: "c",
    Rank.ORDER: "o",
    Rank.FAMILY: "f",
    Rank.GENUS: "g",
    Rank.SPECIES: "s",
    Rank.SUBSPECIES: "ss",
}


# ──  quantity-layer store (RFC §11)  ──────────────────────────────────────


@dataclass(frozen=True)
class Quantity:
    """One ``(location, metric) -> value`` entry, stamped with provenance and
    round. The subject is the owning node. Flags are quantities with value in
    {0, 1}."""

    location: str          # "" for non-spatial metrics (all of v2)
    metric: str            # namespaced string; new mechanics = new keys
    value: float
    provenance: str = ""
    round: int = 0

    def to_json(self) -> dict:
        return {"location": self.location, "metric": self.metric,
                "value": self.value, "provenance": self.provenance,
                "round": self.round}

    @classmethod
    def from_json(cls, d: dict) -> "Quantity":
        return cls(location=d["location"], metric=d["metric"],
                   value=d["value"], provenance=d.get("provenance", ""),
                   round=d.get("round", 0))


class QuantityStore:
    """The RFC §11 store: ``(location, metric) -> Quantity`` with one
    interface (get/set/accumulate/expire) for every future consumer — field
    guide, renderer, gossip, validators, audit. New mechanics are new metric
    keys; there are never migrations.

    This is the critical deferred-feature reservation: v2 is world-blind so
    the store is empty, but the field + interface exist now so ranges, ghost
    ranges, scores, and ley-energy terms land later without touching the
    record schema.
    """

    __slots__ = ("_d",)

    def __init__(self) -> None:
        self._d: dict[tuple[str, str], Quantity] = {}

    def set(self, location: str, metric: str, value: float,
            provenance: str = "", round: int = 0) -> None:
        self._d[(location, metric)] = Quantity(location, metric, value,
                                               provenance, round)

    def get(self, location: str, metric: str) -> Quantity | None:
        return self._d.get((location, metric))

    def value(self, location: str, metric: str, default: float = 0.0) -> float:
        q = self._d.get((location, metric))
        return q.value if q is not None else default

    def accumulate(self, location: str, metric: str, delta: float,
                   provenance: str = "", round: int = 0) -> None:
        """Add *delta* to the current value (0 if absent)."""
        cur = self.value(location, metric)
        self.set(location, metric, cur + delta, provenance, round)

    def expire(self, before_round: int) -> int:
        """Drop every entry with round < before_round; return the count
        removed. Stale layers age out; the committed record does not."""
        stale = [k for k, q in self._d.items() if q.round < before_round]
        for k in stale:
            del self._d[k]
        return len(stale)

    def items(self):
        return self._d.values()

    def __len__(self) -> int:
        return len(self._d)

    def to_json(self) -> list[dict]:
        # sorted for canonical, byte-stable serialization
        return [q.to_json() for q in sorted(
            self._d.values(), key=lambda q: (q.location, q.metric))]

    @classmethod
    def from_json(cls, entries: list[dict]) -> "QuantityStore":
        s = cls()
        for e in entries:
            s.set(e["location"], e["metric"], e["value"],
                  e.get("provenance", ""), e.get("round", 0))
        return s


# ──  name record (M8 seam)  ───────────────────────────────────────────────


@dataclass
class NameRecord:
    """A species' name. ``binomial`` is the M8 output; ``folk`` is reserved
    (null) for the deferred folk-name layer; ``history`` accumulates the
    tentative name at each nomenclature pass (reference only — the committed
    name is the final-round one). Nothing here is committed before treegen
    finishes; names are immutable once committed."""

    binomial: str | None = None
    folk: str | None = None
    history: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"binomial": self.binomial, "folk": self.folk,
                "history": list(self.history)}

    @classmethod
    def from_json(cls, d: dict) -> "NameRecord":
        return cls(binomial=d.get("binomial"), folk=d.get("folk"),
                   history=list(d.get("history", [])))


# ──  lineage provenance (ley-lift seam)  ─────────────────────────────────


@dataclass
class Provenance:
    """Lineage origin. ``regular`` for backbone lineages; ``lifted`` (ley,
    out of v2 scope) records the sampling event per Fauna RFC §6.2 —
    (source species, site, round)."""

    kind: str = "regular"            # "regular" | "lifted"
    source_id: str | None = None
    site_id: str | None = None
    round: int | None = None

    def to_json(self) -> dict:
        if self.kind == "regular":
            return {"kind": "regular"}
        return {"kind": "lifted", "source_id": self.source_id,
                "site_id": self.site_id, "round": self.round}

    @classmethod
    def from_json(cls, d: dict) -> "Provenance":
        return cls(kind=d.get("kind", "regular"),
                   source_id=d.get("source_id"), site_id=d.get("site_id"),
                   round=d.get("round"))


# ──  node  ────────────────────────────────────────────────────────────────


@dataclass
class Node:
    """One committed taxonomic record (kingdom..species).

    Identity: ``path`` (integer tree handle, human-readable) + ``sid``
    (K1 hash-stable id). ``axes`` holds every plan-scoped AxisSpec value
    (M1); ``generics`` maps generic -> realization id; ``flags`` are simple
    committed tags (e.g. "pinned", a kingdom frame); ``quantities`` is the
    RFC §11 store for valued/located/round-stamped data.
    """

    path: str
    rank: Rank
    parent: str | None              # parent path; None for kingdom roots
    sid: str                        # K1 hash-stable id (16 hex chars)
    plan: str | None = None         # body plan, committed at CLASS
    preset: str | None = None       # preset id, committed at ORDER
    label: str | None = None        # curated label; pins only
    g: float = 0.0                  # genetic distance from founder (generations)
    gen_time: float = 0.0           # years per generation (g-clock rate)
    axes: dict = field(default_factory=dict)
    generics: dict = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)
    edge_delta: dict = field(default_factory=dict)
    name: NameRecord = field(default_factory=NameRecord)
    description: str = ""               # M12 one-liner (species, set at gen)
    provenance: Provenance = field(default_factory=Provenance)
    quantities: QuantityStore = field(default_factory=QuantityStore)

    def to_json(self) -> dict:
        return {
            "path": self.path,
            "rank": self.rank.name.lower(),
            "parent": self.parent,
            "sid": self.sid,
            "plan": self.plan,
            "preset": self.preset,
            "label": self.label,
            "g": self.g,
            "gen_time": self.gen_time,
            "axes": self.axes,
            "generics": self.generics,
            "flags": self.flags,
            "edge_delta": self.edge_delta,
            "name": self.name.to_json(),
            "description": self.description,
            "provenance": self.provenance.to_json(),
            "quantities": self.quantities.to_json(),
        }

    @classmethod
    def from_json(cls, d: dict) -> "Node":
        return cls(
            path=d["path"], rank=Rank[d["rank"].upper()], parent=d["parent"],
            sid=d["sid"], plan=d.get("plan"), preset=d.get("preset"),
            label=d.get("label"), g=d.get("g", 0.0),
            gen_time=d.get("gen_time", 0.0), axes=dict(d.get("axes", {})),
            generics=dict(d.get("generics", {})),
            flags=list(d.get("flags", [])),
            edge_delta=dict(d.get("edge_delta", {})),
            name=NameRecord.from_json(d.get("name", {})),
            description=d.get("description", ""),
            provenance=Provenance.from_json(d.get("provenance", {})),
            quantities=QuantityStore.from_json(d.get("quantities", [])),
        )


# ──  tree  ────────────────────────────────────────────────────────────────


@dataclass
class Tree:
    """The accumulating tree. ``nodes`` is keyed by path; ``meta`` carries
    seed + generator provenance + counts."""

    seed: int
    nodes: dict[str, Node] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def add(self, node: Node) -> None:
        if node.path in self.nodes:
            raise ValueError(f"duplicate path {node.path}")
        self.nodes[node.path] = node

    def children(self, path: str) -> list[Node]:
        return sorted((n for n in self.nodes.values() if n.parent == path),
                      key=lambda n: n.path)

    def roots(self) -> list[Node]:
        return sorted((n for n in self.nodes.values() if n.parent is None),
                      key=lambda n: n.path)

    def to_json(self) -> dict:
        counts: dict[str, int] = {}
        for n in self.nodes.values():
            counts[n.rank.name.lower()] = counts.get(n.rank.name.lower(), 0) + 1
        meta = {"seed": self.seed, "generator": "k13_treegen", "version": 2,
                "counts": counts, **self.meta}
        return {"meta": meta,
                "nodes": [self.nodes[p].to_json() for p in sorted(self.nodes)]}

    @classmethod
    def from_json(cls, d: dict) -> "Tree":
        meta = dict(d.get("meta", {}))
        seed = meta.pop("seed", 0)
        t = cls(seed=seed, meta=meta)
        for nd in d["nodes"]:
            t.add(Node.from_json(nd))
        return t

    def dumps(self) -> str:
        """Canonical serialization: sorted keys — byte-stable across runs."""
        return json.dumps(self.to_json(), indent=1, sort_keys=True) + "\n"


# ──  generic rebind (one mechanism, two permission levels)  ──────────────


class RebindError(Exception):
    """A regular rebind that the plan's permission table does not allow."""


def rebind(generics: dict, generic: str, realization: str,
           permissions: dict, force: bool = False) -> None:
    """Bind ``generic -> realization`` in *generics* (mutated in place).

    *permissions* maps each generic to the iterable of realizations legal on
    this plan. Regular evolution rebinds within plan limits: an unknown
    generic or an illegal realization raises ``RebindError``. Ley operators
    rebind across plan limits with ``force=True`` (Fauna RFC §2: one
    mechanism, two permission levels).
    """
    if force:
        generics[generic] = realization
        return
    allowed = permissions.get(generic)
    if allowed is None:
        raise RebindError(f"generic {generic!r} is not bindable on this plan")
    if realization not in allowed:
        raise RebindError(
            f"realization {realization!r} not allowed for generic "
            f"{generic!r} on this plan")
    generics[generic] = realization
