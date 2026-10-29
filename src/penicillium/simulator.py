"""Batch simulator: control strategy, disturbances, faults and the sample-by-sample integration loop.

Follows the MATLAB IndPenSim V2.01 source (``indpensim_run.m``, ``indpensim.m``, ``fctrl_indpensim.m``;
BSD-3-Clause, Copyright (c) 2016, Stephen Goldrick; see LICENSE). Where its code admits more than one reading, the
choice is listed in ``docs/quirks.md``.

Reading order: ``SimulationConfig`` (the switches), ``BatchParameters`` (everything random about a batch), then
``Simulator.step`` -> ``_step`` (one 12-minute sample) -> ``_control`` (the discrete-time logic of IndPenSim).
"""

from __future__ import annotations

import enum
import functools
import math
from dataclasses import dataclass

import numpy as np
from scipy.interpolate import interp1d

from . import _numba, raman
from .constants import BATCH_LENGTH_IN_HOURS, MINUTES_PER_HOUR, NUM_STEPS, STEP_IN_HOURS, STEP_IN_MINUTES
from .model import STATE_NAMES, rhs
from .recipe import Recipe
from .result import CHANNEL_NAMES, BatchResult
from .rng import RNG, randint
from .solvers import SOLVERS, SolverError, integrate

#: Longest supported batch: IndPenSim's recipe tables and sensor-fault ramps end at sample 1750.
MAX_BATCH_LENGTH_H = 350.0


class Fault(enum.IntEnum):
    """Process faults of IndPenSim. Values match the IndPenSim ``Faults`` flag."""

    NONE = 0
    AERATION = 1  #: aeration rate drops to 20 (samples 100-120 and 500-550)
    PRESSURE = 2  #: back pressure rises to 2 bar (samples 500-520 and 1000-1200)
    SUBSTRATE_FEED = 3  #: sugar feed rate fault (samples 100-150, 380-460, 1000-1070)
    BASE_FLOW = 4  #: base flow rate fault (samples 400-420 and 700-800)
    COOLANT_FLOW = 5  #: coolant flow rate fault (samples 350-450 and 1200-1350)
    ALL = 6  #: faults 1-5 together
    TEMPERATURE_SENSOR = 7  #: temperature sensor drift, ramping to +0.4 K from sample 200 to 800
    PH_SENSOR = 8  #: pH sensor drift, ramping to +0.1 from sample 200 to 800


#: Every fault except ``ALL`` (all at once): the faults campaigns cycle through and random-fault episodes draw from.
SINGLE_FAULTS: tuple[Fault, ...] = (
    Fault.AERATION, Fault.PRESSURE, Fault.SUBSTRATE_FEED, Fault.BASE_FLOW, Fault.COOLANT_FLOW,
    Fault.TEMPERATURE_SENSOR, Fault.PH_SENSOR,
)  # fmt: skip

#: Process faults as in ``fctrl_indpensim.m``: fault -> (input, value forced on it, first sample, last sample).
_FAULT_PROFILES: dict[Fault, tuple[tuple[str, int, int, int], ...]] = {
    Fault.AERATION: (("Fg", 20, 100, 120), ("Fg", 20, 500, 550)),
    Fault.PRESSURE: (("pressure", 2, 500, 520), ("pressure", 2, 1000, 1200)),
    Fault.SUBSTRATE_FEED: (("Fs", 2, 100, 150), ("Fs", 20, 380, 460), ("Fs", 20, 1000, 1070)),
    Fault.BASE_FLOW: (("Fb", 5, 400, 420), ("Fb", 10, 700, 800)),
    Fault.COOLANT_FLOW: (("Fc", 2, 350, 450), ("Fc", 10, 1200, 1350)),
}


class RamanMode(enum.IntEnum):
    """IndPenSim ``Raman_spec`` flag.

    Note that this changes the process, not only the outputs: in ``PAT_CONTROL`` a PID loop feeds PAA to a
    1200 mg/L setpoint from 10 h on; otherwise the recipe's PAA feed is used.
    """

    OFF = 0  #: no spectra
    RECORD = 1  #: spectra recorded (Penicillium's default)
    PAT_CONTROL = 2  #: spectra recorded and PAA fed by a PID controller (IndPenSim's default flag)


