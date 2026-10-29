"""Determinism: the same seed gives the same batch.

``tests/data/determinism_golden.json`` was generated once (Windows, Python 3.14). CI runs this file on Linux, macOS
and Windows:

* the random inputs of a batch (initial state, kinetic parameters, disturbances) must match **exactly**;
* a 120 h batch with a sensor fault, PRBS feed perturbations and Raman noise must match to 1e-3 of each channel's
  range. Math libraries and SciPy builds round the last bit differently, and IndPenSim turns some of those bits
  into visible differences: after every sample, a state that is <= 0 is set to 0.001. While penicillin is still ~0
  (the first ~25 h) the solver returns a value within round-off of zero, and whether it lands just below or just
  above zero decides between 0.001 g/L and ~0 (SciPy 1.15 on Linux and Windows differ here); the batches then stay
  ~1e-4 apart. On one platform, runs are bit-identical (``test_no_hidden_global_randomness``).
"""

import json
from pathlib import Path

import numpy as np
import pytest

from penicillium import BatchParameters, Fault, SimulationConfig, Simulator

GOLD = json.loads((Path(__file__).parent / "data" / "determinism_golden.json").read_text())


@pytest.mark.parametrize("seed", [0, 1, 12345])
def test_random_inputs_are_bit_identical(seed):
    gold = GOLD[str(seed)]
    bp = BatchParameters.from_seed(seed, 1150)
    assert {k: repr(float(v)) for k, v in bp.x0.items()} == gold["x0"]
    assert [repr(float(v)) for v in bp.params] == gold["params"]
    for name, values in gold["disturbance_samples"].items():
        assert [repr(float(bp.disturbances[name][i])) for i in (0, 1, 500, 1150)] == values, name


def test_batch_matches_golden_run():
    gold = GOLD["trajectory_seed7"]
    cfg = SimulationConfig(fault=Fault.PH_SENSOR, prbs=True, batch_length_h=120.0)
    r = Simulator(config=cfg, backend="python").run(seed=7)
    idx = gold["samples"]
    for ch in ("P", "X", "S", "V", "T", "pH", "DO2", "PAA", "Fb", "Fs"):
        scale = max(abs(v) for v in gold[ch])
        np.testing.assert_allclose([r[ch][i] for i in idx], gold[ch], rtol=1e-3, atol=1e-3 * scale, err_msg=ch)
    assert r.raman[599].sum() == pytest.approx(gold["raman_sum_sample_599"], rel=1e-3)  # spectra follow P, X, S, PAA
    assert r.total_yield == pytest.approx(gold["total_yield"], rel=1e-3)


def test_no_hidden_global_randomness():
    """Seeded runs must not depend on NumPy's global generator (or the clock)."""
    cfg = SimulationConfig(prbs=True, batch_length_h=110.0)
    np.random.seed(1)  # noqa: NPY002 - the point of the test
    a = Simulator(config=cfg).run(seed=3)
    np.random.seed(2)  # noqa: NPY002
    b = Simulator(config=cfg).run(seed=3)
    for name in a.data:
        np.testing.assert_array_equal(a[name], b[name], err_msg=name)
    np.testing.assert_array_equal(a.raman, b.raman)
