"""K15 artifact query / debug tool (ticket 0038).

One general place to ask questions of a finished k15 run — the project's
main debugging surface.  Answers anything the persisted artifact can
answer (state.json, density.json, tree.json, reflog.json, and — when the
world products exist — biome/substrate per cell via the manifest's
k11/k14 input chain).  Not a canned stats script: the CLI sits on a
small query API that later engines can reuse directly.

Question classes (all work against the seed-1 artifact):

  identity SID   what is this species — rank, names, salient trait axes
  range    SID   cells occupied, bbox, connectivity + patch-size
                 distribution, biome/substrate mix (--world)
  coexist  SID   compositional: species B with share = |A & B| / |A|
                 >= X for threshold X ("how many species share >= X% of
                 A's cells"); streamed over sparse cell-index sets
  events   SID   the species' reflog entries (no round stamps yet —
                 sequence index is the only ordering)
  tuning [SID]   per-instance mass/cell/rain summaries; capacity
                 questions are out of scope (K(c) is not persisted)
  list           live species roster (discovery aid: find sids to ask)

Artifact layout (exp/k15_simdiff/persist.py, k15 schema):

  state.json    run manifest + per-instance digest (iid -> cells/mass/
                rain/sid/traits), retired iids, world shape
  density.json  per-instance WINDOWED density: box = [y0, y1, x0, x1]
                (Y-FIRST, both ends EXCLUSIVE) + N (windowed f8 field,
                row-major) + mask (u1 occupancy,
                len = (x1-x0)*(y1-y0))
  tree.json     the amended species tree (k13 schema; species binomials
                are NULL by design — the k15 authority never runs the
                nomenclature layer, "interim handle" authority.py)
  reflog.json   authority event log (amend/merge/split/subspecies/
                extinct), NO round stamps
  manifest.json provenance / input chain (k11_worldgen + k13_flora)

World join: the manifest's k11_worldgen input seed resolves the k14
world product exp/k14_worldprod/out/seed_N/derived.npz (ground_d2 ->
substrate class via argmin, ground_meta legend) and the k11 world
exp/k11_worldgen/out/seed_N/world.npz (w_biome_map -> biome).  Degrades
gracefully when a product is missing.

Memory (owner hard rule): never materialize (n_species, H, W) arrays.
Density fields stay windowed; the only materialized structure is the
per-species sparse cell-index set (flat y*W+x ints), which the
intersection queries stream over.

Determinism: pure functions of artifact bytes — no randomness, no
wall-clock, sorted iteration everywhere, float accumulation only over
integer counts.  Same artifact bytes => byte-identical output.

Usage:
  PYTHONPATH=. uv run python tools/artifact_query.py identity 20933a8030ce8f5c
  PYTHONPATH=. uv run python tools/artifact_query.py range 20933a8030ce8f5c --world
  PYTHONPATH=. uv run python tools/artifact_query.py coexist 20933a8030ce8f5c --share 0.5
  PYTHONPATH=. uv run python tools/artifact_query.py events 6d96ce770d00b0be
  PYTHONPATH=. uv run python tools/artifact_query.py tuning
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


# ── errors ─────────────────────────────────────────────────────────────


class ArtifactError(Exception):
    """Base for all query-tool errors (unknown sid, missing files, ...)."""


class MissingArtifact(ArtifactError):
    """The artifact directory itself is absent or unreadable."""


class WorldUnavailable(ArtifactError):
    """A world product needed for a biome/substrate join is missing."""


# ── artifact model (lazy, cheap) ───────────────────────────────────────


class Artifact:
    """A persisted k15 run.  Files are parsed lazily per access and
    cached; the raw density.json parse is released after the sparse
    per-species cell sets are built (it is the one large payload)."""

    def __init__(self, out_dir):
        self.dir = Path(out_dir)
        if not self.dir.is_dir():
            raise MissingArtifact(
                f"artifact directory not found: {self.dir} "
                "(expected exp/k15_simdiff/out/seed_NNNNNNNN/)")
        self._cache: dict[str, object] = {}
        self._cell_sets: dict[str, set[int]] | None = None

    def _load(self, name: str):
        if name not in self._cache:
            path = self.dir / f"{name}.json"
            if not path.is_file():
                raise MissingArtifact(
                    f"{name}.json missing from artifact {self.dir} "
                    "(incomplete dump?)")
            with open(path, encoding="utf-8") as fh:
                self._cache[name] = json.load(fh)
        return self._cache[name]

    def state(self) -> dict:
        return self._load("state")

    def tree(self) -> dict:
        return self._load("tree")

    def reflog(self) -> list:
        return self._load("reflog")

    def density(self) -> dict:
        return self._load("density")

    def manifest(self) -> dict:
        return self._load("manifest")

    def world_shape(self) -> tuple[int, int]:
        """(H, W) at anchor resolution, from the run manifest."""
        h, w = self.state()["world"]
        return int(h), int(w)

    # ── sparse cell sets (the density payload, decoded once) ──

    def cell_sets(self) -> dict[str, set[int]]:
        """sid -> set of occupied flat cell indices (y*W+x).

        Decoded from the windowed masks; the raw density.json parse is
        dropped afterwards (the file is ~30 MB; the sets are sparse).
        Total entries across all species <= H*W * species-per-cell."""
        if self._cell_sets is None:
            H, W = self.world_shape()
            sets: dict[str, set[int]] = {}
            for e in self.density()["instances"]:
                occ = [i for i, v in enumerate(e["mask"]) if v]
                if not occ:
                    continue
                y0, y1, x0, x1 = e["box"]
                w = x1 - x0
                s = sets.setdefault(e["sid"], set())
                s.update((y0 + i // w) * W + (x0 + i % w) for i in occ)
            self._cache.pop("density", None)   # release the raw parse
            self._cell_sets = sets
        return self._cell_sets

    def species_cells(self, sid: str) -> set[int] | None:
        """The live occupied cell set for a sid, or None if the species
        has no live instances in this run."""
        return self.cell_sets().get(sid)


# ── shared helpers ─────────────────────────────────────────────────────


def _repo_root(artifact_dir: Path) -> Path:
    """The checkout root holding exp/ and tools/ — walk up from the
    artifact dir, fall back to the module location."""
    resolved = Path(artifact_dir).resolve()
    for anc in resolved.parents:
        if (anc / "exp").is_dir() and (anc / "tools").is_dir():
            return anc
    return Path(__file__).resolve().parent.parent


def _intersect_size(a: set[int], b: set[int]) -> int:
    """|a & b|, iterating the smaller set (sparse streaming)."""
    if len(a) > len(b):
        a, b = b, a
    return sum(1 for c in a if c in b)


def _components(cells: set[int], H: int, W: int) -> list[int]:
    """8-connected component sizes of a flat-index cell set, ascending.

    Deterministic: sizes only, never iteration order.  Used for range
    connectivity / patch-size distribution."""
    remaining = set(cells)
    sizes: list[int] = []
    while remaining:
        stack = [remaining.pop()]
        n = 0
        while stack:
            idx = stack.pop()
            n += 1
            x, y = idx % W, idx // W
            for dy in (-1, 0, 1):
                ny = y + dy
                if ny < 0 or ny >= H:
                    continue
                row = ny * W
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx = x + dx
                    if nx < 0 or nx >= W:
                        continue
                    nb = row + nx
                    if nb in remaining:
                        remaining.discard(nb)
                        stack.append(nb)
        sizes.append(n)
    return sorted(sizes)


def _species_index(a: Artifact) -> dict[str, dict]:
    """sid -> tree node, over every rank (species, subspecies, ...)."""
    return {n["sid"]: n for n in a.tree()["nodes"] if n.get("sid")}


def _node_names(node: dict) -> tuple[str | None, str | None]:
    name = node.get("name") or {}
    return name.get("binomial"), name.get("folk")


def _nearest_named_ancestor(a: Artifact, node: dict) -> dict | None:
    """Climb the parent chain to the nearest node that carries a
    binomial (in the k15 artifact that is typically the genus)."""
    nodes = {n["path"]: n for n in a.tree()["nodes"]}
    path = node.get("parent")
    while path:
        anc = nodes.get(path)
        if not anc:
            return None
        binomial, _ = _node_names(anc)
        if binomial:
            return {"sid": anc["sid"], "rank": anc["rank"],
                    "path": anc["path"], "binomial": binomial}
        path = anc.get("parent")
    return None


def _round(v) -> float | None:
    if v is None:
        return None
    return round(float(v), 6)


# ── question classes ───────────────────────────────────────────────────


def identity(a: Artifact, sid: str) -> dict:
    """1. Identity: sid -> rank, names, salient trait axes.

    Species binomials/folk names are NULL in the k15 artifact by design
    (the authority never runs the nomenclature layer — authority.py
    "interim handle"); the nearest named ancestor (genus) is reported
    for context instead."""
    idx = _species_index(a)
    node = idx.get(sid)
    if node is None:
        raise ArtifactError(
            f"no tree node with sid {sid!r} (tree.json has "
            f"{len(idx)} sids; try `list` for live ones)")
    binomial, folk = _node_names(node)
    st = a.state()
    mine = sorted(iid for iid, rec in st["instances"].items()
                  if rec["sid"] == sid)
    return {
        "sid": sid,
        "rank": node["rank"],
        "path": node["path"],
        "parent": node["parent"],
        "binomial": binomial,
        "folk": folk,
        "nearest_named_ancestor": _nearest_named_ancestor(a, node),
        "description": node.get("description") or "",
        "plan": node.get("plan"),
        "preset": node.get("preset"),
        "g": _round(node.get("g")),
        "gen_time": _round(node.get("gen_time")),
        "provenance": node.get("provenance"),
        "flags": sorted(node.get("flags") or []),
        "axes": dict(sorted((node.get("axes") or {}).items())),
        "alive": bool(mine),
        "instances": len(mine),
        "cells": sum(st["instances"][iid]["cells"] for iid in mine),
    }


def _mix(world: dict, cells: set[int]) -> tuple[dict[str, int], dict[str, int]]:
    """Count biome/substrate classes over the flat-index cell set."""
    biome_names = world["biome_names"]
    substrate_names = world["substrate_names"]
    biomes: Counter[str] = Counter()
    substrates: Counter[str] = Counter()
    for idx in cells:
        biomes[biome_names[world["biome_map"][idx]]] += 1
        substrates[substrate_names[world["substrate_map"][idx]]] += 1

    def pairs(counts: Counter[str]) -> dict[str, int]:
        return dict(sorted(counts.items(), key=lambda t: (-t[1], t[0])))

    return pairs(biomes), pairs(substrates)


def range_info(a: Artifact, sid: str, world: dict | None = None) -> dict:
    """2. Range: cells occupied, tight bbox, connectivity + patch-size
    distribution of the density mask, and — when a world join is
    supplied — the biome/substrate mix over the occupied cells."""
    cells = a.species_cells(sid)
    if cells is None:
        raise ArtifactError(
            f"sid {sid!r} has no live instances in state.json "
            "(extinct or never seeded — `events` may still have history)")
    H, W = a.world_shape()
    comps = _components(cells, H, W)
    hist = Counter(comps)
    ys = [idx // W for idx in cells]
    xs = [idx % W for idx in cells]
    out = {
        "sid": sid,
        "rank": _species_index(a).get(sid, {}).get("rank"),
        "cells": len(cells),
        "instances": sum(1 for rec in a.state()["instances"].values()
                         if rec["sid"] == sid),
        "bbox": [min(xs), max(xs) + 1, min(ys), max(ys) + 1],
        "components": len(comps),
        "largest_patch": max(comps) if comps else 0,
        "patch_sizes": [[size, hist[size]] for size in sorted(hist)],
    }
    if world is not None:
        biomes, substrates = _mix(world, cells)
        out["biomes"] = biomes
        out["substrates"] = substrates
    return out


def coexist(a: Artifact, sid: str, share: float) -> dict:
    """3. Compositional / coexistence (the headline class).

    For species A, enumerate species B with
    share(B) = |cells(A) & cells(B)| / |cells(A)| >= X.  Streamed over
    the sparse per-species cell-index sets — no (n_species, H, W)
    arrays.  A species qualifies only if the overlap is non-empty
    (share=0 effectively means "shares at least one cell")."""
    if not 0.0 <= share <= 1.0:
        raise ArtifactError(f"share must be in [0, 1], got {share!r}")
    sets = a.cell_sets()
    A = sets.get(sid)
    if A is None:
        raise ArtifactError(
            f"sid {sid!r} has no live instances in state.json "
            "(extinct or never seeded)")
    nA = len(A)
    pairs: list[tuple[str, int]] = []
    n_any = 0
    for other, cells in sets.items():
        if other == sid:
            continue
        ov = _intersect_size(A, cells)
        if ov:
            n_any += 1
            if ov / nA >= share:
                pairs.append((other, ov))
    pairs.sort(key=lambda t: (-(t[1] / nA), t[0]))
    idx = _species_index(a)
    return {
        "sid": sid,
        "share": share,
        "cells": nA,
        "species_total": len(sets) - 1,
        "with_any_overlap": n_any,
        "n_coexist": len(pairs),
        "pairs": [
            {"sid": other, "binomial": _node_names(idx[other])[0]
             if other in idx else None,
             "overlap": ov, "share": round(ov / nA, 6),
             "cells": len(sets[other])}
            for other, ov in pairs
        ],
    }


def events(a: Artifact, sid: str, limit: int | None = None) -> dict:
    """4. Events: the species' reflog entries.

    The reflog carries NO round stamps (k15 metadata gap) — sequence
    index is the only ordering, reported as ``seq``.  role="own" entries
    amend/merge/extinct the record itself; role="parent" entries are
    split/subspecies events that created a daughter from this species."""
    log = a.reflog()
    entries: list[dict] = []
    for i, e in enumerate(log):
        if e.get("sid") == sid:
            role = "own"
        elif e.get("parent_sid") == sid:
            role = "parent"
        else:
            continue
        rec = {"seq": i, "event": e.get("event"), "role": role}
        for k in ("instance", "into", "parent_sid"):
            if k in e:
                rec[k] = e[k]
        if e.get("event") == "amend":
            before, after = e.get("before", {}), e.get("after", {})
            changed = sorted(k for k in before
                             if before.get(k) != after.get(k))
            rec["changed_axes"] = changed
            rec["changed_count"] = len(changed)
        entries.append(rec)
    if limit is not None:
        entries = entries[:limit]
    return {
        "sid": sid,
        "note": "reflog entries carry no round stamps (k15 metadata "
                "gap) — `seq` is the sequence index, the only ordering",
        "total": len(entries),
        "entries": entries,
    }


def tuning(a: Artifact, sid: str | None = None) -> dict:
    """5. Tuning placeholder: per-instance mass/cell summaries.

    Capacity K(c) is derived at engine runtime and NOT persisted, so
    fraction-of-capacity questions (what share of a cell's capacity a
    lineage holds) cannot be answered from the artifact — documented in
    the returned ``note``."""
    note = ("mass/cell/rain summaries only. Capacity K(c) is derived at "
            "engine runtime and is not persisted in the dump, so "
            "fraction-of-capacity questions (e.g. what share of a "
            "cell's total capacity a lineage holds) cannot be answered "
            "from the artifact until the world capacity product is "
            "persisted alongside it.")
    st = a.state()
    inst = st["instances"]
    if sid is not None:
        mine = sorted((iid, rec) for iid, rec in inst.items()
                      if rec["sid"] == sid)
        total_cells = sum(rec["cells"] for _, rec in mine)
        total_mass = sum(rec["mass"] for _, rec in mine)
        total_rain = sum(rec["rain"] for _, rec in mine)
        return {
            "sid": sid,
            "note": note,
            "instances": len(mine),
            "cells": total_cells,
            "mass": _round(total_mass),
            "mass_per_cell": _round(total_mass / max(total_cells, 1)),
            "rain_per_cell": _round(total_rain / max(total_cells, 1)),
            "rows": [
                {"iid": iid, "cells": rec["cells"],
                 "mass": _round(rec["mass"]), "rain": _round(rec["rain"])}
                for iid, rec in mine
            ],
        }
    per_sid: dict[str, dict] = {}
    for iid, rec in sorted(inst.items()):
        d = per_sid.setdefault(rec["sid"],
                               {"instances": 0, "cells": 0, "mass": 0.0,
                                "rain": 0.0})
        d["instances"] += 1
        d["cells"] += rec["cells"]
        d["mass"] += rec["mass"]
        d["rain"] += rec["rain"]
    return {
        "note": note,
        "lineages": st["lineages"],
        "instances": len(inst),
        "retired": len(st["retired"]),
        "per_sid": {
            sid: {"instances": d["instances"], "cells": d["cells"],
                  "mass": _round(d["mass"]),
                  "mass_per_cell": _round(d["mass"] / max(d["cells"], 1)),
                  "rain_per_cell": _round(d["rain"] / max(d["cells"], 1))}
            for sid, d in sorted(per_sid.items())
        },
    }


def list_species(a: Artifact) -> dict:
    """Discovery aid: the live species roster (tree x state join)."""
    idx = _species_index(a)
    st = a.state()
    per_sid: dict[str, dict] = {}
    for rec in st["instances"].values():
        d = per_sid.setdefault(rec["sid"],
                               {"instances": 0, "cells": 0, "mass": 0.0})
        d["instances"] += 1
        d["cells"] += rec["cells"]
        d["mass"] += rec["mass"]
    rows = []
    for sid in sorted(per_sid):
        node = idx.get(sid, {})
        rows.append({
            "sid": sid,
            "rank": node.get("rank"),
            "binomial": _node_names(node)[0],
            "named_ancestor":
                (_nearest_named_ancestor(a, node) or {}).get("binomial"),
            "instances": per_sid[sid]["instances"],
            "cells": per_sid[sid]["cells"],
            "mass": _round(per_sid[sid]["mass"]),
        })
    rows.sort(key=lambda r: (-r["cells"], r["sid"]))
    return {"live": len(rows), "rows": rows}


# ── world join (optional; degraded gracefully) ─────────────────────────


def _input_seed(a: Artifact) -> int:
    """The k11 worldgen seed from the manifest input chain; falls back
    to the run's own seed."""
    for inp in a.manifest().get("inputs", []):
        if inp.get("generator") == "k11_worldgen" and inp.get("seed"):
            return int(inp["seed"])
    return int(a.state()["seed"])


