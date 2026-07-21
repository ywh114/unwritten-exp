"""L1 — T0: the grammar/template tier. Zero-model content, zero tokens.

Templates expand compact structured records into varied prose without an
LLM call (design spec §5.4: "LLM as compressor; grammars as
decompressor"). All choices are K1-stream draws — deterministic.
"""

from __future__ import annotations

from kernel.hashrng import Stream

# Slot tables per template. Deliberately tiny: this tier's job is to
# prove zero-model content exists and costs nothing, not to be rich.
_TEMPLATES: dict[str, dict] = {
    "rumor_headline": {
        "subject": ["the miller", "the innkeeper", "the blacksmith", "the constable"],
        "verb": ["was seen arguing with", "owes money to", "is feuding with", "was heard praising"],
        "object": ["a travelling merchant", "the duke's envoy", "a jealous neighbour", "the miller"],
    },
    "weather_line": {
        "sky": ["Low grey clouds", "A hard clear sky", "Drizzle since dawn", "Wind off the river"],
        "mood": ["kept everyone indoors.", "slowed the market.", "was good for the barley.", "made the roads mud."],
    },
}


def render(template_id: str, stream: Stream, clock: int) -> str:
    """Expand a template deterministically. Slots render in definition
    order (sentence order); slot i draws at index i."""
    if template_id not in _TEMPLATES:
        raise KeyError(f"unknown template {template_id!r}")
    slots = _TEMPLATES[template_id]
    parts = []
    for i, (slot, options) in enumerate(slots.items()):
        parts.append(options[stream.randrange(len(options), clock, i)])
    return " ".join(parts)


def templates() -> list[str]:
    return sorted(_TEMPLATES)
