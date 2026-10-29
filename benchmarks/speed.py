"""Speed benchmark: one batch per backend and Raman setting, and campaign throughput.

    python benchmarks/speed.py

Results go to stdout as a Markdown table.
"""

from __future__ import annotations

import argparse
import os
import platform
import time

import numpy as np

from penicillium import BatchSpec, RamanMode, SimulationConfig, Simulator, __version__, simulate_batches


def time_batch(config: SimulationConfig, backend: str, repeats: int = 3) -> float:
    sim = Simulator(config=config, backend=backend)
    sim.run(seed=0)  # warm-up (Numba compilation is cached on disk)
    best = np.inf
    for seed in range(1, repeats + 1):
        t = time.perf_counter()
        sim.run(seed=seed)
        best = min(best, time.perf_counter() - t)
    return best


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", type=int, default=100, help="batches in the throughput test (0 to skip)")
    args = ap.parse_args()
    rows = []
    for backend in ("numba", "python"):
        for mode in (RamanMode.OFF, RamanMode.RECORD):
            dt = time_batch(SimulationConfig(raman_mode=mode), backend, repeats=3 if backend == "numba" else 1)
            rows.append((f"Penicillium {__version__} ({backend})", mode != RamanMode.OFF, dt))
    print(f"Machine: {platform.processor() or platform.machine()}, {os.cpu_count()} logical CPUs, {platform.system()}, "
          f"Python {platform.python_version()}\n")  # fmt: skip
    print("| implementation | Raman spectra | seconds per 230 h batch (best of 3) |")
    print("|---|---|---|")
    for name, raman, dt in rows:
        print(f"| {name} | {'yes' if raman else 'no'} | {dt:.2f} |")
    if args.campaign:
        specs = [BatchSpec(seed=i, config=SimulationConfig(raman_mode=RamanMode.OFF)) for i in range(args.campaign)]
        simulate_batches(specs[: os.cpu_count()], keep_raman=False)  # warm up the workers' caches
        t = time.perf_counter()
        simulate_batches(specs, keep_raman=False)
        dt = time.perf_counter() - t
        print(f"\nCampaign: {args.campaign} batches (Raman off, numba) on {os.cpu_count()} processes in {dt:.1f} s "
              f"({args.campaign / dt * 60:.0f} batches per minute).")  # fmt: skip


if __name__ == "__main__":
    main()