@dataclass(frozen=True)
class SimulationConfig:
    """Simulation switches. Defaults are the IndPenSim defaults.

    Attributes:
        fault: process fault to inject.
        disturbances: filtered random disturbances on kinetics, feed concentrations, coolant inlet
            temperature and inlet O2 (IndPenSim ``Dis`` flag).
        raman_mode: whether Raman spectra are simulated and whether PAA is under PAT control. Default
            ``RECORD`` (spectra recorded, PAA fed by the recipe, as in the IndPenSim campaigns).
        raman_noise: random baseline noise on the spectra.
        prbs: pseudo-random binary perturbations on sugar and PAA feed after sample 500 (``PRBS``).
        inhibition: IndPenSim ``Inhib`` flag: 0 no inhibition terms, 1 DO2 and pH inhibition only, 2 (default)
            DO2, temperature, pH, dissolved CO2, PAA and nitrogen. With 1 or 2 the maximum biomass growth rate is
            also reset after a sustained decline in growth.
        viscosity_from_input: use a fixed viscosity instead of the simulated one (``Vis`` flag).
        temperature_setpoint: temperature setpoint [K].
        ph_setpoint: pH setpoint.
        offline_interval_h: interval of offline measurements [h].
        offline_delay_steps: delay of offline measurements [samples].
        batch_length_h: batch duration [h], a multiple of 0.2 h up to 350 h (IndPenSim: 230 h fixed, or
            variable with downstream delays).
        quirks: ``"matlab"`` (default) follows IndPenSim's controller code so batches match MATLAB: the pH
            controller's previous error does not include the setpoint, and the heating PID starts from the
            previous *cooling* flow. ``"fixed"`` uses the alternative reading of both. See docs/quirks.md,
            section 4.
    """

    fault: Fault = Fault.NONE
    disturbances: bool = True
    raman_mode: RamanMode = RamanMode.RECORD
    raman_noise: bool = True
    prbs: bool = False
    inhibition: int = 2
    viscosity_from_input: bool = False
    temperature_setpoint: float = 298.0
    ph_setpoint: float = 6.5
    offline_interval_h: float = 12.0
    offline_delay_steps: int = 4
    batch_length_h: float = float(BATCH_LENGTH_IN_HOURS)
    quirks: str = "matlab"

    def __post_init__(self) -> None:
        if self.quirks not in ("matlab", "fixed"):
            raise ValueError(f"quirks must be 'matlab' or 'fixed', got {self.quirks!r}")
        if self.inhibition not in (0, 1, 2):
            raise ValueError(f"inhibition must be 0, 1 or 2, got {self.inhibition!r}")
        n = self.batch_length_h / STEP_IN_HOURS
        if not (0 < self.batch_length_h <= MAX_BATCH_LENGTH_H) or abs(n - round(n)) > 1e-9:
            raise ValueError(
                f"batch_length_h must be a multiple of {STEP_IN_HOURS} h in (0, {MAX_BATCH_LENGTH_H}], "
                f"got {self.batch_length_h}"
            )

    @property
    def n_steps(self) -> int:
        """Number of 12-minute samples in the batch."""
        return round(self.batch_length_h / STEP_IN_HOURS)


#: Initial conditions and batch parameters that can be overridden: name -> (description, unit).
INITIAL_CONDITIONS: dict[str, tuple[str, str]] = {
    "S": ("Substrate concentration", "g/L"),
    "DO2": ("Dissolved oxygen concentration", "mg/L"),
    "X": ("Biomass concentration (1/3 growing, 2/3 non-growing regions)", "g/L"),
    "V": ("Volume", "L"),
    "Wt": ("Vessel weight", "kg"),
    "pH": ("pH", "-"),
    "T": ("Temperature", "K"),
    "O2": ("O2 fraction in off-gas", "-"),
    "CO2outgas": ("CO2 in off-gas", "%"),
    "PAA": ("Phenylacetic acid concentration", "mg/L"),
    "NH3": ("Nitrogen concentration", "mg/L"),
    "mu_x_max": ("Maximum specific growth rate of biomass", "1/h"),
    "mu_p_max": ("Maximum specific production rate of penicillin", "1/h"),
    "alpha_kla": ("kLa constant", "-"),
    "PAA_c": ("PAA concentration in the PAA feed", "mg/L"),
    "N_conc_paa": ("Nitrogen concentration in the PAA feed", "mg/L"),
}

#: The five kinetic parameters of a batch, in the order of ``BatchParameters.params`` (model ``par[0:5]``).
_PARAMS: tuple[str, ...] = ("mu_p_max", "mu_x_max", "alpha_kla", "N_conc_paa", "PAA_c")

#: Names of the eight disturbance sequences, in IndPenSim's order (model ``par[22:30]``).
DISTURBANCES: tuple[str, ...] = (
    "distMuP", "distMuX", "distcs", "distcoil", "distabc", "distPAA", "distTcin", "distO_2in",
)  # fmt: skip

#: Standard deviations of the white noise behind each disturbance, before the low-pass filter (indpensim_run.m).
_DISTURBANCE_SCALES: dict[str, float] = {
    "distMuP": 0.03, "distMuX": 0.25, "distcs": 1500, "distcoil": 300, "distabc": 0.2, "distPAA": 300000,
    "distTcin": 100, "distO_2in": 0.02,
}  # fmt: skip

#: Random draws of a batch (indpensim_run.m): name -> (mean, standard deviation). ``X`` is drawn around the
#: batch's base biomass level (``None``), itself 0.5 +- 0.05.
_DRAWS: dict[str, tuple[float | None, float]] = {
    "mux": (0.41, 0.025), "mup": (0.041, 0.0025), "S": (1, 0.1), "DO2": (15, 0.5), "X": (None, 0.1),
    "V": (5.800e04, 500), "Wt": (6.2e04, 500), "CO2outgas": (0.038, 0.001), "O2": (0.20, 0.05),
    "pH": (6.5, 0.1), "T": (297, 0.5), "PAA": (1400, 50), "NH3": (1700, 50),
    "alpha_kla": (85, 10), "PAA_c": (530000, 20000), "N_conc_paa": (150000, 2000),
}  # fmt: skip

