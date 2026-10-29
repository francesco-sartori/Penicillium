import numpy as np
import pytest

from penicillium import CHANNELS, Fault, RamanMode, SimulationConfig, Simulator
from penicillium.constants import NUM_STEPS


def _run(sim, n, seed=1, rng=None):
    sim.reset(seed, rng)
    for _ in range(n):
        sim.step(**sim.recipe_inputs())
    return sim.result()


def test_step_requires_reset():
    with pytest.raises(RuntimeError, match="reset"):
        Simulator().step(**Simulator().recipe_inputs(1))


def test_unknown_solver_and_backend():
    with pytest.raises(ValueError, match="solver"):
        Simulator(solver="euler")
    with pytest.raises(ValueError, match="backend"):
        Simulator(backend="fortran")


def test_numba_and_python_backends_agree():
    pytest.importorskip("numba")
    a = _run(Simulator(backend="numba"), 40, rng=np.random.default_rng(0))
    b = _run(Simulator(backend="python"), 40, rng=np.random.default_rng(0))
    # The math libraries differ in the last bit; usually that stays at ~1e-12, but it can flip one of LSODA's
    # adaptive step-size decisions, which moves the result by up to ~1e-7 (seed 1 does).
    for name in a.data:
        scale = np.nanmax(np.abs(b[name]), initial=0.0)
        np.testing.assert_allclose(a[name], b[name], rtol=1e-6, atol=1e-6 * scale + 1e-12, err_msg=name)


def test_observation_and_result_shapes():
    sim = Simulator()
    obs0 = sim.reset(seed=1)
    assert set(obs0) >= {"Fs", "T", "pH", "DO2"}
    obs, reward = sim.step(**sim.recipe_inputs())
    assert isinstance(reward, float)
    assert 6.0 < obs["pH"] < 7.0
    for _ in range(14):
        sim.step(**sim.recipe_inputs())
    res = sim.result()
    assert len(res) == 15 == sim.k
    assert set(res.data) == set(CHANNELS)
    np.testing.assert_allclose(res.time[-1], 3.0)
    df = res.to_pandas()
    assert df.shape == (15, len(CHANNELS))
    assert res.raman.shape == (15, 2200)
    assert np.all(res.raman[:10] == 0)  # spectra start after sample 10
    assert np.all(res.raman[10:] > 0)


def test_same_seed_same_batch_and_seeds_differ():
    a = _run(Simulator(), 20, seed=1)
    b = _run(Simulator(), 20, seed=1)
    c = _run(Simulator(), 20, seed=2)
    for name in ("V", "P", "T", "pH", "DO2"):
        np.testing.assert_array_equal(a[name], b[name])
    np.testing.assert_array_equal(a.raman, b.raman)
    assert not np.allclose(a["V"], c["V"])


def test_legacy_random_state_is_accepted():
    a = _run(Simulator(), 15, rng=np.random.RandomState(0))
    b = _run(Simulator(), 15, rng=np.random.RandomState(0))
    np.testing.assert_array_equal(a.raman, b.raman)


def test_raman_off_and_noise_off():
    res = _run(Simulator(config=SimulationConfig(raman_mode=RamanMode.OFF)), 12)
    assert res.raman is None
    with pytest.raises(ValueError):
        res.raman_to_pandas()
    a = _run(Simulator(config=SimulationConfig(raman_noise=False)), 12, rng=np.random.default_rng(1))
    b = _run(Simulator(config=SimulationConfig(raman_noise=False)), 12, rng=np.random.default_rng(2))
    np.testing.assert_array_equal(a.raman, b.raman)


def test_aeration_fault_overrides_input_and_flags_it():
    sim = Simulator(config=SimulationConfig(fault=Fault.AERATION))
    res = _run(sim, 105)
    assert np.all(res["Fault_ref"][:99] == 0)
    assert np.all(res["Fault_ref"][99:105] == 1)
    assert np.all(res["Fg"][99:105] == 20)


def test_sensor_fault_flagged_for_whole_batch():
    res = _run(Simulator(config=SimulationConfig(fault=Fault.PH_SENSOR)), 5)
    assert np.all(res["Fault_ref"] == 1)


