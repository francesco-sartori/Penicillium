"""IndPenSim right-hand side: the ODE system for the industrial penicillin fermentation.

The MATLAB IndPenSim model by Goldrick et al. (2015, 2019): ``indpensim_ode.m`` and ``Parameter_list.m`` of
IndPenSim V2.01 (BSD-3-Clause, Copyright (c) 2016, Stephen Goldrick; see LICENSE). Time is in hours.

The state vector is never modified in place; the pH > 7 branch works on a local copy of the ion concentration.
The ``inhib_flag`` branches for flags 0, 1 and 2 select the inhibition terms as in IndPenSim.

``rhs_into`` is the single source of the model: ``rhs`` calls it, ``penicillium._numba`` compiles it and
``penicillium.jax_model`` rewrites its source for JAX. Keep it in the subset of Python all three accept.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

#: State vector (33 entries). The simulator records each entry as the channel of the same name.
STATE_NAMES: tuple[str, ...] = (
    "S",  # 0  substrate concentration [g/L]
    "DO2",  # 1  dissolved oxygen [mg/L]
    "O2",  # 2  O2 fraction in off-gas [-]
    "P",  # 3  penicillin concentration [g/L]
    "V",  # 4  volume [L]
    "Wt",  # 5  weight [kg]
    "pH",  # 6  H+ concentration [mol/L] (converted to pH in the outputs)
    "T",  # 7  temperature [K]
    "Q",  # 8  generated heat [kJ]
    "Viscosity",  # 9  viscosity [cP]
    "Culture_age",  # 10 integral of biomass [g h/L]
    "a0",  # 11 growing regions of biomass [g/L]
    "a1",  # 12 non-growing regions [g/L]
    "a3",  # 13 degenerated regions [g/L]
    "a4",  # 14 autolysed regions [g/L]
    "n0", "n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9",  # 15-24 vacuole number densities by size class
    "nm",  # 25 maximum vacuole density
    "phi0",  # 26 mean vacuole volume
    "CO2outgas",  # 27 CO2 in off-gas [%]
    "CO2_d",  # 28 dissolved CO2 [mg/L]
    "PAA",  # 29 phenylacetic acid [mg/L]
    "NH3",  # 30 nitrogen [mg/L]
    "mu_P_calc",  # 31 integral of mu_p over the sample interval
    "mu_X_calc",  # 32 integral of mu_e over the sample interval
)  # fmt: skip
N_STATES = len(STATE_NAMES)

#: Parameter and input vector (31 entries), built by ``Simulator._step``.
PARAM_NAMES: tuple[str, ...] = (
    "mu_p", "mux_max", "alpha_kla", "N_conc_paa", "PAA_c",  # 0-4   kinetic parameters of the batch
    "inhib_flag",  # 5  IndPenSim Inhib flag: 0, 1 or 2
    "Fs", "Fg", "RPM", "Fc", "Fh", "Fb", "Fa",  # 6-12  sugar feed, aeration, agitation, cooling, heating, base, acid
    "step1",  # 13 step size of the pH ion balance (h/20, as in IndPenSim)
    "Fw", "pressure", "viscosity",  # 14-16 water, back pressure, input viscosity (used with vis_flag = 1)
    "F_discharge", "Fpaa", "Foil", "NH3_shots",  # 17-20 discharge (negative), PAA, oil, ammonia shots
    "dist_flag",  # 21 disturbances on (1) or off (0)
    "distMuP", "distMuX", "distcs", "distcoil", "distabc", "distPAA", "distTcin", "distO_2in",  # 22-29 this sample
    "vis_flag",  # 30 use the input viscosity instead of the state
)  # fmt: skip
N_PARAMS = len(PARAM_NAMES)


def rhs_into(t, y, par, dy) -> None:
    """Write the time derivative of the IndPenSim state into ``dy`` (length ``N_STATES``).

    Written in the subset of Python that Numba compiles (scalars, indexing, ``math``), so the same source serves
    the pure-Python and the compiled backend; see ``rhs`` and ``penicillium._numba``. ``t`` in hours, ``y`` the
    state (``STATE_NAMES``), ``par`` the parameters and inputs (``PARAM_NAMES``).
    """
    # Kinetic parameters of this batch (mu_p, mux_max and PAA_c also get the disturbances below)
    mu_p, mux_max, alpha_kla, N_conc_paa, PAA_c = par[0], par[1], par[2], par[3], par[4]

    # Biomass and morphology parameters
    ratio_mu_e_mu_b, P_std_dev, mean_P = 0.4, 0.0015, 0.002  # A0 growth vs extension; production vs substrate
    mu_v, mu_a, mu_diff, beta_1 = 1.71e-4, 3.5e-3, 5.36e-3, 0.006  # vacuolation, autolysis, differentiation [1/h]
    K_b, K_diff_L, K_e, K_v = 0.05, 0.09, 0.009, 0.05  # saturation constants [g/L]; K_diff floor
    delta_r, k_v, D = 0.75e-4, 3.22e-5, 2.66e-11  # vacuole size class width [cm], growth velocity, diffusion
    rho_a0, rho_d, r_0, delta_0 = 0.35, 0.18, 1.5e-4, 1e-4  # densities; smallest vacuole radius and width [cm]

    # Process parameters: yields and maintenance, feeds, vessel and aeration
    Y_sX, Y_sP, m_s, c_oil, c_s = 1.85, 0.9, 0.029, 1000, 600
    Y_O2_X, Y_O2_P, m_O2_X = 650, 160, 17.5
    a, b, c, d = 0.38, 0.34, -0.38, 0.25  # kLa exponents
    Henrys_c, n_imp, r, r_imp, Po, epsilon, R = 0.0251, 3, 2.1, 0.85, 5, 0.1, 8.314

    # Inhibition switches, temperatures [K] and heat transfer
    X_crit_DO2, P_crit_DO2, A_inhib = 0.1, 0.3, 1
    Tf, Tw, Tcin, Th, Tair = 288, 288, 285, 333, 290
    C_ps, C_pw, dealta_H_evap, U_jacket, A_c = 5.9, 4.18, 2430.7, 36, 105
    Eg, Ed, k_g, k_d, Y_QX = 14880, 173250, 450, 2.5e29, 25

    # pH, nitrogen, PAA and hydrolysis
    abc, gamma1, gamma2, m_ph, K1, K2 = 0.033, 0.0325e-5, 2.5e-11, 0.0025, 1e-5, 2.5e-8
    N_conc_oil, N_conc_shot, Y_NX, Y_NP, m_N, X_crit_N = 20000, 400000, 10, 80, 0.03, 150
    Y_PAA_P, Y_PAA_X, m_PAA, X_crit_PAA, P_crit_PAA = 187.5, 45, 1.05, 2400, 200
    B_1, B_2, B_3, B_4, B_5 = -64.29, -1.825, 0.3649, 0.1280, -4.9496e-04

    # CO2, viscosity, evaporation, densities and inlet gas
    delta_c_0, k3, k1, k2, t1, t2, q_co2, X_crit_CO2 = 0.89, 0.005, 0.001, 0.0001, 1, 250, 0.1353, 7570
    alpha_evp, beta_T, pho_g, pho_oil, pho_w, pho_paa = 5.2400e-4, 2.88, 1540, 900, 1000, 1000
    O_2_in, N2_in, C_CO2_in, Tv, T0, alpha_1 = 0.21, 0.79, 0.033, 373, 273, 2451.8

    # Process inputs
    Fs = par[6]
    Fg = par[7] / 60
    RPM = par[8]
    Fc = par[9]
    Fh = par[10]
    Fb = par[11]
    Fa = par[12]
    step1 = par[13]
    Fw = par[14]
    Fw = 0 if Fw < 0 else Fw
    pressure = par[15]
    viscosity = y[9] if par[30] == 0 else par[16]
    F_discharge = par[17]
    Fpaa = par[18]
    Foil = par[19]
    NH3_shots = par[20]

    pho_b = 1100 + y[3] + y[11] + y[12] + y[13] + y[14]

    if par[21] == 1:  # process disturbances
        mu_p += par[22]
        mux_max += par[23]
        c_s = c_s + par[24]
        c_oil += par[25]
        abc += par[26]
        PAA_c += par[27]
        Tcin += par[28]
        O_2_in += par[29]

    # Age-dependent term
    A_t1 = y[10] / (y[11] + y[12] + y[13] + y[14])

    s = y[0]
    a_1 = y[12]
    a_0 = y[11]
    a_3 = y[13]
    total_X = y[11] + y[12] + y[13] + y[14]

    # Liquid height in vessel
    h_b = (y[4] / 1000) / (3.141592653589793 * r**2)
    h_b = h_b * (1 - epsilon)

    # Log-mean pressure of vessel
    pressure_bottom = 1 + pressure + pho_b * h_b * 9.81e-5
    pressure_top = 1 + pressure
    total_pressure = (pressure_bottom - pressure_top) / (math.log(pressure_bottom / pressure_top))

    # Minimum value for viscosity (IndPenSim uses < 4 here and <= 4 before the kLa below)
    viscosity = 1 if viscosity < 4 else viscosity
    DOstar_tp = total_pressure * O_2_in / Henrys_c

    # Inhibition terms, IndPenSim ``Inhib`` flag: 2 = DO2, T, pH, CO2, PAA and N (default); 1 = DO2 and pH only;
    # 0 = none, with a constant hydrolysis rate. Each switch is 0.5 (1 +- tanh(...)), from 1 to 0 within ~1 unit.
    inhib_flag = par[5]
    if inhib_flag == 0:
        pH_inhib = NH3_inhib = T_inhib = CO2_inhib = DO_2_inhib_X = DO_2_inhib_P = PAA_inhib_X = PAA_inhib_P = 1.0
        mu_h = 0.003
    else:
        pH_inhib = 1 / (1 + (y[6] / K1) + (K2 / y[6]))
        DO_2_inhib_X = 0.5 * (1 - math.tanh(A_inhib * (X_crit_DO2 * ((total_pressure * O_2_in) / Henrys_c) - y[1])))
        DO_2_inhib_P = 0.5 * (1 - math.tanh(A_inhib * (P_crit_DO2 * ((total_pressure * O_2_in) / Henrys_c) - y[1])))
        if inhib_flag == 1:
            NH3_inhib = T_inhib = CO2_inhib = PAA_inhib_X = PAA_inhib_P = 1.0
        else:
            NH3_inhib = 0.5 * (1 - math.tanh(A_inhib * (X_crit_N - y[30])))
            T_inhib = k_g * math.exp(-(Eg / (R * y[7]))) - k_d * math.exp(-(Ed / (R * y[7])))
            CO2_inhib = 0.5 * (1 + math.tanh(A_inhib * (X_crit_CO2 - y[28] * 1000)))
            PAA_inhib_X = 0.5 * (1 + (math.tanh(X_crit_PAA - y[29])))
            PAA_inhib_P = 0.5 * (1 + (math.tanh(-P_crit_PAA + y[29])))
        pH = -math.log10(y[6])
        mu_h = math.exp((B_1 + B_2 * pH + B_3 * y[7] + B_4 * (pH**2)) + B_5 * (y[7] ** 2))  # penicillin hydrolysis

    # Penicillin inhibition curve: Gaussian in the substrate concentration
    P_inhib = (
        2.5 * P_std_dev * ((P_std_dev * 2.5066282746310002) ** -1 * math.exp(-0.5 * ((s - mean_P) / P_std_dev) ** 2))
    )

    # Specific growth rates of biomass regions with inhibition effect
    mu_a0 = ratio_mu_e_mu_b * mux_max * pH_inhib * NH3_inhib * T_inhib * DO_2_inhib_X * CO2_inhib * PAA_inhib_X
    mu_e = mux_max * pH_inhib * NH3_inhib * T_inhib * DO_2_inhib_X * CO2_inhib * PAA_inhib_X

    K_diff = 0.75 - (A_t1 * beta_1)
    if K_diff < K_diff_L:
        K_diff = K_diff_L

    # Growing A_0 region
    r_b0 = mu_a0 * a_1 * s / (K_b + s)
    r_sb0 = Y_sX * r_b0

    # Non-growing A_1 regions
    r_e1 = (mu_e * a_0 * s) / (K_e + s)
    r_se1 = Y_sX * r_e1

    # Differentiation (A_0 -> A_1)
    r_d1 = mu_diff * a_0 / (K_diff + s)
    r_m0 = m_s * a_0 / (K_diff + s)

    # Total vacuole volume
    v_2 = y[26]
    n = 16
    for k in range(2, 11):
        v_2 += 4.1887902047863905 * (1.5e-4 + (k - 2) * delta_r) ** 3 * y[n] * delta_r
        n += 1
    rho_a1 = a_1 / ((a_1 / rho_a0) + v_2)
    v_a1 = a_1 / (2 * rho_a1) - v_2

    # Penicillin produced from the non-growing A_1 regions
    r_p = mu_p * rho_a0 * v_a1 * P_inhib * DO_2_inhib_P * PAA_inhib_P - mu_h * y[3]

    # Vacuole formation and degeneration
    r_m1 = (m_s * rho_a0 * v_a1 * s) / (K_v + s)
    r_d4 = mu_a * a_3

    # Vacuole number densities: advection-diffusion in vacuole size (central differences over classes 1-9)
    dn0_dt = ((mu_v * v_a1) / (K_v + s)) * (1.909859317102744 * ((r_0 + delta_0) ** -3)) - k_v * y[15]
    for j in range(9):
        n = 16 + j
        dy[n] = -k_v * ((y[n + 1] - y[n - 1]) / (2 * delta_r)) + D * (y[n + 1] - 2 * y[n] + y[n - 1]) / delta_r**2
    n_k = dy[24]  # the derivative of the last size class feeds the maximum-size class...

    r_k = r_0 + 8 * delta_r
    r_m = r_0 + 10 * delta_r

    dn_m_dt = k_v * n_k / (r_m - r_k) - mu_a * y[25]
    n_k = y[24]  # ...while the degeneration term below uses its value (as in indpensim_ode.m)

    dphi_0_dt = ((mu_v * v_a1) / (K_v + s)) - k_v * y[15] * (3.141592653589793 * (r_0 + delta_0) ** 3) / 6

    # Volume and weight
    F_evp = y[4] * alpha_evp * (math.exp(2.5 * (y[7] - T0) / (Tv - T0)) - 1)
    pho_feed = c_s / 1000 * pho_g + (1 - c_s / 1000) * pho_w
    dilution = Fs + Fb + Fa + Fw - F_evp + Fpaa
    dV1 = Fs + Fb + Fa + Fw + F_discharge / (pho_b / 1000) - F_evp + Fpaa
    dWt = Fs * pho_feed / 1000 + pho_oil / 1000 * Foil + Fb + Fa + Fw + F_discharge - F_evp + Fpaa * pho_paa / 1000

    # Biomass regions
    vac_term = (3.141592653589793 * ((r_k + r_m) ** 3) / 6) * rho_d * k_v * n_k
    da_0_dt = r_b0 - r_d1 - y[11] * dilution / y[4]
    da_1_dt = r_e1 - r_b0 + r_d1 - vac_term - y[12] * dilution / y[4]
    da_3_dt = vac_term - r_d4 - y[13] * dilution / y[4]
    da_4_dt = r_d4 - y[14] * dilution / y[4]

    # Penicillin
    dP_dt = r_p - y[3] * dilution / y[4]

    X_1 = da_0_dt + da_1_dt + da_3_dt + da_4_dt
    X_t = y[11] + y[12] + y[13] + y[14]

    # Heat of reaction (never negative)
    Qrxn_X = X_1 * Y_QX * y[4] * Y_O2_X / 1000
    Qrxn_P = dP_dt * Y_QX * y[4] * Y_O2_P / 1000
    Qrxn_t = Qrxn_X + Qrxn_P
    if Qrxn_t < 0:
        Qrxn_t = 0

    # Agitation power: ungassed, then gassed (Michel-Miller)
    N = RPM / 60
    D_imp = 2 * r_imp
    unaerated_power = n_imp * Po * pho_b * (N**3) * (D_imp**5)
    P_g = 0.706 * (((unaerated_power**2) * N * D_imp**3) / (Fg**0.56)) ** 0.45
    P_n = P_g / unaerated_power
    variable_power = (n_imp * Po * pho_b * (N**3) * (D_imp**5) * P_n) / 1000

    # Substrate
    dy[0] = (
        -r_se1
        - r_sb0
        - r_m0
        - r_m1
        - (Y_sP * mu_p * rho_a0 * v_a1 * P_inhib * DO_2_inhib_P * PAA_inhib_P)
        + Fs * c_s / y[4]
        + Foil * c_oil / y[4]
        - y[0] * dilution / y[4]
    )

    # Dissolved oxygen
    V_s = Fg / (3.141592653589793 * r**2)
    T = y[7]
    V = y[4]
    V_m = y[4] / 1000
    P_air = (V_s * R * T * V_m / (22.4 * h_b)) * math.log(1 + pho_b * 9.81 * h_b / (pressure_top * 1e5))
    P_t1 = variable_power + P_air
    viscosity = 1 if viscosity <= 4 else viscosity
    vis_scaled = viscosity / 100
    oil_f = Foil / V
    kla = alpha_kla * ((V_s**a) * ((P_t1 / V_m) ** b) * vis_scaled**c) * (1 - oil_f**d)
    OUR = -X_1 * Y_O2_X - m_O2_X * X_t - dP_dt * Y_O2_P
    OTR = kla * (DOstar_tp - y[1])
    dy[1] = OUR + OTR - (y[1] * dilution / y[4])

    # O2 off-gas
    Vg = epsilon * V_m
    Qfg_in = 85714.28571428572 * Fg
    Qfg_out = Fg * (N2_in / (1 - y[2] - y[27] / 100)) * 85714.28571428572
    dy[2] = (Qfg_in * O_2_in - Qfg_out * y[2] - 0.06 * OTR * V_m) / (Vg * 1293.3035714285716)

    dy[3] = dP_dt
    dy[4] = dV1
    dy[5] = dWt

    # pH (y[6] is the H+ concentration). Above pH 7 the balance is written for OH- and acid and base swap roles.
    pH_dis = Fs + Foil + Fb + Fa + F_discharge + Fw
    h_ion = y[6]
    if -math.log10(h_ion) < 7:
        cb, ca, pH_balance = -abc, abc, 0
    else:
        cb, ca, pH_balance = abc, -abc, 1
        h_ion = 1e-14 / h_ion - h_ion  # OH- minus H+

    B = -(h_ion * y[4] + ca * Fa * step1 + cb * Fb * step1) / (y[4] + Fb * step1 + Fa * step1)

    if pH_balance == 1:
        dy[6] = (
            -gamma1 * (r_b0 + r_e1 + r_d4 + r_d1 + m_ph * total_X)
            - gamma1 * r_p
            - gamma2 * pH_dis
            + ((-B - (B**2 + 4e-14) ** 0.5) / 2 - h_ion)
        )
    else:
        dy[6] = (
            gamma1 * (r_b0 + r_e1 + r_d4 + r_d1 + m_ph * total_X)
            + gamma1 * r_p
            + gamma2 * pH_dis
            + ((-B + (B**2 + 4e-14) ** 0.5) / 2 - h_ion)
        )

    # Temperature: feeds, evaporation, reaction, agitation, cooling and heating coils, jacket losses
    Ws = P_t1
    Qcon = U_jacket * A_c * (y[7] - Tair)
    dQ_dt = (
        Fs * pho_feed * C_ps * (Tf - y[7]) / 1000
        + Fw * pho_w * C_pw * (Tw - y[7]) / 1000
        - F_evp * pho_b * C_pw / 1000
        - dealta_H_evap * F_evp * pho_w / 1000
        + Qrxn_t
        + Ws
        - (alpha_1 / 1000)
        * Fc ** (beta_T + 1)
        * ((y[7] - Tcin) / (Fc / 1000 + (alpha_1 * (Fc / 1000) ** beta_T) / 2 * pho_b * C_ps))
        - (alpha_1 / 1000)
        * Fh ** (beta_T + 1)
        * ((y[7] - Th) / (Fh / 1000 + (alpha_1 * (Fh / 1000) ** beta_T) / 2 * pho_b * C_ps))
        - Qcon
    )
    dy[7] = dQ_dt / ((y[4] / 1000) * C_pw * pho_b)
    dy[8] = dQ_dt

    # Viscosity
    dy[9] = 3 * (a_0 ** (1 / 3)) * (1 / (1 + math.exp(-k1 * (t - t1)))) * (1 / (1 + math.exp(-k2 * (t - t2)))) - k3 * Fw

    # Culture age
    dy[10] = y[11] + y[12] + y[13] + y[14]

    # Hyphae and vacuoles
    dy[11] = da_0_dt
    dy[12] = da_1_dt
    dy[13] = da_3_dt
    dy[14] = da_4_dt
    dy[15] = dn0_dt
    dy[25] = dn_m_dt
    dy[26] = dphi_0_dt

    # CO2 off-gas
    total_X_CO2 = y[11] + y[12]
    CER = total_X_CO2 * q_co2 * V
    dy[27] = (117857.14285714287 * Fg * C_CO2_in + CER - 117857.14285714287 * Fg * y[27]) / (Vg * 1293.3035714285716)

    # Dissolved CO2
    Henrys_c_co2 = (math.exp(11.25 - 395.9 / (y[7] - 175.9))) / 4400
    C_star_CO2 = (total_pressure * y[27]) / Henrys_c_co2
    dy[28] = kla * delta_c_0 * (C_star_CO2 - y[28]) - y[28] * dilution / y[4]

    # PAA
    dy[29] = Fpaa * PAA_c / V - Y_PAA_P * dP_dt - Y_PAA_X * X_1 - m_PAA * y[3] - y[29] * dilution / y[4]

    # Nitrogen
    X_C_nitrogen = (-r_b0 - r_e1 - r_d1 - r_d4) * Y_NX
    P_C_nitrogen = -dP_dt * Y_NP
    dy[30] = (
        (NH3_shots * N_conc_shot) / y[4]
        + X_C_nitrogen
        + P_C_nitrogen
        - m_N * total_X
        + (N_conc_paa * Fpaa / y[4])
        + N_conc_oil * Foil / y[4]
        - y[30] * dilution / y[4]
    )
    # Rate integrals over the sample (the simulator restarts them at 0): mu_P_calc is simply mu_p * 0.2 h.
    dy[31] = mu_p
    dy[32] = mu_e


def rhs(t: float, y: Sequence[float], par: Sequence[float]) -> list[float]:
    """Time derivative of the IndPenSim state.

    Signature follows ``scipy.integrate.odeint(..., tfirst=True)``: ``t`` in hours, ``y`` the state
    (``STATE_NAMES``), ``par`` the parameters and inputs (``PARAM_NAMES``).
    """
    dy = [0.0] * N_STATES
    rhs_into(t, y, par, dy)
    return dy
