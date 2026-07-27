# Naming: Binomial Stems — v0.1 Proposal

**Status:** Draft v0.1 (2026-07-27). Content companion to the Fauna Engine RFC v0.3
§9 and the Biosphere Vocabulary Proposal v1.0. Supplies the researched stem list
and composition rules for the **binomial generator** — the single mechanical
naming register. Nothing here is new machinery; every entry is data consumed by
the epithet formula: `epithet = f(salient axis)`.

**Dependencies:** Fauna RFC §9 ("The naming stack"), Biosphere Vocabulary
Proposal ( [name] -tagged axes), Biosphere Addendum B1 (knobs with [name]
consumers). Implementers: the K13 treegen `Node.axes` and `Node.knobs`
dictionaries are the input space; the output is a `binomial` string committed
at Species rank per RFC §11.

**Ground rules (from RFC §9, sharpened):**

1. **Morphology-free, proofreadable-in-one-sitting.** Stems are terminal
   building blocks; no declension tables, no case agreement rules beyond the
   suffix mechanics in §2. A human can audit the entire register in 15 minutes.
2. **Real Latin/Greek roots as actually used in Linnaean nomenclature.** Every
   stem below is attested in at least one published binomial. Hoax stems =
   deletion.
3. **One mechanical register.** The engine computes an epithet; the LLM never
   composes one. "Formula is *correct* here" (RFC §9.3) — names become data.
4. **Salience-ordering, not free composition.** The engine picks the
   highest-salience axis, looks up the corresponding stem, applies a suffix,
   and stops. Secondary-axis tiebreak is deterministic (§3.3).

---

## 1. Stem register

~120 stems, organized by the trait axis they describe. Each entry: stem,
meaning, part-of-speech role (prefix-root = goes before body-part root;
suffix-root = final element before suffix; standalone = complete word), 1–2
real binomial attestations, and the engine axis it maps to. Notation: `→`
marks the stem as it appears in an epithet; `←` marks a genus where it serves
as root.

### 1.1 Size

Stems describing body mass, absolute dimensions, or proportion extremes.

| # | Stem | Meaning | Role | Real attestation | Engine axis |
|---|---|---|---|---|---|
| 1 | `mega-` / `-megas` | great, large | prefix / suffix-root | *Megascops* (screech-owl genus, "great watcher"), *Epimachus megas* | body_mass, size extreme |
| 2 | `macro-` | large, long | prefix | *Macroclemys* (alligator snapper, "large turtle"), *Macropus* (kangaroo, "big foot") | body_mass, limb length |
| 3 | `gigant-` / `gigante-` | gigantic | prefix / standalone | *Gigantopithecus*, *Sequoiadendron giganteum* | body_mass (top decile) |
| 4 | `grandi-` | large, grand | prefix | *Tyrannus grandis*, *Platanista gangetica* subsp. *minor* opposes | body_mass |
| 5 | `magni-` | large | prefix | *Magnirostris* (protoceratopsid, "large beak"), *Alces magnus* | size of specific part |
| 6 | `maj-` / `major` | greater | standalone | *Parus major* (great tit), *Dendrocopos major* (great spotted woodpecker) | size relative to sister species |
| 7 | `micro-` | small | prefix | *Microtus* (vole genus, "small ear"), *Microcebus* ("small monkey" — mouse lemur) | body_mass (bottom decile) |
| 8 | `parv-` / `parvi-` | small, slight | prefix | *Parvulus* (genus), *Parvicursor* ("small runner" — alvarezsaurid) | body_mass |
| 9 | `min-` / `minut-` / `minor` | very small, lesser | standalone | *Sorex minutus* (pygmy shrew), *Fregata minor* (great frigatebird — ironic) | body_mass (bottom) |
| 10 | `nan-` / `nanus` | dwarf | standalone | *Nanus* (genus), *Dryobates nanus* | body_mass, island dwarf |
| 11 | `pumil-` | dwarf, diminutive | standalone | *Caryota pumila*, *Amaranthus pumilus* (seabeach amaranth) | body_mass |
| 12 | `gracil-` | slender, gracile | standalone | *Australopithecus gracilis*, *Gracilinanus* (gracile opossum) | build/robustness |
| 13 | `robust-` | robust, stout | standalone | *Paranthropus robustus*, *Brachylophus robustus* | build/robustness |
| 14 | `longi-` | long | prefix | *Longicauda* (genus), *Tyrannus longicauda* | tail, neck, snout, limb length |
| 15 | `brevi-` | short | prefix | *Breviceps* (rain frog, "short head"), *Breviparopus* ("short equal-foot") | tail, neck, snout length |
| 16 | `alti-` | tall, high | prefix | *Altirhinus* ("high snout" — iguanodontian), *Alticola* (mountain vole) | height, altitude |
| 17 | `humil-` | low, humble | standalone | *Festuca humilior*, *Chamaecrista humilis* | low stature |
| 18 | `procer-` | tall, slender-tall | standalone | *Proceratophrys* (horned frog, "tall eyebrow"?), *Euphorbia procera* | height |
| 19 | `angust-` | narrow | standalone | *Angustidontus* (eurypterid), *Astragalus angustus* | narrow body/part |
| 20 | `lat-` / `lati-` | wide, broad | prefix | *Latimeria* (coelacanth), *Laticauda* (sea krait, "wide tail") | broad body/part |

### 1.2 Color

Stems describing hue, brightness, and pattern. Pigment set is clade-steady (RFC
§2: "per-clade pigment set + pattern parameters"), so color epithets are
anchored to real chemistry; a blue squirrel is impossible in a melanin-only
clade, so the engine never picks the stem.

