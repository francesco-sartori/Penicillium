# Reporting a benchmark

A result obtained on simulated data can be repeated exactly by anyone, but only if the paper says how the data
were made and how the method was scored. When you publish a fault-detection, soft-sensor or control result
obtained with Penicillium, report at least the following.

| Item | Why | Where to find it |
|---|---|---|
| **Package version** | Numerical output may change between minor versions (with a changelog entry and an updated validation report) | `penicillium.__version__`, `campaign.json` |
| **Campaign seed** and campaign call | The seed fixes every batch of a campaign; the call fixes how many batches of each fault | `scenarios.fault_campaign(n_normal=..., n_per_fault=..., seed=...)` |
| **Non-default options** | Faults, Raman mode, batch length, measurement noise and so on change the data | `result.config` of any batch; `campaign.json` records only the generator, version and description |
| **Split seed** and split rule | Which batches went into training, validation and test; always split by batch | `camp.split(test_fraction=..., seed=...)`, or the list of batch ids |
| **Label used** | `fault_active` means "the cause acts" for process faults but "this batch is faulty" for sensor faults ([fault labels](scenarios.md#fault-labels-in-campaigns)); say which label each metric uses, and how you treated the sensor faults | your code |
| **Data the method saw** | Online measurements only (`camp.online()`), or also lab results, spectra or hidden states | your code |
| **Scoring rule** | Batch level or sample level; how an alarm before the fault starts is counted (a false alarm, not a detection); how delays are measured | your code |
| **Uncertainty** | With few test batches per class, give an interval for every rate (for example Clopper–Pearson for a detection rate) | your code |

Some properties of the IndPenSim faults affect what a benchmark measures:

- each fault type acts in the same fixed windows in every batch, so a classifier can learn the batch time instead
  of the process, and detection delays reflect the windows ([Faults](faults.md#faults));
- under the sensor faults, `T` and `pH` hold the true broth values, which makes detection easier than on a plant
  ([Faults](faults.md#sensor-faults-the-subtle-ones));
- a campaign with `seed=0` shares its batches with `Simulator().run(seed=n)` and with the default seeds of the
  command line ([Campaigns](scenarios.md#ready-made-campaigns)).

Fixed seed sets, a scoring script and the list of faults that can be detected from `camp.online()` are planned, as
a versioned benchmark protocol.

A suggested sentence for the methods section, next to the one in [Citing](citing.md):

> The data were generated with Penicillium x.y.z, `scenarios.fault_campaign(n_normal=N, n_per_fault=M, seed=S)`
> with default options, and split by batch with `camp.split(test_fraction=0.3, seed=R)`. Detection was scored per
> batch on `fault`, an alarm before the first fault window counting as a false alarm, and per sample on
> `fault_active`, with sensor faults scored from 40 h.
