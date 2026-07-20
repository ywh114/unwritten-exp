"""K3 demo fixture — village square with a 12-person crowd field and a
14-resident roster (12 inside the square, 2 outside).

The field has three components: a market knot (~5 expected), loiterers
(~4), and a perimeter group (~3).  The roster includes two residents
(Nina, Oscar) whose priors lie entirely outside the square — these must
**never** be assigned during identity refinement (hard filtration test).

All positions and priors are plain dataclass literals so the fixture is
seed-independent and the demo replays byte-identically under --seed.
"""

from __future__ import annotations

from kernel.gmm_dynamics.gmm import Gaussian, GMM

from kernel.collapse.field import Resident
from kernel.collapse.geometry import Rect

import numpy as np

# ---- rect ------------------------------------------------------------------

SQUARE = Rect(0.0, 0.0, 100.0, 100.0)

# A smaller rect in the corner that contains zero mass from any component
# — used for the "search an empty region" demo step.
EMPTY_RECT = Rect(-50.0, -50.0, -40.0, -40.0)

# A rect that contains roughly 3 of the 12 expected villagers.
PARTIAL_RECT = Rect(10.0, 10.0, 40.0, 40.0)

# ---- crowd field -----------------------------------------------------------

# Three Gaussian components whose weights sum to 12.
FIELD_COMPONENTS = [
    # market knot — dense crowd near the centre
    (5.0,  (60.0, 55.0),  ((8.0, 1.0), (1.0, 8.0))),
    # loiterers — spread out near the western edge
    (4.0,  (20.0, 30.0),  ((25.0, 3.0), (3.0, 25.0))),
    # perimeter — tighter knot near the south-east corner
    (3.0,  (85.0, 15.0),  ((4.0, 0.5), (0.5, 4.0))),
]


def build_field() -> GMM:
    """A 12-person crowd field over the village square."""
    weights = np.array([c[0] for c in FIELD_COMPONENTS], dtype=float)
    means = np.array([[c[1][0], c[1][1]] for c in FIELD_COMPONENTS], dtype=float)
    covs = np.array([[[c[2][0][0], c[2][0][1]], [c[2][1][0], c[2][1][1]]]
                      for c in FIELD_COMPONENTS], dtype=float)
    return GMM(weights, means, covs)


# ---- residents -------------------------------------------------------------

RESIDENT_NAMES = [
    ("alice",   "Alice"),
    ("bob",     "Bob"),
    ("carl",    "Carl"),
    ("dana",    "Dana"),
    ("erin",    "Erin"),
    ("frank",   "Frank"),
    ("grace",   "Grace"),
    ("hank",    "Hank"),
    ("iris",    "Iris"),
    ("jake",    "Jake"),
    ("kate",    "Kate"),
    ("leo",     "Leo"),
]
# Two outside-prior residents:
OUTSIDE_NAMES = [
    ("nina",   "Nina"),
    ("oscar",  "Oscar"),
]

# Prior positions for the 12 inside-prior residents (scattered across the
# square with plausible personal spreads).
_INSIDE_PRIORS = [
    ((58.0, 52.0), 4.0),   # alice — near market
    ((63.0, 58.0), 3.0),   # bob
    ((55.0, 48.0), 5.0),   # carl
    ((25.0, 35.0), 6.0),   # dana — loiterer
    ((15.0, 28.0), 5.0),   # erin
    ((22.0, 22.0), 7.0),   # frank
    ((30.0, 38.0), 4.0),   # grace
    ((82.0, 12.0), 3.0),   # hank — perimeter
    ((88.0, 18.0), 3.5),   # iris
    ((78.0, 10.0), 4.0),   # jake
    ((50.0, 70.0), 6.0),   # kate — edge of market
    ((70.0, 40.0), 5.0),   # leo
]

# Outside priors — clearly outside the square
_OUTSIDE_PRIORS = [
    ((-20.0, -20.0), 3.0),  # nina — SW of square
    ((120.0, 50.0),  4.0),  # oscar — east of square
]


def build_residents() -> list[Resident]:
    """14 residents: 12 with priors inside the square, 2 outside."""
    residents: list[Resident] = []
    for (slug, name), ((mx, my), sd) in zip(RESIDENT_NAMES, _INSIDE_PRIORS):
        residents.append(Resident(
            id=slug,
            name=name,
            prior=Gaussian(mean=(mx, my), var=sd * sd),
        ))
    for (slug, name), ((mx, my), sd) in zip(OUTSIDE_NAMES, _OUTSIDE_PRIORS):
        residents.append(Resident(
            id=slug,
            name=name,
            prior=Gaussian(mean=(mx, my), var=sd * sd),
        ))
    return residents
