"""K5 — the minimal predicate vocabulary.

10 kinds covering ~20 canonical political facts.  The design constraint:
enough to express the scripted-fixture scenarios and the conflicts they
generate, but not a byte more — "a database with opinions," not Prolog
(lab spec §2, K5).  Each kind name is the verb that will appear in
human-readable chronicle lines and debug outputs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PredicateKind(StrEnum):
    OWNS = "owns"           # entity owns a resource
    CONTROLS = "controls"   # entity controls a region
    IS = "is"               # entity has a status  (detail: dead, ruler, heir, banished, …)
    FEALTY = "fealty"       # vassal owes fealty to liege
    HOSTILE = "hostile"     # entity/faction hostile to another
    ALLIED = "allied"       # entity/faction allied to another
    LOCATED = "located"     # entity is located in a region
    DISPUTED = "disputed"   # a region is disputed (detail names contenders)
    BOUND = "bound"         # entity bound by an oath  (detail: marriage, treaty, …)
    HOLDS = "holds"         # entity holds a title or office


@dataclass(frozen=True, order=True)
class Predicate:
    """A single ground fact: <subject> <kind> <object> [detail].

    All fields are resource/entity/region slugs — string handles that the
    wiki store and orchestrator tools resolve, never free text.
    """

    kind: PredicateKind
    subject: str
    object: str = ""
    detail: str = ""

    def narrative(self) -> str:
        """One-line human-readable rendering for chronicle / debug output."""
        parts = [self.subject, self.kind.value]
        if self.object:
            parts.append(self.object)
        if self.detail:
            parts.append(f"[{self.detail}]")
        return " ".join(parts)
