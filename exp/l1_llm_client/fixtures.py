"""L1 demo fixtures: the shared schema and prompts used across tiers."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VillageRumor(BaseModel):
    """Structured output schema for the demo and tests."""

    headline: str = Field(description="one line, under 12 words")
    subject: str = Field(description="who the rumor is about")
    severity: int = Field(ge=1, le=5, description="1 trivial, 5 village-shaking")
    involves_mill: bool


PROMPT = [
    {
        "role": "user",
        "content": (
            "Invent one rumor currently circulating in the village of Ashwick. "
            "The village has a mill on the river, an inn called the Restless Fox, "
            "and a burned bridge. Return the structured record."
        ),
    }
]
