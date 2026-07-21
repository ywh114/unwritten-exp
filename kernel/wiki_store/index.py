"""K7 — deterministic vector index for wiki retrieval.

`HashedIndex` is a zero-dependency, byte-identical bag-of-words index
over 256-dimensional signed projections.  Each token maps via BLAKE2b
(four u64 draws per token) to signed unit-vector contributions; the
document vector is their sum.  Cosine distance is used for queries.

A `VectorIndex` protocol is documented as the swap-point for a future
ChromaDB backend at assembly.
"""

from __future__ import annotations

import hashlib
import math
import re
import struct
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# Protocol (documented swap point for ChromaDB at assembly)
# ---------------------------------------------------------------------------
# class VectorIndex(Protocol):
#     def add(self, id: str, text: str) -> None: ...
#     def remove(self, id: str) -> None: ...
#     def query(self, text: str, k: int) -> list[tuple[str, float]]: ...
#       # returns list of (id, distance), sorted by distance ascending;
#       # ties broken by id string order.

# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_DIM = 256


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


# ---------------------------------------------------------------------------
# HashedIndex
# ---------------------------------------------------------------------------


@dataclass
class HashedIndex:
    """Deterministic bag-of-words index: token → BLAKE2b → signed
    256-dim projection; document vector = sum of token projections;
    cosine distance for query."""

    _dim: int = _DIM
    _vectors: dict[str, np.ndarray] = field(default_factory=dict)
    # id → unit-normalised vector for cached query comparisons
    _norms: dict[str, np.ndarray] = field(default_factory=dict)

    def _token_seed(self, token: str) -> bytes:
        """32-byte BLAKE2b key per token (deterministic, cross-platform)."""
        h = hashlib.blake2b(digest_size=32, person=b"k7.wiki.idx")
        h.update(token.encode("utf-8"))
        return h.digest()

    def _token_projection(self, token: str) -> np.ndarray:
        """256-dim signed unit-projection from a token."""
        key = self._token_seed(token)
        vec = np.zeros(self._dim, dtype=np.float64)
        for d in range(0, self._dim, 2):
            h = hashlib.blake2b(digest_size=8, key=key,
                                person=b"k7.wiki.prj")
            h.update(struct.pack("<H", d))
            u64 = int.from_bytes(h.digest(), "little")
            # two signed components: sign from top bit, magnitude from
            # lower 63 bits normalised
            for offset in range(2):
                if d + offset >= self._dim:
                    break
                v = (u64 >> (offset * 32)) & 0xFFFFFFFF
                sign = 1.0 if (v & 0x80000000) == 0 else -1.0
                mag = float(v & 0x7FFFFFFF) / 0x7FFFFFFF
                vec[d + offset] = sign * mag
        return vec

    def _embed(self, text: str) -> np.ndarray:
        toks = _tokens(text)
        if not toks:
            return np.zeros(self._dim)
        vec = np.zeros(self._dim)
        for tok in toks:
            vec += self._token_projection(tok)
        return vec

    def _normalise(self, vec: np.ndarray) -> np.ndarray:
        n = float(np.linalg.norm(vec))
        if n == 0.0:
            return vec
        return vec / n

    def add(self, id: str, text: str) -> None:
        self._vectors[id] = self._embed(text)
        self._norms[id] = self._normalise(self._vectors[id])

    def remove(self, id: str) -> None:
        self._vectors.pop(id, None)
        self._norms.pop(id, None)

    def query(self, text: str, k: int) -> list[tuple[str, float]]:
        q = self._normalise(self._embed(text))
        results: list[tuple[str, float]] = []
        for id, v in self._norms.items():
            dot = float(np.dot(q, v))
            dot = max(-1.0, min(1.0, dot))
            # cosine distance = 1 − cos_sim
            dist = 1.0 - dot
            results.append((id, dist))
        results.sort(key=lambda x: (x[1], x[0]))
        return results[:k]
