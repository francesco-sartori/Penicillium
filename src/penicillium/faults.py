"""Fault onset, duration and magnitude, fixed or random (an addition to IndPenSim).

By default a fault acts in IndPenSim V2.01's fixed windows (``penicillium.Fault``). A ``FaultSpec`` describes one
window of one fault instead, with its onset, duration and magnitude each fixed or drawn from a distribution, and its
shape (a step, or a ramp). A sensor fault (7-8) keeps its final offset after the window, as IndPenSim's drift does::

    from penicillium import FaultSpec, SimulationConfig, Simulator
    from penicillium.faults import Normal, Uniform

    cfg = SimulationConfig(fault_specs=FaultSpec("aeration", randomise=True))  # random onset and duration
    cfg = SimulationConfig(fault_specs=FaultSpec("substrate_feed", onset_h=Uniform(30, 120),
                                                 duration_h=Normal(8, 2, low=1), magnitude=0.6, effect="scale"))
    result = Simulator(config=cfg).run(seed=1)
    result.metadata["fault_windows"]  # the windows this batch drew

``FaultSpec.indpensim(fault)`` gives the IndPenSim windows of a fault as specs (the preset). Random values are drawn
from the batch seed, each from its own stream, so they never change the other random inputs of the batch.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Union

import numpy as np
from scipy.interpolate import interp1d

from .constants import MINUTES_PER_HOUR, STEP_IN_HOURS, STEP_IN_MINUTES
from .simulator import _FAULT_PROFILES, SINGLE_FAULTS, Fault

#: SeedSequence spawn key of the fault streams ("FLTS"). Three-element keys ``(_FAULT_KEY, spec, field)`` are clear
#: of the batch's own streams (one-element keys), of the noise streams (two-element keys) and of each other.
_FAULT_KEY = 0x464C5453

#: The faults a ``FaultSpec`` can describe (``ALL`` is several specs, ``NONE`` none).
SPEC_FAULTS: tuple[Fault, ...] = SINGLE_FAULTS

#: Process faults (forced inputs) and the faults that may share a batch under ``Fault.ALL``.
_PROCESS_FAULTS: tuple[Fault, ...] = tuple(_FAULT_PROFILES)


@dataclass(frozen=True)
class Uniform:
    """Uniform distribution on ``[low, high]``."""

    low: float
    high: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.low) and math.isfinite(self.high) and self.low <= self.high):
            raise ValueError(f"Uniform needs finite low <= high, got {self.low}, {self.high}")

    def draw(self, rng: np.random.Generator) -> float:
        return float(rng.uniform(self.low, self.high))


@dataclass(frozen=True)
class Normal:
    """Normal distribution, clipped to ``[low, high]`` when given."""

    mean: float
    sd: float
    low: float | None = None
    high: float | None = None

    def __post_init__(self) -> None:
        if not (math.isfinite(self.mean) and math.isfinite(self.sd) and self.sd >= 0):
            raise ValueError(f"Normal needs a finite mean and sd >= 0, got {self.mean}, {self.sd}")
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(f"Normal needs low <= high, got {self.low}, {self.high}")

    def draw(self, rng: np.random.Generator) -> float:
        value = self.mean + self.sd * float(rng.standard_normal())
        if self.low is not None:
            value = max(value, self.low)
        if self.high is not None:
            value = min(value, self.high)
        return value


@dataclass(frozen=True)
class Choice:
    """One of ``values``, each with the same probability."""

    values: tuple[float, ...]

    def __init__(self, values: Sequence[float]):
        values = tuple(float(v) for v in values)
        if not values:
            raise ValueError("Choice needs at least one value")
        object.__setattr__(self, "values", values)

    def draw(self, rng: np.random.Generator) -> float:
        return self.values[int(rng.integers(len(self.values)))]


Distribution = Union[Uniform, Normal, Choice]  # noqa: UP007 (runtime alias on Python 3.10)
Shape = Union[str, Callable[[float], float]]  # noqa: UP007

_EFFECTS: dict[str, str] = {
    "set": "the input is forced to the magnitude (IndPenSim)",
    "scale": "the input loses the fraction ``magnitude`` (0-1) of its value",
    "offset": "the magnitude is added (inputs: kept >= 0; sensors: the reading is true value - magnitude)",
}


@dataclass(frozen=True)
class _FaultInfo:
    target: str  # input forced, or "T" / "pH" for the sensor read by the controller
    effects: tuple[str, ...]  # first one is the default
    durations_h: tuple[float, float]  # range of the IndPenSim windows (``randomise`` draws from it)


_INFO: dict[Fault, _FaultInfo] = {
    Fault.AERATION: _FaultInfo("Fg", ("set", "scale"), (4.0, 10.0)),
    Fault.PRESSURE: _FaultInfo("pressure", ("set", "offset"), (4.0, 40.0)),
    Fault.SUBSTRATE_FEED: _FaultInfo("Fs", ("set", "scale", "offset"), (10.0, 16.0)),
    Fault.BASE_FLOW: _FaultInfo("Fb", ("set", "scale"), (4.0, 20.0)),
    Fault.COOLANT_FLOW: _FaultInfo("Fc", ("set", "scale"), (20.0, 30.0)),
    Fault.TEMPERATURE_SENSOR: _FaultInfo("T", ("offset",), (120.0, 120.0)),
    Fault.PH_SENSOR: _FaultInfo("pH", ("offset",), (120.0, 120.0)),
}

#: Sensor drift of IndPenSim (faults 7 and 8): offset, ramp from sample 200 to 800, then constant.
_SENSOR_DRIFT: dict[Fault, float] = {Fault.TEMPERATURE_SENSOR: 0.4, Fault.PH_SENSOR: 0.1}

#: Last sample of IndPenSim's sensor-drift table (350 h, the longest batch).
_TABLE_END = 1750

#: Earliest onset that ``randomise`` draws [h].
RANDOM_ONSET_MIN_H = 20.0


def _hours(sample: int) -> float:
    """Time at the end of sample ``sample`` [h], in integers as the recipe does (100 -> 20.0 exactly)."""
    return sample * STEP_IN_MINUTES / MINUTES_PER_HOUR


def _as_fault(fault: Fault | str | int) -> Fault:
    if isinstance(fault, str):
        try:
            fault = Fault[fault.upper()]
        except KeyError:
            raise ValueError(f"unknown fault {fault!r}; choose from {[f.name.lower() for f in SPEC_FAULTS]}") from None
    fault = Fault(fault)
    if fault not in SPEC_FAULTS:
        raise ValueError(f"a FaultSpec describes one of {[f.name for f in SPEC_FAULTS]}, not {fault.name}")
    return fault


@dataclass(frozen=True)
class FaultSpec:
    """One window of one fault: when it starts, how long it lasts, how large it is and how it evolves.

    Each of ``onset_h``, ``duration_h`` and ``magnitude`` is a number, a distribution (``Uniform``, ``Normal``,
    ``Choice``, drawn per batch from the batch seed) or ``None``. ``None`` takes the value of the fault's first
    IndPenSim window, or with ``randomise=True`` draws the onset and duration from the defaults (see
    ``docs/faults.md``). Windows are in 12-minute samples: the fault acts from the sample ending at ``onset_h`` to the
    one ending at ``onset_h + duration_h``, both included, as in IndPenSim (onset 20 h, duration 4 h: samples 100 to
    120).

    Attributes:
        fault: the fault (``Fault`` or its name, e.g. ``"aeration"``); any fault except ``NONE`` and ``ALL``.
        onset_h: start of the window [h], at least 0.2 h.
        duration_h: length of the window [h], >= 0 (0: one sample); ``math.inf`` (steps only): to the end of the batch.
        magnitude: size of the fault, in the unit of the input (``set``, ``offset``), as a fraction 0-1 (``scale``),
            or in K or pH units for the sensor faults (the reading is the true value minus the magnitude).
        shape: ``"step"`` (constant over the window), ``"ramp"`` (linear from 0 at the onset to the magnitude at the
            end of the window) or a function ``f(tau) -> [0, 1]`` of the fraction ``tau`` of the window elapsed (a ramp
            of that form). After the window the fault ends, or with ``hold`` keeps its final value. With ``n_jobs > 1``
            it must be picklable (a module-level function).
            ``None``: ``"step"`` for faults 1-5, ``"ramp"`` for the sensor faults 7-8 (IndPenSim's).
        effect: how the magnitude acts on an input: ``"set"``, ``"scale"`` or ``"offset"``; ``None``: the fault's
            default (``"set"`` for faults 1-5, ``"offset"`` for 7-8).
        hold: after the window, keep the value reached at its end until the end of the batch, as IndPenSim's sensor
            drift does. ``None``: ``True`` for the sensor faults 7-8 (whatever the duration or shape), ``False`` for
            faults 1-5.
        randomise: draw the onset and duration left at ``None`` instead of taking IndPenSim's.
    """

    fault: Fault
    onset_h: float | Distribution | None = None
    duration_h: float | Distribution | None = None
    magnitude: float | Distribution | None = None
    shape: Shape | None = None
    effect: str | None = None
    hold: bool | None = None
    randomise: bool = False
    _info: _FaultInfo = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        fault = _as_fault(self.fault)
        object.__setattr__(self, "fault", fault)
        info = _INFO[fault]
        object.__setattr__(self, "_info", info)
        sensor = fault in _SENSOR_DRIFT
        if self.shape is None:
            object.__setattr__(self, "shape", "ramp" if sensor else "step")
        if self.hold is None:
            object.__setattr__(self, "hold", sensor)
        if not (callable(self.shape) or self.shape in ("step", "ramp")):
            raise ValueError(f"shape must be 'step', 'ramp' or a function f(tau), got {self.shape!r}")
        if self.effect is not None and self.effect not in info.effects:
            raise ValueError(f"{fault.name} supports effect {info.effects}, got {self.effect!r}")
        if isinstance(self.onset_h, (int, float)) and not (STEP_IN_HOURS <= self.onset_h < math.inf):
            raise ValueError(f"onset_h must be finite and >= {STEP_IN_HOURS} h, got {self.onset_h}")
        if isinstance(self.duration_h, (int, float)):
            if not self.duration_h >= 0:
                raise ValueError(f"duration_h must be >= 0, got {self.duration_h}")
            if math.isinf(self.duration_h) and self.shape != "step":
                raise ValueError("an infinite duration needs shape='step'")
        if isinstance(self.magnitude, (int, float)):
            _check_magnitude(self.magnitude, self.effective_effect)
        elif self.magnitude is None and self.effective_effect != info.effects[0]:
            raise ValueError(f"effect {self.effective_effect!r} needs a magnitude (IndPenSim's is a forced value)")

    @property
    def effective_effect(self) -> str:
        """``effect``, or the fault's default."""
        return self.effect if self.effect is not None else self._info.effects[0]

    @classmethod
    def indpensim(cls, fault: Fault | str | int) -> tuple[FaultSpec, ...]:
        """The IndPenSim V2.01 windows of ``fault`` as specs (``Fault.ALL``: those of faults 1-5).

        They give the same inputs as ``SimulationConfig(fault=fault)``; only the label of the sensor faults differs:
        1 from the start of the drift (40 h), where IndPenSim marks the whole batch.
        """
        fault = Fault(Fault[fault.upper()] if isinstance(fault, str) else fault)
        if fault == Fault.ALL:
            return tuple(spec for f in _PROCESS_FAULTS for spec in cls.indpensim(f))
        if fault in _SENSOR_DRIFT:
            return (cls(fault, onset_h=40.0, duration_h=120.0, magnitude=_SENSOR_DRIFT[fault], shape="ramp",
                        hold=True),)  # fmt: skip
        if fault not in _FAULT_PROFILES:
            raise ValueError(f"{fault.name} has no IndPenSim windows")
        return tuple(
            cls(fault, onset_h=_hours(first), duration_h=_hours(last - first), magnitude=float(value))
            for _, value, first, last in _FAULT_PROFILES[fault]
        )


def _check_magnitude(value: float, effect: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"magnitude must be finite, got {value}")
    if effect == "set" and value < 0:
        raise ValueError(f"effect 'set' needs a magnitude >= 0, got {value}")
    if effect == "scale" and not 0 <= value <= 1:
        raise ValueError(f"effect 'scale' needs a magnitude in [0, 1], got {value}")


def _clip_magnitude(value: float, effect: str) -> float:
    if effect == "set":
        return max(value, 0.0)
    if effect == "scale":
        return min(max(value, 0.0), 1.0)
    return value


@dataclass(frozen=True)
class FaultWindow:
    """A window drawn for one batch: samples ``first`` to ``last`` (1-based, both included)."""

    fault: Fault
    target: str
    effect: str
    shape: Shape
    hold: bool
    first: int
    last: int
    magnitude: float
    _ramp: np.ndarray | None = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.shape == "ramp" and self.last > self.first:
            # Built like IndPenSim's sensor drift (linear interpolation evaluated at the samples), so the IndPenSim
            # preset gives the same values as the default code path, whatever SciPy's interpolation formula.
            # With ``hold`` the table runs on at the peak to sample 1750, as IndPenSim's does (the held value is then
            # interpolated too, which is not always exactly the magnitude).
            points = [[0, 0], [self.first, 0], [self.last, self.magnitude]]
            end = self.last
            if self.hold:
                end = max(_TABLE_END, self.last + 1)
                points.append([end, self.magnitude])
            points = np.array(points, dtype=float)
            # fill_value="extrapolate" as in ``simulator._drift_ramp``: without it interp1d delegates to np.interp,
            # which rounds differently.
            interp = interp1d(points[:, 0], points[:, 1], kind="linear", fill_value="extrapolate")
            object.__setattr__(self, "_ramp", interp(np.arange(self.first, end + 1)))

    def acts(self, k: int) -> bool:
        """Whether the fault acts in sample ``k`` (its label)."""
        return self.first <= k and (k <= self.last or self.hold)

    def weight(self, k: int) -> float:
        """Fraction of the magnitude applied in sample ``k`` (``acts(k)`` must hold)."""
        if self.shape == "step":
            return 1.0
        tau = 1.0 if k >= self.last else (k - self.first) / (self.last - self.first)
        if self.shape == "ramp":
            return tau
        w = float(self.shape(tau))
        if not 0.0 <= w <= 1.0:
            raise ValueError(f"fault shape {self.shape!r} returned {w} at tau = {tau} (sample {k}); expected [0, 1]")
        return w

    def amount(self, k: int) -> float:
        """Magnitude applied in sample ``k``: ``weight(k) * magnitude``.

        A linear ramp is interpolated as IndPenSim interpolates its sensor drift, so the IndPenSim preset is
        reproduced bit for bit.
        """
        if self._ramp is not None and k - self.first < len(self._ramp):
            return float(self._ramp[k - self.first])
        return self.weight(k) * self.magnitude

    def apply(self, k: int, value: float) -> float:
        """The input ``value`` with this fault applied in sample ``k``."""
        if self.effect == "set":
            if self.shape == "step":
                return self.magnitude
            return value + self.weight(k) * (self.magnitude - value)
        if self.effect == "scale":
            return value * (1 - self.weight(k) * self.magnitude)
        return max(value + self.amount(k), 0.0)

    def as_dict(self) -> dict[str, Any]:
        """Description for ``BatchResult.metadata["fault_windows"]`` and ``Campaign.fault_windows``."""
        shape = self.shape if isinstance(self.shape, str) else getattr(self.shape, "__name__", repr(self.shape))
        return {
            "fault": int(self.fault), "fault_name": self.fault.name, "target": self.target, "effect": self.effect,
            "shape": shape, "hold": self.hold, "onset_h": _hours(self.first), "end_h": _hours(self.last),
            "magnitude": self.magnitude,
        }  # fmt: skip


def normalise_specs(specs: Any, fault: Fault | int) -> tuple[tuple[FaultSpec, ...], Fault]:
    """Validate ``SimulationConfig.fault_specs`` and work out the batch's fault code.

    One fault type gives that code; several process faults (1-5) give ``Fault.ALL``. A ``fault`` set explicitly
    must agree with the specs.
    """
    specs = (specs,) if isinstance(specs, FaultSpec) else tuple(specs)
    bad = [s for s in specs if not isinstance(s, FaultSpec)]
    if bad:
        raise TypeError(f"fault_specs must hold FaultSpec objects, got {bad!r}")
    types = {s.fault for s in specs}
    fault = Fault(fault)
    if fault == Fault.NONE:
        if len(types) == 1:
            return specs, next(iter(types))
        fault = Fault.ALL
    if fault == Fault.ALL:
        if not types <= set(_PROCESS_FAULTS):
            raise ValueError("faults of different types can share a batch only among faults 1-5 (Fault.ALL)")
        return specs, fault
    if types != {fault}:
        raise ValueError(f"fault={fault.name} but fault_specs describe {sorted(t.name for t in types)}")
    return specs, fault


def _stream(seed: int, spec_index: int, field_index: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(_FAULT_KEY, spec_index, field_index)))