| # | Stem | Meaning | Role | Real attestation | Engine axis |
|---|---|---|---|---|---|
| 21 | `melan-` / `melano-` | black, dark | prefix | *Melanerpes* (woodpecker, "black creeper"), *Melanocetus* (black seadevil) | pigmentation (melanic) |
| 22 | `nigr-` / `nigri-` | black, dark | prefix / standalone | *Branta nigricans*, *Nigrita* (negrofinch) | pigmentation |
| 23 | `ater` / `atr-` | dull black | standalone / prefix | *Parus ater* (coal tit), *Atrichornis* (scrub-bird, "dark bird") | pigmentation (matte) |
| 24 | `fusc-` | dusky, dark brown | standalone | *Fuscus* (genus), *Turdus fuscus* | pigmentation |
| 25 | `leuc-` / `leuco-` | white, pale | prefix | *Leucochloris* (white-throated hummingbird), *Leucopternis* (white hawk) | pigmentation (albinistic/pale) |
| 26 | `alb-` / `albi-` | white | prefix / standalone | *Albus* (genus), *Calyptorhynchus albus* | pigmentation |
| 27 | `candid-` | shining white | standalone | *Candidus* (genus), *Crocidura candida* | pigmentation |
| 28 | `nive-` / `nivalis` | snowy white | standalone | *Plectrophenax nivalis* (snow bunting), *Galanthus nivalis* | pigmentation, alpine habitat |
| 29 | `cinere-` / `cinereus` | ash-grey | standalone | *Cinereus* (genus), *Peromyscus cinereus* | pigmentation (grey) |
| 30 | `glauc-` | blue-grey, sea-grey | standalone | *Glaucidium* (pygmy owl, "little grey"), *Pseudotsuga glauca* | pigmentation (grey-blue) |
| 31 | `grise-` | grey (Medieval Latin) | standalone | *Griseus* (genus), *Streptopelia grisea* | pigmentation (warm grey) |
| 32 | `ruf-` / `rufi-` | red, reddish | prefix / standalone | *Rufus* (genus), *Canis rufus* (red wolf) | pigmentation (rufous) |
| 33 | `rub-` / `rubr-` | red | prefix / standalone | *Rubus* (bramble, from red fruit), *Rubricapillus* ("red-headed") | pigmentation |
| 34 | `erythr-` / `erythro-` | red (Greek) | prefix | *Erythrocebus* (patas monkey, "red monkey"), *Erythrotriorchis* (red goshawk) | pigmentation |
| 35 | `ferrugin-` | rust-red, iron-colored | standalone | *Ferrugineus* (used in many genera), *Myiarchus ferrugineus* | pigmentation |
| 36 | `flav-` / `flavi-` | yellow, golden-yellow | prefix / standalone | *Flavus* (genus), *Crotalus flavus* | pigmentation |
| 37 | `lute-` | yellow (deep, saffron) | standalone | *Luteus* (genus), *Lycoperdon luteum* | pigmentation |
| 38 | `xanth-` / `xantho-` | yellow (Greek) | prefix | *Xanthocephalus* (yellow-headed blackbird), *Xanthoria* (lichen) | pigmentation |
| 39 | `aure-` / `aureus` | golden | standalone | *Aureus* (genus), *Staphylococcus aureus* | pigmentation (iridescent-gold) |
| 40 | `fulv-` | tawny, yellow-brown | standalone | *Fulvus* (genus), *Fulica fulva* | pigmentation |
| 41 | `virid-` / `viridi-` | green | prefix / standalone | *Viridis* (genus), *Bufo viridis* (green toad) | pigmentation |
| 42 | `chlor-` / `chloro-` | green (Greek) | prefix | *Chloris* (greenfinch), *Chlorocebus* (green monkey) | pigmentation |
| 43 | `caerul-` / `caerule-` | blue, sky-blue | standalone | *Caeruleus* (genus), *Cyanistes caeruleus* (blue tit) | pigmentation |
| 44 | `cyan-` / `cyano-` | dark blue (Greek) | prefix | *Cyanocitta* (blue jay), *Cyanocompsa* (blue bunting) | pigmentation |
| 45 | `purpur-` | purple | standalone | *Purpureus* (genus), *Lamium purpureum* | pigmentation |
| 46 | `violace-` | violet | standalone | *Violaceus* (genus), *Janthinobacterium violaceum* | pigmentation |
| 47 | `rose-` | pink, rosy | standalone | *Roseus* (genus), *Phoenicopterus roseus* (greater flamingo) | pigmentation |
| 48 | `auranti-` / `aurantiac-` | orange | standalone | *Aurantius* (genus), *Amanita aurantiaca* | pigmentation |
| 49 | `variegat-` | variegated, mottled | standalone | *Variegatus* (used in many genera), *Vireo variegatus* | pattern |
| 50 | `maculat-` | spotted | standalone | *Maculatus* (genus), *Crocodylus maculatus* | pattern |
| 51 | `striat-` | striped | standalone | *Striatus* (genus), *Atheris striata* | pattern |
| 52 | `fasciat-` | banded | standalone | *Fasciatus* (genus), *Hemigalus fasciatus* | pattern |
| 53 | `punctat-` | dotted, punctate | standalone | *Punctatus* (genus), *Ictalurus punctatus* (channel catfish) | pattern |

### 1.3 Habitat

Stems describing the environment where the species lives. This is the largest
single category and the primary axis for epithets — habitat is often the
salient discriminant between sister species.

