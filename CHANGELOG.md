# Changelog

All notable changes are listed here. Versions follow [Semantic Versioning](https://semver.org/); a minor version
may change numerical output only with an entry here and an updated validation report.

## Unreleased

- README badges (PyPI, documentation, DOI) and the Zenodo concept DOI in `CITATION.cff`, the README and
  [citing](docs/citing.md).

## 0.1.0a1 (2026-10-29)

- `CITATION.cff` gives a single licence, `MIT`, so that Zenodo can read it and archive the release. The parts
  derived from IndPenSim are still also under its BSD 3-Clause License (`LICENSE`, `NOTICE`). No code changes.

## 0.1.0a0 (2026-10-29)

First public release (alpha).

- The project is called **Penicillium**: `pip install penicillium`, `import penicillium`, command `penicillium`
  (working name during development: `pypensim-next`).

### Simulator
- Pure-Python IndPenSim simulator (NumPy, SciPy, pandas), optional Numba backend (`[fast]`), 55 channels, Raman
  spectra, faults 0-8, disturbances, PRBS feeds, PAT control of PAA, offline lab measurements, batches up to 350 h.
- Follows MATLAB IndPenSim V2.01.
- `SimulationConfig(quirks="matlab" | "fixed")`: IndPenSim's controller code as written, or an alternative reading of two of its details.
- `SimulationConfig(inhibition=0 | 1 | 2)`: IndPenSim's three inhibition models.
- `BatchParameters`: the random inputs of a batch, replayable; `BatchParameters.from_matlab()` replays a batch
  captured from MATLAB IndPenSim.
- Seeding: every random quantity has its own `SeedSequence` stream; the random inputs of a batch are bit-identical
  on every platform (trajectories agree to ~1e-4) and independent of NumPy's global generator. The eight disturbances are independent, as in IndPenSim.
- `PAA_pred` channel: PAA predicted from the Raman spectrum with a PLS model fitted by this project.
- `metadata["growth_rate_resets"]`: samples where IndPenSim's growth-rate reset fired.
- `MeasurementNoise` and `Sensor`: sensor and assay errors (white noise, relative error, calibration offset,
  drift, quantisation, bounds) added to a copy of a result; exact values kept in `BatchResult.truth`. `OUR`/`CER`
  are recomputed from the measured off-gas. Preset `MeasurementNoise.typical()` (measurements only; recipe set
  points stay exact); `measurement_noise=` on the
  campaign builders; `penicillium generate --noise typical`. The simulator stays noise-free.

### Ecosystem
- `penicillium.envs`: Gymnasium environments `IndPenSim-v0`, `IndPenSimFault-v0`, `IndPenSimRaman-v0`
  (pass `check_env`, seeded); `collect_minari_dataset` for offline RL.
- `penicillium.scenarios`: one-call fault, soft-sensor and Goldrick-2019 campaigns in tidy form, batch-wise
  splits, and a control benchmark.
- `simulate_batches` for parallel campaigns; `penicillium generate` command-line dataset generator.

### Operator console
- `penicillium dcs` (`[dcs]` extra): one batch in real time in a DCS-style web app (FastAPI + React):
  process graphic with PV and SP, faceplates with trends, CAS/AUTO modes and operator setpoints, priority alarms
  with acknowledgement, event journal, offline lab results, Raman spectrum, hold/resume/abort, ×1 to ×36000 speed.
  `penicillium.dcs.BatchSession` is the same logic without the web layer.

### Differentiable model
- `penicillium.jax_model` (`[jax]` extra): the model right-hand side as a jit-compiled JAX function generated from
  the same source as the NumPy/Numba versions, with exact state and parameter Jacobians; gradients through stiff
  integration (e.g. diffrax) match finite differences.

### Validation
- Line-by-line comparison with IndPenSim V2.01 (`docs/quirks.md`).
- Statistical comparison with the published 100-batch IndPenSim data set (`docs/validation.md`), with mean
  differences, Welch intervals and KS power per strategy, a coverage appendix for every channel, and the method
  and evidence behind the fault types inferred for published batches 91-100.
- Cross-platform determinism tests.

### Documentation
- Changes after a review of the pre-release manual: "Limitations at a glance" on
  the first page; "no significant difference detected" with KS p-values and test power instead of
  "indistinguishable"; fault labels (`fault_active`) defined for process and sensor faults; the limits of the
  worked examples stated (batch-level counting and Clopper-Pearson intervals in tutorial 5, sample-wise
  cross-validation in tutorial 6, baselines in tutorial 7, Student's t interval in tutorial 2); reward shaping
  equivalence of the Gymnasium reward; replay of the 15 Octave batches in Penicillium and MATLAB; seeding overlap
  warnings; new pages on reporting a benchmark and related simulators.
