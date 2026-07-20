"""K6 experiment — gossip transport: mechanical rumor diffusion over a contact graph.

The library itself lives here until promotion to kernel/ (per lab spec §6
promotion rule, the reviewer decides).
"""

from exp.k6_gossip.rumor import Rumor, Belief, perturb
from exp.k6_gossip.network import GossipParams, GossipNetwork

__all__ = ["Rumor", "Belief", "perturb", "GossipParams", "GossipNetwork"]
