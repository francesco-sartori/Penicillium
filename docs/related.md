# Related simulators

Penicillium is one of several simulators of penicillin fermentation. They differ in the model, the scale and the
tools around them, and two of them are often confused: PenSim and IndPenSim are different models.

| | PenSim | IndPenSim | PenSimPy | Penicillium |
|---|---|---|---|---|
| **Reference** | Birol, Ündey and Çınar (2002) | Goldrick et al. (2015, 2019) | Quartic.ai | This package |
| **Scope** | Fed-batch penicillin fermentation, unstructured kinetic model; an earlier, smaller benchmark | Industrial-scale (100 m³) fed-batch fermentation, structured and segregated model fitted to plant records; recipes, PID loops, eight faults, lab assays, Raman spectra | Python implementation of IndPenSim | Python implementation of IndPenSim V2.01 |
| **Language** | See the reference | MATLAB | Python | Python (optional Numba and JAX) |
| **Licence** | See the reference | BSD 3-Clause | MIT | MIT; the parts derived from IndPenSim also under IndPenSim's BSD 3-Clause ([licensing](licensing.md)) |
| **Interfaces** | See the reference | MATLAB scripts | Step-by-step Python interface | Python API, campaigns, Gymnasium and Minari, JAX model, command line, operator console |
| **Published data** | – | 100-batch data set (Goldrick, 2019, CC BY 4.0) | – | Generates campaigns on demand; validated against the 100-batch data set ([validation](validation.md)) |
| **Last release** | – | V2.01, July 2019 | June 2021 | Alpha, 2026 |

Where Penicillium's behaviour differs from IndPenSim V2.01, or where we are unsure how a detail of V2.01 was meant
to work, the difference is listed in [Differences and quirks](quirks.md).

PenSimPy (Quartic.ai, MIT License) was the first Python implementation of IndPenSim. Penicillium's first version
was ported from PenSimPy 1.2.5 before being checked line by line against the MATLAB original; the portions derived
from it keep PenSimPy's MIT notice ([licensing](licensing.md)). PenSimPy's last release dates from June 2021. It
pins NumPy 1.18, pandas 1.0 and SciPy 1.4, and its default solver uses `fastodeint`, a C++ extension that is not
published on PyPI, so `pip install pensimpy` does not complete on current Python versions (checked October 2026).

We could not find a current download of PenSim, so its language, licence and interfaces are not given here; the
reference below describes the package.

**References.** G. Birol, C. Ündey, A. Çınar. *A modular simulation package for fed-batch fermentation: penicillin
production.* Computers and Chemical Engineering 26 (2002) 1553–1565. The IndPenSim papers and data set are listed
in [Citing and references](citing.md).
