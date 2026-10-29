"""Recipes: piecewise-constant setpoint profiles for the operator-controlled inputs.

``INDPENSIM_PROFILES`` are the sequential batch control tables of IndPenSim (``fctrl_indpensim.m``), with
times converted from samples (12 min) to hours; they cover batches up to 350 h.

How a ``(time, value)`` setpoint is read matters:

* ``hold="until"`` (default, as in IndPenSim): the value applies up to and including ``time``. IndPenSim
  writes ``if k <= Recipe(SQ), u = Recipe_sp(SQ)``.
* ``hold="from"``: the value applies from ``time`` onwards. Applied to the IndPenSim
  tables this shifts every profile by one segment; with the default recipe the broth discharge is then on
  for 26 h out of every 28 h instead of 2 h pulses, and the vessel is nearly drained by ~135 h.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

#: Recipe-driven inputs: sugar feed, soybean oil feed, aeration,
#: back pressure, broth discharge, water injection, phenylacetic acid feed. Units in ``CHANNELS``.
INPUTS: tuple[str, ...] = ("Fs", "Foil", "Fg", "pressure", "discharge", "Fw", "Fpaa")

#: IndPenSim tables, e.g. ``Recipe_Fs = [15 60 ...]`` samples -> 3, 12, ... hours.
INDPENSIM_PROFILES: dict[str, list[tuple[float, float]]] = {
    "Fs": [
        (3, 8), (12, 15), (16, 30), (20, 75), (24, 150), (28, 30), (32, 37), (36, 43), (40, 47),
        (44, 51), (48, 57), (52, 61), (56, 65), (60, 72), (64, 76), (68, 80), (72, 84), (76, 90),
        (80, 116), (160, 90), (350, 80),
    ],
    "Foil": [
        (4, 22), (16, 30), (56, 35), (60, 34), (64, 33), (68, 32), (72, 31), (76, 30), (80, 29), (350, 23),
    ],
    "Fg": [(8, 30), (20, 42), (40, 55), (90, 60), (200, 75), (250, 65), (350, 60)],
    "pressure": [(12.5, 0.6), (25, 0.7), (30, 0.8), (40, 0.9), (100, 1.1), (150, 1), (200, 0.9), (350, 0.9)],
    "discharge": [
        (100, 0), (102, 4000), (130, 0), (132, 4000), (150, 0), (152, 4000), (170, 0), (172, 4000),
        (190, 0), (192, 4000), (210, 0), (212, 4000), (230, 0), (232, 4000), (250, 0), (252, 4000),
        (270, 0), (272, 4000), (350, 0),
    ],
    "Fw": [(50, 0), (75, 500), (150, 100), (160, 0), (170, 400), (200, 150), (250, 250), (270, 0), (350, 100)],
    "Fpaa": [(5, 5), (40, 0), (200, 10), (300, 4), (350, 0)],
}  # fmt: skip


@dataclass(frozen=True)
class Profile:
    """Piecewise-constant profile defined by ``(time_h, value)`` setpoints.

    With ``hold="until"`` the value at time ``t`` is that of the first setpoint with ``t <= time``; with
    ``hold="from"`` it is that of the last setpoint with ``time <= t``. Outside the setpoint range the
    first or last value applies.
    """

    setpoints: tuple[tuple[float, float], ...]
    hold: str = "until"
    _times: tuple[float, ...] = field(init=False, repr=False, compare=False)

    def __init__(self, setpoints: Iterable[tuple[float, float]], hold: str = "until"):
        if hold not in ("until", "from"):
            raise ValueError("hold must be 'until' or 'from'")
        pts = sorted((float(t), float(v)) for t, v in setpoints)
        if not pts:
            raise ValueError("a profile needs at least one setpoint")
        times = [t for t, _ in pts]
        if len(set(times)) != len(times):
            raise ValueError("duplicate setpoint times in profile")
        object.__setattr__(self, "setpoints", tuple(pts))
        object.__setattr__(self, "hold", hold)
        object.__setattr__(self, "_times", tuple(times))

    def value_at(self, time: float) -> float:
        if self.hold == "until":
            i = bisect.bisect_left(self._times, time)
            return self.setpoints[min(i, len(self.setpoints) - 1)][1]
        i = bisect.bisect_right(self._times, time) - 1
        return self.setpoints[max(i, 0)][1]


@dataclass(frozen=True)
class Recipe:
    """One profile per recipe-driven input (see ``INPUTS``)."""

    profiles: Mapping[str, Profile]

    def __post_init__(self) -> None:
        missing = set(INPUTS) - set(self.profiles)
        if missing:
            raise ValueError(f"recipe is missing profiles for: {sorted(missing)}")
        unknown = set(self.profiles) - set(INPUTS)
        if unknown:
            raise ValueError(f"unknown recipe inputs: {sorted(unknown)}")

    @classmethod
    def default(cls) -> Recipe:
        """The IndPenSim default recipe."""
        return cls.from_setpoints(INDPENSIM_PROFILES)

    @classmethod
    def from_setpoints(cls, setpoints: Mapping[str, Iterable[tuple[float, float]]], hold: str = "until") -> Recipe:
        """Build a recipe from ``{input: [(time_h, value), ...]}``."""
        return cls({name: Profile(pts, hold) for name, pts in setpoints.items()})

    def replace(self, **setpoints: Iterable[tuple[float, float]]) -> Recipe:
        """Return a copy with some profiles replaced, e.g. ``recipe.replace(Fs=[(0, 50)])``.

        New profiles use the ``hold`` convention of the profile they replace.
        """
        profiles = dict(self.profiles)
        profiles.update({name: Profile(pts, self.profiles[name].hold) for name, pts in setpoints.items()})
        return Recipe(profiles)

    def at(self, time: float) -> dict[str, float]:
        """Value of every input at ``time`` (hours)."""
        return {name: self.profiles[name].value_at(time) for name in INPUTS}


DEFAULT_PROFILES = INDPENSIM_PROFILES
