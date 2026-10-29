# Penicillium

Penicillium is a Python implementation of **IndPenSim** (Goldrick et al., 2015, 2019), the simulator of a
100 m³ fed-batch *Penicillium chrysogenum* fermentation.

**An industrial penicillin fermentation in your laptop. No mould, no MATLAB, no 3 a.m. call from the plant.**

IndPenSim is the standard benchmark for bioprocess
monitoring, soft sensors, fault detection and control. The model was fitted to records of a real industrial
plant, and it includes everything a process engineer would expect:

- a structured, segregated model of fungal growth and morphology (growing, non-growing, vacuolated and
  autolysed hyphae), substrate-limited penicillin production, product hydrolysis and 33 dynamic states;
- mass balances for substrate, oxygen, CO₂, phenylacetic acid (PAA) and nitrogen, with oxygen transfer from
  aeration, agitation, back pressure and broth viscosity;
- an energy balance with cooling and heating coils, evaporation and jacket losses;
- pH and temperature PID loops, and a sequential (recipe-driven) feeding strategy for sugar, oil, PAA, water,
  aeration, pressure and harvest draws;
- slow random disturbances, eight fault scenarios, delayed off-line lab assays and a simulated Raman
  spectrometer.

```python
from penicillium import Simulator

result = Simulator().run(seed=1)  # one 230 h batch, sampled every 12 minutes
print(f"{result.total_yield:.0f} kg of penicillin harvested")
df = result.to_pandas()  # 55 channels, indexed by time in hours
```

That is a full 230-hour production batch in about 0.6 seconds. On the real plant it takes ten days.

## Where to start

| You want to... | Read |
|---|---|
| Install it | [Installation](installation.md) |
| Run and plot a batch in five minutes | [Your first batch](quickstart.md) |
| Learn each feature from a worked notebook | [Tutorials](tutorials/index.md) |
| Understand the plant you are simulating | [The process](process.md) |
| Check the equations before you trust the numbers | [The model](model.md) |
| Change the feeding strategy or write your own controller | [Recipes and control](control.md) |
| Switch faults, disturbances, PAA control, batch length... | [Simulation options](configuration.md), [Faults and disturbances](faults.md) |
| Look up what `Fg` or `CER` means, and in which unit | [Variables and units](variables.md) |
| Generate a data set for fault detection or soft sensors | [Campaigns and datasets](scenarios.md) |
| Copy a ready-made study (step tests, setpoint sweeps, feed optimisation) | [Cookbook](cookbook.md) |
| Run the plant from a control-room screen | [Operator console](dcs.md) |
| Know how far you can trust it | [Validation](validation.md) |
| Fix something that went wrong | [FAQ and troubleshooting](faq.md) |

## What you get

| | |
|---|---|
| **Install** | Python 3.10 or later; tested on Linux, macOS and Windows with Python 3.10 to 3.14. No compiler and no MATLAB. Optional Numba backend for speed. |
| **Fidelity** | Checked line by line against IndPenSim V2.01; 14 of 15 batches of V2.01 replayed within 0.1 % on yield. Against the published 100-batch data set, no significant difference detected in the yield distributions of recipe-driven, operator-controlled and faulty batches (KS p = 0.31–0.93; the tests have low power) ([validation](validation.md)). |
| **Speed** | 0.6 s per batch, or about 380 batches per minute in parallel on an Intel Core i7-7700HQ ([benchmarks](benchmarks.md)). |
| **Reproducible** | Random inputs bit-identical and trajectories within about 1e-4 on Linux, macOS and Windows. |
| **Honest** | Every known difference from IndPenSim is documented ([quirks](quirks.md)). |
| **Licence** | MIT; the parts derived from IndPenSim are also under IndPenSim's BSD 3-Clause licence. Documented provenance ([licensing](licensing.md)). |

## Limitations at a glance

Read these before you build a study on Penicillium. Each one is explained on the linked page.

| Limitation | What it means for you |
|---|---|
| Fixed fault windows | Each fault acts at the same times, with the same duration and magnitude, in every batch (IndPenSim's windows), so a classifier can infer the fault from the batch time; detection delays reflect the windows ([Faults](faults.md#faults)) |
| True values in the sensor-fault channels | With faults 7 and 8, the recorded `T` and `pH` are the true broth values, not the drifting reading the controller acts on, which makes detection easier than on a plant ([Faults](faults.md#sensor-faults-the-subtle-ones)) |
| Two meanings of `Fault_ref` | 1 while the cause acts for process faults, but 1 for the entire batch with sensor faults ([fault labels](scenarios.md#fault-labels-in-campaigns)) |
| Loop signals not recorded | The controller outputs `Fa`, `Fb`, `Fc`, `Fh` are recorded, but not the setpoint, mode and process value of each loop, so actuator faults cannot be seen as an output departing from its flow ([Recipes and control](control.md)) |
| Fixed agitator speed | 100 rpm; dissolved oxygen is not controlled, so an aeration fault shows in DO2, where under a DO cascade it would show in the agitator speed ([Recipes and control](control.md#the-default-recipe)) |
| A single plant | The model's constants describe one 100 m³ plant; there is no documented way to re-parameterise it yet ([The model](model.md)) |
| Scale of OUR and CER | Monitoring signals only: they cannot close a mass balance, and their ratio is not a quantitative respiratory quotient ([Lab data](measurements.md)) |
| 6.4 h floor of the alarm rule in tutorial 5 | The example monitor needs 32 consecutive samples above a limit, so it cannot alarm in less than 6.4 h, nor on fault windows shorter than that ([tutorial 5](tutorials/05_campaigns_and_fault_detection.ipynb)) |
| No monitoring or control methods | Penicillium simulates the plant; monitoring, soft-sensor, MPC and state-estimation methods are yours to write (the tutorials show examples) |
| Octave reference, not MATLAB | The batch-by-batch comparison used IndPenSim V2.01 run in GNU Octave ([Batch by batch](validation_octave.md#limitations)) |
| Known gaps with the published data | APC yields 4 % below the published campaign, and the coolant fault of Goldrick et al. (2019), Fig. 7D, is not reproduced ([Validation](validation.md#open-points)) |
| The interface may still change | Names of classes, functions and arguments may change before version 1.0 |

!!! note "Status"
    Penicillium is alpha software (0.1.0a1). The model is validated, but the Python API may still change
    between releases. Install it with `pip install "penicillium[fast]"` ([installation](installation.md)).

!!! tip "A word on names"
    *Penicillium* is the genus of the mould. `penicillium` is the Python package. *Penicillin* is what you are
    trying to make. If you mix them up in a paper, reviewers will notice.

If you publish results obtained with Penicillium, please cite IndPenSim and this package (see
[Citing and references](citing.md)), and report what is needed to repeat them ([Reporting a
benchmark](benchmarking.md)). Penicillium is built on IndPenSim, created by Stephen Goldrick
([Licensing](licensing.md)).