#: Named random streams of a batch. The order is fixed: changing it would change every seeded batch.
_RANDOM_NAMES: tuple[str, ...] = ("X_base", *_DRAWS, *DISTURBANCES)

#: Keys of ``BatchParameters.x0``, in IndPenSim's order (``x0`` structure of indpensim_run.m).
_X0_NAMES: tuple[str, ...] = (
    "mux", "mup", "S", "DO2", "X", "P", "V", "Wt", "CO2outgas", "O2", "pH", "T", "a0", "a1", "a3", "a4",
    "Culture_age", "PAA", "NH3",
)  # fmt: skip

#: Channels returned by ``reset`` and ``step``.
OBSERVATION_CHANNELS: tuple[str, ...] = (
    "Foil", "Fw", "Fs", "Fa", "Fb", "Fc", "Fh", "Fg", "Wt", "discharge", "DO2", "T", "O2", "pressure",
)  # fmt: skip


def pid_controller(uk1, ek, ek1, yk, yk1, yk2, u_min, u_max, Kp, Ti, Td, h):
    """Velocity-form PID with derivative on measurement and output saturation (``PIDSimple3.m`` of IndPenSim).

    ``u_k = u_{k-1} + Kp [(e_k - e_{k-1}) + e_k h / Ti - (Td / h)(y_k - 2 y_{k-1} + y_{k-2})]``, clipped to
    ``[u_min, u_max]``; the I term is off for ``Ti <= 1e-7`` and the D term for ``Td <= 0.001``.
    """
    P = ek - ek1
    I = ek * h / Ti if Ti > 1e-7 else 0
    D = -Td / h * (yk - 2 * yk1 + yk2) if Td > 0.001 else 0
    uu = uk1 + Kp * (P + I + D)
    uu = u_max if uu > u_max else uu
    uu = u_min if uu < u_min else uu
    return uu


def off_gas_rates(Fg, O2, CO2outgas):
    """Oxygen uptake rate [g/min] and carbon evolution rate [g/h] from aeration and off-gas (``indpensim.m``).

    Works on scalars and arrays, so measured (noisy) off-gas gives consistently measured rates.
    """
    O2_in = 0.204
    OUR = (1.4285714285714286 * Fg) * (O2_in - O2 * (0.7902 / (1 - O2 - CO2outgas / 100)))
    CER = (1.9642857142857144 * Fg) * ((0.0065 * CO2outgas) * (0.7902 / (1 - O2_in - CO2outgas / 100) - 0.0330))
    return OUR, CER


@functools.cache
def _drift_ramp(magnitude: float) -> np.ndarray:
    # Built like IndPenSim (linear interpolation evaluated at samples 1..1750).
    points = np.array([[0, 0], [200, 0], [800, magnitude], [1750, magnitude]])
    return interp1d(points[:, 0], points[:, 1], kind="linear", fill_value="extrapolate")(np.arange(1, 1751))


def _sensor_drift(k: int, magnitude: float) -> float:
    """Sensor-fault offset at sample ``k``: a ramp from 0 at sample 200 to ``magnitude`` at sample 800."""
    return float(_drift_ramp(magnitude)[k - 1])


def _low_pass(noise: np.ndarray) -> np.ndarray:
    """IndPenSim's disturbance filter ``filter(1 - 0.995, [1 -0.995], noise)``, ``y[n] = 0.005 x[n] + 0.995 y[n-1]``.

    Written as a plain Python loop rather than ``scipy.signal.lfilter``: Python float arithmetic follows IEEE 754 the
    same way on every platform, while SciPy's compiled loop may use fused multiply-adds (it does on macOS), which
    changes the last bits after a few hundred samples. This keeps the random inputs of a seeded batch bit-identical
    everywhere.
    """
    out = np.empty(len(noise))
    y = 0.0
    for n, x in enumerate(noise.tolist()):
        y = 0.005 * x + 0.995 * y
        out[n] = y
    return out


def _nan_to_num(x: float) -> float:
    """Scalar ``numpy.nan_to_num`` (much cheaper on a single value)."""
    if math.isnan(x):
        return 0.0
    if math.isinf(x):
        return math.copysign(np.finfo(float).max, x)
    return x


def _ph(h_ion: float) -> float:
    """pH from the H+ concentration that the model integrates."""
    return -math.log(h_ion) / math.log(10)


def _ph_channel(h_ions) -> np.ndarray:
    """pH of a recorded H+ channel; rows not simulated yet (0) stay 0."""
    return np.array([_ph(v) if v != 0 else v for v in h_ions])


def _initial_state(x0: dict[str, float]) -> list[float]:
    """The 33 model states at time 0 (``model.STATE_NAMES``) built from ``x0`` as in ``indpensim.m``.

    Heat ``Q`` starts at 0, viscosity at 4 cP, vacuole densities, dissolved CO2 and the two rate integrals at 0.
    """
    return [x0["S"], x0["DO2"], x0["O2"], x0["P"], x0["V"], x0["Wt"], x0["pH"], x0["T"], 0, 4,
            x0["Culture_age"], x0["a0"], x0["a1"], x0["a3"], x0["a4"]] + [0] * 12 + [
            x0["CO2outgas"], 0, x0["PAA"], x0["NH3"], 0, 0]  # fmt: skip


