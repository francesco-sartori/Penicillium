# Contributing to Penicillium

Thank you for helping. Issues and pull requests are welcome.

## Set up

```bash
git clone https://github.com/francesco-sartori/Penicillium.git
cd Penicillium
pip install -e ".[dev]"
```

## Before you open a pull request

- Run the fast tests: `pytest -m "not slow"` (seconds). `pytest` also runs the full batches (about 4 min).
- Lint and format with ruff (120 columns, configured in `pyproject.toml`): `ruff check .` and `ruff format .`.
- Add an entry under "Unreleased" in [CHANGELOG.md](CHANGELOG.md).
- If the change alters simulator output, say so in the CHANGELOG entry and update the validation report: rerun
  `validation/compare_100_batches.py` (writes `docs/validation_100_batches.md` and
  `docs/validation_coverage.md`) and check the batch-by-batch comparison with IndPenSim V2.01
  (`tests/test_octave_v201.py`, [docs/validation_octave.md](docs/validation_octave.md)).

## Where to start

Issues labelled
[good first issue](https://github.com/francesco-sartori/Penicillium/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
are small and self-contained.

## Reporting a bug

Open an [issue](https://github.com/francesco-sartori/Penicillium/issues/new) with:

- the Penicillium version (`python -c "import penicillium; print(penicillium.__version__)"`), Python version and
  operating system;
- a minimal script that reproduces the problem, including the seed and any `SimulationConfig` options;
- what you expected and what you got (full traceback, or the values that differ).

Differences from IndPenSim that are already known are listed in
[differences and quirks](https://penicillium.readthedocs.io/en/latest/quirks/).
