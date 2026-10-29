# Variables and units

Every batch result has 55 channels, one value per 12-minute sample, recorded at the end of the sample
(`result.time` = 0.2, 0.4, ... h). The names follow IndPenSim, so code and papers that use those names carry
over. `penicillium.CHANNELS` maps each name to a description and a unit in code.

```python
from penicillium import CHANNELS

CHANNELS["DO2"]  # ('Dissolved oxygen concentration', 'mg/L')
```

## Manipulated variables

| Channel | Description | Unit | Set by |
|---|---|---|---|
| `Fs` | Sugar feed | L/h | recipe, PRBS, you |
| `Foil` | Soybean oil feed | L/h | recipe, you |
| `Fg` | Aeration (air flow) | **m³/min** | recipe, you |
| `pressure` | Head-space back pressure (gauge) | bar | recipe, you |
| `discharge` | Broth draw-off, **negative while drawing** | L/h | recipe, you |
| `Fw` | Water for injection | L/h | recipe, you |
| `Fpaa` | Phenylacetic acid feed | L/h | recipe, PRBS, PAT controller, you |
| `Fa` | Acid | L/h | pH controller |
| `Fb` | Base | L/h | pH controller |
| `Fc` | Cooling water | L/h | temperature controller |
| `Fh` | Hot water | L/h | temperature controller |
| `RPM` | Agitator speed | rpm | fixed at 100 |

## Process states

| Channel | Description | Unit | Typical range (nominal batch) |
|---|---|---|---|
| `T` | Broth temperature | K | 297.5–300 (setpoint 298) |
| `pH` | pH | – | 6.4–6.6 |
| `DO2` | Dissolved oxygen | mg/L | 7–15 |
| `S` | Substrate (sugar) | g/L | 0.001–0.002 after the first day |
| `X` | Total biomass ($A_0 + A_1 + A_3 + A_4$) | g/L | 0.5 → 20–25 |
| `P` | Penicillin | g/L | 0 → 20–35 |
| `PAA` | Phenylacetic acid | mg/L | 200–2500 (higher in failing batches) |
| `NH3` | Nitrogen | mg/L | 1500–2100 |
| `V` | Broth volume | L | 58 000 → about 85 000 |
| `Wt` | Vessel (broth) weight | kg | 62 000 → about 94 000 |
| `Viscosity` | Apparent broth viscosity | cP | 4 → 40–80 |
| `CO2_d` | Dissolved CO₂ | g/L | rises with the off-gas CO₂; growth inhibition above 7.57 ([quirks](quirks.md), 2.8) |
| `O2` | O₂ in off-gas, **as a fraction** | – | about 0.19 |
| `CO2outgas` | CO₂ in off-gas, **in percent** | % | 0.04 → about 1.8 |
| `Q` | Net heat accumulated in the broth (integral of the energy balance) | MJ | |
| `Culture_age` | Integral of biomass over time | g h/L | |
| `a0`, `a1`, `a3`, `a4` | Biomass regions: growing, non-growing, degenerated, autolysed | g/L | |
| `n0` … `n9`, `nm` | Vacuole number densities per size class, and of the largest class | – | |
| `phi0` | Mean vacuole volume | – | |
| `mu_P_calc`, `mu_X_calc` | Specific production and growth rates, integrated over the sample | – | |

Yes, off-gas O₂ is a fraction and off-gas CO₂ is a percentage. IndPenSim did it that way, every derived
data set does it that way, and changing it now would break all of them. Write it on a sticky note.

## Derived and auxiliary channels

| Channel | Description | Unit |
|---|---|---|
| `OUR` | Oxygen uptake rate, computed from aeration and off-gas analysis (IndPenSim's formula) | see below |
| `CER` | Carbon evolution rate, computed likewise | see below |
| `Fault_ref` | 1 while a fault is active, else 0 ([faults](faults.md#fault-labels)) | – |
| `PAA_pred` | PAA predicted from the Raman spectrum by PLS (`PAT_CONTROL` mode only, else NaN) | mg/L |

## Off-line lab channels

`P_offline`, `X_offline`, `PAA_offline`, `NH3_offline` and `Viscosity_offline` carry the lab results in the
units of their online counterparts. They are NaN except in the rows where a result is reported
([Lab data and Raman spectra](measurements.md#off-line-lab-results)).

## Notes on units

The units in the tables of this page are the units of the stored values, and the units used by Goldrick et al.
(2015, 2019): g/L, mg/L, L/h, m³/min, cP, K, bar, kg and L. Off-gas O₂ is stored as a fraction, where the 2015
paper writes it in percent. Where the labels of
`penicillium.CHANNELS` differ (below), this page is right; the labels will be corrected before version 1.0.

!!! warning "Four units to handle with care"
    - **`CO2_d` is in g/L**, the unit of Goldrick et al. (2015, Table 1); `penicillium.CHANNELS` currently says
      "mg/L". The growth-inhibition threshold of the V2.01 code (7.57) does not match the paper's critical value
      (35 mg/L), so treat the absolute value with care ([quirks](quirks.md), 2.8).
    - **`Fg` is in m³/min**, as in Goldrick et al. (2015): the model divides it by 60 and by the vessel
      cross-section to get the superficial gas velocity in m/s. The default recipe's 30–75 m³/min corresponds
      to 0.5–0.9 vvm. `penicillium.CHANNELS` currently labels `Fg` as "L/h".
    - **`Q` is in MJ.** The energy balance integrates kJ, and the output divides by 1000. `penicillium.CHANNELS` currently says "kJ".
    - **`OUR` and `CER`** follow IndPenSim's off-gas formulas, with constants inherited from the MATLAB code;
      `CHANNELS` labels them g/min and g/h. They behave like a plant's OUR and CER (proportional to oxygen
      consumption and CO₂ production), but their absolute scale is not mass-balance consistent with the
      model's oxygen uptake term. Use them as monitoring signals and features, not to close a mass balance.

Other conventions:

- **Temperature** is in kelvin throughout. 298 K = 24.85 °C. The [operator console](dcs.md) converts to °C for
  people who are not thermodynamicists.
- **pH** is reported as pH, although the model integrates the H⁺ concentration.
- **`discharge`** is negative in the results and observations (an outflow). You pass it to `Simulator.step` as a
  positive flow.
- **Harvest** (`result.total_yield`, kg) is the penicillin in the vessel at the end plus the penicillin removed by
  every draw: $\sum_k \big[\Delta(VP)_k + |F_{dis,k}|\,P_k\,h\big]/1000$.
