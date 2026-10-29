# Licensing and provenance

Penicillium is released under the **MIT License**. The parts derived from IndPenSim (the model equations,
controllers, recipe tables, fault profiles and reference Raman spectrum) are also subject to **IndPenSim's BSD
3-Clause License**, Copyright (c) 2016, Stephen Goldrick. The package's SPDX licence expression is
`MIT AND BSD-3-Clause`. Both licence texts are in `LICENSE` and below; third-party attributions are in `NOTICE`.
This page records where each part of the package comes from, so that companies and researchers can check what
they are reusing.

| Part | Origin | Licence | Notes |
|---|---|---|---|
| Model equations (`model.py`) | IndPenSim `indpensim_ode.m`, Goldrick et al. (2015, 2019) | BSD-3-Clause (IndPenSim) | Checked line by line against IndPenSim V2.01. The equations are published in the two papers. |
| Controllers, faults, recipe logic (`simulator.py`, `recipe.py`) | IndPenSim `fctrl_indpensim.m`, `indpensim.m` | BSD-3-Clause (IndPenSim) | Recipe tables are IndPenSim's numerical setpoints. |
| Raman simulation (`raman.py`, `_raman_reference.py`) | IndPenSim `Raman_Sim.m` and `reference_Specra.txt` | BSD-3-Clause (IndPenSim) | The reference spectrum is the first 2200 rows of `reference_Specra.txt`, the rows `Raman_Sim.m` uses. |
| PAA PLS model (`_paa_pls.py`) | Fitted by this project on its own simulated spectra (`validation/train_paa_pls.py`) | MIT | IndPenSim's `PAA_PLS_model.mat` is **not** used or distributed. |
| Octave driver (`validation/octave/run_indpensim_v201.m`) | This project; its random-setup block is adapted from IndPenSim V2.01 `indpensim_run.m` | MIT and BSD-3-Clause (IndPenSim) | Repository only, not in the package. Runs a separately downloaded copy of V2.01 in GNU Octave; no V2.01 file is included. |
| Octave batches (`validation/octave/data/`) | Inputs and outputs of IndPenSim V2.01 run in GNU Octave by this project | MIT and BSD-3-Clause (IndPenSim) | Repository only, not in the package. Numerical data, no IndPenSim code. |
| Gymnasium environment, scenarios, solvers, tests | This project | MIT | |

`model.py`, `simulator.py` and `raman.py` also contain portions derived from PenSimPy 1.2.5, Copyright (c) 2020
Quartic.ai Canada, Inc., under the MIT License, whose notice is part of Penicillium's licence below.

If you redistribute Penicillium, or software built from its IndPenSim-derived parts, keep `LICENSE` and `NOTICE`
with it: the BSD 3-Clause License requires its copyright notice, conditions and disclaimer to be retained in
source and reproduced in the documentation of binary distributions. Its third clause also applies: the name of
University College London and of IndPenSim's contributors may not be used to endorse or promote derived products
without written permission. Penicillium is not endorsed by Stephen Goldrick, by University College London or by
any other contributor to IndPenSim.

Not distributed:

- **IndPenSim's MATLAB source** and its data files. IndPenSim V2.01 is distributed on
  [MATLAB File Exchange](https://www.mathworks.com/matlabcentral/fileexchange/49041-industrial-scale-penicillin-simulationv2)
  under the BSD 3-Clause License below, and at <http://www.industrialpenicillinsimulation.com/>. Penicillium
  contains no MATLAB file.
- **The published 100-batch IndPenSim data set** (Goldrick, 2019, Mendeley Data,
  [doi:10.17632/pdnjz7zz5x.1](https://doi.org/10.17632/pdnjz7zz5x.1), CC BY 4.0). The validation scripts download
  it; cite it if you use it.
- **The papers.** Link to them: Goldrick et al. 2015, [doi:10.1016/j.jbiotec.2014.10.029](https://doi.org/10.1016/j.jbiotec.2014.10.029);
  Goldrick et al. 2019 (open access, CC BY-NC-ND 4.0), [doi:10.1016/j.compchemeng.2019.05.037](https://doi.org/10.1016/j.compchemeng.2019.05.037).

Data you generate with Penicillium is yours. Please cite IndPenSim (Goldrick et al. 2015, 2019) and this
package (`CITATION.cff`) when you publish it.

## IndPenSim licence

```text
Copyright (c) 2016, Stephen Goldrick
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution
* Neither the name of University College London nor the names of its
  contributors may be used to endorse or promote products derived from this
  software without specific prior written permission.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Penicillium licence

```text
MIT License

Copyright (c) 2026 Francesco Sartori

Portions derived from PenSimPy 1.2.5:
Copyright (c) 2020 Quartic.ai Canada, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