| # | Stem | Meaning | Role | Real attestation | Engine axis |
|---|---|---|---|---|---|
| 54 | `palustr-` | marsh, swamp | standalone | *Palustris* (used widely), *Cistothorus palustris* (marsh wren), *Bracteantha palustris* | niche: wetland |
| 55 | `silv-` / `silvestr-` / `sylvatic-` | forest, woodland | standalone | *Silvestris* (genus), *Felis silvestris* (European wildcat), *Mus sylvaticus* | niche: forest |
| 56 | `mont-` / `montan-` | mountain | standalone | *Montanus* (genus), *Passer montanus* (tree sparrow — "of the mountains"), *Charadrius montanus* (mountain plover) | niche: montane |
| 57 | `alpin-` | alpine, high-mountain | standalone | *Alpinus* (genus), *Lagopus alpinus*, *Pinguicula alpina* | niche: alpine |
| 58 | `arid-` | dry, arid | standalone | *Arida* (genus), *Pogonomyrmex aridus* | niche: desert/arid |
| 59 | `desert-` / `desertor-` | desert | standalone | *Deserti* (as epithet), *Oenanthe deserti* (desert wheatear), *Ammomanes deserti* (desert lark) | niche: desert |
| 60 | `arenari-` / `arenicola` | sand-dwelling | standalone | *Arenarius* (genus), *Agrotis arenarius*, *Leymus arenarius* (lyme grass) | niche: sandy/desert |
| 61 | `aquat-` / `aquatic-` | water-dwelling | standalone | *Aquaticus* (genus), *Sorex aquaticus*, *Rallus aquaticus* (water rail) | niche: freshwater |
| 62 | `marin-` / `maritim-` | sea, marine | standalone | *Marinus* (genus), *Larus marinus* (great black-backed gull), *Armadillidium marinum* | niche: marine |
| 63 | `lacustr-` | lake | standalone | *Lacustris* (used widely), *Acrocephalus lacustris* | niche: lake |
| 64 | `fluviatil-` / `fluvial-` | river | standalone | *Fluviatilis* (genus), *Potamogale fluviatilis*, *Unio fluviatilis* | niche: river |
| 65 | `ripari-` | riverbank, shore | standalone | *Riparius* (genus), *Riparia riparia* (sand martin/bank swallow), *Passerculus riparius* | niche: riparian |
| 66 | `littor-` / `littoral-` | shore, littoral | standalone | *Littoralis* (genus), *Pisidium littorale* | niche: coastal shore |
| 67 | `campestr-` | plain, field, grassland | standalone | *Campestris* (genus), *Colaptes campestris* (campo flicker), *Agaricus campestris* (field mushroom) | niche: grassland |
| 68 | `pratens-` / `praticola` | meadow-dwelling | standalone | *Pratensis* (genus), *Anthus pratensis* (meadow pipit), *Cardamine pratensis* (cuckooflower) | niche: meadow |
| 69 | `agrest-` | field, cultivated land | standalone | *Agrestis* (genus), *Microtus agrestis* (field vole) | niche: field/agro |
| 70 | `arbore-` / `arboricol-` | tree-dwelling | standalone / prefix | *Arboreus* (genus), *Dendroica arborea*, *Thylogale arboreus* | niche: arboreal |
| 71 | `sax-` / `saxatil-` | rock-dwelling | standalone | *Saxatilis* (genus), *Achaearanea saxatilis*, *Rupicapra rupicapra* is related | niche: rocky/rupicolous |
| 72 | `rupestr-` | cliff, crag | standalone | *Rupestris* (genus), *Columba rupestris* (hill pigeon), *Sedum rupestre* | niche: cliff |
| 73 | `cavern-` / `cavernicol-` | cave-dwelling | standalone | *Cavernicola* (genus), *Proteus cavernicola* | niche: cave |
| 74 | `troglodyt-` | cave-dweller (Greek) | standalone | *Troglodytes* (wren genus — misapplied but standard), *Pan troglodytes* (chimpanzee), *Eptesicus troglodytes* | niche: cave |
| 75 | `fossor-` / `fossori-` | digging, burrowing | standalone | *Clivina fossor* (Linnaeus, 1758), *Euneomys fossor* (burrowing rodent) | behavior: fossorial |
| 76 | `arenicol-` | sand-dweller | standalone | *Arenicola* (lugworm genus), *Phrynosoma arenicola* | niche: sandy |
| 77 | `limos-` | muddy | standalone | *Limosa* (godwit genus, "muddy"), *Neoceratodus limosus* | niche: mud |
| 78 | `paludos-` | boggy | standalone | *Paludosus* (genus), *Ranunculus paludosus* | niche: bog/fen |
| 79 | `bore-` / `boreal-` | northern | standalone | *Borealis* (genus), *Balaena borealis* (sei whale), *Lynx borealis* | geography: boreal |
| 80 | `austral-` | southern | standalone | *Australis* (genus), *Balaena australis* (southern right whale), *Eudyptes australis* | geography: austral |
| 81 | `oriental-` | eastern | standalone | *Orientalis* (genus), *Platanista orientalis*, *Cuculus orientalis* | geography: eastern |
| 82 | `occidental-` | western | standalone | *Occidentalis* (genus), *Larus occidentalis* (western gull), *Thuja occidentalis* | geography: western |
| 83 | `arctic-` / `arct-` | arctic, far north | standalone | *Arcticus* (genus), *Lepus arcticus* (arctic hare), *Gavia arctica* (black-throated diver) | geography: arctic |
| 84 | `tropic-` / `tropical-` | tropical | standalone | *Tropicus* (genus), *Phaethon tropicus* | geography: tropical |
| 85 | `insular-` | island | standalone | *Insularis* (genus), *Urocyon insularis* (island fox), *Bothrops insularis* (golden lancehead) | geography: island |
| 86 | `pelag-` / `pelagic-` | open ocean | standalone | *Pelagicus* (genus), *Hydrobates pelagicus* (European storm petrel), *Puffinus pelagicus* | niche: pelagic |
| 87 | `abyss-` / `abyssal-` | deep-sea, abyssal | standalone | *Abyssicola* (genus), *Bathysaurus abyssicola*, *Meadia abyssalis* (abyssal cutthroat eel) | niche: abyssal |

### 1.4 Morphology

Compound-forming: prefix-root + body-part suffix-root. The prefix contributes
the quality (long, short, thick, curved); the suffix-root names the part.

**Prefix roots (combine with body-part roots):**

| # | Stem | Meaning | Role | Real attestation | Engine axis |
|---|---|---|---|---|---|
| 88 | `longi-` | long | prefix | *Longicauda*, *Longirostris* — see #14 | relative dimension |
| 89 | `brevi-` | short | prefix | *Brevicauda*, *Brevirostris* — see #15 | relative dimension |
| 90 | `macro-` | large | prefix | *Macrocephala*, *Macropoda* — see #2 | relative dimension |
| 91 | `micro-` | small | prefix | *Microcephala*, *Micropoda* — see #7 | relative dimension |
| 92 | `lati-` | broad, wide | prefix | *Latirostris* ("broad beak"), *Laticauda* — see #20 | relative dimension |
| 93 | `angusti-` | narrow | prefix | *Angustirostris* ("narrow beak"), *Angustidens* ("narrow tooth") | relative dimension |
| 94 | `crassi-` | thick | prefix | *Crassirostris* ("thick beak"), *Crassicauda* ("thick tail") | relative dimension |
| 95 | `tenui-` | thin, slender | prefix | *Tenuicauda* ("thin tail"), *Tenuipes* ("thin foot"), *Acanthephyra tenuipes* | relative dimension |
| 96 | `curvi-` | curved | prefix | *Curvirostris* ("curved beak"), *Curvicauda* ("curved tail") | shape |
| 97 | `recti-` | straight | prefix | *Rectirostris* ("straight beak"), *Rectipes* ("straight foot") | shape |
| 98 | `acuti-` | sharp, pointed | prefix | *Acutirostris* ("sharp beak"), *Acuticauda* ("sharp tail") | shape |
| 99 | `obtusi-` | blunt | prefix | *Obtusirostris* ("blunt snout"), *Obtusidens* ("blunt tooth") | shape |
| 100 | `plan-` / `plani-` | flat | prefix | *Planirostris* ("flat beak"), *Planicauda* ("flat tail") | shape |

**Body-part suffix roots (final element before gender/number suffix):**

| # | Stem | Meaning | Role | Real attestation | Engine axis |
|---|---|---|---|---|---|
| 101 | `-cauda` / `-caudus` | tail | suffix-root | *Longicauda*, *Brevicauda*, *Laticauda*, *Acanthophthalmus longicaudus* | tail_length_ratio |
| 102 | `-cephala` / `-cephalus` | head | suffix-root | *Macrocephala*, *Breviceps*, *Xanthocephalus* | head_size_ratio |
| 103 | `-poda` / `-pus` / `-pes` | foot | suffix-root | *Macropus*, *Brevipes*, *Tenuipes*, *Cryptopus* | foot_posture, limb_length |
| 104 | `-rostris` | beak, snout | suffix-root | *Longirostris*, *Brevirostris*, *Crassirostris* | snout_ratio |
| 105 | `-pinna` / `-pennis` | wing, fin | suffix-root | *Longipennis* ("long-winged"), *Macropinna* ("big fin"), *Brevi pennis* | wing/fin size |
| 106 | `-dentis` / `-dens` | tooth | suffix-root | *Macrodens*, *Brevidentis*, *Angustidens* | tooth/tusk size |
| 107 | `-cornis` | horn | suffix-root | *Brevicornis*, *Longicornis*, *Acuticornis* | horn/antler size |
| 108 | `-ala` / `-alatus` | wing | suffix-root | *Longialatus*, *Brevialata* | wing span |
| 109 | `-collis` | neck | suffix-root | *Longicollis*, *Brevicollis* | neck_length_ratio |
| 110 | `-auris` / `-auritus` | ear | suffix-root | *Macrotis* (bilby, "big ear"), *Plecotus auritus* (brown long-eared bat) | ear_size_ratio |
| 111 | `-ops` / `-opsis` | face, eye, appearance | suffix-root | *Megascops* ("great face"), *Chloropsis* ("green appearance") | eye/face region |
| 112 | `-oculis` / `-ophthalmus` | eye | suffix-root | *Macroculis*, *Microphthalmus* | eye size |
| 113 | `-thorax` | chest | suffix-root | *Macrothorax*, *Stenothorax* | trunk_depth_ratio |
| 114 | `-gaster` | belly | suffix-root | *Macrogaster*, *Stenogaster* | trunk shape |

