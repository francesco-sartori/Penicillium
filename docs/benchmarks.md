# Speed

Measured with `benchmarks/speed.py` on an Intel Core i7-7700HQ (4 cores / 8 threads) with 16 GB RAM,
Windows 10, Python 3.14, 2026-10-02. One default 230 h batch (recipe driven, disturbances on); best of three runs.

| implementation | Raman spectra | seconds per batch | solver tolerance |
|---|---|---|---|
| Penicillium, Numba backend (`fast` extra) | no | **0.58** | rtol 1e-5 |
| Penicillium, Numba backend | yes | **0.87** | rtol 1e-5 |
| Penicillium, pure Python | no | 11.0 | rtol 1e-5 |
| Penicillium, pure Python | yes | 11.4 | rtol 1e-5 |

These timings are at Penicillium's default tolerance (LSODA, rtol 1e-5), which is not traded for speed: in the
[batch-by-batch comparison with IndPenSim V2.01](validation_octave.md), batches run with the defaults stay within
about 1e-6 (mean over the batch, relative to each variable's peak) and 5e-6 in yield of the same batches solved at
tight tolerances. IndPenSim V2.01 integrates at `ode15s`'s default RelTol 1e-3. A reference-grade run at
rtol 1e-10 takes about 2 s per batch.

Campaigns run in parallel processes (`simulate_batches`, `scenarios.*`): **200 batches in 32 s** on the same machine
(380 batches per minute), so a 1,000-batch campaign takes under 3 minutes.

Reproduce:

```bash
pip install -e ".[fast]"   # from a clone of the repository
python benchmarks/speed.py
```
