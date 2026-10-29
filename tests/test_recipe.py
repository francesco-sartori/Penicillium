import pytest

from penicillium import INPUTS, Profile, Recipe
from penicillium.recipe import DEFAULT_PROFILES


def test_profile_hold_until_is_indpensim_semantics():
    # IndPenSim: `if k <= Recipe(SQ), u = Recipe_sp(SQ)`
    p = Profile([(10, 1.0), (5, 0.5), (20, 2.0)])
    assert p.value_at(0) == 0.5
    assert p.value_at(5) == 0.5  # inclusive
    assert p.value_at(5.01) == 1.0
    assert p.value_at(10) == 1.0
    assert p.value_at(19.9) == 2.0
    assert p.value_at(1e6) == 2.0  # last value after the last setpoint


def test_profile_hold_from():
    p = Profile([(10, 1.0), (5, 0.5), (20, 2.0)], hold="from")
    assert p.value_at(0) == 0.5  # back-fill before first setpoint
    assert p.value_at(9.99) == 0.5
    assert p.value_at(10) == 1.0
    assert p.value_at(1e6) == 2.0


def test_profile_rejects_bad_input():
    with pytest.raises(ValueError):
        Profile([])
    with pytest.raises(ValueError):
        Profile([(1, 1), (1, 2)])
    with pytest.raises(ValueError):
        Profile([(1, 1)], hold="sometimes")


def test_default_discharge_is_a_2h_pulse_as_in_indpensim():
    # fctrl_indpensim.m: discharge 0 up to sample 500, 4000 L/h for samples 501-510, 0 up to 650, ...
    r = Recipe.default()
    at = lambda k: r.at(k * 12 / 60)["discharge"]  # noqa: E731
    assert at(500) == 0
    assert [at(k) for k in range(501, 511)] == [4000] * 10
    assert at(511) == 0
    assert at(650) == 0 and at(651) == 4000


def test_default_recipe_values():
    r = Recipe.default()
    assert set(r.at(0)) == set(INPUTS)
    assert r.at(3.0)["Fs"] == 8  # samples 1-15
    assert r.at(3.2)["Fs"] == 15
    assert r.at(24.0)["Fg"] == 55  # samples 101-200


def test_recipe_validation_and_replace():
    with pytest.raises(ValueError, match="missing"):
        Recipe.from_setpoints({"Fs": [(0, 1)]})
    with pytest.raises(ValueError, match="unknown"):
        Recipe.from_setpoints({**DEFAULT_PROFILES, "bogus": [(0, 1)]})
    r = Recipe.default().replace(Fs=[(0, 50)])
    assert r.at(100)["Fs"] == 50
    assert Recipe.default().at(100)["Fs"] == 90
    from_recipe = Recipe.from_setpoints(DEFAULT_PROFILES, hold="from").replace(Fs=[(0, 50)])
    assert from_recipe.profiles["Fs"].hold == "from"
