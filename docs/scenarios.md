# Campaigns and datasets

One batch is a curiosity; a hundred batches is a data set. Penicillium runs batches in parallel processes (about
380 batches per minute on an Intel Core i7-7700HQ with 16 GB RAM) and offers two levels of convenience:

- **`scenarios`**: ready-made campaigns for the common studies, returned as tidy tables;
- **`simulate_batches`**: any list of batches you specify, returned as `BatchResult` objects.

!!! warning "Scripts need a main guard"
    Parallel runs start fresh Python processes (the `spawn` method, on every operating system), and those
    processes import your script. Put the code that
    launches a campaign under `if __name__ == "__main__":`, or every worker will try to launch the campaign
    too, and Python will stop with a `RuntimeError` about the "bootstrapping phase":

    ```python
    from penicillium import scenarios

    if __name__ == "__main__":
        camp = scenarios.fault_campaign(n_normal=20, n_per_fault=5, seed=0)
        camp.save("faults/")
    ```

    Notebooks need no guard.

## Ready-made campaigns

Each function returns a `Campaign` with:

- `samples`: one row per batch and 12-minute sample: `batch_id`, `time_h`, `kind`, `fault` (the batch's fault
  code), `fault_active` (the per-sample label) and all 55 channels;
- `batches`: one row per batch: `batch_id`, `seed`, `kind`, `fault`, `fault_name`, `batch_length_h`,
  `total_yield_kg`, `final_penicillin_g_per_L`, `fault_onset_h`;
- `lab`: lab results in long form: `batch_id`, `sample_time_h`, `available_time_h`, `P`, `X`, `PAA`, `NH3`,
  `Viscosity`;
- `raman`: `{batch_id: spectra}` when spectra were kept, with the wavenumbers in `raman_wavenumber`.

Batch `i` of a campaign gets the seed `seed × 100 000 + i`, so a campaign is reproducible from its `seed` on any
platform, and campaigns with different seeds never share a batch.

!!! warning "Campaign seed 0 shares its batches with single runs and the command line"
    With `seed=0`, batch `i` of a campaign gets the seed `i`: the same batch as `Simulator().run(seed=i)` and as
    the batches of `penicillium generate` with its default `--seed-start 1`. If you mix these tools in one study,
    a training batch can reappear as a test batch. Use a campaign seed of 1 or more next to single runs and the
    command line, or check that the seeds do not overlap. One seeding scheme for all the tools is planned before
    version 1.0.

### Fault labels in campaigns

`samples.fault` is the fault code of the batch (0 for normal batches), the same in every sample. `fault_active`
is the per-sample label, copied from the `Fault_ref` channel:

- **process faults (1–6):** 1 exactly in the samples in which an input is forced (the cause acts), 0 elsewhere,
  including the samples between two windows of the same fault;
