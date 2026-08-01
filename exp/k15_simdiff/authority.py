"""K15 TreeAuthority — the concrete commit handshake (spec §9).

Implements ``exp.k13_treegen.interface.TreeAuthority`` against
``exp.k13_treegen.model.Tree``: mint / update / redraw, plus the
append-only reflog and the per-round commit decisions. This is the
tree-side half of the K15 round loop; the engine (space/time side) is
``exp/k15_simdiff/engine.py`` (not yet landed). The authority is
SPACE-BLIND: it sees flat gene views only, never cells (interface
ruling, critic finding 5).

┌─ contract recap (interface.py, normative) ─────────────────────────
- update() is the commit: views in, amended tree + ChangeLog out.
  Records amend gerrit-style; the reflog holds history; there are NO
  micro-nodes for sub-SUB_D drift.
- One InstanceView PER INSTANCE (not a per-lineage aggregate).
- Orthodox lineage: the instance closest to the amended species record
  keeps the species ID; ties by established mass, then lowest
  instance id.
- X is deprecated post-commit; the engine re-draws via the changelog.

┌─ distance metric (§9) ─────────────────────────────────────────────
``genes_distance`` — salience-weighted L1 over mutable scalar axes
(normalized by axis span) + mismatch indicator over enum/generic axes,
combined as a weighted mean over the union of trait keys (weight = the
axis salience from the flora content axes; GENERIC_SALIENCE for plan
generics, which the registry does not rate; the "plan"/"preset"
bookkeeping keys the tree's mint carries are ignored). weighted_set
axes (e.g. dispersal_channels) contribute the pmf total-variation
distance (sum |Δw| / 2). The weighting table is a named module
constant, ``AXIS_METRIC``, built once at import from
``exp/k13_treegen/content/flora/axes_core.toml`` (falling back to an
empty table — generics-only — if the file is unavailable); a custom
table can be injected for tests or other kingdoms. In flora every
scalar/int axis is driftable (mutation != none), so the L1 term over
scalars IS the L1 term over mutable scalars; an invariant scalar (none
exist) would contribute 0 anyway because its value never changes.
The MERGE GATE does not read this metric: it reads the scalar-only
subset (``_merge_metric``, ticket 0008) — enum flips and generics are
same-blob noise that diluted the merge signal (measured 15% enum
mismatch at equal pressure), so the merge gate sees ONLY the
diverging scalar axes; weighted_set axes are dropped (their TV is
noise-dominated). The cluster/orthodox bookkeeping keeps the full
metric at SUB_D.

┌─ the commit pipeline (per species group; sids processed in sorted
   order, instances in sorted instance_id order) ─────────────────────
1. Pairwise distances over the instance gene views, plus each
   instance's distance to the record's committed genes (axes +
   generics as one mapping).
2. Orthodox: min (distance-to-record, -mass, instance_id) — the
   record as it stands entering the commit is the reference; the
   record is then amended to the orthodox instance's genes (the only
   non-circular reading of "closest to the AMENDED record").
3. Clusters = connected components of the pairwise graph at d < SUB_D.
   The component containing the orthodox instance is the orthodox
   cluster; its members are KEEP. The orthodox keeps the species ID
   and its genes amend the record gerrit-style (the reflog records the
   before/after). KEEP instances re-mint from the amended record, so
   their sub-SUB_D drift is NOT retained — by design (no micro-nodes
   for drift; divergence needs real separation).
4. Every other cluster is a real divide (its distance to the orthodox
   cluster is >= SUB_D by construction). The RANK is the g currency
   (fauna RFC §1, ticket 0008): a cluster whose representative is
   BELOW the lineage's g_star divides as a SUBSPECIES node (the
   "fragment below g* = subspecies" half); a cluster beyond g* is NOT
   divided individually — it rides the wholesale g-promotion below
   (dividing beyond-g* clusters individually churns a species per
   extreme-mutant fragment). The representative (most-established
   member, tie: lowest instance id) provides the new node's genes;
   every member re-keys to the new sid in the changelog. Callers that
   pass no g state (unit tests) fall back to the old
   [SUB_D, SPECIATION_D) trait-distance band for the rank.
   **g-promotion (ticket 0008):** the rounds' divide trigger — the
   LINEAGE's g (the orthodox instance's g_since_split, the record's
   representative) crossing the lineage's g_star promotes the WHOLE
   gene pool to ONE new SPECIES node: a dense lineage is a continuous
   trait cloud that never splits at SUB_D (measured on seed 1), so
   the g crossing IS the divide. One-shot: a SPECIES node is born
   promoted and never re-promotes (its g keeps accumulating and
   classify stays "species"). The engine resets re-keyed instances'
   g_since_split to 0 (the split ancestor) and seeds the new
   lineage's g*/rate multiplier.
5. Merges, only through the engine-side spatial gate (this class never
   sees cells): ``update`` takes an optional ``merge_candidates``
   argument (see the seam note below). A candidate pair is merged iff
   both members share one species group AND their SCALAR-ONLY pairwise
   distance < MERGE_D AND rounds_since_divergence >= MERGE_GRACE. The
   survivor is the more-established member (tie: lowest instance id);
   the orthodox instance is never absorbed (it keeps the species ID).
   Merges never cross species (speciation is a hard reproductive
   barrier), and two distinct clusters can never be candidates anyway
   (d >= SUB_D > MERGE_D).
6. Species that had living instances but have none now are marked
   extinct: the record stays in the tree as a ghost, the changelog
   lists the sid, the reflog gets the entry. Species never minted are
   never marked (they never had living instances) — EXCEPT genesis
   zero-range species, which the engine registers via
   ``register_unseeded`` (ticket 0004) so this same pass marks them
   extinct at the first commit.
7. ``spawns`` is always empty in v1 (origin events are out of scope).

┌─ divergence-round tracking (MERGE_GRACE) ───────────────────────────
The authority is round-agnostic (reflog entries carry no round), but
the grace needs a round count, so the authority tracks it internally:
``self._round`` counts update() calls (the first call is round 0) and
``self._divergence_round[instance_id]`` records the round at which the
instance's lineage last diverged — its first appearance (genesis or
mid-run founding) or a re-key to a new divide node. Then
rounds_since_divergence(i, j) = current_round − max(div[i], div[j]);
genesis siblings (round 0) first become merge-eligible at commit round
5 (their sixth update). update() is deterministic given the
authority's full state — tree + reflog + round counter + divergence
table + lineage map + alive set — so saved-round replay must restore
all of it (the reflog already rides along with the tree JSON).

┌─ merge-candidate seam (engine-side gate, critic finding 5) ─────────
update()'s signature stays the protocol's (views, rng); the spatial
contact gate lives ENGINE-side, so the touching pairs arrive as an
optional keyword: ``merge_candidates: set[frozenset[instance_id,
instance_id]]`` — each frozenset is one touching pair (exactly 2 ids).
The authority re-checks the gene distance and the grace before
merging. Pairs with unknown ids, pairs straddling two species, and
pairs at d ≥ MERGE_D are silently ignored (they fail the gate); a
malformed candidate (≠ 2 ids) raises ValueError.

┌─ names ─────────────────────────────────────────────────────────────
Interim handles only. New divide nodes get a K1-derived sid (16 hex
digits, drawn from the commit rng) and NO binomial — NameRecord stays
default (final-commit pinning is out of scope for v1). The engine-side
instance-id convention is ``{species_sid}.iNNN``; the authority never
mints instance ids (the engine does) and uses them verbatim in the
reflog.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from exp.k13_treegen.interface import (
    ChangeLog,
    Instance,
    InstanceDelta,
    InstanceId,
    InstanceView,
    Outcome,
    SpeciesId,
)
from exp.k13_treegen.forces import classify as g_classify
from exp.k13_treegen.model import RANK_PREFIX, Node, Rank, Tree
from kernel.hashrng import Stream

# ── commit knobs (§13) ────────────────────────────────────────────────

SUB_D = 0.1              # cluster edge: pairwise distance below this
SPECIATION_D = 0.35      # g-less FALLBACK divide rank (authority tests
                         # that call update() without the g bookkeeping;
                         # the engine always passes g, so the rounds use
                         # classify(g_since_split, g_star) instead — the
                         # SPECIATION_D band is NOT a rounds currency)
MERGE_D = 0.045          # merge gate: pairwise SCALAR-ONLY L1 below
                         # this -> merge-eligible (ticket 0008, agent-58
                         # measurement: same-blob scalar-only p99 floor
                         # ~0.073, contrast pairs p90 ~0.057 — 0.045
                         # merges same-blob pairs and lets genuinely
                         # diverging pairs escape the CONSOL sweep)
MERGE_GRACE = 5          # rounds since divergence before a merge is legal
GENERIC_SALIENCE = 0.4   # weight of plan-generic keys (registry rates none)
DEFAULT_SALIENCE = 0.2   # weight when an authored axis lacks salience

# keys the tree's mint carries that are not genes (flora derive expects
# them; the distance metric ignores them)
_NON_GENE_KEYS = frozenset({"plan", "preset"})


# ── distance metric ───────────────────────────────────────────────────


@dataclass(frozen=True)
class AxisMetric:
    """One trait key's contribution to the distance metric.

    ``value_type`` is "scalar"/"int" (salience-weighted L1, |Δ|/span),
    "enum"/"bool" (0/1 mismatch indicator), or "set" (weighted_set:
    pmf total variation, sum |Δw| / 2). ``span`` is bounds_hi −
    bounds_lo for scalar/int axes, else None.
    """

    salience: float = 1.0
    span: float | None = None
    value_type: str = "enum"


_CONTENT_TOML = (Path(__file__).resolve().parents[2]
                 / "exp" / "k13_treegen" / "content" / "flora"
                 / "axes_core.toml")


def _load_axis_metric(path: Path) -> dict[str, AxisMetric]:
    """Build the metric table from a flora axes_core.toml (M1 registry
    format): every axis gets (salience, span-or-None, value_type)."""
    toml = tomllib.loads(path.read_text())
    table: dict[str, AxisMetric] = {}
    for name, t in toml.get("axis", {}).items():
        vt = t.get("value_type", "scalar")
        if vt in ("scalar", "int"):
            b = t.get("bounds")
            span = float(b[1]) - float(b[0]) if b else None
        else:
            span = None
        table[name] = AxisMetric(
            salience=float(t.get("salience", DEFAULT_SALIENCE)),
            span=span,
            value_type="set" if vt == "weighted_set" else vt,
        )
    return table


try:
    AXIS_METRIC: Mapping[str, AxisMetric] = _load_axis_metric(_CONTENT_TOML)
except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
    # Content pack missing or moved: fall back to a generics-only table.
    # Distances stay defined (everything non-scalar at GENERIC_SALIENCE).
    AXIS_METRIC = {}


def _term(entry: AxisMetric | None, k: str, a: Mapping, b: Mapping) -> float:
    """One key's per-axis contribution, in [0, 1]."""
    av, bv = a.get(k), b.get(k)
    if entry is None:                      # a plan generic (or unknown key)
        return 0.0 if (av is not None and bv is not None and av == bv) else 1.0
    if entry.span is not None and entry.value_type in ("scalar", "int"):
        if av is None or bv is None:
            return 1.0                     # gene appeared/disappeared
        return min(abs(float(av) - float(bv)) / entry.span, 1.0)
    if entry.value_type == "set":          # weighted_set: pmf TV distance
        if av is None or bv is None or not isinstance(av, Mapping) \
                or not isinstance(bv, Mapping):
            return 1.0
        chans = set(av) | set(bv)
        tv = sum(abs(float(av.get(c, 0.0)) - float(bv.get(c, 0.0)))
                 for c in chans) / 2.0
        return min(tv, 1.0)
    return 0.0 if (av is not None and bv is not None and av == bv) else 1.0


