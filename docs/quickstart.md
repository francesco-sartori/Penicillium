# Your first batch

Five minutes from an [installed](installation.md) Penicillium to a plotted batch. Tutorial 1,
[Your first batch](tutorials/01_first_batch.ipynb), goes further: batch phases, every channel, batch-to-batch
variation and saving the data.

## Run a batch

```python
from penicillium import Simulator

result = Simulator().run(seed=1)
print(f"Harvested penicillin: {result.total_yield:.0f} kg")  # about 3600 kg for seed 1
```

This simulates 230 h of fed-batch operation in 1150 samples of 12 minutes, following IndPenSim's default feeding
recipe with the pH and temperature loops in automatic. The seed fixes the batch's random initial conditions, kinetic
parameters and disturbances: the same seed always gives the same batch, and another seed a different batch from the
same plant.

`result.total_yield` is the **harvested** penicillin: what is in the vessel at the end plus what the periodic broth
draws removed. Do not compute it as final titre × final volume, which misses the draws.

## Look at it

```python
import matplotlib.pyplot as plt

df = result.to_pandas()  # index: time_h; one column per channel
df[["P", "X", "S", "DO2", "V", "PAA"]].plot(subplots=True, layout=(2, 3), figsize=(12, 6), sharex=True)
plt.show()
```

`result[name]` returns one channel as a NumPy array and `result.time` the times in hours. Penicillin `P`, biomass
`X` and substrate `S` are in g/L; dissolved oxygen `DO2` and `PAA` in mg/L; the volume `V` in L. Every channel is
listed with its unit in [Variables and units](variables.md), and [The process](process.md) explains what the curves
show.

## Take the controls

`run()` follows the recipe. To decide the inputs yourself, step through the batch one sample at a time:

```python
sim = Simulator()
obs = sim.reset(seed=1)  # obs: the latest online measurements
while not sim.done:
    u = sim.recipe_inputs()  # what the recipe would do next
    if sim.time >= 100:
        u["Fs"] *= 1.1  # your idea here: 10 % more sugar after 100 h
    obs, harvested_kg = sim.step(**u)
print(f"{sim.result().total_yield:.0f} kg")
```

The pH and temperature loops keep running underneath, as on a real plant.

## Where next

The [tutorials](tutorials/index.md) show each feature in a worked notebook: recipes and control, faults and
disturbances, lab data and Raman spectra, data sets for fault detection and soft sensors, reinforcement learning,
the differentiable model and the command line.