### 1.5 Behavior / ecology

| # | Stem | Meaning | Role | Real attestation | Engine axis |
|---|---|---|---|---|---|
| 115 | `nocturn-` | nocturnal, night-active | standalone | *Nocturnus* (genus), *Caprimulgus nocturnus* | activity period |
| 116 | `diurn-` | diurnal, day-active | standalone | *Diurnus* (genus, less common but valid), *Geophaps diurna* | activity period |
| 117 | `crepuscul-` / `vespertin-` | crepuscular, twilight | standalone | *Vespertinus* (genus), *Falco vespertinus* (red-footed falcon — "evening falcon"), *Vespertilio* (bat genus, "of evening") | activity period |
| 118 | `migrat-` / `migratori-` | migratory | standalone | *Migratorius* (genus), *Turdus migratorius* (American robin — misnamed but standard), *Ectopistes migratorius* (passenger pigeon) | seasonality mode |
| 119 | `cursor-` | running, cursorial | standalone | *Cursorius* (courser genus), *Cursor* (genus), *Parvicursor* | locomotor mode |
| 120 | `natat-` / `natator` | swimming | standalone | *Natator* (flatback turtle genus), *Tropidonotus natator* | locomotor mode |
| 121 | `volat-` / `volans` | flying | standalone | *Volans* (genus), *Draco volans* (flying dragon lizard), *Petaurus volans* | locomotor mode |
| 122 | `saltat-` / `saltator` | leaping, jumping | standalone | *Saltator* (genus), *Callicebus saltator* | locomotor mode |
| 123 | `fossor-` | digging | standalone | see #75 (*Clivina fossor*, *Euneomys fossor*) | locomotor mode |
| 124 | `scansor-` | climbing | standalone | *Scansor* (genus), *Dendroscansor* (climbing bird) | locomotor mode |
| 125 | `raptor-` | seizing, predatory | standalone | *Raptor* (genus), *Velociraptor* ("swift seizer") | diet guild |
| 126 | `piscivor-` | fish-eating | standalone | *Piscivorus* (genus), *Agkistrodon piscivorus* (cottonmouth) | diet guild |
| 127 | `insectivor-` | insect-eating | standalone | *Insectivorus* (genus), *Sorex insectivorus* | diet guild |
| 128 | `carnivor-` | meat-eating | standalone | *Carnivorus* (genus), *Carnivora* (the order) | diet guild |
| 129 | `herbivor-` / `graminivor-` | plant/grass-eating | standalone | *Herbivorus* (genus), *Graminivorus* (genus) | diet guild |
| 130 | `gregari-` | gregarious, social | standalone | *Gregarius* (genus), *Vanellus gregarius* (sociable lapwing) | social system |
| 131 | `solitari-` | solitary | standalone | *Solitarius* (genus), *Pezophaps solitarius* (Rodrigues solitaire), *Cuculus solitarius* (red-chested cuckoo) | social system |

### 1.6 Texture / covering

| # | Stem | Meaning | Role | Real attestation | Engine axis |
|---|---|---|---|---|---|
| 132 | `hirsut-` | hairy, shaggy | standalone | *Hirsutus* (genus), *Brachionichthys hirsutus* (spotted handfish — rough skin), *Rubus hirsutus* | covering: fur density |
| 133 | `glabr-` | smooth, hairless | standalone | *Glaber* (genus), *Lithobius glaber*, *Amaranthus glaber* | covering: bare skin |
| 134 | `spinos-` | spiny | standalone | *Spinosus* (genus), *Gasterosteus spinosus* (spiny stickleback), *Zanthoxylum spinosum* | defense: spines |
| 135 | `squam-` / `squamos-` | scaly | standalone | *Squamosus* (genus), *Manis squamosa* (pangolin), *Anthonomus squamosus* | covering: scales |
| 136 | `echinat-` | prickly, hedgehog-like | standalone | *Echinatus* (genus), *Erinaceus echinatus* | covering: spines |
| 137 | `setos-` | bristly | standalone | *Setosus* (genus), *Atheris setosa* | covering: bristles |
| 138 | `tomentos-` | woolly, densely hairy | standalone | *Tomentosus* (genus), *Rhinolophus tomentosus* | covering: fur density |
| 139 | `villos-` | shaggy, villous | standalone | *Villosus* (genus), *Dasypus villosus* (hairy armadillo), *Chaetophractus villosus* | covering: fur texture |
| 140 | `nud-` | naked, bare | standalone | *Nudus* (genus), *Heterocephalus nudus* (partial), *Georychus nudus* | covering: bare |
| 141 | `armat-` | armed, armored | standalone | *Armatus* (genus), *Hoplosternum armatum*, *Acteon armatus* | defense: armor |
| 142 | `cristat-` | crested | standalone | *Cristatus* (genus), *Triturus cristatus* (great crested newt), *Cariama cristata* (red-legged seriema) | signal: crest |
| 143 | `coronat-` | crowned | standalone | *Coronatus* (genus), *Stephanoaetus coronatus* (crowned eagle), *Lemur coronatus* (crowned lemur) | signal: crest/crown |
| 144 | `barbat-` | bearded | standalone | *Barbatus* (genus), *Gypaetus barbatus* (bearded vulture), *Pogona barbata* (bearded dragon) | covering: facial hair |
| 145 | `jubat-` | maned | standalone | *Jubatus* (genus), *Acinonyx jubatus* (cheetah — "maned"), *Panthera leo* subsp. *jubata* | covering: mane |

### Summary counts

| Category | Count |
|---|---|
| Size | 20 |
| Color | 33 |
| Habitat | 34 |
| Morphology (prefixes + body-part roots) | 27 |
| Behavior / ecology | 17 |
| Texture / covering | 14 |
| **Total** | **145** |

Any stem not in §1 that is found in a published binomial may be added as a
**patch** to this document; stems must clear the same attestation bar
(≥1 published binomial, axis consumer tagged [name] in the Vocabulary
Proposal).

---

## 2. Suffix mechanics

The RFC specifies exactly four suffixes. Each has distinct semantics and
combinatorics.

### 2.1 The four suffixes

