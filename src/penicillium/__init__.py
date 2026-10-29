"""Maintained, validated Python implementation of the IndPenSim penicillin fermentation simulator."""

from . import scenarios
from ._version import __version__
from .batches import BatchSpec, simulate_batches
from .noise import MeasurementNoise, Sensor
from .recipe import INPUTS, Profile, Recipe
from .result import CHANNELS, BatchResult
from .simulator import DISTURBANCES, INITIAL_CONDITIONS, BatchParameters, Fault, RamanMode, SimulationConfig, Simulator
from .solvers import SolverError

__all__ = [
    "CHANNELS",
    "DISTURBANCES",
    "INITIAL_CONDITIONS",
    "INPUTS",
    "BatchParameters",
    "BatchResult",
    "BatchSpec",
    "Fault",
    "MeasurementNoise",
    "Profile",
    "RamanMode",
    "Recipe",
    "Sensor",
    "SimulationConfig",
    "Simulator",
    "SolverError",
    "__version__",
    "scenarios",
    "simulate_batches",
]
