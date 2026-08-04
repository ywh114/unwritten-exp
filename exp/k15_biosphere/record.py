"""Species description record for the K15 biosphere rewrite (ticket 0041;
spec B9 §1).

A species is stored as a flat record of trait values: ``axes`` (every
plan-scoped trait value) + ``generics`` (generic -> realization), sid,
g/gen_time, and the plan/preset refs the record commits at.  This is the
record half of the k13 ``Node`` shape (``exp/k13_treegen/model.py``),
minus everything the tree machinery needs — path/parent/rank, label,
flags, edge deltas, NameRecord, provenance, QuantityStore are other
layers' business.

The record holds COMMITTED traits only.  Nothing derived is ever stored
in it: the derived view is computed on read from these committed axes and
never written back (B9 §1).  There is no ``DERIVED_AXES`` concept here
because there is nothing derived to guard.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpeciesRecord:
    """One committed species description: flat axes + generics + identity.

    ``sid`` is the hash-stable species id; ``g`` the genetic distance from
    founder (generations) and ``gen_time`` years per generation (the g-clock
    rate).  ``plan`` / ``preset`` reference the body plan and content preset
    the record commits at.  ``axes`` maps axis name -> committed value
    (scalars, enums as strings, weighted sets as dicts); ``generics`` maps
    generic -> realization id.
    """

    sid: str
    plan: str | None = None         # body plan, committed at class level
    preset: str | None = None       # preset id, committed at order level
    g: float = 0.0                  # genetic distance from founder (gen)
    gen_time: float = 0.0           # years per generation (g-clock rate)
    axes: dict[str, object] = field(default_factory=dict)
    generics: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict:
        """JSON-shaped dict; ``from_json`` round-trips byte-exactly."""
        return {
            "sid": self.sid,
            "plan": self.plan,
            "preset": self.preset,
            "g": self.g,
            "gen_time": self.gen_time,
            "axes": self.axes,
            "generics": self.generics,
        }

    @classmethod
    def from_json(cls, d: dict) -> "SpeciesRecord":
        return cls(
            sid=d["sid"], plan=d.get("plan"), preset=d.get("preset"),
            g=d.get("g", 0.0), gen_time=d.get("gen_time", 0.0),
            axes=dict(d.get("axes", {})),
            generics=dict(d.get("generics", {})),
        )
