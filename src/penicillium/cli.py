"""Command-line interface: generate batch datasets, or start the operator console.

    penicillium generate --n-batches 20 --faults 0 1 3 --out data/
    python -m penicillium generate --n-batches 5 --raman --format csv --out data/

Each batch is written to its own file (``batch_<seed>_fault<k>.parquet`` or ``.csv``, plus
``..._raman.parquet`` when ``--raman`` is given), and ``metadata.json`` lists every batch with its seed,
fault, total yield and the simulator version.

``penicillium dcs`` runs one batch in real time in a DCS-style console in the browser (``dcs`` extra).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from ._version import __version__
from .batches import process_pool
from .noise import MeasurementNoise
from .simulator import Fault, RamanMode, SimulationConfig, Simulator


def _simulate(seed: int, fault: int, args: argparse.Namespace) -> dict:
    config = SimulationConfig(
        fault=Fault(fault),
        disturbances=not args.no_disturbances,
        raman_mode=RamanMode.RECORD if args.raman else RamanMode.OFF,  # spectra do not affect the process
        batch_length_h=args.batch_length,
    )
    result = Simulator(config=config).run(seed=seed)
    if args.noise == "typical":
        result = MeasurementNoise.typical().apply(result)
    stem = f"batch_{seed:05d}_fault{fault}"
    df = result.to_pandas()
    df.insert(0, "seed", seed)
    df.insert(1, "fault", fault)
    for name, values in result.truth.items():
        df[f"{name}_true"] = values
    files = [_write(df, args.out / stem, args.format)]
    if args.raman:
        files.append(_write(result.raman_to_pandas().rename(columns=str), args.out / f"{stem}_raman", args.format))
    return {
        "seed": seed,
        "fault": Fault(fault).name,
        "fault_code": fault,
        "total_yield_kg": result.total_yield,
        "final_penicillin_g_per_L": float(result["P"][-1]),
        "measurement_noise": args.noise,
        "files": [f.name for f in files],
        "config": {k: (v.name if hasattr(v, "name") else v) for k, v in asdict(config).items()},
    }


def _write(df, path: Path, fmt: str) -> Path:
    if fmt == "parquet":
        out = path.with_suffix(".parquet")
        df.to_parquet(out)
    else:
        out = path.with_suffix(".csv")
        df.to_csv(out)
    return out


def _generate(args: argparse.Namespace) -> int:
    if args.format == "parquet":
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            print("Parquet output needs pyarrow (pip install pyarrow), or use --format csv.", file=sys.stderr)
            return 2
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = [(args.seed_start + i, fault) for fault in args.faults for i in range(args.n_batches)]
    print(f"Simulating {len(jobs)} batches with {args.jobs} worker(s) into {args.out}/", flush=True)
    if args.jobs > 1:
        pool = process_pool(args.jobs)
        results = (f.result() for f in [pool.submit(_simulate, seed, fault, args) for seed, fault in jobs])
    else:
        pool = None
        results = (_simulate(seed, fault, args) for seed, fault in jobs)
    records = []
    try:
        for i, rec in enumerate(results, 1):
            records.append(rec)
            print(f"[{i}/{len(jobs)}] seed {rec['seed']} {rec['fault']}: {rec['total_yield_kg']:.0f} kg", flush=True)
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=True)
    meta = {"generator": "penicillium", "version": __version__, "batches": records}
    (args.out / "metadata.json").write_text(json.dumps(meta, indent=2))
    return 0


def _dcs(args: argparse.Namespace) -> int:
    try:
        from .dcs.server import serve
    except ImportError as exc:
        print(f'The console needs the dcs extra (pip install "penicillium[dcs]"): {exc}', file=sys.stderr)
        return 2
    serve(host=args.host, port=args.port, backend=args.backend, open_browser=not args.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="penicillium", description="IndPenSim penicillin fermentation simulator")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="simulate batches and write them to files")
    gen.add_argument("--n-batches", type=int, default=10, help="batches per fault type (default 10)")
    gen.add_argument("--seed-start", type=int, default=1, help="seed of the first batch (default 1)")
    gen.add_argument(
        "--faults",
        type=int,
        nargs="+",
        default=[0],
        choices=[int(f) for f in Fault],
        help="fault codes to simulate, 0 = none (default 0); see penicillium.Fault",
    )
    gen.add_argument("--no-disturbances", action="store_true", help="switch off process disturbances")
    gen.add_argument("--raman", action="store_true", help="also write Raman spectra")
    gen.add_argument(
        "--noise",
        choices=["none", "typical"],
        default="none",
        help="measurement noise on online and lab channels; exact values go to <channel>_true (default none)",
    )
    gen.add_argument("--batch-length", type=float, default=230.0, help="batch length in hours (default 230)")
    gen.add_argument("--format", choices=["parquet", "csv"], default="parquet")
    gen.add_argument("--jobs", type=int, default=1, help="parallel worker processes (default 1)")
    gen.add_argument("--out", type=Path, required=True, help="output directory")

    dcs = sub.add_parser("dcs", help="operator console: one batch in real time in the browser (needs the dcs extra)")
    dcs.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1)")
    dcs.add_argument("--port", type=int, default=8050, help="port (default 8050)")
    dcs.add_argument("--backend", choices=["auto", "numba", "python"], default="auto", help="model backend")
    dcs.add_argument("--no-browser", action="store_true", help="do not open the console in a browser")

    args = parser.parse_args(argv)
    if args.command == "generate":
        return _generate(args)
    if args.command == "dcs":
        return _dcs(args)
    return 1  # pragma: no cover


if __name__ == "__main__":
    raise SystemExit(main())