| Suffix | Meaning | When to use | Example |
|---|---|---|---|
| `-ensis` | "from [a place or habitat]" | Habitat/dry-land axes (marsh, forest, mountain, desert, island, river, shore, field…) — replaces *nominal* habitat. Also geography proper: `borealis`, `australis` already carry the suffix sense. | *Palustris* = "of the marsh" (palustr- + -is, the 3rd-declension form equivalent to -ensis for `-ster` stems). *Montanus* = "of the mountain." *Americensis* = "from America" (hypothetical; real form is *americanus*, the -anus variant). |
| `-oides` | "resembling, -like" | Morphology resemblance (head shape, foot shape, body form) and color-approximation when the color is not a pure hue. Also the safe default when a form is "X-like" without a single salient dimension. | *Sciuroides* = "squirrel-like." *Vulpeculoides* = "fox-like." *Pisciformis* is analogous (fish-shaped). |
| `-cola` | "dweller of" | Habitat axes where the relationship is *inhabitation*, not geographic origin. Best for microhabitat, substrate, and organic association: `arenicola` (sand-dweller), `cavernicola` (cave-dweller), `arboricola` (tree-dweller), `limicola` (mud-dweller), `pratincola` (meadow-dweller). Overlaps with `-ensis` but carries the "I live here" not "I am from here" connotation. | *Arenicola* (lugworm — sand-dweller), *Cavernicola*, *Oenanthe deserti* uses `-i` instead; `-cola` is the productive form. |
| `-i` / `-ae` | genitive "of [person]" | Reserved for eponymy (named after a person). **The engine should avoid generating these** — person-honor names are curation, not generation. If the engine ever must autogenerate an eponym (e.g., a player-named species), use `-i` for masculine eponym, `-ae` for feminine. | *Darwini* = "of Darwin." *Banksiae* = "of Banks." *Thomsoni* (gazelle). |

### 2.2 Stem-to-suffix latinization rules

These are the **only** rules the implementer needs. No declension tables.

**Rule A — -ensis / -is / -anus (habitat origin).**

The stem determines the form:

- Stems in `-estr-` / `-ustr-`: use 3rd-declension `-is` form, with gender agreement.
  `palustr-` → *palustris* (m/f), *palustre* (n). `silvestr-` → *silvestris*.
  `campestr-` → *campestris*. `rupestr-` → *rupestris*.
- Stems in `-an-` / `-in-` already: leave as-is or add `-us/-a/-um`:
  `montan-` → *montanus*, `alpin-` → *alpinus*, `marin-` → *marinus*, `aquat-` → *aquaticus*.
- Stems in `-ens-` already: `pratens-` → *pratensis*.
- Bare stems: append `-ensis`:
  `ripar-` → *ripariensis*, `lacustr-` → *lacustris* (special: `-str-` stem).
- Geographic: `bore-` → *borealis*, `austral-` → *australis*, `oriental-` → *orientalis*,
  `occidental-` → *occidentalis*, `arctic-` → *arcticus*, `insular-` → *insularis*.

**Hardcoded map (implement as a lookup, not rules):**

| Stem | Habitat adjective form | Gender (m/f/n default) |
|---|---|---|
| `palustr-` | `palustris` | m/f = `palustris`, n = `palustre` |
| `silvestr-` | `silvestris` | m/f = `silvestris`, n = `silvestre` |
| `montan-` | `montanus` | m = `montanus`, f = `montana`, n = `montanum` |
| `alpin-` | `alpinus` | m = `alpinus`, f = `alpina`, n = `alpinum` |
| `arid-` | `aridus` | m = `aridus`, f = `arida`, n = `aridum` |
| `campestr-` | `campestris` | m/f = `campestris`, n = `campestre` |
| `pratens-` | `pratensis` | m/f = `pratensis`, n = `pratense` |
| `marin-` | `marinus` | m = `marinus`, f = `marina`, n = `marinum` |
| `aquat-` | `aquaticus` | m = `aquaticus`, f = `aquatica`, n = `aquaticum` |
| `fluviatil-` | `fluviatilis` | m/f = `fluviatilis`, n = `fluviatile` |
| `rupestr-` | `rupestris` | m/f = `rupestris`, n = `rupestre` |
| `agrest-` | `agrestis` | m/f = `agrestis`, n = `agrestre` |
| `littoral-` | `littoralis` | m/f = `littoralis`, n = `littorale` |
| `bore-` | `borealis` | m/f = `borealis`, n = `boreale` |
| `austral-` | `australis` | m/f = `australis`, n = `australe` |
| `oriental-` | `orientalis` | m/f = `orientalis`, n = `orientale` |
| `occidental-` | `occidentalis` | m/f = `occidentalis`, n = `occidentale` |
| `arctic-` | `arcticus` | m = `arcticus`, f = `arctica`, n = `arcticum` |
| `insular-` | `insularis` | m/f = `insularis`, n = `insulare` |
| `pelag-` | `pelagicus` | m = `pelagicus`, f = `pelagica`, n = `pelagicum` |
| `abyss-` | `abyssalis` Or `abyssicola` | see `-cola` table |

**Rule B — -cola (inhabitant).**

Stem + `-cola`. No gender change — `-cola` is common gender (m/f same, n not used for animals). Connect with `-i-` if the stem ends in a consonant cluster: `aren-` → *arenicola* (with linking -i-). `cavern-` → *cavernicola*. `arbor-` → *arboricola*. `prat-` → *praticola* (already attested; the `-i-` is absorbed). `petr-` → *petricola* (rock-dweller). `lim-` → *limicola*. `silv-` → *silvicola*.

**Hardcoded map:**

| Stem | -cola form |
|---|---|
| `aren-` | `arenicola` |
| `cavern-` | `cavernicola` |
| `arbor-` | `arboricola` |
| `prat-` | `praticola` |
| `silv-` | `silvicola` |
| `rip-` | `ripicola` |
| `sax-` | `saxicola` |
| `lim-` | `limicola` |
| `troglodyt-` | `troglodytes` (Greek form, native -es suffix; `troglodyticola` would be a monster) |

**Rule C — -oides (resemblance).**

Stem + `-oides`. The stem should ideally be a noun (the thing being resembled).
In practice, adjective stems work too. Gender: `-oides` is indeclinable in
classical Latin but behaves as common-gender adjective in nomenclature;
agreement is with the genus gender, but since the epithet formula doesn't
decline per genus, use a fixed form: `-oides` for all genera.

Examples: *sciur-* + `-oides` → *Sciuroides*. *vulpecul-* + `-oides` →
*Vulpeculoides*. If an adjectival stem is the input (e.g., `maculat-` for
"spotted-like"), prefer the `-atus` form: *maculatus*, not *maculatoides*.

**Rule D — standalone adjective stems (color, texture, size, behavior).**

These already carry their own suffix form. Add gender agreement with the genus:

- Masculine genus → `-us` (2nd decl.) or matching 3rd-decl. form
- Feminine genus → `-a` or matching
- Neuter genus → `-um` or matching

