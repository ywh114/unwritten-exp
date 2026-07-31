# K14 World Products — Contracts

K14 = world products derived from K11 (owner ruling: K13 is the unified
tree-of-life engine, fauna + flora — the flora tree itself lives in
`exp/k13_treegen/flora/`). This file is the module-boundary contract for
the world-facing layers (P6+).

## Inputs

- K11 world dump, resolved by (generator, seed) via `exp.artifacts`
  (read-only, never copied — `require("k11", seed)`).
- Everything here is a single-pass raster/graph op over the K11 fields —
  no pipeline internals, no re-derived physics (growing season and HAND
  come from K11's own products).

## Pass order

| Stage | Module | Output |
|---|---|---|
| D0 | `derived.py` (P6) | `derived.npz` + `derived.k11pack` in `out/seed_N/` (+ manifest) |
| stress | `stress.py` (P7) | per-species passable/costly/blocked |
| F1 | `dispersal.py` (P8) | per-genus range masks + colonization PNG |
| F2/F4 | `cover.py` (P9) | per-cell layer cover mix + provisions |

## Datapack

`datapack.build_pack` writes the unified `.k11pack` viewer overlay
(header `generator = "k14_worldprod"`, `pack = "d0_derived"`), consumed
by the K11 map viewer (`exp/k11_worldgen/viewer/`).
