# Biosphere Addendum B1 — Within-Plan Morphometrics (Generation Knobs)

**Status:** v0.2 — 2026-07-27. Companion and amendment to the **Biosphere Vocabulary Proposal v1.0**; sits beside companion docs A (slots/parts) and the field-guide keying note. Nothing here contradicts v1.0; it fills the empty layer between **body plan** and **species**. v0.2 adds §13 (labile surface dials — ear posture, tail carriage, and ~28 more soft-tissue/secondary knobs) and §14 (curated mutation-coupling bindings).

## 1. Preamble

**Purpose.** A body plan ("quadruped tetrapod") plus slots gives you a blob with attachment points. It does not give you a *squirrel*. This addendum defines the missing layer: **within-plan morphometrics** — a small set of scalar/enum **knobs** per plan whose values make a generated organism *recognizable at a glance* as squirrel-grade, cat-grade, tuna-grade, whelk-grade. Knobs are proportions and ratios, not anatomy: every knob is an **axis** in the proposal's sense and must pay rent to consumers.

**What knobs are for.** Generation, not identification puzzles. Primary consumers: **[draw]** (later parametric illustration), **[name]** (epithet fodder: *longicauda*, *macrocephala*), **[tell]** (gossip/narration texture), **[stress]** (niche stress function reads morphology), **[drift]** (evolutionary forces move knob values). **[id]** keys may consult knobs but are not the justification for most of them. **[pop]** consumes a few (trophic silhouette counters).

**Deferral note.** The demo is text-based. **No geometry yet**: no spine paths, no joint coordinates, no mesh. Slots stay strings. Knobs are scalar proportions/ratios that feed words now and drawing later. Any knob whose only conceivable consumer is a renderer we don't have is kept only if [name]/[tell]/[stress] can already spend it.

**Preset model.** Named morphs are **hand-authored presets in TOML** — curated types, parametric z (P4). The pipeline:

```
plan  →  preset (hand-authored point in knob space)  →  drift envelope  →  species
```

This addendum supplies (a) the knob vocabulary those presets are points in, and (b) worked-example preset anchors per plan. Drift envelopes are per-knob variance bounds set at authoring time; species are perturbations inside the envelope, not new presets.

**Adopt-don't-invent.** Where a recognized scientific parameterization exists, we adopt it **verbatim** and say so. Confirmed adoptions:

| Domain | Scheme | Source |
|---|---|---|
| Tetrapod limbs | intermembral / brachial / crural indices; Mt:F; IFA (olecranon) | Howell 1944; Hildebrand 1985; Garland & Janis 1993 |
| Bird wings | aspect ratio, wing loading, hand-wing index (HWI); 4 wing classes | Sheard et al. 2020 (HWI); Savile 1957; AVONET / Tobias et al. 2022 |
| Bat wings | digit ratios LD3/FL, LD5/FL; uropatagium extent | standard chiropteran morphometrics |
| Fish | Lindsey body-form classes; SL/HL/predorsal conventions; BCF/MPF modes | Lindsey 1978; Sfakiotakis et al. 1999 |
| Shells | **Raup's model (W, D, T, S)** + ammonoid morphospace | Raup 1966; Raup 1967 |
| Cephalopods | mantle-length (ML) based indices | standard teuthological convention |

**Anti-creep rule (carried from v1.0).** Every knob below names ≥1 consumer in brackets. Approximate ranges stay approximate; presets are authored anchors, not measurements.

---

## 2. Quadruped tetrapod

**Adopted schemes.** Howell/Hildebrand limb indices and morphotype table (cursorial, scansorial, fossorial, saltatorial, graviportal, semiaquatic); Garland & Janis 1993 for Mt:F (metapodial:femur) cursoriality signal.

**Constraint couplings.** Olecranon index high ⇒ digs or stands, not leaps (IFA and saltatoriality anticorrelate). Mt:F >0.65 couples with unguligrade posture and parasagittal stance. Stance sprawl couples with trunk depth (sprawlers are wide, not deep).

**Knob table** (`knob — definition — bounds — [consumers]`):

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| intermembral_index | forelimb:hindlimb length ×100 | leapers 50–75; arboreal 75–85; terrestrial 85–100; orangutan-grade ~145 | [draw][stress][tell][name] |
| brachial_index | radius:humerus ×100 | cursors >100; fossorial <80 | [draw][stress][drift] |
| crural_index | tibia:femur ×100 | deer-grade 110–130; generalized lower | [draw][stress] |
| metapodial_proximal_ratio | metapodial:femur (Mt:F) | <0.38 noncursorial; 0.38–0.65 carnivoran-grade; >0.65 ungulate (horse ~0.9) | [stress][draw][drift] |
| olecranon_index | IFA: olecranon:ulna ×100 | generalized 20–35; diggers 40–60 | [stress][draw][tell] |
| limb_length_to_trunk | limb length : trunk length | 0.4 (mole) – 1.4 (deer) | [draw][tell][name] |
| trunk_elongation | trunk L : expected for mass | weasel-grade high; bear-grade low | [draw][stress][name] |
| trunk_depth_ratio | chest depth : trunk length | deep-chested cursor vs low slinker | [draw][tell] |
| neck_length_ratio | neck : head-body length (HBL) | 0.05–0.45 | [draw][tell][name] |
| head_size_ratio | head : HBL | 0.20–0.40 | [draw][tell][name] |
| snout_ratio | snout : skull (dolicho >0.5, brachy <0.35) | 0.2–0.6 | [draw][name][tell][stress] |
| ear_size_ratio | pinna : HBL | fennec ~0.25; arctic-fox-grade ~0.05 | [draw][name][tell][stress] |
| tail_length_ratio | tail : HBL | deer 0.1–0.15; squirrel 0.8–1.0; monkey 0.7–1.2 | [draw][name][tell][pop] |
| tail_taper | tip thickness : base thickness | tuft/prehensile variants | [draw][tell] |
| stance_sprawl | normalized stance width/shoulder height proxy | parasagittal 0.2–0.4; sprawling 0.8–1.2; humerus elevation 0–20° vs 70–90° | [draw][stress] |
| foot_posture | enum: plantigrade / digitigrade / unguligrade | unguligrade ⇒ metatarsus 30–45% of hindlimb | [draw][stress][tell][name] |

