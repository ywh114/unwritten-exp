"""Cross-exp artifact resolution (owner ruling 2026-07-29: don't copy —
reference by (generator, seed) with provenance).

Every generated artifact (K11 world dump, K13 tree JSON — fauna/flora)
is a REGENERABLE CACHE, never a source of truth and never copied into
a consumer's tree. Consumers resolve the producer's artifact by
(generator, seed), check its provenance stamp (version + git commit +
byte hash), and regenerate via the producer's CLI when missing.

    from exp.artifacts import find, require, stamp, write_manifest

    world_dir = require("k11", seed=1)          # path, regenerating if needed
    info = stamp("k11", seed=1)                 # provenance dict
    write_manifest(out_dir, inputs=[("k11", 1), ("flora", 1)])

Layout convention (producer-owned):
    k11   -> exp/k11_worldgen/out/seed_{seed:08d}/   (world.json + world.npz)
    k13   -> exp/k13_treegen/out/k13_seed{seed:08d}.json
    flora -> exp/k13_treegen/out/flora_seed{seed:08d}.json
    k15   -> exp/k15_simdiff/out/seed_{seed:08d}/    (the ticket-0013
             delivery dump: state/density/tree/reflog + display layers)

The stamp is the contract: {generator, version, seed, commit, sha256}.
``sha256`` covers the canonical artifact bytes (for k11: world.json
then world.npz, in order) — computed on demand, never stored inside
the artifact itself (no self-reference).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class GeneratorSpec:
    name: str
    rel_path: str            # format string with {seed:08d}
    is_dir: bool
    stamp_files: tuple[str, ...]  # canonical-byte files, hashed in order
    version_key: str         # stamp field carrying the schema version
    cli: tuple[str, ...]     # regen command after `python -m`; "{seed}"
                             # is formatted with the seed number
    meta_file: str = "world.json"  # dir manifests' JSON header file
                             # (k15's delivery dump names it state.json)


GENERATORS: dict[str, GeneratorSpec] = {
    "k11": GeneratorSpec(
        name="k11_worldgen",
        rel_path="exp/k11_worldgen/out/seed_{seed:08d}",
        is_dir=True,
        stamp_files=("world.json", "world.npz"),
        version_key="k11_version",
        cli=("exp.k11_worldgen", "demo", "--seed", "{seed}")),
    "k13": GeneratorSpec(
        name="k13_treegen",
        rel_path="exp/k13_treegen/out/k13_seed{seed:08d}.json",
        is_dir=False,
        stamp_files=(),
        version_key="version",
        cli=("exp.k13_treegen.fauna", "{seed}")),
    "flora": GeneratorSpec(
        name="k13_flora",
        rel_path="exp/k13_treegen/out/flora_seed{seed:08d}.json",
        is_dir=False,
        stamp_files=(),
        version_key="version",
        cli=("exp.k13_treegen.flora", "{seed}")),
    "k15": GeneratorSpec(
        name="k15_simdiff",
        rel_path="exp/k15_simdiff/out/seed_{seed:08d}",
        is_dir=True,
        stamp_files=("state.json", "density.json", "tree.json",
                     "reflog.json"),
        version_key="k15_version",
        meta_file="state.json",
        cli=("exp.k15_simdiff", "--seed", "{seed}", "--rounds", "8")),
}

_commit_cache: str | None = None


def current_commit() -> str:
    """The repo's current HEAD (cached; empty string outside a repo)."""
    global _commit_cache
    if _commit_cache is None:
        try:
            _commit_cache = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                capture_output=True, text=True, check=True).stdout.strip()
        except Exception:
            _commit_cache = ""
    return _commit_cache


def _spec(generator: str) -> GeneratorSpec:
    if generator not in GENERATORS:
        raise KeyError(f"unknown generator {generator!r} "
                       f"(known: {sorted(GENERATORS)})")
    return GENERATORS[generator]


def artifact_path(generator: str, seed: int) -> Path:
    """The canonical path for (generator, seed) — existence not checked."""
    spec = _spec(generator)
    return REPO_ROOT / spec.rel_path.format(seed=seed)


def find(generator: str, seed: int) -> Path | None:
    """The artifact path if it exists (dir with all stamp files, or the
    file itself), else None."""
    spec = _spec(generator)
    p = artifact_path(generator, seed)
    if spec.is_dir:
        if p.is_dir() and all((p / f).exists() for f in spec.stamp_files):
            return p
        return None
    return p if p.is_file() else None


def _stamp_files(generator: str, seed: int) -> list[Path]:
    spec = _spec(generator)
    p = artifact_path(generator, seed)
    if spec.is_dir:
        return [p / f for f in spec.stamp_files]
    return [p]


def artifact_hash(generator: str, seed: int) -> str:
    """sha256 over the canonical artifact bytes (stamp files in order)."""
    h = hashlib.sha256()
    for f in _stamp_files(generator, seed):
        h.update(f.name.encode() + b"\0")
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def stamp(generator: str, seed: int, with_hash: bool = True) -> dict:
    """The provenance stamp for (generator, seed): generator name,
    schema version (from the artifact's own meta), seed, producing git
    commit, and the canonical byte hash."""
    spec = _spec(generator)
    if find(generator, seed) is None:
        raise FileNotFoundError(f"no {generator} artifact for seed {seed}")
    p = artifact_path(generator, seed)
    meta_file = (p / spec.meta_file) if spec.is_dir else p
    meta = json.loads(meta_file.read_text())
    if spec.is_dir:
        version = meta.get(spec.version_key)
        commit = meta.get("commit")
    else:
        m = meta.get("meta", {})
        version = m.get(spec.version_key)
        commit = m.get("commit")
    out = {"generator": spec.name, "version": version, "seed": seed,
           "commit": commit}
    if with_hash:
        out["sha256"] = artifact_hash(generator, seed)
    return out


def require(generator: str, seed: int, regenerate: bool = True) -> Path:
    """The artifact path, regenerating via the producer's CLI when
    missing. Staleness (version/commit drift) is the CONSUMER's call —
    compare stamp() against expectations and regenerate deliberately."""
    found = find(generator, seed)
    if found is not None:
        return found
    if not regenerate:
        raise FileNotFoundError(f"no {generator} artifact for seed {seed}")
    spec = _spec(generator)
    cmd = [sys.executable, "-m",
           *[a.format(seed=seed) for a in spec.cli]]
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    found = find(generator, seed)
    if found is None:
        raise RuntimeError(f"{generator} regen for seed {seed} produced "
                           f"no artifact at {artifact_path(generator, seed)}")
    return found


def write_manifest(out_dir: str | Path, inputs: list[tuple[str, int]],
                   note: str = "") -> Path:
    """Record a derived product's inputs (generator, seed, stamp incl.
    byte hash) in <out_dir>/manifest.json — the chain rule: any derived
    artifact is rebuildable from its manifest's inputs."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {
        "inputs": [stamp(g, s) for g, s in inputs],
        "created_commit": current_commit(),
        "note": note,
    }
    path = out / "manifest.json"
    path.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return path
