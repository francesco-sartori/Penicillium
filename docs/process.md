# The process

IndPenSim, and therefore Penicillium, simulates one specific plant: a **100 m³ stirred-tank fed-batch
fermenter** producing **penicillin G** with an industrial strain of the filamentous fungus *Penicillium
chrysogenum*. Goldrick et al. (2015, section 3) estimated the model's parameters from the batch records of ten
fermentations in a 100,000-litre industrial bioreactor and validated the simulation against them. This page
describes the simulated plant as an operator or process engineer would see it. [The model](model.md) gives the equations.

!!! note "Primary sources"
    Everything on this page describes the plant **as the simulator implements it** (IndPenSim V2.01), not the
    real facility. For the process, the industrial data and the reasoning behind the model, read the original
    papers:

    - S. Goldrick et al., *The development of an industrial-scale fed-batch fermentation simulation*, Journal of
      Biotechnology 193 (2015) 70–82, [doi:10.1016/j.jbiotec.2014.10.029](https://doi.org/10.1016/j.jbiotec.2014.10.029):
      the process, the model and its validation against the plant's batch records.
    - S. Goldrick et al., *Modern day monitoring and control challenges outlined on an industrial-scale benchmark
      fermentation process*, Computers and Chemical Engineering 130 (2019) 106471,
      [doi:10.1016/j.compchemeng.2019.05.037](https://doi.org/10.1016/j.compchemeng.2019.05.037) (open access):
      operating modes, measurements, control objectives, the Raman analyser and the 100-batch data set.
    - The IndPenSim website, <http://www.industrialpenicillinsimulation.com/>, which distributes the simulator
      and the data.

## Equipment

| Item | Value in the model |
|---|---|
| Vessel | Cylindrical, radius 2.1 m (diameter 4.2 m), about 100 m³ nominal working volume |
| Agitation | Three Rushton impellers, 1.7 m diameter (power number 5), fixed at 100 rpm (Goldrick et al. 2015, section 3.2) |
| Aeration | Compressed air (21 % O₂) through a sparger, 30–75 m³/min in the default recipe |
| Head space | Back pressure 0.6–1.1 bar (gauge) in the default recipe |
| Heat exchange | Internal cooling coils (cooling water at 285 K; Goldrick et al. 2015, section 3.2) and, in the model, a hot-water flow at 333 K, on a split-range temperature loop; heat losses to the surroundings (290 K) |
| pH | Split-range acid and base dosing on a PID loop |
| Feeds | Sugar solution (about 600 g/L), soybean oil, phenylacetic acid (PAA) solution, water for injection |
| Harvest | Periodic broth draws ("discharge") of 4000 L/h for 2 h |
| Online sensors | Temperature, pH, dissolved O₂, off-gas O₂ and CO₂, vessel weight, volume, all flows, pressure, agitator speed |
| Off-line lab | Penicillin, biomass, PAA, nitrogen (ammonia) and viscosity, every 12 h |
| PAT | A Raman spectrometer with an immersion probe (simulated spectra, 2200 points from 201 to 2400 cm⁻¹) |

## The chemistry in one paragraph

This is the biology as the model represents it. For the physiology itself and the literature behind each
assumption, see Goldrick et al. (2015) and the morphological model it builds on (Paul and Thomas, 1996; see
[Citing](citing.md)).

The fungus grows on sugar and soybean oil (in the model the oil feed also carries nitrogen), consumes oxygen
and releases CO₂ and heat. Penicillin G is a *secondary metabolite*. In the model it is made by the
non-growing regions of the hyphae, and only when the sugar concentration is very low. The model represents
carbon-catabolite repression by a narrow production window around 2 mg/L of substrate. The recipe therefore
feeds sugar just fast enough to sustain the culture, and the substrate concentration sits around 1–2 mg/L for
most of the batch. Production also needs **phenylacetic acid (PAA)**, the precursor of penicillin G's side
chain. In the model, production stops below about 200 mg/L of PAA and growth is inhibited above about
2400 mg/L. These are the model's switch points, not general physiological constants. Penicillin is not stable
in the broth: it slowly hydrolyses, at a rate that depends on pH and temperature.

## Anatomy of a default batch

The default batch lasts **230 h** (just under ten days). It is recorded every **12 minutes**, which gives 1150
samples. Here is what happens in a typical nominal batch (seed 1; other seeds differ by some percent):

| Time | Phase | What you see |
|---|---|---|
| 0 h | Start | About 58 m³ of medium, 62 t vessel weight, 0.5 g/L biomass from the seed fermenter, 1 g/L sugar, 1400 mg/L PAA, 1700 mg/L nitrogen, 297 K, pH 6.5 |
| 0–24 h | Growth | The initial sugar is used up within hours. The sugar feed ramps from 8 to 150 L/h, and soybean oil is fed at 22–30 L/h. Biomass reaches about 7 g/L at 20 h. Oxygen demand rises and dissolved O₂ falls from about 15 to 10 mg/L. |
| 24–80 h | Transition to production | The sugar feed drops to 30 L/h and then rises in 4-hour steps to 116 L/h. Growth slows down. Penicillin appears after about a day and reaches about 8 g/L at 60 h. PAA falls, until the PAA feed (10 L/h from 40 h) replaces what is consumed. Water is added from 50 h. |
| 80–230 h | Production | Biomass plateaus around 22–24 g/L, and penicillin rises roughly linearly to about 30 g/L. Viscosity climbs from about 40 to 60–80 cP. The volume peaks around 85 m³ near 100 h. |
| 100, 130, 150, 170, 190, 210 h | Harvest draws | Each draw removes about 8 m³ of broth, and the penicillin it contains counts towards the harvest. |
| 230 h | End | About 79 m³ in the vessel. Harvested penicillin is typically 2000–4000 kg per batch. |

The temperature loop holds the broth at 298 K (24.85 °C) to within about ±0.5 K, with occasional 1–2 K
excursions. The pH loop holds 6.5 ± 0.1. Both are IndPenSim's PID loops as published. Goldrick et al. (2019,
section 1.2) list tighter pH and temperature control among the benchmark's control challenges.

!!! info "Batch-to-batch variation is a feature"
    Over 20 nominal batches (seeds 1–20) Penicillium gives a mean harvest of 2800 kg with a standard deviation
    of 760 kg (range 1700–4200 kg). The published IndPenSim data set reports 2913 ± 768 kg for its
    recipe-driven batches. The spread comes from the random initial conditions, kinetic parameters and slow
    disturbances. Most of the low-yield batches are batches in which PAA drifted above its toxicity threshold
    ([quirks](quirks.md), 3.2). If every one of your batches looks the same, you have probably switched off the
    disturbances.

## Ways to operate the plant

The published 100-batch data set (Goldrick, 2019, Mendeley Data) contains batches run in four ways, and
Penicillium supports all of them. Goldrick et al. (2019, sections 1.1 and 5) describe the modes:

| Mode | How | In Penicillium |
|---|---|---|
| **Recipe driven** | Fixed feeding profiles (sequential batch control) | Default: `Simulator().run(...)` |
| **Operator dependent** | Recipe, but the sugar and PAA feeds are moved by an "operator" in random steps from 95 h | `SimulationConfig(prbs=True)` |
| **Advanced process control (APC)** | PAA feed under closed-loop control. The paper's APC used a Raman soft sensor and a PI loop at 1250 mg/L (section 5.1). IndPenSim V2.01's controller uses 1200 mg/L and the true PAA ([quirks](quirks.md), 2.5) | `SimulationConfig(raman_mode=RamanMode.PAT_CONTROL)` |
| **With faults** | Aeration, pressure, feed, base, coolant or sensor faults | `SimulationConfig(fault=Fault.AERATION)`, ... |

You can also run it in a fifth way that the original authors did not offer: **your own control**, sample by
sample, from Python ([Recipes and control](control.md)), from a reinforcement-learning agent
([Gymnasium](gymnasium.md)), or by hand from a [DCS-style operator console](dcs.md).

## What the simulator does not include

A good model knows what it leaves out. IndPenSim (and so Penicillium) does not simulate:

- the seed train and inoculation (each batch starts from a sampled initial state), or downstream processing;
- foaming, antifoam dosing, contamination or strain degeneration;
- spatial gradients: the broth is perfectly mixed, although the model accounts for the hydrostatic pressure
  over the liquid height when it computes oxygen solubility;
- agitator speed as a manipulated variable: it is fixed at 100 rpm, as in the published default recipe;
- ammonia or nitrogen shots: the term exists in the model but is always zero; nitrogen comes from the initial
  medium, the oil feed and the PAA feed;
- cost, scheduling or turnaround between batches.

None of these omissions is likely to trouble a monitoring or control study. All of them would trouble a plant
manager.