def _biome_names() -> list[str]:
    """Biome id -> name from the k11 legend; numeric fallback keeps the
    tool alive if the legend module moves."""
    try:
        from exp.k11_worldgen.biomes import BIOMES
        return [b["name"] for b in BIOMES]
    except Exception:                      # pragma: no cover
        return []


def world_join(a: Artifact) -> dict:
    """Resolve the k14 world product for this run and load the anchor
    (256²) biome + substrate maps.  Pure function of the persisted
    world products; raises WorldUnavailable with a clear message when a
    product is missing.

    substrate class = argmin(ground_d2, axis=0) — the exact anchor map
    the engine derives (build_ground class_id = argmax(weighted), and
    d2 = -log(weighted) so argmin(d2) == argmax(weighted)).
    """
    import numpy as np                    # world products are .npz
    seed = _input_seed(a)
    repo = _repo_root(a.dir)
    k11 = repo / "exp" / "k11_worldgen" / "out" / f"seed_{seed:08d}"
    k14 = repo / "exp" / "k14_worldprod" / "out" / f"seed_{seed:08d}"
    if not (k11 / "world.npz").is_file():
        raise WorldUnavailable(
            f"k11 world product missing at {k11 / 'world.npz'} — run "
            f"exp.k11_worldgen for seed {seed} first")
    if not (k14 / "derived.npz").is_file():
        raise WorldUnavailable(
            f"k14 world product missing at {k14 / 'derived.npz'} — run "
            f"exp.k14_worldprod for seed {seed} first")
    with np.load(k11 / "world.npz") as z:
        biome = np.asarray(z["w_biome_map"], dtype=np.int64).ravel()
    with np.load(k14 / "derived.npz") as z:
        d2 = z["ground_d2"]
        meta = json.loads(str(z["ground_meta"]))
    substrate = np.argmin(d2, axis=0).astype(np.int64).ravel()
    names = _biome_names()
    if not names:
        names = [f"biome_{i}" for i in range(int(biome.max()) + 1)]
    return {
        "seed": seed,
        "biome_map": biome,
        "biome_names": names,
        "substrate_map": substrate,
        "substrate_names": [m["name"] for m in meta],
        "sources": {"k11": str(k11 / "world.npz"),
                    "k14": str(k14 / "derived.npz")},
    }


