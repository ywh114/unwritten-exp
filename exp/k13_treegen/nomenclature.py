"""M8 — nomenclature: naming engine + blind classification shell
(docs/m8-nomenclature.md).

Names are data, computed from the committed record. assign_names() runs one
pass per round over the tree: pins bring real names (content), generated
genera are composed (mechanical descriptor+suffix OR free invention,
seeded style mix), species epithets follow the salience of the
discriminating trait. World facts (geography, habitat-of-occurrence)
arrive via NameContext; absent in the blind build, those stems stay
silent.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from exp.k13_treegen.content import ContentPack
from exp.k13_treegen.model import Rank, Tree
from exp.k13_treegen.seeding import naming_stage

# plan -> genus_suffix table grades used for mechanical composition.
PLAN_SUFFIX_GRADE = {
    "tetrapod": ["rodent", "generic"],
    "winged_biped": ["bird"],
    "hexapod": ["insect"],
}
# gender per plan suffix (authored; Greek -mys/-ops/-ornis masculine,
# -ptera/-formica/-avis feminine, -therium neuter).
SUFFIX_GENDER = {
    "-mys": "m", "-ops": "m", "-oides": "m", "-ornis": "m", "-saurus": "m",
    "-ichthys": "m", "-piscis": "m", "-batrachus": "m", "-ophis": "m",
    "-serpens": "m", "-carcinus": "m", "-astacus": "m", "-limax": "m",
    "-vermis": "m", "-helminthus": "m", "-pulmo": "m",
    "-avis": "f", "-gavia": "f", "-ptera": "f", "-formica": "f",
    "-lacerta": "f", "-chelys": "f", "-testudo": "f", "-rana": "f",
    "-arachne": "f", "-concha": "f", "-medusa": "f",
    "-therium": "n", "-scorpio": "n",
}


# salience of a context-fact stem (geography/habitat-of-occurrence) —
# strong, but beatable by a truly discriminating trait.
CONTEXT_SALIENCE = 0.85


@dataclass
class NameContext:
    """World-fact hook (rounds seam): geography, habitat-of-occurrence.
    Absent in the blind build — gated stems stay silent."""
    facts: dict[str, str] = field(default_factory=dict)


def _gender_of_invented(name: str) -> str:
    if name.endswith("us"):
        return "m"
    if name.endswith("a"):
        return "f"
    if name.endswith("um"):
        return "n"
    return "m"


def _agree(base: str, pattern: str, gender: str) -> str:
    """Gender agreement, two patterns only (no declension tables, §3.4.2)."""
    if pattern == "us":
        return base + {"m": "us", "f": "a", "n": "um"}[gender]
    if pattern == "is":
        return base + {"m": "is", "f": "is", "n": "e"}[gender]
    return base


def _compose_genus(stream, pack: ContentPack, plan: str,
                   used: set[str]) -> tuple[str, str]:
    """Seeded style mix: mechanical descriptor+suffix or free invention.
    Redraw on collision with committed names (K1 child stream)."""
    stems = pack.stems
    for clock in range(50):
        if stream.bernoulli(0.5, clock, 0):
            # mechanical: color/habitat descriptor + plan suffix
            pool = [s for s in stems["stem"]
                    if s["category"] in ("color", "habitat")]
            pick = pool[stream.randrange(len(pool), clock, 1)]
            descriptor = pick["stem"].split(" /")[0].rstrip("-")
            grades = PLAN_SUFFIX_GRADE.get(plan, ["generic"])
            grade = grades[stream.randrange(len(grades), clock, 2)]
            suffixes = stems["genus_suffix"][grade]["suffixes"]
            suffix = suffixes[stream.randrange(len(suffixes), clock, 3)]
            name = (descriptor + suffix.lstrip("-")).capitalize()
            gender = SUFFIX_GENDER.get(suffix, "m")
        else:
            inv = stems["invent"]
            name = (inv["onsets"][stream.randrange(len(inv["onsets"]),
                                                   clock, 1)]
                    + inv["link"][stream.randrange(len(inv["link"]),
                                                   clock, 2)]
                    + inv["rimes"][stream.randrange(len(inv["rimes"]),
                                                    clock, 3)])
            gender = _gender_of_invented(name)
        if name not in used:
            return name, gender
    raise RuntimeError("genus name space exhausted (should not happen)")


def _dominant_guild(spectrum) -> str | None:
    if not isinstance(spectrum, dict) or not spectrum:
        return None
    return max(spectrum.items(), key=lambda kv: kv[1])[0]


def _axis_value(node_axes: dict, axis: str):
    if axis == "diet_dominant":
        return _dominant_guild(node_axes.get("diet_spectrum"))
    return node_axes.get(axis)


def _salience(node_axes: dict, axis: str, pool_entries: list,
              stats: dict, weight: float) -> float:
    """Deviation from the genus norm x authored salience."""
    v = _axis_value(node_axes, axis)
    if v is None or v == "N/A":
        return 0.0
    directions = {e.get("direction") for e in pool_entries}
    med, std = stats.get(axis, (None, None))
    if isinstance(v, (int, float)):
        if med is None or not std:
            return 0.0
        z = abs(v - med) / std
        # only count if some pool entry covers this side of the median
        side = "high" if v > med else "low"
        if side not in directions:
            return 0.0
        return z * weight
    # enum: salient iff it differs from the genus modal and is covered
    if med is not None and str(v) == str(med):
        return 0.0
    if str(v) not in {e.get("value") for e in pool_entries}:
        return 0.0
    return weight


def _pick_stem(entries: list, node_axes: dict, axis: str,
               stats: dict, stream, clock: int):
    """Filter the pool to the species' value/direction; seeded pick."""
    v = _axis_value(node_axes, axis)
    if isinstance(v, (int, float)):
        med, _ = stats.get(axis, (0.0, 1.0))
        side = "high" if v > med else "low"
        cand = [e for e in entries if e.get("direction") == side]
    else:
        cand = [e for e in entries if e.get("value") == str(v)]
    if not cand:
        return None
    return cand[stream.randrange(len(cand), clock)]


