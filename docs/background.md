# Background: IndPenSim and PenSimPy (checked 2026-10-17)

## IndPenSim (MATLAB)

- Reference: IndPenSim V2.01, the release on [MATLAB File Exchange](https://www.mathworks.com/matlabcentral/fileexchange/49041-industrial-scale-penicillin-simulationv2) (version 2.0.1,
  9 July 2019). Default solver `ode15s` with MATLAB's default options
  (`solv = 2` in `indpensim_run.m`).
- Published 100-batch data set (Goldrick et al. 2019): compared by distribution in
  [validation_100_batches.md](validation_100_batches.md). MATLAB's random streams differ from NumPy's, so
  individual batches cannot be matched.

## PenSimPy

[PenSimPy](https://pypi.org/project/pensimpy/) (Quartic.ai,
MIT) was the first Python port of IndPenSim, and Penicillium builds on it: its first version was ported from
PenSimPy 1.2.5 before being checked line by line against IndPenSim V2.01. PenSimPy's last release dates from June 2021 and its original repository (github.com/Quarticai/PenSimPy) is
no longer online. It pins NumPy 1.18, pandas 1.0 and SciPy 1.4, and its default solver path uses `fastodeint`, a
C++ extension built on Boost and OpenMP that is not published on PyPI, so `pip install pensimpy` does not complete
on current Python versions. It offers a step-by-step interface with a random-agent example, but no Gymnasium
environment.

Penicillium adds:

- an open licence (MIT, with IndPenSim's BSD 3-Clause for the parts derived from it) and documented provenance;
- pure Python on 3.10–3.14 with no compiler, tested on Linux, macOS and Windows, with an optional Numba backend;
- Gymnasium environments, Minari datasets and a differentiable JAX model;
- a browser-based DCS operator interface;
- all of IndPenSim's options, including its three inhibition models and eight faults, and statistical validation
  against the published IndPenSim data set.
