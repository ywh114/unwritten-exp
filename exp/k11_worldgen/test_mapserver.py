"""K11 mapserver tests — the constraint parser, pixel/area/search stats.

Runs against the real seed-1 dump when present (skipped otherwise); the
parser tests use synthetic fields.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from exp.k11_worldgen.mapserver import (
    World, _area_stats, _lex, _Parser, _search)

SEED1 = pathlib.Path(__file__).parent / "out" / "seed_00000001"


def parse(fields, expr):
    return _Parser(_lex(expr), fields).parse()


def test_parser_precedence_and_parens():
    f = {"a": np.arange(4).reshape(2, 2), "b": np.ones((2, 2), int)}
    # a: [[0,1],[2,3]]
    assert parse(f, "a > 1 & b == 1").tolist() == [[False, False],
                                                   [True, True]]
    assert parse(f, "a > 1 | a == 0 & b == 1").tolist() == [[True, False],
                                                            [True, True]]
    assert parse(f, "(a > 1 | a == 0) & b == 1").tolist() == [[True, False],
                                                              [True, True]]
    assert parse(f, "! (a > 1)").tolist() == [[True, True], [False, False]]


def test_parser_errors():
    with pytest.raises(ValueError):
        parse({}, "nope > 1")
    with pytest.raises(ValueError):
        parse({"a": np.zeros((1, 1))}, "a ~ 1")
    with pytest.raises(ValueError):
        parse({"a": np.zeros((1, 1))}, "a > ")


@pytest.mark.skipif(not (SEED1 / "world.npz").exists(),
                    reason="seed 1 dump not present")
class TestSeed1:
    @pytest.fixture(scope="class")
    def world(self):
        return World(SEED1)

    def test_fields_present_and_metric(self, world):
        f = world.fields()
        for name in ("elev_m", "T_c", "P_mm", "biome", "biome_sim",
                     "salinity", "cover"):
            assert name in f
        assert f["T_c"].max() > 10.0        # metric, not normalized
        assert f["P_mm"].max() > 50.0

    def test_sim_in_unit_interval(self, world):
        s = world.sim
        assert s is not None
        assert 0.0 <= float(s.min()) and float(s.max()) <= 1.0

    def test_biome_name_search(self, world):
        mask = _search(world, 'biome == "boreal taiga"')
        assert mask.sum() > 100
        # and it really is taiga
        from exp.k11_worldgen.biomes import BIOME_ID
        assert (world.d["biome_map"][mask]
                == BIOME_ID["boreal taiga"]).all()

    def test_combined_search(self, world):
        mask = _search(world, 'elev_m > 2000 & biome == "boreal taiga"')
        assert mask.sum() > 0
        assert (world.fields()["elev_m"][mask] > 2000).all()

    def test_mask_search(self, world):
        mask = _search(world, "river == 1 & biome_sim < 0.3")
        assert (world.d["river_mask"][mask] == 1).all()

    def test_area_stats(self, world):
        mask = np.zeros(world.shape, bool)
        mask[100:117, 100:117] = True
        st = _area_stats(world, mask)
        assert st["cells"] == 17 * 17
        assert "elev_m" in st and "biome_hist" in st
        assert abs(sum(st["biome_hist"].values()) - 1.0) < 1e-6
