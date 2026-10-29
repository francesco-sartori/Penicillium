# Tutorials

Nine notebooks, one per main feature of Penicillium. Each one runs end to end in a few minutes and is shown here
with its output. To run them yourself, download them with the button at the top of each page, or open them from
`docs/tutorials/` in a clone of the repository, after installing the notebook extra:

```bash
pip install -e ".[notebooks]"  # tutorial 8 also needs: pip install -e ".[jax]" diffrax
```

| # | Tutorial | What you learn |
|---|---|---|
| 1 | [Your first batch](01_first_batch.ipynb) | Run a batch, read the results, batch phases, every channel by group, compare seeds, save the data |
| 2 | [Recipes and control](02_recipes_and_control.ipynb) | Read and change the recipe, compare recipes on the same batches, step through a batch with your own control rules, control PAA from lab results |
| 3 | [Options, faults and disturbances](03_options_faults_disturbances.ipynb) | `SimulationConfig`, disturbances on and off, the IndPenSim faults and their labels, setpoints, batch length, initial conditions, replaying a batch |
| 4 | [Lab data, Raman spectra and measurement noise](04_lab_data_raman_and_noise.ipynb) | Delayed lab assays, Raman spectra and a 3D waterfall, realistic sensor and assay errors, one file with everything |
| 5 | [Campaigns and fault detection](05_campaigns_and_fault_detection.ipynb) | One-call data sets; an MPCA monitor built in three stages (training, validation, test) and scored per batch and per sample |
| 6 | [A Raman soft sensor](06_raman_soft_sensor.ipynb) | Calibrate a PLS model on spectra and lab results, test it on new batches |
| 7 | [Reinforcement learning](07_reinforcement_learning.ipynb) | The Gymnasium environments, training a policy with the cross-entropy method and testing it on unseen batches, Minari datasets and behaviour cloning |
| 8 | [The differentiable model (JAX)](08_differentiable_model.ipynb) | Exact Jacobians, parameter sensitivity, gradients through integration |
| 9 | [The command line](09_command_line.ipynb) | Generate data sets without Python, start the operator console |

The tutorials link to the matching pages of the user guide, which explain each feature in full.

Longer case studies (replications of Goldrick et al. 2015 and 2019, a statistical check of the noise model) are
in the repository's `notebooks/` folder.
