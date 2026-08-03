"""M2 — consistency linter (the semantic safety net).

Reviewable-data rules over the content pack. This is the layer v1 lacked: it
checks MEANING, not just structure. The crocodile-on-monkey bug class dies
here (rule: pin mass within preset magnitude). Every rule has a
planted-violation test in test_m2.py.

Rules:
  R1 diet_guild <-> feeding_organ compatible
  R2 flightless preset not overridden into active flight by a pin
  R3 pin body_mass within x0.01-x100 of its preset (the crocodile-on-monkey
     catch: an 800x mismatch is a pin/preset coherence error)
  R4 behavior coherence (social system vs group_size)
  R5 pins reference existing presets; overrides reference registered axes
  R6 every preset knob/axis references a registered axis (typo guard)
  R7 preset/pin colors within the plan's palette (M3; a mammal is never blue)
  R8 pin rank valid; radiation>=0; radiation>0 requires rank above species (M4)
  R9 drift keys registered scalar/int axes, |drift|<=3 sigma, needs radiation
     (M4 directional-drift derivations)
  R10 invented clades within budget and small-bodied (M4)
  R11 "N/A" literal only on morphometrics dials; pins may reactivate (user
      ruling: inapplicability pruning happens in the record, not downstream)

``lint(pack)`` returns a list of human-readable violation strings (empty ==
clean). ``lint_or_raise`` raises LintError aggregating them.
"""

from __future__ import annotations

from exp.k13_treegen.fauna.content import ContentPack
from exp.k13_treegen.model import Rank
from exp.k13_treegen.registry import ValueType

# diet_guild -> feeding_organ keywords (substring match, lowercase). Built to
# accept the realization vocabulary of the content pack; unknown combos are
# flagged for human review, which is the point of the linter.
DIET_FEEDING: dict[str, list[str]] = {
    "grazer": ["hypsodont", "herbivore", "incisor", "rumen"],
    "browser": ["hypsodont", "herbivore", "bunodont", "incisor"],
    "folivore": ["herbivore", "bunodont", "hypsodont"],
    "frugivore": ["bunodont", "generalist", "frugivore"],
    "granivore": ["conical", "seed", "incisor", "bunodont", "generalist"],
    "nectarivore": ["nectar", "lapping", "proboscis", "siphon"],
    "fungivore": ["mandibulate", "generalist"],
    "insectivore": ["insect", "probe", "lapping", "predatory",
                    "generalist", "tongue"],
    "piscivore": ["piscivore", "spear", "hooked", "carnassial", "carnivore"],
    "molluscivore": ["mandibulate", "durophage", "carnivore"],
    "carnivore": ["carnassial", "carnivore", "hooked", "predatory", "fang",
                  "shear"],
    "scavenger": ["hooked", "carnivore", "scaveng"],
    "filter_feeder": ["lamellate", "filter", "baleen", "raker"],
    "detritivore": ["mandibulate", "herbivore", "detrit"],
    "omnivore": ["bunodont", "generalist", "mandibulate", "carnivore",
                 "incisor", "lamellate", "filter"],
    "planktivore": ["filter", "lamellate", "raker"],
}

# flight styles that imply active flight (a flightless preset must not be
# overridden into one of these by a pin).
ACTIVE_FLIGHT = {"soaring", "sustained_flapping", "hovering", "bounding"}

# R3: pin mass must be within this factor of its preset (either direction).
PIN_MASS_FACTOR = 100.0

# R4: social systems implying a multi-individual group.
GREGARIOUS = {"family", "pack", "herd", "flock", "school", "colony",
              "eusocial"}

# R-med: aquatic strata. A pin may not jump its preset from clearly-terrestrial
# to aquatic (the crocodile-on-monkey signal: an arboreal preset anchoring a
# demersal pin). Semi-aquatic presets (otter/duck/reptile grades) are exempt.
AQUATIC_STRATA = {"demersal", "pelagic", "benthic"}


def _preset_terrestrial(preset: dict) -> bool:
    loco = str(preset.get("generics", {}).get("locomotor", "")).lower()
    stratum = _eff(preset, None, "axes", "vertical_stratum")
    semi = ("aquatic" in loco or "swim" in loco or "semi" in loco)
    return not semi and stratum not in AQUATIC_STRATA


class LintError(Exception):
    """The content pack has consistency violations."""


