# M8 — nomenclature (naming engine + blind classification shell)

Interface doc. Names are data, computed from the committed record (RFC §9:
"the engine computes an epithet; the LLM never composes one"). Source
research: `specs/naming-binomial-stems.md` (attested register, suffix
mechanics, collision chain). User rulings 2026-07-28 relax its purism for
the fantasy setting:

- **Stems**: attested-majority, invented Latinate gap-fill, deliberate
  double coverage (an axis may have several stems — variety is wanted).
- **Genera**: composed stochastically mixed — mechanical descriptor+plan-
  suffix AND free Latinate invention (real taxonomy is confusing too).
  Only PIN-name collisions are guarded; no real-world taxonomy check
  ("accidental collisions with non-pinned allowed").
- **Folk names**: deferred past M8 (rounds/LLM layer).

## The one function

```
assign_names(tree, pack, seed, context=None) -> None   # mutates NameRecords
```

Stream: `naming_stage(seed, round)` (M0 seeding). The blind build runs one
pass (round 0); the rounds re-pass — rename only when a salient axis moved
(stability metric), append to `name.history`, commit at the final round.

## Genus names (classification shell)

- **Pins name their clade** (authored in pins.toml `name` table): species
  pins carry real binomials (*Equus caballus*), genus/clade pins carry the
  real clade name (*Equus*, Muridae, Coleoptera) — content, taste-authored.
- **Generated genera**: seeded style pick per genus —
  `mechanical` (descriptor stem + §3.1 plan suffix: *Cinereomys*) or
  `invent` (free Latinate from authored onset/rime fragment pools:
  *Velluma*, *Thraexis*). Collision vs committed names → K1-child redraw.
- **Gender**: authored per plan suffix (-mys m, -ornis m, -ptera f,
  -therium n, ...); invented names take gender from their ending
  (-us m, -a f, -um n). The epithet agrees via the §2.2 gender maps.
- **Placement refinement**: a species pin may name `parent_pin` (horse →
  equines genus) so pinned species sit inside pinned clades.

## Species epithets (naming engine)

1. **Salience** per [name]-consumer axis: scalars `|v − genus median| /
   std × axis.salience` (std 0 → 0); enums 0/1 vs the genus modal ×
   salience. Highest wins — the discriminating trait.
2. **Axis → stem pool** (stems.toml, attested + invented): threshold
   direction picks high/low stem (longi-/brevi-), enum axes map directly.
   Seeded pick when the pool has several stems (double coverage).
3. **Suffix** per the §2.3 policy table by axis category; gender form per
   the §2.2 hardcoded maps.
4. **Collision (within-genus only)**: secondary axis → seeded suffix swap
   → 4-char sid fragment. Each step via the genus's K1 child stream.

## The world hook — NameContext

```python
@dataclass
class NameContext:
    facts: dict[str, str] = field(default_factory=dict)  # habitat, region
```

Stems gated on world facts (geography: *borealis*; true habitat-of-
occurrence: *palustris*) are candidates only when the context supplies the
fact. The blind build passes an empty context — those stems are silent,
exactly the Condition.env pattern. Record-driven habitat (vertical_stratum
→ *arboricola*, moisture_opt → *aridus*) is always computable and allowed.

## Metrics checker added

- `nomenclature` — every species named (pins from content, generated
  well-formed: genus capitalized + epithet from the register); uniqueness
  within genus (cross-genus epithet repeats ALLOWED — convergent *rufus*);
  pinned names byte-equal to pins.toml; no generated name equals a pin's.
