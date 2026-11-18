"""Cases and fingerprints of the fault non-regression golden file (``tests/data/fault_golden_0.1.0a1.json``).

Shared by the generator (``tests/data/make_fault_golden.py``, run against the code of tag ``v0.1.0a1``) and the test
(``tests/test_fault_regression.py``, run against the current code), so both compute every case the same way. It uses
only the 0.1.0a1 API.
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

#: Channels whose values are also stored, at a few samples, for the tolerance comparison on other platforms.
SAMPLED_CHANNELS: tuple[str, ...] = (
    "P", "X", "S", "V", "T", "pH", "DO2", "PAA", "Fs", "Fg", "pressure", "Fb", "Fc", "Fault_ref",
)  # fmt: skip

#: Controller modes covered by the full matrix: (quirks, inhibition).
MODES: tuple[tuple[str, int], ...] = (("matlab", 2), ("fixed", 2), ("matlab", 0), ("matlab", 1))


def cases() -> dict[str, dict]:
    """Every batch case: name -> keyword arguments of ``SimulationConfig`` plus ``seed``, ``backend`` and ``slow``.

    ``short``: faults 0-8, 30 h (first windows of faults 1 and 3, labels of every fault), fast. ``full``: faults 0-8 x
    seeds 1, 7 x ``MODES``, 280 h, which covers every IndPenSim window (the last one ends at 270 h). Extras: Raman
    with PRBS and noise, PAT control, and the Numba backend.
    """
    out: dict[str, dict] = {}
    for fault in range(9):
        out[f"short_f{fault}"] = {"fault": fault, "batch_length_h": 30.0, "seed": 1, "backend": "python", "slow": False}
    for fault in range(9):
        for seed in (1, 7):
            for quirks, inhibition in MODES:
                out[f"full_f{fault}_s{seed}_{quirks}_inh{inhibition}"] = {
                    "fault": fault, "batch_length_h": 280.0, "quirks": quirks, "inhibition": inhibition,
                    "seed": seed, "backend": "python", "slow": True,
                }  # fmt: skip
    out["raman_prbs_f8"] = {"fault": 8, "batch_length_h": 120.0, "raman_mode": 1, "prbs": True, "seed": 7,
                            "backend": "python", "slow": True}  # fmt: skip
    out["pat_f3"] = {"fault": 3, "batch_length_h": 120.0, "raman_mode": 2, "seed": 7, "backend": "python",
                     "slow": True}  # fmt: skip
    out["numba_f6"] = {"fault": 6, "batch_length_h": 280.0, "seed": 1, "backend": "numba", "slow": True}
    return out


def fingerprint(backend: str = "python") -> dict[str, str]:
    """What must match for results to be bit-identical: platform, Python, NumPy, SciPy (and Numba) versions."""
    import scipy

    fp = {
        "system": platform.system(),
        "machine": platform.machine(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "numpy": np.__version__,
        "scipy": scipy.__version__,
    }
    if backend == "numba":
        import numba

        fp["numba"] = numba.__version__
    return fp


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _array_sha(values) -> str:
    a = np.array(values, dtype="<f8")
    a[np.isnan(a)] = np.nan  # one NaN bit pattern
    return _sha(a.tobytes())


def run_case(spec: dict) -> dict:
    """Simulate one case and return its hashes and sampled values."""
    from penicillium import Fault, RamanMode, SimulationConfig, Simulator

    kw = {k: v for k, v in spec.items() if k not in ("seed", "backend", "slow")}
    kw["fault"] = Fault(kw["fault"])
    kw.setdefault("raman_mode", 0)
    kw["raman_mode"] = RamanMode(kw["raman_mode"])
    r = Simulator(config=SimulationConfig(**kw), backend=spec["backend"]).run(seed=spec["seed"])
    n = len(r.time)
    idx = sorted({int(i) for i in np.linspace(0, n - 1, 12)})
    return {
        "channels": {name: _array_sha(values) for name, values in r.data.items()},
        "time": _array_sha(r.time),
        "raman": None if r.raman is None else _array_sha(r.raman),
        "total_yield": repr(float(r.total_yield)),
        "metadata": _sha(json.dumps(r.metadata, sort_keys=True).encode()),
        "samples": idx,
        "values": {name: [repr(float(r[name][i])) for i in idx] for name in SAMPLED_CHANNELS},
        "raman_sum": None if r.raman is None else repr(float(r.raman.sum())),
    }


def run_campaign() -> dict:
    """Hashes of a small ``fault_campaign``: batch table, labels and every sample."""
    from penicillium import RamanMode, SimulationConfig, scenarios

    cfg = SimulationConfig(raman_mode=RamanMode.OFF, batch_length_h=30.0)
    camp = scenarios.fault_campaign(n_normal=1, n_per_fault=1, seed=0, config=cfg, n_jobs=1)
    return {
        "batches_columns": list(camp.batches.columns),
        "batches": _sha(camp.batches.to_csv(index=False).encode()),
        "fault_active": _array_sha(camp.samples["fault_active"]),
        "samples_columns": list(camp.samples.columns),
        "samples": _sha(camp.samples.to_csv(index=False).encode()),
    }


def run_cli() -> dict:
    """Hash of the batch records ``penicillium generate`` writes to ``metadata.json`` (without the version)."""
    from penicillium.cli import main

    with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
        main(["generate", "--n-batches", "1", "--faults", "0", "1", "7", "--batch-length", "3", "--format", "csv",
              "--out", tmp])  # fmt: skip
        meta = json.loads((Path(tmp) / "metadata.json").read_text())
    return {"batches": _sha(json.dumps(meta["batches"], sort_keys=True).encode())}
