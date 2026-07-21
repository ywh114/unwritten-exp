"""C2 — commit: apply a validated chronicle to the village state.

Discharges due promises, expires old promises, ingests promises as wiki
facts, writes events as wiki facts, and returns a dry-register chronicle
rendering.
"""

from __future__ import annotations

from kernel.wiki_store import make_fact

from capability.backfill.schema import Village
from capability.backfill.schema import SeasonChronicle


def commit_chronicle(
    village: Village,
    chronicle: SeasonChronicle,
    t0: float,
    t1: float,
    due_promises,  # list[Promise]
    counter_anchors: dict[str, tuple[float, float, str]] | None = None,
) -> tuple[list[str], str]:
    """Commit a validated chronicle to the ledger and wiki.

    Returns:
      - discharges: promise ids discharged
      - chronicle_text: dry-register rendering of the season
    """
    discharges: list[str] = []

    # Discharge promises that were resolved in this chronicle
    resolved_ids: set[str] = set()
    for event in chronicle.events:
        if event.promise_discharge:
            resolved_ids.add(event.promise_discharge)

    for p in due_promises:
        if p.id in resolved_ids:
            village.ledger.discharge(p.id, note="resolved this season")
            discharges.append(p.id)

    # Expire all promises whose window closed by t1
    expired = village.ledger.expire(t1)

    # Ingest discharged and expired promises as wiki facts
    for pid in discharges + expired:
        p = village.ledger.get(pid)
        if p is not None:
            village.wiki.ingest_promise(p, t1)

    # Write counter-anchor facts (one per counter)
    if counter_anchors:
        for name, (v0, v1, direction) in sorted(counter_anchors.items()):
            fact_text = f"[counter] {name}: {v0:.1f} → {v1:.1f} ({direction})"
            village.wiki.write(
                make_fact(
                    text=fact_text,
                    trust=1.0,
                    importance="notable",
                    provenance="counter",
                    valid_from=t0,
                )
            )

    # Write each event as a wiki fact
    for event in chronicle.events:
        fact_text = f"[{event.kind}] {event.title}"
        if event.involves:
            fact_text += f" — {', '.join(event.involves)}"

        village.wiki.write(
            make_fact(
                text=fact_text,
                trust=0.9,
                importance="notable",
                provenance="canon",
                valid_from=t0,
            )
        )

    # Dry-register chronicle rendering
    chronicle_lines: list[str] = []

    chronicle_lines.append(f"Season t={t0:.0f}–{t1:.0f} ({len(chronicle.events)} events)")
    chronicle_lines.append("")

    for i, event in enumerate(chronicle.events, 1):
        chronicle_lines.append(f"  [{i}] [{event.kind}] {event.title}")
        if event.involves:
            chronicle_lines.append(f"      involves: {', '.join(event.involves)}")
        if event.promise_discharge:
            chronicle_lines.append(f"      discharges promise: {event.promise_discharge}")

    chronicle_lines.append("")
    chronicle_lines.append(f"  texture: {chronicle.texture_line}")

    if discharges:
        chronicle_lines.append("")
        chronicle_lines.append("  discharges:")
        for pid in discharges:
            p = village.ledger.get(pid)
            if p:
                chronicle_lines.append(f"    {pid}: {p.predicate.narrative()}")

    if expired:
        chronicle_lines.append("")
        chronicle_lines.append("  expired:")
        for pid in expired:
            p = village.ledger.get(pid)
            if p:
                chronicle_lines.append(f"    {pid}: {p.predicate.narrative()}")

    chronicle_text = "\n".join(chronicle_lines)
    return discharges, chronicle_text