def _eff(preset: dict, pin: dict | None, section: str, key: str):
    """Effective value: pin override (knobs/axes/generics) else preset."""
    if pin:
        for sec in ("knobs", "axes", "generics"):
            v = pin.get(sec, {}).get(key)
            if v is not None:
                return v
    for sec in ("knobs", "axes", "generics"):
        v = preset.get(sec, {}).get(key)
        if v is not None:
            return v
    return None


def _dominant_guild(spectrum) -> str | None:
    """The highest-weight guild of a diet_spectrum map."""
    if not isinstance(spectrum, dict) or not spectrum:
        return None
    return max(spectrum.items(), key=lambda kv: kv[1])[0]


def _check_diet_feeding(pack: ContentPack, errs: list[str]) -> None:
    def bad(where: str, diet: str, fo: str) -> None:
        kw = DIET_FEEDING.get(diet)
        if kw is None:
            errs.append(f"{where}: unknown diet guild {diet!r}")
            return
        if not any(k in fo.lower() for k in kw):
            errs.append(
                f"{where}: dominant diet {diet!r} incompatible with "
                f"feeding_organ {fo!r}")
    for pid, p in pack.presets.items():
        diet = _dominant_guild(p.get("axes", {}).get("diet_spectrum"))
        fo = p.get("generics", {}).get("feeding_organ")
        if diet and fo:
            bad(f"preset {pid}", diet, fo)
    for pin in pack.pins:
        p = pack.presets.get(pin.get("preset"))
        if not p:
            continue
        spectrum = (pin.get("axes", {}).get("diet_spectrum")
                    or p.get("axes", {}).get("diet_spectrum"))
        diet = _dominant_guild(spectrum)
        fo = _eff(p, pin, "generics", "feeding_organ")
        if diet and fo:
            bad(f"pin {pin.get('label')!r}", diet, fo)


def _check_flight(pack: ContentPack, errs: list[str]) -> None:
    for pin in pack.pins:
        p = pack.presets.get(pin.get("preset"))
        if not p:
            continue
        preset_fs = _eff(p, None, "knobs", "flight_style")
        pin_fs = pin.get("knobs", {}).get("flight_style")
        if preset_fs == "flightless" and pin_fs in ACTIVE_FLIGHT:
            errs.append(
                f"pin {pin.get('label')!r}: flightless preset overridden "
                f"into active flight {pin_fs!r}")


def _check_pin_mass(pack: ContentPack, errs: list[str]) -> None:
    for pin in pack.pins:
        preset_mass = pack.preset_body_mass(pin.get("preset"))
        pin_mass = pin.get("axes", {}).get("body_mass")
        if (preset_mass and isinstance(pin_mass, (int, float))
                and pin_mass > 0 and preset_mass > 0):
            ratio = pin_mass / preset_mass
            if ratio > PIN_MASS_FACTOR or ratio < 1.0 / PIN_MASS_FACTOR:
                errs.append(
                    f"pin {pin.get('label')!r}: body_mass {pin_mass} is "
                    f"{ratio:.0f}x preset {pin.get('preset')!r} "
                    f"({preset_mass}) — pin/preset coherence error "
                    f"(crocodile-on-monkey class)")


def _check_behavior(pack: ContentPack, errs: list[str]) -> None:
    def check(where: str, soc: str, gs) -> None:
        if soc in GREGARIOUS and isinstance(gs, (int, float)) and gs <= 1:
            errs.append(f"{where}: social_system {soc!r} but group_size {gs}")
        if soc == "eusocial" and isinstance(gs, (int, float)) and gs < 10:
            errs.append(f"{where}: eusocial but group_size {gs}")
    for pid, p in pack.presets.items():
        check(f"preset {pid}", p.get("axes", {}).get("social_system"),
              p.get("axes", {}).get("group_size"))
    for pin in pack.pins:
        p = pack.presets.get(pin.get("preset"))
        if not p:
            continue
        check(f"pin {pin.get('label')!r}",
              _eff(p, pin, "axes", "social_system"),
              _eff(p, pin, "axes", "group_size"))


def _check_medium(pack: ContentPack, errs: list[str]) -> None:
    for pin in pack.pins:
        p = pack.presets.get(pin.get("preset"))
        if not p or not _preset_terrestrial(p):
            continue
        pin_stratum = _eff(p, pin, "axes", "vertical_stratum")
        if pin_stratum in AQUATIC_STRATA:
            errs.append(
                f"pin {pin.get('label')!r}: aquatic stratum "
                f"{pin_stratum!r} under terrestrial preset "
                f"{pin.get('preset')!r} (medium jump)")