@dataclass
class BatchParameters:
    """Everything random about a batch: initial state, kinetic parameters and disturbance sequences.

    ``Simulator.reset(seed)`` draws them from the seed. Build them yourself to replay a batch exactly, for example
    one captured from MATLAB IndPenSim with ``BatchParameters.from_matlab``.

    Attributes:
        x0: initial state, IndPenSim's ``x0`` structure (pH stored as the H+ concentration, as in IndPenSim
            after its ``10^-pH`` conversion).
        params: ``[mu_p, mux_max, alpha_kla, N_conc_paa, PAA_c]``.
        disturbances: the sequences in ``DISTURBANCES``, one value per sample plus one (index ``k - 1`` is
            used for sample ``k``).
    """

    x0: dict[str, float]
    params: list[float]  # mu_p, mux_max, alpha_kla, N_conc_paa, PAA_c
    disturbances: dict[str, np.ndarray]

    @classmethod
    def from_matlab(cls, path) -> BatchParameters:
        """Load a batch captured from MATLAB IndPenSim.

        ``path`` is a ``.mat`` file holding the workspace variables of ``indpensim_run.m`` after its setup
        block: ``x0`` (with pH as pH, before ``indpensim`` converts it), ``alpha_kla``, ``PAA_c``,
        ``N_conc_paa`` and the eight ``dist*`` vectors. Save them in MATLAB with::

            save('batch.mat', 'x0', 'alpha_kla', 'PAA_c', 'N_conc_paa', 'distMuP', 'distMuX', 'distcs', ...
                 'distcoil', 'distabc', 'distPAA', 'distTcin', 'distO_2in')
        """
        from scipy.io import loadmat

        m = loadmat(path, squeeze_me=True, struct_as_record=False)
        x0 = {name: float(getattr(m["x0"], name)) for name in _X0_NAMES}
        x0["pH"] = 10 ** (-x0["pH"])
        params = [x0["mup"], x0["mux"], float(m["alpha_kla"]), float(m["N_conc_paa"]), float(m["PAA_c"])]
        disturbances = {name: np.atleast_1d(np.asarray(m[name], dtype=float)) for name in DISTURBANCES}
        return cls(x0=x0, params=params, disturbances=disturbances)

    def copy(self) -> BatchParameters:
        return BatchParameters(
            x0=dict(self.x0),
            params=list(self.params),
            disturbances={name: np.array(v, dtype=float) for name, v in self.disturbances.items()},
        )

    @classmethod
    def from_seed(cls, seed: int, n_steps: int = NUM_STEPS) -> BatchParameters:
        """Draw the batch from ``seed`` (means and standard deviations of ``indpensim_run.m``, see ``_DRAWS``).

        Every random quantity has its own stream (``numpy.random.SeedSequence(seed)`` spawned by name), so the
        draws are independent, as in IndPenSim, and identical on every platform.
        """
        streams = dict(zip(_RANDOM_NAMES, np.random.SeedSequence(seed).spawn(len(_RANDOM_NAMES)), strict=True))

        def normal(name: str, size: int | None = None):
            draw = np.random.default_rng(streams[name]).standard_normal(size)
            return draw if size else float(draw)

        disturbances = {
            name: _low_pass(scale * normal(name, n_steps + 1)) for name, scale in _DISTURBANCE_SCALES.items()
        }

        base = 0.5 + 0.05 * normal("X_base")  # base biomass level (``initial_conds`` in indpensim_run.m)
        v = {name: (base if mean is None else mean) + sd * normal(name) for name, (mean, sd) in _DRAWS.items()}
        x0 = {name: v.get(name, 0.0) for name in _X0_NAMES}  # P, a3, a4 and Culture_age start at 0
        x0["pH"] = 10 ** (-x0["pH"])  # stored as H+ concentration
        x0["a0"] = base * 0.3333333333333333  # growing regions: 1/3 of the base level
        x0["a1"] = base * 0.6666666666666666  # non-growing regions: 2/3
        params = [x0["mup"], x0["mux"], v["alpha_kla"], v["N_conc_paa"], v["PAA_c"]]
        return cls(x0=x0, params=params, disturbances=disturbances)

    def initial_conditions(self) -> dict[str, float]:
        """Current values of everything in ``INITIAL_CONDITIONS`` (pH as pH, biomass as a0 + a1)."""
        x0 = self.x0
        values = {name: x0[name] for name in ("S", "DO2", "V", "Wt", "T", "O2", "CO2outgas", "PAA", "NH3")}
        values["X"] = x0["a0"] + x0["a1"]
        values["pH"] = _ph(x0["pH"])
        values.update(zip(_PARAMS, self.params, strict=True))
        return {name: float(values[name]) for name in INITIAL_CONDITIONS}

    def override(self, values: dict[str, float]) -> None:
        """Replace some of ``INITIAL_CONDITIONS`` (pH as pH; ``X`` is split 1/3 : 2/3 into a0 and a1)."""
        unknown = set(values) - set(INITIAL_CONDITIONS)
        if unknown:
            raise ValueError(f"unknown initial conditions {sorted(unknown)}; choose from {list(INITIAL_CONDITIONS)}")
        for name, value in values.items():
            if name in _PARAMS:
                self.params[_PARAMS.index(name)] = value
            elif name == "pH":
                self.x0["pH"] = 10 ** (-value)
            else:
                self.x0[name] = value
                if name == "X":
                    self.x0["a0"] = value * 0.3333333333333333
                    self.x0["a1"] = value * 0.6666666666666666


