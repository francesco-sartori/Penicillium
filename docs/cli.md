# Command line

Installing Penicillium adds a `penicillium` command (also available as `python -m penicillium`). It has two
subcommands: `generate` writes batches to files, and `dcs` starts the [operator console](dcs.md).

## `penicillium generate`

```bash
penicillium generate --n-batches 20 --faults 0 1 2 3 4 5 --jobs 4 --out data/
penicillium generate --n-batches 5 --raman --format csv --out data/
```

| Option | Default | Meaning |
|---|---|---|
| `--out DIR` | required | Output directory (created if missing) |
| `--n-batches N` | 10 | Batches **per fault code** |
| `--faults K [K ...]` | `0` | Fault codes to simulate, 0 = none ([codes](faults.md#faults)) |
| `--seed-start S` | 1 | Seed of the first batch; batch `i` of each fault code gets seed `S + i` |
| `--batch-length H` | 230 | Batch length in hours |
| `--no-disturbances` | off | Switch off the random disturbances |
| `--raman` | off | Also write Raman spectra (one file per batch) |
| `--noise {none,typical}` | none | [Measurement noise](measurements.md#measurement-noise) on the online and lab channels; exact values in `<channel>_true` columns |
| `--format {parquet,csv}` | parquet | Parquet needs pyarrow (the `parquet` extra) |
| `--jobs J` | 1 | Parallel worker processes |

Each batch is written to `batch_<seed>_fault<k>.parquet` (or `.csv`), with `..._raman` files when spectra are
requested, and `metadata.json` lists every batch with its seed, fault, yield, configuration and the package
version. The same seeds are reused for every fault code, so `batch_00001_fault0` and `batch_00001_fault3` are
the *same* batch with and without the fault. That pairing is convenient for studying fault signatures.

!!! note
    The command line seeds batches as `S + i`, while `scenarios` campaigns use `seed × 100 000 + i`. The same
    nominal seed therefore gives different batches through the two routes. Both are reproducible; just do not
    mix them in one study and expect matching batch numbers.

!!! warning "The default seeds overlap with campaign seed 0"
    With the default `--seed-start 1`, the command line simulates the seeds 1, 2, 3, ..., which are also the
    batches of `Simulator().run(seed=n)` and of a campaign with `seed=0` (whose batch `i` gets the seed `i`). A
    batch generated here for training can therefore reappear as a test batch of such a campaign. Choose
    `--seed-start` so that the seeds of the different tools do not overlap. One seeding scheme for all the tools
    is planned before version 1.0.

### Worked example: a paired fault data set

```bash
penicillium generate --n-batches 3 --faults 0 1 3 --noise typical --jobs 2 --out data/
```

The command simulates the seeds 1–3 without fault, with the aeration fault and with the substrate-feed fault.
The same seeds are reused for every fault code, so `batch_00001_fault0` and `batch_00001_fault3` are the same
batch with and without the fault: a paired design for studying fault signatures. For seed 1 the harvest is
3602 kg without fault, 1633 kg with the aeration fault and 1985 kg with the substrate-feed fault. With
`--noise typical` each file holds the measurements, and `<channel>_true` columns the exact values.
[Tutorial 9](tutorials/09_command_line.ipynb) runs this example; its second half, an operator scenario scripted
without the browser, is on the [operator console](dcs.md#architecture) page.

## `penicillium dcs`

```bash
penicillium dcs                      # opens http://localhost:8050/ in your browser
penicillium dcs --port 9000 --no-browser
```

| Option | Default | Meaning |
|---|---|---|
| `--host` | 127.0.0.1 | Address to listen on (use 0.0.0.0 to let trainees on the network connect) |
| `--port` | 8050 | Port |
| `--backend` | auto | Model backend: auto, numba, python |
| `--no-browser` | off | Do not open a browser |

Needs the `dcs` extra. See [Operator console](dcs.md).

## Other

```bash
penicillium --version
penicillium generate --help
```