def genes_distance(a: Mapping, b: Mapping,
                   metric: Mapping[str, AxisMetric] = AXIS_METRIC, *,
                   include_generics: bool = True) -> float:
    """Salience-weighted distance between two gene mappings (instance
    traits or record genes: axes + generics as one flat mapping).

    Weighted mean over the union of keys: each scalar axis contributes
    w·|Δ|/span, each enum/bool/generic axis w·(mismatch), each
    weighted_set axis w·TV, with w the axis salience (or
    GENERIC_SALIENCE for generics). Returns 0.0 for identical or empty
    mappings, 1.0 when every considered axis is at full divergence.

    ``include_generics=False`` restricts the key set to the metric's
    own table: keys with no AxisMetric entry (plan generics, enums the
    caller's subset table omits) contribute NOTHING and are excluded
    from the denominator — the merge-gate metric's shape (ticket 0008:
    the merge gate sees only the diverging scalar axes).
    """
    num = den = 0.0
    for k in sorted(set(a) | set(b)):
        if k in _NON_GENE_KEYS:
            continue
        entry = metric.get(k)
        if entry is None and not include_generics:
            continue
        w = entry.salience if entry is not None else GENERIC_SALIENCE
        num += w * _term(entry, k, a, b)
        den += w
    return num / den if den else 0.0


