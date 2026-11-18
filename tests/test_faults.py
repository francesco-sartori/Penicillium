"""Fault onset, duration, magnitude and shape options (``FaultSpec``)."""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from penicillium import Fault, FaultSpec, MeasurementNoise, RamanMode, SimulationConfig, Simulator, scenarios
from penicillium.faults import Choice, FaultWindow, Normal, Uniform, draw_windows

OFF = {"raman_mode": RamanMode.OFF}


def run(specs, hours: float, seed: int = 1, **kw):
    return Simulator(config=SimulationConfig(fault_specs=specs, batch_length_h=hours, **OFF, **kw)).run(seed=seed)


def quadratic(tau: float) -> float:
    return tau**2


# ---------------------------------------------------------------- the IndPenSim preset


@pytest.mark.parametrize("fault", [1, 2, 3, 4, 5, 6, 7, 8])
@pytest.mark.parametrize("hours", [60.0, pytest.param(280.0, marks=pytest.mark.slow)])
def test_preset_gives_the_inputs_of_the_default_bit_for_bit(fault, hours):
    cfg = SimulationConfig(fault=Fault(fault), batch_length_h=hours, **OFF)
    a = Simulator(config=cfg).run(seed=1)
    b = run(FaultSpec.indpensim(fault), hours)
    assert b.config.fault == fault
    for name in a.data:
        if name != "Fault_ref":
            np.testing.assert_array_equal(a[name], b[name], err_msg=name)
    assert a.total_yield == b.total_yield
    if fault in (7, 8):  # labelled from the start of the drift (sample 200), not the whole batch
        np.testing.assert_array_equal(b["Fault_ref"], (np.arange(1, len(b.time) + 1) >= 200).astype(float))
    else:
        np.testing.assert_array_equal(a["Fault_ref"], b["Fault_ref"])


def test_preset_windows():
    assert [(s.onset_h, s.duration_h, s.magnitude) for s in FaultSpec.indpensim("aeration")] == [
        (20.0, 4.0, 20.0), (100.0, 10.0, 20.0)
    ]  # fmt: skip
    (drift,) = FaultSpec.indpensim(Fault.PH_SENSOR)
    assert (drift.onset_h, drift.duration_h, drift.magnitude) == (40.0, 120.0, 0.1)
    assert (drift.shape, drift.hold) == ("ramp", True)
    assert len(FaultSpec.indpensim(Fault.ALL)) == 11


# ---------------------------------------------------------------- shapes and effects


def window(shape="step", effect="offset", first=10, last=20, magnitude=2.0, hold=False):
    return FaultWindow(Fault.SUBSTRATE_FEED, "Fs", effect, shape, hold, first, last, magnitude)


def test_step_is_constant_over_the_window():
    w = window()
    assert [w.acts(k) for k in (9, 10, 20, 21)] == [False, True, True, False]
    assert {w.amount(k) for k in range(10, 21)} == {2.0}


def test_ramp_is_a_sawtooth():
    w = window("ramp")
    assert w.amount(10) == 0.0 and w.amount(20) == 2.0 and w.amount(15) == pytest.approx(1.0)
    assert not w.acts(21)  # back to 0 right after the window
    held = window("ramp", hold=True)
    assert held.acts(500) and held.amount(500) == pytest.approx(2.0)


def test_custom_ramp_shape_and_its_bounds():
    w = window(quadratic)
    assert w.amount(15) == pytest.approx(0.5) and w.amount(20) == pytest.approx(2.0)
    with pytest.raises(ValueError, match="expected"):
        window(lambda tau: 2.0).amount(15)


def test_effects():
    assert window(effect="set", magnitude=5.0).apply(12, 80.0) == 5.0
    assert window("ramp", effect="set", magnitude=0.0).apply(15, 80.0) == pytest.approx(40.0)
    assert window(effect="scale", magnitude=0.25).apply(12, 80.0) == 60.0
    assert window(effect="offset", magnitude=-100.0).apply(12, 80.0) == 0.0  # flows stay >= 0


