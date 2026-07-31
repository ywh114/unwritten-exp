"""The organism/environment sim contract — organism side (K13).

THE MODEL (user rulings, 2026-07-31): checkout/commit.

- The TREE (K13) is the authority and owns every decision: drift,
  merge, subspecies, split, extinction, and ops we have not designed
  yet. It exposes an update method and nothing else to the sim.
- X (``Instance``) is a WORKING COPY of species state, minted by the
  tree and handed to the sim. X is keyed by (species ID, instance ID):
  one species, many gene-pool instances. X carries the WIP genes.
- The sim DRESSES X with spatiotemporal data (density fields over
  cells). The dressed bundle is sim-side property; the tree never
  sees it, and K13 never sees a cell. K13 is space-blind by design.
- STRESS IS THE ONLY env->X channel. Competition, predation
  (source-typed: avian/terrestrial/...), productivity, positive
  resource signals — all travel inside the one verdict. There is no
  lateral X<->X channel; speciation is a hard reproductive barrier,
  so gene flow cannot cross species boundaries (infertile-offspring
  nuance is L2 detail). Provenance names are prefix-typed into four
  dispatch classes (organism-side dispatch on env-defined names):
  "pressure:" (or plain) -> DEFENSIVE pressure: reduce/endure a
  mismatch with what the organism already is, UNGATED — you always
  answer what hurts you; "pull:<resource>" -> OPPORTUNITY pull: a tug
  toward exploiting an available resource, regardless of current
  suitability, GATED by total stress: response ~ (some power p of)
  total stress, so comfortable populations (s ~ 0) ignore pulls
  entirely and only stressed ones chase opportunities — pull is an
  escape valve, not a lure; p is organism-side content. Ley radiation
  counts as stress here, so irradiated lineages both unlock illegal
  targets and chase them. Organism-side the pull vector is also
  NORMALIZED over competing pulls (weight ~ availability x
  exploitation-gap, divided by the total): one dominant resource
  pulls hard (specialize); many comparable pulls cancel to noise
  (stay general) — abundance-induced generalism is emergent, no
  anti-specialization dial. Then "ley:" -> gate credit, "lift:" ->
  event trigger (below).
- DISPERSAL: the sim CLONES X (keeping WIP genes) and dresses the
  clone. Partition policy is sim-internal — this contract holds no
  opinion about why instances split or merge — but the settled
  mechanics are: partition = MOBILITY-KERNEL CONNECTED COMPONENTS
  (edge where the instance's kernel can actually traverse; NOT
  geometric/voronoi, which ignores terrain), sticky across rounds to
  encourage divergence, recomputed only on major range change, with a
  FINAL pass merging non-differentiated instances so the committed
  tree carries no meaningless partitions. Same-species instances do
  not diffuse into each other: foreign-instance rain is con-specific
  competition in the same niche, so the density term already crushes
  establishment where residents saturate productivity — the contact
  zone stays sharp with no special casing (add an explicit
  resident-priority discount only if this proves leaky). Genesis
  partition rate is the one stochastic knob.
- COMMIT: at round end the sim hands a flat list of parsed views to
  tree.update(). The tree amends records gerrit-style (reflog holds
  history; no micro-nodes for drift), classifies each instance
  three-way — re-merge (only if really similar), SUBSPECIES node
  (a real divide, deliberately rare: the divergence band is narrow),
  or SPLIT (hard barrier -> new species node) — marks species with no
  remaining instances extinct, and returns a ChangeLog over INSTANCE
  IDs. Orthodox lineage: the instance closest to the amended species
  record keeps the species ID (tie: established mass, then lowest
  instance ID). Names pin only at the FINAL commit; before that they
  are working/debugging handles.
- RE-SYNC: post-commit, old X is deprecated. Each dressed bundle
  re-draws its X from the tree via the changelog. Truly new entries
  (origin events) go through the SPAWN VIP channel; ley lifts ride
  the normal update (Provenance "lifted").
- LEY RADIATION IS NOT A CHANNEL: it is one more ENV-defined
  provenance factor (e.g. "ley:radiation", source-typed like
  "predation:avian"). Localization comes free — the sim clones an
  instance hugging the ley site, and only that instance accumulates
  ley pressure. The unlock (past a gate, illegal mutation targets
  become legal — rebind(force=True) territory) is X-internal blackbox
  behavior; this contract never names ley below this line.
- LIFTING IS A SEPARATE MECHANISM on the same pathway: an ephemeral
  feed whose provenance carries "lift:<flavor>" names ("lift:sand",
  "lift:deep", "lift:bloom", combinations — env folds the site's
  substrate/depth/productivity into which flavors it emits, so the
  combination IS the site metadata packet). The sim OPENS this
  channel by decision; the feed containing it is the event, there is
  no separate event type. X's lift routine (force-rebind sampling
  across plan limits, Fauna RFC §6.2) fires on receipt; a committed
  offspring lineage gets Provenance "lifted" with (source, site,
  round), where the site details permanently live. The four
  prefix-typed dispatch classes ("pressure:"/"pull:"/"ley:"/"lift:")
  are defined in the STRESS bullet above.
- update() IS PURE: views + K1 streams in -> tree + changelog out.
  Deterministic replay from any saved round.
- THE ROUND IS THE TRANSACTION BOUNDARY: feed stress -> X changes ->
  parse -> commit -> changelog -> re-draw, no mid-round tree reads.
  Round length N years (~100 to start) is a resolution knob: stress
  integrates monthly inside the round, vital rates yearly, drift per
  generation via gen_time; per-round quantities are derived, never
  authored.

The stress interface itself is NOT yet pinned (biosphere addendum B5
§7 open questions). StressVerdict/StressFn are stubs carrying only
the settled points: signed s in [-1, +1]; provenance = per-requirement
suitability factors in [0, 1] with ENV-defined names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Mapping, Protocol

from kernel.hashrng import Stream

# ──  identity  ────────────────────────────────────────────────────────

SpeciesId = str    # K1 sid of the species node in the tree
InstanceId = str   # sim-minted (K1-derived) gene-pool working-copy id


# ──  what the organism exposes  ───────────────────────────────────────

# The derived projection: the ONLY thing the environment ever reads.
# Keys are metric names from the kingdom's derived vocabulary (fauna:
# "temp_opt_c", "moisture_opt", ...; flora: "ph_tolerance", ...).
# Env mechanics are written against this vocabulary — a derived metric
# the organism computes but does not expose here is invisible to
# selection.
DerivedView = Mapping[str, float]


# ──  stress (STUB — interface not yet determined)  ────────────────────

# Opaque cell handle. K13 never looks inside it; env passes whatever
# its cell representation is. Any-typed on purpose.
CellRef = Any


@dataclass(frozen=True)
class StressVerdict:
    """Env's answer for one (instance, cell, month). THE ONLY channel:
    abiotic requirements, competition, predation (source-typed names
    like "predation:avian"), productivity, and positive resource
    signals all arrive in this one object.

    STUB: the stress interface is not yet pinned (B5 §7). Settled:

    - ``s``: signed stress in [-1, +1]; +1 lethal, 0 indifferent,
      -1 maximal growth. Positive signals live at the growth end.
    - ``provenance``: per-requirement suitability factors in [0, 1]
      whose product is F (s = 1 - 2F). Requirement names are
      ENV-defined; organism-side select() reads them but never
      computes them.
    """

    s: float
    provenance: Mapping[str, float] = field(default_factory=dict)


class StressFn(Protocol):
    """The env-side stress computation. Implemented by kernel/stress +
    K15, never in this package. Present only as a seam so organism-side
    signatures can name it."""

    def __call__(self, view: DerivedView, cell: CellRef,
                 month: int) -> StressVerdict: ...


# ──  population (semantics organism-side, storage sim-side)  ──────────


@dataclass
class Population:
    """Two-density accounting (B5): cheap propagule ``rain`` everywhere
    the dispersal kernel reaches vs ``established`` density that vital
    rates act on. Rain is stress-blind; establishment is not.

    The SEMANTICS are defined here (organism-side); the per-cell
    STORAGE is part of the sim's spatial dressing and never enters
    K13. The sim updates its fields using verdicts plus the kingdom's
    vital rates.
    """

    rain: float = 0.0
    established: float = 0.0


@dataclass(frozen=True)
class VitalRates:
    """Base per-year rates at s = 0, derived from traits. Consumed by
    the sim's field update; never env vocabulary. PROVISIONAL shape —
    kingdoms may extend (Mapping-like) as vital-rate models land."""

    birth: float = 0.0
    death: float = 0.0
    establish: float = 0.0    # rain -> established conversion at s = 0


# ──  trait pressure plane (organism side only)  ───────────────────────

# The backward-pass intermediate: accumulated selection pressure per
# trait. Keys are trait names (axes or generics); values are signed
# accumulated pressure. Continuous traits take a nudge proportional to
# pressure; discrete traits (flags, generics, pathway enums) treat
# pressure past a threshold as switch propensity resolved by RNG draw,
# with legal targets enforced by content. Shape is kingdom-specific;
# env never sees it.
TraitPressure = dict[str, float]


# ──  X: the working copy  ─────────────────────────────────────────────


@dataclass
class Instance:
    """X — one gene-pool working copy of a species, minted by the tree.

    Carries the WIP genes (``traits``, amended freely during rounds —
    this is what dispersal clones preserve) and the accumulated trait
    pressure plane. Spatial state is NOT here: densities live in the
    sim's dressing; stress arrives via feed calls with a scalar
    ``weight`` (how much of the population experienced that verdict),
    so space collapses to a number before it reaches X.

    Post-commit every Instance is deprecated; the sim re-draws via the
    changelog.
    """

    species_id: SpeciesId
    instance_id: InstanceId
    traits: dict = field(default_factory=dict)        # WIP genes
    pressure: TraitPressure = field(default_factory=dict)

    def view(self, mass: float) -> "InstanceView":
        """The flat, space-collapsed parse handed to tree.update().
        ``mass`` is the total established mass across this instance's
        dressing, computed sim-side (orthodox-lineage tie-break)."""
        return InstanceView(species_id=self.species_id,
                            instance_id=self.instance_id,
                            traits=dict(self.traits), mass=mass)


@dataclass(frozen=True)
class InstanceView:
    """The parsed X: flat, ID-keyed, space-blind. This — and only
    this — crosses the commit boundary upward."""

    species_id: SpeciesId
    instance_id: InstanceId
    traits: Mapping = field(default_factory=dict)     # WIP genes
    mass: float = 0.0


# ──  commit: changelog & spawn  ───────────────────────────────────────


class Outcome(IntEnum):
    """Per-instance parse classification decided by tree.update()."""
    KEEP = 0         # continues under its species
    MERGE = 1        # absorbed into another instance (rare: only if
                     # really similar) — target carries the genes
    SUBSPECIES = 2   # committed as a SUBSPECIES node (real divide,
                     # deliberately rare: narrow divergence band)
    SPLIT = 3        # hard reproductive barrier: new SPECIES node


@dataclass(frozen=True)
class InstanceDelta:
    """One instance's fate. ``target``: merge -> surviving instance id;
    SUBSPECIES/SPLIT -> new node sid; KEEP -> None."""

    instance_id: InstanceId
    outcome: Outcome
    target: str | None = None
    orthodox: bool = False   # keeps the species ID (closest-to-record,
                             # then mass, then lowest instance id)


@dataclass(frozen=True)
class SpawnRequest:
    """VIP channel: the tree asks the sim to place something ex nihilo
    (origin events). Placement is always sim-side. STUB — semantics
    of ``hint`` TBD. Ley lifts do NOT use this; they ride the normal
    update as dressed clones with Provenance "lifted"."""

    species_id: SpeciesId
    hint: str = ""


@dataclass(frozen=True)
class ChangeLog:
    """update()'s entire return beyond the amended tree: the one-way,
    instance-keyed handshake the sim needs to re-draw X. Species whose
    instances all vanished are marked extinct (record stays as ghost).
    Amended trait states are applied to the tree directly; the reflog
    holds history."""

    instances: tuple[InstanceDelta, ...] = ()
    extinct_species: tuple[SpeciesId, ...] = ()
    spawns: tuple[SpawnRequest, ...] = ()


# ──  the two authorities  ─────────────────────────────────────────────

# Kingdom content packs are not yet unified (fauna ContentPack vs
# flora ContentPack — merging them is part of the K15 dedupe), so the
# pack parameter is Any-typed here.
ContentRef = Any


class KingdomSim(Protocol):
    """Organism-side behavior for one kingdom (flora/fauna), consumed
    by the sim. Every method is space-blind: stress arrives as a
    verdict plus scalar weight; no method may read a cell."""

    def derive(self, traits: Mapping, pack: ContentRef) -> DerivedView:
        """Project WIP genes to the derived vocabulary env reads."""
        ...

    def select(self, verdict: StressVerdict, traits: Mapping,
               pack: ContentRef) -> TraitPressure:
        """Map stress provenance back through the trait->derived
        dependency map onto traits: one feed's pressure increment.
        Entirely organism-side: env defines the requirement names, the
        organism decides which traits answer them."""
        ...

    def mutate(self, x: Instance, rng: Stream) -> None:
        """Apply the accumulated pressure plane to x.traits (drift per
        generation via gen_time), then reset the plane. Called by the
        sim at generation boundaries inside the round."""
        ...

    def vital(self, traits: Mapping, pack: ContentRef) -> VitalRates:
        """Base vital rates for the sim's two-density field update."""
        ...


class TreeAuthority(Protocol):
    """The tree as the sim sees it: mint, commit, re-draw. PURE —
    views + K1 streams in, changelog out, deterministic replay."""

    def mint(self, species_id: SpeciesId, instance_id: InstanceId,
             rng: Stream) -> Instance:
        """Hand out a working copy of a species' current genes."""
        ...

    def update(self, views: list[InstanceView],
               rng: Stream) -> ChangeLog:
        """The commit. Amends records gerrit-style (reflog holds
        history); classifies each instance KEEP/MERGE/SUBSPECIES/SPLIT
        with the orthodox rule; marks empty species extinct; may
        attach SpawnRequests (VIP). Decisions may grow ops we have
        not designed yet — that is why X is deprecated after this."""
        ...

    def redraw(self, instance_id: InstanceId) -> Instance | None:
        """Post-commit re-sync: the working copy for an instance id
        (possibly re-keyed per the changelog), or None if gone."""
        ...
