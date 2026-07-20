"""K3 acceptance tests — measurement semantics with deterministic collapse.

Lab spec §2 K3 done-when items: rect_mass exactness, presence/count
conservation, collapse determinism, filtration invariant (1e5 trials),
refine→coarsen identity+diffusion, hysteresis, identity conditioning,
and K2 integration.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from kernel.gmm_dynamics.gmm import Gaussian, GMM
from kernel.hashrng import Stream

from kernel.collapse.field import (
    Silhouette,
    Resident,
    absence_renormalize,
    coarsen,
    collapse_field,
    presence_count,
    refine_identity,
)
from kernel.collapse.geometry import Rect, rect_mass
from kernel.collapse.tiers import HysteresisLadder, Tier


# ---- helpers ---------------------------------------------------------------

def _gauss(mean, cov) -> GMM:
    return GMM(np.ones(1), np.array(mean).reshape(1, 2),
               np.array(cov).reshape(1, 2, 2))


# ---------------------------------------------------------------------------
# 1. rect_mass
# ---------------------------------------------------------------------------

class TestRectMass:
    def test_rho_zero_exact(self):
        """axis-aligned cov → product of 1-D normals."""
        mean = np.array([2.0, -1.0])
        cov = np.diag([9.0, 4.0])
        rect = Rect(-4.0, -3.0, 3.0, 1.0)
        got = rect_mass(mean, cov, rect)
        # per-axis:
        sx, sy = 3.0, 2.0
        px = (0.5*(1+math.erf((3-2)/sx/math.sqrt(2)))
              - 0.5*(1+math.erf((-4-2)/sx/math.sqrt(2))))
        py = (0.5*(1+math.erf((1+1)/sy/math.sqrt(2)))
              - 0.5*(1+math.erf((-3+1)/sy/math.sqrt(2))))
        assert got == pytest.approx(px * py, abs=1e-10)

    def test_total_plane_near_one(self):
        """a rect covering ±10σ → mass ≈ 1.0."""
        mean = np.array([5.0, 5.0])
        cov = np.diag([4.0, 4.0])
        rect = Rect(-100.0, -100.0, 100.0, 100.0)
        assert rect_mass(mean, cov, rect) == pytest.approx(1.0, abs=1e-4)

    def test_vs_monte_carlo(self):
        """correlated cov, 200k seeded MC."""
        mean = np.array([0.0, 0.0])
        cov = np.array([[4.0, 1.5], [1.5, 2.0]])
        rect = Rect(-2.0, -1.0, 1.5, 2.0)
        exact = rect_mass(mean, cov, rect)

        rng = np.random.RandomState(42)
        samples = rng.multivariate_normal(mean, cov, size=200_000)
        inside = np.sum((samples[:, 0] >= rect.x0) & (samples[:, 0] <= rect.x1) &
                        (samples[:, 1] >= rect.y0) & (samples[:, 1] <= rect.y1))
        mc = inside / 200_000
        assert exact == pytest.approx(mc, abs=1.5e-3)

    def test_degenerate_point_mass(self):
        mean = np.array([5.0, 5.0])
        cov = np.diag([0.0, 0.0])
        assert rect_mass(mean, cov, Rect(4, 4, 6, 6)) == 1.0
        assert rect_mass(mean, cov, Rect(10, 10, 20, 20)) == 0.0


# ---------------------------------------------------------------------------
# 2. presence / absence
# ---------------------------------------------------------------------------

class TestPresenceAbsence:
    def test_presence_count_sum_to_N(self):
        field = GMM(np.array([5.0, 4.0, 3.0]),
                     np.array([[60, 55], [20, 30], [85, 15]]),
                     np.tile(np.eye(2) * 25.0, (3, 1, 1)))
        rect = Rect(0, 0, 100, 100)
        pc = presence_count(field, rect)
        assert pc == pytest.approx(12.0, abs=1.5)  # most mass inside

    def test_absence_hard_count_conservation(self):
        field = GMM(np.array([5.0, 7.0]),
                     np.array([[20, 20], [80, 80]]),
                     np.tile(np.eye(2) * 100.0, (2, 1, 1)))
        N = field.weights.sum()
        result = absence_renormalize(field, Rect(-1000, -1000, -900, -900),
                                     hard_count=True)
        assert result.weights.sum() == pytest.approx(N, rel=1e-12)

    def test_absence_soft(self):
        field = GMM(np.array([10.0]),
                     np.array([[50, 50]]),
                     np.eye(2).reshape(1, 2, 2) * 400.0)
        result = absence_renormalize(field, Rect(0, 0, 50, 50), hard_count=False)
        assert result.weights.sum() < field.weights.sum()

    def test_zero_mass_raises(self):
        field = GMM(np.array([1.0]), np.array([[0, 0]]), np.eye(2).reshape(1, 2, 2) * 0.01)
        with pytest.raises(ValueError):
            absence_renormalize(field, Rect(-100, -100, 100, 100), hard_count=True)


# ---------------------------------------------------------------------------
# 3. determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_seed_same_result(self):
        field = GMM(np.array([5.0, 7.0]),
                     np.array([[30, 30], [70, 70]]),
                     np.tile(np.eye(2) * 50.0, (2, 1, 1)))
        rect = Rect(0, 0, 100, 100)
        s1 = collapse_field(field, rect, Stream(42, "k3.test"), clock=0)
        s2 = collapse_field(field, rect, Stream(42, "k3.test"), clock=0)
        assert [sil.id for sil in s1] == [sil.id for sil in s2]
        assert [sil.position for sil in s1] == [sil.position for sil in s2]

    def test_seed_plus_one_differs(self):
        field = GMM(np.array([5.0, 7.0]),
                     np.array([[30, 30], [70, 70]]),
                     np.tile(np.eye(2) * 50.0, (2, 1, 1)))
        rect = Rect(0, 0, 100, 100)
        s1 = collapse_field(field, rect, Stream(42, "k3.test"), clock=0)
        s2 = collapse_field(field, rect, Stream(43, "k3.test"), clock=0)
        assert s1[0].position != s2[0].position


# ---------------------------------------------------------------------------
# 4. filtration (1e5 trials)
# ---------------------------------------------------------------------------

class TestFiltration:
    def test_filtration_1e5_trials(self):
        """Filtration invariant: coarse facts always imply fine facts.
        Small synthetic field+roster, 1e5 stream seeds, batched."""
        field = GMM(np.array([5.0]),
                     np.array([[50.0, 50.0]]),
                     np.array([[[25.0, 0.0], [0.0, 25.0]]]))
        rect = Rect(20, 20, 80, 80)
        residents = [
            Resident(id="a", name="a", prior=Gaussian((45, 45), 36.0)),
            Resident(id="b", name="b", prior=Gaussian((55, 55), 36.0)),
            Resident(id="c", name="c", prior=Gaussian((40, 60), 25.0)),
            Resident(id="d", name="d", prior=Gaussian((60, 40), 25.0)),
            Resident(id="e", name="e", prior=Gaussian((50, 50), 49.0)),
        ]

        failures = 0
        N = 100_000
        for trial in range(N):
            stream = Stream(trial, "k3.filtration")
            silhouettes = collapse_field(field, rect, stream, clock=0)
            assigned: set[str] = set()
            for sil in silhouettes:
                ident = refine_identity(sil, residents, stream, clock=1 + trial,
                                        assigned_ids=assigned)
                assigned.add(ident.id)
                # invariant 1: position unchanged
                if not (math.isclose(ident.position[0], sil.position[0], rel_tol=1e-12)
                        and math.isclose(ident.position[1], sil.position[1], rel_tol=1e-12)):
                    failures += 1
                # invariant 2: resident's prior has non-zero density at position
                if ident.id not in {r.id for r in residents}:
                    failures += 1
                    continue
                r = next(r for r in residents if r.id == ident.id)
                # pdf check: compute Gaussian pdf manually
                dx = sil.position[0] - r.prior.means[0, 0]
                dy = sil.position[1] - r.prior.means[0, 1]
                v = float(r.prior.covs[0, 0, 0])  # isotropic
                pdf_val = math.exp(-(dx*dx + dy*dy) / (2*v)) / (2*math.pi*v)
                if pdf_val <= 0.0:
                    failures += 1
            # invariant 3: no double-assignment
            if len(assigned) != len(silhouettes):
                failures += 1

            if failures:
                break

        assert failures == 0, f"filtration violated at trial {trial}"


# ---------------------------------------------------------------------------
# 5. refine → coarsen = identity + diffusion
# ---------------------------------------------------------------------------

class TestCoarsenInvariant:
    def test_refine_coarsen_identity_plus_diffusion(self):
        """coarsen then compare: count preserved, mean preserved, cov grows."""
        field = GMM(np.array([5.0, 7.0]),
                     np.array([[30, 30], [70, 70]]),
                     np.tile(np.eye(2) * 30.0, (2, 1, 1)))
        rect = Rect(0, 0, 100, 100)
        stream = Stream(1, "k3.coarsen")
        sil = collapse_field(field, rect, stream, clock=0)

        residents = [
            Resident(id=f"r{i}", name=f"R{i}",
                     prior=Gaussian((s.position[0], s.position[1]), 25.0))
            for i, s in enumerate(sil)
        ]
        identities = []
        assigned: set[str] = set()
        for s in sil:
            identities.append(refine_identity(s, residents, stream, clock=10,
                                              assigned_ids=assigned))
            assigned.add(identities[-1].id)

        sigma, dt = 2.0, 0.5
        field2 = coarsen(identities, dt=dt, sigma=sigma)
        assert len(identities) == pytest.approx(field2.total_mass(), rel=1e-9)

        pos = np.array([i.position for i in identities])
        assert np.allclose(field2.mixture_mean(), pos.mean(axis=0), atol=1e-9)

        # cov should be (cov of positions) + σ²·dt·I
        expected_cov = np.cov(pos.T, bias=True) + np.eye(2) * sigma * sigma * dt
        assert np.allclose(field2.mixture_cov(), expected_cov, atol=1e-9)


# ---------------------------------------------------------------------------
# 6. hysteresis
# ---------------------------------------------------------------------------

class TestHysteresis:
    def test_no_flicker(self):
        ladder = HysteresisLadder(promote_radius=5.0, demote_epsilon=2.0)
        distances = [6, 4, 6, 4, 6, 4]  # oscillate inside band
        tiers: list[Tier] = []
        cur = Tier.FIELD
        for d in distances:
            cur = ladder.tier_for_distance(d, cur)
            tiers.append(cur)
        # should never see FIELD → SILHOUETTE → FIELD → SILHOUETTE
        for i in range(len(tiers) - 2):
            assert not (tiers[i] == tiers[i+2] == Tier.FIELD
                        and tiers[i+1] == Tier.SILHOUETTE)

    def test_promote_demote_boundaries(self):
        ladder = HysteresisLadder(promote_radius=10.0, demote_epsilon=1.0)
        # FIELD: promote at ≤ 10
        assert ladder.tier_for_distance(10, Tier.FIELD) == Tier.SILHOUETTE
        assert ladder.tier_for_distance(10.5, Tier.FIELD) == Tier.FIELD
        # SILHOUETTE: promote at ≤ 10, demote at ≥ 11
        assert ladder.tier_for_distance(10, Tier.SILHOUETTE) == Tier.IDENTITY
        assert ladder.tier_for_distance(10.5, Tier.SILHOUETTE) == Tier.SILHOUETTE
        assert ladder.tier_for_distance(11, Tier.SILHOUETTE) == Tier.FIELD
        # IDENTITY: demote at ≥ 11
        assert ladder.tier_for_distance(11, Tier.IDENTITY) == Tier.SILHOUETTE
        assert ladder.tier_for_distance(10, Tier.IDENTITY) == Tier.IDENTITY


# ---------------------------------------------------------------------------
# 7. identity conditioning
# ---------------------------------------------------------------------------

class TestIdentityConditioning:
    def test_outside_prior_never_assigned(self):
        field = GMM(np.array([4.0]),
                     np.array([[50, 50]]),
                     np.array([[[100, 0], [0, 100]]]))
        rect = Rect(0, 0, 100, 100)
        inside = [
            Resident(id="in1", name="I1", prior=Gaussian((50, 50), 25.0)),
            Resident(id="in2", name="I2", prior=Gaussian((50, 50), 25.0)),
            Resident(id="in3", name="I3", prior=Gaussian((50, 50), 25.0)),
            Resident(id="in4", name="I4", prior=Gaussian((50, 50), 25.0)),
        ]
        outside = [Resident(id="out", name="Out",
                            prior=Gaussian((500, 500), 1.0))]
        residents = inside + outside

        for trial in range(1000):
            stream = Stream(trial, "k3.outside")
            sil = collapse_field(field, rect, stream, clock=0)
            assigned: set[str] = set()
            for s in sil:
                ident = refine_identity(s, residents, stream, clock=trial,
                                        assigned_ids=assigned)
                assigned.add(ident.id)
            assert "out" not in assigned

    def test_no_double_assignment(self):
        field = GMM(np.array([3.0]),
                     np.array([[50, 50]]),
                     np.array([[[100, 0], [0, 100]]]))
        rect = Rect(0, 0, 100, 100)
        residents = [
            Resident(id=f"r{i}", name=f"R{i}",
                     prior=Gaussian((50, 50), 100.0))
            for i in range(6)
        ]
        for trial in range(500):
            stream = Stream(trial, "k3.double")
            sil = collapse_field(field, rect, stream, clock=0)
            assigned: set[str] = set()
            for s in sil:
                ident = refine_identity(s, residents, stream, clock=trial,
                                        assigned_ids=assigned)
                assigned.add(ident.id)
            assert len(assigned) == len(sil)


# ---------------------------------------------------------------------------
# 8. K2 integration
# ---------------------------------------------------------------------------

class TestK2Integration:
    def test_evolve_then_collapse(self):
        """Evolve a crowd field under a schedule, then collapse — counts
        and filtration still hold."""
        from kernel.gmm_dynamics.dynamics import DriftField, Schedule, evolve

        field = GMM(np.array([7.0, 5.0]),
                     np.array([[30, 30], [70, 70]]),
                     np.tile(np.eye(2) * 20.0, (2, 1, 1)))

        drift = DriftField(mu=(50, 50), theta=(0.05, 0.05), sigma=(0.3, 0.3))
        sched = Schedule(period=100.0, segments=[(0.0, drift)])

        evolved = evolve(field, 0.0, 50.0, sched)
        rect = Rect(0, 0, 100, 100)
        pc = presence_count(evolved, rect)
        count = int(round(pc))

        stream = Stream(99, "k3.k2int")
        sil = collapse_field(evolved, rect, stream, clock=0)
        assert len(sil) == count
        assert count > 0
