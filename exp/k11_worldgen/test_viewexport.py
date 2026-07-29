"""K11 viewexport tests — the .k11view bundle round-trips."""

from __future__ import annotations

import json
import pathlib
import struct

import numpy as np
import pytest

from exp.k11_worldgen.units import alt_m

SEED1 = pathlib.Path(__file__).parent / "out" / "seed_00000001"
BUNDLE = SEED1 / "seed_00000001.k11view"


def _read_bundle(path):
    with open(path, "rb") as f:
        assert f.read(4) == b"K11V"
        hlen = struct.unpack("<I", f.read(4))[0]
        header = json.loads(f.read(hlen))
        shape = header["shape"]
        data = {}
        for name in header["order"]:
            meta = header["fields"][name]
            dt = np.dtype("<u2" if meta["dtype"] == "<u2" else "u1")
            arr = np.frombuffer(
                f.read(shape[0] * shape[1] * dt.itemsize),
                dtype=dt).reshape(shape)
            if "scale" in meta:
                arr = arr * meta["scale"] + meta["offset"]
            data[name] = arr
    return header, data


@pytest.mark.skipif(not BUNDLE.exists(), reason="bundle not exported")
def test_bundle_round_trip():
    header, data = _read_bundle(BUNDLE)
    assert header["format"] == "k11view/1"
    assert header["shape"] == [1024, 1024]
    z = np.load(SEED1 / "world.npz")
    ref = alt_m(z["d_elev"], header["sea_level"])
    assert np.abs(data["elev_m"] - ref).max() < 1.0      # <1 m error
    assert (data["biome"] == z["d_biome_map"]).all()      # enums exact
    assert 0.0 <= data["biome_sim"].min()
    assert data["biome_sim"].max() <= 1.0
    # masks bitfield
    assert ((data["masks"] & 1) > 0).sum() == int(z["d_river_mask"].sum())
    # backdrop + palette for the self-contained viewer
    assert header["backdrop_png_b64"]
    assert "5" in header["biome_colors"]                  # taiga
