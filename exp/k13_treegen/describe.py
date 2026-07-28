"""M12 — description renderer (docs/m12-description.md).

One-liner species descriptions from the committed record. describe()
returns (text, trace): the trace maps every slot to its source axis or
generic — a word that traces to nothing is a bug, and the tests assert
it. N/A is silence, values render what the record says.
"""

from __future__ import annotations

from exp.k13_treegen.content import ContentPack
from exp.k13_treegen.model import Node
from exp.k13_treegen.registry import GrammarRole

# size classes by body_mass kg (grounded in the preset spread: mouse
# 0.02, rabbit 2, deer 100, bear 300, whale-grade 1e5). Plain words —
# NOT "X-grade": "grade" is reserved for the preset archetype (B1).
SIZE_CLASSES = [
    (0.1, "tiny"),
    (1.0, "small"),
    (10.0, "medium"),
    (100.0, "sizeable"),
    (1000.0, "large"),
    (float("inf"), "enormous"),
]
# top-two guilds closer than this read as a pair ("carnivore-frugivore").
PAIR_RATIO = 1.5

# authored phrase table for salient parts: axis -> {value or
# "high"/"low" -> phrase}. Keyed on the ACTUAL record value — a phrase
# can never contradict the axis it renders.
PART_PHRASES: dict[str, dict[str, str]] = {
    "tail_length_ratio": {"high": "a long tail", "low": "a stub tail"},
    "ear_size_ratio": {"high": "large ears", "low": "pin ears"},
    "ear_posture": {"erect": "erect ears", "semi-erect": "half-erect ears",
                    "folded": "folded ears", "pendant": "pendant ears"},
    "snout_ratio": {"high": "a long snout", "low": "a blunt snout"},
    "neck_length_ratio": {"high": "a long neck", "low": "a short neck"},
    "mane_ruff_extent": {"high": "a full mane"},
    "tail_carriage": {"curled": "a curled tail", "sickle": "a sickle tail",
                      "raised": "a raised tail", "level": "a level tail",
                      "low": "a low-slung tail"},
    "crest": {"high": "a tall crest"},
    "pupil_shape": {"vertical_slit": "slit pupils",
                    "horizontal_slit": "bar pupils",
                    "round": "round pupils", "W": "W-shaped pupils",
                    "crescent": "crescent pupils"},
    "foot_webbing_grade": {"full": "fully webbed feet",
                           "partial": "webbed feet"},
    "vibrissae_prominence": {"high": "bushy whiskers"},
    "horn_cover_texture": {"velvet": "velveted horns",
                           "bare_keratin": "bare keratin horns"},
    "dorsal_crest_spines": {"high": "a spiny dorsal crest"},
    "neck_frill": {"high": "a neck frill"},
    "proboscis_grade": {"high": "a trunk"},
}

_SCALAR_BOUNDS = ("high", "low")


def _size_class(mass: float) -> str:
    for hi, word in SIZE_CLASSES:
        if mass < hi:
            return word
    return "enormous"


def _diet_word(spectrum) -> str:
    if not isinstance(spectrum, dict) or not spectrum:
        return "feeder"
    top = sorted(spectrum.items(), key=lambda kv: -kv[1])
    if len(top) > 1 and top[0][1] < PAIR_RATIO * top[1][1] and top[1][1]:
        return f"{top[0][0]}-{top[1][0]}"
    return top[0][0]


def _part_phrase(node: Node, pack: ContentPack) -> tuple[str | None, str | None]:
    """Highest salience x deviation PART axis; returns (phrase, axis)."""
    preset = pack.presets.get(node.preset or "", {})
    best: tuple[float, str, str] | None = None
    for name, spec in pack.registry.axes.items():
        if spec.grammar_role is not GrammarRole.PART:
            continue
        phrases = PART_PHRASES.get(name)
        if not phrases:
            continue
        value = node.axes.get(name)
        if value is None or value == "N/A":
            continue
        if isinstance(value, (int, float)):
            pval = {**preset.get("knobs", {}),
                    **preset.get("axes", {})}.get(name, value)
            dev = (abs(value - pval) / spec.sigma) if spec.sigma else 0.0
            side = "high" if value > pval else "low"
            phrase = phrases.get(side) or (
                phrases.get("high") if dev > 1.0 else None)
        else:
            pval = {**preset.get("knobs", {}),
                    **preset.get("axes", {})}.get(name)
            dev = 1.0 if value != pval else 0.0
            phrase = phrases.get(str(value))
        if not phrase or dev == 0.0:
            continue
        score = spec.salience * (1.0 + dev)
        if best is None or score > best[0]:
            best = (score, phrase, name)
    if best is None:
        return None, None
    return best[1], best[2]


def _article(phrase: str) -> str:
    return "an" if phrase[0].lower() in "aeiou" else "a"


def describe(node: Node, pack: ContentPack) -> tuple[str, dict]:
    """(text, trace): the one-liner plus per-slot source audit."""
    trace: dict[str, str] = {}
    mass = node.axes.get("body_mass", 1.0)
    size = _size_class(float(mass)) if isinstance(mass, (int, float)) \
        else "medium"
    trace["size"] = "axes.body_mass"
    covering = node.generics.get("covering", "skinned").replace("_", " ")
    trace["covering"] = "generics.covering"
    grade = (pack.presets.get(node.preset or "", {})
             .get("preset", {}).get("grade", "creature"))
    trace["grade"] = "preset.grade"
    diet = _diet_word(node.axes.get("diet_spectrum"))
    trace["diet"] = "axes.diet_spectrum"
    head = f"{size} {covering} {grade}-like {diet}"
    text = f"{_article(size)} {head}"
    part, part_axis = _part_phrase(node, pack)
    if part:
        text += f" with {part}"
        trace["salient_part"] = f"axes.{part_axis}"
    return text, trace
