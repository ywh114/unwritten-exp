"""K4 acceptance tests: evaluation exact to float tolerance under fuzzed
event sequences; function library fits on one page (lab spec §2, K4)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from kernel.counters.counters import Counter
from kernel.counters.laws import ExpDecay, Logistic, Step
from kernel.hashrng import Stream


class TestLaws:
    def test_logistic_endpoints(self):
        law = Logistic(rate=0.02, capacity=1000.0)
        assert law.value_at(100.0, 0.0) == 100.0
        assert law.value_at(100.0, 1e6) == pytest.approx(1000.0)
        assert law.value_at(0.0, 100.0) == 0.0  # 0 is a fixed point
        assert law.value_at(1000.0, 100.0) == 1000.0  # so is K

    def test_logistic_known_value(self):
        # c = K/(1 + A e^{-r t}), A = (K-c0)/c0
        law = Logistic(rate=0.5, capacity=10.0)
        assert law.value_at(2.0, 2.0) == pytest.approx(10.0 / (1.0 + 4.0 * math.exp(-1.0)))

    def test_logistic_decline_from_above(self):
        law = Logistic(rate=0.1, capacity=50.0)
        vals = [law.value_at(200.0, t) for t in range(0, 100, 10)]
        assert all(a > b for a, b in zip(vals, vals[1:]))  # monotone decline
        assert vals[-1] == pytest.approx(50.0, abs=1.0)

    def test_exp_decay_half_life(self):
        law = ExpDecay(rate=0.5, floor=10.0)
        assert law.value_at(110.0, math.log(2) / 0.5) == pytest.approx(60.0)
        assert law.value_at(110.0, 1e6) == pytest.approx(10.0)

    def test_step_holds(self):
        assert Step().value_at(42.0, 1e9) == 42.0

    def test_regime_multipliers(self):
        law = Logistic(rate=0.02, capacity=100.0)
        # doubled rate over dt equals plain rate over 2*dt
        assert law.value_at(10.0, 5.0, rate_mult=2.0) == pytest.approx(law.value_at(10.0, 10.0))
        # capacity multiplier rescales the asymptote
        assert law.value_at(10.0, 1e6, cap_mult=0.5) == pytest.approx(50.0)

    def test_library_fits_on_one_page(self):
        laws_py = Path(__file__).parents[2] / "kernel" / "counters" / "laws.py"
        n_lines = len(laws_py.read_text().splitlines())
        assert n_lines <= 72, f"function library over-parameterized: {n_lines} lines"


class TestCounterChain:
    def counter(self) -> Counter:
        c = Counter(regimes={"harvest": {"rate": 2.0}})
        c.set_anchor(0, 100.0, Logistic(0.02, 1000.0), note="start")
        return c

    def test_value_at_anchor_is_anchor_value(self):
        c = self.counter()
        assert c.value_at(0) == 100.0

    def test_before_first_anchor_raises(self):
        with pytest.raises(ValueError):
            self.counter().value_at(-1)

    def test_non_increasing_anchor_raises(self):
        c = self.counter()
        with pytest.raises(ValueError):
            c.set_anchor(0, 1.0, Step())

    def test_event_step(self):
        c = self.counter()
        pre = c.value_at(10 - 1e-9)
        post = c.insert_event(10, scale=0.5, note="halved")
        assert post == pytest.approx(pre * 0.5)
        assert c.value_at(10) == post
        assert c.anchor_at(10).note == "halved"

    def test_event_delta_and_law_override(self):
        c = self.counter()
        v = c.insert_event(5, delta=25.0, law=Step())
        assert v == pytest.approx(c.value_at(5))
        assert c.value_at(1e6) == v  # Step holds forever

    def test_regime_shift(self):
        c = self.counter()
        c.regime_shift(10, "harvest", note="harvest")
        plain = self.counter()
        # with rate x2, the shifted counter at t matches the plain one at 10 + 2*(t-10)
        t = 40.0
        assert c.value_at(t) == pytest.approx(plain.value_at(10 + 2 * (t - 10)))

    def test_reanchor_consistency(self):
        c = self.counter()
        t0, t1, t2 = 3.7, 11.1, 50.0
        direct = c.value_at(t2)
        a = c.anchor_at(t0)
        c.set_anchor(t0, c.value_at(t0), a.law, a.regime)
        a = c.anchor_at(t1)
        c.set_anchor(t1, c.value_at(t1), a.law, a.regime)
        assert c.value_at(t2) == pytest.approx(direct, rel=1e-12)


class TestFuzzedEventSequences:
    def test_exact_under_fuzz(self):
        """Random event chain vs. densely re-anchored copy: float-exact."""
        stream = Stream(1, "k4-fuzz")
        laws = [Logistic(0.02, 1000.0), ExpDecay(0.01, 20.0), Step()]
        regimes = {"fast": {"rate": 2.0}, "slow": {"rate": 0.3}, "cramped": {"capacity": 0.5}}

        c = Counter(regimes=regimes)
        c.set_anchor(0, 100.0, laws[0], note="genesis")
        t = 0.0
        for event in range(40):
            t += 1.0 + 10.0 * stream.uniform(event, 0)
            kind = event % 3
            if kind == 0:
                c.insert_event(t, scale=0.3 + 1.4 * stream.uniform(event, 1), note="shock")
            elif kind == 1:
                c.insert_event(t, delta=50.0 * stream.uniform(event, 2),
                               law=laws[stream.randrange(3, event, 3)], note="revision")
            else:
                regime = list(regimes)[stream.randrange(3, event, 4)]
                c.regime_shift(t, regime, note="shift")

        # Dense copy: same anchors plus a continuity re-anchor at every
        # probe point, merged in time order.
        dense = Counter(regimes=regimes)
        probes = sorted(0.5 + 200.0 * stream.uniform(10_000 + i, 0) for i in range(100))
        events = [(a.t, a) for a in c.anchors] + [(p, None) for p in probes]
        for t_ev, anchor in sorted(events, key=lambda e: e[0]):
            if t_ev <= dense._times[-1] if dense._times else False:
                continue  # probe landed on an existing anchor time
            if anchor is not None:
                dense.set_anchor(t_ev, anchor.value, anchor.law, anchor.regime, anchor.note)
            else:
                a = c.anchor_at(t_ev)
                dense.set_anchor(t_ev, c.value_at(t_ev), a.law, a.regime)

        worst = 0.0
        for i in range(500):
            tq = 500.0 * stream.uniform(20_000 + i, 0)
            ref, got = c.value_at(tq), dense.value_at(tq)
            worst = max(worst, abs(got - ref) / max(1.0, abs(ref)))
        assert worst < 1e-9
