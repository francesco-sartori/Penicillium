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

!!! warning "The timing of a fault gives its type away"
    The windows are IndPenSim's and cannot be changed through the configuration: each fault type acts at the same
    times, with the same duration and magnitude, in every batch, and no two fault types share onset and duration.
    A classifier trained on these batches can therefore infer the fault type from the time at which something
    happens, instead of from the process. Keep this in mind when you score fault diagnosis, and prefer features
    that do not include the batch time. Detection delays measured on these batches also reflect the windows.

    A process failure with a different timing, duration or value can be imposed through the
    [stepping interface](control.md#control-sample-by-sample): run the batch sample by sample and force the input
    yourself in the samples you choose. `Fault_ref` is then not set, so keep your own label. Options for the
    onset, duration and magnitude of each fault, with the IndPenSim windows kept as the default, are planned.

    ```python
    from penicillium import Simulator

    sim = Simulator()
    sim.reset(seed=1)
    label = []
    while not sim.done:
        u = sim.recipe_inputs()
        active = 60.0 <= sim.time < 66.0  # aeration failure from 60 to 66 h
        if active:
            u["Fg"] = 20.0
        sim.step(**u)
        label.append(int(active))  # your own per-sample label
    result = sim.result()
    ```

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
  This is IndPenSim's convention. If you need "drift > 0" labels, use samples from 200 on.

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
