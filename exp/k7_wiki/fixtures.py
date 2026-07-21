"""K7 demo fixture — 30-fact village wiki.

Mixed trust: canon facts (trust ≥ 0.9), NPC rumors (0.2–0.5), one
fabricated rumor (trust −0.8 — the orchestrator knows it is a lie
even though NPCs relay it as true).  Includes a supersession pair
("bridge intact" → "bridge burned") and one already-archived fact.
"""

from __future__ import annotations

from kernel.wiki_store.facts import FactState, make_fact
from kernel.wiki_store.store import WikiStore


def build_store() -> WikiStore:
    store = WikiStore()

    _w = lambda text, trust=1.0, importance="notable", provenance="canon", **kw: store.write(
        make_fact(text=text, trust=trust, importance=importance,
                  provenance=provenance, **kw))

    _w("The village of Ashwick lies on the west bank of the Silverflow river.",
       trust=1.0, provenance="canon")
    _w("The village mill grinds grain for the entire valley.",
       trust=1.0, provenance="canon")
    _w("The miller is a giant, hereditary post held by the Stonehand line.",
       trust=1.0, provenance="canon")
    _w("King Eldric holds court at the capital.",
       trust=1.0, provenance="canon")
    _w("Duke Aldric is the lord of Northmarch.",
       trust=1.0, provenance="canon")

    # supersession: bridge intact → bridge burned (via the API, so the
    # old fact is properly ARCHIVED, not just window-closed)
    intact_id = store.write(make_fact(
        text="The old stone bridge across the Silverflow is intact and well-maintained.",
        trust=1.0, importance="notable", provenance="canon", valid_from=0.0,
    ))
    store.supersede(make_fact(
        text="The old stone bridge across the Silverflow was burned during the flood riots.",
        trust=1.0, importance="notable", provenance="measurement", valid_from=30.0,
    ), intact_id)

    _w("The flood riots of year 7 claimed twelve lives.",
       trust=1.0, provenance="measurement", valid_from=30.0)

    _w("The village inn is called the Restless Fox.",
       trust=1.0, provenance="canon")
    _w("The innkeeper Mara brews the best ale in three counties.",
       trust=0.8, provenance="npc:miller")
    _w("Mara the innkeeper has a scar across her left eye.",
       trust=1.0, provenance="canon")

    # NPC rumors — moderate trust
    _w("Strange lights were seen over the northern hills last harvest moon.",
       trust=0.4, provenance="npc:farmer")
    _w("The blacksmith's daughter ran off with a travelling merchant.",
       trust=0.3, provenance="npc:miller")
    _w("Duke Aldric has been seen arguing with the king's envoy.",
       trust=0.5, provenance="npc:guard")
    _w("There's an old hermit living in the eastern woods who can read the future.",
       trust=0.2, provenance="npc:farmer")

    # Fabricated rumor — orchestrator knows it is a lie (trust < 0)
    _w("The miller's wife is secretly a witch who poisons the grain.",
       trust=-0.8, provenance="npc:jealous_neighbour")

    _w("A delegation from the elven court passed through the village last spring.",
       trust=0.6, provenance="npc:innkeeper")
    _w("The temple bell can be heard five miles away on a clear day.",
       trust=0.9, provenance="canon")
    _w("Old Man Garrick buried a chest of silver under his barn.",
       trust=0.1, provenance="npc:child")
    _w("The harvest of year 8 was the largest in living memory.",
       trust=0.8, provenance="npc:farmer")
    _w("There is a secret passage from the mill to the riverbank.",
       trust=0.3, provenance="npc:miller")
    _w("The village well has never run dry, even in the worst summers.",
       trust=0.9, provenance="canon")
    _w("Bandits have been spotted on the north road in the last fortnight.",
       trust=0.5, provenance="npc:merchant")
    _w("The constable is in debt to a gambling ring in the capital.",
       trust=-0.3, provenance="npc:rival_constable")  # another negative-trust rumor
    _w("The midwife has delivered every child born in Ashwick for forty years.",
       trust=0.9, provenance="canon")
    _w("A wounded knight was found near the crossroads two nights ago.",
       trust=0.7, provenance="npc:guard")
    _w("The annual fair draws merchants from as far as the coast.",
       trust=0.8, provenance="canon")

    # One already-archived fact (pre-superseded)
    store.write(make_fact(
        text="The village watch consists of four men.",
        trust=1.0, provenance="canon",
        valid_from=0.0, valid_until=10.0, state=FactState.ARCHIVED,
        superseded_by="000000000000",
    ))

    return store
