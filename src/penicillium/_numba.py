"""Numba-compiled model right-hand side (optional: the ``fast`` extra, or ``pip install numba``).

The compiled function is built from the same source as the pure-Python one (``model.rhs_into``). Compilation
happens on first use and is cached on disk, so later processes start quickly.
"""

from __future__ import annotations

import numpy as np

try:
    import numba
except ImportError:  # pragma: no cover - exercised when numba is absent
    numba = None

from .model import N_STATES, rhs_into

AVAILABLE = numba is not None

if AVAILABLE:
    _rhs_into_nb = numba.njit(cache=True)(rhs_into)

    @numba.njit(cache=True)
    def rhs(t: float, y: np.ndarray, par: np.ndarray) -> np.ndarray:
        dy = np.empty(N_STATES)
        _rhs_into_nb(t, y, par, dy)
        return dy

else:  # pragma: no cover
    rhs = None
