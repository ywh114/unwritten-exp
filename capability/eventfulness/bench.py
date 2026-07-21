"""C1 — eventfulness bench: the two arms over LLM calls.

- Unconditioned arm: no count hint → soap-opera bias (too many events).
- Conditioned arm: the calibrated sampler supplies the exact count →
  the model fills in content only; quiet intervals are few-shotted.

All LLM calls go through `llm.llm_client.LLMClient` at Tier T1_FLASH.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field

from kernel.hashrng import Stream
from llm.llm_client import Tier, LLMClient, CallResult, CostLog

from capability.eventfulness.sampler import SCALES, sample_count


# ---------------------------------------------------------------------------
# Structured-output schema
# ---------------------------------------------------------------------------


class IntervalChronicle(BaseModel):
    notable_events: list[str] = Field(
        description="One short line per notable event; [] if nothing happened"
    )
    texture_line: str = Field(
        description="One dry sentence describing the village texture / atmosphere"
    )


# ---------------------------------------------------------------------------
# Few-shots (the quiet-interval examples)
# ---------------------------------------------------------------------------

_QUIET_FEWSHOTS = [
    {
        "notable_events": [],
        "texture_line": "Nothing happened; the barley came in fine.",
    },
    {
        "notable_events": [],
        "texture_line": "An uneventful stretch. The village settled into its rhythms.",
    },
]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _system_prompt(context: str) -> str:
    return (
        f"You are the chronicler of the village. {context}\n\n"
        f"Write a chronicle entry for one interval. "
        f"Return a JSON object with 'notable_events' (list of strings, "
        f"one short sentence per event) and 'texture_line' (one dry "
        f"sentence of village atmosphere).\n\n"
    )


def build_prompt_unconditioned(scale: str, label: str, context: str = "") -> list[dict]:
    """No count hint — the unconditioned arm."""
    return [
        {"role": "system", "content": _system_prompt(context)},
        {"role": "user", "content": (
            f"Write the chronicle for this {scale}: {label}."
        )},
    ]


def build_prompt_conditioned(scale: str, label: str, k: int, context: str = "") -> list[dict]:
    """Exact count + quiet-interval few-shots (proper user/assistant
    example pairs before the final instruction)."""
    import json as _json

    msgs = [{"role": "system", "content": _system_prompt(context)}]
    if k == 0:
        for fs in _QUIET_FEWSHOTS:
            msgs.append({
                "role": "user",
                "content": f"Write the chronicle for this {scale} (example).",
            })
            msgs.append({
                "role": "assistant",
                "content": _json.dumps({
                    "notable_events": fs["notable_events"],
                    "texture_line": fs["texture_line"],
                }),
            })
        msgs.append({
            "role": "user",
            "content": (
                f"Write the chronicle for this {scale}: {label}. "
                f"Nothing notable happened this {scale}. "
                f"Record an empty event list and one texture line."
            ),
        })
    else:
        msgs.append({
            "role": "user",
            "content": (
                f"Write the chronicle for this {scale}: {label}. "
                f"Exactly {k} notable event{'s' if k != 1 else ''} happened "
                f"this {scale}. List exactly {k}; no more, no fewer."
            ),
        })
    return msgs


# ---------------------------------------------------------------------------
# Arm runner
# ---------------------------------------------------------------------------


@dataclass
class ArmReport:
    results: list[dict]   # per-interval: {id, k_requested, k_measured, chronicle}
    cost_log: CostLog      # accumulated cost
    total_calls: int


def run_arm(
    client: LLMClient,
    stream: Stream,
    intervals: list[dict],
    *,
    conditioned: bool,
    context: str = "",
) -> ArmReport:
    cost_log = CostLog()
    results: list[dict] = []

    for i, iv in enumerate(intervals):
        scale = iv["scale"]
        label = iv["label"]
        if conditioned:
            k = sample_count(stream, i, scale)
            msgs = build_prompt_conditioned(scale, label, k, context)
        else:
            k = -1  # unknown
            msgs = build_prompt_unconditioned(scale, label, context)

        result = client.call(
            Tier.T1_FLASH,
            msgs,
            schema=IntervalChronicle,
            purpose="c1_eventfulness",
            clock=i,
            max_tokens=256,
        )
        cost_log.append(result.cost)

        k_measured = 0
        chronicle_text = ""
        if result.parsed is not None:
            k_measured = len(result.parsed.notable_events)
            chronicle_text = " | ".join(result.parsed.notable_events)
            if result.parsed.texture_line:
                chronicle_text += f"  [{result.parsed.texture_line}]"

        results.append({
            "id": iv["id"],
            "scale": scale,
            "label": label,
            "k_requested": k,
            "k_measured": k_measured,
            "chronicle": chronicle_text,
        })

    return ArmReport(results=results, cost_log=cost_log, total_calls=len(intervals))