- **sensor faults (7, 8):** 1 in every sample of the batch, including the 40 h before the drift begins
  (IndPenSim's convention). The drift itself acts from 40 h (sample 201) on;
- **normal batches:** 0 everywhere.

`batches.fault_onset_h` is the time of the first sample with `fault_active` = 1, so for sensor faults it is the
start of the batch, not the start of the drift. Which label the tutorials use:

| Tutorial | Label used |
|---|---|
| 1–3, 6, 8 | No fault labels (nominal batches; tutorial 3 shows `Fault_ref` for each fault) |
| 4 | None (lab data, Raman and noise on nominal batches) |
| 5, fault detection | Batch level: `fault` (normal or faulty). Sample level: `fault_active` for process faults; for sensor faults the samples after 40 h, when the drift acts |
| 7, reinforcement learning | None (`IndPenSim-v0`, nominal batches) |
| 9, command line | `Fault_ref` is written to every file; the tutorial does not score detection |

### Fault detection and diagnosis

```python
from penicillium import scenarios

camp = scenarios.fault_campaign(n_normal=40, n_per_fault=10, seed=0)
train_ids, test_ids = camp.split(test_fraction=0.3)  # by batch, stratified by fault
X = camp.online()  # labels + online measurements only (no hidden states)
train = X[X.batch_id.isin(train_ids)]
```

The faulty batches cycle through the seven single faults (aeration, pressure, substrate feed, base flow, coolant
flow, temperature sensor, pH sensor). `faults=[...]` selects others, and `config=` changes everything else
(default: IndPenSim defaults without Raman). Read [Faults](faults.md#fault-labels) for what the labels mean,
especially for the sensor faults.

!!! tip "Split by batch, always"
    Neighbouring samples of a batch are almost identical. A random split by *sample* leaks the test batches into
    training, and you get a beautiful detector that fails on the first new batch. `camp.split` splits by batch.

When you publish results on these data, report what another group needs to repeat them: see
[Reporting a benchmark](benchmarking.md). Monitoring and soft-sensor models are not part of Penicillium.

### Soft sensors

```python
camp = scenarios.soft_sensor_campaign(n_batches=20, seed=0)
spectra = camp.raman[1]  # (samples, 2200) for batch 1
camp.lab.head()  # batch_id, sample_time_h, available_time_h, P, X, PAA, NH3, Viscosity
```

Raman spectra are recorded, and the feeds are perturbed as in IndPenSim's operator-controlled batches
(`prbs=True`), so that concentrations do not simply track batch time. Expect about 20 MB of spectra per batch.

### The published campaign

```python
camp = scenarios.goldrick2019_campaign(seed=0)
```

This has the structure of the published 100-batch IndPenSim data set: batches 1–30 recipe driven, 31–60
operator controlled (PRBS), 61–90 under PAA feedback control (APC), and 91–100 with faults. Batch lengths vary as
$230 + 25\,\varepsilon$ h. Use it to compare methods against published results, or to compare with the
published data itself: `validation/compare_100_batches.py` does exactly that ([validation](validation_100_batches.md)).

### Control benchmark

```python
import numpy as np

baseline = scenarios.control_benchmark(n_batches=10)  # the IndPenSim recipe
mine = scenarios.control_benchmark(
    policy=lambda obs, env: np.zeros(env.action_space.shape, np.float32)  # replace with yours
)
print(baseline.yield_kg.mean(), mine.yield_kg.mean())  # equal: a zero action *is* the recipe
```

This evaluates a policy on fixed test batches of the [Gymnasium environment](gymnasium.md) (needs the `gym`
extra). Use the same `seed` for every policy you compare, so that all policies face the same batches.

### Saving

```python
camp.save("my_campaign/")  # needs pyarrow (the parquet extra)
```

writes:

| File | Contents |
|---|---|
| `samples.parquet` | the `samples` table |
| `batches.csv` | the `batches` table |
| `lab.csv` | the `lab` table |
| `raman/<batch_id>.npy`, `raman/wavenumber.npy` | spectra (float32), when kept |
| `campaign.json` | generator, package version, description |

Read them back with `pandas.read_parquet`, `pandas.read_csv` and `numpy.load`.

## Any batches you like

`simulate_batches` runs a list of `BatchSpec(seed, config, initial_conditions, recipe)` in parallel and returns
the results in order:

```python
from penicillium import BatchSpec, SimulationConfig, simulate_batches

if __name__ == "__main__":
    specs = [
        BatchSpec(seed=s, config=SimulationConfig(temperature_setpoint=tsp))
        for tsp in (296.0, 298.0, 300.0)
        for s in range(1, 11)
    ]
    results = simulate_batches(specs, keep_raman=False)
    yields = [r.total_yield for r in results]
```

- `n_jobs`: worker processes (default: all CPUs); `n_jobs=1` runs in the current process.
- `progress(done, total, result)`: optional callback as batches finish.
- `keep_raman=False`: drop spectra from the results. Better still, set `raman_mode=RamanMode.OFF` in the config
  so they are never computed.

`scenarios.build_campaign(specs, kinds)` turns any list of specs into a `Campaign` with the tidy tables above.
