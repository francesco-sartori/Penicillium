# Implementation notes and open questions

This page records every known point where Penicillium differs from IndPenSim, the doubts we have about how some
details of IndPenSim were meant to work, and what Penicillium does. The reference is **IndPenSim V2.01** (MATLAB,
Goldrick et al.), the release on
[MATLAB File Exchange](https://www.mathworks.com/matlabcentral/fileexchange/49041-industrial-scale-penicillin-simulationv2) (version 2.0.1, 9 July 2019):
`indpensim.m`, `indpensim_ode.m`, `fctrl_indpensim.m`, `indpensim_run.m`, `Raman_Sim.m`, `Substrate_prediction.m`
(main file header: "IndPenSim_V2.01 … Last editted 9th of July 2019"). This release is the reference for every
comparison in this documentation.

The entries below describe what we observe in the published code and what Penicillium does. Where we write that
a detail "may not be intended", that is our reading of the source, not a statement by its authors.

## 1. Where Penicillium and IndPenSim differ

| # | What | IndPenSim V2.01 | Penicillium |
|---|---|---|---|
| 1.1 | **Recipe lookup** | `if k <= Recipe(SQ), u = sp(SQ)`: a value holds *until* its time | The same (`hold="until"`, the default). `Profile(..., hold="from")` reads a value as applying *from* its time; applied to the IndPenSim tables this shifts every profile by one segment, and with the default recipe the broth discharge then runs for 26 h out of every 28 h instead of 2 h pulses. |
| 1.2 | Random numbers | Reseeds MATLAB's generator before each draw (`rng(Seed_ref + Batch_no + Rand_ref)`); the eight disturbances are consecutive `randn` calls after one seed. PRBS perturbations use `rng('shuffle')`, so they are not reproducible. | One independent `numpy.random.SeedSequence` stream per random quantity, identical on every platform. PRBS and Raman noise come from the simulator's `rng`, in separate streams, so recording spectra or not never changes the PRBS perturbations. The streams differ from MATLAB's, so batch *n* here is not batch *n* of the published IndPenSim data set: compare distributions, or replay MATLAB-generated initial conditions (`BatchParameters.from_matlab`). |
| 1.3 | ODE solver | `ode15s` with **default options** (`RelTol=1e-3`, `AbsTol=1e-6`, maximum step 0.1 x interval = 0.02 h), output on `t_k:h/20:t_k+1`. | LSODA with `rtol=1e-5`, `atol=1e-7`, maximum step `h/20` over exactly `[t_k, t_k+1]`, which keeps its own solver error well below MATLAB's, so differences to MATLAB runs measure MATLAB's solver error. Neither tolerance nor maximum step changes the agreement with MATLAB runs measurably (`docs/solver_sensitivity.md`, `docs/validation.md`). |
| 1.4 | Solver failures | — | A failed interval raises `SolverError` naming the sample; the result keeps the samples before it. With the default recipe the solver does not fail. |
| 1.5 | Batch length | Draws a variable length (`round(230 + 25·randn)` h; `Fixed_Batch_length = 1` selects the *variable* length). | The length is set explicitly, `SimulationConfig(batch_length_h=...)`, up to 350 h, with IndPenSim's full recipe tables; `scenarios.variable_batch_lengths` draws IndPenSim's distribution. |
| 1.6 | PLS model for PAA | `PAA_PLS_model.mat` | Not redistributed; `PAA_pred` uses a model of the same form fitted by Penicillium (`validation/train_paa_pls.py`). |

## 2. IndPenSim details we are unsure about

These are in the MATLAB source, so Penicillium keeps them by default. We are not certain that they are intended.

| # | What |
|---|---|
| 2.1 | pH controller: from sample 3 on, the previous error `ph_err1` does not include the setpoint (`- (-log10(pH_{k-2})) + error`), so the proportional term is not a difference of errors. |
| 2.2 | Heating PID uses the previous *cooling* flow `Fc` as its previous output. |
| 2.3 | `Fc = 0` is followed by `Fc = X.Fc.y(k-1)*0.3` in the heating branch, so the second assignment is the one that applies. |
| 2.4 | The growth-rate reset (`Inhib` 1 or 2) uses `mu_X_calc`, the growth rate integrated over one sample. |
| 2.5 | IndPenSim's PAT control of PAA (`Raman_spec = 2`) computes its error from the **true** PAA concentration; the PLS prediction `PAA_pred` enters only the derivative term, whose gain is `0*0.002 = 0`. The Raman soft sensor therefore does not affect the process; Penicillium records `PAA_pred` as an output channel (from its own PLS model) and controls on the true PAA like IndPenSim. |
| 2.6 | Off-line delay, unit uncertain: `indpensim_run.m` sets `Ctrl_flags.Off_line_delay = 4` with the comment "analysis time delay (hours)", and Goldrick et al. (2019, section 2.1) describe a 4 h delay. `indpensim.m` uses it as a sample index (`X.P.y(k-delay)`, with 12-minute samples), so the results are reported 4 samples (48 min) after sampling. We are not certain whether hours or samples were meant. Penicillium follows the code: its option is named for its unit, `offline_delay_steps=4` (12-minute samples); `offline_delay_steps=20` gives 4 h ([measurements](measurements.md)). |
| 2.7 | OUR and CER: the off-gas formulas of `indpensim.m` give values that rise and fall with the oxygen uptake and CO₂ production of the model, but their absolute scale (labelled g/min and g/h) is not consistent with the model's own oxygen uptake term, so the two channels cannot close an oxygen or carbon balance, and their ratio is not a quantitative respiratory quotient. We are not certain how the constants of these formulas were meant to be set. Penicillium keeps the V2.01 formulas, and the documentation presents `OUR` and `CER` as monitoring signals ([variables](variables.md#notes-on-units), [measurements](measurements.md)). |
| 2.8 | Dissolved CO₂ unit and threshold: Goldrick et al. (2015, Table 1) give the dissolved CO₂ concentration in g L⁻¹ and its critical value for growth as 35 mg L⁻¹ (Table 2). V2.01 inhibits growth with `0.5 (1 + tanh(7570 - 1000 CO2_d))`, which switches at `CO2_d` = 7.57, and simulated batches reach values of about 5–7. We are not certain how the unit of the state and this threshold were meant to relate. Penicillium follows the code and labels `CO2_d` in g/L, the unit of the paper; treat its absolute value with care. |

`SimulationConfig(quirks="fixed")` uses the alternative reading of 2.1 (the previous error includes the setpoint)
and 2.2 (the heating PID starts from the previous heating flow). Both default to IndPenSim's code so that batches
match MATLAB.

## 3. Comparison with the published papers

Details and figures in `notebooks/goldrick2019_benchmark.ipynb` and `notebooks/goldrick2015_simulation.ipynb`.

| # | Finding |
|---|---|
| 3.1 | **PAA control is not the IndPenSim default.** IndPenSim's campaigns and its MATLAB default use no PAA control. With PAT control (`Raman_spec = 2`) the yields are those of the paper's APC campaign (~3500 kg), not of its standard campaigns (~2900 kg). The default here is `RamanMode.RECORD` (spectra recorded, PAA fed by the recipe). |
| 3.2 | **Below-target batches are PAA overshoots.** The model's PAA terms are steep switches: production stops below ~200 mg/L, growth is inhibited above ~2400 mg/L, and in between PAA has no effect. Recipe-fed batches fall below target when PAA climbs above 2400 mg/L; any controller that keeps PAA in the band, from a soft sensor or the true value, gives practically the same batch. |
| 3.3 | **We could not reproduce the coolant fault of the 2019 paper (Fig. 7D).** Its batch lost ~10 g/L of penicillin with the temperature reaching ~298.7 K. The cooling faults in the V2.01 code behave differently: the coolant flow fault is a 20 h loss of cooling at 70-90 h, the temperature sensor fault a +0.4 K drift; both leave the average titre unchanged. The paper's run may have used a different fault profile. Aeration, substrate and pH sensor faults match the paper. |
| 3.4 | **Long batches need PAA dosing.** IndPenSim's recipe lowers the PAA feed at 200 h and stops it at 300 h, so PAA runs out after ~270 h in a 317 h batch and production stops. The 2015 plant adjusted PAA by hand from off-line measurements; the 2015 notebook emulates that. |
| 3.5 | **Nitrogen stays high.** Nitrogen is consumed down to ~520 mg/L in the 2015 paper's batch 3 but stays above ~1500 mg/L here, because the PAA feed supplies nitrogen. The paper fitted the PAA feed composition per batch; those values are not published. |

## 4. Sensitivity of the model itself

The model contains steep switches. The dissolved-CO2 inhibition `0.5 (1 + tanh(7570 - 1000 CO2_d))` changes from 1 to
0 within about 0.001 of `CO2_d`, the PAA terms within about 1 mg/L around 200 and 2400 mg/L. A batch that reaches a
switch can chatter on it (growth stops and restarts from one sample to the next). From that point, round-off decides
the trajectory: two solvers, two tolerances or MATLAB and Python give different batches, with yields a few percent
apart. This is a property of the model, not of either implementation: replay such batches with care
(`BatchParameters.from_matlab`) and compare them statistically.
