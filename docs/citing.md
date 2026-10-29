# Citing and references

If you publish results obtained with Penicillium, please cite **IndPenSim**, which is the model, and
**Penicillium**, which is the implementation you ran. The repository's `CITATION.cff` contains both in
machine-readable form; GitHub's "Cite this repository" button and most reference managers can read it.

A suggested sentence for your methods section:

> Batches were simulated with IndPenSim (Goldrick et al., 2015, 2019) using its Python implementation
> Penicillium (version x.y.z), with [default settings / the settings listed in Table N].

Please state the version (`penicillium.__version__`) and any non-default options (`result.config`). Your
reviewers will want to reproduce your batches, and with the seed and the config they can.

## Penicillium

- F. Sartori. *Penicillium: a validated, pip-installable Python implementation of the IndPenSim penicillin fermentation simulator.* Software, Zenodo. [doi:10.5281/zenodo.23773130](https://doi.org/10.5281/zenodo.23773130)

This DOI always resolves to the latest release. Each release also has its own DOI, listed on the
[Zenodo page](https://doi.org/10.5281/zenodo.23773130); cite that one to name the exact version you ran.

## IndPenSim

- S. Goldrick, A. Ştefan, D. Lovett, G. Montague, B. Lennox. *The development of an industrial-scale fed-batch
  fermentation simulation.* Journal of Biotechnology 193 (2015) 70–82.
  [doi:10.1016/j.jbiotec.2014.10.029](https://doi.org/10.1016/j.jbiotec.2014.10.029)
- S. Goldrick, C. A. Duran-Villalobos, K. Jankauskas, D. Lovett, S. S. Farid, B. Lennox. *Modern day monitoring
  and control challenges outlined on an industrial-scale benchmark fermentation process.* Computers and
  Chemical Engineering 130 (2019) 106471.
  [doi:10.1016/j.compchemeng.2019.05.037](https://doi.org/10.1016/j.compchemeng.2019.05.037) (open access)
- S. Goldrick. *Data for: Modern day monitoring and control challenges outlined on an industrial-scale benchmark
  fermentation process.* Mendeley Data (2019), CC BY 4.0.
  [doi:10.17632/pdnjz7zz5x.1](https://doi.org/10.17632/pdnjz7zz5x.1) (cite if you use the published 100 batches)
- S. Goldrick. *IndPenSim: Industrial-scale Penicillin Simulation*, MATLAB, version 2.01 (2019). MATLAB Central
  File Exchange,
  <https://www.mathworks.com/matlabcentral/fileexchange/49041-industrial-scale-penicillin-simulationv2>.
  BSD 3-Clause License, Copyright (c) 2016, Stephen Goldrick. The software Penicillium is derived from (see
  [licensing](licensing.md)).

## Background

- G. C. Paul, C. R. Thomas. *A structured model for hyphal differentiation and penicillin production using
  Penicillium chrysogenum.* Biotechnology and Bioengineering 51 (1996) 558–572. The morphological model
  IndPenSim builds on.
- G. Birol, C. Ündey, A. Çınar. *A modular simulation package for fed-batch fermentation: penicillin
  production.* Computers and Chemical Engineering 26 (2002) 1553–1565. PenSim, the earlier, smaller penicillin
  benchmark, often confused with IndPenSim. They are different models.
