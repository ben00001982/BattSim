"""
batteries/voltage_model.py

Physics-based terminal voltage model with three sag components:

  V_terminal = V_ocv(SoC)
             - I × R_ohmic(T)            ← ohmic / electrolyte resistance
             - I × R_ct(T, SoC)          ← charge-transfer / activation polarisation
             - ΔV_conc(I, SoC)           ← concentration polarisation at high DoD

All resistance terms are temperature-dependent via an Arrhenius-type model:

  R(T) = R_ref × exp( B × (1/T_K − 1/T_ref_K) )

where T_ref = 298.15 K (25 °C) and B is a chemistry-specific thermal coefficient.

Since V_terminal depends on I and I = P / V_terminal, the solution at each
timestep uses a fast fixed-point iteration (converges in ≤ 5 steps at 1 °C
resolution and typical UAV C-rates).

A lightweight 1-D lumped thermal model tracks cell temperature based on
Joule heating (I²·R_total) and Newton cooling to ambient.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

T_REF_K = 298.15   # Reference temperature: 25 °C in Kelvin


# ── Per-chemistry electrochemical parameters ──────────────────────────────────

@dataclass
class ChemistryVoltageParams:
    """
    Electrochemical and thermal parameters for a battery chemistry.

    All resistance values are in mΩ per cell (normalised to the reference cell
    internal resistance — scale factors multiply the pack-level IR from the
    Cell_Catalog before applying).

    Attributes
    ----------
    B_ohmic_K      : Arrhenius coefficient for ohmic (electrolyte) resistance [K]
                     Higher = more sensitive to cold.
    B_ct_K         : Arrhenius coefficient for charge-transfer resistance [K]
                     Typically 2–3× larger than B_ohmic.
    R_ct_scale     : Multiplier on the cell's catalog IR to get R_ct at 25 °C.
                     Li-Ion ≈ 0.85, LFP ≈ 1.6 (slower kinetics).
    k_conc         : Concentration-polarisation coefficient [V per C-rate unit].
    n_conc         : C-rate exponent for concentration sag (typically 0.5–1.0).
    k_soc_tail     : Extra charge-transfer rise below 20 % SoC [multiplier].
    thermal_cap_j_per_gK : Specific heat capacity [J/(g·K)] for thermal model.
    h_conv_mW_per_cm2K   : Convective heat transfer coefficient [mW/(cm²·K)].
    cell_surface_area_cm2: Nominal cell surface area [cm²] (scaled by total cells).
    """
    B_ohmic_K: float = 1800.0
    B_ct_K:    float = 3800.0
    R_ct_scale: float = 1.0
    k_conc:    float = 0.012
    n_conc:    float = 0.7
    k_soc_tail: float = 3.0
    thermal_cap_j_per_gK: float = 0.90
    h_conv_mW_per_cm2K:   float = 4.0
    cell_surface_area_cm2: float = 30.0


# Chemistry-specific parameter catalogue
CHEM_VOLTAGE_PARAMS: dict[str, ChemistryVoltageParams] = {

    # LiPo — moderate temp sensitivity; aggressive sag at high C in cold
    "LIPO": ChemistryVoltageParams(
        B_ohmic_K=1800, B_ct_K=3800, R_ct_scale=1.00,
        k_conc=0.012, n_conc=0.70, k_soc_tail=3.0,
        thermal_cap_j_per_gK=0.88, h_conv_mW_per_cm2K=4.0,
        cell_surface_area_cm2=28,
    ),

    # LiHV — same anode/cathode chemistry as LiPo, marginally lower IR
    "LIHV": ChemistryVoltageParams(
        B_ohmic_K=1800, B_ct_K=3700, R_ct_scale=0.95,
        k_conc=0.011, n_conc=0.68, k_soc_tail=2.8,
        thermal_cap_j_per_gK=0.88, h_conv_mW_per_cm2K=4.0,
        cell_surface_area_cm2=26,
    ),

    # Li-Ion NMC 18650 — lower IR than LiPo; good low-T performance
    "LION": ChemistryVoltageParams(
        B_ohmic_K=1600, B_ct_K=3500, R_ct_scale=0.85,
        k_conc=0.010, n_conc=0.65, k_soc_tail=2.5,
        thermal_cap_j_per_gK=0.93, h_conv_mW_per_cm2K=3.5,
        cell_surface_area_cm2=32,
    ),

    # Li-Ion 21700 (NMC) — best of breed; lowest IR; excellent cold performance
    "LION21": ChemistryVoltageParams(
        B_ohmic_K=1550, B_ct_K=3300, R_ct_scale=0.80,
        k_conc=0.009, n_conc=0.62, k_soc_tail=2.2,
        thermal_cap_j_per_gK=0.94, h_conv_mW_per_cm2K=3.5,
        cell_surface_area_cm2=38,
    ),

    # LiFePO4 — very flat OCV; highest Arrhenius coefficients (worst in cold)
    # Solid-electrolyte interphase is thick → strong R_ct temperature rise
    "LIFEPO4": ChemistryVoltageParams(
        B_ohmic_K=2400, B_ct_K=5500, R_ct_scale=1.60,
        k_conc=0.008, n_conc=0.55, k_soc_tail=4.5,
        thermal_cap_j_per_gK=1.05, h_conv_mW_per_cm2K=3.0,
        cell_surface_area_cm2=55,
    ),

    # LTO (Lithium Titanate) — exceptional cold, very low B values
    "LITO": ChemistryVoltageParams(
        B_ohmic_K=900,  B_ct_K=2000, R_ct_scale=0.70,
        k_conc=0.005, n_conc=0.50, k_soc_tail=1.5,
        thermal_cap_j_per_gK=0.98, h_conv_mW_per_cm2K=4.0,
        cell_surface_area_cm2=45,
    ),

    # Semi-Solid-State — thicker electrolyte layer → elevated ohmic B
    "SSS": ChemistryVoltageParams(
        B_ohmic_K=2000, B_ct_K=4000, R_ct_scale=1.10,
        k_conc=0.010, n_conc=0.65, k_soc_tail=2.8,
        thermal_cap_j_per_gK=0.91, h_conv_mW_per_cm2K=3.8,
        cell_surface_area_cm2=30,
    ),

    # All-Solid-State — ceramic electrolyte; high ohmic B; low concentration sag
    "SOLID": ChemistryVoltageParams(
        B_ohmic_K=2800, B_ct_K=6000, R_ct_scale=1.20,
        k_conc=0.006, n_conc=0.50, k_soc_tail=3.5,
        thermal_cap_j_per_gK=0.85, h_conv_mW_per_cm2K=3.2,
        cell_surface_area_cm2=28,
    ),

    # NiMH — high IR; very sensitive to temperature (especially charging)
    "NIMH": ChemistryVoltageParams(
        B_ohmic_K=2200, B_ct_K=4500, R_ct_scale=2.0,
        k_conc=0.015, n_conc=0.80, k_soc_tail=5.0,
        thermal_cap_j_per_gK=1.10, h_conv_mW_per_cm2K=3.5,
        cell_surface_area_cm2=40,
    ),
}

# Fallback to LION if chemistry not found
CHEM_VOLTAGE_PARAMS["DEFAULT"] = CHEM_VOLTAGE_PARAMS["LION"]


# ── Helper: Arrhenius resistance scaling ─────────────────────────────────────

def arrhenius_scale(B_K: float, temp_c: float) -> float:
    """
    Return the multiplicative factor R(T) / R_ref using Arrhenius relation.

      factor = exp( B × (1/T_K − 1/T_ref_K) )

    Values > 1 mean resistance has risen above the 25 °C reference.
    """
    T_K = temp_c + 273.15
    return math.exp(B_K * (1.0 / T_K - 1.0 / T_REF_K))


# ── Resistance components at operating conditions ─────────────────────────────

def r_ohmic_mohm(
    r_pack_mohm: float,
    chem_id: str,
    temp_c: float,
    cells_series: int = 1,   # kept for API compatibility, not used
    cells_parallel: int = 1, # kept for API compatibility, not used
) -> float:
    """
    Pack ohmic resistance at temperature [mΩ].

    ``r_pack_mohm`` is the **pack-level** internal resistance already
    adjusted for S×P topology (as stored in Battery_Catalog).  The function
    only applies the Arrhenius temperature scaling on top of that.
    """
    params = CHEM_VOLTAGE_PARAMS.get(chem_id.upper(),
                                      CHEM_VOLTAGE_PARAMS["DEFAULT"])
    return r_pack_mohm * arrhenius_scale(params.B_ohmic_K, temp_c)


def r_ct_mohm(
    r_pack_mohm: float,
    chem_id: str,
    temp_c: float,
    soc_pct: float,
    cells_series: int = 1,   # kept for API compatibility, not used
    cells_parallel: int = 1, # kept for API compatibility, not used
) -> float:
    """
    Pack charge-transfer resistance at temperature and SoC [mΩ].

    ``r_pack_mohm`` is the **pack-level** IR (S×P already applied).
    Includes an extra rise below ~20 % SoC to model lithium plating / SEI
    thickening at low states of charge.
    """
    params = CHEM_VOLTAGE_PARAMS.get(chem_id.upper(),
                                      CHEM_VOLTAGE_PARAMS["DEFAULT"])
    r_ct   = r_pack_mohm * params.R_ct_scale * arrhenius_scale(params.B_ct_K, temp_c)

    if soc_pct < 20.0:
        tail_factor = 1.0 + params.k_soc_tail * ((20.0 - soc_pct) / 20.0) ** 2
        r_ct *= tail_factor

    return r_ct


def delta_v_concentration(
    current_a: float,
    capacity_ah: float,
    soc_pct: float,
    chem_id: str,
    cells_series: int,
) -> float:
    """
    Concentration-polarisation voltage drop [V] across the pack.
    Scales with C-rate^n_conc and intensifies below ~80 % SoC.
    """
    if current_a <= 0 or capacity_ah <= 0:
        return 0.0
    params  = CHEM_VOLTAGE_PARAMS.get(chem_id.upper(),
                                       CHEM_VOLTAGE_PARAMS["DEFAULT"])
    c_rate  = current_a / capacity_ah
    dod_factor = max(0.0, (80.0 - soc_pct) / 80.0)
    dv_cell = params.k_conc * (c_rate ** params.n_conc) * dod_factor
    return dv_cell * cells_series


# ── Full terminal voltage (one fixed-point solve) ─────────────────────────────

def terminal_voltage(
    power_w: float,
    soc_pct: float,
    temp_c: float,
    v_ocv_pack: float,
    r_pack_mohm: float,
    chem_id: str,
    capacity_ah: float,
    cells_series: int,
    cells_parallel: int,
    max_iter: int = 8,
    tol_v: float = 0.001,
) -> tuple[float, float, dict]:
    """
    Solve terminal voltage and current for a given power demand via
    fixed-point iteration (typically converges in 3–5 steps).

    ``r_pack_mohm`` is the **pack-level** internal resistance (S×P already
    baked in, as stored in Battery_Catalog.internal_resistance_mohm).

    Returns
    -------
    v_term   : float  — terminal voltage [V]
    current  : float  — discharge current [A]
    breakdown: dict   — sag component breakdown for diagnostics
    """
    if power_w <= 0:
        return v_ocv_pack, 0.0, {
            "v_ocv": v_ocv_pack, "dv_ohmic": 0, "dv_ct": 0,
            "dv_conc": 0, "r_ohmic_mohm": 0, "r_ct_mohm_val": 0,
        }

    r_ohm = r_ohmic_mohm(r_pack_mohm, chem_id, temp_c)
    r_ct  = r_ct_mohm(r_pack_mohm, chem_id, temp_c, soc_pct)
    r_total_ohm = (r_ohm + r_ct) / 1000.0   # mΩ → Ω

    v_est = v_ocv_pack
    for _ in range(max_iter):
        if v_est <= 0:
            break
        i_est   = power_w / v_est
        dv_ohm  = i_est * r_total_ohm
        dv_conc = delta_v_concentration(i_est, capacity_ah, soc_pct,
                                        chem_id, cells_series)
        v_new   = v_ocv_pack - dv_ohm - dv_conc
        if abs(v_new - v_est) < tol_v:
            v_est = v_new
            break
        v_est = v_new

    v_term  = max(0.1, v_est)
    current = power_w / v_term

    dv_ohm_f  = current * r_ohm  / 1000.0
    dv_ct_f   = current * r_ct   / 1000.0
    dv_conc_f = delta_v_concentration(current, capacity_ah, soc_pct,
                                      chem_id, cells_series)

    breakdown = {
        "v_ocv":         round(v_ocv_pack, 4),
        "dv_ohmic":      round(dv_ohm_f, 4),
        "dv_ct":         round(dv_ct_f, 4),
        "dv_conc":       round(dv_conc_f, 4),
        "r_ohmic_mohm":  round(r_ohm, 3),
        "r_ct_mohm_val": round(r_ct, 3),
    }
    return v_term, current, breakdown


# ── Thermal model ─────────────────────────────────────────────────────────────

@dataclass
class ThermalState:
    """Mutable thermal state for one simulation step."""
    temp_c: float          # current cell temperature [°C]
    ambient_c: float       # ambient / airstream temperature [°C]
    pack_weight_g: float   # total pack weight (proxy for thermal mass)
    chem_id: str
    total_cells: int       # used to estimate surface area

    def step(self, current_a: float, r_total_mohm: float, dt_s: float = 1.0):
        """
        Advance thermal state by dt_s seconds.

        Heat generation : P_heat = I² × R_total  [W]
        Newton cooling  : P_cool = h × A × ΔT    [W]
        Temperature rise: dT = (P_heat − P_cool) / (m × C_p)
        """
        params = CHEM_VOLTAGE_PARAMS.get(self.chem_id.upper(),
                                          CHEM_VOLTAGE_PARAMS["DEFAULT"])

        r_total_ohm = r_total_mohm / 1000.0
        p_heat = current_a ** 2 * r_total_ohm           # Joule heating [W]

        area_cm2 = params.cell_surface_area_cm2 * self.total_cells
        area_m2  = area_cm2 / 10_000
        h_W_per_m2K = params.h_conv_mW_per_cm2K * 10    # mW/cm² → W/m²
        p_cool   = h_W_per_m2K * area_m2 * (self.temp_c - self.ambient_c)

        thermal_mass_j_per_K = self.pack_weight_g * params.thermal_cap_j_per_gK
        dT = (p_heat - p_cool) * dt_s / thermal_mass_j_per_K

        self.temp_c = round(self.temp_c + dT, 4)
        return p_heat, p_cool


# ── Convenience: R_total at operating point ───────────────────────────────────

def total_pack_resistance_mohm(
    r_pack_mohm: float,
    chem_id: str,
    temp_c: float,
    soc_pct: float,
    cells_series: int = 1,   # kept for API compatibility
    cells_parallel: int = 1, # kept for API compatibility
) -> float:
    """Combined ohmic + charge-transfer resistance [mΩ] at operating point.
    ``r_pack_mohm`` is the pack-level IR (S×P already applied)."""
    return (
        r_ohmic_mohm(r_pack_mohm, chem_id, temp_c)
        + r_ct_mohm(r_pack_mohm, chem_id, temp_c, soc_pct)
    )
