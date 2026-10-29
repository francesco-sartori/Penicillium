"""Download and convert the published 100-batch IndPenSim data set (Goldrick, 2019).

    Goldrick, S. (2019). Data for: Modern day monitoring and control challenges outlined on an industrial-scale
    benchmark fermentation process. Mendeley Data, V1. doi:10.17632/pdnjz7zz5x.1. Licence: CC BY 4.0.

The archive (500 MB) holds one 2.6 GB CSV: 37 process columns and 2200 Raman intensities per 12-minute sample. This
module downloads it once, streams the CSV and caches:

* ``process.parquet``: the process columns, renamed to Penicillium channel names, with ``batch_id`` and ``time_h``;
* ``raman.npy`` (float32, samples x 2200, wavenumbers 2400..201 like ``penicillium.raman.WAVENUMBER``), row-aligned
  with ``process.parquet``;
* ``statistics.csv``: the per-batch yields published with the data.

    python validation/indpensim_100_batches.py            # download and convert into ~/.cache/penicillium
    from indpensim_100_batches import load_process        # then in Python (validation/ on sys.path)

The data is not redistributed with Penicillium; cite the DOI above when you use it.
"""

from __future__ import annotations

import csv
import io
import os
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

DOI = "10.17632/pdnjz7zz5x.1"
URL = (
    "https://data.mendeley.com/public-files/datasets/pdnjz7zz5x/files/e7007dff-4061-494f-a9f5-16c20f457d1d/"
    "file_downloaded"
)
ZIP_NAME = "100_Batches_IndPenSim.zip"
CSV_MEMBER = "Mendeley_data/100_Batches_IndPenSim_V3.csv"
STATS_MEMBER = "Mendeley_data/100_Batches_IndPenSim_Statistics.csv"
N_PROCESS_COLUMNS = 37

#: Data set column code (inside the parentheses of each header) -> Penicillium channel name.
RENAME = {
    "Fremoved": "discharge",
    "Fault_ref": "Fault_ref",
    "Control_ref": "control_ref",
    "PAT_ref": "pat_ref",
    "Batch_ref": "batch_ref",
}


def cache_dir() -> Path:
    path = Path(os.environ.get("PENICILLIUM_CACHE", Path.home() / ".cache" / "penicillium")) / "indpensim-100"
    path.mkdir(parents=True, exist_ok=True)
    return path


def download(directory: Path | None = None) -> Path:
    directory = directory or cache_dir()
    target = directory / ZIP_NAME
    if not target.exists():
        print(f"Downloading the IndPenSim 100-batch data set (doi:{DOI}, ~500 MB)...", file=sys.stderr)
        tmp = target.with_suffix(".part")
        request = urllib.request.Request(URL, headers={"User-Agent": "penicillium"})
        with urllib.request.urlopen(request) as response, open(tmp, "wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        tmp.replace(target)
    return target


def _column_name(header: str) -> str:
    match = re.search(r"\(([A-Za-z0-9_]+):", header)
    if match:
        code = match.group(1)
        return RENAME.get(code, code)
    return {"Time (h)": "time_h", "Batch ID": "batch_id", "Fault flag": "fault_flag"}.get(header.strip(), header)


def convert(zip_path: Path | None = None, directory: Path | None = None) -> Path:
    """Stream the CSV out of the archive into ``process.parquet`` and ``raman.npy``."""
    directory = directory or cache_dir()
    if (directory / "process.parquet").exists() and (directory / "raman.npy").exists():
        return directory
    zip_path = zip_path or download(directory)
    with zipfile.ZipFile(zip_path) as zf:
        (directory / "statistics.csv").write_bytes(zf.read(STATS_MEMBER))
        with zf.open(CSV_MEMBER) as raw:
            reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8", newline=""))
            header = next(reader)
            # One header ("1- No Raman spec, 1-Raman spec recorded, 2-PAT control(PAT_ref:PAT ref)") contains commas
            # and is unquoted, so it reads as three fields; the data rows have one.
            i = next(j for j, h in enumerate(header) if "No Raman spec" in h)
            header = [*header[:i], ",".join(header[i : i + 3]), *header[i + 3 :]]
            names = [_column_name(h) for h in header[:N_PROCESS_COLUMNS]]
            process: list[list[float]] = []
            raman_chunks: list[np.ndarray] = []
            chunk: list[list[str]] = []
            for row in reader:
                process.append([float(v) if v not in ("", "NaN") else np.nan for v in row[:N_PROCESS_COLUMNS]])
                chunk.append(row[N_PROCESS_COLUMNS:])
                if len(chunk) == 5000:
                    raman_chunks.append(np.array(chunk, dtype=np.float32))
                    chunk = []
            if chunk:
                raman_chunks.append(np.array(chunk, dtype=np.float32))
    df = pd.DataFrame(process, columns=names)
    df["batch_id"] = df["batch_id"].astype(int)
    df.to_parquet(directory / "process.parquet")
    np.save(directory / "raman.npy", np.concatenate(raman_chunks))
    return directory


def load_process(directory: Path | None = None) -> pd.DataFrame:
    """Process data of all 100 batches (downloads and converts on first use)."""
    return pd.read_parquet(convert(directory=directory) / "process.parquet")


def load_raman(directory: Path | None = None, mmap: bool = True) -> np.ndarray:
    """Raman spectra, row-aligned with ``load_process()`` (memory-mapped by default)."""
    return np.load(convert(directory=directory) / "raman.npy", mmap_mode="r" if mmap else None)


def load_statistics(directory: Path | None = None) -> pd.DataFrame:
    """Per-batch yields published with the data set (grams, as in the file)."""
    return pd.read_csv(convert(directory=directory) / "statistics.csv")


if __name__ == "__main__":
    zip_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    out = convert(zip_arg)
    df = pd.read_parquet(out / "process.parquet")
    print(f"{out}: {df['batch_id'].nunique()} batches, {len(df)} samples, columns: {list(df.columns)}")
