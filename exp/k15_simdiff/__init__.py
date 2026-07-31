"""K15 — sim-diff: the round engine (dispersal, stress adapter, cover,
rounds, commit). Slot reserved in specs/LEDGER.md.

Currently holds the B5 flora stress adapter (the env side of the stress
channel): ``stress_adapter`` evaluates biosphere addendum B5's signed
stress per flora record over the world at anchor resolution; ``__main__``
is the B5 §8 acceptance/demo driver; ``req_flora`` pins the env-defined
requirement-name vocabulary; the kernel/stress contract tests live here.
"""

from exp.k15_simdiff.req_flora import V1_FLORA  # noqa: F401  (re-export)

__all__ = ["V1_FLORA"]
