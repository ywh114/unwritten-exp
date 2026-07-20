"""K6 — gossip network: rumor diffusion over a contact graph.

Daily, simultaneous tells: every believer tells every neighbour with
probability `p_tell`.  Tells deliver a perturbed version of the
believer's rumor with trust multiplied by `tau`.  The graph is the
ONLY channel from the unobserved world (design spec §5.3).

Traceability flows backwards along trust gradients — no teller chain
is stored, only the belief state.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

import networkx as nx

from kernel.hashrng import Stream

from exp.k6_gossip.rumor import Belief, Rumor, perturb

# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

# Bandwidth per day for draw indices — 1M indices leaves room for
# ~50K directed edges with 10 indices each.  Well above the 50-NPC
# fixture (~600 directed edges).
_DAY_BAND = 1_000_000


@dataclass(frozen=True)
class GossipParams:
    p_tell: float = 0.5
    tau: float = 0.85
    q_drop: float = 0.1
    q_mut: float = 0.05
    sigma_drift: float = 0.1


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


@dataclass
class GossipNetwork:
    """Mechanical rumor diffusion over a contact graph.

    `graph` is an undirected `nx.Graph` where nodes are integer ids.
    `world_seed` seeds all draws via K1 `Stream`.
    """

    graph: nx.Graph
    params: GossipParams
    world_seed: int

    # internal state ---------------------------------------------------------
    _beliefs: dict[tuple[int, str, str], Belief] | None = None
    # key = (node, subject, event_class)
    _clock_offset: int = 0  # next unused clock value

    def _stream(self, clock: int) -> Stream:
        return Stream(self.world_seed, f"k6.gossip.{clock}")

    # ---- injection ---------------------------------------------------------

    def inject(self, node: int, rumor: Rumor, trust: float = 1.0) -> None:
        if self._beliefs is None:
            self._beliefs = {}
        key = (node, rumor.subject, rumor.event_class)
        # injection is ground truth — always replaces
        self._beliefs[key] = Belief(rumor=rumor, trust=trust, heard_day=0)

    # ---- queries -----------------------------------------------------------

    def belief(self, node: int) -> Belief | None:
        """Return the *highest-trust* belief a node holds for any
        (subject, event_class) — or None if the node holds nothing."""
        if self._beliefs is None:
            return None
        best = None
        for (n, subj, ecls), b in self._beliefs.items():
            if n == node:
                if best is None or b.trust > best.trust:
                    best = b
        return best

    def believers(self) -> list[int]:
        """All nodes that currently hold at least one belief."""
        if self._beliefs is None:
            return []
        return sorted({n for (n, _, _) in self._beliefs})

    # ---- propagation -------------------------------------------------------

    def propagate(self, days: int, clock0: int = 0) -> None:
        """Forward-simulate `days` days of simultaneous tells."""

        # Enumerate directed edges once (sorted for determinism)
        directed: list[tuple[int, int]] = []
        for u in sorted(self.graph.nodes):
            for v in sorted(self.graph.neighbors(u)):
                directed.append((u, v))
        E = len(directed)

        for d in range(days):
            clock = clock0 + d
            day_base = d * _DAY_BAND
            prev_beliefs = self._beliefs.copy() if self._beliefs else {}

            # Generate all tells from start-of-day beliefs.
            tells: list[tuple[int, Belief]] = []  # (recipient, belief)
            stream = self._stream(clock)

            for e, (u, v) in enumerate(directed):
                idx_base = e * 10
                # try every belief held by u at start-of-day
                for (n, subj, ecls), belief in prev_beliefs.items():
                    if n != u:
                        continue
                    if stream.bernoulli(self.params.p_tell, clock,
                                        day_base + idx_base):
                        rumor2 = perturb(belief.rumor, stream, clock,
                                         day_base + idx_base + 1,
                                         self.params.q_drop, self.params.q_mut,
                                         self.params.sigma_drift)
                        new_trust = belief.trust * self.params.tau
                        tells.append((v, Belief(rumor=rumor2, trust=new_trust,
                                                 heard_day=d)))
                    break  # one belief per node per subject in fixture

            # Apply tells — simultaneous (all against start-of-day state)
            if self._beliefs is None:
                self._beliefs = {}
            for v, belief in tells:
                key = (v, belief.rumor.subject, belief.rumor.event_class)
                old = self._beliefs.get(key)
                if old is None or belief.trust > old.trust:
                    self._beliefs[key] = belief
                # equal trust → keep incumbent (no-op)

        self._clock_offset += days * _DAY_BAND

    # ---- traceability ------------------------------------------------------

    def trace_source(self, start_node: int) -> int | None:
        """Walk the trust gradient back toward the rumor's source.

        From `start_node`, repeatedly move to a neighbour that holds a
        belief about the same `subject` with strictly higher trust.
        Stop when no such neighbour exists.  Return the stop node,
        or None if the start node has no belief about fixture subjects.
        """
        if self._beliefs is None:
            return None
        # get the subject from the start node's highest-trust belief
        b = self.belief(start_node)
        if b is None:
            return None
        subject = b.rumor.subject
        current = start_node
        current_trust = b.trust

        while True:
            best_nbr = None
            best_trust = current_trust
            for nbr in sorted(self.graph.neighbors(current)):
                for (n, subj, ecls), nb in self._beliefs.items():
                    if n == nbr and subj == subject and nb.trust > best_trust:
                        best_trust = nb.trust
                        best_nbr = nbr
            if best_nbr is None:
                return current
            current = best_nbr
            current_trust = best_trust

    def localization_rate(self, true_source: int) -> float:
        """Fraction of believers whose trace-source prediction is within
        2 graph hops of `true_source`."""
        believers = self.believers()
        if not believers:
            return 0.0
        hits = 0
        for node in believers:
            pred = self.trace_source(node)
            if pred is None:
                continue
            dist = nx.shortest_path_length(self.graph, pred, true_source)
            if dist <= 2:
                hits += 1
        return hits / len(believers)
