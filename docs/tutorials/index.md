# Tutorials

Ten notebooks, one per main feature of Penicillium. Each one runs end to end in a few minutes and is shown here
with its output. To run them yourself, download them all at once, or one by one with the buttons in the table (and
at the top of each tutorial), or open them from `docs/tutorials/` in a clone of the repository, after installing
the notebook extra:

```bash
pip install -e ".[notebooks]"  # tutorial 8 also needs: pip install -e ".[jax]" diffrax
```

<a href="penicillium_tutorials.zip" class="md-button md-button--primary nb-download-all" download>Download all tutorials (.zip)</a>

| # | Tutorial | What you learn | Notebook |
|---|---|---|---|
| 1 | [Your first batch](01_first_batch.ipynb) | Run a batch, read the results, batch phases, every channel by group, compare seeds, save the data | <a href="01_first_batch/01_first_batch.ipynb" class="md-button nb-download-row" download title="Download 01_first_batch.ipynb">Download</a> |
| 2 | [Recipes and control](02_recipes_and_control.ipynb) | Read and change the recipe, compare recipes on the same batches, step through a batch with your own control rules, control PAA from lab results | <a href="02_recipes_and_control/02_recipes_and_control.ipynb" class="md-button nb-download-row" download title="Download 02_recipes_and_control.ipynb">Download</a> |
| 3 | [Options, faults and disturbances](03_options_faults_disturbances.ipynb) | `SimulationConfig`, disturbances on and off, the IndPenSim faults and their labels, setpoints, batch length, initial conditions, replaying a batch | <a href="03_options_faults_disturbances/03_options_faults_disturbances.ipynb" class="md-button nb-download-row" download title="Download 03_options_faults_disturbances.ipynb">Download</a> |
| 4 | [Lab data, Raman spectra and measurement noise](04_lab_data_raman_and_noise.ipynb) | Delayed lab assays, Raman spectra and a 3D waterfall, realistic sensor and assay errors, one file with everything | <a href="04_lab_data_raman_and_noise/04_lab_data_raman_and_noise.ipynb" class="md-button nb-download-row" download title="Download 04_lab_data_raman_and_noise.ipynb">Download</a> |
| 5 | [Campaigns and fault detection](05_campaigns_and_fault_detection.ipynb) | One-call data sets; an MPCA monitor built in three stages (training, validation, test) and scored per batch and per sample | <a href="05_campaigns_and_fault_detection/05_campaigns_and_fault_detection.ipynb" class="md-button nb-download-row" download title="Download 05_campaigns_and_fault_detection.ipynb">Download</a> |
| 6 | [A Raman soft sensor](06_raman_soft_sensor.ipynb) | Calibrate a PLS model on spectra and lab results, test it on new batches | <a href="06_raman_soft_sensor/06_raman_soft_sensor.ipynb" class="md-button nb-download-row" download title="Download 06_raman_soft_sensor.ipynb">Download</a> |
| 7 | [Reinforcement learning](07_reinforcement_learning.ipynb) | The Gymnasium environments, training a policy with the cross-entropy method and testing it on unseen batches, Minari datasets and behaviour cloning | <a href="07_reinforcement_learning/07_reinforcement_learning.ipynb" class="md-button nb-download-row" download title="Download 07_reinforcement_learning.ipynb">Download</a> |
| 8 | [The differentiable model (JAX)](08_differentiable_model.ipynb) | Exact Jacobians, parameter sensitivity, gradients through integration | <a href="08_differentiable_model/08_differentiable_model.ipynb" class="md-button nb-download-row" download title="Download 08_differentiable_model.ipynb">Download</a> |
| 9 | [The command line](09_command_line.ipynb) | Generate data sets without Python, start the operator console | <a href="09_command_line/09_command_line.ipynb" class="md-button nb-download-row" download title="Download 09_command_line.ipynb">Download</a> |
| 10 | [Fault timing and magnitude](10_fault_timing.ipynb) | IndPenSim's fault windows as a preset, random onset and duration, custom magnitudes and ramp shapes, campaigns whose fault timing does not give the fault away | <a href="10_fault_timing/10_fault_timing.ipynb" class="md-button nb-download-row" download title="Download 10_fault_timing.ipynb">Download</a> |

The tutorials link to the matching pages of the user guide, which explain each feature in full.

Longer case studies (replications of Goldrick et al. 2015 and 2019, a statistical check of the noise model) are
in the repository's `notebooks/` folder.
