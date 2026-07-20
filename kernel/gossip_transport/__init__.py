"""K6 — gossip_transport: mechanical rumor diffusion over a contact graph.

Rumors are structured records that degrade per hop (field drops,
mutations, magnitude drift) while trust decays exponentially.  The
contact graph is the ONLY channel from the unobserved world (design
spec §5.3).  Traceability walks trust gradients — no teller chain.
LLM delivery is out of scope (that's C3).

Promoted from exp/k6_gossip (2026-07-19, verdict: works).  The exp/
directory keeps the demo, fixtures, and tests as living documentation.
"""

from kernel.gossip_transport.rumor import Belief, Rumor, perturb
from kernel.gossip_transport.network import GossipNetwork, GossipParams

__all__ = ["Rumor", "Belief", "perturb", "GossipNetwork", "GossipParams"]
