"""C2 — backfill pipeline: 5-stage lazy-history over a fixture village.

1. Evaluate counters (K4) — fact anchors
2. Sample eventfulness (C1) — k = notable events
3. Generate (L1 T1-flash) — SeasonChronicle
4. Validate (mechanical) — count, resurrection, counter_agreement, chekhov
5. Commit (K5 + K7) — discharges, expires, facts
"""

from __future__ import annotations

from capability.eventfulness import sample_count
from kernel.hashrng import Stream
from kernel.promise_ledger import Promise
from llm.llm_client import LLMClient, Tier

from capability.backfill.commit import commit_chronicle
from capability.backfill.schema import Village
from capability.backfill.schema import BackfillResult, SeasonChronicle
from capability.backfill.validate import validate_chronicle

FLAT_EPSILON = 1e-6


# ---- prompt building ----------------------------------------------------------


def _npc_cards_text(npcs) -> str:
    """Compact one-liner NPC cards, dead NPCs marked DEAD."""
    lines = []
    for n in npcs:
        tag = " [DEAD]" if n.dead else ""
        lines.append(f"  {n.slug}: {n.name}, {n.role}. {n.state}{tag}")
    return "\n".join(lines)


def _counters_text(counter_anchors: dict[str, tuple[float, float, str]]) -> str:
    """Counter anchors with directions — FACT ANCHORS, immovable."""
    lines = []
    for name, (v0, v1, direction) in sorted(counter_anchors.items()):
        lines.append(
            f"  {name}: {v0:.1f} → {v1:.1f} ({direction})"
        )
    return "\n".join(lines)


def _due_promises_text(due: list[Promise]) -> str:
    """Due promises that must be resolved this season."""
    if not due:
        return "  (none)"
    lines = []
    for p in due:
        lines.append(
            f"  {p.id}: {p.predicate.narrative()} "
            f"(due by t={p.window[1]:.0f}, provenance={p.provenance})"
        )
    return "\n".join(lines)


def _active_promises_text(active: list[Promise]) -> str:
    """All active promises for context."""
    if not active:
        return "  (none)"
    lines = []
    for p in active:
        end = f"t={p.window[1]:.0f}" if p.window[1] is not None else "perpetual"
        lines.append(
            f"  {p.id}: {p.predicate.narrative()} "
            f"(window={p.window[0]:.0f}–{end}, provenance={p.provenance})"
        )
    return "\n".join(lines)


def build_backfill_prompt(
    village: Village,
    counter_anchors: dict[str, tuple[float, float, str]],
    due_promises: list[Promise],
    active_promises: list[Promise],
    k: int,
    dt: float,
) -> str:
    """Build the structured prompt for the LLM."""
    npc_text = _npc_cards_text(village.npcs)
    counter_text = _counters_text(counter_anchors)
    due_text = _due_promises_text(due_promises)
    active_text = _active_promises_text(active_promises)

    return (
        "You are the chronicler of a medieval village. A season has passed.\n"
        "Below are the immutable facts. You generate the narrative.\n\n"
        "--- VILLAGE CONTEXT ---\n"
        f"{npc_text}\n\n"
        "--- COUNTER ANCHORS (immovable) ---\n"
        f"{counter_text}\n\n"
        "--- DUE PROMISES (must be discharged this season) ---\n"
        f"{due_text}\n\n"
        "--- ALL ACTIVE PROMISES (context) ---\n"
        f"{active_text}\n\n"
        "--- TASK ---\n"
        f"Δt = {dt:.0f} days (one season). k = {k} notable events.\n"
        "Generate EXACTLY k events. Each event:\n"
        "- title: one dry sentence\n"
        "- kind: one of death/birth/conflict/economic/weather/social/discharge/other\n"
        "- involves: list of NPC slugs (from the cards above; may be empty)\n"
        "- promise_discharge: null, or the EXACT hex identifier of a DUE promise "
        "that this event resolves. Copy it character-for-character from the DUE "
        "PROMISES list above — for example \"a8b274ffafb50c79\". Do not invent "
        "or shorten the ID.\n\n"
        "Rules:\n"
        "1. Every due promise MUST appear as some event's promise_discharge, "
        "using its exact hex ID from the list.\n"
        "2. You must produce ONE CounterNote per counter listed above, with the "
        "direction matching exactly what is stated (the numbers are fact).\n"
        "3. Never involve a DEAD NPC in any event.\n"
        "4. The texture_line is a single-sentence atmospheric wrap-up of the season.\n"
        "5. Provide exactly the JSON object with fields: events, counter_notes, texture_line."
    )


