"""Gymnasium environment: control an IndPenSim batch (the ``gym`` extra, or ``pip install gymnasium``).

    import gymnasium as gym

    env = gym.make("penicillium.envs:IndPenSim-v0")  # importing the module registers the environments
    obs, info = env.reset(seed=0)
    obs, reward, terminated, truncated, info = env.step(env.action_space.sample())

One episode is one batch (230 h, 1150 steps of 12 minutes by default). At every step the agent adjusts the recipe
inputs, the pH and temperature PID loops act as in IndPenSim, and the reward is the penicillin harvested during
the step (kg), minus optional input costs.

Actions (``action_mode``):

* ``"recipe_relative"`` (default): ``a`` in ``[-1, 1]`` per controlled input; the input is the recipe value times
  ``1 + max_relative_change * a``. ``a = 0`` everywhere reproduces the recipe-driven batch exactly.
* ``"absolute"``: ``a`` is the input value itself, within ``INPUT_BOUNDS``.

Observations are what a plant measures online (``OBSERVATIONS``), optionally the last off-line lab results
(``lab_measurements=True``, values from the latest analysis, which arrives 4 samples after sampling), or the full
33-dimensional model state (``observation="state"``) for model-based methods.

Environments registered on import: ``IndPenSim-v0`` (nominal), ``IndPenSimFault-v0`` (a random IndPenSim fault
per episode, with ``info["fault"]``), and ``IndPenSimRaman-v0`` (observation adds the Raman spectrum).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, ClassVar

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as exc:  # pragma: no cover - exercised without the extra
    raise ImportError("penicillium.envs needs gymnasium: pip install gymnasium") from exc

from .constants import STEP_IN_HOURS
from .model import STATE_NAMES
from .raman import N_WAVENUMBERS
from .recipe import INPUTS, Recipe
from .result import LAB_CHANNELS
from .simulator import SINGLE_FAULTS, Fault, RamanMode, SimulationConfig, Simulator, _initial_state
from .solvers import SolverError

#: Online measurements in the default observation, in order (after the batch time in hours).
OBSERVATIONS: tuple[str, ...] = (
    "T", "pH", "DO2", "O2", "CO2outgas", "OUR", "CER", "V", "Wt", "Fa", "Fb", "Fc", "Fh",
)  # fmt: skip

#: Off-line lab measurements added with ``lab_measurements=True`` (latest available value).
LAB_MEASUREMENTS: tuple[str, ...] = LAB_CHANNELS

#: Physical bounds of the recipe inputs (``action_mode="absolute"`` and clipping in relative mode).
INPUT_BOUNDS: dict[str, tuple[float, float]] = {
    "Fs": (0.0, 300.0), "Foil": (0.0, 60.0), "Fg": (10.0, 120.0), "pressure": (0.3, 2.0), "discharge": (0.0, 5000.0),
    "Fw": (0.0, 1000.0), "Fpaa": (0.0, 30.0),
}  # fmt: skip

#: Inputs the agent controls by default. The broth discharge (harvest) stays on the recipe.
DEFAULT_CONTROLLED: tuple[str, ...] = ("Fs", "Foil", "Fg", "pressure", "Fw", "Fpaa")


class IndPenSimEnv(gym.Env):
    """IndPenSim fed-batch penicillin fermentation as a Gymnasium environment. See the module docstring.

    Args:
        config: simulation settings (fault, disturbances, batch length...). Default: IndPenSim defaults with
            Raman off (faster; use ``raman=True`` to observe spectra).
        recipe: reference recipe (default: IndPenSim's).
        controlled: recipe inputs the agent sets; the others follow the recipe.
        action_mode: ``"recipe_relative"`` or ``"absolute"``.
        max_relative_change: largest relative change per input in ``recipe_relative`` mode.
        observation: ``"measurements"`` (online measurements) or ``"state"`` (the 33 model states).
        lab_measurements: add the latest off-line lab results to the observation.
        raman: observe the Raman spectrum too (observation becomes a ``Dict`` with ``"measurements"`` and
            ``"raman"``).
        input_costs: cost per unit of input per hour, in kg of penicillin, e.g. ``{"Fs": 1e-4}``.
        random_faults: draw one of IndPenSim's faults (or none, with probability ``1 / 8``) at every reset.
        solver_failure_reward: reward of a step whose integration fails (the episode then terminates).
    """

    metadata: ClassVar[dict[str, Any]] = {"render_modes": ["ansi"]}

    def __init__(
        self,
        config: SimulationConfig | None = None,
        recipe: Recipe | None = None,
        controlled: Sequence[str] = DEFAULT_CONTROLLED,
        action_mode: str = "recipe_relative",
        max_relative_change: float = 0.5,
        observation: str = "measurements",
        lab_measurements: bool = False,
        raman: bool = False,
        input_costs: dict[str, float] | None = None,
        random_faults: bool = False,
        solver_failure_reward: float = -100.0,
        render_mode: str | None = None,
    ):
        unknown = set(controlled) - set(INPUTS)
        if unknown:
            raise ValueError(f"unknown inputs {sorted(unknown)}; choose from {INPUTS}")
        if action_mode not in ("recipe_relative", "absolute"):
            raise ValueError("action_mode must be 'recipe_relative' or 'absolute'")
        if observation not in ("measurements", "state"):
            raise ValueError("observation must be 'measurements' or 'state'")
        if render_mode is not None and render_mode not in self.metadata["render_modes"]:
            raise ValueError(f"render_mode must be one of {self.metadata['render_modes']}")
        base = config if config is not None else SimulationConfig(raman_mode=RamanMode.OFF)
        if raman and base.raman_mode == RamanMode.OFF:
            base = replace(base, raman_mode=RamanMode.RECORD)
        self.base_config = base
        self.recipe = recipe if recipe is not None else Recipe.default()
        self.controlled = tuple(controlled)
        self.action_mode = action_mode
        self.max_relative_change = float(max_relative_change)
        self.observation_mode = observation
        self.lab_measurements = lab_measurements
        self.raman = raman
        self.input_costs = dict(input_costs or {})
        self.random_faults = random_faults
        self.solver_failure_reward = float(solver_failure_reward)
        self.render_mode = render_mode

        n = len(self.controlled)
        if action_mode == "recipe_relative":
            self.action_space = spaces.Box(-1.0, 1.0, shape=(n,), dtype=np.float32)
        else:
            low = np.array([INPUT_BOUNDS[c][0] for c in self.controlled], dtype=np.float32)
            high = np.array([INPUT_BOUNDS[c][1] for c in self.controlled], dtype=np.float32)
            self.action_space = spaces.Box(low, high, dtype=np.float32)
        if observation == "state":
            self.observation_names = ("time_h", *STATE_NAMES)
        else:
            self.observation_names = ("time_h", *OBSERVATIONS, *(LAB_MEASUREMENTS if lab_measurements else ()))
        measurements = spaces.Box(-np.inf, np.inf, shape=(len(self.observation_names),), dtype=np.float64)
        if raman:
            spectrum = spaces.Box(-np.inf, np.inf, shape=(N_WAVENUMBERS,), dtype=np.float64)
            self.observation_space = spaces.Dict({"measurements": measurements, "raman": spectrum})
        else:
            self.observation_space = measurements
        self.sim: Simulator | None = None
        self._lab = np.zeros(len(LAB_MEASUREMENTS))  # latest reported lab values (NaN until the first report)
        self._last_inputs: dict[str, float] = {}

    # ------------------------------------------------------------------ Gymnasium API

    def reset(self, *, seed: int | None = None, options: dict[str, Any] | None = None):
        """Start a batch. The batch (initial state, parameters, disturbances) is drawn from ``self.np_random``.

        ``options``: ``{"batch_seed": int}`` picks the batch directly, ``{"fault": Fault}`` sets the fault.
        """
        super().reset(seed=seed)
        options = options or {}
        batch_seed = int(options.get("batch_seed", self.np_random.integers(0, 2**31 - 1)))
        fault = options.get("fault")
        if fault is None:
            if self.random_faults:  # one of the 7 single faults, or none (index 7), with equal probability
                i = int(self.np_random.integers(0, len(SINGLE_FAULTS) + 1))
                fault = Fault.NONE if i == len(SINGLE_FAULTS) else SINGLE_FAULTS[i]
            else:
                fault = self.base_config.fault
        self.sim = Simulator(recipe=self.recipe, config=replace(self.base_config, fault=Fault(fault)))
        self.sim.reset(seed=batch_seed, rng=np.random.default_rng(batch_seed))
        self._lab = np.full(len(LAB_MEASUREMENTS), np.nan)
        self._last_inputs = self.sim.recipe_inputs(1)
        return self._obs(), self._info(batch_seed=batch_seed)

    def step(self, action):
        if self.sim is None:
            raise RuntimeError("call reset() before step()")
        sim = self.sim
        inputs = self.inputs_for(action)
        try:
            _, harvested = sim.step(**inputs)
        except SolverError as exc:
            return self._obs(), self.solver_failure_reward, True, False, self._info(error=str(exc))
        self._last_inputs = inputs
        cost = sum(c * abs(inputs[name]) * STEP_IN_HOURS for name, c in self.input_costs.items())
        reward = float(harvested - cost)
        for j, name in enumerate(LAB_MEASUREMENTS):  # keep the latest reported lab value of each analysis
            value = sim._data[name][sim.k - 1]
            if not math.isnan(value):
                self._lab[j] = value
        return self._obs(), reward, sim.done, False, self._info(harvested_kg=float(harvested), cost=cost)

    def render(self):
        if self.render_mode == "ansi" and self.sim is not None:
            d, i = self.sim._data, max(self.sim.k - 1, 0)
            return (
                f"t={self.sim.time:6.1f} h  P={d['P'][i]:6.2f} g/L  X={d['X'][i]:6.2f} g/L  V={d['V'][i]:8.0f} L  "
                f"T={d['T'][i]:6.2f} K  yield={self.sim._total_yield:8.1f} kg"
            )
        return None

    # ------------------------------------------------------------------ helpers

    def inputs_for(self, action) -> dict[str, float]:
        """The recipe inputs that ``action`` sets for the next step."""
        inputs = self.sim.recipe_inputs()
        a = np.asarray(action, dtype=float).reshape(-1)
        if a.shape != (len(self.controlled),):
            raise ValueError(f"action must have shape ({len(self.controlled)},), got {a.shape}")
        for value, name in zip(a, self.controlled, strict=True):
            lo, hi = INPUT_BOUNDS[name]
            if self.action_mode == "recipe_relative":
                v = inputs[name] * (1 + self.max_relative_change * float(np.clip(value, -1, 1)))
            else:
                v = float(value)
            inputs[name] = float(np.clip(v, lo, hi))
        return inputs

    def recipe_action(self) -> np.ndarray:
        """The action that follows the recipe at the next step (zeros in relative mode)."""
        if self.action_mode == "recipe_relative":
            return np.zeros(len(self.controlled), dtype=np.float32)
        inputs = self.sim.recipe_inputs()
        return np.array([inputs[c] for c in self.controlled], dtype=np.float32)

    def _obs(self):
        """Observation after the last completed sample (before the first one: the initial state)."""
        sim = self.sim
        i = sim.k - 1
        d = sim._data
        if self.observation_mode == "state":
            if i < 0:
                values = [float(v) for v in _initial_state(sim._bp.x0)]
                values[6] = float(-math.log10(sim._bp.x0["pH"]))
            else:
                values = [d[name][i] for name in STATE_NAMES]
                values[6] = -math.log10(values[6])
            vec = np.array([sim.time, *values], dtype=np.float64)
        else:
            if i < 0:
                x0 = sim._bp.x0
                first = {"T": x0["T"], "pH": -math.log10(x0["pH"]), "DO2": x0["DO2"], "O2": x0["O2"],
                         "CO2outgas": x0["CO2outgas"], "V": x0["V"], "Wt": x0["Wt"]}  # fmt: skip
                values = [first.get(name, 0.0) for name in OBSERVATIONS]
            else:
                values = [d[name][i] for name in OBSERVATIONS]
                values[OBSERVATIONS.index("pH")] = -math.log10(d["pH"][i])
            lab = list(np.nan_to_num(self._lab, nan=0.0)) if self.lab_measurements else []
            vec = np.array([sim.time, *values, *lab], dtype=np.float64)
        if self.raman:
            spectrum = sim.latest_spectrum()
            raman = np.zeros(N_WAVENUMBERS) if spectrum is None else np.array(spectrum, dtype=np.float64)
            return {"measurements": vec, "raman": raman}
        return vec

    def _info(self, **extra) -> dict[str, Any]:
        sim = self.sim
        i = sim.k - 1
        info = {
            "time_h": sim.time,
            "fault": sim.config.fault.name,
            "fault_active": bool(sim._data["Fault_ref"][i]) if i >= 0 else False,
            "total_yield_kg": sim._total_yield,
            "penicillin_g_per_L": float(sim._data["P"][i]) if i >= 0 else 0.0,
        }
        info.update(extra)
        return info


def collect_minari_dataset(
    dataset_id: str,
    n_episodes: int,
    policy=None,
    env_kwargs: dict[str, Any] | None = None,
    seed: int = 0,
    **dataset_kwargs,
):
    """Roll out ``policy`` for ``n_episodes`` and save them as a Minari dataset (the ``minari`` extra).

    ``policy(obs, env) -> action``; the default follows the recipe (zero action) with Gaussian exploration noise
    of standard deviation 0.1 in ``recipe_relative`` mode, which gives a "behaviour" dataset for offline RL.
    Extra keyword arguments go to ``DataCollector.create_dataset`` (``algorithm_name``, ``author``...).
    """
    from minari import DataCollector

    env = DataCollector(gym.make("penicillium.envs:IndPenSim-v0", **dict(env_kwargs or {})))
    rng = np.random.default_rng(seed)
    base = env.unwrapped

    def default_policy(obs, env_):
        a = base.recipe_action()
        if base.action_mode == "recipe_relative":
            a = np.clip(a + rng.normal(0.0, 0.1, size=a.shape), -1, 1).astype(np.float32)
        return a

    policy = policy or default_policy
    for episode in range(n_episodes):
        obs, _ = env.reset(seed=seed + episode)
        done = False
        while not done:
            obs, _, terminated, truncated, _ = env.step(policy(obs, env))
            done = terminated or truncated
    dataset_kwargs.setdefault("algorithm_name", "IndPenSim recipe + Gaussian noise (sd 0.1)")
    dataset_kwargs.setdefault(
        "description",
        "IndPenSim fed-batch penicillin fermentation (Penicillium): one episode per batch, reward = penicillin "
        "harvested per 12-minute step [kg].",
    )
    dataset_kwargs.setdefault("code_permalink", "https://github.com/francesco-sartori/Penicillium")
    dataset_kwargs.setdefault("author", "penicillium")
    dataset_kwargs.setdefault("author_email", "unknown@example.com")
    dataset = env.create_dataset(dataset_id=dataset_id, **dataset_kwargs)
    env.close()
    return dataset


def register_envs() -> None:
    """Register the environments with Gymnasium (done on import)."""
    specs = {
        "IndPenSim-v0": {},
        "IndPenSimFault-v0": {"random_faults": True},
        "IndPenSimRaman-v0": {"raman": True},
    }
    for env_id, kwargs in specs.items():
        if env_id not in gym.registry:
            gym.register(id=env_id, entry_point="penicillium.envs:IndPenSimEnv", kwargs=kwargs)


register_envs()
