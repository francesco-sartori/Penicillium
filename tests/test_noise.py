import numpy as np
import pytest

from penicillium import MeasurementNoise, RamanMode, Sensor, SimulationConfig, Simulator, scenarios
from penicillium.cli import main
from penicillium.result import LAB_CHANNELS
from penicillium.simulator import off_gas_rates


@pytest.fixture(scope="module")
def batch():
    return Simulator(config=SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=60.0)).run(seed=4)


def test_none_and_zero_noise_change_nothing(batch):
    exact = MeasurementNoise.none().apply(batch)
    assert exact.truth == {}
    for name, values in batch.data.items():
        np.testing.assert_array_equal(exact[name], values)
    flat = MeasurementNoise(online={"Fs": Sensor()}).apply(batch)  # all errors zero, no quantisation
    np.testing.assert_array_equal(flat["Fs"], batch["Fs"])


def test_apply_leaves_the_simulated_result_untouched(batch):
    before = {k: v.copy() for k, v in batch.data.items()}
    noisy = MeasurementNoise.typical().apply(batch)
    for name, values in before.items():
        np.testing.assert_array_equal(batch[name], values)
        np.testing.assert_array_equal(noisy.truth.get(name, noisy[name]), values)
    assert not np.array_equal(noisy["pH"], batch["pH"])
    np.testing.assert_array_equal(noisy["S"], batch["S"])  # hidden states are not measured
    with pytest.raises(ValueError, match="already"):
        MeasurementNoise.typical().apply(noisy)


def test_noise_is_reproducible_and_per_channel(batch):
    a = MeasurementNoise.typical().apply(batch)
    b = MeasurementNoise.typical().apply(batch)
    np.testing.assert_array_equal(a["DO2"], b["DO2"])
    c = MeasurementNoise.typical().apply(batch, seed=5)
    assert not np.array_equal(a["DO2"], c["DO2"])
    # Removing another channel's sensor, or changing this one's sd, keeps this channel's random draws.
    d = MeasurementNoise.typical().with_(T=None, Fs=None).apply(batch)
    np.testing.assert_array_equal(a["DO2"], d["DO2"])
    assert "T" not in d.truth
    np.testing.assert_array_equal(d["T"], batch["T"])


def test_white_noise_statistics(batch):
    noise = MeasurementNoise(online={"T": Sensor(sd=0.05), "Fs": Sensor(rel=0.02)})
    noisy = noise.apply(batch)
    assert np.std(noisy["T"] - batch["T"]) == pytest.approx(0.05, rel=0.15)
    fed = batch["Fs"] > 1
    rel_err = noisy["Fs"][fed] / batch["Fs"][fed] - 1
    assert np.std(rel_err) == pytest.approx(0.02, rel=0.15) and abs(np.mean(rel_err)) < 0.004


def test_offset_is_constant_and_drift_wanders(batch):
    offset = MeasurementNoise(online={"pH": Sensor(offset_sd=0.05)}).apply(batch)
    err = offset["pH"] - batch["pH"]
    np.testing.assert_allclose(err, err[0], atol=1e-12)
    assert err[0] != 0
    drift = MeasurementNoise(online={"pH": Sensor(drift_sd=0.01)}).apply(batch)
    err = drift["pH"] - batch["pH"]
    assert abs(err[0]) < abs(err).max()  # starts near zero, wanders
    assert np.std(np.diff(err)) == pytest.approx(0.01 * np.sqrt(0.2), rel=0.15)


def test_quantisation_and_bounds(batch):
    noisy = MeasurementNoise(online={"pH": Sensor(sd=0.02, resolution=0.01), "Fa": Sensor(sd=5.0)}).apply(batch)
    np.testing.assert_allclose(noisy["pH"] * 100, np.round(noisy["pH"] * 100), atol=1e-9)
    assert (noisy["Fa"] >= 0).all()  # flows never negative
    discharge = MeasurementNoise(online={"discharge": Sensor(rel=0.05, lo=None, hi=0.0)}).apply(batch)
    assert (discharge["discharge"] <= 0).all()  # negative while draining


