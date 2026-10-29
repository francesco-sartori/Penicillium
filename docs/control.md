# Recipes and control

!!! note "Recipe times are interval ends"
    In every recipe profile, `(time_h, value)` gives the **end** of the interval in which `value` applies: each
    time is the end of its interval, as in IndPenSim. `(40, 0), (200, 10)` means 0 up to 40 h, then 10 from 40 h
    to 200 h.

The plant has two layers of control, as most fed-batch plants do:

1. **Sequential batch control (the recipe).** Seven inputs follow time-based profiles: sugar, oil, aeration,
   back pressure, broth draw, water and PAA. You can replace the recipe, or override it sample by sample.
2. **Regulatory control.** PID loops hold the temperature and pH at their setpoints by manipulating cooling
   and heating water, acid and base. These loops always run.

On top of these you can switch on IndPenSim's "operator" perturbations (PRBS) and its PAA feedback control
(PAT).

## The default recipe

IndPenSim's recipe is piecewise constant. Each entry `(time_h, value)` means *this value applies up to and
including `time_h`*: **each time is the end of its interval**, and the value holds from the previous time. Read
as intervals (the PAA feed, for example, is 5 L/h for 0–5 h, 0 for 5–40 h, 10 L/h for 40–200 h, 4 L/h for
200–300 h, then 0):

| Input | Unit | Profile |
|---|---|---|
| `Fs` sugar feed | L/h | 8 (0–3 h), 15 (–12), 30 (–16), 75 (–20), 150 (–24), 30 (–28), 37 (–32), 43 (–36), 47 (–40), 51 (–44), 57 (–48), 61 (–52), 65 (–56), 72 (–60), 76 (–64), 80 (–68), 84 (–72), 90 (–76), 116 (–80), 90 (–160), 80 (to end) |
| `Foil` soybean oil | L/h | 22 (0–4 h), 30 (–16), 35 (–56), 34 (–60), 33 (–64), 32 (–68), 31 (–72), 30 (–76), 29 (–80), 23 (to end) |
| `Fg` aeration | m³/min | 30 (0–8 h), 42 (–20), 55 (–40), 60 (–90), 75 (–200), 65 (–250), 60 (to end) |
| `pressure` back pressure | bar (g) | 0.6 (0–12.5 h), 0.7 (–25), 0.8 (–30), 0.9 (–40), 1.1 (–100), 1.0 (–150), 0.9 (to end) |
| `discharge` broth draw | L/h | 4000 for 2 h starting at 100, 130, 150, 170, 190, 210, 230, 250 and 270 h; 0 otherwise |
| `Fw` water | L/h | 0 (0–50 h), 500 (–75), 100 (–150), 0 (–160), 400 (–170), 150 (–200), 250 (–250), 0 (–270), 100 (to end) |
| `Fpaa` PAA feed | L/h | 5 (0–5 h), 0 (–40), 10 (–200), 4 (–300), 0 (to end) |

The tables extend to 350 h, the longest batch the simulator supports. The agitator runs at a fixed 100 rpm.

```python
from penicillium import Recipe

recipe = Recipe.default()
print(recipe.at(50.0))  # every input at t = 50 h
print(recipe.profiles["Fs"].setpoints)  # ((3.0, 8.0), (12.0, 15.0), ...)
```

!!! warning "\"Until\", not \"from\""
    The reading convention matters more than you might think. Penicillium reads the tables as IndPenSim
    does: each value holds until its time, so the broth draw comes in 2-hour pulses. Reading them as "from this
    time on" gives a different batch. See [quirks](quirks.md), 1.1.

## Your own recipe

Replace one or more profiles and keep the rest:

```python
from penicillium import Recipe, Simulator

recipe = Recipe.default().replace(
    Fs=[(3, 8), (12, 15), (24, 60), (80, 100), (350, 85)],  # a gentler sugar ramp
    Fpaa=[(5, 5), (40, 0), (350, 8)],  # constant PAA feed from 40 h
)
result = Simulator(recipe=recipe).run(seed=1)
```

or build a complete recipe with `Recipe.from_setpoints({...})`, which needs a profile for each of the seven
inputs in `penicillium.INPUTS`. After the last setpoint the last value holds, and before the first one the
first value holds. Times are in hours, values in the units of the table above.

## Control sample by sample

To decide the inputs as the batch goes, drive the simulator yourself:

```python
from penicillium import Simulator

sim = Simulator()
obs = sim.reset(seed=1)
while not sim.done:
    u = sim.recipe_inputs()  # recipe values for the next 12-minute sample
    if obs["DO2"] < 8 and sim.time > 20:  # a simple rule: back off the sugar if oxygen gets short
        u["Fs"] *= 0.9
    obs, harvested_kg = sim.step(**u)
result = sim.result()
```

- `sim.step(Fs, Foil, Fg, pressure, discharge, Fw, Fpaa)` simulates one 12-minute sample with these inputs
  held constant. `discharge` is the draw-off flow as a **positive** number in L/h. The call returns the new
  observation and the penicillin harvested during the sample [kg]. The harvest is the change in penicillin in
  the vessel plus what the draw removed; it is negative if penicillin degrades faster than it is made.
- `obs` is a dictionary of the latest values of `Fs`, `Foil`, `Fg`, `pressure`, `discharge`, `Fw`, `Fa`, `Fb`,
  `Fc`, `Fh`, `Wt`, `DO2`, `T`, `O2` and `pH`. In `obs` and in the results, `discharge` is negative while broth
  is drawn. The observation returned by `reset()` is all zeros, because nothing has been measured yet.
- `sim.time` (hours), `sim.k` (completed samples), `sim.done`, `sim.recipe_inputs(k)` (the recipe for sample
  `k`) and `sim.latest_spectrum()` tell you where you are. `sim.result()` returns the batch so far, at any
  time.