def test_zero_duration_acts_in_one_sample():
    r = run(FaultSpec("aeration", onset_h=10.0, duration_h=0.0, magnitude=5.0), 12.0)
    assert list(np.flatnonzero(r["Fault_ref"]) + 1) == [50]
    assert r["Fg"][49] == 5.0
    (w,) = draw_windows([FaultSpec("aeration", onset_h=10.0, duration_h=0.0, shape="ramp", magnitude=5.0)], 1, 60)
    assert w.amount(50) == 5.0


# ---------------------------------------------------------------- labels and the batch table


def test_labels_follow_the_window():
    r = run(FaultSpec("aeration", onset_h=10.0, duration_h=2.0, magnitude=12.0), 15.0)
    active = np.flatnonzero(r["Fault_ref"]) + 1
    assert list(active) == list(range(50, 61))  # 10 h to 12 h, both included
    np.testing.assert_array_equal(r["Fg"][active - 1], 12.0)
    assert r.metadata["fault_windows"] == [{
        "fault": 1, "fault_name": "AERATION", "target": "Fg", "effect": "set", "shape": "step", "hold": False,
        "onset_h": 10.0, "end_h": 12.0, "magnitude": 12.0,
    }]  # fmt: skip


def test_sensor_fault_offsets_the_reading_in_the_window_only():
    r = run(FaultSpec("temperature_sensor", onset_h=10.0, duration_h=4.0, magnitude=0.4, shape="step"), 20.0)
    assert list(np.flatnonzero(r["Fault_ref"]) + 1) == list(range(50, 71))
    ref = Simulator(config=SimulationConfig(batch_length_h=20.0, **OFF)).run(seed=1)
    np.testing.assert_array_equal(r["T"][:49], ref["T"][:49])
    assert r["T"][70] > ref["T"][70]  # the loop drives the true temperature up while the reading is low


def test_campaign_reflects_the_drawn_windows():
    cfg = SimulationConfig(batch_length_h=60.0, **OFF)
    camp = scenarios.fault_campaign(1, 3, (Fault.AERATION, Fault.PH_SENSOR), seed=4, config=cfg, n_jobs=1,
                                    randomise=True)  # fmt: skip
    b, w = camp.batches, camp.fault_windows
    assert "fault_end_h" in b.columns and list(w.batch_id) == [2, 3, 4, 5, 6, 7]
    faulty = b[b.kind == "fault"].set_index("batch_id")
    for row in w.itertuples():
        assert faulty.loc[row.batch_id, "fault_onset_h"] == pytest.approx(row.onset_h)
        if not row.hold:
            assert faulty.loc[row.batch_id, "fault_end_h"] == pytest.approx(row.end_h)
        s = camp.samples[camp.samples.batch_id == row.batch_id]
        assert s.loc[s.fault_active == 1, "time_h"].min() == pytest.approx(row.onset_h)
    assert w[w.fault == 1].onset_h.nunique() == 3  # timing no longer gives the fault away
    assert list(b.fault) == [0, 1, 1, 1, 8, 8, 8]


def test_campaign_saves_the_windows(tmp_path):
    cfg = SimulationConfig(batch_length_h=30.0, **OFF)
    spec = FaultSpec("substrate_feed", onset_h=Uniform(5, 20), duration_h=2.0, magnitude=0.5, effect="scale")
    camp = scenarios.fault_campaign(0, 2, (spec,), seed=0, config=cfg, n_jobs=1)
    camp.save(tmp_path)
    assert len((tmp_path / "fault_windows.csv").read_text().splitlines()) == 3
    assert scenarios.fault_campaign(1, 0, seed=0, config=cfg, n_jobs=1).fault_windows is None


# ---------------------------------------------------------------- distributions and seeding


