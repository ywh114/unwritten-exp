"""K11 — interactive map viewer/searcher backend (stdlib only).

    uv run python -m exp.k11_worldgen.mapserver [--dir exp/k11_worldgen/out] [--port 8111]

Serves the viewer page (map.html) and a JSON/PNG API over saved worlds:

  GET /                              -> viewer page
  GET /api/worlds                    -> [{seed, name, pngs}]
  GET /api/world/<seed>/manifest     -> manifest stats + shape + field list
  GET /api/world/<seed>/img/<name>   -> rendered PNG from the seed dir
  GET /api/world/<seed>/pixel?x=&y=  -> all delivered-res fields at cell
  GET /api/world/<seed>/area?x0=&y0=&x1=&y1= -> aggregate stats + histograms
  GET /api/world/<seed>/search?q=EXPR   -> {count, bbox, stats}
  GET /api/world/<seed>/mask.png?q=EXPR -> RGBA mask overlay (red hits)

Search expressions: comparisons `field OP value` (OP in > >= < <= == !=)
joined by `&` `|` `!` and parens. Fields: elev_m, T, P, cover, salinity,
depth_m, hand_m, width_m, biome ("name" or id), aquatic ("name" or id),
biome_sim, and bare mask names river|lake|ocean|sea (== 1 implied).
"""

from __future__ import annotations

import argparse
import io
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np

from exp.k11_worldgen.biomes import BIOME_ID, BIOMES
from exp.k11_worldgen.raster import write_png_rgb
from exp.k11_worldgen.units import alt_m, hand_m, precip_mm, temp_c

HERE = Path(__file__).parent
OUT = HERE / "out"

_BIOME_BY_NAME = dict(BIOME_ID)
_AQUA_NAMES: dict[int, str] = {}   # filled from manifest if present

_OPS = {">": np.greater, ">=": np.greater_equal, "<": np.less,
        "<=": np.less_equal, "==": np.equal, "!=": np.not_equal}


class World:
    """One loaded seed dir: manifest + npz + derived query fields."""

    def __init__(self, seed_dir: Path) -> None:
        self.dir = seed_dir
        self.seed = seed_dir.name
        self.manifest = json.loads((seed_dir / "world.json").read_text())
        z = np.load(seed_dir / "world.npz")
        self.z = z
        self.d = {k[2:]: z[k] for k in z.files if k.startswith("d_")}
        self.sea_level = float(self.manifest["sea_level"])
        self.shape = self.d["elev"].shape
        self.pngs = sorted(p.stem for p in seed_dir.glob("*.png")
                           if p.stem != "load")
        # biome similarity from the persisted d2 field (anchor res,
        # nearest-upscaled to delivered res): s = (d2_2 - d2_1) / d2_2,
        # 1 = confidently this class, 0 = equidistant ecotone.
        if "w_biome_d2_1" in z.files:
            d1, d2 = z["w_biome_d2_1"], z["w_biome_d2_2"]
            sim = (d2 - d1) / np.maximum(d2, 1e-9)
            factor = self.shape[0] // sim.shape[0]
            self.sim = np.repeat(np.repeat(sim, factor, 0), factor, 1)
        else:
            self.sim = None

    def fields(self) -> dict[str, np.ndarray]:
        """Named query/display fields at delivered res."""
        d = self.d
        f: dict[str, np.ndarray] = {
            "elev_m": alt_m(d["elev"], self.sea_level),
            "T_c": temp_c(d["T"]), "P_mm": precip_mm(d["P"]),
            "cover": d["cover"], "salinity": d["salinity"],
            "depth_m": d["depth"], "hand_m": hand_m(d["hand"],
                                                    self.sea_level),
            "width_m": d["width"], "biome": d["biome_map"],
            "aquatic": d["aquatic"],
            "river": d["river_mask"], "lake": d["lake_mask"],
            "ocean": d["ocean_mask"], "sea": d["sea_mask"],
        }
        if self.sim is not None:
            f["biome_sim"] = self.sim
        return f


