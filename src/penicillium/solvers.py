"""ODE integration backends for one sampling interval.

Each backend integrates ``model.rhs`` from ``t0`` to ``t1`` with constant inputs and returns the state at
the end of the interval, plus the time it actually reached.

* ``"lsoda"`` (default): ``scipy.integrate.odeint`` (LSODA, switches automatically between stiff and
  non-stiff methods) over exactly ``[t0, t1]``, with ``rtol=1e-5``, ``atol=1e-7`` and maximum step ``h/20``
  (0.01 h). IndPenSim V2.01 calls ``ode15s`` with MATLAB's default options (``RelTol=1e-3``, ``AbsTol=1e-6``); the
  tighter defaults here keep Penicillium's own solver error ~100x below MATLAB's (docs/solver_sensitivity.md).
* ``"bdf"``, ``"radau"``, ``"rk45"``: ``scipy.integrate.solve_ivp`` with the same defaults, for
  solver-sensitivity studies. ``"bdf"`` is the closest SciPy relative of MATLAB's ``ode15s``.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Sequence

import numpy as np
from scipy.integrate import ODEintWarning, odeint, solve_ivp

from .constants import STEP_IN_HOURS

RHS = Callable[[float, Sequence[float], Sequence[float]], list[float]]

SOLVERS = ("lsoda", "bdf", "radau", "rk45")

#: Default tolerances, tighter than IndPenSim V2.01's ``ode15s`` defaults (``RelTol=1e-3``, ``AbsTol=1e-6``).
DEFAULT_RTOL = 1e-5
DEFAULT_ATOL = 1e-7
DEFAULT_MAX_STEP = STEP_IN_HOURS / 20


class SolverError(RuntimeError):
    """The ODE solver failed on a sampling interval.

    Raised instead of returning a state: after a failure the rows ``odeint`` returns are not defined by the
    solver, so the simulator stops at the last sample it computed (docs/quirks.md 1.4).
    """


def _odeint(rhs: RHS, y0, t_span, par, **kwargs) -> np.ndarray:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ODEintWarning)
            y, info = odeint(rhs, y0, t_span, args=(par,), tfirst=True, full_output=True, **kwargs)
    except (ArithmeticError, ValueError) as exc:  # overflow / log of a negative number inside the model
        raise SolverError(f"model evaluation failed on [{t_span[0]}, {t_span[-1]}]: {exc!r}") from exc
    if info["message"] != "Integration successful.":
        raise SolverError(f"odeint failed on [{t_span[0]}, {t_span[-1]}]: {info['message']}")
    return y


def integrate(
    rhs: RHS,
    y0: Sequence[float],
    t0: float,
    t1: float,
    par: Sequence[float],
    method: str = "lsoda",
    rtol: float | None = None,
    atol: float | None = None,
    max_step: float | None = None,
) -> tuple[np.ndarray, float]:
    """Integrate ``rhs`` over one interval and return ``(y_end, t_end)``."""
    rtol = DEFAULT_RTOL if rtol is None else rtol
    atol = DEFAULT_ATOL if atol is None else atol
    max_step = DEFAULT_MAX_STEP if max_step is None else max_step
    if method == "lsoda":
        y = _odeint(rhs, y0, [t0, t1], par, rtol=rtol, atol=atol, hmax=max_step)
        return y[-1], t1
    if method in ("rk45", "bdf", "radau"):
        try:
            sol = solve_ivp(
                rhs,
                (t0, t1),
                y0,
                method={"rk45": "RK45", "bdf": "BDF", "radau": "Radau"}[method],
                args=(par,),
                rtol=rtol,
                atol=atol,
                max_step=max_step,
            )
        except (ArithmeticError, ValueError) as exc:
            raise SolverError(f"model evaluation failed on [{t0}, {t1}]: {exc!r}") from exc
        if not sol.success:
            raise SolverError(f"solve_ivp ({method}) failed on [{t0}, {t1}]: {sol.message}")
        return sol.y[:, -1], t1
    raise ValueError(f"unknown solver {method!r}; choose one of {SOLVERS}")