16 knobs: 15 scalars + 1 enum. Sits inside the ~5–20 scalar budget.

**Worked-example presets (hand-authored anchors).** Ratios as fractions of HBL unless noted.

| knob | squirrel | cat | weasel/otter | deer | bear | mole | rabbit | monkey |
|---|---|---|---|---|---|---|---|---|
| intermembral_index | 75 | 90 | 70 | 95 | 90 | 80 | 60 | 105 |
| brachial_index | 85 | 95 | 75 | 110 | 85 | 65 | 85 | 100 |
| crural_index | 95 | 100 | 85 | 120 | 90 | 70 | 105 | 90 |
| metapodial_proximal_ratio | 0.45 | 0.55 | 0.35 | 0.80 | 0.40 | 0.25 | 0.50 | 0.45 |
| olecranon_index | 30 | 25 | 35 | 22 | 38 | 55 | 28 | 28 |
| limb_length_to_trunk | 0.7 | 0.9 | 0.5 | 1.3 | 0.8 | 0.4 | 0.9 | 1.0 |
| trunk_elongation | 0.9 | 1.0 | 1.6 | 0.9 | 1.1 | 1.2 | 0.9 | 0.8 |
| neck_length_ratio | 0.15 | 0.20 | 0.12 | 0.40 | 0.15 | 0.05 | 0.15 | 0.08 |
| head_size_ratio | 0.25 | 0.28 | 0.25 | 0.30 | 0.30 | 0.30 | 0.28 | 0.30 |
| snout_ratio | 0.40 | 0.30 | 0.35 | 0.52 | 0.45 | 0.50 | 0.35 | 0.25 |
| ear_size_ratio | 0.06 | 0.08 | 0.04 | 0.12 | 0.05 | 0.01 | 0.20 | 0.05 |
| tail_length_ratio | 0.90 | 0.60 | 0.40 | 0.12 | 0.08 | 0.10 | 0.06 | 0.90 |
| stance_sprawl | 0.4 | 0.3 | 0.5 | 0.25 | 0.4 | 0.9 | 0.35 | 0.4 |
| foot_posture | plantigrade | digitigrade | plantigrade | unguligrade | plantigrade | plantigrade | digitigrade | plantigrade |

Values are author-set anchors inside the published ranges above, not measurements; tune at authoring time.

---

## 3. Winged biped (bird-grade; bat variant)

**Adopted schemes.** Savile 1957 four wing classes; Sheard et al. 2020 hand-wing index (HWI); AVONET / Tobias et al. 2022 trait set (11 traits) as the measurement vocabulary; standard bat digit-ratio morphometrics for the variant.

**Constraint couplings.** **Wing loading ↔ flight-style legality**: sustained flapping flight becomes implausible above ~25 kg/m²; hovering requires low loading. Slot count >0 only legal on slotted high-lift class. High AR couples to low slot count; elliptical wings couple to high slot count and low HWI. Penguin-grade (flightless) nulls wing knobs — flight_style is the gate.

