# FAQ and troubleshooting

## Results and interpretation

### Why doesn't seed *n* reproduce batch *n* of the published data set?

Because MATLAB's random number generator cannot be reproduced in Python, no seed maps to a published batch.
Compare **distributions** (that is how Penicillium is [validated](validation_100_batches.md)), or capture a
batch's random inputs in MATLAB and replay it with `BatchParameters.from_matlab`
([validation](validation.md#batch-by-batch-comparison-with-matlab)).

### Why do yields vary so much between seeds?

Because they do on the plant. Each batch draws its own initial conditions, kinetic parameters ($\mu_{x,max}$,
$\mu_p$, $k_La$ constant, PAA feed strength) and slow disturbances. Nominal batches give about 2800 ± 760 kg, and
the published recipe-driven batches 2913 ± 768 kg. If you compare strategies, use the same seeds for both and
look at paired differences ([tutorial 2](tutorials/02_recipes_and_control.ipynb)).

### My colleague gets slightly different numbers for the same seed.

Expect differences of about 1e-4 of each channel's range between machines. The random inputs are bit-identical,
but CPUs and math libraries round `exp` and `log` differently in the last bit. Batches that hit one of the
model's steep inhibition switches can amplify this to a few percent in yield ([quirks](quirks.md), section 4).
On the same machine and installation, runs are bit-identical.

### Why is the substrate concentration practically zero?

It is supposed to be. Penicillin production peaks at about 2 mg/L of sugar, so the plant runs
substrate-limited, and the model's production term is a narrow Gaussian around that value
([model](model.md#penicillin)). A batch with grams per litre of sugar has stopped making penicillin and
started making biomass.

### Why does penicillin decrease at the end of some batches?

Hydrolysis (about 0.26 %/h at pH 6.5 and 298 K), dilution by feeds, and production stopping when PAA leaves its
200–2400 mg/L band. Look at `PAA`: if it exceeds 2400 mg/L, growth stops; if it falls below 200 mg/L,
production stops.

### Why is the harvest larger than final titre × final volume?

Because the periodic broth draws removed penicillin during the batch, and `total_yield` counts it
([variables](variables.md#notes-on-units)).

### Are the sensor faults visible in `T` and `pH`?

The recorded `T` and `pH` are the true broth values, which drift away from the setpoint. The drifting
*measurement* that the controller saw is not stored, but you can reconstruct it ([faults](faults.md#sensor-faults-the-subtle-ones)).

## Errors

### `RuntimeError: An attempt has been made to start a new process before the current process has finished its bootstrapping phase`

You ran `simulate_batches` or a `scenarios` campaign from a script without a main guard. Wrap the call in
`if __name__ == "__main__":` ([campaigns](scenarios.md)).

### `SolverError`

The ODE solver could not integrate a 12-minute interval. The message names the sample and the time. Penicillium
stops there and returns only values the solver computed: `sim.result()` returns every sample up to the failure.

With the default recipe and settings this should not happen. It usually means the inputs drove the model
somewhere unphysical, for example:

- drawing broth until the vessel is nearly empty (a large or long `discharge`);
- feeding at rates far outside the recipe's range, or negative values;
- extreme initial conditions or parameters.

Check your inputs over the samples before the failure. The Gymnasium environment turns a solver failure into
a terminated episode with a penalty, so an RL agent learns not to do that again.

### `ImportError: backend='numba' needs numba`

Install the `fast` extra, or use `Simulator(backend="python")` (correct, but about 20× slower).

### `ImportError: penicillium.envs needs gymnasium`

Install the `gym` extra. `scenarios.control_benchmark` needs it too.

### Parquet errors from `Campaign.save` or `penicillium generate`

Install pyarrow (the `parquet` extra), or use `penicillium generate --format csv`.

### `ValueError: batch_length_h must be a multiple of 0.2 h in (0, 350.0]`

The batch length must be a whole number of 12-minute samples and at most 350 h, which is where IndPenSim's
recipe tables end.

## Performance

### The first run takes several seconds.

Numba compiles the model on first use and caches it on disk. Later runs start at full speed.

### How do I make campaigns faster or smaller?

- Turn Raman off (`raman_mode=RamanMode.OFF`) unless you need spectra. They cost about 50 % of run time and
  20 MB per batch.
- Use `simulate_batches` or `scenarios`, which use all CPU cores.
- Do not loosen the solver tolerances: it gains little time and costs accuracy
  ([solver sensitivity](solver_sensitivity.md)).

## Scope

### Can I change the agitator speed?

Not through the public API. Agitation is fixed at 100 rpm, as in IndPenSim's recipe. The model itself accepts
any speed, through the `RPM` entry of its parameter vector, if you build your own integration loop around
`penicillium.model.rhs` or `penicillium.jax_model.rhs`.

### Can I simulate a different strain or vessel?

Partly. The per-batch kinetic parameters (`mu_x_max`, `mu_p_max`, `alpha_kla`, `PAA_c`, `N_conc_paa`) and all
initial conditions can be set with `initial_conditions=`. The other constants (yields, vessel geometry, impeller,
heat transfer) are IndPenSim's, fitted to one industrial plant, and are fixed in `model.py`. Changing them makes
it a different benchmark. That may be exactly what you want, but call it something else in your paper.

### Is this a validated model of *my* plant?

No. It is a validated implementation of a published benchmark, which was fitted to one plant. It is excellent
for developing and comparing methods. Before you base decisions on your own process, fit a model to your own
data.
