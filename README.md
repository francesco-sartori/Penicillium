# Penicillium: a Python implementation of the IndPenSim penicillin fermentation simulator

**IndPenSim for Python: validated, pip-installable, fast.** Penicillium is a maintained implementation of
IndPenSim, the industrial-scale (100 m³) fed-batch penicillin fermentation simulator of Goldrick et al. (2015,
2019), the benchmark process for bioprocess monitoring, soft sensors, fault detection and control.

- **Installs anywhere.** Python 3.10 or later; tested on Linux, macOS and Windows with Python 3.10 to 3.14; no
  compiler, no MATLAB.
- **Follows IndPenSim.** Checked line by line against IndPenSim V2.01; 14 of 15 batches of V2.01 (run in GNU
  Octave) replayed within 0.1 % on yield. Against the published 100-batch data set, no significant difference
  detected in the yield distributions of recipe-driven, operator-controlled and faulty batches (KS p = 0.31-0.93;
  the tests have low power) ([validation](https://penicillium.readthedocs.io/en/latest/validation/)).
- **Fast.** 0.6 s per 230 h batch; about 380 batches per minute in parallel on an Intel Core i7-7700HQ
  ([benchmarks](https://penicillium.readthedocs.io/en/latest/benchmarks/)).
- **Ready for ML and control.** One-call campaigns with labels and batch-wise splits, Gymnasium environments, Minari
  datasets and a differentiable JAX model.
- **Reproducible.** Random inputs bit-identical and trajectories within about 1e-4 on Linux, macOS and Windows.
- **Honest about its limits.** Fixed fault windows, true values in the sensor-fault channels and the other known
  limitations are listed on the first page of the documentation ([limitations](https://penicillium.readthedocs.io/en/latest/#limitations-at-a-glance)).
- **Open licence.** MIT, with the parts derived from IndPenSim also under IndPenSim's BSD 3-Clause licence;
  documented provenance ([licensing](https://penicillium.readthedocs.io/en/latest/licensing/)).

> Status: alpha (0.1.0a0). The API may still change.

**Documentation: <https://penicillium.readthedocs.io>**

## Install

```bash
pip install "penicillium[fast]"        # with the Numba backend (recommended)
```

Other extras: `gym`, `minari`, `jax`, `dcs`, `parquet`, `notebooks`, `docs`, `dev`
([installation](https://penicillium.readthedocs.io/en/latest/installation/)).

## Example

```python
from penicillium import Simulator

result = Simulator().run(seed=1)  # one 230 h batch, 1150 samples of 12 min
print(result.total_yield)  # harvested penicillin, kg
df = result.to_pandas()  # 55 channels, indexed by time in hours
```

## Learn more

| | |
|---|---|
| [Tutorials](https://penicillium.readthedocs.io/en/latest/tutorials/) | Nine notebooks, one per feature: first batch, recipes and control, faults, lab data and Raman, campaigns and fault detection, soft sensors, reinforcement learning, the JAX model, the command line |
| [User guide](https://penicillium.readthedocs.io/en/latest/) | The process and the model, every option, variables and units, campaigns, the operator console, FAQ |
| [Validation](https://penicillium.readthedocs.io/en/latest/validation/) | What is checked against IndPenSim and the published data, and the results; [differences and quirks](https://penicillium.readthedocs.io/en/latest/quirks/) |
| [Case studies](https://github.com/francesco-sartori/Penicillium/tree/main/notebooks) | Replications of Goldrick et al. (2015, 2019), a comparison with the published 100-batch data, a statistical check of the noise model |

All of these are on the documentation site, <https://penicillium.readthedocs.io>.

From a clone of the repository, run the tests: `pytest -m "not slow"` (seconds) or `pytest` (adds full batches, ~4 min).

## Citation

If you use Penicillium, cite IndPenSim and this package ([CITATION.cff](https://github.com/francesco-sartori/Penicillium/blob/main/CITATION.cff); see [citing](https://penicillium.readthedocs.io/en/latest/citing/)):

- S. Goldrick, A. Ştefan, D. Lovett, G. Montague, B. Lennox. *The development of an industrial-scale fed-batch
  fermentation simulation.* Journal of Biotechnology 193 (2015) 70-82. doi:10.1016/j.jbiotec.2014.10.029
- S. Goldrick, C. A. Duran-Villalobos, K. Jankauskas, D. Lovett, S. S. Farid, B. Lennox. *Modern day monitoring and
  control challenges outlined on an industrial-scale benchmark fermentation process.* Computers and Chemical
  Engineering 130 (2019) 106471. doi:10.1016/j.compchemeng.2019.05.037

## Licence

Penicillium is released under the MIT License. Its process model, controllers, recipes, fault profiles and
reference Raman spectrum derive from IndPenSim, Copyright (c) 2016, Stephen Goldrick, distributed under the BSD
3-Clause License; that notice applies to those parts too. It is not endorsed by IndPenSim's
authors or by University College London. Full texts are in [LICENSE](https://github.com/francesco-sartori/Penicillium/blob/main/LICENSE) and [NOTICE](https://github.com/francesco-sartori/Penicillium/blob/main/NOTICE).