def test_disturbances_change_the_batch():
    a = _run(Simulator(config=SimulationConfig(disturbances=True)), 30)
    b = _run(Simulator(config=SimulationConfig(disturbances=False)), 30)
    assert not np.allclose(a["T"], b["T"])


def test_offline_measurements_every_12_hours():
    res = _run(Simulator(config=SimulationConfig(raman_mode=RamanMode.OFF)), 61)
    sampled = np.flatnonzero(~np.isnan(res["P_offline"]))
    np.testing.assert_array_equal(sampled, [4, 59])  # 1 h and 12 h
    assert res["P_offline"][59] == res["P"][55]  # 4-sample delay


@pytest.mark.slow
def test_default_batch_is_physically_sane():
    # Guards IndPenSim's recipe lookup: with the "from" reading the default batch is a different one
    # (docs/quirks.md, 1.1).
    sim = Simulator(config=SimulationConfig(raman_mode=RamanMode.OFF))
    res = sim.run(seed=1)
    assert sim.done and len(res) == NUM_STEPS
    assert 296.5 < res["T"].min() and res["T"].max() < 300.5
    assert 6.3 < res["pH"].min() and res["pH"].max() < 6.7
    assert 55_000 < res["V"].min() and res["V"].max() < 100_000
    assert 25 < res["P"][-1] < 40  # g/L, IndPenSim reports ~30 g/L at harvest
    assert 3000 < res.total_yield < 4500
    with pytest.raises(RuntimeError, match="finished"):
        sim.step(**sim.recipe_inputs(NUM_STEPS))


@pytest.mark.slow
def test_prbs_perturbs_feeds():
    config = SimulationConfig(prbs=True, raman_mode=RamanMode.OFF)
    res = _run(Simulator(config=config), 900, rng=np.random.default_rng(3))
    # After sample 475 Fs is frozen; IndPenSim adds 0 or +-15 at samples 600, 700, 800.
    steps = np.round(np.diff(res["Fs"][475:900]), 9)
    assert set(np.unique(steps)) <= {-15.0, 0.0, 15.0}
    assert np.count_nonzero(steps) >= 1


def test_solver_failure_raises_and_keeps_completed_samples(monkeypatch):
    import penicillium.simulator as simulator
    from penicillium import SolverError
    from penicillium.solvers import integrate

    def overflowing_rhs(t, y, par):
        raise OverflowError("math range error")

    with pytest.raises(SolverError, match="model evaluation failed"):
        integrate(overflowing_rhs, [1.0], 0.0, 0.2, [])

    sim = Simulator(backend="python")
    sim.reset(seed=1)
    for _ in range(3):
        sim.step(**sim.recipe_inputs())
    monkeypatch.setattr(simulator, "rhs", overflowing_rhs)
    with pytest.raises(SolverError, match=r"sample 4 \(0\.6 h\)"):
        sim.step(**sim.recipe_inputs())
    assert sim.k == 3 and len(sim.result()) == 3


def test_odeint_failure_is_reported():
    from penicillium import SolverError
    from penicillium.solvers import integrate

    def stiff_blowup(t, y, par):
        return [y[0] ** 3]  # finite-time blow-up at t = 0.5

    with pytest.raises(SolverError):
        integrate(stiff_blowup, [1.0], 0.0, 1.0, [], method="lsoda", max_step=0.01)


@pytest.mark.slow
@pytest.mark.parametrize("fault", list(Fault))
def test_every_fault_runs_to_completion(fault):
    # Every fault batch runs to the end.
    res = Simulator(config=SimulationConfig(fault=fault, raman_noise=False)).run(seed=3)
    assert len(res) == NUM_STEPS
    assert res["V"].min() > 50_000
    assert res["Fault_ref"].any() == (fault != Fault.NONE)
    assert res.total_yield > 0  # substrate faults can cut the yield to ~700 kg without PAA control


