import numpy as np
import pytest

gym = pytest.importorskip("gymnasium")

from gymnasium.utils.env_checker import check_env  # noqa: E402

from penicillium import RamanMode, SimulationConfig, Simulator  # noqa: E402
from penicillium.envs import IndPenSimEnv  # noqa: E402


def _rollout(env, n, seed, action=None):
    obs, info = env.reset(seed=seed)
    observations, rewards = [obs], []
    for _ in range(n):
        a = env.unwrapped.recipe_action() if action is None else action
        obs, r, _terminated, _truncated, info = env.step(a)
        observations.append(obs)
        rewards.append(r)
    return np.array(observations), np.array(rewards), info


def test_check_env_passes():
    check_env(
        IndPenSimEnv(config=SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=4.0)), skip_render_check=True
    )


def test_check_env_state_observation_and_absolute_actions():
    env = IndPenSimEnv(
        config=SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=4.0),
        observation="state",
        action_mode="absolute",
        lab_measurements=True,
    )
    check_env(env, skip_render_check=True)
    obs, _ = env.reset(seed=0)
    assert obs.shape == (34,)


def test_make_by_id_and_seeding_is_deterministic():
    env = gym.make(
        "penicillium.envs:IndPenSim-v0", config=SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=6.0)
    )
    a = _rollout(env, 20, seed=3)
    b = _rollout(env, 20, seed=3)
    c = _rollout(env, 20, seed=4)
    np.testing.assert_array_equal(a[0], b[0])
    np.testing.assert_array_equal(a[1], b[1])
    assert not np.array_equal(a[0], c[0])


def test_zero_action_reproduces_the_recipe_batch():
    cfg = SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=8.0)
    env = IndPenSimEnv(config=cfg)
    _, info = env.reset(options={"batch_seed": 11})
    rewards = []
    while True:
        _, r, terminated, truncated, info = env.step(np.zeros(env.action_space.shape, np.float32))
        rewards.append(r)
        if terminated or truncated:
            break
    ref = Simulator(config=cfg).run(seed=11, rng=np.random.default_rng(11))
    assert len(rewards) == 40
    assert info["total_yield_kg"] == pytest.approx(ref.total_yield, rel=1e-12)
    np.testing.assert_allclose(env.unwrapped.sim.result()["P"], ref["P"], rtol=1e-12)


def test_actions_change_inputs_and_are_clipped():
    env = IndPenSimEnv(config=SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=4.0), controlled=("Fs",))
    env.reset(seed=0)
    recipe_fs = env.sim.recipe_inputs()["Fs"]
    assert env.inputs_for([1.0])["Fs"] == pytest.approx(recipe_fs * 1.5)
    assert env.inputs_for([5.0])["Fs"] == pytest.approx(recipe_fs * 1.5)  # clipped to [-1, 1]
    with pytest.raises(ValueError, match="shape"):
        env.inputs_for([0.0, 0.0])


def test_fault_env_reports_fault_and_raman_env_observes_spectra():
    env = gym.make("penicillium.envs:IndPenSimFault-v0", config=SimulationConfig(raman_mode=RamanMode.OFF))
    faults = {env.reset(seed=s)[1]["fault"] for s in range(12)}
    assert len(faults) > 2
    env = gym.make("penicillium.envs:IndPenSimRaman-v0", config=SimulationConfig(batch_length_h=4.0))
    obs, _ = env.reset(seed=0)
    for _ in range(12):
        obs, *_ = env.step(np.zeros(env.action_space.shape, np.float32))
    assert obs["raman"].shape == (2200,) and obs["raman"].max() > 0


@pytest.mark.slow
def test_minari_dataset(tmp_path, monkeypatch):
    pytest.importorskip("minari")
    monkeypatch.setenv("MINARI_DATASETS_PATH", str(tmp_path))
    from penicillium.envs import collect_minari_dataset

    ds = collect_minari_dataset(
        "penicillium/indpensim-short-v0",
        n_episodes=2,
        env_kwargs={"config": SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=10.0)},
    )
    assert ds.total_episodes == 2
    assert ds.total_steps == 100


def test_control_benchmark_compares_policies_on_identical_batches():
    from penicillium import scenarios

    kwargs = {"config": SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=6.0)}
    base = scenarios.control_benchmark(n_batches=2, env_kwargs=kwargs)
    again = scenarios.control_benchmark(n_batches=2, env_kwargs=kwargs)
    more_sugar = scenarios.control_benchmark(
        policy=lambda obs, env: np.full(env.action_space.shape, 0.5, np.float32), n_batches=2, env_kwargs=kwargs
    )
    assert list(base["yield_kg"]) == list(again["yield_kg"])
    assert list(base["steps"]) == [30, 30] and not base["failed"].any()
    assert list(more_sugar["yield_kg"]) != list(base["yield_kg"])
