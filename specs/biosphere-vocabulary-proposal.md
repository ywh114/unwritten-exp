# Biosphere Vocabulary Proposal — Organs, Limbs, Traits, Interfaces

**Status:** v1.0 — swarm-researched, owner decisions resolved (§14) (2026-07-26). Companion to the Fauna Engine RFC v0.3 and Flora Engine RFC v0.1. The RFCs sketched the machinery; this document supplies the **content**: the authored lists the machinery consumes — empirically grounded in real biodiversity, then filtered through what the engine can actually afford.

**Ground rules (from the RFCs, sharpened):**

1. **Nothing here is new machinery.** Every item is one of:
   - an **axis**: a scalar (or small enum) with bounds, an adaptation *weight*, and a drift variance — the currency of the phylogenetics core;
   - a **part**: a named realization bound to a slot on a body plan, carrying axes;
   - a **slot**: a named anchor on a plan that parts bind to;
   - a **generic**: an abstract functional interface — the layer the ley operators rebind.
2. **Every axis must pay rent** (Fauna RFC §15 "trait-list creep"). Rent is paid to one or more consumers: the **stress function** (niche weights), **drift/runaway** (evolutionary forces), **identification keys** (field guide puzzles), **naming** (nickname fragments, binomial epithets), or **narration/gossip** ("shaggy", "the geese left early"). An axis no consumer reads is deleted.
3. **Closed-form only.** No organ gets its own simulation. A venom gland is `{present, potency, delivery}` — three scalars feeding hazard rates and gossip, not a toxicology model. Where a "powerful" feature is wanted, this document states the concrete cheap implementation.
4. **Convergence is the content.** The reason to survey real clades is to collect *multiple realizations per generic* (flight = feather | membrane | insectoid wing | patagium; the RFC's sub-variant tables, §6.5, pre-figured this). The tree invents lineages; the vocabulary guarantees each realization reads as a real solution.

---

## 0.1 Consumers (who reads the vocabulary)

Every axis/part below lists its **rent payers** in brackets:

- **[stress]** — feeds the niche stress function (weighted distance in the 24-dim month space + extension axes)
- **[drift]** / **[runaway]** — an axis the three evolutionary forces move on
- **[id]** — an identification key the field guide (jNaturalist) can pose puzzles with
- **** — must be drawable by the parametric illustration layer (a named anchor or path parameter)
- **[name]** — feeds nickname fragments or binomial epithets
- **[tell]** — narratable: gossip, chronicle lines, observer descriptions ("shaggy", "the geese left early")
- **[pop]** — feeds counters/trophic ratios (A2 §4 ratio sanity)


---

# PART I — FAUNA

## 1. Interfaces (generics)

The RFC defines nine: `locomotor`, `feeding organ`, `signal`, `covering`, `sensor array`, `sustenance`, `defense`, `support`, `storage`. The research reports support **two additions**, each with its own consumer set (additions are cheap — a generic is just a binding target plus an operator-rebind permission):

| Generic | Function | Rent payers | Notes |
|---|---|---|---|
| `locomotor` | movement through medium(s) | [stress][id][tell] | medium list = legal ranges; realization sets mobility class (A2 §3) |
| `feeding organ` | food capture/processing surface | [stress][id][name][pop] | beak/mouthpart type ↔ diet guild is the classic field-guide key |
| `signal` | display/communication organs | [runaway][id][name][tell] | runaway's home generic; acoustic organs are records with frequency/duty-cycle scalars |
| `covering` | integument + coloration | [stress][id][name][tell] | thermal axes (albedo, insulation) + pattern params |
| `sensor array` | sensing organs | [stress][id][tell] | acuity axes gate observation gameplay (can it detect *you*?) and activity pattern |
| `sustenance` | metabolic/internal processing (gut, fermentation, photosynthesis analog) | [stress][pop] | internal; carries diet-processing axes |
| `defense` | armor, weapons, chemical, behavioral escape | [stress][id][tell][pop] | hazard rates to/from player and predators |
| `support` | skeleton/size-bearing structure | [stress] | GIANT/TINY target; scale bar |
| `storage` | reserves vs bad times (RFC) | [stress][tell] | couples to seasonal-amplitude stress axis |
| **`respiration`** *(new)* | gas-exchange organ | [stress] | **why:** medium boundaries (fish/land ε=0 in A2 §3), amphibian dual-stage plans, hypoxia niches, altitude. Implementation: one enum {gills, lungs, tracheae, cutaneous, book-lungs, gills+lungs} + axes {air-breathing: none/facultative/obligate}. Drives barrier logic and stage-form legality. Cheap: one slot. |
| **`reproduction`** *(new)* | parity mode, mating hardware, brood structures | [stress][pop][tell][id] | **why:** generation-time clock (Fauna RFC §1) derives from the reproductive axis — this *is* the clock's slot; stage-forms (tadpole/caterpillar) bind here; fecundity/care axes feed counters; TSD, brood parasitism, semelparity are high-value [tell] content. Implementation: enum parity {oviparous, ovoviviparous, viviparous} + axes {fecundity, care_mode, stage_forms: 1–2}. | built external artifacts: webs, nests, cases, dams, bowers, mounds | [tell][pop][id] | **why:** ecosystem engineers (beaver-grade raising pond potential, Flora RFC §10.2 explicitly hooks this), trap-web predators, caddis cases, termite mounds. Implementation: enum artifact type + one magnitude scalar; artifacts render as patch decorations, not entities. |

**Rebinding rule** (Fauna RFC §2): regular evolution rebinds realizations within plan limits; ley operators rebind across them. One mechanism, two permission levels. **Multi-binding:** a part may bind a primary + secondary generic (bat wing = locomotor + radiator; antler = display + weapon; toucan bill = feeding + thermoregulation) — this is how real anatomy works and costs one extra field.

## 2. Body plans and slot maps

RFC's 13 plans, retained. Corals/sponges/bryozoans are flora-side. Each plan = spine path + named anchors (Fauna RFC §10.5) + legal slot set + default medium. Slots below are the *vocabulary*; a plan whitelists a subset.

### 2.1 Plan list (with research-grounded grounding)

| Plan | Real anchor clades | Medium default | Notes |
|---|---|---|---|
| tetrapod | mammals, birds (as biped variant), reptiles, amphibians | land | covers winged-biped as flag on limb.fore |
| winged biped | birds, bats (membrane wing variant) | air/land | could fold into tetrapod; kept for anchor-set sanity |
| finned | all fish grades | water | axial-swimmer body forms |
| hexapod exoskeleton | insects | land/air | 3 tagmata, 6 legs, wings 0–4 |
| octopod exoskeleton | arachnids | land | 2 tagmata, 8 legs, no antennae |
| decapod crustacean | crabs, lobsters, shrimp | water | biramous limbs, carapace |
| myriapod | centipedes, millipedes | land/soil | segment-count axis |
| shell (bivalve/gastropod) | molluscs I | water/land | shell morphology axes |
| cephalopod | octopus, squid | water | arms, jet, chromatophores |
| echinoderm | stars, urchins, cucumbers, crinoids | water | pentaradial, tube feet |
| worm-grade | annelids, nematodes, flatworms | soil/water/host | hydrostatic, peristalsis |
| soft-bodied pelagic | jellyfish, salps, ctenophores | water column | bell, tentacles; ley-adjacent |
| aerial buoyant | *(possibility space)* | air | magic-only reachable (RFC §6.2); gas bladder support |

### 2.2 Slot vocabulary (shared naming across plans)

Region anchors: `head.crown`, `head.snout`, `head.cheek`, `head.throat`, `dorsal.neck`, `dorsal.mid`, `dorsal.rump`, `ventral.throat`, `ventral.chest`, `ventral.belly`, `limb.fore.L/R`, `limb.hind.L/R`, `tail.base`, `tail.mid`, `tail.tip`, plus plan-specific: `wing.L/R`, `fin.dorsal/pectoral/pelvic/anal/caudal/adipose`, `mantle.edge`, `arm.1..8`, `disc.margin`, `segment.N`.

Slots are typed; a slot declares which generics may bind there (`tail.tip` accepts signal (rattle, fan, lure), defense (stinger), storage (fat tail), locomotor (fluke)...). This is the entire legality machinery for both evolution and ley operators: an operator is `rebind(generic, slot, new_realization)` — flat, enumerable, veto-able.

## 3. Organs & limbs — the parts vocabulary

Organized by generic. Each realization: **name — real clades — {parameterizing axes} — [consumers]**. This is the authoring checklist; the RFC's rule applies: *a plan earns a part if a folk family or a biome visibly needs it*, and every axis feeds a consumer.

### 3.1 `locomotor` realizations

**Powered flight** (the canonical convergence set — pre-figures Fauna RFC §6.5 sub-variant tables: `wings ∈ {feathered, membrane, insectoid, crystalline, light}`):
- feathered wing — birds — {planform: elliptical / high-aspect soaring / high-speed pointed / slotted-soaring; wing loading; tail-fan size} [id][stress]
- membrane wing on digits II–V — bats — {membrane extent (incl. tail?), aspect ratio} [id]
- membrane wing on one hyper-digit — pterosaur-grade — {wing-finger length, crest coupling}  (deep-history flavor; also a ley realization)
- insectoid wing — insects — {pair count 1–2; forewing type: elytron / tegmen / hemelytron / membranous / scaled; halteres bool} [id]
- **shared convergent axes:** body-mass reduction, pneumatic bones bool, sternal keel depth [stress]

**Gliding** (>60 real lineages — cheap: `locomotor.mode=glide` + membrane part):
- limb patagium — colugo/flying squirrel/sugar glider — {membrane area, tail flattening} [id]
- rib-supported membrane — Draco — {rib count/length} [id]
- enlarged pectoral fins — flying fish — {fin area} 
- dermal flaps / body flattening — gliding geckos, flying frogs, gliding snakes — {flap extent, webbing} 

**Swimming:**
- axial undulation spectrum — {anguilliform / subcarangiform / carangiform / thunniform(lunate) / ostraciform(box)} [stress][id]
- flipper/hydrofoil — ichthyosaur-, turtle-, penguin-, seal-, whale-grades — {aspect ratio, fluke horizontal vs vertical} [id]
- rowing limbs — water beetles, boatmen — {limb flattening, fringe} 
- jet propulsion — cephalopods, scallops, jellyfish — {mantle muscularity, siphon steerability} [id]
- median/paired-fin propulsion — rays, seahorses, triggerfish — 
- fin set (fish): dorsal/pectoral/pelvic/anal/caudal/adipose + finlets, each {presence, size, spine-vs-soft, shape enum: heterocercal/homocercal/forked/lunate/rounded/continuous/absent} [id] — fin shapes are classic ichthyology ID keys, free [id] value
- sand-swimming — skink-grade — {snout wedge, limb reduction degree} [tell] (RFC's SAND-SWIM operator is the ley version; the regular realization must exist first)
- surface-tension walking — water striders, basilisk-grade — {foot area, fringe} [tell]

**Terrestrial:**
- cursorial limb set — {digit count reduction (5→1), unguligrade/digitigrade/plantigrade enum, tendon-spring bool} [stress][id]
- saltation set — kangaroo/jerboa/springhare-grade — {hind:fore ratio, metatarsal fusion} 
- fossorial set — mole/golden-mole/mole-cricket grades — {spade-hand, sesamoid pseudo-thumb bool, eye reduction, pinna loss} [stress][tell]
- scansorial/climbing — {claw curvature, opposable digits, adhesive pads enum: setae (gecko) / wet-adhesion discs (frog) / tarsal pads (insect)} [stress][id]
- prehensile tail — {strength, tactile pad bool} [tell]
- brachiation — {arm elongation, hook-hand} 
- serpentine — {vertebra/segment count, mode enum: lateral-undulation/concertina/rectilinear/sidewinding; limb-reduction gradient} [id][stress]
- peristalsis/hydrostatic — worm grades — {segment count, chaetae bool} 
- ciliary/mucus glide — flatworm/snail grades — 

### 3.2 `feeding organ` realizations

**Vertebrate jaw/teeth:**
- heterodont dentition — mammals — {dental formula I/C/P/M; molar type: bunodont / hypsodont (grazer) / selenodont / lophodont / carnassial-shear index} [stress][id][pop] — molar type ↔ diet is textbook ratio-sanity grounding
- ever-growing incisors — rodents (1 pair), lagomorphs (2 pairs — the folk-visible distinction!) — {diastema} [id][name]
- beak/rhamphotheca — birds, turtles, cephalopods (convergent ×3) — bird beak shape classes {conical-seed / tweezer-insect / hooked-flesh / chisel-wood / probe / lamellate-filter / nectar-tube / crossed / spatulate / skimmer / saw-edged / pouch / upside-down-filter} [id][stress][name] — beak class = diet guild made drawable
- fang/venom delivery — {aglyphous / opisthoglyphous / proteroglyphous / solenoglyphous} + spitting bool [id][tell][stress]
- tusks — {source tooth: incisor/canine, length, curl} [name][tell]
- pharyngeal jaws — moray/cichlid/cyprinid — {tooth shape} [tell][id] (cichlid-grade lake radiation key innovation)
- baleen / lamellate filter / gill rakers — {plate length & fringe fineness / lamellae density / raker count} [id][pop] (filter-feeder guild, three independent substrates; MANA-FILTER's regular anchor)

**Invertebrate mouthparts** (single ground plan → divergent realizations — exactly the clade-steady-trait mechanism):
- mandibulate (chewing) — {mandible size, molar region} [id]
- piercing-sucking stylets (rostrum) — bugs/mosquitoes — {stylet length} [id]
- siphoning coiled proboscis — Lepidoptera — {length (can exceed body)} [id]
- sponging labellum — flies — [id]
- chewing-lapping glossa — bees — {tongue length} [id][pop] (pollinator coupling, Flora RFC §5!)
- rasping-sucking — thrips
- chelicerae + pedipalps — arachnids — {fang orientation, pedipalp form: leg-like / chelate / raptorial} [id]
- radula — molluscs — {type: grazing / harpoon-toxoglossan; magnetite hardening} [tell][id]
- cephalopod beak + arm crown — {arm count, suckers vs hooks} [id]
- forcipules (venom legs) — centipedes [id]
- labial mask — dragonfly nymphs [id] (stage-form differentiator!)
- cirri / lophophore / siphons — sessile filter feeders 
- lure (illicium+esca, tongue lure, caudal lure) — {lure shape, luminous bool} [tell][id] — feeding + signal multi-bind

**Tongue/proboscis specials:** ballistic tongue (chameleon), hyoid-supported long tongue (woodpecker/anteater/hummingbird — 3 independent), forked chemotongue (snake/monitor), rasping papillae tongue (cat), elephant-grade trunk {length, tip fingers 0–2} [tell][name]

### 3.3 `sustenance` (internal processing)

- gut architecture: {rumen 4-chamber / 3-chamber camel-grade / foregut-ferment (kangaroo, hoatzin-grade) / hindgut-cecum (horse, rabbit, koala) / simple} [stress][pop][tell]
- crop + gizzard — {crop capacity, crop-milk bool, gizzard muscularity} [tell][pop] ("crop milk" is exactly the uncanny-good Tier-1 flavor)
- spiral valve (shark), gastric mill (crustacean), pharyngeal mill
- metabolic axes: {BMR level, torpor mode: none/daily/hibernation/aestivation + months} [stress][tell] — drives seasonal presence toggling (geese-left-early gossip)
- osmoregulation: {salinity band, salt glands bool, euryhaline bool, anadromy/catadromy enum} [stress] — extension-axis food
- regional endothermy (tuna-grade rete mirabile) [stress]

### 3.4 `sensor array` realizations

- camera eye — {pupil shape: round/vertical-slit/horizontal-slit/W; tapetum bool + eyeshine color; placement: frontal-binocular vs lateral; fovea count} [id][tell] (pupil shape is a gorgeous folk-ID key: slit = ambush, bar = prey)
- compound eye — {ommatidia count, apposition/superposition} 
- ocelli/simple eyes — {count, arrangement} [id]
- parietal (third) eye — tuatara-grade [tell]
- ears: pinnae {size (Allen-rule axis!), mobility, tufts}; tympanum {position: head/abdomen/legs}; ear asymmetry (owl-grade) [stress][id][name]
- facial disc (owl/harrier-grade) [id]
- lateral line + ampullary electroreception — {pore density, rostrum/bill substrate} [stress][tell]
- active electrogenesis + tuberous sense (weakly electric fish-grade) — {voltage, waveform} [tell]
- echolocation — {type: laryngeal bat-grade / melon+phonic-lips whale-grade / tongue-click / crude-shrew-grade; noseleaf complexity; call frequency} [tell][id]
- infrared pits — {pit position: loreal/labial; depth} [tell][id]
- chemosensation: forked tongue + Jacobson / antennae {type enum: filiform/pectinate/lamellate/clubbed/aristate; length} / barbels {count, length} / VNO-flehmen / bill-tip organ (kiwi/snipe-grade remote touch) [id][tell]
- vibrissae/whiskers — {count, length} [name]
- magnetoreception — {map/compass} [stress] (migration machinery)
- exotic tactile: star-nose rays {count}, Eimer's organs, pectines (scorpion), halteres, statocyst [tell]

### 3.5 `covering` realizations + coloration

- integument types: fur {density, underfur:guard ratio, crimp} / feathers {down loft, powder-down bool, waterproofing} / epidermal scales {keeled/smooth, scutes} / dermal scales {placoid/ganoid/cycloid/ctenoid} / chitin cuticle {sclerotization, calcification} / slime coat {viscosity, thread-reinforced (hagfish-grade)} / bare glandular skin (amphibian) / keratin scales (pangolin-grade) [stress][id][name]
- thermoregulation parts: blubber {thickness}, radiator surfaces (ear area, dewlap, bill-as-radiator, wattles), countercurrent rete bool, sweat/panting/gular-flutter enum [stress]
- **coloration machinery** (RFC's per-clade pigment set + pattern params, grounded): {pigment palette: melanins/carotenoids(diet-derived!)/structural; mechanism: pigmentary / structural-interference / chromatophore-dynamic (speed, neural vs hormonal); pattern per region: spots/stripes/bands/countershading/disruptive; function flags: crypsis / aposematism / mimicry(bool + model link) / counterillumination (ventral photophores)} [id][name][tell][stress] — Gloger's rule couples palette to humidity [stress]; mimicry links two records, an [id] puzzle for free
- seasonal molt dimorphism (ptarmigan/ermine-grade) [tell][stress]

### 3.6 `signal` realizations

- ornaments (runaway's playground): antlers {tine count, span; bone, shed annually} / horns {keratin-on-bone, permanent / pure-keratin rhino-grade / ossicones / pronghorn hybrid} / crests & casques / dewlaps & wattles & combs & snoods / manes / tail fans & trains & wire-plumes / inflatable sacs (gular, esophageal) / ear tufts [runaway][id][name][tell] — substrate distinction (bone antler vs keratin horn vs ossicone) is clade-steady, i.e. Order-level [id]
- acoustic organs: syrinx {complexity, dual-voice} / larynx + resonator (howler hyoid-grade) / vocal sacs {single/paired} / stridulation {mechanism: wing-file / leg-wing / tymbal} / rattle (keratin segments — defense signal) / percussion drumming / winnowing tail feathers [tell][id] — acoustic records are scalars (frequency, duty cycle), no audio engine needed; gossip and "heard at dusk" rendering carry them
- chemical: pheromone/scent glands {placement enum: anal/temporal/dorsal/castor/civet/musk-pod; spray vs smear} [tell][defense secondary]
- bioluminescence: photophores {placement, color, pattern: steady/pulsing/rippling/constellation — RFC §6.5's sub-variant table is real}; intrinsic vs symbiotic-bacterial; lure/counterillumination/burglar-alarm functions [tell][id]

### 3.7 `defense` realizations

- armor: shell {carapace/plastron doming, hinge bool} / osteoderms {coverage, keeling} / armadillo-grade banded carapace {band count} / elytra / bivalve/gastropod shell {coil direction, spire, sculpture, operculum} / urchin test + spines [id][stress]
- spines/quills: {source: modified hair / fin spine / barb; detachable, barbed, venom-channel bool, lockable bool} [id][tell]
- chemical: venom {potency, type: neuro/hemo/cyto, delivery link to feeding organ or stinger/spur} / poison skin {potency, diet-sequestered bool — links to sustenance!} / sprays {skunk-grade aimed / bombardier-grade pulsed-hot / spitting-cobra-grade / acid} / ink {cephalopod-grade pseudomorph} / slime-choking (hagfish) [tell][stress][id]
- autotomy {breakage plane location, regeneration fidelity, wriggle-decoy} / evisceration (cucumber-grade) / thanatosis (death-feigning) / deimatic startle display (hood, frill, eyespot-flash) / inflation (puffer-grade) / conglobation (roll-up) [tell][id]
- aposematism & mimicry — cross-linked records (§3.5) [id][tell]

### 3.8 `storage` realizations (RFC's list, grounded)

fat depots {location: blubber / hump(1–2) / fat tail / fat body(insect)} / water storage {bladder cisterns, cocoon aestivation} / cheek pouches {volume, internal/external} / crop storage / social storage morphs (honeypot repletes — caste coupling) / caching behavior {scatter-hoard / larder / granary / haypile} [stress][tell][name] ("hump", "fat-tailed" are nickname fragments)

### 3.9 `respiration` realizations (new generic)

gills {filament area, external-larval bool} / lungs {paired vs single-functional (snake asymmetry)} / tracheae + spiracles / book lungs {lamella count} / cutaneous {percent contribution; lungless-salamander-grade bool} / accessory air-breathing {organ enum: labyrinth / gut / skin / mouth-lining; obligate vs facultative} / cloacal bursae (turtle-grade, [tell] gold) [stress] — the medium-legality table reads this generic: `gills-only` ⇒ land boundary ε=0 except flood events (A2 §3), `facultative air` ⇒ amphibious ranges, stage-form transitions rebind it (tadpole gills → frog lungs).

### 3.10 `reproduction` realizations (new generic)

- parity: {oviparous / ovoviviparous / viviparous} + egg type {hard-shell / leathery / gelatinous / ootheca / broadcast-pelagic / egg-case ("mermaid's purse") / foam nest} [pop][tell][id]
- fertilization: {external / internal; sperm storage bool; TSD (temperature sex determination) bool — crocodile/turtle-grade [tell]} 
- metamorphosis: {stage_forms: 1–2 (RFC cap); mode: ametabolous / hemimetabolous / holometabolous / amphibian-tadpole; larval medium + larval feeding organ (caterpillar chews, adult sips — two feeding bindings per record!); neoteny axis (axolotl-grade: breeds as larva)} [stress][id][tell] — the RFC's "merging stage-forms is an identification puzzle" is implemented right here: two stage records + one transition month
- parental care: {none / guard / mouthbrood / brood pouch (seahorse-grade, male) / skin-embedding (Surinam-grade) / tadpole-transport / trophic eggs / nest-guard + assisted hatch (crocodile-grade) / milk (mammary / crop-milk / tsetse-grade)} [pop][tell]
- mating system & sociality coupling: {monogamy/polygyny/lek/promiscuity; sex-biased dispersal follows Greenwood's rule from mating system} [pop][stress]
- semelparity bool (salmon/octopus-grade "big bang") [pop][tell]

## 4. Fauna trait axes (the flat list)

Axes not tied to a specific part. Format: `axis — range/type — [consumers]`.

### 4.1 Size & morphometrics
- body_mass (log; the master axis — generation clock, abundance (Damuth), home range, lifespan all derive) [stress][pop][name]
- limb proportion indices (intermembral, hind:fore, metatarsal:femur) [stress]
- tail:length ratio; neck length; snout length; ear size (**Allen-rule axis**); ornament:body ratio [id][name]
- sexual size dimorphism ratio (Rensch coupling) [tell][pop]
- relative brain size (low weight, mostly [tell] — gossip about "clever" corvid-grades)

### 4.2 Ecogeographic rule axes (implemented as stress-descent couplings, not free axes)
| Rule | Implementation |
|---|---|
| Bergmann | cold stress → +mass weight in endotherm clades [stress] |
| Allen | cold stress → −appendage size (ears, tail, bill) [stress] — the RFC's own example; must be drawable |
| Gloger | humidity → +melanin; aridity → pale/red [stress][name] |
| Island rule | isolated fragment → mass toward ~intermediate, sign from current mass; + reduced wariness, −dispersal [stress][tell] — vicariance rounds get this free |
| Rapoport | high-latitude lineages → wider niche tolerance vector [stress] |
| Cope's (optional) | runaway-optional +mass bias per clade |

### 4.3 Niche & activity (niche-vector extension axes beyond the 24-dim base)
diet guild (enum from §5.1) + niche_breadth (0–1) / trophic_level / vertical stratum (fossorial/ground/understorey/canopy/aerial or benthic/demersal/pelagic + depth band) / activity period (diurnal/nocturnal/crepuscular/cathemeral) / seasonality mode (resident / migrant-latitudinal / migrant-altitudinal / irruptive / nomadic / hibernator / aestivator) + migration distance & two-range fields (RFC §3) / dormancy months / salinity band / flow class (rheophile↔lentic) / temperature optimum + breadth / hypoxia tolerance / flora-provision dependencies (links flora output: mast, graze, nectar) / human-presence affinity (reserved per RFC) [all stress, many tell/id]

### 4.4 Life history (clock + counters)
r–K continuum (derived: r ∝ M^−0.25 + deviation term) / fecundity / parity (semelparous bool) / parental care duration + mode / lifespan (mass allometry × volant/fossorial modifiers) / generation time (derived — **this is the g-clock**, RFC §1) / natal dispersal distance + sex bias (Greenwood) [pop][stress][tell]

### 4.5 Social & behavioral
social system (solitary/pair/family/pack/herd/flock/school/colony/fission-fusion/eusocial/lek) / group size + cohesion / territoriality / mating system / caste system (for eusocial: caste count + soldier morphs) / wariness (flight-initiation distance scalar — drives render-boundary flee and hunting gameplay) / crypsis↔aposematism reliance / mobbing propensity / vigilance [pop][tell][stress]

### 4.6 Ecosystem roles (quantity-layer couplings)
engineer_impact (0–1; beaver-grade — couples to pond potential as a quantity-layer modifier, per Flora RFC §10.2; no artifact system, no `construction` generic — see §14 note) / keystone flag / mutualist links (pollination, seed dispersal, cleaner stations — record links, feed Flora F3 coupling) / parasitism (flag tier per RFC §13: ecto/endo/brood/klepto/parasitoid enum, no full records) [pop][tell]

## 5. Ratio-sanity grounding numbers (A2 §4's "pyramid", made concrete)

For C6 counter validation:
- energy transfer ~10%/trophic level (Lindeman); chains ≤4–5 levels
- herbivore density ∝ M^−0.75 (Damuth); carnivore biomass ≈ 1–10% of prey biomass
- home range ∝ M^~1 (terrestrial; >1 carnivores, <1 herbivores)
- reference densities: mouse-grade 10–100/ha; deer-grade 1–10/km²; wolf-grade ~1/100–300 km²
- group size scales with body mass (herbivores) and prey size (carnivores)


---

# PART II — FLORA

Mirror structure. Flora-side "body plans" are **growth forms**; "organs" are slot-bound structures on six slots (RFC): `architecture`, `leaf`, `root`, `display`, `fruit/seed`, `defense`, plus two proposed additions below. Corals, sponges, bryozoans, tube worms are flora-side (sessile structural, RFC §2).

## 6. Flora interfaces (generics)

RFC mapping: `signal`→display organs, `support`→architecture, `feeding organ`→root/leaf chemistry, `defense`, `storage`→tubers/bulbs/rhizomes, `locomotor`→`dispersal`. Grounded additions/confirmations:

| Generic | Flora realization space | Rent payers |
|---|---|---|
| `support` | architecture: height, woodiness, wood density, branching grammar (§7.2) | [stress][pop] |
| `feeding organ` | nutrient economy: photosynthesis grade (C3/C4/CAM), N-fixation, carnivory, parasitism, mycoheterotrophy, mycorrhizal dependence, saprotrophy (fungi), chemosymbiosis (vent-grade) | [stress][pop][tell] |
| `signal` | flower/inflorescence morphology + color, phenology; spore displays (fungi); pollination-syndrome trait bundles | [runaway][id][name][tell] |
| `dispersal` | fruit/seed/spore morphology per channel (wind/water/animal/ballistic/clonal) | [stress][id][tell] |
| `defense` | thorns/spines/prickles (distinct!), trichomes, silica, chemical classes, ant mutualism | [stress][id][tell] |
| `storage` | tubers/bulbs/corms/rhizomes, succulent tissue, caudex, seed endosperm, lignotubers | [stress][tell][name] |
| **`covering`** *(new for flora)* | bark (thickness — fire axis), cuticle/waxes, pubescence, resin/latex exudates | [stress][tell] — bark thickness ↔ fire regime is a first-class axis; cheap enum+scalars |
| **`phenology`** *(new for flora)* | leaf-out/senescence/bloom/fruit timing, deciduousness mode (winter vs drought — distinct triggers!), masting interval, serotiny | [stress][tell][id] — the RFC's "phenology flips leaf/flower layers by month" needs a slot to live in; one slot with month-vector scalars. EVERbloom operator's home. |

## 7. Growth-form plans & slot maps

### 7.1 Terrestrial plans (RFC list, research-validated)
tree / shrub / subshrub / herb-forb / grass-sward (tussock vs sod axis) / rosette-mat (incl. **giant-rosette** afroalpine/páramo convergence — a flag: `giant_rosette`) / cushion / succulent (stem vs leaf vs caudex sub-flag) / vine-liana (2nd-round-only) / epiphyte (2nd-round-only) / fern-grade / moss-grade / lichen-grade (crustose/foliose/fruticose axis) / fungus-honorary (fruiting-body plan) / **bamboo-grade** (woody grass, mass semelparous flowering — flag on grass plan). 

### 7.2 Tree architecture — the Hallé-model grammar (big research payoff)
23 real tree architectures are generated by a **small rule tuple**, which is exactly how the clade machinery works (clade-steady traits at Order rank):
```
arch_grammar = {
  axes: monoaxial | polyaxial
  growth: rhythmic(tiers) | continuous
  flowering_position: terminal | lateral   (terminal → sympodial)
  branch_orientation: orthotropic | plagiotropic
  branching: monopodial | sympodial,  proleptic | sylleptic
  reiteration_propensity: 0–1
} + scalars {apical_dominance, branch_angle, internode_length, tier_spacing}
```
Named archetypes become clade presets: unbranched-terminal (palm/Corner-grade), monocarpic (agave/Holttum-grade), whorled-conifer (Rauh-grade), tiered-pagoda (Massart/Aubréville-grade), forked-tiers (Leeuwenberg-grade). [id][tell] — corner-rule allometry (thicker axes ↔ larger leaves) as a constraint, not an axis.

### 7.3 Aquatic plans (RFC list + grounding)
benthic rosette / rhizome-hardscape / runner-meadow (seagrass-grade) / floating-leaf / floater / macroalgae-holdfast — kelp anatomy decomposition: **holdfast → stipe → blade → pneumatocysts {count, placement}**, annual/perennial axis [id] / phytoplankton-grade (counters only) / **mangrove-grade** (terrestrial plan + high HAND tolerance + pneumatophore/stilt-root parts, per RFC marginals note) / **coral-grade** (colonial modular: polyp module × growth morphotype {massive/branching/plating/foliose/encrusting/free}) / sponge-grade (ascon→sycon→leucon complexity axis).

### 7.4 Non-vascular & fungus plans
moss-grade (acrocarp cushion ↔ pleurocarp mat axis; sphagnum water-storage flag) / liverwort-thalloid / fern-grade (frond division order, fiddlehead vernation) / lycophyte-grade (strobilus cones; resurrection-plant flag) / fungus: fruiting-body form enum {agaric-gilled / bolete-pored / bracket-conk / tooth / coral / puffball / earthstar / cup / morel / stinkhorn / truffle-hypogeous / mold / cordyceps-club} — hymenophore type is the [id] key / lichen: {crustose / leprose / squamulose / foliose / fruticose / gelatinous} + photobiont axis / slime-mold-grade (honorary).

## 8. Flora parts vocabulary (by slot)

### 8.1 `leaf` slot
shape enum {needle/scale/linear/lanceolate/elliptical/ovate/cordate/reniform/hastate/spatulate/lobed-pinnatifid/lobed-palmatifid} / margin {entire/serrate/toothed/spinose — toothed↔cold rule} / compoundness {simple/pinnate/bipinnate/palmate/trifoliate} / phyllotaxis {alternate/opposite/whorled/basal-rosette/distichous} / persistence {evergreen/winter-deciduous/drought-deciduous/marcescent} + leaf lifespan / size (warm-wet rule) / SLA (leaf economics spectrum) / **modified forms**: succulent / spinescent / phyllode / cladode / **carnivorous traps** {pitfall-pitcher/snap/flypaper/suction-bladder/lobster-pot} / drip tips (everwet flag) / variegation & underleaf color / window leaves (buried-grade) [id][stress][name]

### 8.2 `root` slot
system type {tap/fibrous/adventitious/aerial-velamen} / specials: pneumatophores / stilt-prop roots / buttress / knee roots / contractile / haustoria (parasite) / storage roots & tubers / symbiont bindings: mycorrhizal type {arbuscular/ecto/ericoid/orchid/none}, N-fix nodules {rhizobium/frankia/cyanobacterial/none} / axes {depth, root:shoot ratio} [stress][tell]

### 8.3 `display` slot (signal)
flower symmetry {radial/zygomorphic/composite-head} / merosity {3/4–5} / **inflorescence grammar** {raceme/spike/catkin/panicle/corymb/umbel/head-capitulum/spikelet/spadix+spathe/solitary} / sexuality {perfect/monoecious/dioecious} / **pollination syndrome bundle** (canonical correlated sets — one enum pulls the whole trait cluster: wind→small, petal-less, catkins, pre-leafout; bee→yellow/blue UV-guides + landing platform; moth→white night-scent + long spur; bird→red odorless copious nectar; bat→large dull night + musty + cauliflory; beetle→bowl thermogenic; fly→carrion-mimic dark foetid) [runaway][id][name][tell] — syndrome enum is one axis doing ten axes' work; the F3 pollinator-coupling round descends exactly this axis
fungal analogs: hymenophore display, spore-mass color, stinkhorn lures; coral spawning synchrony flag

### 8.4 `fruit/seed` slot (dispersal)
fruit type {berry/drupe/pome/hesperidium/pepo/aggregate/multiple/capsule/follicle/legume-pod/silique/achene/caryopsis/nut/samara/schizocarp/cypsela} / dispersal morphology per channel: wind {winged-samara/plume-pappus/dust/tumbleweed}, animal {fleshy reward: lipid vs sugar; hooks/burs; elaiosome-ant}, water {buoyant, corky husk}, ballistic {explosive dehiscence} / propagule mass / terminal velocity / seed bank {transient/persistent} / **serotiny** (fire-opened) bool / masting interval / clonality {rhizome/stolon/bulb/corm/tuber/sucker/apomixis/viviparous-propagule; spread distance} [stress][id][tell] — clonality axis feeds CLONAL BLOOM; dispersal channel weights are the Flora RFC §3 kernel weights directly

### 8.5 `defense` slot
mechanical: **thorn (stem) / spine (leaf/stipule) / prickle (epidermal)** — three distinct origins, clade-steady [id]; trichomes {glandular/stinging/hooked}, glochids, silica phytoliths (grass), raphide crystals, sclerophylly / chemical classes {alkaloid/cyanogenic/cardiac-glycoside/glucosinolate/tannin/saponin/latex-resin/essential-oil} {constitutive vs induced} / ecological: ant mutualism {extrafloral nectaries/domatia/hollow-thorn myrmecophyte}, mimicry, tolerance-vs-resistance axis [stress][id][tell] — chemical classes are one enum + potency scalar; no chemistry sim

### 8.6 `feeding organ` slot (nutrient economy)
photosynthesis grade {C3/C4/CAM + facultative-CAM flag} / N-fixation (link to root nodules) / carnivory (link to leaf traps; needs insect counters — RFC open question 7, recommend fauna-coupled via provision math) / parasitism {hemi/holo; host specificity} / mycoheterotrophy bool (deep-shade forest coupling) / saprotrophy {white-rot/brown-rot/soft-rot/litter/dung} for fungi / halophyte package {salt-exclusion/salt-glands/succulent-dilution} / xerophyte package / hydrophyte package {aerenchyma, floating-leaf stomata} / resurrection (poikilohydry) bool / chemosymbiosis (vent tube-worm-grade: no gut, symbiont trophosome) [stress][pop][tell]

### 8.7 `storage` slot
tuber/bulb/corm/rhizome (geophyte = cryptophyte life form) / succulent water tissue (stem vs leaf vs caudex-bottle-tree) / lignotuber-burl (fire resprout) / seed endosperm size [stress][tell][name]

### 8.8 `covering` slot
bark {thickness (fire axis), texture: smooth/furrowed/peeling/corky} / cuticle & waxes / pubescence (silvery reflectance) / latex & resin exudates / epiphyte-load tolerance (host surface) [stress][tell]

### 8.9 `phenology` slot
leaf-out month window / deciduous trigger {winter/drought/none} / bloom window {start, length} (release-month selects the wind field — Flora RFC §3's mechanism lives here) / fruiting window / masting interval / serotiny flag / synchronous-flowering (bamboo-grade monocarpy: interval + dies-after) [stress][tell][id]

## 9. Flora trait axes (flat list)

Raunkiær life form (phanero/chamae/hemicrypto/crypto(geophyte)/therophyte/hydrophyte — climate-correlated, one enum) / height / woodiness / wood density / growth rate / longevity (bristlecone-grade extreme tail) / shade tolerance (recommend **one axis**, seedling-adult split deferred — answers RFC open question 3 cheaply) / pioneer↔climax (CSR: competitor/stress-tolerator/ruderal position) / drought tolerance / salinity tolerance / waterlogging tolerance / growing-season requirement / soil fertility requirement / fire strategy {resprouter/seeder/avoider} + bark thickness / clonal spread distance / jump-rate (long-distance dispersal, clade axis per RFC §3) / coloniality (solitary↔clonal colony; module size — coral/fungus/aspen-Pando-grade) [all stress, many id/tell]

**Constraint rules** (enforced at sampling time, like fauna's diet↔habitat↔size conditionals — research-grounded):
CAM↔succulence↔aridity-or-epiphyte · C4↔warm-season open habitat · wind-pollination↔small petal-less + pre-leafout · bird-syndrome↔red+odorless · serotiny↔fire-prone regime · spinescence↔aridity+herbivore pressure · large leaves↔warm-wet · toothed margins↔cold · dioecy↔fleshy fruit+island · mycoheterotrophy↔deep-shade+fungal host · lianas↔seasonal tropics · pneumatophores↔waterlogged anaerobic · buttress↔shallow tropical soil+emergent height · giant-rosette↔high-elevation frost tropics

---

# PART III — INTEGRATION

## 10. Diet/trophic guild enum (fauna, shared with flora provisions)
grazer / browser / folivore / frugivore / granivore / nectarivore / fungivore / insectivore / piscivore / molluscivore / myrmecophage / vermivore / carnivore(apex/mesopredator) / scavenger / filter-feeder / detritivore / sanguivore / durophage(bone-crusher) / omnivore / parasite(§4.6) / planktivore — each maps to flora/fauna provision types (mast, graze-sward, browse, nectar, prey counters) for the pop-coupling.

## 11. Authoring schema sketch
```yaml
# axis record (one line of the flat trait list)
- name: ear_size
  slot: head.cheek
  plan_scope: [tetrapod, winged_biped]
  bounds: [0.0, 1.0]        # relative to body_mass^1/3
  weight: 0.8               # adaptation weight (thermal, Allen coupling)
  drift_var: 0.05
  consumers: [stress, id, name]
# part record
- name: feathered_wing
  generic: locomotor
  slots: [wing.L, wing.R]
  plans: [winged_biped]
  axes: [wing_planform, wing_loading, tail_fan_size]
# generic record
- name: respiration
  realizations: [gills, lungs, tracheae, book_lungs, cutaneous, accessory_air]
  operator_rebinds: [LAVA-ADAPT, SAND-SWIM, ICE-PHASE]  # ley permission list
```

## 12. Anti-creep audit (enforced at content-commit time)
1. Every axis names ≥1 consumer; consumer-less axes rejected (the validator already has this shape: "trait must feed stress, drift, identification, or narration" — Fauna RFC §15).
2. Every part binds ≥1 generic and ≥1 plan; orphan parts rejected.
3. New generics require: rent payer list + ≥2 realizations + operator-table row. (This document adds exactly 3 fauna + 2 flora; expect very few more.)
4. Enum growth (beak classes, fruit types) is cheap and welcome; scalar-axis growth is suspect; new *slots* are schema-level changes.
5. Folk-label vocabulary is mined from these records (size percentiles, covering axes, habitat words) — never free-authored (Fauna RFC §9).

## 13. What this gives the ley operator table for free
- `SWIMS-AIR`, `SAND-SWIM`, `FLIES`: regular realization catalogs (§3.1) supply the "geometry kept" source forms and the sub-variant tables (§6.5).
- `MANA-FILTER`: three filter-feeding substrates (baleen/lamellae/rakers) as anchors.
- `GLOW`: photophore placement/pattern vocabulary (§3.6) is the regular-grade version.
- `RESONANT`: sensor-array exotic modalities (electroreception, IR pits, magnetoreception) are pre-existing "sense the invisible" realizations — ley-sense is one more modality in the same slot.
- Flora operators map to slots 1:1: `BUOYANT`→support, `EVERBLOOM`→phenology, `SPORE-FOG`→dispersal, `PHASE-ROOT`→root, `VOLATILE`→fruit/seed, `CLONAL BLOOM`→clonality axis, `REDUCE [slot]`→any slot (slots are enumerable).

## 14. Design decisions (resolved with repo owner, 2026-07-26)
1. **New generics accepted: 2 fauna + 2 flora.** `respiration` and `reproduction` (fauna), `covering` and `phenology` (flora) are accepted — each has distinct consumers and operator targets; folding them into `sustenance`/existing slots would reproduce the "untargeted generics" problem. The proposed third fauna generic, `construction` (built artifacts: webs/dams/nests), was **dropped on review**: it smuggled in an artifact system the engine does not have. Ecosystem engineering survives as the `engineer_impact` scalar axis (§4.6) only.
2. **Dropped-generic rule:** a dropped generic may leave exactly one scalar axis as residue (as `construction` → `engineer_impact`), provided the residue axis independently passes the rent audit (§12 rule 1). This prevents both artifact-system creep and unlimited generic growth.
3. **Coral/sponge/bryozoan ownership: flora generator owns them entirely** — one owner, no cross-engine records; animal-ish parts (polyps, tube feet) are flora-side parts records.
4. **Parasites stay flag-tier** (Fauna RFC §13), **plus one exception**: a `brood_parasite: bool` enum on the `reproduction` generic (cuckoo-grade; high [tell] value, flag-tier cost). No full parasite lifecycle records.
5. **Stage-form cap kept at 1–2.** Holometabolous insects treat larva+pupa as one "juvenile" stage record (pupa = dormant-phase flag on the juvenile, not its own record). 2-way merge puzzles only.
6. **Hallé architecture grammar: Order-rank steady tuple, Family-rank steady scalar params** (apical dominance, branch angle, tier spacing). Whole tree Orders share a silhouette; Families vary the proportions — mirrors real architectural conservatism.
7. **Hand-seeded magicals allowed (owner override of Fauna RFC §6.2 "no pinned magicals").** The owner may pin a small quota of magical seed records per world, past the ley boundary. Constraints keeping this compatible with the RFC's machinery: (a) a seed is a full committed record (stock source, site, operators) — pinning = authoring a record, per principle 4; (b) after seeding, the standard machinery owns everything downstream — rounds, drift, vicariance, two-range migration, gossip; no custom events, no bespoke mechanics per seed; (c) spectacle-backing rule: every gossip line about a seed must resolve to the committed record at observation (gossip always leads to spectacle — no myth-only flavor text); (d) quota is small (order 5–15/world) — the emergent lift system remains the volume source of magic.

## 15. Provenance
Compiled from 7 parallel research reports (mammals/birds; fish/reptiles/amphibians; invertebrates; cross-clade functional morphology; ecological/behavioral axes; vascular plants; non-vascular plants/fungi/algae/sessile fauna), grounded against Wikipedia/Britannica/primary-lit sources by the reporting agents. Design constraints from: Fauna Engine RFC v0.3, Flora Engine RFC v0.1, A2 addendum (topology/movement/ecology), engine spec v1.1. Numbers cited (Damuth, Lindeman, Kleiber, Fenchel, Greenwood, Bergmann/Allen/Gloger/island rules) are published values as reported by the research agents.

---

# APPENDIX — Taste invariant (owner-calibrated, 2026-07-26)

Context: monster/wonder corpus calibration. Full working corpus: `monster-corpus-v1.md`.

1. **Wonder is singular and embodied.** One whale, one flower sea, one coral highland. You can stand before it; the day is different for having found it. Grand in itself, no setup, no event.
2. **Wonder is read against the mundane.** The everyday corpus (goblins, slimes, wind wolves) is the contrast medium. Even lifted oddities can be mundane; most should be.
3. **The mundane corpus is on-the-nose.** One gimmick per monster, legible from the name, no etymology, no folklore footnotes, no joke-that-needs-explaining. Flatness is a feature: plain cloth for the majestic pattern.
4. **Realism is structural, never decorative.** Believability comes from the machinery (phylogeny, stress, vicariance, ley sites), so the surface is free to be simple, even clichéd, on purpose. Cliché on the surface, rigor underneath — never the reverse.
5. **The majestic is located, rare, hand-placed.** Wonders live at ley sites; gossip always terminates at spectacle. Hand-seeded; lifting provides edge texture only.
6. **Tolkien = north star of feeling, not method.** Events/chronicle can't be generated; the system manufactures objects of wonder, play writes the chronicle.
7. **Taste is calibrated by veto, not specified by rule.**

**The exclusion classifier (corrected by veto pass 1):** a monster is out if it *needs a footnote* (obscure folklore: bugbear, barghest, boggart) or *needs the joke explained* (one-author gimmick inventions: beholder, owlbear, displacer beast, rust monster, gelatinous cube) or is a *baroque parts-list* (chimera, manticore). **Old words are fine** if the culture has re-flattened them into one-gimmick archetypes (lich, wight, wyvern all pass — etymological age is NOT a veto signal; webnovel/game adoption is the re-flattening test).
