# AGENTS.md

Guidance for coding agents (and people) working on this repository. User documentation is at
https://penicillium.readthedocs.io; an index for language models is at
https://penicillium.readthedocs.io/en/latest/llms.txt.

## What this is

Penicillium is a Python implementation of the IndPenSim penicillin fermentation simulator (Goldrick et al., 2015,
2019). The reference is **IndPenSim V2.01** (MATLAB File Exchange 49041, version 2.0.1, 9 July 2019). By default the
simulator reproduces V2.01 batch by batch; everything else is an option.

## Setup and checks

```bash
pip install -e ".[dev]"        # tests, Numba, Gymnasium, JAX, console, ruff
pytest -m "not slow"           # fast suite (about a minute)
pytest                         # everything, including full-batch regressions (use -n auto with pytest-xdist)
ruff check .                   # lint
ruff format --check .          # formatting; also covers notebooks and Python blocks in Markdown
pip install -e ".[docs]" && mkdocs build   # documentation (strict mode: warnings fail the build)
```

Run the fast suite and ruff after every change, and the full suite before a pull request.

## Layout

| Path | Contents |
|---|---|
| `src/penicillium/model.py` | Model right-hand side (`rhs`, `rhs_into`); Numba (`_numba.py`) and JAX (`jax_model.py`) versions are generated from it |
| `src/penicillium/simulator.py` | `Simulator`, `SimulationConfig`, `BatchParameters`, `Fault`: control loops, faults, the sample loop |
| `src/penicillium/faults.py` | `FaultSpec`: fault onset, duration, magnitude and shape options |
| `src/penicillium/scenarios.py` | Ready-made campaigns (`fault_campaign`, `soft_sensor_campaign`, ...) |
| `src/penicillium/noise.py`, `raman.py`, `recipe.py`, `result.py` | Measurement noise, Raman spectra, recipes, results |
| `src/penicillium/envs.py`, `dcs/`, `cli.py` | Gymnasium environments, operator console, command line |
| `tests/` | pytest suite; `tests/data/` holds golden files and their generators |
| `docs/` | MkDocs site; `docs/tutorials/*.ipynb` are stored with outputs and not executed by the docs build |
| `mkdocs_hooks.py` | Docs build hooks: notebook links, tutorials zip, Markdown copies, `llms.txt`, `llms-full.txt` |
| `validation/`, `benchmarks/`, `notebooks/` | Validation scripts and reports, speed benchmarks, case studies |

## Rules

- **IndPenSim V2.01 behaviour stays the default.** New behaviour is opt-in (a new option with a default that keeps
  the old behaviour) and is described as an addition to IndPenSim. Code written for the previous release must run
  unchanged.
- **Default outputs must not change.** `tests/test_fault_regression.py` compares every channel with the outputs of
  0.1.0a1 (bit for bit on the platform that generated the golden file); `tests/test_determinism.py` and
  `tests/test_octave_v201.py` check seeding and agreement with V2.01. If a default output must change, that needs a
  CHANGELOG entry and an updated validation report.
- **Randomness:** every random quantity has its own `numpy.random.SeedSequence` stream derived from the batch seed.
  New random inputs get their own spawn key, so they never shift existing draws. Never use NumPy's global generator
  or Python's `hash()` for seeding.
- **Differences from IndPenSim** go in `docs/quirks.md`, in neutral wording: describe what Penicillium does and
  record doubts about the reference code as doubts.
- **Style:** type hints, Google-style docstrings, ruff with 120 columns. Documentation prose uses no em dashes
  (use a colon, parentheses or commas).
- **Changelog:** user-visible changes get an entry in `CHANGELOG.md`.
- Keep changes minimal: no refactors that a change does not need.

## Golden files

`tests/data/fault_golden_0.1.0a1.json` is generated from the code of tag `v0.1.0a1`:

```bash
git worktree add --detach ../penicillium-a1 v0.1.0a1
PYTHONPATH=../penicillium-a1/src python tests/data/make_fault_golden.py
git worktree remove ../penicillium-a1
```

Do not regenerate it from the current code: it would then test nothing.
