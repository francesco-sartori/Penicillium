# Simulation options

Three things define a simulated batch:

- **`SimulationConfig`**: the switches (fault, disturbances, PAA control, batch length, setpoints...);
- **the seed**, or explicit **`BatchParameters`**: everything random about the batch (initial state, kinetic
  parameters, disturbance sequences);
- **the inputs**: the recipe, or your own decisions sample by sample ([Recipes and control](control.md)).

```python
from penicillium import Fault, RamanMode, SimulationConfig, Simulator

config = SimulationConfig(
    fault=Fault.AERATION,
    raman_mode=RamanMode.OFF,
    batch_length_h=250.0,
)
result = Simulator(config=config).run(seed=42)
```

`SimulationConfig` is immutable. Use `dataclasses.replace(config, fault=...)` to derive variants.

## `SimulationConfig` reference

| Option | Default | Meaning |
|---|---|---|
| `fault` | `Fault.NONE` | Process or sensor fault to inject ([Faults](faults.md)) |
| `disturbances` | `True` | Slow random disturbances on kinetics, feed concentrations, coolant temperature and inlet O₂ (IndPenSim `Dis` flag) |
| `raman_mode` | `RamanMode.RECORD` | `OFF`: no spectra (faster, smaller results). `RECORD`: spectra recorded, process unchanged. `PAT_CONTROL`: spectra recorded **and** PAA under feedback control at 1200 mg/L from 10 h ([control](control.md#paa-feedback-control-pat)) |
| `raman_noise` | `True` | Random baseline noise on the spectra |
| `prbs` | `False` | Operator-style random steps on the sugar and PAA feeds from 95 h ([control](control.md#operator-perturbations-prbs)) |
| `inhibition` | `2` | IndPenSim `Inhib` flag: 0 none, 1 DO₂ and pH only, 2 all ([model](model.md#inhibition-terms)) |
| `viscosity_from_input` | `False` | Use a fixed viscosity in the oxygen-transfer model (IndPenSim `Vis` flag) |
| `temperature_setpoint` | `298.0` | Temperature setpoint [K] |
| `ph_setpoint` | `6.5` | pH setpoint |
| `offline_interval_h` | `12.0` | Interval between lab samples [h] |
| `offline_delay_steps` | `4` | Lab turnaround, in 12-minute samples (4 = 48 min) |
| `batch_length_h` | `230.0` | Batch length [h]; a multiple of 0.2 h, at most 350 h |
| `quirks` | `"matlab"` | `"fixed"` uses an alternative reading of two details of IndPenSim's controller code ([quirks](quirks.md), section 2) |

!!! tip "Raman mode is the only switch that changes speed much"
    Spectra add about 50 % to the run time and about 20 MB per batch to the result. Set
    `raman_mode=RamanMode.OFF` when you do not need them. `RECORD` does not change the process, so the batch is
    identical either way.

## Solver and backend

`Simulator` takes numerical options too:

```python
Simulator(solver="lsoda", rtol=1e-5, atol=1e-7, max_step=0.01, backend="auto")
```

| Argument | Default | Choices |
|---|---|---|
| `solver` | `"lsoda"` | `"lsoda"` (SciPy `odeint`, automatic stiff/non-stiff switching), `"bdf"` (closest relative of MATLAB's `ode15s`), `"radau"`, `"rk45"` |
| `rtol`, `atol` | 1e-5, 1e-7 | Tolerances per 12-minute interval |
| `max_step` | 0.01 h | Largest internal step |
| `backend` | `"auto"` | `"numba"` (compiled), `"python"`, `"auto"` |

The defaults are already about 100× tighter than IndPenSim's MATLAB settings. Loosening them does not save much
time, and tightening them changes results by less than the batch-to-batch variation by many orders of
magnitude ([solver sensitivity](solver_sensitivity.md)). There is rarely a reason to touch them, except to
check exactly that.

## Seeds and what they decide

`Simulator().run(seed=n)` draws, from `n`:

| Quantity | Distribution (mean ± sd) | Unit |
|---|---|---|
| Initial substrate `S` | 1 ± 0.1 | g/L |
| Initial dissolved O₂ `DO2` | 15 ± 0.5 | mg/L |
| Initial biomass `X` | 0.5 ± 0.05 (split 1/3 growing, 2/3 non-growing) | g/L |
| Initial volume `V` | 58 000 ± 500 | L |
| Initial weight `Wt` | 62 000 ± 500 | kg |
| Initial pH | 6.5 ± 0.1 | – |
| Initial temperature `T` | 297 ± 0.5 | K |
| Initial off-gas O₂ fraction `O2` | 0.20 ± 0.05 | – |
| Initial off-gas CO₂ `CO2outgas` | 0.038 ± 0.001 | % |
| Initial PAA | 1400 ± 50 | mg/L |
| Initial nitrogen `NH3` | 1700 ± 50 | mg/L |
| `mu_x_max` (maximum growth rate) | 0.41 ± 0.025 | 1/h |
| `mu_p_max` (maximum production rate) | 0.041 ± 0.0025 | 1/h |
| `alpha_kla` (kLa constant) | 85 ± 10 | – |
| `PAA_c` (PAA in the PAA feed) | 530 000 ± 20 000 | mg/L |
| `N_conc_paa` (nitrogen in the PAA feed) | 150 000 ± 2 000 | mg/L |
| Eight disturbance sequences | see [Faults and disturbances](faults.md#disturbances) | |

The means and standard deviations are IndPenSim's. Each quantity has its own independent random stream, derived
from the seed with NumPy's `SeedSequence`, so the draws are identical on every platform and Python version.
The seed also initialises the streams for the Raman noise and the PRBS steps.

To see what a seed gives without running the batch:

```python
from penicillium import Simulator

Simulator.initial_conditions(seed=1)  # {'S': 0.78, 'DO2': 14.4, 'X': 0.47, ...}
```

!!! note "Batch *n* here is not batch *n* there"
    MATLAB's random generator cannot be reproduced in Python. Seed 7 in Penicillium is therefore not batch 7
    of the published IndPenSim data set, and no seed is. Compare campaigns statistically, or replay MATLAB
    batches exactly (below).

## Overriding initial conditions

Start from a seeded batch and change what you need:

```python
result = Simulator().run(seed=1, initial_conditions={"S": 2.0, "pH": 6.4, "mu_x_max": 0.38})
```

The names and units are in `penicillium.INITIAL_CONDITIONS`. pH is given as pH. `X` is split 1:2 between growing
and non-growing biomass, as IndPenSim does. Overrides apply on top of the seeded values, so everything you do not
name stays as the seed drew it. This is ideal for controlled one-factor studies ([cookbook](cookbook.md)).

## Batch parameters: full control and MATLAB replay

`BatchParameters` holds everything random about a batch: `x0` (initial state), `params` (the five kinetic
parameters) and `disturbances` (eight sequences, one value per sample). Draw them, edit them and pass them back:

```python
from penicillium import BatchParameters, Simulator

bp = BatchParameters.from_seed(1)
bp.disturbances["distTcin"][:] = 0.0  # this batch: no coolant temperature disturbance
result = Simulator().run(batch_parameters=bp)
```

To simulate **exactly the same batch** as a MATLAB IndPenSim run, save the random inputs in MATLAB and load
them with `BatchParameters.from_matlab("batch.mat")`. [Validation](validation.md#batch-by-batch-comparison-with-matlab)
gives the MATLAB snippet.

## Batch length

`batch_length_h` can be anything from one sample (0.2 h) to 350 h in steps of 0.2 h. Since the recipe and the
fault profiles are defined in absolute time, a longer batch sees more harvest draws and later recipe segments. A
shorter batch simply stops early. To mimic IndPenSim's variable batch lengths ($230 + 25\,\varepsilon$ h,
$\varepsilon \sim N(0,1)$), draw them with `penicillium.scenarios.variable_batch_lengths(n, seed)`.

!!! warning "Long batches run out of PAA"
    The default recipe reduces the PAA feed at 200 h and stops it at 300 h, so batches longer than about
    270 h starve of precursor and stop producing ([quirks](quirks.md), 3.4). If you simulate long batches,
    revise the PAA profile, or use PAT control.

## Reproducibility

- Same seed, same config, same recipe: random inputs **bit-identical** and trajectories within about 1e-4 (of each
  channel's range) on Linux, macOS and Windows. Different CPUs and math libraries round
  transcendental functions differently in the last bit, and the model's clipping of near-zero states amplifies
  that a little. This is tested on Linux, macOS and Windows.
- On the same machine and installation, results are bit-identical from run to run.
- `result.seed`, `result.config` and `result.solver` record how a result was made. Campaign files also record the
  package version.
