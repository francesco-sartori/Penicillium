"""Random number helpers accepting both ``numpy.random.Generator`` and the legacy ``RandomState``."""

from __future__ import annotations

from typing import Union

import numpy as np

RNG = Union[np.random.Generator, np.random.RandomState]  # noqa: UP007 (keeps 3.10 runtime alias simple)


def randint(rng: RNG, low: int, high: int, size: int | None = None):
    """Integers in ``[low, high)``."""
    if isinstance(rng, np.random.Generator):
        return rng.integers(low, high, size=size)
    if size is None:
        return rng.randint(low, high)
    return rng.randint(low, high, size=(size, 1))[:, 0]
