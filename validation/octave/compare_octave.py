"""Replay IndPenSim V2.01 batches run under GNU Octave in Penicillium and compare them sample by sample.

The batches come from ``validation/octave/run_indpensim_v201.m``: each ``case_NN.mat`` holds the inputs of one
batch (initial state, kinetic parameters, disturbance sequences, flags) and the channels V2.01 recorded. The same
inputs are given to Penicillium through ``BatchParameters.from_matlab``; PRBS steps are recovered from the
recorded Fs and Fpaa and replayed in the same order.

Usage: python validation/octave/compare_octave.py [folder with case_NN.mat] [--solver lsoda] [--rtol 1e-5] [--out f.csv]
The folder defaults to validation/octave/data (the batches used in docs/validation_octave.md).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat

from penicillium import BatchParameters, BatchResult, Fault, RamanMode, SimulationConfig, Simulator

DATA = Path(__file__).parent / "data"
#: Channels compared (names shared by V2.01's batch structure and Penicillium's result).
CHANNELS = ["S", "DO2", "O2", "P", "V", "Wt", "pH", "T", "Q", "Viscosity", "Culture_age", "a0", "a1", "a3", "a4",
            "X", "CO2outgas", "CO2_d", "PAA", "NH3", "mu_P_calc", "mu_X_calc", "Fs", "Fpaa", "Fa", "Fb", "Fc", "Fh",
            "OUR", "CER"]  # fmt: skip
#: Process states (the controller flows Fa, Fb, Fc, Fh and the heat Q follow on/off switches, see the docs).
STATES = ["S", "DO2", "O2", "P", "V", "Wt", "pH", "T", "Viscosity", "a0", "a1", "a3", "a4", "X", "CO2outgas",
          "CO2_d", "PAA", "NH3"]  # fmt: skip
STEPS = {"Fs": 15, "Fpaa": 1}  # PRBS step sizes in fctrl_indpensim.m


class ReplayPRBS:
    """Stands in for the PRBS generator: returns V2.01's draws (1: no step, 2: +step, 3: -step) in order."""

    def __init__(self, draws: list[int]):
        self._draws = iter(draws)

    def randint(self, low: int, high: int) -> int:
        return next(self._draws)


def prbs_draws(ref: dict[str, np.ndarray], n: int) -> list[int]:
    """V2.01's PRBS draws, recovered from the steps in the recorded Fs and Fpaa (Fs is drawn first)."""
    draws = []
    for k in range(600, n + 1, 100):
        for name, size in STEPS.items():
            step = round((ref[name][k - 1] - ref[name][k - 2]) / size)
            draws.append({0: 1, 1: 2, -1: 3}[step])
    return draws


def load(path: Path) -> dict:
    """Flags, inputs and recorded channels of one Octave batch."""
    m = loadmat(path, squeeze_me=True, struct_as_record=False)
    names = [str(s) for s in m["out_names"]]
    return {
        "mat": m,
        "flags": m["Ctrl_flags"],
        "T": float(m["T"]),
        "ref": {n: m["out"][:, i] for i, n in enumerate(names)},
    }


def replay(path: Path, solver: str = "lsoda", rtol: float | None = None, atol: float | None = None) -> BatchResult:
    """Run the batch stored in ``path`` in Penicillium with the same inputs."""
    case = load(path)
    cf = case["flags"]
    prbs = bool(cf.PRBS)
    cfg = SimulationConfig(fault=Fault(int(cf.Faults)), raman_mode=RamanMode(int(cf.Raman_spec)), raman_noise=False,
                           prbs=prbs, batch_length_h=case["T"], disturbances=bool(cf.Dis))  # fmt: skip
    rng = ReplayPRBS(prbs_draws(case["ref"], len(case["ref"]["S"]))) if prbs else None
    return Simulator(config=cfg, solver=solver, rtol=rtol, atol=atol).run(
        rng=rng, batch_parameters=BatchParameters.from_matlab(path)
    )


def errors(res: BatchResult, ref: dict[str, np.ndarray], ch: str) -> np.ndarray:
    """``|Penicillium - Octave|`` per sample, relative to the channel's peak in the Octave run."""
    b = ref[ch]
    return np.abs(np.asarray(res[ch][: len(b)], float) - b) / max(np.max(np.abs(b)), 1e-12)


def compare(path: Path, solver: str = "lsoda", rtol: float | None = None, atol: float | None = None) -> dict:
    case = load(path)
    m, cf, ref = case["mat"], case["flags"], case["ref"]
    t0 = time.perf_counter()
    res = replay(path, solver, rtol, atol)
    runtime = time.perf_counter() - t0
    row = {"case": path.stem, "T_h": case["T"], "fault": int(cf.Faults), "raman": int(cf.Raman_spec),
           "prbs": int(cf.PRBS), "samples": len(ref["S"]), "octave_s": float(m["runtime_s"]), "penicillium_s": runtime,
           "yield_octave_kg": float(m["total_yield_kg"]), "yield_penicillium_kg": res.total_yield}  # fmt: skip
    row["yield_rel_err"] = abs(row["yield_penicillium_kg"] / row["yield_octave_kg"] - 1)
    worst = np.max([errors(res, ref, ch) for ch in STATES], axis=0)
    row["states_mean"] = float(np.mean([errors(res, ref, ch).mean() for ch in STATES]))
    row["states_max"] = float(worst.max())
    # First sample at which some state differs by more than 1e-3 of its peak (NaN: never).
    row["first_divergence_h"] = float(np.argmax(worst > 1e-3) + 1) * 0.2 if (worst > 1e-3).any() else np.nan
    row["samples_over_1e-3"] = int((worst > 1e-3).sum())
    for ch in CHANNELS:
        err = errors(res, ref, ch)
        row[f"{ch}_mean"] = float(err.mean())
        row[f"{ch}_max"] = float(err.max())
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path, nargs="?", default=DATA)
    ap.add_argument("--solver", default="lsoda")
    ap.add_argument("--rtol", type=float, default=None)
    ap.add_argument("--atol", type=float, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    rows = []
    for path in sorted(args.folder.glob("case_*.mat")):
        r = compare(path, args.solver, args.rtol, args.atol)
        rows.append(r)
        print(
            f"{r['case']}: T {r['T_h']:g} h fault {r['fault']} Raman {r['raman']} PRBS {r['prbs']} | yield "
            f"{r['yield_penicillium_kg']:.1f} vs {r['yield_octave_kg']:.1f} kg ({r['yield_rel_err']:.1e}) | "
            f"states mean {r['states_mean']:.1e} max {r['states_max']:.1e} | first > 1e-3 at "
            f"{r['first_divergence_h']:g} h | {r['penicillium_s']:.1f} s vs {r['octave_s']:.0f} s",
            flush=True,
        )
    df = pd.DataFrame(rows)
    summary = pd.DataFrame({ch: {"median of mean": df[f"{ch}_mean"].median(), "worst mean": df[f"{ch}_mean"].max(),
                                 "worst max": df[f"{ch}_max"].max()} for ch in CHANNELS}).T  # fmt: skip
    print("\nError relative to the channel's peak in the Octave run:")
    print(summary.to_string(float_format=lambda v: f"{v:.1e}"))
    if args.out:
        df.to_csv(args.out, index=False)


if __name__ == "__main__":
    main()
