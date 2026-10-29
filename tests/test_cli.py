import json

import pandas as pd
import pytest

from penicillium.cli import main


def test_generate_csv_with_raman(tmp_path):
    args = ["generate", "--n-batches", "2", "--faults", "0", "1", "--raman", "--format", "csv", "--batch-length", "3"]
    assert main([*args, "--out", str(tmp_path)]) == 0
    meta = json.loads((tmp_path / "metadata.json").read_text())
    assert [(b["seed"], b["fault"]) for b in meta["batches"]] == [
        (1, "NONE"), (2, "NONE"), (1, "AERATION"), (2, "AERATION"),
    ]  # fmt: skip
    df = pd.read_csv(tmp_path / "batch_00001_fault1.csv", index_col=0)
    assert len(df) == 15
    assert {"seed", "fault", "P", "T", "pH", "Fault_ref"} <= set(df.columns)
    raman = pd.read_csv(tmp_path / "batch_00001_fault1_raman.csv", index_col=0)
    assert raman.shape == (15, 2200)


def test_generate_parquet(tmp_path):
    pytest.importorskip("pyarrow")
    assert main(["generate", "--n-batches", "1", "--batch-length", "3", "--out", str(tmp_path)]) == 0
    df = pd.read_parquet(tmp_path / "batch_00001_fault0.parquet")
    assert len(df) == 15 and df.index.name == "time_h"


def test_rejects_unknown_fault(tmp_path):
    with pytest.raises(SystemExit):
        main(["generate", "--faults", "9", "--out", str(tmp_path)])
