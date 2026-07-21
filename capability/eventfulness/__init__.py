"""C1 — eventfulness: sampled quantity vs. narrated quantity.

The count of notable events in an interval is rolled mechanically
(zero-inflated Poisson over a K1 stream); the LLM supplies only
content.  Conditioning is measured to remove the soap-opera bias
(unconditioned zero-rate 0.000 → conditioned 0.410, obedience 1.000 —
see docs/spec-notes/2026-07-20-c1-eventfulness-calibration.md).

Promoted from exp/c1_eventfulness (2026-07-20, verdict: works).  The
exp/ directory keeps the demo, fixtures, tests, and cassettes as living
documentation.
"""

from capability.eventfulness.sampler import SCALES, sample_count, target_distribution
from capability.eventfulness.bench import (
    ArmReport,
    IntervalChronicle,
    build_prompt_conditioned,
    build_prompt_unconditioned,
    run_arm,
)

__all__ = [
    "SCALES", "sample_count", "target_distribution",
    "ArmReport", "IntervalChronicle",
    "build_prompt_conditioned", "build_prompt_unconditioned", "run_arm",
]
