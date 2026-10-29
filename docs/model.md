# The model

This page summarises the equations Penicillium integrates. They are IndPenSim's equations (Goldrick et al.,
2015, built on the structured model of Paul and Thomas, 1996), transcribed **as implemented** in IndPenSim V2.01
rather than as printed in the paper. Where the code and the paper disagree, the code wins, because the code
produced the published data. Constants are given with the units the model uses. The single source of truth is
`src/penicillium/model.py`; this page is a reader's guide to it, so where the two disagree, believe the code
and tell us about the page.

!!! note "Primary sources"
    This page is a summary of the implementation, not a derivation. It does not give the origin of each term,
    the parameter estimation or the validation against plant data. For those, read Goldrick et al. (2015),
    *The development of an industrial-scale fed-batch fermentation simulation*, Journal of Biotechnology 193,
    70–82, [doi:10.1016/j.jbiotec.2014.10.029](https://doi.org/10.1016/j.jbiotec.2014.10.029), and the
    morphological model of Paul and Thomas (1996). For the Raman analyser, the faults and the operating modes, read
    Goldrick et al. (2019), [doi:10.1016/j.compchemeng.2019.05.037](https://doi.org/10.1016/j.compchemeng.2019.05.037)
    (open access). The reference code is distributed on the IndPenSim website,
    <http://www.industrialpenicillinsimulation.com/>.

!!! abstract "In one sentence"
    A perfectly mixed fed-batch reactor with 33 states: four morphological biomass populations, a population
    balance of vacuoles, penicillin with hydrolysis, substrate, dissolved and gaseous O₂ and CO₂, PAA,
    nitrogen, H⁺, volume, weight, temperature, accumulated heat and viscosity.

## Structure and notation

The broth volume is $V$ [L]. Every concentration is diluted by the liquid feeds:

$$
D = \frac{F_s + F_a + F_b + F_w + F_{PAA} - F_{evp}}{V}
$$

where $F_s$ is the sugar feed, $F_a, F_b$ acid and base, $F_w$ water, $F_{PAA}$ the PAA feed and $F_{evp}$
evaporation, all in L/h. (The oil feed and the broth draw do not enter $D$. The draw removes broth at its own
composition, so it does not dilute anything. Leaving the oil out is IndPenSim's simplification.)

Inputs are held constant over each 12-minute sampling interval (zero-order hold). The controllers act once per
interval, on measurements from the previous interval: see [Recipes and control](control.md).

## Biomass: four regions of a hypha

*P. chrysogenum* grows as branched hyphae. The model splits the biomass $X$ [g/L] into four morphological
regions:

| State | Region | Role |
|---|---|---|
| $A_0$ (`a0`) | Growing tips | Extend the hyphae; consume substrate |
| $A_1$ (`a1`) | Non-growing, non-vacuolated | **Make penicillin**; branch into new tips |
| $A_3$ (`a3`) | Degenerated (vacuolated) | Formed from $A_1$ as vacuoles grow to full size |
| $A_4$ (`a4`) | Autolysed | Dead, lysed material |

$X = A_0 + A_1 + A_3 + A_4$. The rates between them are:

$$
\begin{aligned}
r_b &= \mu_b\,A_1\,\frac{S}{K_b + S} && \text{branching } (A_1 \to A_0)\\
r_e &= \mu_e\,A_0\,\frac{S}{K_e + S} && \text{extension (growth of } A_1\text{ at the tips)}\\
r_{d} &= \mu_{diff}\,\frac{A_0}{K_{diff} + S} && \text{differentiation } (A_0 \to A_1)\\
r_{a} &= \mu_a\,A_3 && \text{autolysis } (A_3 \to A_4)
\end{aligned}
$$

$$
\begin{aligned}
\frac{dA_0}{dt} &= r_b - r_d - D A_0 &
\frac{dA_1}{dt} &= r_e - r_b + r_d - r_{v} - D A_1\\
\frac{dA_3}{dt} &= r_v - r_a - D A_3 &
\frac{dA_4}{dt} &= r_a - D A_4
\end{aligned}
$$

Here $r_v$ is the rate at which vacuoles that reach the maximum size class turn non-growing biomass into
degenerated biomass. It comes from the vacuole population balance below.

The specific growth rates carry all the inhibition terms (next section):

$$
\mu_e = \mu_{x,max}\; I_{pH}\, I_N\, I_T\, I_{DO_2,X}\, I_{CO_2}\, I_{PAA,X}, \qquad \mu_b = 0.4\,\mu_e
$$

and the differentiation constant falls with the mean culture age $\bar a = \text{Culture\_age}/X$ [h]:
$K_{diff} = \max(0.75 - 0.006\,\bar a,\; 0.09)$ g/L.

| Constant | Value | Unit |
|---|---|---|
| $\mu_{x,max}$ | drawn per batch: 0.41 ± 0.025 | 1/h |
| $K_b$, $K_e$ | 0.05, 0.009 | g/L |
| $\mu_{diff}$ | 5.36 × 10⁻³ | 1/h |
| $\mu_a$ | 3.5 × 10⁻³ | 1/h |

**Vacuoles.** Vacuoles form in $A_1$ (rate constant $\mu_v = 1.71 \times 10^{-4}$ 1/h) and grow through ten
size classes ($n_0 \ldots n_9$, radii from 1.5 × 10⁻⁴ cm in steps of 0.75 × 10⁻⁴ cm) by advection at velocity
$k_v = 3.22 \times 10^{-5}$ cm/h with a small diffusion term ($D = 2.66 \times 10^{-11}$ cm²/h), discretised
with central differences. Vacuoles that grow out of the last class turn $A_1$ into $A_3$ (the rate $r_v$
below). They accumulate in $n_m$, which decays at the autolysis rate $\mu_a$. The vacuole volume $v_2$ reduces the producing volume of $A_1$:
$v_{A_1} = A_1 / (2 \rho_{a_1}) - v_2$, with $\rho_{a_1} = A_1 / (A_1/\rho_{a_0} + v_2)$ and
$\rho_{a_0} = 0.35$ g/mL.

## Inhibition terms

IndPenSim models inhibition with smooth switches. Each is close to 1 (no effect) on one side of a threshold and
close to 0 on the other:

| Term | Expression | Acts on | Threshold |
|---|---|---|---|
| $I_{DO_2,X}$ | $\tfrac12[1 - \tanh(0.1\,DO_2^* - DO_2)]$ | growth | DO₂ below 10 % of saturation |
| $I_{DO_2,P}$ | $\tfrac12[1 - \tanh(0.3\,DO_2^* - DO_2)]$ | production | DO₂ below 30 % of saturation |
| $I_N$ | $\tfrac12[1 - \tanh(150 - N)]$ | growth | nitrogen below 150 mg/L |
| $I_{CO_2}$ | $\tfrac12[1 + \tanh(7570 - 1000\,CO_{2,d})]$ | growth | dissolved CO₂ above 7.57 g/L (channel `CO2_d`; [quirks](quirks.md), 2.8) |
| $I_{PAA,X}$ | $\tfrac12[1 + \tanh(2400 - PAA)]$ | growth | PAA above 2400 mg/L (toxicity) |
| $I_{PAA,P}$ | $\tfrac12[1 + \tanh(PAA - 200)]$ | production | PAA below 200 mg/L (precursor shortage) |
| $I_T$ | $k_g e^{-E_g/RT} - k_d e^{-E_d/RT}$ | growth | optimum near 297.5 K |
| $I_{pH}$ | $1 / (1 + [H^+]/K_1 + K_2/[H^+])$ | growth | optimum near pH 6.3 |

Values: $k_g = 450$, $E_g = 14\,880$ J/mol, $k_d = 2.5 \times 10^{29}$, $E_d = 173\,250$ J/mol,
$K_1 = 10^{-5}$ mol/L, $K_2 = 2.5 \times 10^{-8}$ mol/L. For a feel of their size:

| T [K] | 293 | 295 | 297.5 | 300 | 302 | 304 |
|---|---|---|---|---|---|---|
| $I_T$ | 0.97 | 0.99 | 1.00 | 0.98 | 0.93 | 0.82 |

| pH | 5.5 | 6.0 | 6.3 | 6.5 | 7.0 | 7.5 |
|---|---|---|---|---|---|---|
| $I_{pH}$ | 0.76 | 0.89 | 0.91 | 0.90 | 0.79 | 0.56 |

!!! warning "Steep switches"
    The tanh terms in PAA, nitrogen and dissolved O₂ have no scaling of their argument, so they go from 1 to 0
    within about one mg/L. The dissolved-CO₂ term is steeper still: it switches within about 0.001 of `CO2_d`. A batch whose PAA wanders up to 2400 mg/L stops growing almost
    instantly. Near such a switch the trajectory becomes very sensitive to round-off: two solvers, or MATLAB
    and Python, can give batches a few percent apart. That is a property of the model's equations
    ([quirks](quirks.md), section 4).

`SimulationConfig(inhibition=...)` selects IndPenSim's `Inhib` flag. **2** (default) uses all terms. **1**
keeps only the DO₂ and pH terms. **0** switches all of them off and uses a constant hydrolysis rate of
0.003 1/h.

**Growth-rate reset.** With flags 1 and 2, IndPenSim models an irreversible loss of growth capacity. If the
growth rate integrated over a sample (`mu_X_calc`) has fallen in 63 of the last 64 samples, $\mu_{x,max}$ is
reset to 5 × the latest `mu_X_calc`. The samples where this happened are listed in
`result.metadata["growth_rate_resets"]`.

## Penicillin

$$
\frac{dP}{dt} = \underbrace{\mu_p\,\rho_{a_0}\,v_{A_1}\,f_S(S)\,I_{DO_2,P}\,I_{PAA,P}}_{\text{production}}
\;-\; \mu_h P \;-\; D P
$$

- $\mu_p$: maximum specific production rate, drawn per batch, 0.041 ± 0.0025 1/h.
- $f_S(S) = \frac{2.5}{\sqrt{2\pi}} \exp\!\left[-\tfrac12\left(\frac{S - 0.002}{0.0015}\right)^2\right]$ is a
  Gaussian in the substrate concentration [g/L], peaking at 1.0 at **S = 2 mg/L**. This is the model of
  carbon-catabolite repression, and it is why the substrate is held so low.
- $\mu_h = \exp(B_1 + B_2\,\text{pH} + B_3 T + B_4\,\text{pH}^2 + B_5 T^2)$ is the hydrolysis (degradation)
  rate, with $B_{1..5} = -64.29,\ -1.825,\ 0.3649,\ 0.1280,\ -4.9496 \times 10^{-4}$. At pH 6.5 and 298 K,
  $\mu_h \approx 0.0026$ 1/h, a half-life of about 270 h. Penicillin in the vessel decays noticeably over a
  ten-day batch.

## Substrate

$$
\frac{dS}{dt} = -Y_{sX}(r_e + r_b) - r_{m_0} - r_{m_1} - Y_{sP}\,(\text{production})
+ \frac{F_s c_s + F_{oil} c_{oil}}{V} - D S
$$

with $Y_{sX} = 1.85$ g/g, $Y_{sP} = 0.9$ g/g (grams substrate per gram formed), maintenance terms
$r_{m_0} = m_s A_0/(K_{diff} + S)$ and $r_{m_1} = m_s \rho_{a_0} v_{A_1} S/(K_v + S)$ with
$m_s = 0.029$ g/(g h), $K_v = 0.05$ g/L. The sugar feed carries $c_s = 600$ g/L and the oil $c_{oil} = 1000$ g/L
(substrate equivalent). Both are subject to [disturbances](faults.md#disturbances).

## Oxygen

Dissolved oxygen [mg/L]:

$$
\frac{dDO_2}{dt} = -\left(Y_{O_2/X}\frac{dX}{dt} + m_{O_2} X + Y_{O_2/P}\frac{dP}{dt}\right)
+ k_La\,(DO_2^* - DO_2) - D\,DO_2
$$

with $Y_{O_2/X} = 650$ mg/g, $m_{O_2} = 17.5$ mg/(g h), $Y_{O_2/P} = 160$ mg/g. The growth term uses the net
rate of change of total biomass, including dilution, as IndPenSim does.

**Saturation.** $DO_2^* = \bar p\, y_{O_2,in} / H$ with $H = 0.0251$ bar L/mg and $y_{O_2,in} = 0.21$. $\bar p$
is the log-mean of the absolute pressures at the top (1 + back pressure) and the bottom of the liquid
(hydrostatic head of the broth, gas hold-up 10 %). For about 80 m³ of broth this gives $DO_2^* \approx 16$ mg/L
at 0.6 bar back pressure and about 20 mg/L at 1.1 bar. **Back pressure is an oxygen-transfer handle.**

**Mass transfer.**

$$
k_La = \alpha_{k_La}\; v_s^{0.38} \left(\frac{P_t}{V_m}\right)^{0.34} \left(\frac{\mu}{100}\right)^{-0.38}
\left(1 - \left(\frac{F_{oil}}{V}\right)^{0.25}\right)
$$

- $\alpha_{k_La}$: drawn per batch, 85 ± 10.
- $v_s = F_g / (60\,\pi r^2)$: superficial gas velocity [m/s], with $F_g$ in m³/min and $r = 2.1$ m.
- $P_t$: total power input, the gassed agitator power plus the power dissipated by the expanding air. Gassed
  power follows Michel–Miller from the ungassed power $n_{imp} P_o \rho_b N^3 D_{imp}^5$ (three impellers,
  power number 5, $D_{imp} = 1.7$ m, $N = 100$ rpm). $V_m$ is the volume in m³.
- $\mu$: broth viscosity [cP], floored at 1 when it is 4 cP or below.
- The last factor models the reduction of $k_La$ by the oil phase.

**Off-gas.** The head-space O₂ fraction (`O2`) and CO₂ percentage (`CO2outgas`) follow gas balances over the
head space. Air flows in, O₂ is transferred to the broth, and CO₂ is evolved by the $A_0$ and $A_1$ regions at
$q_{CO_2}(A_0 + A_1)V$ with $q_{CO_2} = 0.1353$. From the off-gas compositions the simulator computes the oxygen
uptake rate (`OUR`) and carbon evolution rate (`CER`) as a plant's off-gas analyser would (Goldrick et al., 2015,
eq. 32).

**Dissolved CO₂.**
$dCO_{2,d}/dt = 0.89\,k_La\,(C^*_{CO_2} - CO_{2,d}) - D\,CO_{2,d}$, with
$C^*_{CO_2} = \bar p \cdot CO_{2,out} / H_{CO_2}(T)$ and $H_{CO_2} = \exp(11.25 - 395.9/(T - 175.9))/4400$.

## PAA and nitrogen

$$
\frac{dPAA}{dt} = \frac{F_{PAA} c_{PAA}}{V} - 187.5\,\frac{dP}{dt} - 45\,\frac{dX}{dt} - 1.05\,P - D\,PAA
$$

$$
\frac{dN}{dt} = \frac{F_{PAA} c_{N,PAA} + F_{oil} c_{N,oil}}{V} - 10\,(r_b + r_e + r_d + r_a)
- 80\,\frac{dP}{dt} - 0.03\,X - D N
$$

PAA and N in mg/L. The PAA feed concentration $c_{PAA}$ is drawn per batch (530 ± 20 g/L) and disturbed. The
nitrogen content of the PAA feed is $c_{N,PAA} = 150 \pm 2$ g/L and that of the oil $c_{N,oil} = 20$ g/L. The PAA
feed is therefore also the main nitrogen supply, which is why nitrogen rarely limits growth in IndPenSim
([quirks](quirks.md), 3.5).

## Volume, weight and evaporation

$$
\frac{dV}{dt} = F_s + F_a + F_b + F_w + F_{PAA} - F_{evp} + \frac{F_{dis}}{\rho_b/1000},
\qquad
F_{evp} = V \alpha_{evp}\left(e^{2.5\,(T - 273)/100} - 1\right)
$$

with $\alpha_{evp} = 5.24 \times 10^{-4}$ 1/h (about 35 L/h at 298 K and 80 m³). $F_{dis} \le 0$ is the broth
draw. The broth density is $\rho_b = 1100 + P + X$ kg/m³ (concentrations in g/L). The weight balance adds the
sugar feed at its own density and the oil at 900 kg/m³.

!!! note "As in IndPenSim"
    The oil feed adds to the weight but not to the volume. Treat this as part of the benchmark's definition,
    not as a statement about soybean oil.

## Temperature and heat

The energy balance gives the rate of change of the accumulated heat $Q$, and the temperature follows as
$dT/dt = \dot Q / (V_m\,\rho_b\,c_{p,w})$:

$$
\dot Q = \dot Q_{feed} + \dot Q_{water} - \dot Q_{evp} + \dot Q_{rxn} + P_t
- \dot Q_{cool} - \dot Q_{heat} - U A\,(T - T_{air})
$$

| Term | Model |
|---|---|
| Feeds | Sugar feed and water enter at 288 K ($c_{p}$ 5.9 and 4.18 kJ/(kg K)) |
| Evaporation | $F_{evp}\,\rho_b\,c_{p,w}/1000$ plus the latent heat $F_{evp}\,\rho_w\,\Delta H_{evap}/1000$ ($\Delta H_{evap} = 2430.7$ kJ/kg), as written in IndPenSim |
| Reaction | $25 \cdot V\,(650\,dX/dt + 160\,dP/dt)/1000$, never negative: heat proportional to the oxygen consumed for growth and production |
| Agitation | The power input $P_t$ |
| Coils | $\dot Q_{coil} = \frac{\alpha_1}{1000} F^{\beta+1} \dfrac{T - T_{in}}{F/1000 + \alpha_1 (F/1000)^{\beta} \rho_b c_{p}/2}$, $\alpha_1 = 2451.8$, $\beta = 2.88$; cooling water $F_c$ at $T_{in} = 285$ K (disturbed), hot water $F_h$ at 333 K |
| Losses | $U = 36$, $A = 105$ m², ambient 290 K |

The cooling and heating flows come from the [temperature controller](control.md#temperature-loop).

## pH

The model integrates the hydrogen-ion concentration [H⁺] (mol/L), not pH. Protons are produced in proportion
to the growth, differentiation, autolysis and production rates and to a maintenance term
$m_{pH} X$ with $m_{pH} = 0.0025$ ($\gamma_1 = 3.25 \times 10^{-7}$), and to the
total flow through the vessel ($\gamma_2 = 2.5 \times 10^{-11}$). Acid and base additions are neutralised with
the water equilibrium ($K_w = 10^{-14}$), solved as a quadratic. Above pH 7 the balance is written for OH⁻
instead. The acid and base strength (0.033 mol/L equivalent) is subject to a disturbance. The outputs report
pH.

## Viscosity

$$
\frac{d\mu}{dt} = 3\,A_0^{1/3}\,\sigma_1(t)\,\sigma_2(t) - 0.005\,F_w,
\qquad \sigma_i(t) = \frac{1}{1 + e^{-k_i (t - t_i)}}
$$

with $k_1 = 10^{-3}$, $t_1 = 1$ h, $k_2 = 10^{-4}$, $t_2 = 250$ h. The sigmoids are very flat, so in practice the
viscosity grows as $\approx 0.8\,A_0^{1/3}$ cP/h and **water injection is the operator's viscosity handle**.
Viscosity starts at 4 cP and feeds back on oxygen transfer through $k_La$.
`SimulationConfig(viscosity_from_input=True)` (IndPenSim's `Vis` flag) makes the model use a fixed input
viscosity of 4 cP instead of the simulated one. Through the floor above, $k_La$ then sees 1 cP.

## Numerical safeguards

These are inherited from IndPenSim and kept so that batches match:

- after each sample, any state that is zero or negative is set to 0.001;
- a recorded dissolved oxygen below 2 mg/L is replaced by 1 mg/L, and the next sample starts from it;
- each 12-minute interval is integrated with LSODA (`rtol = 1e-5`, `atol = 1e-7`, maximum step 0.01 h).
  These tolerances are tighter than MATLAB's `ode15s` defaults used by IndPenSim, so Penicillium's own solver
  error is about 100× smaller than MATLAB's ([solver sensitivity](solver_sensitivity.md)).

If the solver fails on an interval, Penicillium raises `SolverError` and does not invent numbers
([FAQ](faq.md#solvererror)).
