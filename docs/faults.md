# Faults and disturbances

Real plants have bad days. IndPenSim has two mechanisms for them:

- **Disturbances**: slow, random drifts in kinetics and feed properties, present in every batch unless you
  switch them off. They make each batch unique.
- **Faults**: specific failures of an actuator or sensor at defined times, which you inject on purpose. They
  are what fault-detection studies try to catch.

## Faults

```python
from penicillium import Fault, SimulationConfig, Simulator

result = Simulator(config=SimulationConfig(fault=Fault.AERATION)).run(seed=1)
result["Fault_ref"]  # 1 in the samples where the fault acts, else 0
```

Process faults override an input with a fixed value over fixed sample ranges, exactly as IndPenSim's
`fctrl_indpensim.m` does. Sample $k$ covers $0.2(k-1) < t \le 0.2k$ hours.

| Code | `Fault.` | What fails | Input forced to | Samples (≈ hours) |
|---|---|---|---|---|
| 0 | `NONE` | Nothing | – | – |
| 1 | `AERATION` | Air supply | `Fg` = 20 m³/min | 100–120 (20–24 h), 500–550 (100–110 h) |
| 2 | `PRESSURE` | Back-pressure valve | `pressure` = 2 bar | 500–520 (100–104 h), 1000–1200 (200–240 h) |
| 3 | `SUBSTRATE_FEED` | Sugar feed | `Fs` = 2 L/h, then 20 L/h, then 20 L/h | 100–150 (20–30 h), 380–460 (76–92 h), 1000–1070 (200–214 h) |
| 4 | `BASE_FLOW` | Base dosing pump | `Fb` = 5 L/h, then 10 L/h | 400–420 (80–84 h), 700–800 (140–160 h) |
| 5 | `COOLANT_FLOW` | Cooling water | `Fc` = 2 L/h, then 10 L/h | 350–450 (70–90 h), 1200–1350 (240–270 h) |
| 6 | `ALL` | Faults 1–5 together | as above | as above |
| 7 | `TEMPERATURE_SENSOR` | Temperature transmitter drift | measurement offset ramps from 0 to −0.4 K | ramp from sample 200 to 800 (40–160 h), then constant |
| 8 | `PH_SENSOR` | pH probe drift | measurement offset ramps from 0 to −0.1 | ramp from sample 200 to 800 (40–160 h), then constant |

Windows that start after the end of the batch simply do not occur. The second coolant window, for example,
needs a batch longer than 240 h.

