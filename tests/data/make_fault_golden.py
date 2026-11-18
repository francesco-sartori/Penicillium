"""Generate ``fault_golden_0.1.0a1.json``: outputs of Penicillium 0.1.0a1 with every IndPenSim fault.

Run it against the code of tag ``v0.1.0a1``, from the repository root (Git Bash)::

    git worktree add --detach ../penicillium-a1 v0.1.0a1
    PYTHONPATH=../penicillium-a1/src python tests/data/make_fault_golden.py
    git worktree remove ../penicillium-a1

``tests/test_fault_regression.py`` then checks that the current code gives the same outputs when the fault options
added after 0.1.0a1 are not used: bit for bit on a machine with the same fingerprint, to the tolerance of
``test_determinism.py`` elsewhere. ``--only short`` regenerates the fast cases only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tests/, for _fault_golden_cases

import _fault_golden_cases as gc

import penicillium

OUT = Path(__file__).with_name("fault_golden_0.1.0a1.json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--only", choices=["short"], default=None)
    args = parser.parse_args()
    if penicillium.__version__ != "0.1.0a1":
        sys.exit(f"run this against the code of v0.1.0a1, not {penicillium.__version__} ({penicillium.__file__})")
    golden: dict = {
        "version": penicillium.__version__,
        "fingerprint": {"python": gc.fingerprint("python"), "numba": gc.fingerprint("numba")},
        "cases": {},
    }
    for name, spec in gc.cases().items():
        if args.only == "short" and spec["slow"]:
            continue
        t = time.perf_counter()
        golden["cases"][name] = gc.run_case(spec)
        print(f"{name}: {time.perf_counter() - t:.1f} s", flush=True)
    golden["campaign"] = gc.run_campaign()
    golden["cli"] = gc.run_cli()
    args.out.write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
