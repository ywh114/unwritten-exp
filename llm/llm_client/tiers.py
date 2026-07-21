"""L1 — tier routing.

The four tiers (design spec §7.1): T0 grammar (local, zero-model),
T1 flash, T2 flash-thinking, T3 pro. Verified against the live API
(2026-07-20): only two model ids exist — `deepseek-v4-flash` and
`deepseek-v4-pro`; flash "thinks" by default and accepts
`thinking: {"type": "disabled"}`, so T1/T2 share a model and differ
only in the thinking flag.
"""

from __future__ import annotations

from enum import StrEnum


class Tier(StrEnum):
    T0_GRAMMAR = "t0_grammar"
    T1_FLASH = "t1_flash"
    T2_FLASH_THINKING = "t2_flash_thinking"
    T3_PRO = "t3_pro"


MODEL_IDS = {
    Tier.T1_FLASH: "deepseek-v4-flash",
    Tier.T2_FLASH_THINKING: "deepseek-v4-flash",
    Tier.T3_PRO: "deepseek-v4-pro",
}

# T2 thinks; T1 is the same model with thinking disabled. T0 never
# reaches the API (local grammar tier).
TIER_THINKING = {
    Tier.T1_FLASH: False,
    Tier.T2_FLASH_THINKING: True,
    Tier.T3_PRO: False,
}

# USD per 1M tokens: (cached_input, uncached_input, output).
# Verified 2026-07-20 against https://api-docs.deepseek.com/quick_start/pricing
# — flash rates match engine spec §7.5 exactly; pro rates replace the
# earlier 3x inference (real: cached 1.29x, miss 3.1x, out 3.1x flash).
# Prices drift — re-verify before relying on absolute dollars (L2 owns
# the §7.5 envelope check).
PRICE_TABLE = {
    "deepseek-v4-flash": (0.0028, 0.14, 0.28),
    "deepseek-v4-pro": (0.003625, 0.435, 0.87),
}