def _check_references(pack: ContentPack, errs: list[str]) -> None:
    reg_axes = set(pack.registry.axes)
    for pid, p in pack.presets.items():
        for sec in ("knobs", "axes"):
            for key in p.get(sec, {}):
                if key not in reg_axes:
                    errs.append(f"preset {pid}: {sec}.{key} not a "
                                f"registered axis")
    for pin in pack.pins:
        if pin.get("preset") not in pack.presets:
            errs.append(f"pin {pin.get('label')!r}: unknown preset "
                        f"{pin.get('preset')!r}")
            continue
        for sec in ("knobs", "axes"):
            for key in pin.get(sec, {}):
                if key not in reg_axes:
                    errs.append(f"pin {pin.get('label')!r}: {sec}.{key} "
                                f"not a registered axis")


def _check_palette(pack: ContentPack, errs: list[str]) -> None:
    """R-palette (M3): colors must be reachable by the plan's pigment/
    structural palette — a mammal is never blue. A preset may widen the
    reach for its grade via [preset] palette_extra (e.g. structural blue
    in lizards); pins inherit their preset's widened palette."""

    def legal_for(preset: dict) -> list[str] | None:
        plan = preset.get("preset", {}).get("plan")
        legal = pack.palettes.get(plan)
        if legal is None:
            return None
        return legal + list(preset.get("preset", {}).get("palette_extra", []))

    color_axes = ("base_color", "belly_color", "accent_color")
    for pid, p in pack.presets.items():
        plan = p.get("preset", {}).get("plan")
        legal = legal_for(p)
        if legal is None:
            errs.append(f"preset {pid}: no palette for plan {plan!r}")
            continue
        for ax in color_axes:
            c = p.get("axes", {}).get(ax)
            if c is not None and c not in legal:
                errs.append(f"preset {pid}: {ax} {c!r} not in {plan} "
                            f"palette")
    for pin in pack.pins:
        p = pack.presets.get(pin.get("preset"))
        if not p:
            continue
        plan = p.get("preset", {}).get("plan")
        legal = legal_for(p) or []
        for ax in color_axes:
            c = pin.get("axes", {}).get(ax)
            if c is not None and c not in legal:
                errs.append(f"pin {pin.get('label')!r}: {ax} {c!r} not in "
                            f"{plan} palette")


# R9: drift is a directional lean in units of the axis's own sigma. Past 3
# sigma you are not leaning, you are teleporting — author absolute overrides
# on the pin instead.
DRIFT_MAX_SIGMA = 3.0

# R10: invented clades must be small-bodied. The everyday register is real
# animals (taste bootstrap); invented novelty is accepted in the critter
# tier — a novel rat, not a novel elephant. 1.0 kg = rat-sized.
INVENTED_MAX_MASS_KG = 1.0


def _check_pin_rank(pack: ContentPack, errs: list[str]) -> None:
    ranks = {r.name.lower() for r in Rank}
    labels = {p.get("label"): p for p in pack.pins}
    for pin in pack.pins:
        label = pin.get("label")
        rank = str(pin.get("rank", "species")).lower()
        if rank not in ranks:
            errs.append(f"pin {label!r}: unknown rank {rank!r}")
            continue
        radiation = pin.get("radiation", 0)
        if not isinstance(radiation, int) or radiation < 0:
            errs.append(f"pin {label!r}: radiation {radiation!r} must be a "
                        f"non-negative integer")
        elif radiation > 0 and Rank[rank.upper()] is Rank.SPECIES:
            errs.append(f"pin {label!r}: radiation {radiation} on a "
                        f"species-rank pin (a species does not radiate)")
        pp = pin.get("parent_pin")
        if pp is not None:
            host = labels.get(pp)
            if host is None:
                errs.append(f"pin {label!r}: parent_pin {pp!r} unknown")
            elif host.get("rank") != "genus":
                errs.append(f"pin {label!r}: parent_pin {pp!r} is not a "
                            f"genus-rank pin")
            elif host.get("preset") != pin.get("preset"):
                errs.append(f"pin {label!r}: parent_pin {pp!r} under a "
                            f"different preset")


