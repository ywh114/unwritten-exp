"""C2 — shared pydantic schemas and village types (no circular deps).

The pydantic schemas are the exact ones from the task spec §pipeline.
`NPCCard`/`Village` are the library's world-state types; the demo's
`build_village` fixture (in exp/) constructs them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel


@dataclass
class NPCCard:
    """One villager card — compact, one-line state."""

    slug: str
    name: str
    role: str
    state: str
    dead: bool = False


@dataclass
class Village:
    """The world state the backfill pipeline reads and commits to."""

    npcs: list[NPCCard]
    counters: dict          # counter_name -> kernel.counters.Counter
    ledger: object          # kernel.promise_ledger.PromiseLedger
    wiki: object            # kernel.wiki_store.WikiStore
    dead_slugs: set[str]    # slugs of dead NPCs (resurrection trap)


class BackfillEvent(BaseModel):
    title: str                      # one dry line
    kind: Literal["death", "birth", "conflict", "economic",
                  "weather", "social", "discharge", "other"]
    involves: list[str]             # NPC slugs, may be empty
    promise_discharge: str | None   # promise id this event resolves


class CounterNote(BaseModel):
    counter: str
    direction: Literal["up", "down", "flat"]
    reason: str                     # why it moved (the narration)


class SeasonChronicle(BaseModel):
    events: list[BackfillEvent]     # EXACTLY k
    counter_notes: list[CounterNote]  # one per counter
    texture_line: str


@dataclass
class BackfillResult:
    events: list[BackfillEvent]
    discharges: list[str]           # promise ids discharged
    counter_anchors: dict[str, tuple[float, float, str]]
    # counter_name -> (v0, v1, direction)
    chronicle_text: str
    attempts: int
    accepted: bool
    violations_history: list[list[str]]
    cost_entries: list = field(default_factory=list)
