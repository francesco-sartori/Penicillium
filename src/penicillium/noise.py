"""Measurement noise on the online channels and the lab results, added to a simulated batch afterwards.

    from penicillium import MeasurementNoise, Simulator

    result = Simulator().run(seed=1)
    noisy = MeasurementNoise.typical().apply(result)
    noisy["pH"]  # what the probe read
    noisy.truth["pH"]  # the process value

The simulator itself stays noise-free: noise is applied to a copy of the result, so the process, the controllers
and every seeded batch are unchanged. Each sensor combines the error sources of a real instrument:

    measured = quantise(clip(true * (1 + rel * e1) + sd * e2 + offset + drift(t)))

with ``e1``, ``e2`` standard normal per sample, ``offset`` drawn once per batch (calibration bias) and ``drift`` a
random walk (electrode ageing, membrane fouling). ``OUR`` and ``CER`` are not noised on their own: they are
recomputed from the measured aeration and off-gas, as a plant computes them.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field, replace

import numpy as np

from .result import CHANNELS, LAB_CHANNELS, BatchResult
from .simulator import off_gas_rates

#: Channels computed from other measurements, never noised on their own.
DERIVED_CHANNELS: tuple[str, ...] = ("OUR", "CER")

# SeedSequence spawn key of the noise streams ("NOIS"), clear of the batch's own streams (0, 1, ... and 7).
_NOISE_KEY = 0x4E4F4953


@dataclass(frozen=True)
class Sensor:
    """Error model of one measurement, in the channel's units (see ``penicillium.CHANNELS``).

    Attributes:
        sd: additive white noise, standard deviation (probe precision).
        rel: relative white noise, standard deviation as a fraction of the reading (flowmeters, assays).
        offset_sd: calibration bias, drawn once per batch, standard deviation.
        drift_sd: random-walk drift, standard deviation per square root of hour.
        resolution: quantisation step of the transmitter or the reported result (0: none).
        lo: lowest value the instrument reports (``None``: no bound).
        hi: highest value the instrument reports (``None``: no bound).
    """

    sd: float = 0.0
    rel: float = 0.0
    offset_sd: float = 0.0
    drift_sd: float = 0.0
    resolution: float = 0.0
    lo: float | None = 0.0
    hi: float | None = None

    def __post_init__(self) -> None:
        for name in ("sd", "rel", "offset_sd", "drift_sd", "resolution"):
            if getattr(self, name) < 0:
                raise ValueError(f"Sensor.{name} must be >= 0, got {getattr(self, name)}")

    def scaled(self, factor: float) -> Sensor:
        """The same sensor with every random error multiplied by ``factor`` (resolution and bounds kept)."""
        return replace(self, sd=self.sd * factor, rel=self.rel * factor, offset_sd=self.offset_sd * factor,
                       drift_sd=self.drift_sd * factor)  # fmt: skip

    def measure(self, true: np.ndarray, time_h: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        """Measured values of ``true`` sampled at ``time_h``; NaN (no analysis) stays NaN.

        The draws do not depend on the parameters, so changing one error source leaves the others' realisation
        unchanged.
        """
        n = len(true)
        offset = rng.standard_normal()
        e_rel = rng.standard_normal(n)
        e_add = rng.standard_normal(n)
        steps = rng.standard_normal(n)
        dt = np.diff(time_h, prepend=0.0)
        drift = np.cumsum(self.drift_sd * np.sqrt(dt) * steps)
        out = true * (1 + self.rel * e_rel) + self.sd * e_add + self.offset_sd * offset + drift
        if self.resolution > 0:
            out = np.round(out / self.resolution) * self.resolution
        if self.lo is not None or self.hi is not None:
            out = np.clip(out, self.lo, self.hi)
        return out


@dataclass(frozen=True)
class MeasurementNoise:
    """Sensors of the online channels and the lab assays; channels without a sensor stay exact.

    Attributes:
        online: channel -> sensor, for channels recorded every sample (e.g. ``pH``, ``DO2``, ``Fb``).
        lab: channel -> assay error, for the off-line channels (``P_offline``, ...), applied once per analysis.
    """

    online: dict[str, Sensor] = field(default_factory=dict)
    lab: dict[str, Sensor] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in self.online:
            if name in DERIVED_CHANNELS:
                raise ValueError(f"{name} is computed from Fg, O2 and CO2outgas; give those sensors instead")
            if name in LAB_CHANNELS or name not in CHANNELS:
                raise ValueError(f"{name!r} is not an online channel")
        for name in self.lab:
            if name not in LAB_CHANNELS:
                raise ValueError(f"{name!r} is not a lab channel; lab channels are {LAB_CHANNELS}")

    @classmethod
    def none(cls) -> MeasurementNoise:
        """No noise: ``apply`` returns the exact values."""
        return cls()

    @classmethod
    def typical(cls) -> MeasurementNoise:
        """Indicative errors of industrial fermentation instruments and lab assays.

        Only measurements are noisy: probes, off-gas, weight and volume, and the flows the pH and temperature
        controllers manipulate. The recipe set points (``Fs``, ``Foil``, ``Fg``, ``pressure``, ``discharge``,
        ``Fw``, ``Fpaa``) and the fixed agitator speed stay exact; add a sensor with ``with_`` if your plant records
        metered values for them. The values are typical orders of magnitude, not the specification of a given plant:
        adapt them to your instruments with ``with_``. Do not give the controlled ``pH`` and ``T`` an offset or a
        drift: added after the simulation, it would show a reading away from the setpoint that the controller never
        saw. See docs/measurements.md for the table and the reasoning
        behind each value.
        """
        return cls(
            online={
                # pH and T are controlled: no offset or drift here (a biased probe would move the process, not the
                # reading; that needs the loop, see Fault.PH_SENSOR and Fault.TEMPERATURE_SENSOR).
                "T": Sensor(sd=0.03, resolution=0.01),  # Pt100 [K]
                "pH": Sensor(sd=0.01, resolution=0.01, hi=14.0),  # glass electrode
                "DO2": Sensor(rel=0.02, drift_sd=0.01),  # polarographic probe, membrane fouling [mg/L]
                "O2": Sensor(sd=5e-4, hi=1.0),  # off-gas analyser, fraction
                "CO2outgas": Sensor(sd=0.02, hi=100.0),  # off-gas analyser [%]
                "Fa": Sensor(rel=0.01), "Fb": Sensor(rel=0.01),  # pH controller outputs, Coriolis / magnetic
                "Fc": Sensor(rel=0.02), "Fh": Sensor(rel=0.02),  # temperature controller outputs, utility meters
                "Wt": Sensor(rel=0.002),  # load cells
                "V": Sensor(rel=0.005),  # volume from level / weight
            },
            lab={
                "P_offline": Sensor(rel=0.02, resolution=0.01),  # HPLC [g/L]
                "PAA_offline": Sensor(rel=0.03, resolution=1.0),  # HPLC [mg/L]
                "X_offline": Sensor(rel=0.07, sd=0.2, resolution=0.1),  # dry cell weight [g/L]
                "NH3_offline": Sensor(rel=0.05, resolution=1.0),  # enzymatic / ion-selective [mg/L]
                "Viscosity_offline": Sensor(rel=0.10, resolution=0.1),  # rheometer [cP]
            },
        )  # fmt: skip

    def with_(self, **sensors: Sensor | None) -> MeasurementNoise:
        """A copy with these channels' sensors replaced (``None`` removes one: the channel stays exact)."""
        online, lab = dict(self.online), dict(self.lab)
        for name, sensor in sensors.items():
            target = lab if name in LAB_CHANNELS else online
            if sensor is None:
                target.pop(name, None)
            else:
                target[name] = sensor
        return MeasurementNoise(online, lab)

    def scaled(self, factor: float) -> MeasurementNoise:
        """A copy with every random error multiplied by ``factor`` (0: only quantisation and bounds remain)."""
        return MeasurementNoise(
            {k: s.scaled(factor) for k, s in self.online.items()}, {k: s.scaled(factor) for k, s in self.lab.items()}
        )

    def apply(self, result: BatchResult, seed: int | None = None) -> BatchResult:
        """A copy of ``result`` whose measured channels hold noisy measurements; the exact values go to ``truth``.

        ``seed`` defaults to the batch seed. The noise of each channel has its own random stream, derived from the
        seed and the channel name, so it does not change when sensors are added or removed for other channels.
        """
        if result.truth:
            raise ValueError("result already carries measurement noise; apply noise to the noise-free result")
        seed = result.seed if seed is None else seed
        if seed is None:
            raise ValueError("the result has no seed; pass seed=")
        data = dict(result.data)
        truth: dict[str, np.ndarray] = {}
        for name, sensor in {**self.online, **self.lab}.items():
            if name not in data:
                continue
            truth[name] = data[name]
            data[name] = sensor.measure(data[name], result.time, _stream(seed, name))
        if {"Fg", "O2", "CO2outgas"} & truth.keys():
            for name in DERIVED_CHANNELS:
                truth[name] = data[name]
            data["OUR"], data["CER"] = off_gas_rates(data["Fg"], data["O2"], data["CO2outgas"])
        metadata = {**result.metadata, "measurement_noise": self, "noise_seed": seed}
        return replace(result, data=data, truth=truth, metadata=metadata)

    def __repr__(self) -> str:
        return f"MeasurementNoise(online={sorted(self.online)}, lab={sorted(self.lab)})"


def _stream(seed: int, name: str) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence(seed, spawn_key=(_NOISE_KEY, zlib.crc32(name.encode()))))


__all__ = ["DERIVED_CHANNELS", "MeasurementNoise", "Sensor"]