def draw_windows(specs: Sequence[FaultSpec], seed: int, n_steps: int) -> list[FaultWindow]:
    """The windows of a batch of ``n_steps`` samples, drawn from ``seed``.

    Onset, duration and magnitude of spec ``j`` come from the streams ``(_FAULT_KEY, j, 0 | 1 | 2)``, so a value
    fixed in one field never changes the draws of another, and nothing here touches the batch's other random inputs.
    """
    windows = []
    batch_h = _hours(n_steps)
    for j, spec in enumerate(specs):
        preset = FaultSpec.indpensim(spec.fault)[0]
        effect = spec.effective_effect

        duration = spec.duration_h
        if duration is None:
            lo, hi = spec._info.durations_h
            duration = Uniform(lo, hi) if spec.randomise and lo < hi else preset.duration_h
        duration = duration.draw(_stream(seed, j, 1)) if not isinstance(duration, (int, float)) else duration
        duration = max(float(duration), 0.0)

        onset = spec.onset_h
        if onset is None:
            span = duration if math.isfinite(duration) else 0.0
            onset = (
                Uniform(RANDOM_ONSET_MIN_H, max(RANDOM_ONSET_MIN_H, batch_h - span))
                if spec.randomise
                else preset.onset_h
            )
        onset = onset.draw(_stream(seed, j, 0)) if not isinstance(onset, (int, float)) else onset
        first = max(round(float(onset) / STEP_IN_HOURS), 1)

        magnitude = spec.magnitude
        if magnitude is None:
            magnitude = preset.magnitude if effect == preset.effective_effect else None
            if magnitude is None:
                raise ValueError(f"{spec.fault.name} with effect {effect!r} needs a magnitude")
        if not isinstance(magnitude, (int, float)):
            magnitude = _clip_magnitude(magnitude.draw(_stream(seed, j, 2)), effect)

        last = max(n_steps, first) if math.isinf(duration) else first + round(duration / STEP_IN_HOURS)
        windows.append(
            FaultWindow(spec.fault, spec._info.target, effect, spec.shape, spec.hold, first, last, float(magnitude))
        )
    return windows


def sensor_offset(windows: Sequence[FaultWindow], k: int, target: str) -> tuple[float, bool]:
    """Offset of the ``target`` reading (``"T"`` or ``"pH"``) in sample ``k``, and whether a sensor fault acts."""
    offset, active = 0.0, False
    for w in windows:
        if w.target == target and w.acts(k):
            offset += w.amount(k)
            active = True
    return offset, active


def apply_process_faults(windows: Sequence[FaultWindow], k: int, u: dict[str, float]) -> bool:
    """Apply the process-fault windows acting in sample ``k`` to the inputs ``u``, in order; True if any acts."""
    active = False
    for w in windows:
        if w.target in u and w.target not in ("T", "pH") and w.acts(k):
            u[w.target] = w.apply(k, u[w.target])
            active = True
    return active