# ---- pipeline -----------------------------------------------------------------


def backfill(
    village: Village,
    t0: float,
    t1: float,
    client: LLMClient,
    stream: Stream,
    *,
    max_retries: int = 1,
) -> BackfillResult:
    """Run the full five-stage backfill pipeline.

    Returns a BackfillResult whether or not the chronicle was accepted;
    caller inspects .accepted.
    """
    clock = stream.world_seed  # use seed as logical clock

    # ---- Stage 1: evaluate counters ----
    counter_anchors: dict[str, tuple[float, float, str]] = {}
    for name, counter in sorted(village.counters.items()):
        v0 = counter.value_at(t0)
        v1 = counter.value_at(t1)
        if abs(v1 - v0) < FLAT_EPSILON:
            direction = "flat"
        elif v1 > v0:
            direction = "up"
        else:
            direction = "down"
        counter_anchors[name] = (v0, v1, direction)

    # ---- Stage 2: sample eventfulness ----
    k = sample_count(stream, clock, "season")

    # ---- Stage 3 & 4: generate + validate (retry loop) ----
    dt = t1 - t0
    due_promises = [
        p for p in village.ledger.active()
        if p.window[1] is not None and t0 <= p.window[1] <= t1
    ]

    # k must cover at least the due promises (one event can discharge
    # multiple promises, but enforce minimum coverage)
    k = max(k, len(due_promises))
    active_promises = village.ledger.active()

    prompt = build_backfill_prompt(
        village, counter_anchors, due_promises, active_promises, k, dt,
    )

    violations_history: list[list[str]] = []
    chronicle: SeasonChronicle | None = None
    attempts = 0
    accepted = False

    for attempt in range(1, max_retries + 2):  # initial + retries
        attempts = attempt
        messages = [{"role": "user", "content": prompt}]

        if violations_history:
            # retry-with-warning: feed back violations
            prev_violations = violations_history[-1]
            warning = (
                "Your previous output failed validation:\n"
                + "\n".join(f"  - {v}" for v in prev_violations)
                + "\nRespond again with valid JSON only, fixing these issues."
            )
            messages.append({"role": "user", "content": warning})

        result = client.call(
            Tier.T1_FLASH,
            messages,
            schema=SeasonChronicle,
            purpose="c2.backfill",
            clock=clock,
            max_tokens=1024,
        )

        chronicle = result.parsed
        violations = validate_chronicle(
            chronicle, k, village.dead_slugs,
            counter_anchors, due_promises,
        )
        violations_history.append(violations)

        if not violations:
            accepted = True
            break

    assert chronicle is not None

    # ---- Stage 5: commit (only if accepted) ----
    events: list[BackfillEvent] = list(chronicle.events)
    discharges: list[str] = []
    chronicle_text = ""

    if accepted:
        discharges, chronicle_text = commit_chronicle(
            village, chronicle, t0, t1, due_promises, counter_anchors,
        )

    cost_entries = list(client.cost_log.entries)

    return BackfillResult(
        events=events,
        discharges=discharges,
        counter_anchors=counter_anchors,
        chronicle_text=chronicle_text,
        attempts=attempts,
        accepted=accepted,
        violations_history=violations_history,
        cost_entries=cost_entries,
    )