def test_initial_conditions_can_be_overridden():
    from penicillium import INITIAL_CONDITIONS

    seeded = Simulator.initial_conditions(seed=1)
    assert set(seeded) == set(INITIAL_CONDITIONS)
    assert 6.0 < seeded["pH"] < 7.0 and 50_000 < seeded["V"] < 70_000

    sim = Simulator(config=SimulationConfig(raman_mode=RamanMode.OFF))
    sim.reset(seed=1, initial_conditions={"S": 5.0, "pH": 6.2, "X": 1.0, "mu_x_max": 0.3})
    sim.step(**sim.recipe_inputs())
    res = sim.result()
    used = res.metadata["initial_conditions"]
    assert used["S"] == 5.0 and used["mu_x_max"] == 0.3 and used["X"] == pytest.approx(1.0)
    assert used["V"] == seeded["V"]  # untouched values keep the seeded ones
    assert res["pH"][0] < 6.35  # started from 6.2 instead of ~6.5
    assert res["X"][0] > 0.9

    with pytest.raises(ValueError, match="unknown initial conditions"):
        Simulator().reset(seed=1, initial_conditions={"Temperature": 300})


def test_seeded_initial_conditions_unchanged_by_refactor():
    # Without overrides the batch must be identical to the plain seeded one.
    a = _run(Simulator(), 5)
    sim = Simulator()
    sim.reset(seed=1, initial_conditions={})
    for _ in range(5):
        sim.step(**sim.recipe_inputs())
    np.testing.assert_array_equal(a["P"], sim.result()["P"])


def test_raman_mode_defaults():
    assert SimulationConfig().raman_mode == RamanMode.RECORD  # IndPenSim campaigns: no PAA control


def test_batch_length():
    assert SimulationConfig(batch_length_h=317).n_steps == 1585
    for bad in (0, 351, 230.1):
        with pytest.raises(ValueError, match="batch_length_h"):
            SimulationConfig(batch_length_h=bad)
    sim = Simulator(config=SimulationConfig(batch_length_h=3))
    res = sim.run(seed=1)
    assert sim.done and len(res) == 15
    np.testing.assert_allclose(res.time[-1], 3.0)
    # A shorter batch is the start of the longer one.
    long = _run(Simulator(), 15)
    np.testing.assert_array_equal(res["P"], long["P"])


def test_prbs_does_not_depend_on_raman_recording():
    def fs(mode):
        return _run(Simulator(config=SimulationConfig(prbs=True, raman_mode=mode)), 20)["Fs"]

    np.testing.assert_array_equal(fs(RamanMode.OFF), fs(RamanMode.RECORD))


@pytest.mark.slow
def test_long_batch_follows_the_indpensim_recipe_beyond_230h():
    res = Simulator(config=SimulationConfig(batch_length_h=320, raman_mode=RamanMode.OFF)).run(seed=1)
    assert len(res) == 1600
    t = res.time
    # Discharge pulses continue at 230-232, 250-252 and 270-272 h; aeration drops to 60 after 250 h.
    assert np.all(res["discharge"][(t > 230.1) & (t <= 232)] == -4000)
    assert np.all(res["discharge"][(t > 272.1)] == 0)
    assert np.all(res["Fg"][t > 250.1] == 60)
    assert res["V"].min() > 50_000


def test_simulate_batches_matches_single_runs():
    from penicillium import BatchSpec, simulate_batches

    config = SimulationConfig(batch_length_h=2, raman_mode=RamanMode.OFF)
    specs = [BatchSpec(seed=s, config=config) for s in (1, 2, 3)]
    seen = []
    parallel = simulate_batches(specs, n_jobs=2, progress=lambda i, n, r: seen.append((i, n)))
    serial = simulate_batches(specs, n_jobs=1)
    assert seen == [(1, 3), (2, 3), (3, 3)]
    for a, b, spec in zip(parallel, serial, specs, strict=True):
        assert a.seed == spec.seed
        np.testing.assert_array_equal(a["P"], b["P"])


def test_latest_spectrum():
    sim = Simulator()
    sim.reset(seed=1)
    for _ in range(10):
        sim.step(**sim.recipe_inputs())
    assert sim.latest_spectrum() is None  # spectra start after sample 10
    sim.step(**sim.recipe_inputs())
    np.testing.assert_array_equal(sim.latest_spectrum(), sim.result().raman[-1])
    off = Simulator(config=SimulationConfig(raman_mode=RamanMode.OFF))
    off.reset(seed=1)
    off.step(**off.recipe_inputs())
    assert off.latest_spectrum() is None
