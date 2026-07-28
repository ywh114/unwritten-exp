# M12 — description renderer (the text demo)

Interface doc. One-liner species descriptions, computed from the committed
record — every word traces to an axis or generic (the test asserts the
trace). Not prose generation; a template with slot resolvers.

## Template

```
a|an [size] [covering] [grade]-like [diet] with [salient part]
```

- **size** — body_mass class: mouse-grade / small / medium / sizeable /
  large / enormous (named thresholds).
- **covering** — generics.covering (fur, feathers, chitin cuticle,
  scales...).
- **grade** — the preset's grade string + "-like" (cat-like, deer-like).
- **diet** — dominant guild of diet_spectrum; when the top two guilds are
  close (ratio < PAIR_RATIO), the pair ("carnivore-frugivore").
- **salient part** — the PART-role axis (M1 grammar_role) with the highest
  `axis.salience × |deviation from preset|` (σ units), rendered via the
  authored phrase table; N/A values are never mentioned. Fallback: no
  "with" clause.

## Hard rules (acceptance)

- **Traceable**: `describe()` returns (text, trace) — trace maps each slot
  to the axis/generic it came from. A word that traces to nothing is a
  bug.
- **No contradiction**: values render what the record says — a flightless
  bird is never "soaring" (phrase table is keyed on the ACTUAL value);
  N/A is silence, not a phrase.
- **Grammatical**: a/an agreement on the first slot.