def _check_drift(pack: ContentPack, errs: list[str]) -> None:
    for pin in pack.pins:
        label = pin.get("label")
        drift = pin.get("drift")
        if drift is None:
            continue
        if not isinstance(drift, dict):
            errs.append(f"pin {label!r}: drift must be a table of "
                        f"axis = signed_sigma")
            continue
        if not pin.get("radiation", 0):
            errs.append(f"pin {label!r}: drift on a non-radiating pin is "
                        f"dead content (no descendants to bias)")
        for ax, v in drift.items():
            spec = pack.registry.axes.get(ax)
            if spec is None:
                errs.append(f"pin {label!r}: drift.{ax} not a registered "
                            f"axis")
                continue
            if spec.value_type not in (ValueType.SCALAR, ValueType.INT):
                errs.append(f"pin {label!r}: drift.{ax} is "
                            f"{spec.value_type.value} — a signed lean is "
                            f"meaningless on non-scalar axes (enum redraw "
                            f"is directionless)")
            if not isinstance(v, (int, float)):
                errs.append(f"pin {label!r}: drift.{ax} value {v!r} not "
                            f"numeric")
            elif abs(v) > DRIFT_MAX_SIGMA:
                errs.append(f"pin {label!r}: drift.{ax} = {v} exceeds "
                            f"{DRIFT_MAX_SIGMA} sigma — author absolute "
                            f"overrides instead of teleporting")


def _check_invented_budget(pack: ContentPack, errs: list[str]) -> None:
    budget = pack.budget.get("invented_max", 0)
    invented = [p for p in pack.pins if "invented" in p.get("flags", [])]
    if len(invented) > budget:
        errs.append(f"{len(invented)} invented pins exceed budget "
                    f"invented_max = {budget}")
    for pin in invented:
        mass = _eff(pack.presets.get(pin.get("preset"), {}), pin,
                    "axes", "body_mass")
        if isinstance(mass, (int, float)) and mass > INVENTED_MAX_MASS_KG:
            errs.append(f"invented pin {pin.get('label')!r}: body_mass "
                        f"{mass} kg exceeds invented small-bodied ceiling "
                        f"{INVENTED_MAX_MASS_KG} kg (novelty lives in the "
                        f"critter tier)")


def _check_na_legality(pack: ContentPack, errs: list[str]) -> None:
    """R-na (user ruling): "N/A" marks a feature absent whose axis vocabulary
    cannot express absence (0.0/"none" is already honest elsewhere). Only
    PLAN-SCOPED morphometrics dials may be N/A — an axis scoped "all"
    applies to every body (body_mass included, morphometrics block or not),
    and core/patternation/niche axes are always applicable. Pins may
    REACTIVATE an N/A preset dial (N/A -> real value is a legitimate
    derivation, e.g. a horned-lizard pin)."""
    morph = {n for n, a in pack.registry.axes.items()
             if a.block.value == "morphometrics" and a.plan_scope != "all"}
    for pid, p in pack.presets.items():
        for sec in ("knobs", "axes"):
            for key, v in p.get(sec, {}).items():
                if v == "N/A" and key not in morph:
                    errs.append(f"preset {pid}: {sec}.{key} = N/A on a "
                                f"non-morphometrics axis (core axes are "
                                f"always applicable)")
    for pin in pack.pins:
        for sec in ("knobs", "axes"):
            for key, v in pin.get(sec, {}).items():
                if v == "N/A" and key not in morph:
                    errs.append(f"pin {pin.get('label')!r}: {sec}.{key} = "
                                f"N/A on a non-morphometrics axis")


RULES = [
    ("diet_feeding", _check_diet_feeding),
    ("flight", _check_flight),
    ("pin_mass", _check_pin_mass),
    ("behavior", _check_behavior),
    ("medium", _check_medium),
    ("references", _check_references),
    ("palette", _check_palette),
    ("pin_rank", _check_pin_rank),
    ("drift", _check_drift),
    ("invented_budget", _check_invented_budget),
    ("na_legality", _check_na_legality),
]


def lint(pack: ContentPack) -> list[str]:
    """Run every consistency rule; return violation strings (empty == clean)."""
    errs: list[str] = []
    for _, fn in RULES:
        fn(pack, errs)
    return errs


def lint_or_raise(pack: ContentPack) -> None:
    errs = lint(pack)
    if errs:
        raise LintError("content pack consistency violations:\n  " +
                        "\n  ".join(errs))
