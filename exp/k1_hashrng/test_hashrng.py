"""K1 acceptance tests: reproducibility and independence under hypothesis
tests (lab spec §2, K1 done-when)."""

from __future__ import annotations

import math

import pytest

from kernel.hashrng import Stream, sample, stream_key
from exp.k1_hashrng.statcheck import chi2_uniformity, pearson

SEED = 1


class TestReproducibility:
    def test_same_inputs_same_output(self):
        a = Stream(SEED, "villager:001")
        b = Stream(SEED, "villager:001")
        assert [a.uniform(c) for c in range(1000)] == [b.uniform(c) for c in range(1000)]

    def test_canonical_signature(self):
        assert sample(SEED, "e", 42, "ctx") == Stream(SEED, "e", "ctx").uniform(42)

    def test_random_access_matches_sequential_order(self):
        s = Stream(SEED, "e")
        draws = [s.uniform(c) for c in range(100)]
        for c in (0, 7, 50, 99):
            assert s.uniform(c) == draws[c]

    def test_context_digest_changes_stream(self):
        assert stream_key(SEED, "e", "a") != stream_key(SEED, "e", "b")
        assert Stream(SEED, "e", "a").uniform(0) != Stream(SEED, "e", "b").uniform(0)

    def test_seed_changes_stream(self):
        assert Stream(SEED, "e").uniform(0) != Stream(SEED + 1, "e").uniform(0)

    def test_no_collisions_over_population(self):
        seen = {Stream(SEED, f"e:{i:05d}").u64(0) for i in range(10_000)}
        assert len(seen) == 10_000


class TestUniformity:
    def test_range(self):
        s = Stream(SEED, "e")
        for c in range(10_000):
            assert 0.0 <= s.uniform(c) < 1.0

    def test_chi2_single_stream(self):
        s = Stream(SEED, "villager:001")
        _, _, p = chi2_uniformity((s.uniform(c) for c in range(100_000)), 100)
        assert 0.001 < p < 0.999

    def test_chi2_across_streams(self):
        draws = (
            Stream(SEED, f"e:{i:04d}").uniform(c)
            for i in range(200)
            for c in range(500)
        )
        _, _, p = chi2_uniformity(draws, 100)
        assert 0.001 < p < 0.999


class TestIndependence:
    def test_neighboring_clocks_uncorrelated(self):
        s = Stream(SEED, "e")
        xs = [s.uniform(c) for c in range(50_000)]
        r = pearson(xs[:-1], xs[1:])
        assert abs(r) < 0.02

    def test_neighboring_entities_uncorrelated(self):
        n = 50_000
        xs = [Stream(SEED, f"alice:{i}").uniform(0) for i in range(n)]
        ys = [Stream(SEED, f"alice:{i}").uniform(1) for i in range(n)]
        assert abs(pearson(xs, ys)) < 0.02

    def test_same_clock_across_entities_uncorrelated(self):
        n = 50_000
        xs = [Stream(SEED, f"e:{i}").uniform(7) for i in range(n)]
        ys = [Stream(SEED, f"e:{i + 1}").uniform(7) for i in range(n)]
        assert abs(pearson(xs, ys)) < 0.02


class TestDerivedDistributions:
    def test_bernoulli_rate(self):
        s = Stream(SEED, "e")
        hits = sum(s.bernoulli(0.3, c) for c in range(50_000))
        assert hits == pytest.approx(15_000, rel=0.02)

    def test_randrange_bounds_and_uniformity(self):
        s = Stream(SEED, "e")
        draws = [s.randrange(6, c) for c in range(60_000)]
        assert all(0 <= d < 6 for d in draws)
        _, _, p = chi2_uniformity([d / 6 for d in draws], 6)
        assert 0.001 < p < 0.999

    def test_normal_moments(self):
        s = Stream(SEED, "e")
        n = 100_000
        draws = [s.normal(c) for c in range(n)]
        mean = sum(draws) / n
        var = sum((d - mean) ** 2 for d in draws) / n
        assert abs(mean) < 0.02
        assert var == pytest.approx(1.0, rel=0.02)

    def test_digest_stable(self):
        s = Stream(SEED, "e")
        assert s.digest(0, 365) == Stream(SEED, "e").digest(0, 365)
        assert s.digest(0, 365) != s.digest(1, 365)


class TestValidation:
    def test_bad_inputs_rejected(self):
        with pytest.raises(ValueError):
            stream_key(-1, "e")
        with pytest.raises(ValueError):
            stream_key(1 << 64, "e")
        s = Stream(SEED, "e")
        with pytest.raises(ValueError):
            s.u64(1 << 63)
        with pytest.raises(ValueError):
            s.u64(0, -1)
        with pytest.raises(ValueError):
            s.randrange(0, 0)

    def test_nan_safe_normal(self):
        # Box–Muller guard: 1.0 - uniform is in (0, 1], log never sees 0.
        s = Stream(SEED, "e")
        for c in range(10_000):
            assert math.isfinite(s.normal(c))
