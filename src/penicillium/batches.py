"""Simulate many batches, in parallel processes.

    from penicillium import BatchSpec, SimulationConfig, simulate_batches

    specs = [BatchSpec(seed=s, config=SimulationConfig(prbs=True)) for s in range(1, 27)]
    results = simulate_batches(specs)  # one BatchResult per spec, in order

Works from notebooks and scripts (on Windows too: the worker function lives in this module). Each result
holds the Raman spectra when they are recorded (about 20 MB per 230 h batch), so use
``raman_mode=RamanMode.OFF`` for large campaigns that do not need them.
"""

from __future__ import annotations

import functools
import multiprocessing
import os
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

from .recipe import Recipe
from .result import BatchResult
from .simulator import SimulationConfig, Simulator


@dataclass(frozen=True)
class BatchSpec:
    """One batch to simulate."""

    seed: int
    config: SimulationConfig = field(default_factory=SimulationConfig)
    initial_conditions: dict[str, float] | None = None
    recipe: Recipe | None = None


def process_pool(n_jobs: int) -> ProcessPoolExecutor:
    """Worker processes started with ``spawn`` on every platform.

    ``fork`` (the Linux default before Python 3.14) copies the parent's threads' locks; with JAX or other
    multithreaded libraries imported this can deadlock the workers.
    """
    return ProcessPoolExecutor(n_jobs, mp_context=multiprocessing.get_context("spawn"))


def simulate(spec: BatchSpec, keep_raman: bool = True) -> BatchResult:
    """Simulate one batch (``keep_raman=False`` drops the spectra from the result)."""
    result = Simulator(recipe=spec.recipe, config=spec.config).run(
        seed=spec.seed, initial_conditions=spec.initial_conditions
    )
    if not keep_raman:
        result.raman = None
    return result


def simulate_batches(
    specs: Iterable[BatchSpec],
    n_jobs: int | None = None,
    progress: Callable[[int, int, BatchResult], None] | None = None,
    keep_raman: bool = True,
) -> list[BatchResult]:
    """Simulate ``specs`` and return the results in the same order.

    Args:
        specs: batches to simulate.
        n_jobs: worker processes (default: number of CPUs, at most the number of batches); 1 runs in this
            process.
        progress: optional callback ``progress(done, total, result)`` called as batches finish (in order).
        keep_raman: return the Raman spectra (about 20 MB per batch when recorded); ``False`` drops them.
    """
    specs = list(specs)
    run = functools.partial(simulate, keep_raman=keep_raman)
    n_jobs = min(n_jobs or os.cpu_count() or 1, max(len(specs), 1))
    results: list[BatchResult] = []
    if n_jobs == 1:
        for spec in specs:
            results.append(run(spec))
            if progress:
                progress(len(results), len(specs), results[-1])
        return results
    with process_pool(n_jobs) as pool:
        for result in pool.map(run, specs):
            results.append(result)
            if progress:
                progress(len(results), len(specs), result)
    return results


def yields(results: Sequence[BatchResult]) -> list[float]:
    """Total harvested penicillin [kg] of each batch."""
    return [r.total_yield for r in results]
