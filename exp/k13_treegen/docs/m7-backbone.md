# M7 — backbone: the blind tree-build

Interface doc. Assembles the committed Tree from the content pack: one
kingdom root, the authored frame map, one order per preset, pins placed at
their authored ranks, radiations evolved with M5/M6. World-blind: benign
Condition throughout; the rounds layer re-runs this machinery with real
conditions later.

## Structure

```
k1 animalia                                   (kingdom; plantae hook reserved)
└── pN phylum      (authored frame map: plans.toml phylum/frame)
    └── cN class   (one per plan; plan COMMITTED here)
        └── oN order  (one per preset; preset + full preset axes committed)
            └── fN family  (evolved from order; family pins anchor here)
                └── gN genus (evolved; genus pins anchor here)
                    └── sN species (evolved; species pins committed byte-exact)
```

- **Frame map is authored** (plans.toml: chordata/inner_frame for tetrapod
  + winged_biped, arthropoda/outer_frame for hexapod) and enforced by
  metric — phyla are numbered in first-seen plan order.
- **Class/phylum/kingdom nodes are structural** (no axes). Lineage
  evolution runs order → species: the order node carries the preset's full
  axes; everything below evolves from it.
- **No empty orders**: orders without a radiation pin get a small seeded
  background radiation (BG_RADIATION_LO..HI species).

## Pins (M4 contract, honored here)

- **Order pin** (beetles): the order node itself gets label + merged
  overrides, byte-exact.
- **Family pin** (murid rodents, passerine songbirds): anchors a family in
  its preset's order; radiation spreads over a seeded number of genera.
- **Genus pin** (equines, coal-rat): anchors a genus under the order's
  default family; its `drift` vector biases every descendant — applied as
  a σ-shift on each speciation edge beneath the pin (the "horse but more
  cursorial" existence proof measures exactly this).
- **Species pins**: committed byte-exact (merged_pin) under the default
  family's default genus. **Every species pin gets RELATIVES** (seeded
  1..2 generated sibling species) — no orphan pins.
- **Radiation counts**: actual = round(N × lognormal(0, RADIATION_SIGMA)),
  min 1; the metric allows [N/3, 3N].

## Evolution parameters (per edge, K1-seeded)

- dg budgets per rank step (lognormal): order→family DG_ORDER, family→
  genus DG_FAMILY, genus→species DG_GENUS.
- **Lineage consistency**: rate multiplier and runaway direction are drawn
  ONCE per family from the family's own substream and passed into every
  evolve beneath (evolve's rate_mult/runaway_dir params).
- Benign Condition: drift + background runaway only; between-order
  distance exceeds within-order because orders start from different preset
  points and drift disperses around them.
- Edge streams: `stage_stream(seed, "backbone").child(path)` per node —
  byte-identical replay, different seed differs.

## Metrics checkers added

- `backbone` — single animalia root; frame map (tetrapod/winged_biped
  under inner-frame phylum, hexapod under outer); no empty orders.
- `pin_integration` — every pin present at authored rank; pinned node
  axes byte-exact vs merged_pin; every species pin has ≥1 sibling;
  radiation counts within soft range.
- Sister distance ≈ σ and between>within are verified in test_m7 directly
  on the built tree (they need real clades).
