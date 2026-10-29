# Lab data and Raman spectra

A real penicillin plant measures temperature, pH, dissolved oxygen, off-gas, weight and flows online. The
quantities that matter most (penicillin, biomass, precursor) come from the lab, twice a day, with a delay.
That gap is the reason soft sensors exist. Penicillium records both kinds of data, plus the spectra of a
simulated Raman probe.

## Online measurements

Every channel in [Variables and units](variables.md) is recorded once per 12-minute sample, at the end of the
sample. Online measurements in the narrow sense, the ones a plant would have, are listed in
`penicillium.scenarios.ONLINE_CHANNELS`:

> `Fs`, `Foil`, `Fg`, `pressure`, `discharge`, `Fw`, `Fpaa`, `Fa`, `Fb`, `Fc`, `Fh`, `RPM`, `DO2`, `O2`, `V`,
> `Wt`, `pH`, `T`, `CO2outgas`, `OUR`, `CER`

!!! warning "Noise-free by default"
    The recorded channels are exact model values. Only the Raman spectra carry measurement noise unless you add
    [measurement noise](#measurement-noise) to the online and lab channels.

!!! warning "OUR and CER are monitoring signals, not a mass balance"
    `OUR` and `CER` follow IndPenSim's off-gas formulas, with the constants of the V2.01 code. They rise and fall
    with oxygen consumption and CO₂ production, but their absolute scale is not consistent with the oxygen uptake
    of the model, so they cannot close an oxygen or carbon balance, and a respiratory quotient computed from them
    (`CER / OUR`) should not be read quantitatively. Use them as monitoring signals and features. We are not
    certain how the constants were meant to be set ([quirks](quirks.md), 2.7). Optional channels computed from the
    model's own oxygen consumption and CO₂ production are planned, with the default output unchanged.

## Off-line lab results

Five assays are taken at **1 h, every 12 h and at the end of the batch**:

| Channel | Assay | Unit |
|---|---|---|
| `P_offline` | Penicillin | g/L |
| `X_offline` | Biomass (dry weight) | g/L |
| `PAA_offline` | Phenylacetic acid | mg/L |
| `NH3_offline` | Nitrogen (ammonia) | mg/L |
| `Viscosity_offline` | Broth viscosity | cP |

Each result appears in the row of the time it is **reported**, and holds the value at the time the broth was
**sampled**, `offline_delay_steps` samples earlier (default 4 samples = 48 min). All other rows are NaN:

```python
lab = result.to_pandas()[["P_offline", "X_offline", "PAA_offline"]].dropna()
```

In [campaigns](scenarios.md), `camp.lab` gives the same data in long form, with both `sample_time_h` and
`available_time_h`, which is what you need to build a causal soft sensor.

!!! note "48 minutes or 4 hours?"
    The 2019 IndPenSim paper describes a "4 h" delay in the off-line measurements. The V2.01 code delays them by
    4 *samples* (48 min), and Penicillium follows the code. For a 4-hour turnaround, use
    `SimulationConfig(offline_delay_steps=20)`.

!!! note "Sampling interval on the real plant"
    On the industrial plant behind IndPenSim, penicillin, nitrogen and viscosity were sampled every 24 h and PAA
    every 12 h (Goldrick et al. 2015, section 3.2). The V2.01 code samples all five assays every 12 h, and so does
    Penicillium. `SimulationConfig(offline_interval_h=24)` samples all of them daily; the interval is shared by
    every assay.

## Measurement noise

Real probes are noisy, mis-calibrated and drift; lab assays have a few percent of error. `MeasurementNoise`
adds these errors to a copy of a simulated batch. The simulation itself is untouched, so the controllers, the
process and every seeded batch stay exactly as they are, and the exact values remain available for scoring:

```python
from penicillium import MeasurementNoise, Sensor, Simulator

result = Simulator().run(seed=1)
noisy = MeasurementNoise.typical().apply(result)  # seeded by the batch seed; seed=... to change it
noisy["pH"]  # what the pH probe read
noisy.truth["pH"]  # the process pH
noisy["P_offline"]  # HPLC results, with assay error, on the same schedule as before
```

Each sensor combines the error sources of a real instrument, in the channel's units:

$$
y_\text{meas} = \operatorname{quantise}\Big(\operatorname{clip}\big(y\,(1 + r\,\varepsilon_1) + \sigma\,\varepsilon_2 + b + w(t)\big)\Big)
$$

| `Sensor` field | Symbol | Physical meaning |
|---|---|---|
| `sd` | σ | additive white noise (probe precision), per sample |
| `rel` | r | relative white noise, fraction of the reading (flowmeters, assays) |
| `offset_sd` | b | calibration bias, drawn once per batch |
| `drift_sd` | w(t) | random-walk drift, per √h (electrode ageing, membrane fouling) |
| `resolution` | | quantisation of the transmitter or of the reported result |
| `lo`, `hi` | | instrument range; flows and concentrations never read negative (default `lo=0`) |

Three rules keep the measurements physically consistent:

- `OUR` and `CER` are not noised on their own. They are recomputed from the measured `Fg`, `O2` and
  `CO2outgas`, as a plant computes them, so their errors are correlated with those of the off-gas analyser.
- Lab errors are drawn once per analysis; the schedule and the delay of the lab results do not change.
- Model states that a plant does not measure (`S`, `X`, `P`, `a0`, ...) stay exact.

### The `typical()` preset

The preset gives typical orders of magnitude for industrial fermentation instruments and lab assays. It is not
the specification of any particular plant: check it against your instruments' data sheets and your lab's
method validation.

Only measured quantities get noise. The recipe set points (`Fs`, `Foil`, `Fg`, `pressure`, `discharge`, `Fw`,
`Fpaa`) and the fixed agitator speed (`RPM`) are what the recipe asks for, so they stay exact. If your plant
records metered values for them, add a sensor with `with_`, e.g. `with_(Fs=Sensor(rel=0.01))`. `OUR` and `CER`
still carry noise, through the measured `O2` and `CO2outgas`.

!!! warning "No offset or drift on controlled variables"
    `pH` and `T` are held at their setpoints by controllers that act on the *measurement*. A biased probe would
    therefore read close to the setpoint while the true value moved away. Noise added after the simulation cannot
    reproduce that: an offset or drift on `pH` or `T` would show a reading that sits off the setpoint all batch,
    which the controller would never have tolerated. The preset gives them precision noise and resolution only.
    To study a drifting pH or temperature probe, use the in-loop sensor faults `Fault.PH_SENSOR` and
    `Fault.TEMPERATURE_SENSOR` ([Faults](faults.md)). Offsets and drift are fine on measurements that no
    controller acts on, such as `DO2`, `O2` or `Wt`.

| Channel | Instrument | Error |
|---|---|---|
| `T` | Pt100 | σ 0.03 K, resolution 0.01 K |
| `pH` | glass electrode | σ 0.01, resolution 0.01 |
| `DO2` | polarographic probe | 2 % of reading, drift 0.01 mg/L/√h |
| `O2` | off-gas analyser | σ 0.0005 (fraction) |
| `CO2outgas` | off-gas analyser | σ 0.02 %abs |
| `Fa`, `Fb` | Coriolis or magnetic flowmeters (pH controller outputs) | 1 % of reading |
| `Fc`, `Fh` | utility flowmeters (temperature controller outputs) | 2 % of reading |
| `Wt` | load cells | 0.2 % of reading |
| `V` | level / weight | 0.5 % of reading |
| `P_offline` | HPLC | 2 %, resolution 0.01 g/L |
| `PAA_offline` | HPLC | 3 %, resolution 1 mg/L |
| `X_offline` | dry cell weight | 7 % + σ 0.2 g/L, resolution 0.1 g/L |
| `NH3_offline` | enzymatic / ion-selective | 5 %, resolution 1 mg/L |
| `Viscosity_offline` | rheometer | 10 %, resolution 0.1 cP |

Adapt it per channel, or scale every error at once:

```python
noise = MeasurementNoise.typical().with_(
    pH=Sensor(sd=0.02, resolution=0.01),  # a noisier electrode
    Fc=None,  # cooling water flow exact
    Fs=Sensor(rel=0.01),  # metered sugar feed
)
noise = MeasurementNoise.typical().scaled(2.0)  # a noisier plant
```

Each channel draws from its own random stream, derived from the seed and the channel name: changing one sensor
never changes the noise of another, and the same seed always gives the same measurements.

Campaigns take the same object, and the command line has `--noise typical`. The channels then hold the
measurements, and `<channel>_true` columns the exact values (`camp.online()` returns only the measurements):

```python
camp = scenarios.soft_sensor_campaign(n_batches=10, seed=0, measurement_noise=MeasurementNoise.typical())
camp.lab[["sample_time_h", "P", "P_true"]]
```

The notebook `notebooks/measurement_noise.ipynb` plots measurements against the exact values for every channel.

## Raman spectra

With `raman_mode` set to `RECORD` (the default) or `PAT_CONTROL`, every sample from the 11th (2.2 h) onwards
records one spectrum: 2200 intensities at wavenumbers from 2400 down to 201 cm⁻¹, in steps of 1 cm⁻¹.

```python
result.raman  # NumPy array, shape (n_samples, 2200), wavenumbers descending; first 10 rows are zero
result.raman_wavenumber  # the matching wavenumbers, cm⁻¹
spectra = result.raman_to_pandas()  # DataFrame: rows = time_h, columns = ascending wavenumbers
```

The simulated spectrometer follows Goldrick et al. (2019), section 2.2. Each spectrum is the sum of four parts:

1. **A reference spectrum**, the first spectrum recorded on a real 5 L *P. chrysogenum* fermentation, which
   provides the instrument's non-linear background.
2. **A fluorescence baseline** that grows with the broth composition and batch progress:

    $$
    \Delta I(\tilde\nu_j) = 370\,000\,\Big(a\tfrac{X}{40} + b\tfrac{P}{40} + c\tfrac{\mu}{100} + d\tfrac{k}{n}\Big)\big(e^{j/1100} - 0.5\big)
    $$

    with $a = -1.78 \times 10^{-4}$, $b = 1.056$, $c = -6.81 \times 10^{-3}$, $d = -0.02$, $j$ the point index
    from the high-wavenumber end, $k$ the sample and $n$ the number of samples in the batch. Penicillin
    dominates the baseline rise.
3. **Component peaks** (Gaussians), at these centres:

    | Component | Peaks [cm⁻¹] | Intensity |
    |---|---|---|
    | Glucose (substrate) | 2182, 1762, 1348 | saturating: ∝ S / (0.005 + S) |
    | PAA | 1982, 1562 | ∝ PAA |
    | Penicillin | 1601, 1201 | ∝ P |

4. **Noise** (unless `raman_noise=False`): a smoothed random walk along the wavenumber axis, which imitates the
   slowly varying baseline noise of a real instrument.

Because the spectra are simulated every 12 minutes, they are denser than the real instrument in the paper
(every 30 minutes). Subsample them (`spectra.iloc[::2]`, roughly) if you want to match it. The spectra add
about 20 MB per batch in memory.

### The PAA soft sensor (`PAA_pred`)

In `PAT_CONTROL` mode, Penicillium also runs a PLS model on each spectrum and records its PAA prediction in
`PAA_pred` (NaN in the other modes). The model follows IndPenSim's `Substrate_prediction.m`:

- pre-processing: Savitzky–Golay smoothing (window 5, order 2), then the first difference;
- features: the derivative at 1901–2051 cm⁻¹ and 1541–1601 cm⁻¹ (the PAA bands);
- 4 latent variables; from sample 21 on, the prediction is averaged over three samples.

IndPenSim's own PLS model (`PAA_PLS_model.mat`) cannot be redistributed, so Penicillium ships a model of the same
form fitted on 12 of its own batches (training RMSE 18.7 mg/L; `validation/train_paa_pls.py`). As
[Recipes and control](control.md#paa-feedback-control-pat) explains, the prediction does not influence the
process. It is there for you to evaluate, or to beat with your own chemometrics.

!!! tip "Building your own soft sensor"
    `scenarios.soft_sensor_campaign()` generates batches with spectra and lab results, and with PRBS feed
    perturbations so that the concentrations are not all correlated with time. Train on the spectra at
    `sample_time_h` against the lab values, and validate on whole batches you held out. A model that has seen
    other samples from the test batch is grading its own homework.