def _epithet(node_axes: dict, pack: ContentPack, gender: str,
             stats: dict, stream, skip: set[str],
             context: NameContext | None = None) -> str | None:
    """Salience-ordered epithet; *skip* holds epithets already taken in
    this genus (collision chain: descend the salience order). Context
    stems (geography/habitat-of-occurrence) join the pool only when the
    NameContext supplies their fact."""
    pools: dict[str, list] = {}
    for e in pack.stems["axis_stem"]:
        pools.setdefault(e["axis"], []).append(e)
    scored: list[tuple[float, str, object]] = []
    for axis, entries in pools.items():
        spec = pack.registry.axes.get(
            "diet_spectrum" if axis == "diet_dominant" else axis)
        weight = spec.salience if spec is not None else 0.3
        s = _salience(node_axes, axis, entries, stats, weight)
        if s > 0:
            scored.append((s, "axis", axis))
    if context:
        for cs in pack.stems.get("context_stem", []):
            if context.facts.get(cs["fact"]) == cs["value"]:
                scored.append((CONTEXT_SALIENCE, "stem", cs))
    scored.sort(key=lambda t: (-t[0], str(t[2])))
    for rank, (_, kind, payload) in enumerate(scored):
        if kind == "axis":
            stem = _pick_stem(pools[payload], node_axes, payload, stats,
                              stream.child("pick"), rank)
        else:
            stem = payload
        if stem is None:
            continue
        ep = _agree(stem["base"], stem["pattern"], gender)
        if ep not in skip:
            return ep
    return None


def _genus_stats(members: list, pools: list) -> dict:
    """Median/std (scalars) and modal (enums) over the genus's species."""
    import statistics
    stats: dict = {}
    for axis in pools:
        vals = [_axis_value(m.axes, axis) for m in members]
        vals = [v for v in vals if v is not None and v != "N/A"]
        if not vals:
            continue
        if isinstance(vals[0], (int, float)):
            stats[axis] = (statistics.median(vals),
                           statistics.pstdev(vals) if len(vals) > 1 else 0.0)
        else:
            stats[axis] = (max(set(vals), key=vals.count), None)
    return stats


