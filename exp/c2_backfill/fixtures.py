"""C2 — fixture village: 20 NPCs, K4 counters, K5 promises, K7 wiki.

Builds a synthetic village-in-a-dataclass for the backfill pipeline demo.
Deterministic: same seed → byte-identical village.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kernel.counters import Counter, Logistic, Step
from kernel.hashrng import Stream
from kernel.promise_ledger import PromiseLedger, Predicate, PredicateKind
from kernel.wiki_store import WikiStore

from capability.backfill.schema import NPCCard, Village


_NPC_TEMPLATES: list[tuple[str, str, str, str, bool]] = [
    # slug, name, role, state, dead
    ("elder_oswin",  "Oswin",  "village elder",   "aging but respected; holds the high seat", False),
    ("miller_tobias","Tobias", "miller",           "grumbling about the broken wheel", False),
    ("blacksmith_elara","Elara","blacksmith",      "forging a ceremonial sword for the duke", False),
    ("herbalist_lyra","Lyra",  "herbalist",        "worried about blight in the eastern field", False),
    ("hunter_kade",   "Kade",   "hunter",          "tracking wolves near the northern ridge", False),
    ("carpenter_maeve","Maeve","carpenter",         "repairing the mill roof after last storm", False),
    ("innkeep_bram",  "Bram",   "innkeeper",       "watering down ale; nobody complains", False),
    ("shepherd_ciaran","Ciaran","shepherd",         "lost two sheep to a ridge predator", False),
    ("baker_elara",   "Elara the Younger", "baker", "selling day-old bread at half price", False),
    ("weaver_niamh",  "Niamh",  "weaver",          "dyed the new wool crimson — a bold choice", False),
    ("fisher_owen",   "Owen",   "fisher",          "claims he saw a river spirit at dawn", False),
    ("tanner_rory",   "Rory",   "tanner",          "foul-smelling but indispensable", False),
    ("farmer_eadric", "Eadric", "farmer",           "largest grain plot east of the millpond", False),
    ("hedge_witch_selene","Selene","hedge-witch",   "villagers avoid her but pay for remedies", False),
    ("minstrel_finn", "Finn",   "minstrel",         "collecting tales for a song about the duke", False),
    ("apothecary_ida","Ida",    "apothecary",       "short on feverfew after the last outbreak", False),
    ("carter_garrick","Garrick","carter",            "waiting for the duke's supply train", False),
    ("midwife_branna","Branna", "midwife",          "delivered three babes this season alone", False),
    ("old_cade",      "Old Cade",     "retired guard",  "died last winter fighting a bear", True),
    ("ser_aelin",     "Ser Aelin",    "fallen knight",  "buried under the old oak after the plague", True),
]



def build_village(seed: int) -> Village:
    """Build the fixture village deterministically from `seed`."""
    stream = Stream(seed, "c2.fixtures")

    # --- NPCs ---
    npcs: list[NPCCard] = []
    dead_slugs: set[str] = set()
    for slug, name, role, state, dead in _NPC_TEMPLATES:
        if dead:
            dead_slugs.add(slug)
        npcs.append(NPCCard(slug=slug, name=name, role=role, state=state, dead=dead))

    # --- Counters (K4) ---
    counters: dict[str, Counter] = {}

    # grain: Logistic, harvest regime boosts rate
    grain = Counter(regimes={"harvest": {"rate": 2.0, "capacity": 1.1}})
    grain.set_anchor(t=0.0, value=500.0, law=Logistic(rate=0.03, capacity=800.0),
                     regime="harvest", note="autumn harvest begins")
    counters["grain"] = grain

    # population: Logistic, slow growth
    pop = Counter()
    pop.set_anchor(t=0.0, value=120.0, law=Logistic(rate=0.015, capacity=200.0),
                   note="spring census")
    counters["population"] = pop

    # garrison: Step (no dynamics; events create steps)
    garrison = Counter()
    garrison.set_anchor(t=0.0, value=30.0, law=Step(),
                        note="spring muster count")
    # Insert a few pre-authored events for the season
    # Recruitment at t=20
    garrison.insert_event(t=20.0, delta=5.0, note="border patrol recruited")
    # Desertion at t=50
    garrison.insert_event(t=50.0, delta=-3.0, note="two guards deserted")
    counters["garrison"] = garrison

    # --- Promise set (K5) ---
    ledger = PromiseLedger(seed=seed)

    # Due promises (Chekhov seeds — window ends inside [0, 90]):
    # 1. Miller promised to repair the mill wheel by mid-season
    pid1 = ledger.assert_(
        Predicate(PredicateKind.BOUND, "miller_tobias",
                  detail="repair the mill wheel by autumn"),
        scope="village",
        window=(0.0, 45.0),
        strength=0.9,
        provenance="npc:miller_tobias",
        note="miller vowed to fix the wheel before harvest peak",
    )

    # 2. The duke's envoy arrives at harvest
    pid2 = ledger.assert_(
        Predicate(PredicateKind.LOCATED, "duke_envoy", "village",
                  detail="arrives at harvest"),
        scope="village",
        window=(0.0, 60.0),
        strength=1.0,
        provenance="canon",
        note="duke's tax collector expected by midsummer",
    )

    # Background promises (not due this season):
    # 3. Blacksmith owes the duke a ceremonial sword
    ledger.assert_(
        Predicate(PredicateKind.OWNS, "duke", "ceremonial_sword",
                  detail="commissioned from blacksmith"),
        scope="village",
        window=(0.0, 200.0),
        strength=0.8,
        provenance="canon",
        note="duke commissioned a blade from Elara; due by year's end",
    )

    # 4. Village elder holds the title of chief
    ledger.assert_(
        Predicate(PredicateKind.HOLDS, "elder_oswin", "chief",
                  detail="hereditary title"),
        scope="village",
        window=(0.0, None),
        strength=1.0,
        provenance="measurement",
        note="oswin has been chief for three decades",
    )

    # 5. Hunter is hostile to the northern tribe
    ledger.assert_(
        Predicate(PredicateKind.HOSTILE, "hunter_kade", "northern_tribe",
                  detail="wolves driven south"),
        scope="northern_ridge",
        window=(0.0, None),
        strength=0.6,
        provenance="npc:hunter_kade",
        note="kade blames the tribe for the wolf incursion",
    )

    # 6. Shepherds owe fealty to the elder
    ledger.assert_(
        Predicate(PredicateKind.FEALTY, "shepherd_ciaran", "elder_oswin",
                  detail="annual tithe of wool"),
        scope="village",
        window=(0.0, None),
        strength=0.7,
        provenance="canon",
        note="tradition since the founding",
    )

    # --- Wiki (K7, empty at t=0) ---
    wiki = WikiStore()

    return Village(
        npcs=npcs,
        counters=counters,
        ledger=ledger,
        wiki=wiki,
        dead_slugs=dead_slugs,
    )
