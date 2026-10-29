"""Raman spectrum simulation (IndPenSim ``Raman_Sim.m``) and the PAA PLS soft sensor."""

from __future__ import annotations

import numpy as np
from scipy.signal import lfilter, savgol_filter

from ._paa_pls import COEF, INTERCEPT
from ._raman_reference import RAMAN_SPECTRA, RAMAN_WAVENUMBER
from .constants import NUM_STEPS
from .rng import RNG, randint

#: Wavenumbers in cm^-1, descending (2400 to 201), one per spectrum point.
WAVENUMBER = np.asarray(RAMAN_WAVENUMBER, dtype=float)
N_WAVENUMBERS = WAVENUMBER.size
#: Reference (starting) spectrum every simulated spectrum is built on, a.u., ordered like ``WAVENUMBER``.
REFERENCE_SPECTRUM = np.asarray(RAMAN_SPECTRA, dtype=float)

# Baseline drift shape, as in IndPenSim.
_SHIFT = np.exp(np.arange(1, N_WAVENUMBERS + 1) / 1100) - 0.5


def _peak(start: int, half_width: int, height: float, decay: float) -> np.ndarray:
    """Gaussian ``height * exp(-decay * j^2)``, ``j = -half_width..half_width``, placed from index ``start``."""
    out = np.zeros(N_WAVENUMBERS)
    out[start : start + 2 * half_width + 1] = height * np.exp(-decay * np.arange(-half_width, half_width + 1) ** 2)
    return out


#: Normalised Gaussian peak shapes of the components, ordered like ``WAVENUMBER``.
PEAK_SHAPES = {
    "substrate": (
        _peak(78, 140, 0.011398350868612364, 0.0004081632653061224)
        + _peak(598, 40, 0.009277727451196111, 0.005)
        + _peak(852, 200, 0.007978845608028654, 0.0002)
    ),
    "PAA": _peak(298, 120, 0.01329807601338109, 0.0005555555555555556)
    + _peak(808, 30, 0.01237030326826148, 0.008888888888888889),
    "penicillin": _peak(299, 900, 0.02659615202676218, 0.0022222222222222222)
    + _peak(679, 120, 0.02659615202676218, 0.0022222222222222222),
}


def smooth(y: np.ndarray, width: int) -> np.ndarray:
    """Centred moving average with shrinking windows at the edges, like MATLAB ``smooth``."""
    n = len(y)
    c = lfilter(np.ones(width) / width, [1], y, axis=0)
    cbegin = np.cumsum(y[0 : width - 2])
    cbegin = cbegin[::2] / np.arange(1, width - 1, 2)
    cend = np.cumsum(y[n - width + 2 : n][::-1])
    cend = cend[::-2] / np.arange(1, width - 1)[::-2]
    return np.concatenate([cbegin, c[width - 1 :], cend])


def baseline_noise(rng: RNG) -> np.ndarray:
    """Random-walk baseline noise added to each spectrum (smoothed cumulative sum of +-50 steps, x10)."""
    steps = 50 * randint(rng, -1, 2, N_WAVENUMBERS)
    return 10 * smooth(np.cumsum(steps), 25)


def spectrum(
    k: int,
    penicillin: float,
    biomass: float,
    viscosity: float,
    substrate: float,
    paa: float,
    rng: RNG | None,
    n_steps: int = NUM_STEPS,
) -> np.ndarray:
    """Raman intensity at sample ``k`` (1-based) for the given broth composition.

    ``rng=None`` disables the random baseline noise.
    ``n_steps`` is the batch length in samples (the baseline drifts with the fraction of the batch elapsed).
    """
    # Baseline: drift with biomass, penicillin, viscosity and batch progress (coefficients from IndPenSim).
    a = -0.000178143846614472
    b = 1.05644816081515
    c = -0.00681439987249108
    d = -0.02
    increase = a * (biomass / 40) + b * (penicillin / 40) + c * (viscosity / 100) + d * (k / n_steps)
    spectra = increase * 370000 * _SHIFT + REFERENCE_SPECTRUM

    if rng is not None:
        spectra = spectra + baseline_noise(rng)

    # Component peaks: glucose saturates (S / (0.005 + S)), PAA and penicillin are linear in concentration.
    term_glucose = PEAK_SHAPES["substrate"] * 1714.2857142857142 * substrate / (0.005 + substrate)
    term_paa = PEAK_SHAPES["PAA"] * 1700 * paa
    term_penicillin = PEAK_SHAPES["penicillin"] * 100000 * penicillin
    return spectra + term_glucose + term_paa + term_penicillin


#: Spectrum points used by IndPenSim's PAA PLS model (MATLAB 350:500 and 800:860 of the derivative).
_PLS_REGIONS = np.r_[349:500, 799:860]
_PLS_COEF = np.asarray(COEF)


def paa_pls_features(spectra: np.ndarray) -> np.ndarray:
    """Features of IndPenSim's PAA PLS model (``Substrate_prediction.m``) for one spectrum or a stack of them.

    Savitzky-Golay smoothing (order 2, window 5) along the wavenumber axis, first difference, then the points of
    the PAA peaks. Spectra ordered like ``WAVENUMBER``.
    """
    smoothed = savgol_filter(np.asarray(spectra, dtype=float), 5, 2, axis=-1)
    return np.diff(smoothed, axis=-1)[..., _PLS_REGIONS]


def paa_pls_predict(spectrum: np.ndarray) -> float:
    """PAA [mg/L] predicted from one spectrum by Penicillium's PLS model (see ``validation/train_paa_pls.py``)."""
    return float(paa_pls_features(spectrum) @ _PLS_COEF + INTERCEPT)
