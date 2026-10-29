import numpy as np
import pandas as pd
import pytest

from penicillium import Fault, RamanMode, SimulationConfig, scenarios


@pytest.fixture(scope="module")
def short_fault_campaign():
    cfg = SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=110.0)
    return scenarios.fault_campaign(
        n_normal=2, n_per_fault=1, faults=(Fault.AERATION, Fault.BASE_FLOW), seed=3, config=cfg, n_jobs=1
    )


def test_fault_campaign_is_tidy_and_labelled(short_fault_campaign):
    camp = short_fault_campaign
    assert list(camp.batches["fault_name"]) == ["NONE", "NONE", "AERATION", "BASE_FLOW"]
    assert len(camp.samples) == 4 * 550
    assert set(camp.samples.columns[:5]) == {"batch_id", "time_h", "kind", "fault", "fault_active"}
    aeration = camp.samples[camp.samples.batch_id == 3]
    active = aeration.loc[aeration.fault_active == 1, "time_h"]
    assert active.min() == pytest.approx(20.0) and active.max() == pytest.approx(110.0)  # samples 100-120, 500-550
    assert camp.batches.loc[2, "fault_onset_h"] == pytest.approx(20.0)
    assert np.isnan(camp.batches.loc[0, "fault_onset_h"])
    assert camp.samples.loc[camp.samples.batch_id <= 2, "fault_active"].sum() == 0
    assert set(camp.online().columns) >= {"T", "pH", "fault_active"} and "a0" not in camp.online().columns


def test_lab_table_has_delays(short_fault_campaign):
    lab = short_fault_campaign.lab
    assert set(lab.columns) >= {"batch_id", "sample_time_h", "available_time_h", "P", "X"}
    np.testing.assert_allclose(lab["available_time_h"] - lab["sample_time_h"], 0.8)
    assert (lab.groupby("batch_id").size() > 5).all()


def test_split_is_by_batch_and_stratified(short_fault_campaign):
    train, test = short_fault_campaign.split(test_fraction=0.5, seed=0)
    assert set(train).isdisjoint(test) and sorted(train + test) == [1, 2, 3, 4]
    assert len([b for b in test if b <= 2]) == 1  # one of the two normal batches


def test_campaigns_are_reproducible(short_fault_campaign, tmp_path):
    cfg = SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=110.0)
    again = scenarios.fault_campaign(
        n_normal=2, n_per_fault=1, faults=(Fault.AERATION, Fault.BASE_FLOW), seed=3, config=cfg, n_jobs=1
    )
    pd.testing.assert_frame_equal(again.samples, short_fault_campaign.samples)
    out = short_fault_campaign.save(tmp_path / "camp")
    assert (out / "samples.parquet").exists() and (out / "campaign.json").exists()


def test_variable_lengths_like_indpensim():
    lengths = scenarios.variable_batch_lengths(2000, seed=1)
    assert np.mean(lengths) == pytest.approx(230, abs=2) and np.std(lengths) == pytest.approx(25, abs=2)
    assert all(v == round(v) for v in lengths)


@pytest.mark.slow
def test_soft_sensor_and_goldrick_structure():
    camp = scenarios.soft_sensor_campaign(n_batches=2, seed=1, config=SimulationConfig(batch_length_h=20.0), n_jobs=2)
    assert camp.raman[1].shape == (100, 2200)
    g = scenarios.goldrick2019_campaign(seed=0, n_per_strategy=1, n_faults=2, variable_length=False, n_jobs=4)
    assert list(g.batches["kind"]) == ["recipe", "operator", "apc", "fault", "fault"]
    assert list(g.batches["fault_name"][-2:]) == ["AERATION", "PRESSURE"]