def assign_names(tree: Tree, pack: ContentPack, seed: int,
                 context: NameContext | None = None,
                 round: int = 0) -> None:
    """One naming pass over the tree (round 0 = the blind build)."""
    context = context or NameContext()
    stream = naming_stage(seed, round)
    pin_by_label = {p["label"]: p for p in pack.pins}
    used: set[str] = set()

    # 1. pins commit their authored names
    for n in tree.nodes.values():
        pin = pin_by_label.get(n.label or "")
        if pin and pin.get("name"):
            nm = pin["name"]
            n.name.binomial = nm.get("binomial")
            n.name.folk = nm.get("folk")
            if nm.get("binomial"):
                used.add(nm["binomial"].split()[0])   # genus part reserved

    # 1b. kingdom/phylum/class: authored latin names (deterministic, no
    # seeding). Class from the plan's class_name; phylum capitalized from
    # the plans beneath it; kingdom from its frame flag.
    for n in tree.nodes.values():
        if n.name.binomial:
            continue
        if n.rank is Rank.KINGDOM:
            n.name.binomial = ("Animalia" if "animalia" in n.flags else
                               n.flags[0].capitalize() if n.flags else None)
        elif n.rank is Rank.CLASS and n.plan:
            plan = pack.registry.plans.get(n.plan)
            if plan and plan.class_name:
                n.name.binomial = plan.class_name
    for n in tree.nodes.values():
        if n.rank is Rank.PHYLUM and not n.name.binomial:
            for c in tree.children(n.path):
                plan = pack.registry.plans.get(c.plan or "")
                if plan and plan.phylum:
                    n.name.binomial = plan.phylum.capitalize()
                    break

    # 2. genera: composed names (seeded style mix) + clade names above
    genus_name: dict[str, tuple[str, str]] = {}   # path -> (name, gender)
    for n in tree.nodes.values():
        if n.rank is not Rank.GENUS:
            continue
        if n.name.binomial:
            genus_name[n.path] = (n.name.binomial, "m")
            continue
        name, gender = _compose_genus(stream.child(n.path), pack,
                                      n.plan or "", used)
        n.name.binomial = name
        used.add(name)
        genus_name[n.path] = (name, gender)

    # clade names: family = type-genus root + idae; order = + formes
    def _first_genus(path: str) -> str | None:
        for child in tree.children(path):
            if child.path in genus_name:
                return child.path
            g = _first_genus(child.path)
            if g:
                return g
        return None

    for n in tree.nodes.values():
        if n.rank in (Rank.FAMILY, Rank.ORDER) and not n.name.binomial:
            g = _first_genus(n.path)
            root = genus_name.get(g, (None,))[0] if g else None
            if root:
                stem = root
                for ending in ("us", "is", "a", "um", "e"):
                    if stem.lower().endswith(ending):
                        stem = stem[:-len(ending)]
                        break
                suffix = "idae" if n.rank is Rank.FAMILY else "formes"
                n.name.binomial = stem + suffix

    # 3. species epithets within each genus
    pools = sorted({e["axis"] for e in pack.stems["axis_stem"]})
    for gpath, (gname, gender) in genus_name.items():
        members = [n for n in tree.children(gpath)
                   if n.rank is Rank.SPECIES]
        unnamed = [m for m in members if not m.name.binomial]
        if not unnamed:
            continue
        stats = _genus_stats(members, pools)
        taken: set[str] = set()
        for m in members:
            if m.name.binomial and " " in m.name.binomial:
                taken.add(m.name.binomial.split()[-1])
        for m in unnamed:
            sstream = stream.child(m.path)
            ep = _epithet(m.axes, pack, gender, stats, sstream, taken,
                          context)
            if ep is None:
                # last resort (spec §3.3 rule 4): sid fragment, EXTENDED
                # until unique — even pathological twins must not collide.
                for n_chars in (4, 8, 12, 16):
                    ep = "sp" + m.sid[:n_chars]
                    if ep not in taken:
                        break
            m.name.binomial = f"{gname} {ep}"
            taken.add(ep)
