"""Human-readable species description (spec B9 §6; ticket 0042).

``describe(record, pack)`` renders the full derived view in human terms
— the encyclopedia entry and the note-3a "what IS this species" answer
in one: what it is (binomial slot, plan, salient traits), its climate
envelope, its mass and proportions, every intrinsic-stress term with
its cause, what it offers the food web (the provision map), and how it
disperses.  It reads ONLY the canonical view (``flora.view.assemble_view``)
— this hook computes nothing itself (B9 §1, §6).

Runnable against the real content pack:

    PYTHONPATH=. uv run python -m exp.k15_biosphere.describe succulent.cactus

reads the settled flora content IN PLACE (``exp/k13_treegen/content/
flora`` — the CONTENT_DIR pattern; content is shared data, never
copied, never imported) and describes the preset's committed record.
"""

from __future__ import annotations

import sys
from pathlib import Path

from exp.k15_biosphere.content import ContentPack, load_content, merged_preset
from exp.k15_biosphere.flora.view import assemble_view
from exp.k15_biosphere.record import SpeciesRecord

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = Path(__file__).parent.parent / "k13_treegen" / "content" / "flora"

SALIENT_TRAIT_COUNT = 6


def _fmt(value, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}g}"
    if isinstance(value, dict):
        return ", ".join(f"{k}={_fmt(v)}" for k, v in sorted(value.items()))
    return str(value)


def describe(record: SpeciesRecord, pack: ContentPack) -> str:
    """The full derived view in human terms (the encyclopedia entry)."""
    view = assemble_view(record, pack)
    plan = record.plan or "?"
    lines = [f"species {record.sid}"]
    # what it is: the binomial stays a slot until the final-round naming
    # pass runs over the committed tree (B9 §5)
    lines.append("  binomial:   (unassigned — the naming pass runs once, "
                 "at the final round; B9 §5)")
    lines.append(f"  plan:       {plan}"
                 + (f"  (preset {record.preset})" if record.preset else ""))
    lines.append(f"  generation: g={record.g:.1f} gen  "
                 f"gen_time={record.gen_time:.1f} yr/gen")
    salient = [a for a in pack.registry.salience_order(plan)
               if a.name in record.axes][:SALIENT_TRAIT_COUNT]
    if salient:
        lines.append("  traits:     " + ", ".join(
            f"{a.name}={_fmt(record.axes[a.name])}" for a in salient))
    # climate envelope
    lines.append(f"  climate:    optimum {view['temp_opt_c']:.1f}±"
                 f"{view['temp_breadth_c']:.1f} °C, moisture "
                 f"{view['moisture_opt']:.2f}±{view['moisture_breadth']:.2f} "
                 f"(normalized)")
    # mass + proportions
    lines.append(f"  mass:       {view['mass_total_kg']:.1f} kg dry per "
                 f"individual (aboveground {view['mass_agb_kg']:.1f} kg)")
    if view["mass_proportions"]:
        lines.append("  proportions: " + ", ".join(
            f"{k}={_fmt(v)}" for k, v in sorted(
                view["mass_proportions"].items())))
    # intrinsic stress — every term with its cause (B9 §6)
    for key in sorted(view["intrinsic_stress"]):
        term = view["intrinsic_stress"][key]
        lines.append(f"  stress {key}: {term['value']:.3f}  —  {term['cause']}")
        lines.append(f"      wiring: {term['wiring']}")
    # what it offers the food web
    lines.append("  provisions: "
                 f"mast {view['provision_mast']:.2f}  "
                 f"graze {view['provision_graze']:.2f}  "
                 f"browse {view['provision_browse']:.2f}  "
                 f"nectar {view['provision_nectar']:.2f}  "
                 f"shelter {view['provision_shelter']:.2f}")
    # how it disperses
    channels = view["dispersal_channels"] or {}
    ch = (", ".join(f"{k}={v:.2f}" for k, v in sorted(channels.items()))
          or "n/a")
    lines.append("  dispersal:  channels (" + ch + ")  "
                 f"propagule {_fmt(view['propagule_mass_mg'])} mg × "
                 f"{_fmt(view['propagule_count'])}  "
                 f"seed_bank {_fmt(view['seed_bank'])}  "
                 f"jump_rate {_fmt(view['jump_rate'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: python -m exp.k15_biosphere.describe <preset_id>",
              file=sys.stderr)
        return 2
    preset_id = args[0]
    pack = load_content(CONTENT_DIR)
    preset = pack.presets.get(preset_id)
    if preset is None:
        print(f"no preset {preset_id!r} in the flora pack "
              f"({len(pack.presets)} presets)", file=sys.stderr)
        return 2
    axes, generics = merged_preset(preset)
    record = SpeciesRecord(
        sid="<preset>", plan=preset["preset"]["plan"], preset=preset_id,
        axes=axes, generics=generics)
    print(describe(record, pack))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
