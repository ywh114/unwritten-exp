"""K6 demo fixture — 50-NPC village contact graph.

Watts–Strogatz graph (n=50, k=6, p=0.1) seeded from a K1 stream, per
the determinism rule.  The rumor: "the mill burned" at the riverside mill
on day 0, magnitude 1.0, injected at node 0.
"""

import networkx as nx

from kernel.hashrng import Stream

from exp.k6_gossip.rumor import Rumor


def build_graph(world_seed: int) -> nx.Graph:
    """50-NPC Watts–Strogatz contact graph, seed derived from K1."""
    seed = Stream(world_seed, "k6.fixture.graph").randrange(2**31, 0, 0)
    return nx.watts_strogatz_graph(50, 6, 0.1, seed=int(seed))


def build_rumor() -> Rumor:
    return Rumor(
        subject="mill",
        event="burned",
        location="riverside mill",
        day=0.0,
        magnitude=1.0,
    )


def injected_node() -> int:
    return 0
