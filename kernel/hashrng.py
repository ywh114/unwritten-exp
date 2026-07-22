"""K1 — hashrng: deterministic content-addressed sampling.

Foundation stone of the Unwritten lab. Every stochastic decision in every
later library draws from a content-addressed stream keyed by
(world_seed, entity_id, context_digest) so that:

* same inputs -> identical outputs, across processes and machines;
* neighboring entity_ids, clocks, or contexts -> statistically
  independent draws (no seed-correlation artifacts);
* streams are random-access by (clock, index) — no sequential state,
  which is what makes analytic time-skip cheap downstream (K2+).

Design: BLAKE2b in counter mode. A 256-bit *stream key* is derived from
(world_seed, entity_id, context_digest); each draw is an 8-byte BLAKE2b
digest of (clock, index) keyed by the stream key. BLAKE2b is specified in
RFC 7693 and is bit-stable across platforms; all integers are packed
little-endian explicitly, so results do not depend on host endianness,
word size, or Python version.

Bulk fields: `Stream.u64_batch(clocks, indices)` is a SEPARATE,
vectorized draw mode for bulk generation (lattice noise etc.) — a keyed
splitmix64-style numpy mixer over coordinate arrays, since one BLAKE2b
per coordinate is far too slow for ~1e7-draw fields (measured 50 s of a
70 s K11 world build). Values do NOT match u64() at the same
coordinates; never mix the two modes for the same purpose.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Iterator

# BLAKE2b personalization strings (<= 16 bytes each). Distinct personas for
# key derivation vs. draws so the two uses can never collide, even if input
# encodings ever overlap.
_PERSON_KEY = b"uw.k1.stream"
_PERSON_DRAW = b"uw.k1.draw"

_KEY_BYTES = 32  # 256-bit stream key
_DRAW_BYTES = 8  # one u64 per draw


def _pack_str(s: str) -> bytes:
    data = s.encode("utf-8")
    return struct.pack("<I", len(data)) + data


def stream_key(world_seed: int, entity_id: str, context_digest: str = "") -> bytes:
    """Derive the 256-bit stream key for an (entity, context) pair."""
    if not 0 <= world_seed < 1 << 64:
        raise ValueError("world_seed must fit in u64")
    h = hashlib.blake2b(digest_size=_KEY_BYTES, person=_PERSON_KEY)
    h.update(struct.pack("<Q", world_seed))
    h.update(_pack_str(entity_id))
    h.update(_pack_str(context_digest))
    return h.digest()


def _draw_u64(key: bytes, clock: int, index: int) -> int:
    if not -(1 << 63) <= clock < 1 << 63:
        raise ValueError("clock must fit in i64")
    if not 0 <= index < 1 << 64:
        raise ValueError("index must fit in u64")
    h = hashlib.blake2b(digest_size=_DRAW_BYTES, key=key, person=_PERSON_DRAW)
    h.update(struct.pack("<qQ", clock, index))
    return int.from_bytes(h.digest(), "little")


def _draw_u64_batch(key: bytes, clocks, indices):
    """Vectorized bulk draws over numpy arrays of (clock, index).

    One scalar BLAKE2b call per coordinate is the right thing for
    random-access single draws, but hopeless for bulk field generation
    (K11's lattice noise needs ~1e7 draws — measured 50 s of hashing
    in a 70 s world build). This mixer derives three u64 lane keys
    from the stream key and runs a splitmix64-style vectorized round
    over the coordinate arrays: deterministic, platform-stable (uint64
    wraparound arithmetic), statistically independent per coordinate,
    and ~1000x faster. It is a SEPARATE draw mode — values do not
    match u64(); callers must not mix the two for the same purpose.
    numpy is imported lazily so kernel.hashrng stays dependency-light.
    """
    import numpy as np

    k0 = np.uint64(int.from_bytes(key[0:8], "little"))
    k1 = np.uint64(int.from_bytes(key[8:16], "little"))
    k2 = np.uint64(int.from_bytes(key[16:24], "little"))
    c = np.asarray(clocks).astype(np.uint64)   # i64 two's-complement wrap
    i = np.asarray(indices).astype(np.uint64)  # is deterministic
    z = (c * np.uint64(0x9E3779B97F4A7C15)
         + i * np.uint64(0xC2B2AE3D27D4EB4F) + k0)
    z = (z ^ (z >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    z = (z ^ (z >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    z = z ^ (z >> np.uint64(31)) ^ k1
    z = (z ^ (z >> np.uint64(29))) * np.uint64(0xBF58476D1CE4E5B9)
    z = z ^ (z >> np.uint64(32)) ^ k2
    return z


class Stream:
    """Random-access deterministic draw stream for one entity+context.

    Draws are addressed by (clock, index): `clock` is the world clock value
    (any i64, so dates/minutes/ticks all fit), `index` distinguishes
    multiple draws at the same clock. There is no sequential state —
    drawing at clock 10**9 costs the same as drawing at clock 0.
    """

    __slots__ = ("world_seed", "entity_id", "context_digest", "key")

    def __init__(self, world_seed: int, entity_id: str, context_digest: str = "") -> None:
        self.world_seed = world_seed
        self.entity_id = entity_id
        self.context_digest = context_digest
        self.key = stream_key(world_seed, entity_id, context_digest)

    def __repr__(self) -> str:
        return (
            f"Stream(world_seed={self.world_seed}, entity_id={self.entity_id!r}, "
            f"context_digest={self.context_digest!r})"
        )

    def child(self, context: str) -> "Stream":
        """Derived substream with independent draws, same provenance.

        K1 draws are keyed by (clock, index) only, so two fields drawn
        from the SAME stream at the same coordinates are identical —
        every independent random field needs its own context."""
        joiner = "|" if self.context_digest else ""
        return Stream(self.world_seed, self.entity_id,
                      self.context_digest + joiner + context)

    def u64(self, clock: int, index: int = 0) -> int:
        """Raw 64-bit unsigned draw."""
        return _draw_u64(self.key, clock, index)

    def u64_batch(self, clocks, indices):
        """Vectorized bulk draws over numpy (clock, index) arrays.

        Fast path for bulk field generation (lattice noise etc.) — a
        keyed splitmix64-style mixer rather than per-draw BLAKE2b.
        SEPARATE draw mode: values do not match u64() at the same
        coordinates; do not mix the two for the same purpose.
        """
        return _draw_u64_batch(self.key, clocks, indices)

    def uniform(self, clock: int, index: int = 0) -> float:
        """Uniform float in [0, 1) — 53 bits of entropy."""
        return (self.u64(clock, index) >> 11) * (1.0 / (1 << 53))

    def uniforms(self, clock: int, n: int) -> Iterator[float]:
        """n consecutive uniforms at one clock (indices 0..n-1)."""
        for index in range(n):
            yield self.uniform(clock, index)

    def bernoulli(self, p: float, clock: int, index: int = 0) -> bool:
        return self.uniform(clock, index) < p

    def randrange(self, n: int, clock: int, index: int = 0) -> int:
        """Uniform int in [0, n) via multiply-shift (no modulo bias)."""
        if n <= 0:
            raise ValueError("n must be positive")
        return (self.u64(clock, index) * n) >> 64

    def normal(self, clock: int, index: int = 0) -> float:
        """Standard normal via Box–Muller; consumes draw indices 2i and 2i+1."""
        u1 = 1.0 - self.uniform(clock, 2 * index)  # (0, 1]
        u2 = self.uniform(clock, 2 * index + 1)
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def digest(self, clock_start: int, clock_stop: int, draws_per_clock: int = 1) -> str:
        """SHA-256 hex digest of a clock range of draws — stream identity
        for bit-identical-rerun checks."""
        h = hashlib.sha256()
        for clock in range(clock_start, clock_stop):
            for index in range(draws_per_clock):
                h.update(struct.pack("<Q", self.u64(clock, index)))
        return h.hexdigest()


def sample(world_seed: int, entity_id: str, clock: int, context_digest: str = "") -> float:
    """One-shot uniform in [0, 1) — the lab spec's canonical call signature."""
    return Stream(world_seed, entity_id, context_digest).uniform(clock)