def _group_distances(traits_list: list[Mapping], record: Mapping,
                     metric: Mapping[str, AxisMetric], *,
                     include_generics: bool = True
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized exact equivalent of pairwise genes_distance over a
    group (the commit's O(n²) hot loop): returns (dist (n,n), rec (n,))
    float64 where dist[i][j] = genes_distance(traits_list[i],
    traits_list[j], metric) and rec[i] = genes_distance(
    traits_list[i], record, metric).

    Semantics preserved exactly: per pair the key set is the UNION of
    the pair's keys (a key absent from both contributes nothing, its
    salience excluded from the denominator); keys accumulate in sorted
    order, matching genes_distance's summation order. One deliberate
    repair: genes_distance's weighted_set TV sums over a Python set
    (hash-randomized iteration order across processes — a latent
    cross-run nondeterminism in float accumulation); here categories
    are sorted, which is deterministic. ``include_generics=False``
    skips keys outside the metric table (see genes_distance)."""
    n = len(traits_list)
    keys = sorted((set().union(*(set(t) for t in traits_list))
                   | set(record)) - _NON_GENE_KEYS)
    num = np.zeros((n, n))
    den = np.zeros((n, n))
    rnum = np.zeros(n)
    rden = np.zeros(n)
    for k in keys:
        entry = metric.get(k)
        if entry is None and not include_generics:
            continue
        w = entry.salience if entry is not None else GENERIC_SALIENCE
        p = np.array([t.get(k) is not None for t in traits_list])
        rp = record.get(k) is not None
        u = p[:, None] | p[None, :]
        den += w * u
        rden += w * (p | rp)
        if entry is not None and entry.span is not None \
                and entry.value_type in ("scalar", "int"):
            col = np.array([float(t[k]) if t.get(k) is not None
                            else np.nan for t in traits_list])
            T = np.minimum(
                np.abs(col[:, None] - col[None, :]) / entry.span, 1.0)
            T = np.where(np.isnan(T), 1.0, T)
            rv = float(record[k]) if rp else np.nan
            rt = np.minimum(np.abs(col - rv) / entry.span, 1.0)
            rt = np.where(np.isnan(rt), 1.0, rt)
        elif entry is not None and entry.value_type == "set":
            vals = [t.get(k) for t in traits_list]
            valid = np.array([isinstance(v, Mapping) for v in vals])
            rmap = record.get(k)
            rvalid = isinstance(rmap, Mapping)
            cats = sorted(set().union(
                *(set(v) for v in vals if isinstance(v, Mapping)),
                set(rmap) if rvalid else set()))
            if cats:
                M = np.array([[float(v.get(c, 0.0)) for c in cats]
                              if isinstance(v, Mapping)
                              else [np.nan] * len(cats)
                              for v in vals], dtype=np.float64)
                T = np.minimum(
                    0.5 * np.abs(M[:, None, :] - M[None, :, :]).sum(-1),
                    1.0)
                rc = np.array([float(rmap.get(c, 0.0)) for c in cats]) \
                    if rvalid else np.full(len(cats), np.nan)
                rt = np.minimum(0.5 * np.abs(M - rc).sum(-1), 1.0)
            else:
                T = np.zeros((n, n))
                rt = np.zeros(n)
            T = np.where(valid[:, None] & valid[None, :], T, 1.0)
            T = np.where(np.isnan(T), 1.0, T)
            rt = np.where(valid & rvalid, rt, 1.0)
            rt = np.where(np.isnan(rt), 1.0, rt)
        else:
            col = np.array([t.get(k) for t in traits_list],
                           dtype=object)
            both = p[:, None] & p[None, :]
            T = np.where(both & (col[:, None] == col[None, :]),
                         0.0, 1.0)
            rv = record.get(k)
            rt = np.where(p & rp & (col == rv), 0.0, 1.0)
        num += w * np.where(u, T, 0.0)
        rnum += w * np.where(p | rp, rt, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        dist = np.where(den > 0.0, num / den, 0.0)
        rec = np.where(rden > 0.0, rnum / rden, 0.0)
    return dist, rec


# ── the authority ─────────────────────────────────────────────────────


class TreeAuthority:
    """The concrete TreeAuthority: a model.Tree plus the commit state.

    State that must be restored for deterministic replay: the ``Tree``
    itself, ``reflog`` (append-only), ``_round`` (commit counter),
    ``_divergence_round`` (per instance), ``_instance_lineage``
    (instance id -> current sid), ``_alive`` (sids with living
    instances), ``_promoted`` (sids that have g-promoted — ticket
    0008; derivable from the tree: every SPECIES node created by a
    promotion is born promoted), and ``_sid_path`` (sid -> node path).
    """

    def __init__(self, tree: Tree,
                 metric: Mapping[str, AxisMetric] | None = None) -> None:
        self.tree = tree
        self.metric = AXIS_METRIC if metric is None else metric
        # merge-gate metric: scalar/int axes only (ticket 0008 — enum
        # flips and generics are same-blob noise; the merge gate must
        # see ONLY the diverging scalar axes). Falls back to the full
        # metric when the table has no scalars (degenerate, never for
        # the real flora content).
        scalar = {k: e for k, e in self.metric.items()
                  if e.value_type in ("scalar", "int")}
        self._merge_metric = scalar if scalar else self.metric
        # ticket 0008: sids that have already g-promoted (their g
        # crossed the lineage's g_star — reproductively isolated).
        # A SPECIES node is born promoted and NEVER re-promotes (its g
        # keeps accumulating; classify stays "species"; further
        # divides come from the trait-cluster path as SPLITs). The
        # order-side lineages promote once per crossing cohort, so a
        # lineage whose members cross at different rounds radiates
        # one species per cohort instead of re-promoting every commit.
        self._promoted: set[SpeciesId] = set()
        self.reflog: list[dict] = []
        self._round = 0
        self._divergence_round: dict[InstanceId, int] = {}
        self._instance_lineage: dict[InstanceId, SpeciesId] = {}
        self._alive: set[SpeciesId] = set()
        self._sid_path: dict[SpeciesId, str] = {
            n.sid: p for p, n in tree.nodes.items()}

    # ── checkout / re-sync ─────────────────────────────────────────

    def mint(self, species_id: SpeciesId, instance_id: InstanceId,
             rng: Stream) -> Instance:
        """Hand out a working copy of a species' current genes.

        Makes no draws: the traits are copied verbatim from the record
        (axes + generics, plus the "plan"/"preset" bookkeeping keys the
        flora sim's derive expects). ``rng`` is accepted for protocol
        shape. Minting counts the species as alive until a commit says
        otherwise.
        """
        path = self._sid_path.get(species_id)
        if path is None:
            raise KeyError(f"unknown species id {species_id!r}")
        node = self.tree.nodes[path]
        traits = {**node.axes, **node.generics,
                  "plan": node.plan, "preset": node.preset}
        self._instance_lineage[instance_id] = species_id
        self._alive.add(species_id)
        return Instance(species_id=species_id, instance_id=instance_id,
                        traits=traits)

    def redraw(self, instance_id: InstanceId) -> Instance | None:
        """Post-commit re-sync: a fresh working copy minted from the
        instance's current lineage node, or None if the instance is
        gone (unknown id, or absorbed by a merge — the engine re-keys
        absorbed bundles to the survivor id per the changelog before
        re-drawing)."""
        sid = self._instance_lineage.get(instance_id)
        if sid is None:
            return None
        path = self._sid_path.get(sid)
        if path is None:
            return None
        node = self.tree.nodes[path]
        traits = {**node.axes, **node.generics,
                  "plan": node.plan, "preset": node.preset}
        return Instance(species_id=sid, instance_id=instance_id,
                        traits=traits)

    def register_unseeded(self, sids: Iterable[str]) -> None:
        """Genesis bookkeeping (ticket 0004): species whose viable range
        at genesis was zero are NEVER minted — no instance exists — but
        they are registered in ``_alive`` so the NORMAL update()
        extinction pass (``_alive - alive_now``) marks them extinct at
        the first commit (reflog entry, branch terminated; the record
        stays as a ghost). Call before the first update(). Without the
        registration the authority's "never minted, never marked"
        invariant would keep them alive-but-empty forever."""
        for sid in sids:
            self._alive.add(sid)

    # ── the commit ─────────────────────────────────────────────────

    def update(self, views: list[InstanceView], rng: Stream, *,
               merge_candidates: set[frozenset[str]] | None = None,
               g_since_split: Mapping[str, float] | None = None,
               g_star: Mapping[str, float] | None = None) -> ChangeLog:
        """The commit. See the module docstring for the full pipeline.

        ``merge_candidates``: optional set of 2-instance frozensets the
        engine has verified spatially touch (this class is space-blind;
        critic finding 5). The authority still re-checks the gene
        distance < MERGE_D and the MERGE_GRACE before merging. See the
        seam note in the module docstring.

        ``g_since_split`` / ``g_star``: the lineage g bookkeeping
        (fauna RFC §1, ticket 0008) — per-instance accumulated genetic
        distance in generations since the last split, and per-lineage
        seeded speciation cutoff. When a group's lineage has a g_star,
        the divide RANK (subspecies vs species) is
        classify(g_since_split, g_star) instead of the SPECIATION_D
        trait-distance band. The engine always passes both; callers
        that omit them get the old trait-distance band (authority unit
        tests).
        """
        commit_round = self._round
        self._round += 1

        candidates: set[frozenset[str]] = set(merge_candidates or ())
        for pair in candidates:
            if len(pair) != 2:
                raise ValueError(
                    f"merge candidate must be a 2-instance pair, "
                    f"got {sorted(pair)!r}")

        views_sorted = sorted(views, key=lambda v: v.instance_id)
        ids = [v.instance_id for v in views_sorted]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate instance ids in views")

        groups: dict[SpeciesId, list[InstanceView]] = {}
        for v in views_sorted:
            groups.setdefault(v.species_id, []).append(v)

        # per-lineage candidate buckets (ticket 0004 companion fix):
        # every candidate is a SAME-LINEAGE pair by construction (the
        # engine's spatial gate and the CONSOL sweep build them per
        # lineage), so the pairs are bucketed by species ONCE here and
        # each group's _process_group scans only its own pairs. The
        # pre-bucket code re-sorted and scanned the FULL candidate set
        # inside every group — O(groups x pairs) — which blew up the
        # CONSOL commit at the radiated tree's lineage counts (measured
        # ~394 s at commit round 4, seed 1, ticket 0004). Identical
        # semantics: a pair whose ids are unknown or straddle two
        # species was ALWAYS skipped by the per-group filter, so
        # dropping them up front changes nothing; within a group the
        # surviving pairs iterate in the same sorted order as before.
        view_sid = {v.instance_id: v.species_id for v in views_sorted}
        cands_by_sid: dict[SpeciesId, list[frozenset[str]]] = {}
        for pair in candidates:
            a, b = tuple(pair)
            pa, pb = view_sid.get(a), view_sid.get(b)
            if pa is None or pb is None or pa != pb:
                continue
            cands_by_sid.setdefault(pa, []).append(pair)

        deltas: dict[InstanceId, InstanceDelta] = {}
        alive_now: set[SpeciesId] = set()

        for sid in sorted(groups):
            path = self._sid_path.get(sid)
            if path is None:
                raise KeyError(f"view references unknown species {sid!r}")
            node = self.tree.nodes[path]
            group = sorted(groups[sid], key=lambda v: v.instance_id)
            alive_now.add(sid)
            self._process_group(node, group, commit_round, rng,
                                cands_by_sid.get(sid, ()), deltas,
                                alive_now, g_since_split, g_star)

        extinct = sorted(self._alive - alive_now)
        for sid in extinct:
            self.reflog.append({"event": "extinct", "sid": sid})
        self._alive = alive_now

        return ChangeLog(
            instances=tuple(deltas[v.instance_id] for v in views_sorted),
            extinct_species=tuple(extinct),
            spawns=(),
        )

    # ── internals ──────────────────────────────────────────────────

    def _process_group(self, node: Node, group: list[InstanceView],
                       commit_round: int, rng: Stream,
                       candidates: Iterable[frozenset[str]],
                       deltas: dict[InstanceId, InstanceDelta],
                       alive_now: set[SpeciesId],
                       g_since_split: Mapping[str, float] | None = None,
                       g_star: Mapping[str, float] | None = None) -> None:
        """One species group: orthodox, clusters, divides, merges.
        *candidates* is the group's OWN merge-candidate pairs (the
        update() caller buckets the same-lineage pairs per species —
        see the seam note; the pre-bucket full-set scan was
        O(groups × pairs) and dominated the CONSOL commit at high
        lineage counts, ticket 0004)."""
        sid = node.sid
        m = self.metric
        n = len(group)
        idx = {v.instance_id: i for i, v in enumerate(group)}
        record_genes = {**node.axes, **node.generics}

        for v in group:
            self._divergence_round.setdefault(v.instance_id, commit_round)
            self._instance_lineage.setdefault(v.instance_id, sid)

        # pairwise distances over the instance gene views (vectorized —
        # the O(n²) dict loop was the commit wall-clock bottleneck at
        # lineage sizes >100; identical semantics)
        traits_list = [v.traits for v in group]
        dist, rec = _group_distances(traits_list, record_genes, m)

        # orthodox: closest to the record; ties mass desc, then id asc
        orthodox_i = min(
            range(n),
            key=lambda i: (rec[i], -group[i].mass, group[i].instance_id))
        orthodox_id = group[orthodox_i].instance_id

        # clusters = connected components of the graph at d < SUB_D
        adj = [[] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                if dist[i][j] < SUB_D:
                    adj[i].append(j)
                    adj[j].append(i)
        seen = [False] * n
        clusters: list[list[int]] = []
        for i in range(n):
            if seen[i]:
                continue
            stack, comp = [i], []
            seen[i] = True
            while stack:
                x = stack.pop()
                comp.append(x)
                for y in adj[x]:
                    if not seen[y]:
                        seen[y] = True
                        stack.append(y)
            clusters.append(sorted(comp))
        clusters.sort(key=lambda c: tuple(group[i].instance_id for i in c))
        orthodox_cluster = next(c for c in clusters if orthodox_i in c)

        # amend the record gerrit-style to the orthodox instance's genes
        before = dict(record_genes)
        self._amend(node, group[orthodox_i].traits)
        after = {**node.axes, **node.generics}
        if before != after:
            self.reflog.append({"event": "amend", "sid": sid,
                                "instance": orthodox_id,
                                "before": before, "after": after})

        deltas[orthodox_id] = InstanceDelta(instance_id=orthodox_id,
                                            outcome=Outcome.KEEP,
                                            target=None, orthodox=True)

        star = (g_star or {}).get(sid)
        gs = g_since_split or {}
        handled: set[int] = set()
        dist_merge = None          # scalar-only merge matrix (lazy)

        # g-currency promotion (ticket 0008, fauna RFC §1): the
        # LINEAGE's g — the orthodox instance's g_since_split (the
        # record's representative — "per lineage, scalar g") —
        # crossing the lineage's seeded g* means the whole gene pool
        # is reproductively isolated from its founder: ONE promotion
        # re-keys every instance of the lineage to a new SPECIES node
        # (the old record stays as the ghost ancestor). This is the
        # rounds' divide trigger — a dense lineage is a continuous
        # trait cloud that never splits at SUB_D (measured on seed 1),
        # so the trait clusters can't fire the divide. One-shot: a
        # SPECIES node is born promoted and never re-promotes (its g
        # keeps accumulating; classify stays "species"; further
        # divides come from the trait-cluster path as SPLITs). The
        # engine resets the re-keyed instances' g_since_split (the
        # split ancestor — fauna RFC §1's d(A,B) = (g_A − g0) +
        # (g_B − g0)) and seeds the new lineage's g*/rate multiplier.
        if star is not None and sid not in self._promoted:
            if gs.get(orthodox_id, 0.0) > star:
                new_sid = self._divide(
                    node, Rank.SPECIES, group[orthodox_i].traits,
                    [v.instance_id for v in group], rng)
                alive_now.add(new_sid)
                self._promoted.add(new_sid)
                for i in range(n):
                    handled.add(i)
                    iid = group[i].instance_id
                    deltas[iid] = InstanceDelta(instance_id=iid,
                                                outcome=Outcome.SPLIT,
                                                target=new_sid,
                                                orthodox=False)
                    self._instance_lineage[iid] = new_sid
                    self._divergence_round[iid] = commit_round

        # divergent clusters -> real divides (ticket 0008): the RANK is
        # the g currency — classify(cluster rep's g_since_split, the
        # lineage's g_star) (fauna RFC §1: fragment beyond g* = new
        # species, below = subspecies). g never converges, so it can
        # NOT gate clusters — the SUB_D trait-distance graph above is
        # the cluster bookkeeping, unchanged. A cluster whose rep is
        # BEYOND the lineage's g* is NOT divided here: the fragments
        # past g* ride the wholesale g-promotion above (the lineage
        # promotes as ONE record when its orthodox crosses g*) —
        # dividing them individually would churn a species per
        # extreme-mutant fragment (measured: hundreds of spurious
        # SPLITs per round at seed 1). The SPECIATION_D band is only
        # the g-less fallback for callers that pass no g state.
        for cluster in clusters:
            if cluster == orthodox_cluster:
                continue
            if all(i in handled for i in cluster):
                continue          # already re-keyed by the promotion
            rep = min(cluster, key=lambda i: (-group[i].mass,
                                              group[i].instance_id))
            if star is not None:
                rep_g = gs.get(group[rep].instance_id, 0.0)
                if rep_g > star:
                    # beyond g*: the wholesale promotion handles the
                    # lineage — the fragment stays KEEP for now
                    for i in cluster:
                        iid = group[i].instance_id
                        if iid not in deltas:
                            deltas[iid] = InstanceDelta(
                                instance_id=iid, outcome=Outcome.KEEP,
                                target=None, orthodox=False)
                    continue
                outcome, rank = Outcome.SUBSPECIES, Rank.SUBSPECIES
            else:
                cdist = min(dist[i][j] for i in cluster
                            for j in orthodox_cluster)
                outcome, rank = (Outcome.SPLIT, Rank.SPECIES) \
                    if cdist >= SPECIATION_D \
                    else (Outcome.SUBSPECIES, Rank.SUBSPECIES)
            new_sid = self._divide(node, rank, group[rep].traits,
                                   [group[i].instance_id for i in cluster],
                                   rng)
            alive_now.add(new_sid)
            if rank is Rank.SPECIES:
                self._promoted.add(new_sid)
            for i in cluster:
                iid = group[i].instance_id
                handled.add(i)
                deltas[iid] = InstanceDelta(instance_id=iid,
                                            outcome=outcome,
                                            target=new_sid, orthodox=False)
                self._instance_lineage[iid] = new_sid
                self._divergence_round[iid] = commit_round

        # merges, engine-gated (candidates; orthodox cluster only).
        # Vectorized prefilter (the candidate set reaches 1e5 at high
        # occupancy — the per-pair Python checks dominated the commit):
        # only survivors get the sequential survivor/absorbed pass.
        # Instances already re-keyed by a divide this commit (handled)
        # are not merge candidates.
        cand: list[tuple[str, str]] = []
        for pair in sorted(candidates, key=lambda p: tuple(sorted(p))):
            a_id, b_id = sorted(pair)
            if {a_id, b_id} - set(idx):            # unknown / other species
                continue
            if idx[a_id] in handled or idx[b_id] in handled:
                continue
            cand.append((a_id, b_id))
        if cand:
            if dist_merge is None:
                # scalar-only merge matrix: the merge gate reads the
                # same-blob noise floor under the DIVERGENT axes only
                # (ticket 0008 — the full metric dilutes the signal
                # with enum noise; the CONSOL sweep erased the
                # incipient cohort at d_V0 < MERGE_D). Generics are
                # excluded (enum-like flips are noise).
                dist_merge, _ = _group_distances(
                    traits_list, record_genes, self._merge_metric,
                    include_generics=False)
            in_orth = np.zeros(n, dtype=bool)
            in_orth[orthodox_cluster] = True
            ia_v = np.array([idx[a] for a, _ in cand])
            ib_v = np.array([idx[b] for _, b in cand])
            grace_v = np.array([
                commit_round - max(
                    self._divergence_round.get(a, commit_round),
                    self._divergence_round.get(b, commit_round))
                for a, b in cand])
            ok = (dist_merge[ia_v, ib_v] < MERGE_D) \
                & (grace_v >= MERGE_GRACE) \
                & in_orth[ia_v] & in_orth[ib_v]
            cand = [c for c, keep in zip(cand, ok) if keep]
        absorbed: set[str] = set()
        for a_id, b_id in cand:
            ia, ib = idx[a_id], idx[b_id]
            if a_id in absorbed or b_id in absorbed:
                continue
            if orthodox_id in (a_id, b_id):
                survivor_id = orthodox_id          # orthodox never absorbed
            elif group[ia].mass > group[ib].mass:
                survivor_id = a_id
            elif group[ib].mass > group[ia].mass:
                survivor_id = b_id
            else:
                survivor_id = min(a_id, b_id)
            absorbed_id = b_id if survivor_id == a_id else a_id
            absorbed.add(absorbed_id)
            deltas[absorbed_id] = InstanceDelta(instance_id=absorbed_id,
                                                outcome=Outcome.MERGE,
                                                target=survivor_id,
                                                orthodox=False)
            self._instance_lineage.pop(absorbed_id, None)
            self.reflog.append({"event": "merge", "sid": sid,
                                "instance": absorbed_id,
                                "into": survivor_id})

        # remaining orthodox-cluster members keep their species
        for i in orthodox_cluster:
            iid = group[i].instance_id
            if iid not in deltas:
                deltas[iid] = InstanceDelta(instance_id=iid,
                                            outcome=Outcome.KEEP,
                                            target=None, orthodox=False)

    def _divide(self, parent: Node, rank: Rank, traits: Mapping,
                instance_ids: list[str], rng: Stream) -> SpeciesId:
        """Create a new species/subspecies node diverged from *parent*.

        The new node's genes are the representative instance's genes,
        restricted to the parent's axis/generic key sets; its sid is a
        K1 draw from the commit rng (deterministic per inputs). Path =
        parent path + rank prefix + child index (treegen convention).
        The name stays an interim handle: NameRecord.binomial is never
        set (final-commit pinning is out of scope for v1).
        """
        event = "split" if rank is Rank.SPECIES else "subspecies"
        path = f"{parent.path}.{RANK_PREFIX[rank]}" \
               f"{len(self.tree.children(parent.path))}"
        srng = rng.child(f"k15.commit.{RANK_PREFIX[rank]}"
                         f"{parent.sid}:{instance_ids[0]}")
        new_sid = f"{srng.u64(0):016x}"
        node = Node(
            path=path, rank=rank, parent=parent.path, sid=new_sid,
            plan=parent.plan, preset=parent.preset,
            g=parent.g, gen_time=parent.gen_time,
            axes={k: traits[k] for k in parent.axes if k in traits},
            generics={k: traits[k] for k in parent.generics if k in traits},
            description=(f"interim {rank.name.lower()}: "
                         f"{len(instance_ids)} instance(s) off {parent.sid}"),
        )
        self.tree.add(node)
        self._sid_path[new_sid] = path
        self.reflog.append({"event": event, "sid": new_sid,
                            "parent_sid": parent.sid,
                            "instances": sorted(instance_ids),
                            "genes": {**node.axes, **node.generics}})
        return new_sid

    @staticmethod
    def _amend(node: Node, traits: Mapping) -> None:
        """Gerrit-style amend: the record's existing axis/generic values
        take the instance's values. Never adds or removes keys — a new
        gene requires a divide, not a drift."""
        for k in node.axes:
            if k in traits:
                node.axes[k] = traits[k]
        for k in node.generics:
            if k in traits:
                node.generics[k] = traits[k]
