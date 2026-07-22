"""K11 — raster helpers, deterministic value noise, and a stdlib PNG writer.

No dependencies beyond numpy + kernel.hashrng. The PNG writer emits
8-bit grayscale and palette PNGs (zlib-compressed, standard chunks).
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

from kernel.hashrng import Stream

# ---- deterministic value noise -------------------------------------------------


def value_noise(stream: Stream, shape: tuple[int, int], cell_size: int) -> np.ndarray:
    """Bilinearly-interpolated value noise over the grid.

    Lattice values are K1 draws keyed by (lattice_x, lattice_y), so the
    field is deterministic and resolution-independent at lattice points.
    `cell_size` is the lattice spacing in grid cells.
    """
    h, w = shape
    ly, lx = np.mgrid[0:h, 0:w].astype(float)
    gx, gy = lx / cell_size, ly / cell_size
    x0, y0 = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = gx - x0, gy - y0
    # smoothstep
    fx = fx * fx * (3 - 2 * fx)
    fy = fy * fy * (3 - 2 * fy)

    def lat(ix, iy):
        # vectorized lattice draws: Stream.u64 per point would be slow, so
        # draw per unique lattice coordinate via a hash of the stream key
        # and the lattice coords — still K1, just batched.
        return _lattice_values(stream, ix, iy)

    v00 = lat(x0, y0)
    v10 = lat(x0 + 1, y0)
    v01 = lat(x0, y0 + 1)
    v11 = lat(x0 + 1, y0 + 1)
    top = v00 + (v10 - v00) * fx
    bot = v01 + (v11 - v01) * fx
    return top + (bot - top) * fy


def _lattice_values(stream: Stream, ix: np.ndarray, iy: np.ndarray) -> np.ndarray:
    """K1 bulk draws at (clock=lattice_x, index=lattice_y) -> [0,1) floats.

    Uses the vectorized batch mixer (Stream.u64_batch): a scalar BLAKE2b
    per lattice point cost ~50 s of a 70 s world build (9e6 draws)."""
    ix = np.asarray(ix, dtype=np.int64)
    iy = np.asarray(iy, dtype=np.int64)
    return (stream.u64_batch(ix, iy) >> np.uint64(11)) * (1.0 / (1 << 53))


def fbm(stream: Stream, shape: tuple[int, int], base_cell: int, octaves: int = 4,
        persistence: float = 0.5) -> np.ndarray:
    """Fractal value noise: sum of octaves, normalized to ~[0, 1]."""
    total = np.zeros(shape)
    amp_sum = 0.0
    amp = 1.0
    cell = base_cell
    for o in range(octaves):
        total += amp * value_noise(stream, shape, max(1, cell))
        amp_sum += amp
        amp *= persistence
        cell = max(1, cell // 2)
    return total / amp_sum


# ---- PNG writer (stdlib) -------------------------------------------------------


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png_gray(path: str, img: np.ndarray) -> None:
    """8-bit grayscale PNG from a uint8 array."""
    img = np.ascontiguousarray(img, dtype=np.uint8)
    h, w = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw, 9))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def write_png_palette(path: str, idx: np.ndarray, palette: list[tuple[int, int, int]]) -> None:
    """8-bit palette PNG from an index array + RGB palette (<= 256 entries)."""
    idx = np.ascontiguousarray(idx, dtype=np.uint8)
    h, w = idx.shape
    plte = b"".join(bytes((r, g, b)) for r, g, b in palette)
    raw = b"".join(b"\x00" + idx[y].tobytes() for y in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
           + _chunk(b"PLTE", plte)
           + _chunk(b"IDAT", zlib.compress(raw, 9))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def write_png_rgb(path: str, img: np.ndarray) -> None:
    """8-bit RGB PNG from a (h, w, 3) uint8 array."""
    img = np.ascontiguousarray(img, dtype=np.uint8)
    h, w, _ = img.shape
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw, 9))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def normalize_u8(field: np.ndarray, lo: float | None = None, hi: float | None = None) -> np.ndarray:
    """Scale a float field to uint8 [0, 255]."""
    lo = float(field.min()) if lo is None else lo
    hi = float(field.max()) if hi is None else hi
    if hi - lo < 1e-12:
        return np.zeros(field.shape, dtype=np.uint8)
    return np.clip((field - lo) / (hi - lo) * 255.0, 0, 255).astype(np.uint8)


def upsample_bicubic(a: np.ndarray, factor: int = 4) -> np.ndarray:
    """Catmull-Rom bicubic upsampling by an integer factor.

    Mechanical step of the resolution ladder: smooth interpolation of a
    continuous field, inventing no detail (edge indices clamp)."""
    def cr(t: np.ndarray) -> tuple[np.ndarray, ...]:
        return (-0.5 * t**3 + t**2 - 0.5 * t,
                1.5 * t**3 - 2.5 * t**2 + 1.0,
                -1.5 * t**3 + 2.0 * t**2 + 0.5 * t,
                0.5 * t**3 - 0.5 * t**2)

    out = a.astype(np.float64)
    for axis in (1, 0):
        n = out.shape[axis]
        m = n * factor
        pos = (np.arange(m) + 0.5) / factor - 0.5
        i = np.floor(pos).astype(int)
        t = (pos - i).astype(np.float64)
        ws = cr(t)
        acc = 0.0
        for k, w_k in zip((-1, 0, 1, 2), ws):
            idx = np.clip(i + k, 0, n - 1)
            acc = acc + w_k.reshape([-1 if ax == axis else 1 for ax in range(out.ndim)]) * np.take(out, idx, axis=axis)
        out = acc
    return out


# ---- distance / nearest-value transforms --------------------------------------


def distance_to_mask(mask: np.ndarray) -> np.ndarray:
    """Approximate distance (in cells) to the nearest True cell — two-pass
    chamfer, cheap and good enough for shelf/decay profiles."""
    H, W = mask.shape
    INF = float(H + W)
    d = np.where(mask, 0.0, INF)
    for y in range(H):
        for x in range(W):
            if d[y, x] > 0:
                d[y, x] = 1 + min(
                    d[y - 1, x] if y > 0 else INF,
                    d[y, x - 1] if x > 0 else INF,
                )
    for y in range(H - 1, -1, -1):
        for x in range(W - 1, -1, -1):
            if d[y, x] > 0:
                d[y, x] = min(d[y, x], 1 + min(
                    d[y + 1, x] if y < H - 1 else INF,
                    d[y, x + 1] if x < W - 1 else INF,
                ))
    return d


def nearest_values(mask: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For every cell: (distance to nearest True cell, that cell's value).

    Multi-source Dijkstra over 4-neighbors — exact (unlike chamfer), and
    fast enough at demo sizes. Used to carry boundary properties (e.g.
    fault convergence) into the cells around the boundary.
    """
    import heapq

    H, W = mask.shape
    dist = np.full((H, W), np.inf)
    val = np.zeros((H, W), dtype=float)
    heap: list[tuple[float, int, int]] = []
    for y in range(H):
        for x in range(W):
            if mask[y, x]:
                dist[y, x] = 0.0
                val[y, x] = float(values[y, x])
                heapq.heappush(heap, (0.0, y, x))
    while heap:
        d, y, x = heapq.heappop(heap)
        if d > dist[y, x]:
            continue
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx_ = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx_ < W and d + 1 < dist[ny, nx_]:
                dist[ny, nx_] = d + 1
                val[ny, nx_] = val[y, x]
                heapq.heappush(heap, (d + 1, ny, nx_))
    return dist, val
