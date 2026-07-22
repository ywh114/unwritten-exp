"""Dependency-directed test selection (user 2026-07-23).

The full suite takes ~1 min; most of it is irrelevant to any given
change. This runner builds the import graph between the repo's
packages (kernel.*, exp.*, llm.*, capability.*) by AST-scanning
imports — no manifest to maintain — and runs only the tests of:

  the target package(s), plus every package that TRANSITIVELY DEPENDS
  on them (reverse reachability).

So `k11` runs just the K11 tests, but `hashrng` runs K1's tests plus
K11's and anything else importing kernel.hashrng.

Usage:
  uv run python tools/testgraph.py k11 [k9 ...]   # explicit targets
  uv run python tools/testgraph.py --git          # targets from
                                                  # git status/diff
  extra pytest args after `--` (default: -q -m "not slow")
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOPS = ("kernel", "exp", "llm", "capability")


def packages() -> dict[str, Path]:
    """Package name -> path. Packages are subpackages with __init__.py
    (kernel.complex, exp.k11_worldgen) and top-level modules
    (kernel.hashrng)."""
    pkgs: dict[str, Path] = {}
    for top in TOPS:
        d = ROOT / top
        if not d.is_dir():
            continue
        for sub in sorted(d.iterdir()):
            if sub.is_dir() and (sub / "__init__.py").exists():
                pkgs[f"{top}.{sub.name}"] = sub
            elif sub.suffix == ".py" and sub.stem != "__init__":
                pkgs[f"{top}.{sub.stem}"] = sub
    return pkgs


def imports_of(path: Path) -> set[str]:
    """Absolute dotted imports found under a package path."""
    files = [path] if path.is_file() else sorted(path.rglob("*.py"))
    deps: set[str] = set()
    for f in files:
        try:
            tree = ast.parse(f.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                deps.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    deps.add(node.module)
    return deps


def build_graph(pkgs: dict[str, Path]) -> dict[str, set[str]]:
    """Package -> packages it depends on (longest-prefix match)."""
    names = sorted(pkgs, key=len, reverse=True)
    graph: dict[str, set[str]] = {p: set() for p in pkgs}
    for p, path in pkgs.items():
        for imp in imports_of(path):
            for n in names:
                if imp == n or imp.startswith(n + "."):
                    if n != p:
                        graph[p].add(n)
                    break
    return graph


def reverse_reachable(graph: dict[str, set[str]], targets: set[str]) -> set[str]:
    """targets ∪ everything that transitively depends on them."""
    dependents: dict[str, set[str]] = {p: set() for p in graph}
    for p, deps in graph.items():
        for d in deps:
            dependents[d].add(p)
    seen = set(targets)
    stack = list(targets)
    while stack:
        p = stack.pop()
        for q in dependents.get(p, ()):
            if q not in seen:
                seen.add(q)
                stack.append(q)
    return seen


def resolve(pkgs: dict[str, Path], target: str) -> set[str]:
    """Fuzzy target -> package names: exact, then substring on the
    package short name ('k11' -> exp.k11_worldgen)."""
    if target in pkgs:
        return {target}
    hits = {p for p in pkgs if target in p.rsplit(".", 1)[-1]}
    return hits


def git_targets(pkgs: dict[str, Path]) -> set[str]:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    targets: set[str] = set()
    for line in out.splitlines():
        rel = line[3:].split(" -> ")[-1]
        for p, path in pkgs.items():
            rp = str(path.relative_to(ROOT))
            if rel == rp or rel.startswith(rp + "/"):
                targets.add(p)
    return targets


def test_files(pkgs: dict[str, Path], affected: set[str]) -> list[str]:
    files: list[str] = []
    for p in sorted(affected):
        path = pkgs[p]
        if path.is_dir():
            files.extend(str(f) for f in sorted(path.rglob("test_*.py")))
    return files


def main(argv: list[str]) -> int:
    args, passthrough = argv, ["-q", "-m", "not slow"]
    if "--" in argv:
        i = argv.index("--")
        args, passthrough = argv[:i], argv[i + 1:]
    pkgs = packages()
    if "--git" in args:
        targets = git_targets(pkgs)
        args = [a for a in args if a != "--git"]
    else:
        targets = set()
    for a in args:
        targets |= resolve(pkgs, a)
    if not targets:
        print("no targets resolved (usage: testgraph.py <pkg...> | --git)")
        return 0
    graph = build_graph(pkgs)
    affected = reverse_reachable(graph, targets)
    files = test_files(pkgs, affected)
    print(f"targets: {sorted(targets)}")
    print(f"affected packages: {sorted(affected)}")
    print(f"test files: {[str(Path(f).relative_to(ROOT)) for f in files]}")
    if not files:
        print("no test files for the affected packages")
        return 0
    return subprocess.run(["pytest", *passthrough, *files], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
