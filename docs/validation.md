# Validation

Penicillium is checked in five independent ways. Each check has a script or test, so every claim here can be
rerun.

| # | Question | Method | Result | Where |
|---|---|---|---|---|
| 1 | Does the code implement IndPenSim? | Line-by-line comparison of model, controllers, recipes, faults, Raman simulation and PLS soft sensor with the MATLAB source of IndPenSim V2.01 | Every difference is listed and either aligned, switchable or explained | [quirks.md](quirks.md) |
| 2 | Does it match the published IndPenSim data? | 100-batch data set of Goldrick et al. (2019) vs simulated campaigns with the same strategies, lengths and faults (3 replicates, 300 batches) | Yield distributions: no significant difference detected for recipe-driven (KS p = 0.93), operator-controlled (p = 0.31) and fault batches (p = 0.63); the tests have low power (30 published batches per strategy, 10 with faults). APC yields 4 % lower (p = 0.10). Coverage of the simulated 5-95 % bands (about 90 % expected): 79-95 % in the channels of the main table; over every process state and measurement ([coverage appendix](validation_coverage.md)) 80-95 % for the recipe-driven, operator-controlled and APC batches and 73-92 % for the faulty batches. **The lowest coverage is 73 %, for the vessel weight `Wt` in the faulty batches** | [validation_100_batches.md](validation_100_batches.md), `validation/compare_100_batches.py` |
| 3 | Does it give the same batches as IndPenSim? | IndPenSim V2.01 run under GNU Octave with saved random inputs; 15 batches (recipe, variable length, faults 1-8, PRBS, Raman recording, PAT control) replayed in Penicillium | 14 of 15 batches within 0.1 % on yield and ~1e-4 on the states; the 15th takes another path at the dissolved-CO2 inhibition threshold (0.7 % yield). With tight solver tolerances on both sides, 4 batches including that one agree to < 1e-7 on yield over the whole batch | [validation_octave.md](validation_octave.md), `tests/test_octave_v201.py` |
| 4 | How much do numerical settings matter? | Same batches with LSODA at several tolerances and with BDF, against a tight-tolerance reference | Default settings within ~1e-5 of the reference (DO2: 3e-3) | [solver_sensitivity.md](solver_sensitivity.md) |
| 5 | Is a seeded batch the same everywhere? | Golden random inputs and a golden 120 h batch (fault, PRBS, Raman noise), tested on Linux, macOS and Windows in CI | Random inputs bit-identical and trajectories within about 1e-4 on Linux, macOS and Windows (IndPenSim clips states <= 0 to 0.001, which turns last-bit differences near zero into small offsets) | `tests/test_determinism.py` |

## How to read the statistical comparison

The two-sample Kolmogorov-Smirnov (KS) test is the primary test: it compares the whole yield distributions
(location, spread and shape) without assuming normality, which the yields of faulty batches are not. A p-value
above 0.05 means that **no significant difference was detected**, not that the distributions are equal. The
published data set has 100 batches (30 per strategy, 10 with faults), which limits the power of any test: a shift
of the mean yield by 5 % would be detected in only about 12 % of such comparisons for the recipe-driven batches.
The [100-batch page](validation_100_batches.md#size-of-the-differences) therefore also gives, for each strategy,
the mean difference with its 95 % Welch interval and the power of the KS test, so that you can judge the size of
the gap yourself.

The coverage of the trajectory bands is limited by the same data. The samples of one batch are strongly
correlated in time, so with 30 published batches per strategy the coverage of a band varies by several percentage
points by chance, and more for the 10 faulty batches. The main table of the
[100-batch page](validation_100_batches.md#trajectory-envelopes) shows 12 channels, with coverages of 79-95 %.
Over **every** channel ([coverage appendix](validation_coverage.md)), the coverage of the process states and
measurements is 80-95 % for the recipe-driven, operator-controlled and APC batches, and 73-92 % for the faulty
batches. **The lowest value is 73 %, for the vessel weight `Wt` in the faulty batches**: 27 % of those
published samples lie outside the simulated band, against about 10 % expected. The faulty batches have the
lowest coverage in most channels. We read the result as no systematic deviation that these data can detect,
not as a proof of equivalence, but the faulty batches are the weakest part of the comparison.

## Batch-by-batch comparison with MATLAB

This has been done with IndPenSim V2.01 run under GNU Octave: see
[Batch-by-batch comparison with IndPenSim V2.01](validation_octave.md), with 15 batches whose inputs are saved in
`validation/octave/data`. That page also explains [how to replay those 15 batches in MATLAB](validation_octave.md#replay-the-15-batches-in-penicillium-or-in-matlab).

MATLAB's random generator cannot be reproduced in Python, so batch *n* here is not batch *n* of a MATLAB campaign.
To compare single batches with MATLAB, capture the random inputs in MATLAB and replay them:

```matlab
% in indpensim_run.m, after the disturbances are generated:
save('batch.mat', 'x0', 'alpha_kla', 'PAA_c', 'N_conc_paa', 'distMuP', 'distMuX', 'distcs', 'distcoil', ...
     'distabc', 'distPAA', 'distTcin', 'distO_2in')
```

```python
from penicillium import BatchParameters, RamanMode, SimulationConfig, Simulator

config = SimulationConfig(raman_mode=RamanMode.OFF, raman_noise=False, batch_length_h=T)  # T, faults as in MATLAB
result = Simulator(config=config).run(batch_parameters=BatchParameters.from_matlab("batch.mat"))
```

Two caveats. MATLAB runs IndPenSim with `ode15s` at its default tolerance (`RelTol = 1e-3`), looser than
Penicillium's, so part of any difference is MATLAB's own solver error. And batches that reach one of the model's
steep inhibition switches become chaotic from that point ([quirks.md](quirks.md), section 4).

## Open points

- APC campaign: simulated yields average 3356 kg against 3484 kg published (sd ~320 kg in both).
- Faulty batches: the coverage of the simulated bands is lower than for the other strategies (73-92 % over the
  process states and measurements), and lowest for the vessel weight `Wt` (73 %).
- A few published batches show pH excursions to 5.4-5.8 lasting 10-50 h, and one operator-controlled batch runs
  with low dissolved oxygen for most of the batch; neither appears in 300 simulated batches.
- The coolant fault of Goldrick et al. (2019), Fig. 7D, is not reproduced by IndPenSim's published fault profile
  ([quirks.md](quirks.md) 3.3).
