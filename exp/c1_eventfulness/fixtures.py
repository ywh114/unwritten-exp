"""C1 demo fixture — Ashwick village context and 100-interval schedule.

The context blurb is the LLM's world backdrop (2–3 sentences of fixed
village description — reuse the K7/L2 flavor).  Intervals are labelled
deterministically: 40 weeks, 35 seasons, 25 years.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Village context blurb (fixed — no LLM generation)
# ---------------------------------------------------------------------------

VILLAGE_CONTEXT = (
    "Ashwick lies on the west bank of the Silverflow river. The village mill "
    "(held by the Stonehand line) grinds grain for the entire valley; the old "
    "stone bridge was burned during the flood riots of year 7. The Restless Fox "
    "inn is the social hub. King Eldric holds court at the capital, and Duke "
    "Aldric is lord of Northmarch."
)

# ---------------------------------------------------------------------------
# Interval schedule
# ---------------------------------------------------------------------------


def build_intervals() -> list[dict]:
    """100 intervals: 40 weeks + 35 seasons + 25 years, each with
    deterministic id, scale, and label."""
    intervals: list[dict] = []
    for w in range(40):
        intervals.append({
            "id": f"week:{w:03d}",
            "scale": "week",
            "label": f"week {w % 13 + 1} of year {w // 13 + 1}",
        })
    for s in range(35):
        intervals.append({
            "id": f"season:{s:03d}",
            "scale": "season",
            "label": f"{['spring','summer','autumn','winter'][s%4]} of year {s//4 + 1}",
        })
    for y in range(25):
        intervals.append({
            "id": f"year:{y:03d}",
            "scale": "year",
            "label": f"year {y + 1}",
        })
    return intervals
