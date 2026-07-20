"""K5 — the promise ledger: a database with opinions.

The constraint engine behind every lazy-history decision in the Unwritten
world.  Operations:

* assert_()  — commit a promise; lower-authority conflicts suspend.
* discharge / break / expire — terminal states; suspended dependents
  re-examine for reconciliation.
* suspend / reconcile — TMS-lite: override a promise, attempt to
  restore it when the override resolves.
* validate() — return currently-conflicting active pairs.
* density(region) — sum of active-promise strengths touching a region.
* graveyard() — discharged / expired / broken promise archive.

Pure logic.  No LLM, no positions, no engine — this is the design spec
§4 promise formalism made code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kernel.hashrng import Stream
from kernel.promise_ledger.predicates import Predicate, PredicateKind
from kernel.promise_ledger.promise import Promise, PromiseState, make_id


@dataclass
class PromiseLedger:
    """The heart of the constraint system.

    `seed`: when given, promise ids are deterministic (derived from the
    K1 hashrng stream), so whole scenarios replay byte-identically — the
    lab's determinism convention. When None, ids are random UUIDs.
    """

    _by_id: dict[str, Promise] = field(default_factory=dict)
    seed: int | None = None
    _id_counter: int = 0

    def _next_id(self) -> str:
        if self.seed is None:
            return make_id()
        self._id_counter += 1
        return f"{Stream(self.seed, 'k5.promise-ledger').u64(0, self._id_counter):012x}"

    # ---- assertion ---------------------------------------------------------

    def assert_(
        self,
        predicate: Predicate,
        *,
        scope: str | None = None,
        window: tuple[float, float | None] = (0.0, None),
        strength: float = 1.0,
        provenance: str = "canon",
        note: str = "",
        depends_on: tuple[str, ...] = (),
    ) -> str:
        """Commit a new promise.

        Returns the new promise id.  Raises ValueError if a same-or-higher
        -authority active promise conflicts with it.  Lower-authority
        conflicts are automatically suspended (with this promise recorded as
        `suspended_by`).
        """
        pid = self._next_id()
        p = Promise(
            id=pid, scope=scope, predicate=predicate, window=window,
            strength=strength, provenance=provenance, note=note,
            depends_on=depends_on,
        )
        self._by_id[pid] = p
        self._enforce_authority(p)
        return pid

    # ---- termination -------------------------------------------------------

    def discharge(self, pid: str, *, note: str = "") -> None:
        """Fulfil a promise — move it to the graveyard."""
        p = self._require_active(pid)
        p.state = PromiseState.DISCHARGED
        if note:
            p.note += f" | discharged: {note}"
        self._on_terminal(pid)

    def break_(self, pid: str, *, note: str = "") -> None:
        """Violate a promise — mark it broken."""
        p = self._require_active(pid)
        p.state = PromiseState.BROKEN
        if note:
            p.note += f" | broken: {note}"
        self._on_terminal(pid)

    def expire(self, at_time: float) -> list[str]:
        """Expire all active promises whose window has closed by `at_time`.

        Returns the list of expired ids."""
        expired: list[str] = []
        for pid, p in list(self._by_id.items()):
            if p.state != PromiseState.ACTIVE:
                continue
            end = p.window[1]
            if end is not None and end <= at_time:
                p.state = PromiseState.EXPIRED
                expired.append(pid)
        for pid in expired:
            self._on_terminal(pid)
        return expired

    # ---- TMS-lite suspension -----------------------------------------------

    def suspend(self, pid: str, *, suspended_by: str, note: str = "") -> None:
        """Externally suspend a promise (e.g. regime change cascade)."""
        p = self._require_active(pid)
        self._set_suspended(p, suspended_by, note)

    def reconcile(self) -> int:
        """Try to re-activate every suspended promise whose `suspended_by`
        is no longer active, provided it conflicts with nothing now active.

        Returns the number of promises restored."""
        restored = 0
        # iterate over a snapshot of ids so we can mutate safely
        for pid in list(self._by_id):
            p = self._by_id[pid]
            if p.state != PromiseState.SUSPENDED:
                continue
            # if the suspender is still active, stay suspended.
            # external suspenders (not in ledger) are permanent blocks.
            if p.suspended_by:
                if p.suspended_by not in self._by_id:
                    continue  # external blocker, don't touch
                susp = self._by_id[p.suspended_by]
                if susp.state == PromiseState.ACTIVE:
                    continue
            # check that all dependencies are active
            if p.depends_on and any(
                d not in self._by_id or self._by_id[d].state != PromiseState.ACTIVE
                for d in p.depends_on
            ):
                continue
            # check for conflicts with currently active promises
            if any(self._conflicts(p, a) for a in self._active() if a.id != p.id):
                continue
            p.state = PromiseState.ACTIVE
            p.suspended_by = None
            restored += 1
        return restored

    # ---- validation --------------------------------------------------------

    def validate(self) -> list[tuple[Promise, Promise]]:
        """Return every pair of active promises that conflict."""
        active = list(self._active())
        pairs: list[tuple[Promise, Promise]] = []
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                if self._conflicts(active[i], active[j]):
                    pairs.append((active[i], active[j]))
        return pairs

    # ---- density index -----------------------------------------------------

    def density(self, region: str) -> float:
        """Sum of `strength` of every active promise that touches `region`
        (in scope, subject, or object)."""
        total = 0.0
        for p in self._active():
            if (p.scope == region
                    or p.predicate.subject == region
                    or p.predicate.object == region):
                total += p.strength
        return total

    def density_ranking(self) -> list[tuple[str, float]]:
        """All regions mentioned by any promise, ranked by density descending."""
        regions: set[str] = set()
        for p in self._by_id.values():
            if p.scope:
                regions.add(p.scope)
            if p.predicate.subject:
                regions.add(p.predicate.subject)
            if p.predicate.object:
                regions.add(p.predicate.object)
        ranked = [(r, self.density(r)) for r in regions]
        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    # ---- graveyard ---------------------------------------------------------

    def graveyard(self, *, scope: str | None = None) -> list[Promise]:
        """All non-active promises, sorted by id for stable output."""
        result = [p for p in self._by_id.values()
                  if p.state != PromiseState.ACTIVE]
        if scope is not None:
            result = [p for p in result if p.scope == scope]
        return sorted(result, key=lambda p: p.id)

    # ---- queries -----------------------------------------------------------

    def get(self, pid: str) -> Promise | None:
        return self._by_id.get(pid)

    def active(self, *, scope: str | None = None) -> list[Promise]:
        result = list(self._active())
        if scope is not None:
            result = [p for p in result if p.scope == scope]
        return result

    def all(self) -> list[Promise]:
        return list(self._by_id.values())

    # ========================================================================
    # internals
    # ========================================================================

    def _active(self):
        # generator, not list, so callers can short-circuit
        return (p for p in self._by_id.values() if p.state == PromiseState.ACTIVE)

    def _require_active(self, pid: str) -> Promise:
        p = self._by_id.get(pid)
        if p is None:
            raise KeyError(f"unknown promise id {pid}")
        if p.state != PromiseState.ACTIVE:
            raise ValueError(f"promise {pid} is {p.state.value}, not active")
        return p

    def _set_suspended(self, p: Promise, by: str, note: str = "") -> None:
        p.state = PromiseState.SUSPENDED
        p.suspended_by = by
        if note:
            p.note += f" | suspended: {note}"
        # cascade to dependents
        for dep in list(self._by_id.values()):
            if dep.state == PromiseState.ACTIVE and p.id in dep.depends_on:
                self._set_suspended(dep, by, note=f"cascade: {p.id} suspended")

    def _on_terminal(self, pid: str) -> None:
        """After discharge/break/expire, re-examine promises suspended by it."""
        for p in list(self._by_id.values()):
            if p.state == PromiseState.SUSPENDED and p.suspended_by == pid:
                p.suspended_by = None  # the blocker is gone
        self.reconcile()

    def _enforce_authority(self, new: Promise) -> None:
        for existing in list(self._by_id.values()):
            if existing.id == new.id or existing.state != PromiseState.ACTIVE:
                continue
            if not self._conflicts(new, existing):
                continue
            # Conflict — resolve by authority
            if existing.authority < new.authority:
                # new is stronger — overrides existing
                self._set_suspended(existing, new.id,
                                    note=f"overridden by {new.id} ({new.provenance})")
            elif existing.authority > new.authority:
                # new is weaker — allowed but suspended
                self._set_suspended(new, existing.id,
                                    note=f"overridden by {existing.id} ({existing.provenance})")
                return  # promise is in the ledger, just suspended
            else:
                del self._by_id[new.id]
                raise ValueError(
                    f"{new.id}: conflicts with same-authority promise "
                    f"{existing.id} ({existing.provenance})"
                )

    # ---- conflict rules ----------------------------------------------------

    def _conflicts(self, a: Promise, b: Promise) -> bool:
        """Hard-coded contradiction detection.  Intentionally small."""
        pk_a, pk_b = a.predicate.kind, b.predicate.kind
        s_a, s_b = a.predicate.subject, b.predicate.subject
        o_a, o_b = a.predicate.object, b.predicate.object
        da, db = a.predicate.detail, b.predicate.detail

        # 1.  Two different entities CONTROLS the same region
        if pk_a == pk_b == PredicateKind.CONTROLS and o_a == o_b and s_a != s_b:
            return True

        # 2.  HOSTILE ↔ ALLIED between the same pair (order insensitive)
        if {pk_a, pk_b} == {PredicateKind.HOSTILE, PredicateKind.ALLIED}:
            pair_a = frozenset((s_a, o_a))
            pair_b = frozenset((s_b, o_b))
            if pair_a == pair_b and "" not in pair_a:
                return True

        # 3.  A dead entity cannot hold active status
        dead_a = s_a if (pk_a == PredicateKind.IS and da == "dead") else None
        dead_b = s_b if (pk_b == PredicateKind.IS and db == "dead") else None
        _status_kinds = (
            PredicateKind.IS, PredicateKind.CONTROLS, PredicateKind.HOLDS,
            PredicateKind.LOCATED, PredicateKind.FEALTY,
        )
        if dead_a and s_b == dead_a and pk_b in _status_kinds and db != "dead":
            return True
        if dead_b and s_a == dead_b and pk_a in _status_kinds and da != "dead":
            return True

        # 4.  Banished entity cannot be located or control territory
        if pk_a == PredicateKind.IS and da == "banished":
            if s_a == s_b and pk_b in (PredicateKind.LOCATED, PredicateKind.CONTROLS):
                return True
        if pk_b == PredicateKind.IS and db == "banished":
            if s_a == s_b and pk_a in (PredicateKind.LOCATED, PredicateKind.CONTROLS):
                return True

        return False
