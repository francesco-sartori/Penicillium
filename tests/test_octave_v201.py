"""Batch-by-batch agreement with IndPenSim V2.01 run under GNU Octave (docs/validation_octave.md).

``validation/octave/data`` holds 15 batches run with V2.01's code and its default ``ode15s`` settings, plus four of
them at RelTol 1e-8 (``tight/``). Each is replayed in Penicillium with the same inputs.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation" / "octave"))
from compare_octave import DATA, compare

CASES = sorted(DATA.glob("case_*.mat"))
TIGHT = sorted((DATA / "tight").glob("case_*.mat"))
#: Batch 3 reaches the dissolved-CO2 inhibition threshold at 88 h, where round-off decides the path (quirks.md 4).
CHAOTIC = {"case_03"}

pytestmark = pytest.mark.slow


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_matches_v201_at_default_tolerances(path):
    r = compare(path)
    if path.stem in CHAOTIC:
        assert r["yield_rel_err"] < 3e-2
        return
    assert r["yield_rel_err"] < 1e-3
    assert r["states_mean"] < 1e-3
    assert r["Fs_max"] == 0  # recipe, faults and PRBS steps reproduced exactly
    if r["raman"] != 2:  # under PAT control the PAA feed is a PID output
        assert r["Fpaa_max"] == 0


@pytest.mark.parametrize("path", TIGHT, ids=lambda p: p.stem)
def test_matches_v201_at_tight_tolerances(path):
    r = compare(path, rtol=1e-10, atol=1e-12)
    assert r["yield_rel_err"] < 1e-6
    assert np.isnan(r["first_divergence_h"])  # no state ever differs by 1e-3 of its peak
