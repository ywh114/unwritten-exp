"""K3 — append-only collapse log.

Every measurement operation appends a record (clock, tier, target, facts,
stream_digest).  `stream_digest` is a SHA-256 hash over the exact K1 draws
the operation consumed — the audit handle for the filtration invariant:
coarse records constrain fine records, and any change in the underlying
draws is detectable by re-deriving the digest.
"""

from __future__ import annotations

import hashlib
import struct
from collections.abc import Iterable
from dataclasses import dataclass, field

from kernel.hashrng import Stream


def digest_draws(stream: Stream, clock: int, u64_indices: Iterable[int]) -> str:
    """16-hex-char digest of the stream's u64 draws at (clock, index).

    Deterministic given the stream; covers exactly the draws an operation
    consumed, so a changed draw changes the digest.
    """
    h = hashlib.sha256()
    for i in u64_indices:
        h.update(struct.pack("<Q", stream.u64(clock, i)))
    return h.hexdigest()[:16]


@dataclass
class CollapseRecord:
    clock: int
    tier: str             # "field" | "silhouette" | "identity"
    region_or_entity: str  # rect repr or silhouette/identity id
    facts: dict            # human-readable facts committed
    stream_digest: str     # digest_draws over the draws consumed


@dataclass
class CollapseLog:
    """Append-only measurement record."""

    records: list[CollapseRecord] = field(default_factory=list)

    def append(self, clock: int, tier: str, region_or_entity: str,
               facts: dict, stream_digest: str) -> None:
        self.records.append(
            CollapseRecord(
                clock=clock,
                tier=tier,
                region_or_entity=region_or_entity,
                facts=facts,
                stream_digest=stream_digest,
            )
        )

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):
        return iter(self.records)
