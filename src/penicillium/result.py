"""Batch results and channel metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    import pandas as pd

#: name -> (description, unit), names and units as in IndPenSim.
CHANNELS: dict[str, tuple[str, str]] = {
    # Manipulated variables
    "Fs": ("Sugar feed rate", "L/h"),
    "Foil": ("Soybean oil feed rate", "L/h"),
    "Fg": ("Aeration rate", "L/h"),
    "pressure": ("Vessel back pressure", "bar"),
    "discharge": ("Broth discharge rate (negative when discharging)", "L/h"),
    "Fw": ("Water for injection/dilution", "L/h"),
    "Fpaa": ("Phenylacetic acid flow rate", "L/h"),
    "Fa": ("Acid flow rate", "L/h"),
    "Fb": ("Base flow rate", "L/h"),
    "Fc": ("Cooling water flow rate", "L/h"),
    "Fh": ("Heating water flow rate", "L/h"),
    "RPM": ("Agitator speed", "rpm"),
    # States
    "S": ("Substrate concentration", "g/L"),
    "DO2": ("Dissolved oxygen concentration", "mg/L"),
    "O2": ("Oxygen fraction in off-gas", "-"),
    "P": ("Penicillin concentration", "g/L"),
    "V": ("Volume", "L"),
    "Wt": ("Vessel weight", "kg"),
    "pH": ("pH", "-"),
    "T": ("Temperature", "K"),
    "Q": ("Generated heat", "kJ"),
    "Viscosity": ("Viscosity", "cP"),
    "Culture_age": ("Culture age (integral of biomass)", "g h/L"),
    "a0": ("Growing biomass regions", "g/L"),
    "a1": ("Non-growing biomass regions", "g/L"),
    "a3": ("Degenerated biomass regions", "g/L"),
    "a4": ("Autolysed biomass regions", "g/L"),
    **{f"n{i}": (f"Vacuole number density, size class {i}", "-") for i in range(10)},
    "nm": ("Vacuole number density, maximum size class", "-"),
    "phi0": ("Mean vacuole volume", "-"),
    "CO2outgas": ("CO2 in off-gas", "%"),
    "CO2_d": ("Dissolved CO2", "mg/L"),
    "PAA": ("Phenylacetic acid concentration", "mg/L"),
    "NH3": ("Nitrogen concentration", "mg/L"),
    "mu_P_calc": ("Penicillin specific production rate, integrated over the sample", "-"),
    "mu_X_calc": ("Biomass specific growth rate, integrated over the sample", "-"),
    # Derived
    "X": ("Biomass concentration", "g/L"),
    "OUR": ("Oxygen uptake rate", "g/min"),
    "CER": ("Carbon evolution rate", "g/h"),
    "Fault_ref": ("Fault active (1) or not (0)", "-"),
    "PAA_pred": ("PAA predicted from the Raman spectrum by PLS (PAT control only, else NaN)", "mg/L"),
    # Offline measurements (NaN when not sampled)
    "NH3_offline": ("Offline nitrogen concentration", "mg/L"),
    "Viscosity_offline": ("Offline viscosity", "cP"),
    "PAA_offline": ("Offline PAA concentration", "mg/L"),
    "P_offline": ("Offline penicillin concentration", "g/L"),
    "X_offline": ("Offline biomass concentration", "g/L"),
}
CHANNEL_NAMES: tuple[str, ...] = tuple(CHANNELS)

#: Off-line lab measurements (NaN except when an analysis result is reported).
LAB_CHANNELS: tuple[str, ...] = ("P_offline", "X_offline", "PAA_offline", "NH3_offline", "Viscosity_offline")


@dataclass
class BatchResult:
    """Simulated batch.

    Attributes:
        time: sample times in hours (end of each 12-minute sample).
        data: channel name -> values, one per sample (see ``CHANNELS``).
        raman: Raman intensities, shape ``(n_samples, n_wavenumbers)``; zeros for the first 10 samples;
            ``None`` if Raman simulation was off.
        raman_wavenumber: wavenumbers in cm^-1 matching the columns of ``raman`` (descending).
        total_yield: harvested penicillin over the batch (sum of step rewards), kg.
        truth: noise-free values of the channels that ``MeasurementNoise.apply`` replaced by measurements; empty
            for a simulated (noise-free) result.
    """

    time: np.ndarray
    data: dict[str, np.ndarray]
    raman: np.ndarray | None
    raman_wavenumber: np.ndarray
    total_yield: float
    seed: int | None = None
    config: Any = None
    solver: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    truth: dict[str, np.ndarray] = field(default_factory=dict)

    def __getitem__(self, name: str) -> np.ndarray:
        return self.data[name]

    def __len__(self) -> int:
        return len(self.time)

    def to_pandas(self, channels: list[str] | None = None) -> pd.DataFrame:
        """Time-indexed dataframe (index ``time_h``) of the selected channels (default: all)."""
        import pandas as pd

        names = list(self.data) if channels is None else channels
        return pd.DataFrame({name: self.data[name] for name in names}, index=pd.Index(self.time, name="time_h"))

    def raman_to_pandas(self) -> pd.DataFrame:
        """Raman spectra as a dataframe: rows are samples, columns ascending wavenumbers."""
        import pandas as pd

        if self.raman is None:
            raise ValueError("Raman simulation was disabled for this batch")
        return pd.DataFrame(
            self.raman[:, ::-1], index=pd.Index(self.time, name="time_h"), columns=self.raman_wavenumber[::-1]
        )
