"""C2 — mechanical validation of generated chronicles.

Each violation is a named string.  The pipeline retries (with the violation
list fed back as a warning) if ANY check fails.
"""

from __future__ import annotations


def validate_chronicle(
    chronicle,            # SeasonChronicle
    k: int,
    dead_slugs: set[str],
    counter_anchors: dict[str, tuple[float, float, str]],
    due_promises,         # list[Promise]
) -> list[str]:
    """Validate a generated SeasonChronicle.  Returns list of violation
    strings; empty list = clean."""
    violations: list[str] = []

    # 1. count — len(events) == k
    if len(chronicle.events) != k:
        violations.append(
            f"count: expected {k} events, got {len(chronicle.events)}"
        )

    # 2. resurrection — no DEAD NPC slug in any event's involves
    resurrected: list[str] = []
    for event in chronicle.events:
        for slug in event.involves:
            if slug in dead_slugs:
                resurrected.append(f"{slug} in '{event.title}'")
    if resurrected:
        violations.append(
            f"resurrection: dead NPCs involved — " + "; ".join(resurrected)
        )

    # 3. counter_agreement — every counter has a note with matching direction
    noted_counters: set[str] = set()
    for note in chronicle.counter_notes:
        noted_counters.add(note.counter)
        expected = counter_anchors.get(note.counter)
        if expected is None:
            violations.append(
                f"counter_agreement: unknown counter '{note.counter}' in notes"
            )
        elif note.direction != expected[2]:
            violations.append(
                f"counter_agreement: {note.counter} noted as {note.direction!r} "
                f"but measured as {expected[2]!r}"
            )

    missing = set(counter_anchors) - noted_counters
    if missing:
        violations.append(
            f"counter_agreement: missing notes for counters: {sorted(missing)}"
        )

    # 4. chekhov — every due promise appears as some event's promise_discharge
    discharged_in_chronicle: set[str] = set()
    for event in chronicle.events:
        if event.promise_discharge:
            discharged_in_chronicle.add(event.promise_discharge)

    due_ids = {p.id for p in due_promises}
    missing_due = due_ids - discharged_in_chronicle
    if missing_due:
        violations.append(
            f"chekhov: due promises not discharged in chronicle: "
            + ", ".join(sorted(missing_due))
        )

    # extra discharges (not due) are NOT a violation — they're just
    # forward-looking. But we do not check for them as errors.

    return violations


# Human-readable type alias for use in demo and tests
Violation = str
