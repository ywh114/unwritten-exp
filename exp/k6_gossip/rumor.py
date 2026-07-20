"""K6 — rumor record and mechanical perturbation.

A rumor is a structured record about a world event.  It travels the gossip
network as bytes, degrading mechanically each hop — field drops, mutations,
magnitude drift — while trust decays.  This library moves structured
records; it never writes prose.  (LLM delivery is C3's job.)

A node stores exactly one Belief per (subject, event-class): the
highest-trust version heard.  The event-class is the canonical name
for a set of mutation-linked events, so "burned" and "collapsed"
compete for the same belief slot.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from kernel.hashrng import Stream

# ---------------------------------------------------------------------------
# Mutation table + canonical event-class mapping
# ---------------------------------------------------------------------------

_MUTATION_TABLE: dict[str, str] = {
    "burned": "collapsed",
    "collapsed": "burned",
}

_EVENT_CLASS: dict[str, str] = {}
for _a, _b in _MUTATION_TABLE.items():
    _canon = min(_a, _b)
    _EVENT_CLASS[_a] = _canon
    _EVENT_CLASS[_b] = _canon


def _mutated_event(event: str) -> str:
    return _MUTATION_TABLE.get(event, event)


# ---------------------------------------------------------------------------
# Rumor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rumor:
    """One structured world-event report.

    `subject` is what the rumor is *about* (e.g. "mill").
    `event` is what happened (e.g. "burned").
    `location` and `day` are droppable details — they become None under
    enough perturbation.
    `magnitude` is severity, 1.0 at origin, drifting per hop.
    """

    subject: str
    event: str
    location: str | None
    day: float | None
    magnitude: float

    @property
    def event_class(self) -> str:
        """Two mutated versions of the same ancestor share this key and
        compete for belief slots."""
        return _EVENT_CLASS.get(self.event, self.event)


# ---------------------------------------------------------------------------
# Belief
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Belief:
    """A node's held version of a rumor at a moment in time."""

    rumor: Rumor
    trust: float       # [0, 1], decays per hop
    heard_day: int     # the day this version was received


# ---------------------------------------------------------------------------
# Perturbation
# ---------------------------------------------------------------------------


def perturb(rumor: Rumor, stream: Stream, clock: int, idx_base: int,
            q_drop: float = 0.1, q_mut: float = 0.05,
            sigma_drift: float = 0.1) -> Rumor:
    """Apply one hop of mechanical degradation.

    Draw indices used (all from `clock`, starting at `idx_base`):
      0 : field-drop coin for `location`
      1 : field-drop coin for `day`
      2 : mutation coin
      3,4 : magnitude drift normals (consumes draw indices 2·3, 2·3+1,
            2·4, 2·4+1 in the K1 normal stream)

    Returns a new Rumor (immutable — the caller decides if a node keeps it).
    """
    loc = rumor.location
    if stream.bernoulli(q_drop, clock, idx_base + 0):
        loc = None
    day = rumor.day
    if stream.bernoulli(q_drop, clock, idx_base + 1):
        day = None

    ev = rumor.event
    if stream.bernoulli(q_mut, clock, idx_base + 2):
        ev = _mutated_event(ev)

    # magnitude log-normal drift: mag *= exp(N(0, sigma_drift))
    z = stream.normal(clock, idx_base + 3)  # K1 normal consumes 2·i, 2·i+1
    mag = rumor.magnitude * math.exp(sigma_drift * z)
    mag = max(0.1, min(3.0, mag))

    return Rumor(subject=rumor.subject, event=ev, location=loc,
                 day=day, magnitude=mag)
