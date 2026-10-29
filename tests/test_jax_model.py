import numpy as np
import pytest

jax = pytest.importorskip("jax")

from penicillium import RamanMode, SimulationConfig, Simulator, model, solvers  # noqa: E402
from penicillium import simulator as simulator_module  # noqa: E402


@pytest.fixture(scope="module")
def states():
    """(t, y0, par) at the start of a few sampling intervals of a real batch (with a base-flow fault)."""
    captured = []
    original = simulator_module.integrate

    def spy(f, y0, t0, t1, par, *args):
        if round(t0 / 0.2) % 97 == 3:
            captured.append((float(t0), np.array(y0, float), np.array(par, float)))
        return original(f, y0, t0, t1, par, *args)

    simulator_module.integrate = spy
    try:
        Simulator(config=SimulationConfig(raman_mode=RamanMode.OFF, fault=4), backend="python").run(seed=5)
    finally:
        simulator_module.integrate = original
    return captured


def test_jax_rhs_matches_numpy_model(states):
    from penicillium import jax_model

    assert len(states) >= 10
    for t, y, par in states:
        a = np.array(model.rhs(t, y, par))
        b = np.asarray(jax_model.rhs(t, y, par))
        np.testing.assert_allclose(b, a, rtol=1e-8, atol=1e-12 * np.abs(a).max())


@pytest.mark.parametrize("inhibition", [0, 1])
def test_jax_rhs_matches_for_other_inhibition_flags(states, inhibition):
    from penicillium import jax_model

    t, y, par = states[5]
    par = par.copy()
    par[5] = inhibition
    np.testing.assert_allclose(np.asarray(jax_model.rhs(t, y, par)), model.rhs(t, y, par), rtol=1e-8, atol=1e-12)


def test_jacobians_match_finite_differences(states):
    from penicillium import jax_model

    t, y, par = states[len(states) // 2]
    J = np.asarray(jax_model.state_jacobian(t, y, par))
    assert J.shape == (33, 33) and np.isfinite(J).all()
    for i in (0, 1, 3, 7, 11, 29):  # S, DO2, P, T, a0, PAA
        h = 1e-6 * max(1e-3, abs(y[i]))
        yp, ym = y.copy(), y.copy()
        yp[i] += h
        ym[i] -= h
        fd = (np.array(model.rhs(t, yp, par)) - np.array(model.rhs(t, ym, par))) / (2 * h)
        np.testing.assert_allclose(J[:, i], fd, rtol=1e-4, atol=1e-6 * np.abs(fd).max(), err_msg=f"column {i}")
    S = np.asarray(jax_model.parameter_jacobian(t, y, par))
    assert S.shape == (33, 31)
    assert S[0, 6] > 0  # more sugar feed, faster substrate increase


@pytest.mark.slow
def test_gradient_through_stiff_integration(states):
    diffrax = pytest.importorskip("diffrax")
    import jax.numpy as jnp

    from penicillium import jax_model

    t0, y0, par = states[4]

    def penicillin_after_interval(p):
        term = diffrax.ODETerm(lambda t, y, args: jax_model.rhs(t, y, args))
        sol = diffrax.diffeqsolve(
            term, diffrax.Kvaerno5(), t0, t0 + 0.2, 0.001, jnp.asarray(y0), args=p,
            stepsize_controller=diffrax.PIDController(rtol=1e-8, atol=1e-10), max_steps=10_000,
        )  # fmt: skip
        return sol.ys[-1][3]

    grad = float(jax.grad(penicillin_after_interval)(jnp.asarray(par))[6])  # d P / d Fs
    eps = 1e-3
    hi, lo = par.copy(), par.copy()
    hi[6] += eps
    lo[6] -= eps
    p_hi = solvers.integrate(model.rhs, y0, t0, t0 + 0.2, hi, rtol=1e-11, atol=1e-13)[0][3]
    p_lo = solvers.integrate(model.rhs, y0, t0, t0 + 0.2, lo, rtol=1e-11, atol=1e-13)[0][3]
    assert grad == pytest.approx((p_hi - p_lo) / (2 * eps), rel=1e-4)