def test_distributions_stay_in_bounds():
    rng = np.random.default_rng(0)
    assert all(2 <= Uniform(2, 3).draw(rng) <= 3 for _ in range(200))
    assert all(1 <= Normal(1, 5, low=1, high=2).draw(rng) <= 2 for _ in range(200))
    assert {Choice([2, 20]).draw(rng) for _ in range(200)} == {2.0, 20.0}
    with pytest.raises(ValueError):
        Uniform(3, 2)


def test_randomise_defaults():
    for seed in range(30):
        (w,) = draw_windows([FaultSpec("coolant_flow", randomise=True)], seed, 1150)
        duration = (w.last - w.first) * 0.2
        assert 20 - 0.2 <= duration <= 30 + 0.2 and w.first * 0.2 >= 20 - 0.1 and w.last <= 1150
        assert (w.effect, w.magnitude, w.shape) == ("set", 2.0, "step")
        (d,) = draw_windows([FaultSpec("ph_sensor", randomise=True)], seed, 1150)
        assert (d.last - d.first, d.shape, d.hold, d.magnitude) == (600, "ramp", True, 0.1)


def test_draws_are_reproducible_and_each_field_has_its_own_stream():
    spec = FaultSpec("aeration", onset_h=Uniform(20, 100), duration_h=Uniform(2, 8), magnitude=Uniform(5, 25))
    a, b = draw_windows([spec], 7, 1150), draw_windows([spec], 7, 1150)
    assert a == b and a != draw_windows([spec], 8, 1150)
    fixed = FaultSpec("aeration", onset_h=Uniform(20, 100), duration_h=3.0, magnitude=Uniform(5, 25))
    (c,) = draw_windows([fixed], 7, 1150)
    assert (c.first, c.magnitude) == (a[0].first, a[0].magnitude)  # fixing the duration moves nothing else


def test_fault_draws_do_not_shift_the_other_random_inputs():
    cfg = SimulationConfig(prbs=True, raman_mode=RamanMode.RECORD, batch_length_h=120.0)
    spec = FaultSpec("aeration", onset_h=Uniform(20, 60), duration_h=Uniform(2, 8), magnitude=Uniform(5, 25))
    plain, faulty = Simulator(config=cfg), Simulator(config=replace(cfg, fault_specs=spec))
    plain.reset(seed=5)
    faulty.reset(seed=5)
    assert plain._bp.x0 == faulty._bp.x0 and plain._bp.params == faulty._bp.params
    for name in plain._bp.disturbances:
        np.testing.assert_array_equal(plain._bp.disturbances[name], faulty._bp.disturbances[name])
    assert plain._rng.bit_generator.state == faulty._rng.bit_generator.state
    assert plain._prbs_rng.bit_generator.state == faulty._prbs_rng.bit_generator.state
    a, b = plain.run(seed=5), faulty.run(seed=5)
    np.testing.assert_array_equal(plain._prbs, faulty._prbs)  # same PRBS steps although the batches differ
    assert plain._rng.bit_generator.state == faulty._rng.bit_generator.state  # Raman noise drew the same numbers
    # Measurement noise: the same draws; compared before the fault, since some errors scale with the true value.
    n = int(np.flatnonzero(b["Fault_ref"])[0])
    noise = MeasurementNoise.typical()
    na, nb = noise.apply(a, seed=5), noise.apply(b, seed=5)
    for name in na.truth:
        np.testing.assert_array_equal(na[name][:n], nb[name][:n], err_msg=name)


def test_draws_are_the_same_in_other_processes():
    code = (
        "import json; from penicillium.faults import FaultSpec, draw_windows; "
        "print(json.dumps([w.as_dict() for w in draw_windows([FaultSpec('pressure', randomise=True)], 3, 1150)]))"
    )
    here = [w.as_dict() for w in draw_windows([FaultSpec("pressure", randomise=True)], 3, 1150)]
    src = str(Path(__file__).parents[1] / "src")
    for hash_seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": src}
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
        assert json.loads(out.stdout) == here


