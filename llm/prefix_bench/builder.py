"""L2 — PromptBuilder: the cache-discipline layout.

Prefix caching only pays when the prefix is *byte-identical* across
calls. The discipline (design spec §7.2):

    [system + schemas + digest + intents] → [event tail]

- The **prefix** changes only at epoch boundaries (`begin_epoch`), so
  every call within an epoch re-reads it from cache.
- The **tail** is the pending event batch — inherently uncacheable, kept
  small, and the only thing that varies call to call.
- Digests are canonical (sort-keys JSON) so equal state serializes to
  identical bytes — an unstable serialization silently destroys the
  cache as surely as an unstable prefix.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


def canonical_digest(state: Mapping) -> str:
    """Byte-stable serialization of a digest-state mapping."""
    return json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class PromptBuilder:
    """Builds messages with an epoch-stable prefix and an event tail."""

    system: str
    schemas: tuple[dict, ...] = ()           # JSON-schema dicts, rendered into the system block
    _digest_block: str = ""
    _intents: tuple[str, ...] = ()
    _tail: list[str] = field(default_factory=list)

    # ---- epoch management ---------------------------------------------------

    def begin_epoch(self, digest_state: Mapping, intents: Iterable[str] = ()) -> None:
        """Start a new epoch: replace the digest/intents blocks. Pending
        tail events carry over (they still need flushing)."""
        self._digest_block = canonical_digest(digest_state)
        self._intents = tuple(intents)

    # ---- events ---------------------------------------------------------------

    def add_event(self, event: str) -> None:
        self._tail.append(event)

    @property
    def pending_count(self) -> int:
        return len(self._tail)

    # ---- building ---------------------------------------------------------------

    def prefix_messages(self) -> list[dict]:
        """The cacheable prefix: system (+schemas), digest, intents."""
        system_content = self.system
        if self.schemas:
            system_content += "\n\nSchemas:\n" + "\n".join(
                json.dumps(s, sort_keys=True) for s in self.schemas
            )
        msgs = [{"role": "system", "content": system_content}]
        msgs.append({"role": "system", "content": f"World digest:\n{self._digest_block}"})
        msgs.append({
            "role": "system",
            "content": "Active intents:\n" + ("\n".join(f"- {i}" for i in self._intents) or "(none)"),
        })
        return msgs

    def build_messages(self) -> list[dict]:
        """Prefix + the pending tail as one user message."""
        if not self._tail:
            raise ValueError("nothing to flush — tail is empty")
        return self.prefix_messages() + [
            {"role": "user", "content": "Events:\n" + "\n".join(f"- {e}" for e in self._tail)}
        ]

    def flush(self) -> list[dict]:
        """Build and clear the tail."""
        msgs = self.build_messages()
        self._tail.clear()
        return msgs

    def prefix_bytes(self) -> bytes:
        """Canonical bytes of the prefix — byte-stability check for tests
        and for the bench's fake-cache transport."""
        return json.dumps(self.prefix_messages(), sort_keys=True, ensure_ascii=False).encode("utf-8")