The observation contains only what the plant measures online. To peek at hidden states (biomass, penicillin)
for a model-based controller, read them from `sim.result()`, but be aware that a real plant cannot. For a
Gymnasium interface with configurable observations and actions, see [Reinforcement learning](gymnasium.md).

## Temperature loop

A split-range PID manipulates the cooling water `Fc` and the hot water `Fh` (both 0–1500 L/h) to hold the
setpoint (default 298 K, `SimulationConfig(temperature_setpoint=...)`).

All of IndPenSim's PIDs use the velocity (incremental) form, with derivative action on the measurement and
the output clipped to its range. With $h = 0.2$ h:

$$
u_k = u_{k-1} + K_p\left[(e_k - e_{k-1}) + \frac{h}{T_i} e_k - \frac{T_d}{h}(y_k - 2y_{k-1} + y_{k-2})\right]
$$

| Branch | Active when | $K_p$ | $T_i$ [h] | $T_d$ [h] | The other output |
|---|---|---|---|---|---|
| Cooling (`Fc`) | $T \ge T_{sp} - 0.05$ K | −300 L/(h K) | 1.6 | 0.005 | `Fh` decays to 10 % of its previous value each sample |
| Heating (`Fh`) | $T < T_{sp} - 0.05$ K | 50 L/(h K) | 0.05 | 1 | `Fc` decays to 30 % each sample |

## pH loop

A split-range PID manipulates base `Fb` and acid `Fa` (both 0–225 L/h) to hold the pH setpoint (default 6.5,
`SimulationConfig(ph_setpoint=...)`). Growth produces acid, so in practice the loop doses base almost all the
time.

| Branch | Active when | $K_p$ | $T_i$ [h] | $T_d$ [h] | The other output |
|---|---|---|---|---|---|
| Base (`Fb`) | pH ≤ setpoint + 0.05 | 0.08 | 4 × 10⁻⁵ | 8 | `Fa` = 0 |
| Acid (`Fa`) | pH > setpoint + 0.05 | 0.08 | 12.5 | 0.125 | `Fb` halves each sample |

Both loops act once per sample, on the measurements of the **previous** sample, so they see the process with
12 minutes of dead time. The temperature loop is loose by design: excursions of 1–2 K are normal, and they
were normal on the real plant too.

!!! note "Two controller details"
    Penicillium's controllers follow IndPenSim's code by default, so that batches match MATLAB: from the third
    sample on, the pH controller's previous error term does not include the setpoint, and the heating PID starts
    from the previous *cooling* flow. `SimulationConfig(quirks="fixed")` uses the alternative reading of both
    ([quirks](quirks.md), section 2).

## Operator perturbations (PRBS)

`SimulationConfig(prbs=True)` reproduces IndPenSim's *operator-dependent* batches:

- from sample 476 (95.2 h), the sugar and PAA feeds stop following the recipe and hold their previous values;
- at 120, 140, 160 h... (every 100 samples), each feed takes a random step: 0, +step or −step with equal
  probability, where the step is 15 L/h for sugar and 1 L/h for PAA. The steps accumulate, like an operator
  nudging the feeds from shift to shift.

The steps come from a random stream separate from everything else, so the same seed gives the same
perturbations whether or not you record Raman spectra. PRBS batches excite the process more richly, which is
useful for system identification and for training soft sensors.

!!! warning
    With `prbs=True`, the `Fs` and `Fpaa` values you pass to `step()` after 95 h are ignored: the perturbation
    sequence owns those two feeds.

## PAA feedback control (PAT)

`SimulationConfig(raman_mode=RamanMode.PAT_CONTROL)` reproduces IndPenSim's *advanced process control*
batches. From 10 h, a PID loop sets the PAA feed (0–150 L/h, $K_p = 0.1$, $T_i = 0.5$ h) to hold PAA at
**1200 mg/L**. This keeps PAA safely between the starvation (200 mg/L) and toxicity (2400 mg/L) thresholds, and
yields are higher and much more consistent (in the published data set, 3484 ± 308 kg against 2913 ± 768 kg for
the recipe).

In IndPenSim the controller acts on the **true** PAA concentration. The Raman/PLS prediction enters only a
derivative term whose gain is zero, so the "Raman-based" control is in fact ideal feedback. Penicillium does
the same, and records the PLS prediction in the `PAA_pred` channel so you can study the soft sensor
([quirks](quirks.md), 2.5). To build a genuinely Raman-based controller, step the simulator yourself, feed
`sim.latest_spectrum()` to your own model and set `Fpaa`.

## Order of precedence

Every sample, the inputs are decided in this order, and later steps override earlier ones:

1. the recipe, or the values you pass to `step()`;
2. PRBS (`Fs`, `Fpaa`), when enabled;
3. process faults, which force an input to a fixed value ([Faults](faults.md));
4. PAT control (`Fpaa`), when enabled.

The temperature and pH loops compute `Fc`, `Fh`, `Fa` and `Fb` independently of all of these. A process fault
therefore always wins, which is rather the point of a fault.

!!! note "What the results record about the loops"
    The results hold the controller outputs `Fa`, `Fb`, `Fc` and `Fh` and the broth values `T` and `pH`, but not
    the setpoint, mode and process value of each loop as a control system records them. Under the sensor faults 7
    and 8, the process value the controller acted on (the drifting reading) is therefore not stored
    ([Faults](faults.md#sensor-faults-the-subtle-ones)), and an actuator fault cannot be seen as an output departing
    from its measured flow. The [operator console](dcs.md) and `penicillium.dcs.BatchSession` show all four for
    each loop. A loop table (process value, setpoint, output and mode of each loop at each sample) is planned.
