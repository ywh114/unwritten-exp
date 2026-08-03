"""Preview — resolve a pin against its preset into a complete specimen
record and dump it as M0 Node JSON.

This is NOT the generator (M5–M7 will be). Pins are hand-authored Tier-1
anchors, so a resolved pin is the only complete organism record the system
can present today — useful for eyeballing content and for exercising the
Node JSON persistence shape end-to-end.

Usage:  uv run python -m exp.k13_treegen.fauna.preview tiger
        uv run python -m exp.k13_treegen.fauna.preview --list
"""

from __future__ import annotations

import argparse
import json
import pathlib

from exp.k13_treegen.fauna.content import ContentPack, load_content, merged_pin
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.fauna.seeding import STAGE_PINS, stage_stream

CONTENT = pathlib.Path(__file__).parent.parent / "content" / "fauna"


def resolve_pin(pack: ContentPack, label: str, seed: int = 0) -> Node:
    """Merge preset + pin overrides (pin wins) into a specimen Node."""
    pin = next((p for p in pack.pins if p.get("label") == label), None)
    if pin is None:
        raise KeyError(f"no pin labeled {label!r}")
    preset = pack.presets[pin["preset"]]
    # M0: knobs (morphometrics) and core axes both live in Node.axes
    axes, generics = merged_pin(pack, pin)
    stream = stage_stream(seed, *STAGE_PINS).child(f"preview/{label}")
    return Node(
        path=f"preview.{label.replace(' ', '_')}",
        rank=Rank[str(pin.get("rank", "species")).upper()],
        parent=None,
        sid=f"{stream.u64(0):016x}",
        plan=preset["preset"]["plan"],
        preset=pin["preset"],
        label=label,
        axes=axes,
        generics=generics,
        flags=list(pin.get("flags", [])),
    )


def preview_record(pack: ContentPack, label: str, seed: int = 0) -> dict:
    """The full preview: Node JSON + pin-only metadata (rank/radiation/
    drift — backbone controls, not Node fields)."""
    pin = next(p for p in pack.pins if p.get("label") == label)
    return {
        "node": resolve_pin(pack, label, seed).to_json(),
        "pin": {k: pin[k] for k in ("rank", "radiation", "drift")
                if k in pin},
    }


def gloss(pack: ContentPack, label: str) -> str:
    """One-line informal summary (NOT the M12 description renderer)."""
    n = resolve_pin(pack, label)
    a = n.axes
    diet = a.get("diet_spectrum", {})
    diet_s = max(diet, key=diet.get) if diet else "?"
    patt = a.get("pattern_motif", "?")
    colors = "/".join(str(a.get(c, "?")) for c in
                      ("base_color", "belly_color", "accent_color"))
    return (f"{label} [{n.plan}/{n.preset}] {a.get('body_mass', '?')} kg, "
            f"{diet_s}, {patt} {colors}, {n.generics.get('covering', '?')}, "
            f"{a.get('activity_period', '?')}, {a.get('social_system', '?')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("label", nargs="?", help="pin label, e.g. tiger")
    ap.add_argument("--list", action="store_true", help="list pin labels")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    pack = load_content(CONTENT)
    if args.list or not args.label:
        for p in pack.pins:
            print(f"{p['label']:<24} {p['preset']:<24} "
                  f"{p.get('rank', 'species')}")
        return
    print(gloss(pack, args.label))
    print(json.dumps(preview_record(pack, args.label, args.seed),
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
