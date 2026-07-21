"""K7 — wiki fact record.

Content-addressed immutable fact: id = SHA-256(text, provenance, valid_from)
truncated to 12 hex chars.  Trust ∈ [-1, 1] is the orchestrator's view
(world-POV), never a per-character belief.  Negative-trust facts are stored
verbatim — no inversion, no rewriting (a liar does not reliably speak the
exact opposite).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum


class FactState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class Fact:
    id: str
    text: str
    trust: float
    importance: str          # "critical" | "notable" | "minor"
    provenance: str          # K5-aligned: "measurement" | "canon" |
                             # "hard_orchestrator[:x]" | "soft_orchestrator[:x]" |
                             # "npc:slug" | "rumor:slug"
    valid_from: float
    valid_until: float | None   # None = still open
    state: FactState
    promise_id: str | None = None
    superseded_by: str | None = None


def _content_id(text: str, provenance: str, valid_from: float) -> str:
    """Content-addressed fact id — same content → same id always."""
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    h.update(provenance.encode("utf-8"))
    h.update(f"{valid_from:.12g}".encode("utf-8"))
    return h.hexdigest()[:12]


def make_fact(
    text: str,
    trust: float = 0.0,
    importance: str = "notable",
    provenance: str = "canon",
    valid_from: float = 0.0,
    **kwargs,
) -> Fact:
    """Create a Fact with a content-addressed id."""
    if not -1.0 <= trust <= 1.0:
        raise ValueError(f"trust must be in [-1, 1], got {trust}")
    fact = Fact(
        id=_content_id(text, provenance, valid_from),
        text=text,
        trust=trust,
        importance=importance,
        provenance=provenance,
        valid_from=valid_from,
        valid_until=kwargs.pop("valid_until", None),
        state=kwargs.pop("state", FactState.ACTIVE),
        promise_id=kwargs.pop("promise_id", None),
        superseded_by=kwargs.pop("superseded_by", None),
    )
    if kwargs:
        raise TypeError(f"unexpected keyword arguments: {sorted(kwargs)}")
    return fact


def close(fact: Fact, t: float, *, superseded_by: str | None = None) -> Fact:
    """Return an ARCHIVED copy closed at `t`."""
    return Fact(
        id=fact.id,
        text=fact.text,
        trust=fact.trust,
        importance=fact.importance,
        provenance=fact.provenance,
        valid_from=fact.valid_from,
        valid_until=t,
        state=FactState.ARCHIVED,
        promise_id=fact.promise_id,
        superseded_by=superseded_by,
    )