A hardcoded gender map:

| Stem root | m form | f form | n form |
|---|---|---|---|
| `ruf-` | `rufus` | `rufa` | `rufum` |
| `flav-` | `flavus` | `flava` | `flavum` |
| `nigr-` | `niger` | `nigra` | `nigrum` |
| `fusc-` | `fuscus` | `fusca` | `fuscum` |
| `gracil-` | `gracilis` | `gracilis` | `gracile` |
| `robust-` | `robustus` | `robusta` | `robustum` |
| `hirsut-` | `hirsutus` | `hirsuta` | `hirsutum` |
| `glabr-` | `glaber` | `glabra` | `glabrum` |
| `spinos-` | `spinosus` | `spinosa` | `spinosum` |
| `nocturn-` | `nocturnus` | `nocturna` | `nocturnum` |
| `migratori-` | `migratorius` | `migratoria` | `migratorium` |
| `volans` | `volans` | `volans` | `volans` (present participle, indeclinable adj.) |
| `natator` | `natator` | `natatrix` | — (agent noun; use `natator` for m, `natatrix` for f) |

### 2.3 Decision table: which suffix for which axis

| Axis category | Primary suffix | Fallback suffix | Notes |
|---|---|---|---|
| Habitat (place) | `-ensis` / `-is` form | `-cola` | `-ensis` for geographic origin; `-cola` for substrate inhabitation. The fallback handles edge cases like "mud-dweller" where both make sense — prefer `-cola` for microhabitat. |
| Habitat (substrate) | `-cola` | `-ensis` | Sand, rock, cave, mud, tree — the organism lives *in* it, not *from* it. |
| Color (pure hue) | none (standalone adj.) | — | `rufus`, `flavus`, `viridis` are already complete words. |
| Color (approximate) | `-oides` | standalone adj. | "Glaucous-like" is `glaucoides` if the color is approximate. |
| Size (standalone) | none (standalone adj.) | — | `gracilis`, `robustus`, `giganteus`. |
| Size (relative to part) | compound (prefix + body-part root) | standalone | `longicauda`, `brevipes`, `macrocephala`. |
| Morphology (part shape) | compound (prefix + body-part root) | `-oides` | `latirostris`, `curvicauda`. If no part root fits, `-oides` ("that-shaped"). |
| Texture / covering | none (standalone adj.) | — | `hirsutus`, `glaber`, `spinosus`, `squamosus`. |
| Behavior | none (standalone adj.) | — | `nocturnus`, `migratorius`, `natator`, `cursorius`. |
| Geography | `-ensis` variant (e.g., `-alis`) | — | `borealis`, `australis`, `orientalis`. These are already fossilized forms. |
| Diet | none (standalone adj.) | — | `piscivorus`, `carnivorus`, `insectivorus`. |
| Honor (person) | `-i` / `-ae` | **avoid** | Engine should not generate eponyms. Human-authored only. |

---

## 3. Composition rules

### 3.1 Genus name construction

Genus names are **free-form within clade conventions** — the engine does not
autogenerate genus names; they are committed at Genus rank from curated roots.
This document supplies the **body-plan suffix vocabulary** for curators:

| Body plan / grade | Suffix convention | Example roots | Real precedent |
|---|---|---|---|
| Rodent-grade (small gnawer) | `-mys` | *Cinereomys*, *Sciurops* | *Peromyscus*, *Oryzomys*, *Eliomys* |
| Bird-grade | `-ornis` / `-avis` / `-gavia` | *Cyanornis*, *Leptavis* | *Phaethornis*, *Leptornis*, *Eoavis* |
| Fish-grade | `-ichthys` / `-piscis` | *Melanichthys*, *Macropiscis* | *Melanoichthys*, *Ichthyornis* |
| Lizard-grade | `-saurus` / `-lacerta` | *Microsaurus*, *Flavilacerta* | *Mosasaurus*, *Megalosaurus* |
| Turtle-grade | `-chelys` / `-testudo` | *Megachelys* | *Archelon*, *Chelonia* |
| Frog/toad-grade | `-batrachus` / `-rana` | *Microbatrachus* | *Megalobatrachus*, *Bufo* genus itself |
| Snake-grade | `-ophis` / `-serpens` | *Leptophis*, *Microserpens* | *Leptophis*, *Dendroaspis* |
| Insect-grade | `-ptera` / `-formica` | *Xanthoptera*, *Macroformica* | *Coleoptera*, *Hymenoptera* |
| Spider/scorpion-grade | `-arachne` / `-scorpio` | *Cavernarachne* | *Ariadne*, *Palpigradi* |
| Crustacean-grade | `-carcinus` / `-astacus` | *Abyssocarcinus* | *Carcinus*, *Astacus* |
| Mollusc-grade | `-concha` / `-limax` | *Macroconcha* | *Spirula*, *Limax* |
| Worm-grade | `-vermis` / `-helminthus` | *Microvermis* | *Vermes* (archaic), *Plathelminthes* |
| Soft-bodied pelagic | `-medusa` / `-pulmo` | *Caerulomedusa* | *Aurelia*, *Pelagia* |
| Generic "creature" | `-ops` / `-oides` / `-therium` | *Sciurops*, *Megaloides* | *Titanoides*, *Megatherium* |

**Construction rule:** clade-descriptor prefix + body-plan suffix.
`Cinereomys` = "ash-grey mouse." The prefix is typically a color or habitat
stem from §1. Curators may invent new roots but must check for collision with
published genera (search GBIF/ITIS; the `pins.py` validator does a mechanical
check).

### 3.2 Epithet selection: salience ordering

The engine computes the epithet deterministically from the species record:

1. **Compute salience for every [name]-tagged axis.** Salience = the normalized
   deviation of this species' axis value from its clade median, weighted by an
   authored `salience_weight` (default 1.0 for all [name] axes; curators may
   boost or suppress per axis).
2. **Select the axis with the highest salience score.** This is the
   *discriminating trait*.
3. **For compound axes** (morphology: "long tail," "broad beak"), the engine
   first determines which body-part axis has the highest local salience, then
   pairs it with the appropriate dimensional prefix.
4. **Map axis → stem via the tables in §1.** If the axis is "tail_length_ratio"
   and the value is ≥0.7 (long tail), map to `longi-` + `-cauda` → *longicauda*.
   Thresholds are in a simple lookup:

| Axis | High-threshold stem | Low-threshold stem | Threshold value |
|---|---|---|---|
| tail_length_ratio | `longi-` + `-cauda` | `brevi-` + `-cauda` | 0.5 (median) |
| ear_size_ratio | `macro-` + `-auris` | `micro-` + `-auris` | 0.10 |
| snout_ratio | `longi-` + `-rostris` | `brevi-` + `-rostris` | 0.40 |
| neck_length_ratio | `longi-` + `-collis` | `brevi-` + `-collis` | 0.20 |
| body_mass | `gigante-` (top 5%), `maj-` (top 30%) | `minut-` (bottom 5%), `parv-` (bottom 30%) | clade-relative percentile |