# ── CLI ────────────────────────────────────────────────────────────────


def _make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="artifact_query.py",
        description="K15 artifact query / debug tool (ticket 0038).")
    p.add_argument("--dir", default=None, metavar="DIR",
                   help="artifact dir (default: the repo's "
                        "exp/k15_simdiff/out/seed_00000001)")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="CMD")

    q = sub.add_parser("identity", help="sid -> rank, names, trait axes")
    q.add_argument("sid")

    q = sub.add_parser("range", help="cells, bbox, patches, biome mix")
    q.add_argument("sid")
    q.add_argument("--world", action="store_true",
                   help="join biome/substrate per cell (degrades to a "
                        "note when the world products are missing)")

    q = sub.add_parser("coexist", help="species sharing >= X of A's cells")
    q.add_argument("sid")
    q.add_argument("--share", type=float, required=True, metavar="X",
                   help="threshold 0..1 (fraction of A's cells)")

    q = sub.add_parser("events", help="the species' reflog entries")
    q.add_argument("sid")
    q.add_argument("--limit", type=int, default=None, metavar="N",
                   help="cap the number of entries shown")

    q = sub.add_parser("tuning", help="per-instance mass/cell summaries")
    q.add_argument("sid", nargs="?", default=None,
                   help="restrict to one species (default: all)")

    sub.add_parser("list", help="live species roster (discovery aid)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _make_parser().parse_args(argv)
    if args.dir:
        out_dir = Path(args.dir)
    else:
        out_dir = (Path(__file__).resolve().parent.parent
                   / "exp" / "k15_simdiff" / "out" / "seed_00000001")
    try:
        a = Artifact(out_dir)
        if args.cmd == "identity":
            result = identity(a, args.sid)
        elif args.cmd == "range":
            world = None
            if args.world:
                try:
                    world = world_join(a)
                except WorldUnavailable as e:
                    print(f"note: world join unavailable — {e}",
                          file=sys.stderr)
            result = range_info(a, args.sid, world)
        elif args.cmd == "coexist":
            result = coexist(a, args.sid, args.share)
        elif args.cmd == "events":
            result = events(a, args.sid, args.limit)
        elif args.cmd == "tuning":
            result = tuning(a, args.sid)
        elif args.cmd == "list":
            result = list_species(a)
        else:                              # pragma: no cover
            raise AssertionError(args.cmd)
    except ArtifactError as e:
        print(f"artifact_query: {e}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True,
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
