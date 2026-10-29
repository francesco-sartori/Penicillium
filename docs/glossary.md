# Glossary

APC
:   Advanced process control. In IndPenSim, the campaign in which the PAA feed is under feedback control
    (`RamanMode.PAT_CONTROL`).

Autolysis
:   Self-digestion of dead hyphal material. Region $A_4$ of the biomass model.

Back pressure
:   Gauge pressure in the vessel head space (`pressure`, bar). Raises oxygen solubility, and also dissolved CO₂.

Batch, fed-batch
:   A batch starts, runs and is harvested as a unit. In a fed-batch, nutrients are fed during the run instead of
    being charged at the start, which keeps the substrate low and controllable.

Broth
:   The fermenting mixture of medium, fungus and product.

Catabolite repression
:   Suppression of secondary metabolism by readily metabolised sugar. The reason penicillin plants keep glucose
    near zero.

CER
:   Carbon evolution rate, computed from the off-gas CO₂ and the air flow.

DCS
:   Distributed control system: the control-room system that runs a plant. See [Operator console](dcs.md).

Discharge, draw
:   Periodic removal of broth during the batch (`discharge`), part of the harvest.

DO₂, DO₂*
:   Dissolved oxygen concentration (mg/L) and its saturation value at the current pressure.

Hyphae
:   The branching filaments a mould grows as. Their growing tips, non-growing sections, vacuolated sections and
    autolysed remains are the four biomass regions of the model.

Hydrolysis
:   Degradation of penicillin in the broth. Its rate depends on pH and temperature.

kLa
:   Volumetric oxygen mass-transfer coefficient (1/h): how fast oxygen moves from bubbles into the broth. It
    depends on aeration, power input, viscosity and oil.

OUR
:   Oxygen uptake rate, computed from the off-gas O₂ and the air flow.

PAA
:   Phenylacetic acid, the precursor of penicillin G's side chain. Required for production above about
    200 mg/L, and toxic to growth above about 2400 mg/L.

PAT
:   Process analytical technology: online analysers such as the Raman probe, used to monitor or control
    quality attributes.

PID
:   Proportional–integral–derivative controller. IndPenSim uses the velocity (incremental) form.

PLS
:   Partial least squares regression, the standard chemometric method for predicting concentrations from
    spectra.

PRBS
:   Pseudo-random binary sequence. In IndPenSim, random steps on the sugar and PAA feeds that imitate operator
    interventions.

Recipe, sequential batch control
:   Predefined time profiles for the manipulated variables.

Sample
:   One 12-minute interval of the simulation, and the record at its end. 230 h = 1150 samples.

Secondary metabolite
:   A product not needed for growth, made mainly by non-growing cells. Penicillin is one.

Seed
:   The integer from which all random quantities of a batch are derived.

Soft sensor
:   A model that estimates an unmeasured quantity (penicillin, biomass, PAA) from measured ones (spectra,
    off-gas, flows).

Split range
:   One controller output driving two actuators, such as cooling and heating water, or acid and base.

Titre
:   Product concentration in the broth (`P`, g/L).

Vacuole
:   Fluid-filled space inside an ageing hypha. Vacuolation turns producing biomass into degenerated biomass.

vvm
:   Volume of gas per volume of liquid per minute, the common unit of aeration intensity.

WFI
:   Water for injection: purified water fed to dilute the broth (`Fw`), which lowers viscosity.

Yield, harvest
:   In this documentation, the total penicillin harvested from a batch in kg (`total_yield`), including the
    draws. (Not the yield *coefficient* in g product per g substrate.)
