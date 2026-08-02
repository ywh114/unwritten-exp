"""K15 — persistence + delivery (ticket 0013).

The engine rounds demo writes a per-run dump under
``exp/k15_simdiff/out/seed_NNNNNNNN/`` (mirrors the k11/k14
persist/deliver convention — JSON manifest + binary arrays + the
viewer datapack):

  state.json      the run manifest + per-instance digest (seed, rounds,
                  schema version, world shape, per-instance sid/box/
                  cells/mass/rain, retired, reflog length)
  density.json    the per-lineage density fields at end-of-run: per
                  instance, the WINDOWED Dressed form (bbox + N + mask
                  — the natural form, NOT full rasters)
  rounds/rNNNN.json  optional per-round density snapshots (--per-round)
  tree.json       the amended tree — the SAME schema k13 delivers,
                  post-rounds (the authority's Tree after the run)
  reflog.json     the authority reflog — the full decision record
  delivery.npz    the high-res (1024²) display-only pass: the final
                  round's instance densities upscaled with edge-aware
                  interpolation + a settlement diffusion at delivery
                  res (never a per-lineage stack — streamed into one
                  running plane), plus the anchor-res richness fields
  delivery.k11pack  the viewer overlay (.k11pack, the k14 datapack
                  format): species richness + the lineages-present
                  tooltip layer
  manifest.json   provenance (inputs chain; write_manifest)

Determinism (hard rule): the dump is a pure function of the engine
state — no uuid/random/time in any payload, sorted instance/sid
iteration everywhere, fixed dtypes (N f8, mask u1), sorted JSON keys;
same (seed, rounds) => byte-identical files. The provenance manifest's
commit stamp is the only checkout-dependent line (provenance, not
payload; identical within one checkout).

The high-res pass is DISPLAY-ONLY (owner decision 2026-08-01): it never
feeds back into a sim round. Upscale = bilinear field + interpolated-
mask re-threshold (the k14 display-map de-blocking idiom, NOT raw 4x
block stamping); settlement = a 3x3 box average restricted to each
instance's own high-res mask (edge-aware — density never leaks into
empty cells).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from exp.artifacts import current_commit, write_manifest
from exp.k14_worldprod.datapack import RAMP_TERRESTRIAL, _q8, write_pack

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

VERSION = 1              # state.json / density.json schema version
HI_FACTOR = 4            # 256² anchor -> 1024² delivery
SETTLE_PASSES = 2        # delivery-res settlement diffusion passes
TOOLTIP_LINEAGE_MAX = 12  # lineages shown in the tooltip line (pack)

# named ramps as stop lists (t, [r,g,b]); the viewer interpolates
RAMP_DENSITY = [[0.0, [8, 12, 26]], [0.5, [52, 88, 148]],
                [1.0, [242, 216, 120]]]
RAMP_RICHNESS = [[0.0, [14, 22, 38]], [0.5, [64, 128, 84]],
                 [1.0, [198, 240, 136]]]


def out_dir(seed: int) -> Path:
    """The canonical per-seed dump dir (k11/k14 convention)."""
    return OUT / f"seed_{seed:08d}"


def _instance_records(eng) -> list[dict]:
    """The deterministic per-instance density records: sorted instance
    ids, windowed Dressed form (box + N f8 + mask u1 — the bbox
    optimization's natural form). Float payloads are full-precision
    (json repr of identical f64 is byte-identical across runs)."""
    recs = []
    for iid in sorted(eng.instances):
        d = eng.instances[iid]
        N = d.N.astype(np.float64)
        recs.append({
            "iid": iid,
            "sid": d.x.species_id,
            "box": [int(v) for v in d.box],
            "N": [float(v) for v in N.ravel()],
            "mask": [int(v) for v in (N > 0.0).ravel()],
        })
    return recs


def round_snapshot(eng, t: int, out: Path | None = None) -> Path:
    """The optional per-round density snapshot (--per-round): the same
    instance records as the end-of-run dump, at round *t*'s entry state
    (called by the demo right after each round)."""
    out = out or out_dir(eng.seed)
    (out / "rounds").mkdir(parents=True, exist_ok=True)
    p = out / "rounds" / f"r{t:04d}.json"
    p.write_text(json.dumps({
        "round": t,
        "meta": {"schema": "k15.density/1", "world": [eng.ctx.H, eng.ctx.W],
                 "dtypes": {"N": "f8", "mask": "u1"}},
        "instances": _instance_records(eng),
    }, sort_keys=True) + "\n")
    return p


# ── the high-res display-only pass (Phase 3) ───────────────────────────


def _bilinear_up(a: np.ndarray, factor: int) -> np.ndarray:
    """Deterministic bilinear upscale of a 2-D float field (delivery
    ladder mechanical step: continuous field, edges clamp — the same
    role upsample_bicubic plays in k11, bounded so a non-negative
    density never overshoots negative)."""
    a = a.astype(np.float64)
    H, W = a.shape

    def axis(n: int, m: int):
        pos = (np.arange(m) + 0.5) / factor - 0.5
        i0 = np.clip(np.floor(pos).astype(int), 0, n - 1)
        i1 = np.clip(i0 + 1, 0, n - 1)
        t = np.clip(pos - i0, 0.0, 1.0)
        return i0, i1, t

    y0, y1, ty = axis(H, H * factor)
    x0, x1, tx = axis(W, W * factor)
    return ((1.0 - ty)[:, None] * (1.0 - tx)[None, :] * a[np.ix_(y0, x0)]
            + (1.0 - ty)[:, None] * tx[None, :] * a[np.ix_(y0, x1)]
            + ty[:, None] * (1.0 - tx)[None, :] * a[np.ix_(y1, x0)]
            + ty[:, None] * tx[None, :] * a[np.ix_(y1, x1)])


def _settle_hi(a: np.ndarray, mask: np.ndarray,
               passes: int = SETTLE_PASSES) -> np.ndarray:
    """Delivery-res settlement diffusion: a 3x3 box average restricted
    to the instance's own high-res mask (edge-aware — density never
    leaks into empty cells), `passes` times. Deterministic."""
    a = a.copy()
    H, W = a.shape
    for _ in range(passes):
        p = np.pad(a, 1)
        acc = np.zeros_like(a)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                acc += p[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
        a = acc / 9.0
        a[~mask] = 0.0
    return a


def _hires_density(eng, factor: int = HI_FACTOR) -> np.ndarray:
    """The final round's instance density fields at delivery res: per
    instance, bilinear upscale + interpolated-mask re-threshold (the
    k14 display-map de-blocking idiom), then settlement diffusion, all
    summed into ONE running (H*factor, W*factor) plane — the hard rule
    against a per-lineage stack."""
    H, W = eng.ctx.H, eng.ctx.W
    acc = np.zeros((H * factor, W * factor), dtype=np.float64)
    for iid in sorted(eng.instances):
        d = eng.instances[iid]
        m = d.N > 0.0
        if not m.any():
            continue
        y0, y1, x0, x1 = d.box
        n_hi = _bilinear_up(d.N.astype(np.float64), factor)
        mask_hi = _bilinear_up(m.astype(np.float64), factor) > 0.5
        n_hi[~mask_hi] = 0.0
        n_hi = _settle_hi(n_hi, mask_hi)
        acc[y0 * factor:y1 * factor, x0 * factor:x1 * factor] += n_hi
    return acc


def _anchor_fields(eng) -> tuple[np.ndarray, np.ndarray, list, dict]:
    """The anchor-res (256²) occupancy facts: richness (distinct sids
    per cell, u2), the deduped lineages table + per-cell u2 index
    (tooltip = lineages present), and the by-sid instance groups.
    Sorted sid/instance iteration; table index assignment in sorted
    cell order — deterministic."""
    H, W = eng.ctx.H, eng.ctx.W
    by_sid: dict[str, list] = {}
    for iid in sorted(eng.instances):
        d = eng.instances[iid]
        by_sid.setdefault(d.x.species_id, []).append(d)

    def _present(ds: list) -> np.ndarray:
        present = np.zeros((H, W), dtype=bool)
        for d in ds:
            y0, y1, x0, x1 = d.box
            m = d.N > 0.0
            if m.any():
                present[y0:y1, x0:x1] |= m
        return present

    rich = np.zeros((H, W), dtype=np.uint16)
    cell_sids: dict[int, list[str]] = {}
    for sid in sorted(by_sid):
        present = _present(by_sid[sid])
        rich[present] += 1
        for y, x in zip(*np.nonzero(present)):
            # appended in sorted sid order => the per-cell list is sorted
            cell_sids.setdefault(int(y) * W + int(x), []).append(sid)

    table: list[list[str]] = []
    seen: dict[tuple, int] = {}
    idx = np.zeros(H * W, dtype=np.uint16)
    for cell in sorted(cell_sids):
        key = tuple(cell_sids[cell])
        k = seen.get(key)
        if k is None:
            k = len(table)
            seen[key] = k
            table.append(list(key))
        idx[cell] = k
    return rich, idx.reshape(H, W), table, by_sid


def _deliver(eng, rounds: int, out: Path) -> None:
    """The delivery products: high-res display pass (delivery.npz) and
    the viewer datapack (delivery.k11pack). Display-only — nothing here
    feeds back into a sim round."""
    H, W = eng.ctx.H, eng.ctx.W
    density_hi = _hires_density(eng)
    rich, lin_idx, table, by_sid = _anchor_fields(eng)
    # the k11 delivery rule for count fields: pointwise re-derive at the
    # target res from the interpolated parent (round to integer cells)
    rich_hi = np.rint(_bilinear_up(rich.astype(np.float64), HI_FACTOR)) \
        .astype(np.uint16)

    np.savez(out / "delivery.npz",
             sim_density=density_hi.astype(np.float32),
             richness_hi=rich_hi,
             richness_anchor=rich,
             lineages_idx=lin_idx)

    density_q, dm = _q8(density_hi.astype(np.float32), 0.0,
                        float(np.percentile(density_hi, 99.5)) or 1.0)
    rich_q, rm = _q8(rich_hi.astype(np.float64), 0.0,
                     float(rich_hi.max()) or 1.0)
    layers = [
        {"id": "sim_density", "label": "Sim density (display)",
         "kind": "continuous", "field": "sim_density", **dm,
         "shape": list(density_hi.shape), "colormap": RAMP_DENSITY,
         "alpha": 0.55, "mask": None, "unit": ""},
        {"id": "species_richness", "label": "Species richness",
         "kind": "continuous", "field": "species_richness", **rm,
         "shape": list(rich_hi.shape), "colormap": RAMP_RICHNESS,
         "alpha": 0.55, "mask": None, "unit": ""},
        {"id": "lineages", "label": "Lineages present", "kind": "list",
         "field": "lineages_idx", "dtype": "u2", "shape": [H, W],
         "scale": 1, "offset": 0, "lists": table},
    ]
    write_pack(out / "delivery.k11pack", layers,
               {"sim_density": density_q, "species_richness": rich_q,
                "lineages_idx": lin_idx},
               {"generator": "k15_simdiff", "pack": "sim_delivery",
                "seed": eng.seed, "rounds": rounds})


# ── the dump ───────────────────────────────────────────────────────────


def dump(eng, rounds: int, *, out: Path | None = None) -> Path:
    """Write the full delivery dump for a finished run and return the
    out dir. Deterministic: same (seed, rounds) => byte-identical files
    (the determinism gate: two runs, cmp the whole dir)."""
    out = out or out_dir(eng.seed)
    out.mkdir(parents=True, exist_ok=True)

    # 1. per-lineage density fields at end-of-run (windowed form)
    density = {
        "meta": {"schema": "k15.density/1", "world": [eng.ctx.H, eng.ctx.W],
                 "rounds": rounds, "dtypes": {"N": "f8", "mask": "u1"}},
        "instances": _instance_records(eng),
    }
    (out / "density.json").write_text(
        json.dumps(density, sort_keys=True) + "\n")

    # 2. state digest (the acceptance digest + run provenance)
    st = eng.state_json()
    st.update({
        "experiment": "k15_simdiff", "k15_version": VERSION,
        "commit": current_commit(),  # provenance stamp (k11 convention);
                                     # constant within a checkout, so the
                                     # determinism gate is unaffected
        "rounds": rounds, "world": [eng.ctx.H, eng.ctx.W],
        "lineages": len({d.x.species_id for d in eng.instances.values()}),
    })
    (out / "state.json").write_text(
        json.dumps(st, indent=1, sort_keys=True) + "\n")

    # 3. the amended tree (the same schema k13 delivers, post-rounds).
    # The meta amendment is idempotent (deterministic across re-dumps).
    tree = eng.authority.tree
    tree.meta["delivered_by"] = "k15_simdiff"
    tree.meta["rounds"] = rounds
    tree.meta["amended"] = True
    (out / "tree.json").write_text(tree.dumps())

    # 4. the authority reflog — the full decision record
    (out / "reflog.json").write_text(
        json.dumps(eng.authority.reflog, indent=1, sort_keys=True) + "\n")

    # 5. the high-res display pass + the viewer datapack
    _deliver(eng, rounds, out)

    # 6. provenance manifest (inputs chain; identical within a checkout)
    write_manifest(out, inputs=[("k11", eng.seed), ("flora", eng.seed)],
                   note="k15 sim-diff delivery (dump + display layers)")
    return out
