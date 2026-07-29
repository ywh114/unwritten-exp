"""K14 model — the K13 Node/Tree model re-exported unchanged.

Flora ranks map onto the same Rank enum (owner ruling: interface
mirroring): KINGDOM = the flora root (plantae+honorary), PHYLUM = line
(seed plants / spore plants / decomposers), CLASS = growth-form plan,
ORDER = clade-steady tuple (flower architecture, fruit family, root
family, chemistry, photosynthesis grade, mycorrhizal dependence, Hallé
grammar), FAMILY = narrowed parameter ranges, GENUS = folk label,
SPECIES = the committed species record.
"""

from exp.k13_treegen.model import (  # noqa: F401
    NameRecord, Node, Provenance, QuantityStore, Rank, Tree)