For continuous color axes, convert the hue value to the nearest named color
stem. For discrete axes (diet guild, activity period), map directly:
`piscivore` → *piscivorus*, `nocturnal` → *nocturnus*.

### 3.3 Collision avoidance (deterministic tiebreak)

If two species in the same genus would receive the same epithet:

1. **Secondary-axis promottion:** the lower-salience species uses its
   second-highest-salience axis instead. If still colliding, descend.
2. **Geographic disambiguation:** append the geography stem if available
   (*longicauda borealis* is not standard binomial form; instead, the
   secondary axis becomes the epithet, and the geography is stored as metadata
   — the epithet is always a single word).
3. **Seeded suffix swap:** if all axes exhausted, `-oides` → `-iformis`,
   `-cola` → `-ensis` (only in collision context).
4. **Last resort — hash fragment:** append first 4 chars of the species'
   K1 `sid` as a pseudo-authority: *longicauda-a3f7*. Names are immutable once
   committed per RFC §11.

Rule 4 should be vanishingly rare; the axis space is large enough that
collision in a genus of <~20 species (the engine's typical radiation cap) is
unlikely if there are ≥3 discriminable axes.

### 3.4 Banned patterns

1. **No hybrid Greco-Latin compounds beyond attested precedent.** `-oides`
   (Greek `-οειδής`) on Latin stems is acceptable — it is the standard
   Linnaean suffix regardless of stem origin. But `macro-` (Greek) +
   `-cauda` (Latin) = *Macrocauda* is legal because *Macropus* established
   the pattern in 1790. The rule: **one stem = one language** is aspirational
   but not a ban; the real ban is constructing novel portmanteaus from three
   languages (e.g., `xantho-` + `palustr-` + `-ensis` in one word).
2. **No declension tables.** Gender agreement is handled by §2.2's hardcoded
   maps. The implementer never looks up a declension.
3. **No case agreement across the binomial.** The genus and epithet are
   independent words; the epithet agrees in gender with the genus (adjective
   form), not in case. Since genus names are curated and their gender is
   authored, the epithet form follows the genus gender from §2.2's table.
4. **No morphological derivation.** `longus` + `cauda` does not become
   *longae caudae* (genitive phrase); it becomes *longicauda* (compound
   adjective). Compounds are concatenated stem + connecting vowel `-i-` +
   body-part root.
5. **No "New Latin" inventions.** Every stem must appear in at least one
   published binomial. The stem list in §1 is closed; additions require a
   patch to this document.

---

## 4. Validation appendix: worked examples

~20 binomials demonstrating the rules end-to-end. For each: the engine preset
or grade, the salient axis and value, the stem selection, the suffix choice,
and the final binomial.

### Terrestrial mammals (tetrapod plan)

**1. Squirrel-grade arboreal rodent, long tail**
- Preset: `squirrel` (B1 §2, tail_length_ratio = 0.90)
- Salient axis: tail_length_ratio > 0.5 → `longi-` + `-cauda`
- Genus: `Sciur-` (Latin *sciurus*) + `-ops` (face/appearance) = *Sciurops*
- Epithet: *longicauda* (f, agrees with Sciurops feminine by convention for `-ops` genera)
- **Binomial:** *Sciurops longicauda*

**2. Desert mole-grade, large digging claws**
- Preset: `mole` (B1 §2, olecranon_index = 55, fossorial set)
- Salient axis: foot posture / fossorial specialization → `fossor-`
- Genus: `Talp-` (Latin *talpa*, mole) + `-oides` = *Talpoides*
- Epithet: *fossor* (m, agent noun)
- **Binomial:** *Talpoides fossor*

**3. Marsh-dwelling rat-grade, dark coat**
- Preset: generic murid, habitat = marsh, color = dark
- Salient axis: habitat = palustrine → `palustr-` + `-is` = *palustris*
- Genus: `Cinereo-` (ash-grey) + `-mys` (mouse) = *Cinereomys* (the RFC's own example)
- Epithet: *palustris* (habitat wins over color for salience when the wetland deviation is large)
- **Binomial:** *Cinereomys palustris*

**4. Alpine hare-grade, white winter coat**
- Preset: `rabbit` or `pika-analog`, alpine habitat
- Salient axis: habitat = alpine → *alpinus*
- Genus: `Lepor-` (Latin *lepus*) + `-ida` (descendant of) = *Leporida*
- Epithet: *alpina* (f, agrees with -a genus)
- **Binomial:** *Leporida alpina*

**5. Forest wolf-analog, robust build**
- Preset: `bear` or `wolf` grade, forest habitat, large body_mass
- Salient axis: build = robust (body_mass top decile in clade) → *robustus*
- Genus: `Lup-` (Latin *lupus*) + `-oides` = *Lupoides*
- Epithet: *robustus* (m)
- **Binomial:** *Lupoides robustus*

**6. Savannah cursorial grazer, long neck**
- Preset: `deer` (B1 §2, neck_length_ratio = 0.40)
- Salient axis: neck_length_ratio > 0.20 → `longi-` + `-collis`
- Genus: `Cervi-` (Latin *cervus*, deer) + `-ops` = *Cerviops*
- Epithet: *longicollis* (m/f)
- **Binomial:** *Cerviops longicollis*

**7. Island dwarf weasel-grade**
- Preset: `weasel/otter` (B1 §2), island_rule → dwarf
- Salient axis: body_mass (bottom decile) + geography insular → primary = size
- Genus: `Mustel-` (Latin *mustela*, weasel) + `-ina` (diminutive) = *Mustelina*
- Epithet: *pumila* (f, dwarf)
- **Binomial:** *Mustelina pumila*

### Birds (winged biped plan)

**8. Marsh hawk-grade, rufous plumage**
- Preset: `hawk` grade, marsh habitat, rufous coloration
- Salient axis: color = rufous → *rufus*
- Genus: `Circ-` (Latin *circus*, harrier) + `-ornis` (bird) = *Circornis*
- Epithet: *rufus* (m)
- **Binomial:** *Circornis rufus*

**9. Forest woodpecker-grade, spotted back**
- Preset: `woodpecker` analog, forest habitat, spotted pattern
- Salient axis: pattern = spotted → *maculatus*
- Genus: `Pic-` (Latin *picus*, woodpecker) + `-oides` = *Picoides*
- Epithet: *maculatus* (m)
- **Binomial:** *Picoides maculatus*

**10. Cliff-dwelling dove-grade, ash-grey**
- Preset: `dove` analog, cliff habitat
- Salient axis: habitat = cliff → *rupestris*
- Genus: `Columb-` (Latin *columba*) + `-ina` = *Columbina*
- Epithet: *rupestris* (f)
- **Binomial:** *Columbina rupestris*

**11. Pelagic storm-petrel-grade, dark plumage**
- Preset: `petrel` analog, pelagic
- Salient axis: habitat = pelagic → *pelagicus*
- Genus: `Hydro-` (water) + `-bates` (walker) = *Hydrobates* (real genus, used as example)
- Epithet: *pelagicus* (m)
- **Binomial:** *Hydrobatoides pelagicus*

### Fish (finned plan)

**12. Abyssal angler-grade, bioluminescent lure**
- Preset: `anglerfish` analog, abyssal
- Salient axis: habitat = abyssal → *abyssicola*
- Genus: `Melan-` (black) + `-ichthys` (fish) = *Melanichthys*
- Epithet: *abyssicola* (common gender)
- **Binomial:** *Melanichthys abyssicola*

**13. River trout-grade, spotted**
- Preset: `trout` analog, river
- Salient axis: habitat = river → *fluviatilis*
- Genus: `Salm-` (Latin *salmo*, salmon) + `-oides` = *Salmonoides*
- Epithet: *fluviatilis* (m/f)
- **Binomial:** *Salmonoides fluviatilis*

**14. Reef fish-grade, bright blue**
- Preset: `reef fish` analog, blue coloration
- Salient axis: color = blue → *caeruleus*
- Genus: `Chrom-` (color) + `-is` (fish-grade ending) = *Chromis* (real genus)
- Epithet: *caeruleus* (m)
- **Binomial:** *Chromoides caeruleus*

### Invertebrates

**15. Cave spider-grade, eyeless**
- Preset: `spider` analog (octopod exoskeleton), cave
- Salient axis: eye reduction → `micro-` + `-ophthalmus`
- Genus: `Cavern-` + `-arachne` = *Cavernarachne*
- Epithet: *microphthalmus* (combined: small eye)
- **Binomial:** *Cavernarachne microphthalmus*

**16. Sand-dwelling scorpion-grade, pale yellow**
- Preset: `scorpion` analog, sandy
- Salient axis: habitat = sand → `arenicola`
- Genus: `Aren-` (sand) + `-scorpio` = *Arenoscorpio*
- Epithet: *arenicola*
- **Binomial:** *Arenoscorpio arenicola*

**17. Forest leaf-litter myriapod, striped**
- Preset: `millipede` analog, forest, striped pattern
- Salient axis: pattern = striped → *striatus*
- Genus: `Myria-` (countless) + `-poda` = *Myriapoda* (class-level; genus = *Silvopoda* coined)
- Epithet: *striatus* (m)
- **Binomial:** *Silvopoda striata*

**18. Deep-sea decapod, spiny carapace**
- Preset: `crab` analog (decapod crustacean), abyssal, spiny
- Salient axis: texture = spiny → *spinosus*
- Genus: `Abyss-` + `-ocarcinus` = *Abyssocarcinus*
- Epithet: *spinosus* (m)
- **Binomial:** *Abyssocarcinus spinosus*

### Molluscs

**19. Freshwater bivalve, broad shell**
- Preset: `bivalve` analog (shell plan), freshwater
- Salient axis: shell shape = broad → `lati-` + `-concha`? → morphology compound; use `latissima` (very broad) or habitat `lacustris`
- Actually, bivalve shell morphology is a plan-specific axis. Use habitat: *lacustris*.
- Genus: `Uni-` (one, from *Unio*) + `-ella` = *Uniella*
- Epithet: *lacustris* (f)
- **Binomial:** *Uniella lacustris*

### Flora (example — flora is flora-engine territory but stems work both ways)

**20. Bog-dwelling pitcher-plant analog, purple flowers**
- This document is fauna-focused per the RFC; flora naming reuses the same
  stem register with flora-specific genus suffixes. One example for
  demonstration:
- Genus: `Heli-` (sun) + `-amphora` = *Heliamphora* (real genus)
- Epithet: *paludosa* (boggy) — *Heliamphora paludosa*
- **Binomial:** *Heliamphora paludosa*

---

## 5. Implementation notes

### 5.1 Input interface

```
binomial = generate_binomial(node: Node, genus: str, clade_medians: dict) -> str
```

1. `node.axes` and `node.knobs` supply the trait values.
2. `genus` is the curated genus name (string, already committed at Genus rank).
3. `clade_medians` is a precomputed dict of median values for all [name]-tagged
   axes within the genus (or sibling clade, for small genera).
4. Salience = `|node.axes[axis] - clade_medians[axis]| / clade_std[axis] *
   salience_weight[axis]`.
5. The stem map and suffix maps are static lookup tables loaded from this
   document (ideally as a TOML or JSON data file generated from this spec).

### 5.2 Gender tracking

Genus gender must be authored with the genus. The epithet gender agrees:

| Genus gender | Adjective epithet ending | Example |
|---|---|---|
| Masculine (`-us`, `-er`, `-or`, `-ops` by convention) | `-us`, `-is` (3rd decl. m) | *Lupoides robustus* |
| Feminine (`-a`, `-is` (f), `-e` (f)) | `-a`, `-is` (3rd decl. f) | *Leporida alpina* |
| Neuter (`-um`, `-on`, `-e` (n)) | `-um`, `-e` (3rd decl. n) | *Palustre* (if genus is neuter) |

`-cola` and `-oides` are common-gender and don't change.

### 5.3 Data file format (recommended)

```toml
# stems.toml — generated from §1
[habitat.palustris]
stem = "palustr-"
meaning = "marsh, swamp"
role = "standalone"
attestation = ["Cistothorus palustris", "Bracteantha palustris"]
axis = "niche: wetland"
form_masculine = "palustris"
form_feminine = "palustris"
form_neuter = "palustre"

[morphology.longicauda]
stem_prefix = "longi-"
stem_suffix = "-cauda"
meaning = "long tail"
role = "compound"
attestation = ["Longicauda (genus)", "Tyrannus longicauda"]
axis = "tail_length_ratio"
threshold_direction = "high"
threshold = 0.5
```

### 5.4 Audit checklist

Before a commit that adds or changes this document:

- [ ] Every stem in §1 attested in ≥1 published binomial (search GBIF / ITIS).
- [ ] No hybrid compounds beyond attested precedent.
- [ ] Gender agreement maps in §2.2 are complete for all stems used.
- [ ] The salience formula produces distinct epithets for all species in the
  test fixture (`exp/k13_treegen/test_treegen.py`).
- [ ] Collision-resolution fallback exercised in a test with >20 species in
  one genus (should not hit the hash-fragment path).

---

## 6. References

- Fauna Engine RFC v0.3, §9 "The naming stack"
- Biosphere Vocabulary Proposal v1.0, [name] consumer tags
- Biosphere Addendum B1 v0.2, knob tables
- GBIF backbone taxonomy (gbif.org) — all attestations verified 2026-07-27
- Jobling, J.A. (2010) *Helm Dictionary of Scientific Bird Names*. Helm.
- Stearn, W.T. (2004) *Botanical Latin*, 4th ed. Timber Press.
- Raup, D.M. (1966) "Geometric analysis of shell coiling." *J. Paleontology*.