**Knob table:**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| body_mass | kg (drives loading, pop counters) | 0.002 (hummingbird) – 16+ | [stress][pop][draw] |
| aspect_ratio | wingspan²/area | albatross 13–15.4; condor 5.7; ducks 7–8; elliptical 4–5; high-AR class 8–18 | [draw][stress][name] |
| wing_loading | weight/wing area | living birds 1–20 kg/m² (duck 90–120 N/m²); legality limit ~25 kg/m² | [stress][tell][draw] |
| hand_wing_index | HWI (Kipp's-distance-based) | 0.016 (rhea) – 74.8 (hermit hummingbird); passerines 15–30; swifts/albatross 45–75 | [stress][drift][draw] |
| hand_wing_fraction | hand-wing : total wing length | low in soarers, high in migrants | [draw][stress] |
| slot_count | emarginated primary slots | 0–6 | [draw][tell] |
| slot_depth | slot depth : chord | 0–0.3 | [draw] |
| neck_fraction | neck : body-core length | owl ~0.20; heron 0.45–0.55 | [draw][tell][name] |
| head_fraction | head : body-core | 0.15–0.35 | [draw][tell] |
| tarsus_fraction | tarsus : body-core | percher 0.11–0.15; heron 0.4–0.5; penguin ~0.06 | [draw][stress][name] |
| leg_setback | leg attachment position on core | rear-set (penguin/loon-grade) vs central | [draw][stress][tell] |
| tail_length_ratio | tail : body-core | 0.2–1.0 | [draw][name] |
| tail_shape + fork_depth | enum 7 classes (square, rounded, pointed, graduated, forked, deeply forked, lyre/streamer) + scalar | fork depth 0–0.5 tail length | [draw][tell][name] |
| beak_length_ratio | beak : head length | hawking 0.15–0.3; seed 0.5–0.7; probing 1.0–2.5 | [draw][name][stress][tell] |
| beak_depth_ratio | depth : length | seed-crusher 0.6–1.0; probe 0.05–0.15 | [draw][stress][name] |
| beak_hook / beak_width | hooked flag + width scalar | raptor-grade hooked; duck-grade wide | [draw][tell][stress] |
| flight_style | enum 5: sustained-flapping, bounding, soaring, hovering, flightless | must satisfy loading/AR legality | [stress][tell][pop] |

**Bat variant:** swap knobs 4–6 (HWI, hand_wing_fraction, slots) for:

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| LD3/FL | digit III length : forearm | insect-hawker low; gleaner high | [draw][stress] |
| LD5/FL | digit V length : forearm | wingtip shape control | [draw] |
| uropatagium_extent | tail membrane : leg span | 0 (free-tail-grade) – 1.0 | [draw][tell][name] |

Bird set: 17 knobs (15 scalars + 2 enums). Bat: 16.

**Worked-example presets:**

| knob | sparrow | crow | owl | heron | duck | eagle | hummingbird | penguin |
|---|---|---|---|---|---|---|---|---|
| aspect_ratio | 5.0 | 6.0 | 6.5 | 7.5 | 7.5 | 7.0 | 8.0 | — (flipper) |
| wing_loading (kg/m²) | 2.5 | 5 | 3 | 6 | 11 | 6 | 0.8 | — |
| hand_wing_index | 20 | 30 | 15 | 30 | 35 | 25 | 60 | 0.5 |
| slot_count | 0 | 4 | 3 | 1 | 0 | 5 | 0 | 0 |
| neck_fraction | 0.25 | 0.25 | 0.20 | 0.50 | 0.30 | 0.25 | 0.15 | 0.30 |
| tarsus_fraction | 0.13 | 0.15 | 0.15 | 0.45 | 0.12 | 0.18 | 0.08 | 0.06 |
| leg_setback | central | central | central | central | rear | central | central | rear |
| tail_shape | rounded | fan/square | rounded | short square | pointed | wedge | forked | stub |
| beak_length_ratio | 0.4 | 0.5 | 0.3 | 1.2 | 0.8 | 0.4 | 1.5 | 0.5 |
| beak_depth_ratio | 0.7 | 0.4 | 0.5 (hooked) | 0.15 | 0.3 (wide) | 0.6 (hooked) | 0.08 | 0.3 |
| flight_style | bounding | sustained-flapping | sustained-flapping | sustained-flapping | sustained-flapping | soaring | hovering | flightless |
| Savile class | elliptical | slotted high-lift | slotted high-lift | high-lift | high-speed | slotted high-lift | high-speed | — |

---

## 4. Finned (fish-grade)

**Adopted schemes.** Lindsey 1978 body-form classes with their ratios; standard ichthyological measurement conventions (SL/TL/FL, HL, predorsal/preanal); Sfakiotakis et al. 1999 BCF/MPF swimming-mode classification verbatim.

**Conventions.** SL ≈ 0.80–0.90 TL. HL/SL 0.20–0.35. Eye 15–35% HL.

**Constraint couplings.** **Peduncle depth ↔ caudal AR anticorrelate with body depth**: deep compressiform bodies pair with low-AR tails (no thunniform pancake). Anguilliform body ⇒ continuous/reduced fins (dorsal_fin_base long, paired fins optional). Globiform ⇒ ostraciform/tetraodontiform modes only; thunniform requires fusiform + lunate tail. Depressiform + rajiform couple (pectoral 0.4–0.9 SL).

**Knob table** (16 scalars + 3 enums; all lengths as fractions of SL unless noted):

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| body_depth/SL | max depth : SL | fusiform 0.18–0.28; compressiform 0.30–0.70; depressiform 0.05–0.20; anguilliform 0.03–0.06; globiform 0.5–0.9 | [draw][stress][name] |
| body_width/depth | width : depth | fusiform 0.7–1.0; compressiform 0.15–0.35; depressiform 3–10+; globiform ~1 | [draw][name] |
| max_depth_position | position of max depth along SL | 0.25 (anterior) – 0.6 | [draw] |
| caudal_peduncle_depth/SL | peduncle depth : SL | thunniform low + keels; maneuverers deep | [draw][stress] |
| head_length/SL | HL : SL | 0.20–0.35 | [draw][name] |
| snout_length/HL | snout : HL | 0.2–0.5 (gar-grade higher) | [draw][name][tell] |
| eye_diameter/HL | eye : HL | 0.15–0.35 | [draw][tell][name] |
| predorsal/SL | snout→dorsal origin : SL | cruisers 0.30–0.40; pikes/eels 0.6–0.9 | [draw][stress] |
| preanal/SL | snout→anus : SL | 0.5–0.75; eel-grade higher | [draw] |
| dorsal_fin_height/SL | height : SL | sail-grade high; cruiser low | [draw][tell][name] |
| dorsal_fin_base/SL | base : SL | continuous (eel) – short | [draw] |
| anal_fin_base/SL | base : SL | gymnotiform long; standard short | [draw] |
| pectoral_fin_length/SL | pectoral : SL | 0.10 (BCF cruisers) – 0.4–0.9 (ray wings) | [draw][stress][name] |
| caudal_span/SL or AR | tail spread / aspect ratio | lunate AR 4–8; forked 3–5; rounded <2; heterocercal flag | [draw][stress][name] |
| mouth_gape/HL | gape : HL | 0.15–1.0+ | [draw][stress][tell] |
| mouth_protrusion | protrusibility : HL | 0 – 0.65 (slingjaw-grade) | [draw][stress][tell] |
| caudal_class | enum: heterocercal / homocercal / lunate / forked / rounded / continuous | Lindsey classes | [draw][name][id] |
| mouth_position | enum: terminal / subterminal / superior | feeding-guild signal | [stress][tell][name] |
| dorsal_config | enum: single / divided / continuous / spiny+soft | fin arrangement | [draw][id] |

**Worked-example presets:**

| knob | perch | eel | tuna | flounder | shark | seahorse | ray | puffer |
|---|---|---|---|---|---|---|---|---|
| body_depth/SL | 0.25 | 0.04 | 0.25 | 0.55 | 0.15 | 0.10 | 0.08 | 0.7 |
| body_width/depth | 0.35 | 0.9 | 0.8 | 0.3 | 0.9 | 0.5 | 8 | 0.9 |
| predorsal/SL | 0.38 | 0.65 | 0.35 | 0.35 | 0.45 | 0.30 | 0.50 | 0.55 |
| pectoral_fin_length/SL | 0.15 | 0.05 | 0.15 | 0.10 | 0.20 | 0.05 | 0.80 | 0.12 |
| caudal class/AR | forked 3.5 | continuous | lunate 7 | rounded 1.5 | heterocercal | none/prehensile | reduced | rounded 1.5 |
| mouth_position | terminal | terminal | terminal | twisted/asym. | subterminal | superior (tube) | subterminal | terminal |
| mouth_protrusion | 0.25 | 0.05 | 0.10 | 0.15 | 0.20 | 0.05 | 0.10 | 0.15 |
| swimming mode | carangiform | anguilliform | thunniform | MPF (fin waves) | subcarangiform | MPF (dorsal) | rajiform | tetraodontiform |
| body-form class | fusiform | anguilliform | fusiform | compressiform (flat) | fusiform/depressiform | elongate | depressiform | globiform |

---

## 5. Hexapod (insect-grade)

**Adopted schemes.** Standard tagmata proportions (head/thorax/abdomen fractions of BL); antenna, leg, wing ratios to body length — no single canonical index set exists, so ratios-to-BL is the convention.

**Knob table (10):**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| head_fraction | head : BL | 0.08–0.20 | [draw][name] |
| thorax_fraction | thorax : BL | 0.20–0.35 | [draw] |
| abdomen_fraction | abdomen : BL | 0.45–0.70 | [draw] |
| antenna_length | antenna : BL | 0.05 (fly-grade) – 1.5 (longhorn-grade) | [draw][name][tell] |
| antenna_form | enum: filiform / clubbed / feathery / elbowed | butterfly clubbed; moth feathery; ant elbowed | [draw][tell][name] |
| hindleg_ratio | hindleg : midleg length | 1.0–1.3+ (grasshopper jumper) | [draw][stress][tell] |
| wing_span_ratio | wingspan : BL | 0 (apterous) – 4 | [draw][stress][name] |
| wing_count | enum: 0 / 2 / 4 (+ elytra flag) | beetle elytra; fly halteres | [draw][tell][stress] |
| waist_constriction | petiole width : thorax width | ant-grade 0.2–0.4; none ~1.0 | [draw][tell][name] |
| abdomen_taper | tip : base width | wasp-waist vs blunt | [draw][tell] |

**Worked-example presets:**

| knob | ant | butterfly | beetle | dragonfly | grasshopper | bee |
|---|---|---|---|---|---|---|
| head_fraction | 0.18 | 0.10 | 0.15 | 0.15 | 0.15 | 0.15 |
| thorax_fraction | 0.22 | 0.25 | 0.30 | 0.30 | 0.30 | 0.30 |
| abdomen_fraction | 0.60 | 0.65 | 0.55 | 0.55 | 0.55 | 0.55 |
| antenna_length | 0.5 (elbowed) | 0.6 (clubbed) | 0.4 | 0.05 | 0.8 | 0.4 |
| hindleg_ratio | 1.0 | 1.0 | 1.0 | 1.0 | 1.3 | 1.1 |
| wing_span_ratio | 0 (worker) | 3.0 | 1.5 (elytra) | 3.5 | 2.5 | 2.0 |
| wing_count | 0 | 4 | 4+elytra | 4 | 4 | 4 |
| waist_constriction | 0.3 | 0.8 | 1.0 | 0.9 | 0.9 | 0.5 |

---

## 6. Arachnid-grade (spiders, scorpions, harvestmen)

**Knob table (9):**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| cephalothorax_fraction | prosoma : body length | 0.30–0.45 | [draw] |
| leg_span_ratio | leg span : body length | 2 (crab spider) – 15+ (harvestman extreme) | [draw][name][tell] |
| leg_thickness | femur L:D | 4 (tarantula-grade heavy) – 50 (daddy-long-legs) | [draw][tell] |
| leg_order_emphasis | which leg pair dominates | crab spider: front; wolf: rear-drive | [draw][tell] |
| pedipalp_ratio | pedipalp : body length | scorpion chelate large | [draw][name][tell] |
| chela_ratio | claw : body length | scorpion 0.2–0.5 | [draw][stress][name] |
| tail_ratio | metasoma : body length | scorpion 0.8–1.2; others 0 | [draw][tell][name] |
| laterigrade | enum flag: crab-sideways legs | crab spider | [draw][tell] |
| eye_shine / pattern class | enum coarse pattern | wolf vs orb | [tell][name] |

**Constraint coupling.** **Scorpion claw-size ↔ tail-venom anticorrelation**: heavy chelae pair with slender low-venom tails; slender chelae with thick potent tails. Author presets on the tradeoff line, not off it.

**Worked-example presets:**

| knob | orb spider | wolf spider | tarantula | crab spider | harvestman | scorpion |
|---|---|---|---|---|---|---|
| cephalothorax_fraction | 0.35 | 0.40 | 0.40 | 0.40 | fused ~0.5 (oval) | 0.35 |
| leg_span_ratio | 4 | 3 | 4 | 2.5 | 12 | 3 |
| leg_thickness (L:D) | 25 | 12 | 6 | 15 | 45 | 12 |
| pedipalp_ratio | 0.3 | 0.3 | 0.4 | 0.3 | 0.4 | 0.9 (chelate) |
| chela_ratio | 0 | 0 | 0 | 0 | 0 | 0.35 |
| tail_ratio | 0 | 0 | 0 | 0 | 0 | 1.0 |
| laterigrade | no | no | no | yes | no | no |

---

## 7. Shell (gastropod / bivalve / ammonite — Raup)

**Adopted scheme.** **Raup 1966 shell model, verbatim — gold-flagged.** Four parameters generate essentially all coiled-shell morphospace; do not invent alternatives.

| Raup param | definition | range | note |
|---|---|---|---|
| W | whorl expansion rate | 1–10⁶ (log) | r_θ = r₀ · W^(θ/2π) |
| D | umbilicus distance (whorl overlap) | 0–1 | 0 = involute, high = evolute |
| T | translation rate (coiling axis) | 0–4 | T=0 ⇒ planispiral |
| S | aperture W:H | 0.3–3 | aperture shape |

**Gastropod knob table (Raup 4 + 2 = 6):** W, D, T, S as above + `whorl_count` (3–8) [draw][tell] + `ornament_class` (enum: smooth / ribbed / spired-spines / nodose) [draw][tell][name].

**Worked Raup anchors:**

| morph | W | D | T | S |
|---|---|---|---|---|
| garden snail | 2–3 | 0.1–0.2 | 0.3–0.6 | ~1 |
| conch/whelk-grade | 1.5–2 | ~0 | 1–2 | ~0.6 |
| limpet | 10²–10⁶ | 0 | ~0 (cap) | — |
| Nautilus (planispiral) | ~3 | low | 0 | ~1 |

**Ammonite/ammonoid morphospace (adopted verbatim):** knobs `W`, `U` (umbilical ratio), `WW/WH` (whorl width:height). Named morphotypes: **serpenticone** (evolute, thin), **oxycone** (involute, compressed, keeled), **spherocone** (globular), **platycone** (intermediate flat). Enum `ammonoid_morphotype` + `suture_complexity` (goniatitic → ammonitic) [tell][name][id].

**Bivalve knob table (5):**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| length_height_ratio | shell L:H | 0.6 (scallop) – 3+ (mussel/razor) | [draw][name] |
| inflation | thickness : length | 0.3–0.9 | [draw][stress] |
| umbo_position | umbo along hinge 0–1 | 0 central (scallop) – 1 terminal (mussel) | [draw][name] |
| valve_asymmetry | enum: equivalve / inequivalve (oyster-grade) | — | [draw][tell][stress] |
| ornament_class | enum: smooth / concentric / radial ribs / spiny | scallop radial; oyster rough | [draw][tell][name] |

---

## 8. Cephalopod

**Adopted scheme.** ML (mantle length) based indices — standard teuthological convention.

**Knob table (7):**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| mantle_LW | mantle L:W | octopus sac ~0.7–1.0 (by width); squid 4–6 (by length) | [draw][name] |
| arm_length_ML | arms : ML | octopus 3–6; squid 0.5–0.9 | [draw][tell][name] |
| tentacle_ratio | feeding tentacles : ML | 0 (octopus) – 1–2 (squid) | [draw][tell] |
| arm_count | 8 / 8+2 | octopus vs squid/cuttlefish | [draw][id][tell] |
| fin_ratio | fin length : ML | cuttlefish ~1.0 (full margin); squid ~0.4; octopus 0 | [draw][stress][name] |
| fin_position | enum: marginal / terminal / absent | — | [draw] |
| shell_state | enum: external (nautilus) / internal (cuttlebone, pen) / absent | couples to Raup knobs if external | [tell][stress][draw] |

**Worked-example presets:**

| knob | octopus | squid | cuttlefish | nautilus |
|---|---|---|---|---|
| mantle_LW | 0.9 (sac) | 5 (torpedo) | 2 (broad) | external shell (see §7) |
| arm_length_ML | 4 | 0.7 | 1.0 | 2 (many cirri) |
| tentacle_ratio | 0 | 1.5 | 1.2 | 0 |
| arm_count | 8 | 8+2 | 8+2 | many |
| fin_ratio | 0 | 0.4 | 1.0 | 0 |
| shell_state | absent | pen | cuttlebone | external (T=0 Raup) |

---

## 9. Decapod (crab/lobster/shrimp-grade)

**Knob table (7):**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| carapace_WL | carapace width : length | crab 1.2–1.6; lobster 0.4; shrimp 0.3 | [draw][name] |
| carapace_dome | height : width | fiddler dome vs flat swimming crab | [draw][tell] |
| cheliped_ratio | cheliped : carapace length | fiddler extreme; lobster heavy | [draw][stress][name][tell] |
| cheliped_asymmetry | major : minor claw | 1.0 – fiddler-grade (major = 30–65% body mass) | [draw][tell][name] |
| abdomen_state | enum: extended (lobster/shrimp) / folded (crab) | carcinization flag | [draw][tell] |
| leg_specialization | enum: walking / swimmerets+paddle (swimming crab) / digging | — | [draw][stress] |
| rostrum_ratio | rostrum : carapace length | shrimp long-serrated; crab ~0 | [draw][name] |

Anchors: crab W:L 1.4, folded abdomen, no rostrum; lobster 0.4, extended, heavy symmetric chelae; shrimp 0.3, extended, rostrum 0.5; fiddler crab 1.3, asymmetry extreme.

---

## 10. Myriapod

**Knob table (5):**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| segment_count | trunk segments | centipede 15–191 (always odd leg-pair count); millipede diplosegments to ~750 legs | [draw][tell][name] |
| leg_per_segment | enum: 1 (centipede) / 2 (millipede diplosegment) | — | [draw][id] |
| leg_length_ratio | leg : body width | centipede long-fast; millipede short | [draw][stress][tell] |
| body_section | enum: flattened (centipede) / cylindrical (millipede) | — | [draw][name] |
| terminal_pair | enum flag: elongated rear legs / forcipules emphasis | centipede yes | [draw][tell] |

---

## 11. Worm-grade

**Knob table (4):**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| length_diameter | L:D | 10:1 (stubby grub-grade) – 100:1 (earthworm-grade) | [draw][name] |
| segment_count | visible annuli | 100–200 (segmented) | [draw][tell] |
| segmentation_visible | enum: annulated / smooth | earthworm vs nematode-grade | [draw][tell] |
| taper_profile | enum: both-ends / posterior / none | — | [draw][tell] |

---

## 12. Soft-bodied pelagic (jellyfish-grade)

**Knob table (5):**

| knob | definition | bounds/range | consumers |
|---|---|---|---|
| bell_diameter_height | bell diameter : height | 0.8 (tall hydromedusa) – 3 (flat saucer) | [draw][name] |
| tentacle_diameter | tentacle : bell diameter | 0.5 – 30 (lion's-mane-grade) | [draw][tell][name] |
| tentacle_count_class | enum: 4 / 8 / many / marginal ring | — | [draw][tell] |
| oral_arm_ratio | oral arms : bell diameter | 0 – 1.5 | [draw][tell] |
| bell_margin | enum: smooth / scalloped / lappeted | — | [draw][name] |

---

## 13. Labile surface dials (soft-tissue, posture, secondary)

The locomotor literature that built §§2–12 is strong on construction-core and weak on
the soft-tissue, posture, and surface dials — the axes that vary fastest within clades,
read instantly at a glance, and carry the most [name]/[tell] value per scalar. This
section fills that gap. All dials here are **labile** (high drift variance, species-level
play); none are clade-steady. Established classifications are adopted where they exist.

### 13.1 Tetrapod additions (mammal-biased)

| knob | states/range | notes | consumers |
|---|---|---|---|
| ear_posture | erect / semi-erect / folded / pendant | wild bunny erect, domestic lop pendant; dog-breed spectrum. Domestication coupling (§14) pulls this | [draw][tell][name][drift] |
| tail_carriage | low / level / raised / curled / sickle | husky sickle, pig curl, tucked; domestication coupling pulls this | [draw][tell][name] |
| foot_webbing_grade | none / partial / full | otter vs weasel; reads "aquatic" instantly | [draw][stress][tell][name] |
| toe_count | int 1–5 per foot | rhino 3 vs tapir 4; horse 1 vs deer 2 | [draw][id][name] |
| claw_retractability | retractile / semi / fixed (adopted 3-state) | felid vs canid | [draw][stress][tell] |
| vibrissae_prominence | 0–1 | rat/walrus-grade "whiskery" | [draw][tell][name] |
| mane_ruff_extent | none / cheek ruff / mane / full × scalar | lion, maned wolf, markhor; "maned ___" | [draw][name][tell][runaway] |
| dewlap_jowl_flesh | 0–1 | zebu dewlap, moose bell, basset flews | [draw][tell][name] |
| skin_wrinkle_looseness | 0–1 | shar-pei-grade, elephant, rhino | [draw][tell] |
| fat_depot | none / single hump / double hump / nuchal hump / fat tail / fat rump | camel 1-vs-2 hump is within-genus variation; fat-tailed sheep; "humpback"/"fat-tailed" naming gold | [draw][name][tell][stress] |
| horn_cover_texture | bare keratin / velvet / shed × smooth / ridged | separates horn from antler; ribbed antelope sheaths | [draw][tell][name] |
| pupil_shape | round / vertical slit / horizontal slit / W / crescent (adopted taxonomy) | cat vertical, goat/horse horizontal, cuttlefish W; cross-plan enum shared with cephalopods | [draw][tell][name][id] |
| stance_profile | scalar (merges head carriage + belly clearance) | high-set vs low-slung dachshund-grade | [draw][tell] |
| tail_flag_rump_patch | none / dark tip / white flag / tuft × rump patch none/heart/round | whitetail flag, roe heart patch; signal-marking enum | [draw][tell][name][id] |
| proboscis_grade | none / short (tapir) / full trunk (scalar) | elephant, tapir, saiga, elephant-shrew | [draw][tell][name] |

### 13.2 Winged-biped additions

| knob | states/range | notes | consumers |
|---|---|---|---|
| toe_arrangement | anisodactyl / zygodactyl / heterodactyl / syndactyl / pamprodactyl (adopted 5-state) | percher vs climber vs kingfisher; encodes lifestyle | [draw][stress][id][name] |
| foot_webbing_grade | none / semipalmate / palmate / totipalmate / lobate (adopted series) | duck vs pelican vs grebe | [draw][stress][tell][name] |
| crest | none / fixed / erectile × scalar size | cockatoo erectile, cardinal fixed, hoopoe fan; "crested ___" | [draw][name][tell][runaway] |
| comb_type | none / single / rose / pea / V / duplex (adopted poultry classification) | galliform reads | [draw][tell][name] |
| wattle_snood | scalar ×2 | turkey snood varies within species | [draw][tell][name] |
| cere_bareface | scalar bare-skin extent around bill/eye | parrot cere, vulture bare face, macaw patch | [draw][tell][name] |
| leg_feathering | bare / partial / booted | golden vs bald eagle field mark; ptarmigan | [draw][tell][name] |
| tarsal_spur | none / single / multiple | rooster, spurfowl | [draw][tell][stress] |
| throat_pouch | none / pouch / inflatable | pelican pouch, frigatebird balloon | [draw][tell][name] |
| head_casque | none / keratin casque / bony knob | cassowary, hornbill | [draw][tell][name] |
| facial_disc | none / partial / full | owl-defining | [draw][tell][name] |

Tail streamers/wires/racquets are a **modifier flag on the existing tail_shape enum**, not a new enum.

### 13.3 Herp additions

| knob | states/range | notes | consumers |
|---|---|---|---|
| throat_fan_dewlap | none / small / large extensible fan | anole-defining | [draw][tell][name] |
| dorsal_crest_spines | none / nuchal / dorsal crest / sail | iguana, basilisk, sailfin; big silhouette | [draw][tell][name] |
| vocal_sac | none / median / paired (adopted 3-state) | calling frogs | [draw][tell][name] |
| parotoid_glands | 0–1 | toad vs frog distinction | [draw][tell][stress] |
| neck_frill | bool (erectile) | frilled lizard; rare but iconic, near-free | [draw][tell][name] |
| skin_texture | smooth-moist / granular / warty / keeled | toad "warty", snake keels | [draw][tell][name] |

### 13.4 Fish additions

| knob | states/range | notes | consumers |
|---|---|---|---|
| barbels | count 0/1/2/4/6/8 × length × placement (nasal/maxillary/mandibular — adopted nomenclature) | instant "catfish" | [draw][tell][name][id] |
| adipose_fin | bool × size | standard dichotomous-key trait; salmonids, many catfish | [draw][id][name] |
| skin_type | cycloid / ctenoid / naked / denticle / scute / bony plate | shark denticles, sturgeon scutes (fixed 5 rows), seahorse armor | [draw][tell][name] |
| dorsal_sail_height | 0–1 | sailfish, grayling — the sail IS the name | [draw][tell][name] |
| pelvic_fin_modification | normal / fused suction disc / head disc / absent | goby, lumpsucker, remora | [draw][tell][stress][name] |
| fin_spines | count × lockable bool × venom_channel bool | perch spines, catfish locks, lionfish venom | [draw][stress][tell][id] |
| peduncle_keels_finlets | keel count 0–2 × finlet count 0–9 | tuna fast-swimmer tell | [draw][stress][name] |
| tail_filaments | bool × length | threadfin drama | [draw][tell][name] |
| lip_thickness | 0–1 | wrasse, carp suckermouth | [draw][tell] |
| breeding_male_flags | nuchal hump / kype / tubercles (seasonal toggles) | salmon kype, minnow pearls | [draw][tell][pop] |

### 13.5 Cephalopod / arthropod / shell additions

| knob | plan | states/range | notes | consumers |
|---|---|---|---|---|
| arm_webbing_depth | cephalopod | 0–1 | free octopus arms → dumbo umbrella | [draw][tell][name] |
| skin_papillae_density | cephalopod | 0–1 | mimic-octopus texture morph | [draw][tell] |
| mantle_flanges | cephalopod | bool × extent | flamboyant cuttlefish | [draw][tell][name] |
| horn_mandible_exaggeration | arthropod | scalar × curvature × bifurcation × **sexual-dimorphism flag** | rhino beetle horns, stag beetle mandibles; the single most recognizable beetle trait | [draw][tell][name][runaway] |
| cerci_type | arthropod | none / filaments / forceps | earwig pincers (male curved / female straight dimorphism is textbook) | [draw][tell][name] |
| pronotum_extension | arthropod | none / horn / helmet / thorn / bifurcating × height | treehoppers (~3,500 species); formal landmark homology scheme exists (humeral angle, median carina, posterior apex) — adopt | [draw][tell][name] |
| eye_stalks | arthropod | scalar × dimorphism flag | stalk-eyed flies | [draw][tell][name] |
| swimming_leg_fringe | arthropod | bool × density | water-beetle oar legs | [draw][stress] |
| elytra_sculpture | arthropod | smooth / striate / punctate / tuberculate | carabid striae standard | [draw][tell][id] |
| siphonal_canal_length | shell | 0–1 (notch → long closed tube) | murex; **orthogonal to Raup W/D/T — safe addition** | [draw][tell][name] |
| varix_spines | shell | varix count (classic 3/whorl) × spine elaboration | murex spikes; axial ornament, outside Raup | [draw][tell][name] |
| periostracum_texture | shell | smooth / hairy / bristly / frondose | "hairy shell" surprise | [draw][tell][name] |
| marginal_lappets_rhopalia | jellyfish | lappet count (8/16/24) × rhopalia prominence | bell-edge silhouette | [draw][tell][name] |

Cross-plan reuse note: webbing, dewlap flesh, casque, dorsal crest, and pupil shape
share one schema across plans with plan-appropriate ranges — ~30 unique channels
cover all of §13.

## 14. Mutation-coupling bindings (curated rules)

Stated as biological rules, not wiring. Each entry: directional coupling, documented
scope, strength rating. SEMI-UNIVERSAL = documented across many independent clades;
CLADE-SCOPED = real but narrow; CONTESTED = pattern robust, mechanism disputed.
Anything weaker than these is omitted (expensive-tissue brain↔gut, armor↔speed,
strict handicap/runaway cost — all failed review).

| # | rule (directional) | scope | rating |
|---|---|---|---|
| 1 | tameness↑ ⇒ pigmentation loss (piebald)↑, ear_posture → pendant, snout↓, relative brain↓ (10–30%), adrenal output↓, tail_carriage → curled — the **domestication package** (§13.1 dials are its targets) | mammals (~15+ species), weaker birds/fish | SEMI-UNIVERSAL (mechanism debated) |
| 2 | offspring size↑ ⇒ offspring number↓ (≈inverse proportionality, allocation-corrected) | mammals, insects, plants, marine inverts | SEMI-UNIVERSAL |
| 3 | maturation age↑ ⇒ lifespan↑, fecundity↓, growth↓ — the fast–slow life-history axis; strongest cross-vertebrate covariance known | vertebrates | SEMI-UNIVERSAL |
| 4 | flight use↓ ⇒ pectoral mass↓ (~20–25% body-mass savings), keel depth↓ (deterministic allometry), wings↓, hindlimb mass↑, BMR↓, often body size↑ — the **island flightlessness package**, >1,000 independent replicates (rails ≥17) | birds | SEMI-UNIVERSAL |
| 5 | body size × lifespan↑ ⇒ cancer-suppression investment↑; suppression↑ ⇒ regenerative capacity↓ / aging↑ | vertebrates (convergent solutions per clade) | SEMI-UNIVERSAL |
| 6 | investment in sensory modality A↑ ⇒ modality B neural representation↓ (cavefish eyes↔lateral line co-map to linked loci; bats; subterranean mammals) — one modality's gain rides another's loss | vertebrates | SEMI-UNIVERSAL |
| 7 | eumelanism↑ ⇒ aggression↑, stress-reactivity↓ (sex-dependent immunity shifts); melanin↓ (albinism) ⇒ visual acuity↓ ⇒ survival/foraging↓ | 40+ wild vertebrate species | SEMI-UNIVERSAL pattern, CONTESTED mechanism (albinism cost: solid) |
| 8 | ornament size↑ ⇒ production/maintenance cost↑, expression becomes condition-dependent (small in low-condition individuals). NOTE: strict handicap/runaway-cost form refuted (peacock trains don't measurably handicap flight) — keep cost-coupling, drop runaway-cost claims | birds, ungulates | SEMI-UNIVERSAL (weakened form) |

Rejected candidates, for the record: expensive tissue brain↔gut (fails mammal-wide,
bird, bat tests); armor↔speed (contradicted in armored fish; solid only in turtles);
venom production cost (real but small — ~10–20% transient metabolic elevation, snake
data only; venom's real economy is behavioral metering, not a tradeoff axis).

Beyond the curated table: a few **weak couplings between arbitrary axis pairs** per
lineage give each clade idiosyncratic texture (flavor only; the curated rules are the
ones worth learning — they're real natural history).

## 15. Knob count per plan (summary)

| plan | scalars | enums | total |
|---|---|---|---|
| quadruped tetrapod | 15 | 1 | 16 |
| winged biped (bird) | 15 | 2 | 17 |
| winged biped (bat variant) | 14 | 2 | 16 |
| finned (fish) | 16 | 3 | 19 |
| hexapod | 8 | 2 | 10 |
| arachnid | 7 | 2 | 9 |
| shell — gastropod | 5 | 1 | 6 |
| shell — bivalve | 4 | 1 | 5 |
| cephalopod | 5 | 2 | 7 |
| decapod | 4 | 3 | 7 |
| myriapod | 2 | 3 | 5 |
| worm-grade | 2 | 2 | 4 |
| soft-bodied pelagic | 2 | 3 | 5 |

§13 adds **labile surface dials** on top: tetrapod +15, winged biped +11 (+1 modifier),
herp +6, fish +10, cephalopod +3, arthropod +6, shell +3, jellyfish +1 — ~30 unique
channels after cross-plan sharing. Core knobs stay at **~5–20 per plan** (if a plan
needs more, it is two plans wearing a trench coat; split it); labile dials are allowed
to accumulate, because biology is high-dimensional and their rent is cheap — one
[tell] or [name] hit justifies a dial.

---

## 16. Authoring schema (TOML, per proposal §11)

```toml
# presets/tetrapod/squirrel.toml — one preset record
[preset]
id        = "tetrapod.squirrel"
plan      = "quadruped_tetrapod"
grade     = "squirrel"          # curated type, parametric z (P4)
status    = "hand-authored"
source    = "addendum-B1 §2 table"

[knobs]                          # point in knob space
intermembral_index         = 75
brachial_index             = 85
crural_index               = 95
metapodial_proximal_ratio  = 0.45
olecranon_index            = 30
limb_length_to_trunk       = 0.7
trunk_elongation           = 0.9
trunk_depth_ratio          = 0.8
neck_length_ratio          = 0.15
head_size_ratio            = 0.25
snout_ratio                = 0.40
ear_size_ratio             = 0.06
tail_length_ratio          = 0.90
tail_taper                 = 0.6
stance_sprawl              = 0.4
foot_posture               = "plantigrade"

[drift_envelope]                 # species = preset + perturbation inside envelope
intermembral_index         = { sigma = 5,   min = 60, max = 85 }
tail_length_ratio          = { sigma = 0.1, min = 0.6, max = 1.1 }
ear_size_ratio             = { sigma = 0.02, min = 0.02, max = 0.15 }
snout_ratio                = { sigma = 0.05, min = 0.3, max = 0.5 }
# unlisted knobs: fixed at preset value this z-level

[consumers.note]
draw   = "proportions only; geometry deferred"
name   = "epithet candidates: longicauda, bushy-tail"
stress = "scansorial niche reads IMI + foot_posture"
```

---

## 17. Provenance

Four research domains fed this addendum:

| domain | scope | key sources |
|---|---|---|
| A. Quadruped tetrapods | limb indices, posture, axial ratios, 8-morph table | Howell, *Speed in Animals* (1944); Hildebrand, "Walking and Running" (1985); Garland & Janis, "Does metatarsal/femur ratio predict maximal running speed in cursorial mammals?" *J. Zool.* 229 (1993) — https://doi.org/10.1111/j.1469-7998.1993.tb02626.x |
| B. Winged bipeds | wing classes, HWI, AVONET, bat digits | Savile, "Adaptive evolution in the avian wing," *Evolution* 11 (1957) — https://doi.org/10.2307/2406040; Sheard et al., "Ecological drivers of global gradients in avian dispersal inferred from wing morphology," *Nat. Commun.* 11 (2020) — https://doi.org/10.1038/s41467-020-16313-6; Tobias et al., "AVONET: morphological, ecological and geographical data for all birds," *Ecol. Lett.* 25 (2022) — https://doi.org/10.1111/ele.13898 |
| C. Fish | body-form classes, measurement conventions, swimming modes | Lindsey, "Form, function, and locomotory habits in fish," in *Fish Physiology* 7 (1978); Sfakiotakis, Lane & Davies, "Review of fish swimming modes for aquatic locomotion," *IEEE J. Oceanic Eng.* 24 (1999) — https://doi.org/10.1109/48.757275 |
| D. Invertebrates | Raup shell model, ammonoid morphospace, arthropod ratios, cephalopod ML indices | Raup, "Geometric analysis of shell coiling: general problems," *J. Paleontol.* 40 (1966) — https://www.jstor.org/stable/1301764; Raup, "Geometric analysis of shell coiling: coiling in ammonoids," *J. Paleontol.* 41 (1967) — https://www.jstor.org/stable/1301975 |
| E. Surface-dial gap sweeps (§13) | vertebrate soft-tissue/posture dials; fish/invertebrate secondary dials | textbook-level traits (Proctor & Lynch, *Manual of Ornithology*, toe/webbing classifications; Wikipedia anatomical terminology; treehopper pronotum landmarks per Sugiura et al. 2025, *Eur. J. Entomol.*) |
| F. Mutation-coupling research (§14) | tradeoff/pleiotropy literature | Wilkins, Wrangham & Fitch, "The domestication syndrome in mammals," *Genetics* 197 (2014); Smith & Fretwell, "The optimal balance between size and number of offspring," *Am. Nat.* 108 (1974); Ducrest, Keller & Roulin, "Pleiotropy in the melanocortin system," *TREE* 23 (2008); McCue, "Cost of producing venom in three North American pitviper species," *Copeia* (2006) |

**Gold flag.** Raup (1966) W/D/T/S is adopted verbatim as the shell vocabulary. If a future knob duplicates a Raup parameter, the Raup parameter wins and the knob is deleted.