_WORLDS: dict[str, World] = {}


def _world(seed: str) -> World | None:
    if seed not in _WORLDS:
        d = OUT / seed
        if (d / "world.npz").exists():
            _WORLDS[seed] = World(d)
        else:
            return None
    return _WORLDS[seed]


# ──  the constraint mini-language  ────────────────────────────────────────

_TOKEN = re.compile(r"\s*(>=|<=|==|!=|[><&|!()]|\"[^\"]*\"|'[^']*'|"
                    r"[A-Za-z_][A-Za-z0-9_]*|-?\d+\.?\d*)")


def _lex(expr: str) -> list[str]:
    out, pos = [], 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            raise ValueError(f"cannot parse at {expr[pos:]!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


class _Parser:
    def __init__(self, tokens: list[str], fields: dict[str, np.ndarray]):
        self.toks, self.i, self.f = tokens, 0, fields

    def peek(self) -> str | None:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def eat(self, tok: str) -> None:
        if self.peek() != tok:
            raise ValueError(f"expected {tok!r}, got {self.peek()!r}")
        self.i += 1

    def parse(self) -> np.ndarray:
        m = self.or_()
        if self.peek() is not None:
            raise ValueError(f"trailing token {self.peek()!r}")
        return m

    def or_(self) -> np.ndarray:
        m = self.and_()
        while self.peek() == "|":
            self.eat("|")
            m = m | self.and_()
        return m

    def and_(self) -> np.ndarray:
        m = self.unary()
        while self.peek() == "&":
            self.eat("&")
            m = m & self.unary()
        return m

    def unary(self) -> np.ndarray:
        if self.peek() == "!":
            self.eat("!")
            return ~self.unary()
        if self.peek() == "(":
            self.eat("(")
            m = self.or_()
            self.eat(")")
            return m
        return self.comparison()

    def comparison(self) -> np.ndarray:
        name = self.peek()
        if name not in self.f:
            raise ValueError(f"unknown field {name!r}")
        self.i += 1
        arr = self.f[name]
        op = self.peek()
        if op not in _OPS:
            raise ValueError(f"expected operator, got {op!r}")
        self.i += 1
        raw = self.peek()
        self.i += 1
        if raw is None:
            raise ValueError("missing value")
        if raw.startswith(('"', "'")):           # named enum value
            word = raw.strip("\"'")
            if name == "biome":
                if word not in _BIOME_BY_NAME:
                    raise ValueError(f"unknown biome {word!r}")
                val = _BIOME_BY_NAME[word]
            elif name == "aquatic":
                if word not in _AQUA_NAMES:
                    raise ValueError(f"unknown aquatic class {word!r}")
                val = _AQUA_NAMES[word]
            else:
                raise ValueError(f"string value only for biome/aquatic")
        else:
            val = float(raw)
        return _OPS[op](arr, val)


def _search(w: World, expr: str) -> np.ndarray:
    return _Parser(_lex(expr), w.fields()).parse()


# ──  stats helpers  ───────────────────────────────────────────────────────

_BIOME_NAMES = {i: n for n, i in BIOME_ID.items()}


def _area_stats(w: World, mask: np.ndarray) -> dict:
    n = int(mask.sum())
    out: dict = {"cells": n}
    if n == 0:
        return out
    for name, arr in w.fields().items():
        if name in ("biome", "aquatic", "river", "lake", "ocean", "sea"):
            continue
        v = arr[mask]
        out[name] = {"mean": float(v.mean()), "min": float(v.min()),
                     "max": float(v.max())}
    hist: dict[str, float] = {}
    for bid in np.unique(w.d["biome_map"][mask]):
        hist[_BIOME_NAMES.get(int(bid), str(bid))] = float(
            (w.d["biome_map"][mask] == bid).mean())
    out["biome_hist"] = hist
    return out


def _pixel(w: World, x: int, y: int) -> dict:
    out: dict = {"x": x, "y": y}
    for name, arr in w.fields().items():
        v = arr[y, x]
        out[name] = float(v) if arr.dtype.kind == "f" else int(v)
    out["biome_name"] = _BIOME_NAMES.get(int(w.d["biome_map"][y, x]),
                                         "?")
    return out


def _mask_png(mask: np.ndarray) -> bytes:
    rgba = np.zeros(mask.shape + (4,), dtype=np.uint8)
    rgba[mask] = (255, 40, 40, 160)
    tmp = io.BytesIO()
    # raster.write_png_rgb takes a path; write to a temp file instead
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        write_png_rgb(tf.name, rgba)
        tmp.write(Path(tf.name).read_bytes())
    return tmp.getvalue()


# ──  HTTP  ────────────────────────────────────────────────────────────────


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj) -> None:
        self._send(json.dumps(obj).encode())

    def _err(self, code: int, msg: str) -> None:
        self.send_response(code)
        self.send_header("Content-Length", str(len(msg)))
        self.end_headers()
        self.wfile.write(msg.encode())

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        parts = [p for p in u.path.split("/") if p]
        try:
            if not parts:
                self._send((HERE / "viewer" / "map.html").read_bytes(),
                           "text/html")
                return
            if parts[:2] == ["api", "worlds"]:
                worlds = [{"seed": d.name,
                           "pngs": sorted(p.stem for p in d.glob("*.png")
                                          if p.stem != "load")}
                          for d in sorted(OUT.glob("seed_*"))
                          if (d / "world.npz").exists()]
                self._json(worlds)
                return
            if len(parts) >= 3 and parts[:2] == ["api", "world"]:
                w = _world(parts[2])
                if w is None:
                    self._err(404, "no such world")
                    return
                self._world_api(w, parts[3:], q)
                return
            self._err(404, "not found")
        except ValueError as e:
            self._err(400, str(e))
        except Exception as e:  # surface, don't hang the dev loop
            self._err(500, f"{type(e).__name__}: {e}")

    def _world_api(self, w: World, rest: list[str], q: dict) -> None:
        if rest == ["manifest"]:
            self._json({"seed": w.seed, "shape": w.shape,
                        "sea_level": w.sea_level,
                        "stats": w.manifest["stats"],
                        "pngs": w.pngs,
                        "fields": sorted(w.fields()),
                        "has_sim": w.sim is not None})
            return
        if rest[0] == "img" and len(rest) == 2:
            p = w.dir / f"{rest[1]}.png"
            if p.exists():
                self._send(p.read_bytes(), "image/png")
                return
            self._err(404, "no such image")
            return
        if rest == ["pixel"]:
            x, y = int(q["x"][0]), int(q["y"][0])
            if not (0 <= x < w.shape[1] and 0 <= y < w.shape[0]):
                self._err(400, "out of bounds")
                return
            self._json(_pixel(w, x, y))
            return
        if rest == ["area"]:
            x0, y0 = int(q["x0"][0]), int(q["y0"][0])
            x1, y1 = int(q["x1"][0]), int(q["y1"][0])
            mask = np.zeros(w.shape, bool)
            mask[min(y0, y1):max(y0, y1) + 1,
                 min(x0, x1):max(x0, x1) + 1] = True
            self._json(_area_stats(w, mask))
            return
        if rest == ["search"]:
            expr = q["q"][0]
            mask = _search(w, expr)
            ys, xs = np.nonzero(mask)
            out = _area_stats(w, mask)
            if len(ys):
                out["bbox"] = [int(xs.min()), int(ys.min()),
                               int(xs.max()), int(ys.max())]
            self._json(out)
            return
        if rest == ["mask.png"]:
            self._send(_mask_png(_search(w, q["q"][0])), "image/png")
            return
        self._err(404, "not found")


def main() -> None:
    global OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", type=Path, default=OUT)
    ap.add_argument("--port", type=int, default=8111)
    args = ap.parse_args()
    OUT = args.dir
    print(f"serving {OUT} on http://localhost:{args.port}")
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