def test_typical_noises_measurements_not_set_points(batch):
    noisy = MeasurementNoise.typical().apply(batch)
    for name in ("Fs", "Foil", "Fg", "pressure", "discharge", "Fw", "Fpaa", "RPM"):
        np.testing.assert_array_equal(noisy[name], batch[name])
    assert {"Fa", "Fb", "Fc", "Fh", "DO2", "O2", "V", "Wt", "pH", "T", "CO2outgas"} <= noisy.truth.keys()
    for name in ("pH", "T"):  # controlled: a bias would act through the controller, not on the record
        sensor = MeasurementNoise.typical().online[name]
        assert sensor.offset_sd == 0 and sensor.drift_sd == 0
        assert np.abs(noisy[name] - batch[name]).max() < 5 * sensor.sd + sensor.resolution


def test_off_gas_rates_follow_the_measured_gas(batch):
    noisy = MeasurementNoise(online={"O2": Sensor(sd=1e-3)}).apply(batch)
    our, cer = off_gas_rates(noisy["Fg"], noisy["O2"], noisy["CO2outgas"])
    np.testing.assert_array_equal(noisy["OUR"], our)
    np.testing.assert_array_equal(noisy["CER"], cer)
    np.testing.assert_allclose(off_gas_rates(batch["Fg"], batch["O2"], batch["CO2outgas"])[0], batch["OUR"])
    assert "OUR" in noisy.truth and not np.array_equal(noisy["OUR"], batch["OUR"])
    with pytest.raises(ValueError, match="computed"):
        MeasurementNoise(online={"OUR": Sensor(sd=1.0)})


def test_lab_noise_keeps_the_analysis_schedule(batch):
    noisy = MeasurementNoise.typical().apply(batch)
    for name in LAB_CHANNELS:
        np.testing.assert_array_equal(np.isnan(noisy[name]), np.isnan(batch[name]))
    reported = ~np.isnan(batch["P_offline"])
    assert not np.array_equal(noisy["P_offline"][reported], batch["P_offline"][reported])


def test_invalid_specs():
    with pytest.raises(ValueError, match="online"):
        MeasurementNoise(online={"P_offline": Sensor(rel=0.1)})
    with pytest.raises(ValueError, match="lab"):
        MeasurementNoise(lab={"P": Sensor(rel=0.1)})
    with pytest.raises(ValueError, match=">= 0"):
        Sensor(sd=-1)
    assert MeasurementNoise.typical().scaled(0).online["pH"].sd == 0


def test_campaign_with_noise_keeps_truth():
    cfg = SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=40.0)
    clean = scenarios.fault_campaign(n_normal=2, n_per_fault=0, seed=2, config=cfg, n_jobs=1)
    noisy = scenarios.fault_campaign(
        n_normal=2, n_per_fault=0, seed=2, config=cfg, n_jobs=1, measurement_noise=MeasurementNoise.typical()
    )
    np.testing.assert_array_equal(noisy.samples["pH_true"], clean.samples["pH"])
    assert not np.array_equal(noisy.samples["pH"], clean.samples["pH"])
    np.testing.assert_array_equal(noisy.lab["P_true"], clean.lab["P"])
    assert not np.array_equal(noisy.lab["P"], clean.lab["P"])
    assert "pH_true" not in noisy.online().columns


def test_cli_noise_flag(tmp_path):
    out = tmp_path / "data"
    assert main(["generate", "--n-batches", "1", "--batch-length", "10", "--noise", "typical",
                 "--format", "csv", "--out", str(out)]) == 0  # fmt: skip
    import pandas as pd

    df = pd.read_csv(next(out.glob("batch_*.csv")))
    assert {"pH", "pH_true", "OUR_true"} <= set(df.columns)
    assert not np.array_equal(df["pH"], df["pH_true"])