def test_parallel_campaign_equals_serial():
    cfg = SimulationConfig(batch_length_h=30.0, **OFF)
    serial = scenarios.fault_campaign(0, 2, (Fault.AERATION,), seed=1, config=cfg, n_jobs=1, randomise=True)
    parallel = scenarios.fault_campaign(0, 2, (Fault.AERATION,), seed=1, config=cfg, n_jobs=2, randomise=True)
    assert serial.fault_windows.equals(parallel.fault_windows)
    assert serial.samples.equals(parallel.samples)


# ---------------------------------------------------------------- edge cases and validation


def test_window_after_the_end_never_acts():
    r = run(FaultSpec("aeration", onset_h=100.0, duration_h=4.0), 20.0)
    assert r["Fault_ref"].sum() == 0 and r.metadata["fault_windows"][0]["onset_h"] == 100.0
    cfg = SimulationConfig(batch_length_h=20.0, **OFF)
    camp = scenarios.fault_campaign(0, 1, (FaultSpec("aeration", onset_h=100.0),), config=cfg, n_jobs=1)
    assert math.isnan(camp.batches.fault_onset_h[0]) and math.isnan(camp.batches.fault_end_h[0])


def test_window_past_the_end_is_cut_off():
    r = run(FaultSpec("aeration", onset_h=18.0, duration_h=10.0, magnitude=5.0), 20.0)
    assert list(np.flatnonzero(r["Fault_ref"]) + 1) == list(range(90, 101))


def test_overlapping_windows_apply_in_order():
    specs = (FaultSpec("aeration", onset_h=10.0, duration_h=1.0, magnitude=20.0),
             FaultSpec("aeration", onset_h=10.4, duration_h=1.0, magnitude=0.5, effect="scale"))  # fmt: skip
    r = run(specs, 12.0)
    assert r["Fg"][49] == 20.0 and r["Fg"][52] == 10.0 and r["Fg"][56] == pytest.approx(r["Fg"][44] * 0.5)
    both = run((FaultSpec("aeration", onset_h=10.0, duration_h=1.0), FaultSpec("pressure", onset_h=10.0)), 12.0)
    assert both.config.fault == Fault.ALL and both["pressure"][49] == 2.0 and both["Fg"][49] == 20.0


def test_invalid_specs_are_rejected():
    with pytest.raises(ValueError):
        FaultSpec(Fault.ALL)
    with pytest.raises(ValueError):
        FaultSpec("aeration", magnitude=1.5, effect="scale")
    with pytest.raises(ValueError):
        FaultSpec("aeration", magnitude=-1.0)
    with pytest.raises(ValueError):
        FaultSpec("ph_sensor", effect="set")
    with pytest.raises(ValueError, match="needs a magnitude"):
        FaultSpec("aeration", effect="scale")
    with pytest.raises(ValueError):
        FaultSpec("aeration", onset_h=0.0)
    with pytest.raises(ValueError):
        FaultSpec("aeration", duration_h=math.inf, shape="ramp")
    with pytest.raises(ValueError, match="unknown fault"):
        FaultSpec("blower")
    with pytest.raises(ValueError):
        SimulationConfig(fault=Fault.PRESSURE, fault_specs=FaultSpec("aeration"))
    with pytest.raises(ValueError):
        SimulationConfig(fault_specs=(FaultSpec("aeration"), FaultSpec("ph_sensor")))
    with pytest.raises(ValueError, match="faults="):
        scenarios.fault_campaign(config=SimulationConfig(fault_specs=FaultSpec("aeration")))


def test_unpicklable_shape_is_caught_before_the_workers_start():
    spec = FaultSpec("aeration", onset_h=10.0, duration_h=2.0, magnitude=5.0, shape=lambda tau: tau)
    with pytest.raises(ValueError, match="picklable"):
        scenarios.fault_campaign(0, 2, (spec,), config=SimulationConfig(batch_length_h=12.0, **OFF), n_jobs=2)