!!! warning "With IndPenSim's windows, the timing of a fault gives its type away"
    By default each fault type acts at the same times, with the same duration and magnitude, in every batch, and
    no two fault types share onset and duration. A classifier trained on these batches can therefore infer the
    fault type from the time at which something happens, instead of from the process, and detection delays
    reflect the windows. For fault diagnosis, draw the timing at random per batch
    (`FaultSpec(fault, randomise=True)`, or `randomise=True` in
    [`fault_campaign`](scenarios.md#fault-detection-and-diagnosis)), as described below.

### Sensor faults: the subtle ones

With faults 7 and 8 the transmitter reads **low**. The PID loop believes it and drives the *true* temperature
up by as much as 0.4 K, or the *true* pH up to 6.6. The control loop looks perfectly healthy throughout: the
measurement sits on its setpoint. This is the classic case that only a model, a redundant measurement or the
lab can catch.

!!! warning "What the recorded channels contain"
    The `T` and `pH` channels in the results are the **true** broth values, not the drifting measurement.
    A detector trained on `T` and `pH` from a fault-7 or fault-8 batch therefore sees the broth drift away from
    its setpoint, which is easier than the real problem. To work with the measurement the controller saw,
    reconstruct it: the measured value is the true value minus the drift ramp (0 up to 40 h, linear to 0.4 K
    or 0.1 at 160 h, constant after). The [operator console](dcs.md) shows the drifting measurement, as a
    control room would. Recording the in-loop reading in `T` and `pH`, with the broth values in `T_true` and
    `pH_true` (as with [measurement noise](measurements.md#measurement-noise)), is planned.

### Fault labels

`Fault_ref` (and `fault_active` in [campaigns](scenarios.md) and in the info of `IndPenSimFault-v0`) is the
per-sample label:

- for process faults (1–6) it is 1 exactly in the samples where an input is forced;
- for sensor faults (7, 8) it is 1 **for the whole batch**, including the first 40 h before the drift begins.
  This is IndPenSim's convention. If you need "drift > 0" labels, use samples from 200 on, or the
  [fault options](#fault-timing-and-magnitude), which label the window only.

So the label has two meanings: "the cause acts in this sample" for process faults, and "this batch has the fault"
for sensor faults. [Campaigns and datasets](scenarios.md#fault-labels-in-campaigns) lists which label each tutorial
uses. A separate label for the samples in which the cause acts, in every output, is planned, with `Fault_ref`
kept as IndPenSim's label.

### What the faults do to the batch

Harvested penicillin for seeds 1–3, compared with the same seeds without a fault (3602, 2440 and 2224 kg):

| Fault | Harvest [kg] | Change | Why |
|---|---|---|---|
| Aeration | 1633, 1177, 1271 | −45 to −55 % | DO₂ halves during the first window. During the second, production slows; the PAA no longer consumed accumulates past the 2400 mg/L toxicity threshold by about 160 h, and biomass declines from then on |
| Pressure | 2735, 2174, 1935 | −11 to −24 % | Oxygen transfer actually *improves* (DO₂ rises from about 12 to 22 mg/L), but dissolved CO₂ rises past its inhibition threshold and growth stops. The long window at 200–240 h costs the most |
| Substrate feed | 1985, 649, 880 | −45 to −73 % | Sugar starvation in the growth phase stunts the culture for the rest of the batch |
| Base flow | 3593, 2403, 2177 | −0 to −2 % | The pH loop compensates once the window ends |
| Coolant flow | 3598, 2422, 2205 | < 1 % | The temperature peaks about 2 K above its normal range for 20 h, and the culture tolerates it |
| All (1–5) | 863, 649, 720 | −68 to −76 % | A very bad day |
| Temperature sensor | 3587, 2406, 2195 | about −1 % | 0.4 K is within the kinetic optimum |
| pH sensor | 3612, 2452, 2257 | about +0.5 % | 0.1 pH units barely moves the pH inhibition term |

The faults with little effect on yield are the interesting ones for monitoring: a good detector must catch them
from their signature in the online data, not from the yield. The coolant-flow fault of the 2019 paper's
Fig. 7D, which lost about 10 g/L, differs from the cooling faults of the V2.01 code, and we could not reproduce it
([quirks](quirks.md), 3.3).

## Fault timing and magnitude

*An addition to IndPenSim.* A `FaultSpec` describes one window of one fault: its onset, duration, magnitude and
shape. Each of the three numbers can be fixed or drawn per batch from a distribution. Pass one spec, or several,
as `SimulationConfig(fault_specs=...)`; the fault code (`config.fault`) is then taken from the specs. Without
specs, every fault keeps IndPenSim's windows, and every output is the same as in earlier versions.

```python
from penicillium import FaultSpec, SimulationConfig, Simulator
from penicillium.faults import Normal, Uniform

# One line: aeration fault with a random onset and duration, IndPenSim's magnitude
cfg = SimulationConfig(fault_specs=FaultSpec("aeration", randomise=True))

# Fully custom: a sugar feed that loses 60 % of its flow, at a random time, for about 8 h
leak = FaultSpec(
    "substrate_feed", onset_h=Uniform(30, 120), duration_h=Normal(8, 2, low=1), magnitude=0.6, effect="scale"
)
cfg = SimulationConfig(fault_specs=leak)


# A custom ramp: the temperature reading drifts as tau**2 over 60 h, then is recalibrated
def quadratic(tau: float) -> float:
    return tau**2


drift = FaultSpec("temperature_sensor", onset_h=50, duration_h=60, magnitude=0.8, shape=quadratic, hold=False)
cfg = SimulationConfig(fault_specs=drift)

result = Simulator(config=cfg).run(seed=1)
result.metadata["fault_windows"]  # the window drawn for this batch
```

`FaultSpec.indpensim(fault)` returns IndPenSim's windows as specs (two for aeration, three for the sugar feed,
eleven for `Fault.ALL`). They give the same inputs as `SimulationConfig(fault=fault)`, bit for bit, and are a
starting point for variants, for example `dataclasses.replace(spec, magnitude=10.0)`.

### Options

| Option | Default | Meaning |
|---|---|---|
| `fault` | | `Fault` or its name (`"aeration"`); any fault except `NONE` and `ALL` |
| `onset_h` | first IndPenSim window | Start of the window [h], at least 0.2 h |
| `duration_h` | first IndPenSim window | Length of the window [h]; `0` is one sample; `math.inf` (steps only) lasts to the end of the batch |
| `magnitude` | first IndPenSim window | Size of the fault (see the table below) |
| `shape` | `"step"` (faults 1–5), `"ramp"` (7–8) | `"step"`: constant over the window. `"ramp"`: rises linearly from 0 at the onset to the magnitude at the end of the window. A function `f(tau)` returning a value in [0, 1], where `tau` is the fraction of the window elapsed, gives a ramp of that form. After the window, see `hold` |
| `effect` | `"set"` (1–5), `"offset"` (7–8) | How the magnitude acts (see the table below) |
| `hold` | `True` (7–8), `False` (1–5) | After the window, keep the value reached at its end until the end of the batch, as IndPenSim's sensor drift does. With `False` the fault ends with the window (a sensor recalibrated, a pump restarted) |
| `randomise` | `False` | Draw the onset and duration left unset (see below) |

Each of `onset_h`, `duration_h` and `magnitude` takes a number or one of the distributions of
`penicillium.faults`: `Uniform(low, high)`, `Normal(mean, sd, low=None, high=None)` (clipped to the bounds) and
`Choice(values)`. Times are rounded to the 12-minute sample grid. The window runs from the sample that ends at
`onset_h` to the sample that ends at `onset_h + duration_h`, both included, as IndPenSim's windows do (onset 20 h,
duration 4 h: samples 100 to 120).

### What the magnitude means

| Code | Acts on | Default effect and IndPenSim magnitude | Other effects | Shapes that fit |
|---|---|---|---|---|
| 1 `AERATION` | aeration `Fg` | `set`: forced to 20 (unit of the `Fg` channel) | `scale` | step (blower trip), ramp (sparger or filter fouling) |
| 2 `PRESSURE` | back pressure | `set`: forced to 2 bar | `offset` [bar] | step (valve stuck), ramp (exhaust filter blinding) |
| 3 `SUBSTRATE_FEED` | sugar feed `Fs` | `set`: forced to 2 L/h | `scale`, `offset` [L/h] | step (pump failure), ramp (line fouling) |
| 4 `BASE_FLOW` | base flow `Fb` | `set`: forced to 5 L/h | `scale` | step (pump failure), ramp (pump wear) |
| 5 `COOLANT_FLOW` | cooling water `Fc` | `set`: forced to 2 L/h | `scale` | step (valve or pump), ramp (partial blockage) |
| 7 `TEMPERATURE_SENSOR` | temperature reading of the loop | `offset`: reads 0.4 K low | – | step (calibration bias), ramp (drift) |
| 8 `PH_SENSOR` | pH reading of the loop | `offset`: reads 0.1 low | – | step (calibration bias), ramp (drift) |

- `set`: the input is forced to the magnitude, as IndPenSim does. With a ramp the input moves from its normal
  value to the magnitude over the window.
- `scale`: the input loses the fraction `magnitude` (0 to 1) of its value: `0.6` is a 60 % loss of flow.
- `offset`: the magnitude is added to the input (the result is kept at 0 or above). For the sensor faults the
  reading the controller acts on is the true value minus the magnitude, so a positive magnitude reads low.

!!! note "`set` and random timing"
    A forced value is a deeper cut at some times than at others: forcing the aeration to 20 at 200 h, when the
    recipe gives 75, is a larger loss than at 25 h, when it gives 42. Use `effect="scale"` for a fault of the
    same relative size at any time.

### Random timing

With `randomise=True`, each onset and duration that you leave unset is drawn per batch, and the magnitude stays
IndPenSim's unless you set it:

| Fault | Duration [h] | Onset [h] |
|---|---|---|
| Aeration | uniform 4–10 | uniform from 20 to the batch length minus the duration |
| Pressure | uniform 4–40 | as above |
| Sugar feed | uniform 10–16 | as above |
| Base flow | uniform 4–20 | as above |
| Coolant flow | uniform 20–30 | as above |
| Temperature, pH sensors | 120 (IndPenSim's ramp), then held to the end | uniform from 20 to the batch length minus 120 |

The duration ranges span those of IndPenSim's windows for each fault. The onset range keeps the window inside
the batch, unless the batch is shorter than 20 h plus the duration (the onset is then 20 h and the window is cut
off at the end). In a [campaign](scenarios.md#fault-detection-and-diagnosis), `fault_campaign(..., randomise=True)`
does this for every faulty batch (for `Fault.ALL`, faults 1–5 each get their own window).

The random values come from the batch seed, each from its own random stream (one per spec and per onset,
duration and magnitude). The same seed therefore gives the same windows on every platform and in every process,
fixing one of the three values does not change the draws of the others, and switching the fault options on does
not change the batch's other random inputs (initial state, kinetic parameters, disturbances, PRBS steps, Raman
noise, measurement noise).

### Several windows

A batch can hold several windows: of the same fault, or of several of faults 1–5 (the batch code is then
`Fault.ALL`). Windows on the same input apply in the order given: `set` replaces the value, `scale` multiplies it,
offsets add. A window that starts after the end of the batch never acts; one that runs past the end is cut off.

A spec with a custom `shape` function must be picklable to reach the worker processes of a campaign with
`n_jobs > 1`: define the function at module level, not as a `lambda`.

### Labels

With fault options, `Fault_ref` (and `fault_active` in campaigns) is 1 exactly in the samples of the windows, for
every fault, and `metadata["fault_windows"]` lists the windows drawn. This differs from IndPenSim's convention for
the sensor faults, which marks the whole batch ([quirks](quirks.md), 1.7).

## Disturbances

With `SimulationConfig(disturbances=True)` (the default), eight parameters wander slowly during every batch.
Each disturbance is white noise passed through IndPenSim's first-order low-pass filter,

$$
d_n = 0.005\,w_n + 0.995\,d_{n-1}, \qquad d_0 = 0,
$$

a time constant of 200 samples (40 h). The stationary standard deviation is about 0.05 × that of the noise
$w_n$. The disturbance starts at zero and builds up over the first day or two of the batch.

| Sequence | Disturbs | Nominal | Typical excursion (1 sd) |
|---|---|---|---|
| `distMuP` | max. production rate $\mu_p$ | 0.041 1/h (per batch) | ± 0.0015 1/h |
| `distMuX` | max. growth rate $\mu_{x,max}$ | 0.41 1/h (per batch) | ± 0.0125 1/h |
| `distcs` | sugar concentration in the feed | 600 g/L | ± 75 g/L |
| `distcoil` | oil substrate concentration | 1000 g/L | ± 15 g/L |
| `distabc` | acid/base strength in the pH balance | 0.033 | ± 0.01 |
| `distPAA` | PAA concentration in the PAA feed | 530 g/L (per batch) | ± 15 g/L |
| `distTcin` | cooling water inlet temperature | 285 K | ± 5 K |
| `distO_2in` | O₂ fraction in the inlet air | 0.21 | ± 0.001 |

The eight sequences are independent, as in IndPenSim ([quirks](quirks.md), 1.2).

Switch disturbances off to see the "textbook" batch, with only the random initial conditions left:

```python
from penicillium import SimulationConfig, Simulator

clean = Simulator(config=SimulationConfig(disturbances=False)).run(seed=1)
```

You can also inspect or edit the sequences of a batch through `BatchParameters.from_seed(seed).disturbances`
([Simulation options](configuration.md#batch-parameters-full-control-and-matlab-replay)).
