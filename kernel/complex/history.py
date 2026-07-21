"""Versioning — append-only commit history.

ComplexHistory replays commits to reconstruct the complex at any version.
Changes are commits, never edits (A2 §6, invariant 16).
"""

from __future__ import annotations

import copy
from typing import Any

from kernel.complex.cells import Complex, Edge, Node, Patch
from kernel.gmm_dynamics.dynamics import DriftField


class ComplexHistory:
    """Append-only list of commits for versioned topology."""

    def __init__(self, initial: Complex) -> None:
        self._initial = initial
        self._commits: list[dict] = []

    def add(self, commit: dict) -> None:
        """Append a commit to the log."""
        self._commits.append(commit)

    @property
    def version(self) -> int:
        """Current version (= number of commits applied)."""
        return len(self._commits)

    def at(self, version: int) -> Complex:
        """Reconstruct the complex at the given version (0 = initial)."""
        if version < 0:
            version = max(0, len(self._commits) + version)
        if version == 0:
            return self._initial
        if version > len(self._commits):
            raise IndexError(
                f"Version {version} > max {len(self._commits)}"
            )
        complex = self._initial
        for i in range(version):
            complex = _apply_commit(complex, self._commits[i])
        return complex

    def at_latest(self) -> Complex:
        """Reconstruct the complex at the latest version."""
        return self.at(len(self._commits))

    def __repr__(self) -> str:
        return (
            f"ComplexHistory(version={len(self._commits)}, "
            f"initial={self._initial})"
        )


def _apply_commit(complex: Complex, commit: dict) -> Complex:
    """Apply a single commit to a complex, returning a new Complex."""
    ctype = commit["type"]

    new_nodes = dict(complex.nodes)
    new_edges = dict(complex.edges)
    new_patches = dict(complex.patches)

    if ctype == "split_patch":
        # remove parent
        pid = commit["patch_id"]
        if pid in new_patches:
            del new_patches[pid]

        # add new detail edges
        for ed in commit.get("new_edges", []):
            new_edges[ed["id"]] = Edge(
                id=ed["id"],
                node_a=ed["node_a"],
                node_b=ed["node_b"],
                length=ed["length"],
                kind=ed["kind"],
                quality=ed["quality"],
                polyline=tuple(tuple(p) for p in ed["polyline"]),
            )

        # add children
        for child in commit["children"]:
            new_patches[child["id"]] = Patch(
                id=child["id"],
                field=DriftField(
                    mu=child["field_mu"],
                    theta=child["field_theta"],
                    sigma=child["field_sigma"],
                ),
                boundary_edges=tuple(child["boundary_edges"]),
                measure=child["measure"],
                parent=child["parent"],
            )

    elif ctype == "split_edge":
        eid = commit["edge_id"]
        # remove parent edge
        if eid in new_edges:
            del new_edges[eid]

        # add new node
        nn = commit["new_node"]
        new_nodes[nn["id"]] = Node(id=nn["id"], pos=tuple(nn["pos"]))

        # add child edges
        for key in ("child_a", "child_b"):
            ce = commit[key]
            new_edges[ce["id"]] = Edge(
                id=ce["id"],
                node_a=ce["node_a"],
                node_b=ce["node_b"],
                length=ce["length"],
                kind=ce["kind"],
                quality=ce["quality"],
                polyline=tuple(tuple(p) for p in ce["polyline"]),
            )

    elif ctype == "cover_transition":
        # cover transitions don't change the complex structure
        pass

    elif ctype == "patch_transition":
        # allow patch-level state changes (for cover demo)
        pass

    return Complex(
        list(new_nodes.values()),
        list(new_edges.values()),
        list(new_patches.values()),
    )
