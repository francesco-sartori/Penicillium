# Cookbook

Worked studies that you can copy and adapt. Each one runs in seconds to a couple of minutes with the `fast`
extra. Scripts that use `simulate_batches` need the `if __name__ == "__main__":` guard
([why](scenarios.md)). It is omitted below for brevity; notebooks do not need it.

The [tutorials](tutorials/index.md) cover more studies step by step: comparing two recipes on the same batches
(tutorial 2), dosing PAA from the lab results (tutorial 2), changing one initial condition at a time (tutorial 3)
and exporting the data (tutorials 1 and 4).

## Sweep a setpoint

What does the temperature setpoint cost or gain? Sweep it over the same seeds:

```python
import numpy as np
from penicillium import BatchSpec, RamanMode, SimulationConfig, simulate_batches

setpoints = [296.0, 297.0, 298.0, 299.0, 300.0]
seeds = range(1, 21)
specs = [
    BatchSpec(seed=s, config=SimulationConfig(temperature_setpoint=tsp, raman_mode=RamanMode.OFF))
    for tsp in setpoints
    for s in seeds
]
y = np.array([r.total_yield for r in simulate_batches(specs, keep_raman=False)]).reshape(len(setpoints), -1)
for tsp, row in zip(setpoints, y):
    print(f"{tsp:.0f} K: {row.mean():6.0f} ± {row.std(ddof=1):4.0f} kg")
```

The temperature term in the model peaks near 297.5 K ([model](model.md#inhibition-terms)), but hydrolysis,
evaporation and the controllers also respond to temperature, so the optimum of the whole batch is an empirical
question. That is what the sweep is for.

## Step test for system identification

A classic open-loop step: hold the recipe, step the sugar feed by +10 % at 120 h, and watch the response. A
twin batch without the step, on the same seed, removes the disturbances from the comparison:

```python
import matplotlib.pyplot as plt
from penicillium import Simulator


def batch(step_at=None, size=0.10):
    sim = Simulator()
    sim.reset(seed=3)
    while not sim.done:
        u = sim.recipe_inputs()
        if step_at is not None and sim.time >= step_at:
            u["Fs"] *= 1 + size
        sim.step(**u)
    return sim.result()


ref, stepped = batch(), batch(step_at=120)
fig, axes = plt.subplots(3, 1, sharex=True, figsize=(8, 7))
for ax, name in zip(axes, ["DO2", "OUR", "P"]):
    ax.plot(ref.time, stepped[name] - ref[name])
    ax.set_ylabel(f"Δ{name}")
axes[-1].set_xlabel("Time [h]")
axes[-1].set_xlim(110, 180)
plt.show()
```

Subtracting the twin isolates the response to your step from everything else that happens in the batch. On a
real plant you cannot do this; in a simulator you would be foolish not to.

## Use back pressure for oxygen

Back pressure raises oxygen solubility ([model](model.md#oxygen)), and it also raises dissolved CO₂. Find out
where the trade-off lands:

```python
from penicillium import Recipe, Simulator

for p in (0.9, 1.1, 1.3, 1.5):
    recipe = Recipe.default().replace(pressure=[(12.5, 0.6), (25, 0.7), (30, 0.8), (40, 0.9), (350, p)])
    r = Simulator(recipe=recipe).run(seed=2)
    print(
        f"{p:.1f} bar: DO2 min {r['DO2'][200:].min():5.1f} mg/L, "
        f"CO2_d max {r['CO2_d'].max():5.2f}, harvest {r.total_yield:5.0f} kg"
    )
```

On seed 2, 0.9 and 1.1 bar give the same harvest; at 1.3 and 1.5 bar it falls to 2170 and 810 kg. Watch `CO2_d` approach 7.57 g/L, the threshold above which growth stops. The pressure fault does exactly this
([faults](faults.md#what-the-faults-do-to-the-batch)).

## The yield distribution, and the batches that fail

```python
import numpy as np
from penicillium import scenarios

camp = scenarios.goldrick2019_campaign(seed=1, n_faults=0, variable_length=False)
b = camp.batches
print(b.groupby("kind")["total_yield_kg"].describe())

# Which recipe batches fell short, and did their PAA overshoot?
peak_paa = camp.samples.groupby("batch_id")["PAA"].max()
recipe = b[b.kind == "recipe"].set_index("batch_id")
low = recipe.total_yield_kg < recipe.total_yield_kg.quantile(0.25)
print("peak PAA, low-yield batches:", peak_paa[recipe.index[low]].median().round())
print("peak PAA, the others:       ", peak_paa[recipe.index[~low]].median().round())
```

APC batches (PAA under control) should show a higher mean and a much smaller spread than recipe batches. That
was the main finding of the 2019 paper, and it is a useful sanity check of your installation.
