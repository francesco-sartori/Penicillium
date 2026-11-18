"""Non-regression against 0.1.0a1: without the fault options, every output is that of 0.1.0a1.

``tests/data/fault_golden_0.1.0a1.json`` holds the outputs of the code of tag ``v0.1.0a1`` (generator:
``tests/data/make_fault_golden.py``) for faults 0-8, two seeds, both ``quirks`` readings, the three inhibition models,
Raman with PRBS, PAT control and the Numba backend, plus a campaign and the command line. On a machine with the same
fingerprint (platform, Python, NumPy, SciPy, Numba) every channel must match **bit for bit**; elsewhere the labels must
match exactly and the trajectories to the tolerance of ``test_determinism.py`` (math libraries round differently).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import _fault_golden_cases as gc
import numpy as np
import pytest

from penicillium import BatchSpec, Fault, RamanMode, SimulationConfig, Simulator, _numba, scenarios

GOLDEN_PATH = Path(__file__).parent / "data" / "fault_golden_0.1.0a1.json"
GOLDEN = json.loads(GOLDEN_PATH.read_text())
CASES = gc.cases()


def _exact(backend: str) -> bool:
    return GOLDEN["fingerprint"][backend] == gc.fingerprint(backend)


def _params():
    for name, spec in CASES.items():
        marks = [pytest.mark.slow] if spec["slow"] else []
        if spec["backend"] == "numba":
            marks.append(pytest.mark.skipif(not _numba.AVAILABLE, reason="needs numba"))
        yield pytest.param(name, marks=marks, id=name)


@pytest.mark.parametrize("name", _params())
def test_batch_matches_0_1_0a1(name):
    spec, gold = CASES[name], GOLDEN["cases"][name]
    got = gc.run_case(spec)
    assert got["samples"] == gold["samples"]
    assert got["values"]["Fault_ref"] == gold["values"]["Fault_ref"]  # labels: exact everywhere
    assert got["channels"]["Fault_ref"] == gold["channels"]["Fault_ref"]
    if _exact(spec["backend"]):
        assert got == gold
        return
    for ch in gc.SAMPLED_CHANNELS:
        g = np.array([float(v) for v in gold["values"][ch]])
        scale = max(np.abs(g).max(), 1e-12)
        np.testing.assert_allclose(
            [float(v) for v in got["values"][ch]], g, rtol=1e-3, atol=1e-3 * scale, err_msg=f"{name}: {ch}"
        )
    assert float(got["total_yield"]) == pytest.approx(float(gold["total_yield"]), rel=1e-3)


def test_campaign_matches_0_1_0a1():
    got, gold = gc.run_campaign(), GOLDEN["campaign"]
    assert got["batches_columns"] == gold["batches_columns"]
    assert got["samples_columns"] == gold["samples_columns"]
    assert got["fault_active"] == gold["fault_active"]
    if _exact_auto():
        assert got == gold


def test_cli_metadata_matches_0_1_0a1():
    got, gold = gc.run_cli(), GOLDEN["cli"]
    if _exact_auto():
        assert got == gold


def _exact_auto() -> bool:
    """Campaigns and the command line use the default backend: numba when installed (the golden was made with it)."""
    return _exact("numba") if _numba.AVAILABLE else False


def test_0_1_0a1_call_sites_still_work():
    """Code written for 0.1.0a1 runs unchanged."""
    cfg = SimulationConfig(fault=Fault.AERATION, raman_mode=RamanMode.OFF, batch_length_h=21.0)
    assert replace(cfg, fault=Fault.PH_SENSOR).fault == Fault.PH_SENSOR
    assert SimulationConfig(fault=4).fault == Fault.BASE_FLOW
    r = Simulator(config=cfg).run(seed=1)
    assert r["Fault_ref"][99] == 1 and r["Fault_ref"][98] == 0  # sample 100 (20 h)
    assert r["Fg"][99] == 20
    assert set(r.metadata) == {"initial_conditions", "growth_rate_resets"}
    camp = scenarios.fault_campaign(2, 1, (Fault.AERATION,), 0, cfg, 1)  # positional, as in 0.1.0a1
    assert list(camp.batches.columns) == GOLDEN["campaign"]["batches_columns"]
    assert BatchSpec(seed=1, config=cfg).config.fault == Fault.AERATION
