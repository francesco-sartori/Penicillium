# Differentiable model (JAX)

Install the `jax` extra: `pip install "penicillium[jax]"`.

`penicillium.jax_model` is the IndPenSim model as a jit-compiled, differentiable JAX function. It is generated
from the same source as the Python and Numba backends (so it cannot drift from them) and agrees with them to
~1e-9 relative.

```python
from penicillium import jax_model

dy = jax_model.rhs(t, y, par)  # d(state)/dt, shape (33,)
A = jax_model.state_jacobian(t, y, par)  # exact d(dy/dt)/d(state), (33, 33)
B = jax_model.parameter_jacobian(t, y, par)  # exact d(dy/dt)/d(inputs and parameters), (33, 31)
```

`y` follows `model.STATE_NAMES` (pH as H+ concentration); `par` follows `model.PARAM_NAMES`: kinetic parameters,
the inputs `Fs`, `Fg`, `Fc`, `Fb`, `Fpaa`... and the disturbance values. `jax.vmap` evaluates many states at once.

Uses:

- **Linearisation for MPC and extended Kalman filters:** `A` and `B` at the current operating point.
- **Parameter sensitivity and estimation:** derivatives with respect to `mu_p`, `mux_max`, `alpha_kla`...
- **Gradients through simulation**, with any JAX integrator. With [diffrax](https://docs.kidger.site/diffrax/):

```python
import diffrax
import jax


def penicillin_after(par, y0, t0=100.0, t1=100.2):
    term = diffrax.ODETerm(lambda t, y, p: jax_model.rhs(t, y, p))
    sol = diffrax.diffeqsolve(
        term,
        diffrax.Kvaerno5(),
        t0,
        t1,
        0.001,
        y0,
        args=par,
        stepsize_controller=diffrax.PIDController(rtol=1e-8, atol=1e-10),
    )
    return sol.ys[-1][3]


dP_dpar = jax.grad(penicillin_after)(par, y0)  # e.g. dP_dpar[6]: effect of the sugar feed rate
```

This gradient matches finite differences of the LSODA solution to 1e-7 (`tests/test_jax_model.py`). The
controllers, recipe logic and discrete events of a whole batch (`Simulator`) stay in Python; differentiating a
complete batch means writing the control loop in JAX around `rhs`.

Importing the module switches JAX to 64-bit mode (`jax_enable_x64`), which the model needs.
