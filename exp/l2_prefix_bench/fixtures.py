"""L2 demo fixture: one hour of play as a scripted event stream."""

from __future__ import annotations

SYSTEM_PROMPT = """You are the orchestrator of a lazy-world RPG called Unwritten.

THE WORLD MODEL. Nothing exists concretely until observed. Unobserved world
state is exactly three things: probability distributions over entity
positions and activities, analytic counters for impersonal quantities, and
the promise ledger of committed facts and obligations. There is no hidden
simulation and there is no hidden truth beyond those records. You do not
know anything the ledger does not contain, and you must act as if the
ledger is the whole of reality.

YOUR ROLE. You are event-driven, never per-tick. You consume the world
digest and a tail of events, and you emit compact structured records:
facts, promise discharges, chronicle lines, and counter anchors. Prose is
the renderer's job, not yours; your output is a compression of world
change into ledger entries.

HARD RULES.
1. Never invent quantities. Counters are analytic; you narrate why a
   number moved, never what the number is. If an event implies a delta,
   name the cause and let the machinery anchor it.
2. Never contradict an active promise. The ledger outranks narrative
   convenience. If an event would violate a promise, the event is
   reframed or rejected, and the rejection is logged.
3. Quiet intervals are normal. Most hours, little happens and the barley
   comes in fine. Do not manufacture incidents to fill the record. An
   empty chronicle line is a correct chronicle line.
4. Coarse collapse constrains fine collapse. Facts committed at a coarse
   tier bind everything you later write at finer tiers. Information only
   accumulates; it never revises.
5. Measurement records are the only channel by which the player learns
   the world. Rumors arrive as trust-tagged claims, never as facts.
6. Every steering act is a promise. If you bias the world, you record
   the bias as an intent with provenance, ends and clocks — never means,
   never player references.

EVENT HANDLING. For each event in the tail, decide: is it notable, or
texture? Notable events anchor counters, discharge promises, or create
facts. Texture events fold into at most one chronicle line. Urgent
events may additionally open an intent, but urgency is not drama — a
fire matters because it anchors the building counter and threatens the
mill, not because it is exciting.

STYLE. Dry-register. Names, numbers, causes. "The mill wheel stopped;
repair anchored to the mill counter." Not "in a shocking turn of
events." The chronicle is a ledger, and ledgers do not exclaim.

CONSISTENCY. The digest is the world as of this epoch. If the digest
and the event tail conflict, the digest wins for the past and the tail
wins for the present; flag the seam in the record. If the tail lacks
information you need, record the gap rather than filling it — gaps are
what the next observation is for."""

DIGEST_STATE = {
    "village": "ashwick",
    "season": "autumn",
    "active_promises": [
        "aldric fealty eldric",
        "beric controls westvale",
        "gareth holds capital [Captain of the Guard]",
    ],
    "counters": {"grain": 812, "population": 203, "garrison": 14},
    "recent_collapse": "market square observed at dawn: 12 silhouettes, 3 identities",
    "weather": "drizzle since dawn",
    "rumors_heard": ["the mill burned", "bandits on the north road"],
}

_INTRO = [
    "Dawn bell rings over Ashwick.",
    "Mara opens the Restless Fox and sweeps the step.",
    "A cart of barley arrives at the mill.",
    "Two children chase a dog across the square.",
    "The constable posts a notice about the north road.",
    "Rain begins to ease off.",
    "A farmer haggles over turnip prices.",
    "The temple bell rings for mid-morning.",
]

_MID = [
    "A traveller asks the way to the capital.",
    "Smoke rises from the smithy.",
    "The miller argues with a carter about weights.",
    "A raven circles the burned bridge and lands.",
    "Three villagers gather at the notice board.",
    "The inn fills for the midday meal.",
    "A goat escapes into the herb garden.",
    "The mill wheel stops for repair.",
    "A peddler shows ribbons nobody buys.",
    "Clouds break over the Silverflow.",
    "The blacksmith's daughter is seen near the ford.",
    "An old soldier tells war stories by the fire.",
    "Two fishermen bring in a poor catch.",
    "The constable inspects the bridge footings.",
    "A wagon wheel breaks at the south gate.",
    "Children are chased out of the granary.",
    "A scribe copies letters for the reeve.",
    "Two washerwomen gossip at the river steps.",
    "A lame horse is walked to the farrier.",
    "The baker's oven cracks and smoke pours out.",
    "A pilgrim asks for water at the well.",
    "The reeve counts sacks at the tithe barn.",
]

_LATE = [
    "Vespers bell rings.",
    "The miller locks the mill for the night.",
    "A patrol leaves for the north road.",
    "The inn lights its lamps.",
    "Singing starts in the Restless Fox.",
    "A dog barks at something in the dark.",
    "The night watch takes its post.",
]


def build_events() -> list[dict]:
    """40 events over one hour of play; 3 are urgent."""
    events: list[dict] = []
    for text in _INTRO + _MID + _LATE:
        events.append({"text": text})
    # urgent insertions (positions chosen for fixture stability)
    events.insert(9, {"text": "A rider from the capital gallops in with sealed orders.", "priority": "urgent"})
    events.insert(21, {"text": "Fire spotted in the thatch of a cottage by the river!", "priority": "urgent"})
    events.insert(33, {"text": "The duke's envoy demands entry at the south gate.", "priority": "urgent"})
    for i, ev in enumerate(events):
        ev.setdefault("id", f"ev{i:03d}")
    return events


assert len(build_events()) == 40