class Simulator:
    """IndPenSim batch simulator.

    Run a whole batch with the default recipe::

        result = Simulator().run(seed=1)
        df = result.to_pandas()

    or step through it, choosing the recipe inputs yourself (e.g. for control or RL)::

        sim = Simulator()
        obs = sim.reset(seed=1)
        while not sim.done:
            obs, reward = sim.step(**my_policy(obs))
        result = sim.result()

    Args:
        recipe: setpoint profiles used by ``run`` (and as reference by ``recipe_inputs``). Default: the
            IndPenSim default recipe.
        config: simulation switches.
        solver: ODE backend, see ``penicillium.solvers``. Default: ``"lsoda"``.
        rtol: relative tolerance of the solver (``None``: ``1e-5``).
        atol: absolute tolerance of the solver (``None``: ``1e-7``).
        max_step: largest solver step in hours (``None``: 0.01 h, a twentieth of a sample).
        backend: how the model is evaluated: ``"numba"`` (compiled, ~30x faster model evaluations; needs
            the ``fast`` extra or ``pip install numba``), ``"python"``, or ``"auto"`` (numba if installed). They
            agree to ~1e-11 relative (the math libraries round differently in the last bits); the first numba run
            in a fresh environment spends a few seconds compiling.
    """

    def __init__(
        self,
        recipe: Recipe | None = None,
        config: SimulationConfig | None = None,
        solver: str | None = None,
        rtol: float | None = None,
        atol: float | None = None,
        max_step: float | None = None,
        backend: str = "auto",
    ):
        self.config = config if config is not None else SimulationConfig()
        solver = solver if solver is not None else "lsoda"
        if solver not in SOLVERS:
            raise ValueError(f"unknown solver {solver!r}; choose one of {SOLVERS}")
        self.recipe = recipe if recipe is not None else Recipe.default()
        self.solver = solver
        self.rtol = rtol
        self.atol = atol
        self.max_step = max_step
        if backend == "auto":
            backend = "numba" if _numba.AVAILABLE else "python"
        if backend == "numba" and not _numba.AVAILABLE:
            raise ImportError("backend='numba' needs numba: pip install numba")
        if backend not in ("numba", "python"):
            raise ValueError(f"unknown backend {backend!r}; choose 'auto', 'numba' or 'python'")
        self.backend = backend
        self._n_steps = self.config.n_steps
        # Sample k (1-based) integrates from _t_grid[k-1] to _t_grid[k].
        self._t_grid = np.arange(0, self.config.batch_length_h + STEP_IN_HOURS, STEP_IN_HOURS)
        self._k = 0
        self._seed: int | None = None

    # ------------------------------------------------------------------ public API

    @property
    def k(self) -> int:
        """Number of completed samples."""
        return self._k

    @property
    def done(self) -> bool:
        return self._k >= self._n_steps

    @property
    def time(self) -> float:
        """Current time in hours."""
        return self._k * STEP_IN_HOURS

    def recipe_inputs(self, k: int | None = None) -> dict[str, float]:
        """Recipe inputs for sample ``k`` (1-based; default: the next sample)."""
        k = self._k + 1 if k is None else k
        # The recipe is read at the end of the sample, k * 12 / 60 h, computed in integers so 15 * 12 / 60 == 3.0.
        return self.recipe.at(k * STEP_IN_MINUTES / MINUTES_PER_HOUR)

    @staticmethod
    def initial_conditions(seed: int = 0, config: SimulationConfig | None = None) -> dict[str, float]:
        """Initial conditions and batch parameters that ``seed`` gives (see ``INITIAL_CONDITIONS`` for units).

        ``config`` is accepted for symmetry with ``Simulator``; it does not change the draws.
        """
        return BatchParameters.from_seed(seed).initial_conditions()

    def reset(
        self,
        seed: int = 0,
        rng: RNG | None = None,
        initial_conditions: dict[str, float] | None = None,
        batch_parameters: BatchParameters | None = None,
    ) -> dict[str, float]:
        """Start a new batch and return the initial observation.

        Args:
            seed: batch seed. Initial conditions, kinetic parameters and disturbances are derived from it
                (``BatchParameters.from_seed``).
            rng: generator for Raman noise and PRBS perturbations. Defaults to
                ``numpy.random.default_rng(seed)``; a ``Generator`` is split into independent streams for the
                two. A legacy ``numpy.random.RandomState`` is used as one shared stream
                for both.
            initial_conditions: values replacing the seeded ones, e.g. ``{"S": 2.0, "pH": 6.4}``; see
                ``INITIAL_CONDITIONS`` and ``Simulator.initial_conditions(seed)``.
            batch_parameters: initial state, kinetic parameters and disturbances to use instead of those drawn
                from ``seed`` (for example ``BatchParameters.from_matlab(...)`` to replay a MATLAB batch).
                ``initial_conditions`` overrides are applied on top.
        """
        self._seed = seed
        rng = rng if rng is not None else np.random.default_rng(seed)
        if isinstance(rng, np.random.Generator):
            # Independent streams, so recording spectra (or not) never changes the PRBS perturbations.
            self._rng, self._prbs_rng = rng.spawn(2)
        else:
            self._rng = self._prbs_rng = rng
        if batch_parameters is not None:
            short = [n for n in DISTURBANCES if len(batch_parameters.disturbances[n]) < self._n_steps]
            if short:
                raise ValueError(f"disturbance sequences shorter than the batch ({self._n_steps} samples): {short}")
            self._bp = batch_parameters.copy()
        else:
            self._bp = BatchParameters.from_seed(seed, self._n_steps)
        if initial_conditions:
            self._bp.override(initial_conditions)
        self._params = list(self._bp.params)  # model par[0:5]; the growth-rate reset changes mux_max in place
        self._growth_resets: list[int] = []
        # Recorded channels, one row per sample. The 31 state channels are also the next sample's initial state.
        self._data = {name: np.zeros(self._n_steps) for name in CHANNEL_NAMES}
        self._data["PAA_pred"][:] = np.nan  # NaN until predicted
        self._raman = np.zeros((self._n_steps, raman.N_WAVENUMBERS)) if self.config.raman_mode else None
        self._prbs = np.zeros(self._n_steps)  # PRBS perturbation drawn at each sample
        self._yield_pre = 0.0  # V * P / 1000 at the end of the previous sample [kg]
        self._total_yield = 0.0
        self._k = 0
        return self._observation(index=0)

    def step(
        self,
        Fs: float,
        Foil: float,
        Fg: float,
        pressure: float,
        discharge: float,
        Fw: float,
        Fpaa: float,
    ) -> tuple[dict[str, float], float]:
        """Simulate one 12-minute sample with the given recipe inputs.

        Returns the observation at the end of the sample and the penicillin harvested during it [kg].
        """
        if self._seed is None:
            raise RuntimeError("call reset() before step()")
        if self.done:
            raise RuntimeError("batch finished; call reset() to start a new one")
        self._k += 1
        try:
            reward = self._step(self._k, Fs, Foil, Fg, pressure, discharge, Fw, Fpaa)
        except SolverError as exc:
            self._k -= 1  # the sample was not recorded; result() returns the samples before it
            raise SolverError(f"sample {self._k + 1} ({self.time:.1f} h): {exc}") from exc
        self._total_yield += reward
        return self._observation(index=self._k - 1), reward

    def latest_spectrum(self) -> np.ndarray | None:
        """Raman spectrum of the last completed sample (wavenumbers as ``raman.WAVENUMBER``, descending).

        ``None`` before the first spectrum (spectra start after sample 10) or when Raman is off. The array is a
        view; copy it if you keep it.
        """
        if self._raman is None or self._k <= 10:
            return None
        return self._raman[self._k - 1]

    def run(
        self,
        seed: int = 0,
        rng: RNG | None = None,
        initial_conditions: dict[str, float] | None = None,
        batch_parameters: BatchParameters | None = None,
    ) -> BatchResult:
        """Simulate a whole batch with ``self.recipe`` (arguments as in ``reset``)."""
        self.reset(seed, rng, initial_conditions, batch_parameters)
        while not self.done:
            self.step(**self.recipe_inputs())
        return self.result()

    def result(self) -> BatchResult:
        """Data recorded so far."""
        n = self._k
        data = {name: values[:n].copy() for name, values in self._data.items()}
        # Outputs use pH and kJ.
        data["pH"] = _ph_channel(data["pH"])
        data["Q"] = data["Q"] / 1000
        return BatchResult(
            time=np.arange(1, n + 1) * STEP_IN_HOURS,
            data=data,
            raman=None if self._raman is None else self._raman[:n].copy(),
            raman_wavenumber=raman.WAVENUMBER.copy(),
            total_yield=self._total_yield,
            seed=self._seed,
            config=self.config,
            solver=self.solver,
            metadata={
                "initial_conditions": self._bp.initial_conditions(),
                # Samples at which IndPenSim's growth-rate reset (Inhib 1/2) set mu_x_max to 5 * mu_X_calc.
                "growth_rate_resets": list(self._growth_resets),
            },
        )

    # ------------------------------------------------------------------ internals

    def _observation(self, index: int) -> dict[str, float]:
        d = self._data
        obs = {name: float(d[name][index]) for name in OBSERVATION_CHANNELS}
        h_ion = d["pH"][index]
        obs["pH"] = _ph(h_ion) if h_ion != 0 else 0.0
        return obs

    def _step(self, k, Fs, Foil, Fg, pressure, discharge, Fw, Fpaa) -> float:
        """Sample ``k`` (1-based, from ``t_{k-1}`` to ``t_k``), recorded in row ``i = k - 1``; returns the reward."""
        d, cfg, i = self._data, self.config, k - 1
        if k == 1:  # the controllers of the first samples read the initial measurements from row 0
            for name in ("S", "DO2", "X", "P", "V", "CO2outgas", "pH", "T"):
                d[name][0] = self._bp.x0[name]

        u = self._control(k, Fs, Foil, Fg, pressure, discharge, Fw, Fpaa)

        # Start from x0, then from the states recorded for the previous sample, i.e. *after* the clamps below (as
        # in indpensim.m). The two rate integrals mu_P_calc and mu_X_calc restart from 0 every sample.
        y0 = _initial_state(self._bp.x0) if k == 1 else [d[name][k - 2] for name in STATE_NAMES[:31]] + [0, 0]

        # Growth-rate reset (Inhib 1/2, indpensim.m): growth cannot recover after a long decline (sub-optimal pH or
        # temperature). If mu_X_calc fell in 63 of its last 64 changes, mu_x_max becomes 5 x the last mu_X_calc.
        if cfg.inhibition in (1, 2) and k > 65:
            window = d["mu_X_calc"][k - 66 : k - 1]
            if np.count_nonzero(window[1:] < window[:-1]) >= 63:
                self._params[1] = d["mu_X_calc"][k - 2] * 5
                self._growth_resets.append(k)

        # Model parameters and inputs, laid out as model.PARAM_NAMES.
        dist = self._bp.disturbances
        par = [
            *self._params, cfg.inhibition, u["Fs"], u["Fg"], u["RPM"], u["Fc"], u["Fh"], u["Fb"], u["Fa"],
            STEP_IN_HOURS / 20,  # step1 in the pH model: IndPenSim passes h/20
            u["Fw"], u["pressure"], 4, u["discharge"], u["Fpaa"], u["Foil"], 0,  # input viscosity 4, no NH3 shots
            int(cfg.disturbances), *(dist[name][i] for name in DISTURBANCES), int(cfg.viscosity_from_input),
        ]  # fmt: skip
        if self.backend == "numba":
            f, y0, par = _numba.rhs, np.asarray(y0, dtype=float), np.asarray(par, dtype=float)
        else:
            f = rhs  # looked up at call time (tests replace it)
        y, _ = integrate(f, y0, self._t_grid[i], self._t_grid[k], par, self.solver, self.rtol, self.atol, self.max_step)
        y = np.array(y, dtype=float)
        y[:31] = np.where(y[:31] <= 0, 0.001, y[:31])  # indpensim.m: "minimum values for numerical stability"

        # Record inputs and states. What is written here for the 31 states is where sample k + 1 starts from.
        for name, value in u.items():
            d[name][i] = value
        for name, value in zip(STATE_NAMES, y, strict=True):
            d[name][i] = value
        if d["DO2"][i] < 2:  # indpensim.m floors dissolved oxygen at 1 mg/L when it drops below 2
            d["DO2"][i] = 1
        d["X"][i] = d["a0"][i] + d["a1"][i] + d["a3"][i] + d["a4"][i]

        # Off-gas: oxygen uptake and carbon evolution rates (constants as in indpensim.m).
        d["OUR"][i], d["CER"][i] = off_gas_rates(d["Fg"][i], d["O2"][i], d["CO2outgas"][i])

        if k > 10 and cfg.raman_mode:  # spectra start after sample 10
            self._raman[i] = raman.spectrum(
                k, d["P"][i], d["X"][i], d["Viscosity"][i], d["S"][i], d["PAA"][i],
                self._rng if cfg.raman_noise else None, self._n_steps,
            )  # fmt: skip

        # PLS prediction of PAA from the previous spectrum, smoothed over three samples (Substrate_prediction.m).
        # In IndPenSim it only feeds the PAA controller's derivative term, whose gain is zero, so it is an output.
        if k > 10 and cfg.raman_mode == RamanMode.PAT_CONTROL:
            j = k - 1  # 1-based sample of the spectrum used
            pred = raman.paa_pls_predict(self._raman[j - 1])
            if j > 20:
                pred = (d["PAA_pred"][j - 2] + d["PAA_pred"][j - 3] + pred) / 3
            d["PAA_pred"][j - 1] = pred

        # Offline measurements every `offline_interval_h`, at 1 h and at the end of the batch, reporting the value
        # from `offline_delay_steps` samples earlier; NaN between analyses.
        every = round(cfg.offline_interval_h / STEP_IN_HOURS)
        sampled = k % every == 0 or k in (round(1 / STEP_IN_HOURS), self._n_steps)
        j = i - cfg.offline_delay_steps
        for name in ("NH3", "Viscosity", "PAA", "P", "X"):
            d[f"{name}_offline"][i] = d[name][j] if sampled and j >= 0 else np.nan

        # Reward: penicillin in the vessel now minus at the previous sample, plus what the discharge removed
        # (discharge is negative while draining). Summed over the batch it is the harvested penicillin [kg].
        d["V"][i] = _nan_to_num(d["V"][i])
        d["P"][i] = _nan_to_num(d["P"][i])
        peni_yield = d["V"][i] * d["P"][i] / 1000
        reward = peni_yield - self._yield_pre - d["discharge"][i] * d["P"][i] * STEP_IN_HOURS / 1000
        self._yield_pre = peni_yield
        return float(reward)

    def _control(self, k, Fs, Foil, Fg, pressure, discharge, Fw, Fpaa) -> dict[str, float]:
        """Inputs applied during sample ``k`` (``fctrl_indpensim.m``): pH and temperature PIDs, PRBS, faults, PAT.

        The controllers see the measurements up to sample ``k - 1`` (row ``k - 2``): one sample of dead time. Before
        three samples of history exist, row 0 stands in for the missing ones. Returns the recorded inputs and
        ``Fault_ref``.
        """
        d, cfg, h = self._data, self.config, STEP_IN_HOURS
        fixed = cfg.quirks == "fixed"
        r1, r2, r3 = max(k - 2, 0), max(k - 3, 0), max(k - 4, 0)  # rows of samples k-1, k-2, k-3
        fault_ref = 0

        # ---- pH: split range, base when pH is below the setpoint (error >= -0.05), acid otherwise.
        ph_drift = 0.0
        if cfg.fault == Fault.PH_SENSOR:
            ph_drift = _sensor_drift(k, 0.1)
            fault_ref = 1
        ph, ph1, ph2 = _ph(d["pH"][r1]), _ph(d["pH"][r2]), _ph(d["pH"][r3])
        ph_err = cfg.ph_setpoint - ph + ph_drift
        # From sample 3 on IndPenSim omits the setpoint here; kept unless quirks="fixed" (quirks.md 2.1).
        ph_err1 = (cfg.ph_setpoint if fixed or k <= 2 else 0.0) - ph1 + ph_drift
        if ph_err >= -0.05:
            Fb = pid_controller(d["Fb"][r1], ph_err, ph_err1, ph, ph1, ph2, 0, 225, 8e-2, 4.0000e-05, 8, h)
            Fa = 0
        else:
            Fa = pid_controller(d["Fa"][r1], ph_err, ph_err1, ph, ph1, ph2, 0, 225, 8e-2, 12.5, 0.125, h)
            Fb = 0 if k == 1 else d["Fb"][r1] * 0.5

        # ---- Temperature: split range, cooling water when T is above the setpoint - 0.05 K, hot water otherwise.
        T_drift = 0.0
        if cfg.fault == Fault.TEMPERATURE_SENSOR:
            T_drift = _sensor_drift(k, 0.4)
            fault_ref = 1
        T, T1, T2 = d["T"][r1], d["T"][r2], d["T"][r3]
        T_err = cfg.temperature_setpoint - T + T_drift
        T_err1 = cfg.temperature_setpoint - T1 + T_drift
        if T_err <= 0.05:
            Fc = pid_controller(d["Fc"][r1], T_err, T_err1, T, T1, T2, 0, 1.5e3, -300, 1.6, 0.005, h)
            Fh = 0 if k == 1 else d["Fh"][r1] * 0.1
        else:
            # IndPenSim uses the previous cooling flow as the heating controller's previous output (quirk 4.2).
            Fh_prev = d["Fh"][r1] if fixed else d["Fc"][r1]
            Fh = pid_controller(Fh_prev, T_err, T_err1, T, T1, T2, 0, 1.5e3, 50, 0.050, 1, h)
            Fc = 0 if k == 1 else d["Fc"][r1] * 0.3
        Fc = 1e-4 if Fc < 1e-4 else Fc
        Fh = 1e-4 if Fh < 1e-4 else Fh

        # The recipe's discharge is an outflow: negative in the model. Agitation is fixed at 100 rpm.
        u = {"Fs": Fs, "Foil": Foil, "Fg": Fg, "pressure": pressure, "discharge": -discharge, "Fw": Fw, "Fpaa": Fpaa,
             "Fa": Fa, "Fb": Fb, "Fc": Fc, "Fh": Fh, "RPM": 100}  # fmt: skip

        # ---- PRBS (operator-style batches): from sample 476 the sugar and PAA feeds hold their last value, and every
        # 100 samples after 500 a step of 0, +step or -step is added.
        if cfg.prbs and k > 475:
            for name, size in (("Fs", 15), ("Fpaa", 1)):
                u[name] = d[name][k - 2]
                if k > 500 and k % 100 == 0:
                    r = randint(self._prbs_rng, 1, 4)
                    self._prbs[k - 1] = 0 if r == 1 else (size if r == 2 else -size)
                    # IndPenSim adds the perturbation just drawn (`X.PRBS_noise_addition(end)` of an array that grows
                    # to length k).
                    u[name] = d[name][k - 2] + self._prbs[k - 1]

        # ---- Process faults force an input to a fixed value over fixed sample ranges.
        for fault in _FAULT_PROFILES if cfg.fault == Fault.ALL else (cfg.fault,):
            for name, value, first, last in _FAULT_PROFILES.get(fault, ()):
                if first <= k <= last:
                    u[name] = value
                    fault_ref = 1

        # ---- PAT control of PAA from 10 h: PID on the true PAA to 1200 mg/L. IndPenSim's PLS prediction enters only
        # a zero-gain D term (quirks.md 2.5), so the D input is 0 here.
        if cfg.raman_mode == RamanMode.PAT_CONTROL and k * STEP_IN_HOURS >= 10:
            PAA_err, PAA_err1 = 1200 - d["PAA"][r1], 1200 - d["PAA"][r2]
            u["Fpaa"] = pid_controller(d["Fpaa"][r1], PAA_err, PAA_err1, 0.0, 0.0, 0.0, 0, 150, 0.1, 0.50, 0, h)

        u["Fault_ref"] = fault_ref
        return u
