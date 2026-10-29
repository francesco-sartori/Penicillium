import math

import numpy as np

from penicillium import raman
from penicillium.model import N_PARAMS, N_STATES, PARAM_NAMES, STATE_NAMES, rhs


def _state(ph=6.5):
    y = [0.0] * N_STATES
    y[0], y[1], y[2], y[3], y[4], y[5] = 1.0, 15.0, 0.2, 0.0, 58000, 62000
    y[6] = 10**-ph
    y[7] = 297.0
    y[9] = 4.0
    y[11], y[12] = 0.5 / 3, 1.0 / 3
    y[27], y[29], y[30] = 0.038, 1400, 1700
    return y


def _params():
    par = [0.0] * N_PARAMS
    par[:5] = [0.041, 0.41, 85, 150000, 530000]
    named = dict(inhib_flag=2, Fs=8, Fg=30, RPM=100, Fc=10, Fh=1e-4, Fb=1, Fa=0, step1=0.005, Fw=0,
                 pressure=0.6, viscosity=4, F_discharge=0, Fpaa=5, Foil=22)  # fmt: skip
    for name, value in named.items():
        par[PARAM_NAMES.index(name)] = value
    return par


def test_layout():
    assert N_STATES == 33 and len(STATE_NAMES) == 33
    assert N_PARAMS == 31


def test_rhs_is_finite():
    dy = rhs(0.0, _state(), _params())
    assert len(dy) == N_STATES
    assert all(math.isfinite(v) for v in dy)
    # Volume balance: 10 L/h more sugar feed gives 10 L/h more volume.
    par = _params()
    par[PARAM_NAMES.index("Fs")] += 10
    np.testing.assert_allclose(rhs(0.0, _state(), par)[4] - dy[4], 10)


def test_rhs_does_not_modify_state_when_alkaline():
    # The pH > 7 branch must work on a local copy; the solver's state is never modified.
    y = np.array(_state(ph=7.5))
    before = y.copy()
    rhs(0.0, y, _params())
    np.testing.assert_array_equal(y, before)


def test_smooth_matches_moving_average_in_the_middle():
    x = np.arange(100, dtype=float) ** 1.5
    s = raman.smooth(x, 25)
    assert s.shape == x.shape
    np.testing.assert_allclose(s[50], x[38:63].mean())
    assert s[0] == x[0]  # window of 1 at the edges, like MATLAB smooth
    assert s[-1] == x[-1]


def test_spectrum_shape_and_noise_switch():
    args = (100, 1.0, 10.0, 50.0, 0.1, 1000.0)
    clean = raman.spectrum(*args, rng=None)
    assert clean.shape == (raman.N_WAVENUMBERS,)
    np.testing.assert_array_equal(clean, raman.spectrum(*args, rng=None))
    noisy = raman.spectrum(*args, rng=np.random.default_rng(0))
    assert not np.allclose(clean, noisy)
    # More penicillin, more signal under the penicillin peaks.
    more_p = raman.spectrum(100, 2.0, 10.0, 50.0, 0.1, 1000.0, rng=None)
    assert (more_p - clean).max() > 0


def test_paa_pls_prediction_tracks_paa_on_held_out_batch():
    import numpy as np

    from penicillium import RamanMode, SimulationConfig, Simulator

    r = Simulator(config=SimulationConfig(raman_mode=RamanMode.PAT_CONTROL, batch_length_h=60.0)).run(seed=4)
    pred, paa = r["PAA_pred"], r["PAA"]
    assert np.isnan(pred[:9]).all() and np.isfinite(pred[30:-1]).all()
    # pred[j] uses the spectrum of sample j (one sample late) and is a 3-sample average, as in IndPenSim.
    err = pred[30:-1] - paa[30:-1]
    assert np.sqrt(np.mean(err**2)) < 60  # mg/L, PAA ~1200
    off = Simulator(config=SimulationConfig(batch_length_h=4.0)).run(seed=4)
    assert np.isnan(off["PAA_pred"]).all()  # only computed under PAT control
