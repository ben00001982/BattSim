"""
mission/simulator.py

UAV battery discharge simulation engine.

Each timestep (default 1 s) advances:
  1. Terminal voltage  — via voltage_model.terminal_voltage()
  2. Discharge current — solved simultaneously with V_terminal
  3. SoC              — Peukert-adjusted, temperature-derated
  4. Cell temperature — I²R Joule heating + Newton convective cooling

All results are collected into a SimulationResult for analysis and plotting.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from batteries.models import BatteryPack, MissionProfile, UAVConfiguration
from batteries.discharge import (
    DischargeCurve, peukert_capacity,
    temperature_derate_factor, available_c_rates, closest_c_rate,
)
from batteries.voltage_model import (
    terminal_voltage, ThermalState,
    total_pack_resistance_mohm, CHEM_VOLTAGE_PARAMS,
)


# ── Simulation result container ───────────────────────────────────────────────

@dataclass
class SimulationResult:
    """
    Full time-series output from one simulation run.
    Every list is aligned to the same time axis (one entry per timestep).
    """
    # ── Inputs (stored for reference) ──
    pack_id:       str = ""
    mission_id:    str = ""
    uav_id:        str = ""
    dt_s:          float = 1.0
    initial_soc:   float = 100.0
    ambient_temp_c:float = 25.0
    peukert_k:     float = 1.05
    cutoff_soc:    float = 10.0
    dod_limit:     float = 80.0

    # ── Time-series outputs ──
    time_s:         list[float] = field(default_factory=list)
    soc_pct:        list[float] = field(default_factory=list)
    voltage_v:      list[float] = field(default_factory=list)
    current_a:      list[float] = field(default_factory=list)
    power_w:        list[float] = field(default_factory=list)
    temp_c:         list[float] = field(default_factory=list)
    energy_wh:      list[float] = field(default_factory=list)   # cumulative

    # ── Sag breakdown (sampled at each step) ──
    dv_ohmic:  list[float] = field(default_factory=list)
    dv_ct:     list[float] = field(default_factory=list)
    dv_conc:   list[float] = field(default_factory=list)
    r_total:   list[float] = field(default_factory=list)        # mΩ

    # ── Phase labels ──
    phase_type: list[str] = field(default_factory=list)

    # ── Terminal flags ──
    depleted:   bool = False
    cutoff_time_s: Optional[float] = None

    # ── Derived metrics ──────────────────────────────────────────────────────

    @property
    def total_duration_s(self) -> float:
        return self.time_s[-1] if self.time_s else 0.0

    @property
    def total_energy_consumed_wh(self) -> float:
        return self.energy_wh[-1] if self.energy_wh else 0.0

    @property
    def final_soc(self) -> float:
        return self.soc_pct[-1] if self.soc_pct else self.initial_soc

    @property
    def min_voltage(self) -> float:
        return min(self.voltage_v) if self.voltage_v else 0.0

    @property
    def max_current(self) -> float:
        return max(self.current_a) if self.current_a else 0.0

    @property
    def max_temp_c(self) -> float:
        return max(self.temp_c) if self.temp_c else self.ambient_temp_c

    @property
    def peak_sag_v(self) -> float:
        """Maximum total voltage sag seen during the mission."""
        if not self.dv_ohmic:
            return 0.0
        return max(o + c + n for o, c, n
                   in zip(self.dv_ohmic, self.dv_ct, self.dv_conc))

    def summary(self) -> str:
        status = "DEPLETED" if self.depleted else "COMPLETED"
        lines = [
            f"{'═'*52}",
            f" Simulation: {self.pack_id} × {self.mission_id}  [{status}]",
            f"{'═'*52}",
            f"  Duration         : {self.total_duration_s:.0f} s  ({self.total_duration_s/60:.1f} min)",
            f"  Energy consumed  : {self.total_energy_consumed_wh:.2f} Wh",
            f"  Initial SoC      : {self.initial_soc:.1f} %",
            f"  Final SoC        : {self.final_soc:.1f} %",
            f"  Min voltage      : {self.min_voltage:.3f} V",
            f"  Max current      : {self.max_current:.1f} A",
            f"  Peak sag total   : {self.peak_sag_v:.3f} V",
            f"  Peak temperature : {self.max_temp_c:.1f} °C",
        ]
        if self.depleted and self.cutoff_time_s:
            lines.append(f"  ⚠ Depleted at     : {self.cutoff_time_s:.0f} s")
        return "\n".join(lines)


# ── Main simulation function ──────────────────────────────────────────────────

def run_simulation(
    pack:            BatteryPack,
    mission:         MissionProfile,
    uav:             UAVConfiguration,
    discharge_pts,                        # list[DischargePoint] from DB
    initial_soc_pct: float = 100.0,
    ambient_temp_c:  float = 25.0,
    dt_s:            float = 1.0,
    peukert_k:       float = 1.05,
    cutoff_soc_pct:  float = 10.0,
    dod_limit_pct:   float = 80.0,
) -> SimulationResult:
    """
    Run a full time-step discharge simulation.

    Parameters
    ----------
    pack            : BatteryPack to simulate
    mission         : MissionProfile defining power demand
    uav             : UAVConfiguration for computing phase power
    discharge_pts   : list of DischargePoint from BatteryDatabase
    initial_soc_pct : starting state of charge [%]
    ambient_temp_c  : ambient / airstream temperature [°C]
    dt_s            : timestep [s]
    peukert_k       : Peukert exponent for capacity correction
    cutoff_soc_pct  : simulation stops at this SoC floor [%]
    dod_limit_pct   : recommended DoD limit — flagged if exceeded

    Returns
    -------
    SimulationResult with full time-series
    """
    chem_id = pack.chemistry_id.upper()

    # ── Build OCV curve (use lowest available C-rate ≈ OCV) ──────────────────
    # Some chemistry variants share discharge data with their parent chemistry
    CHEM_DISCHARGE_FALLBACK = {
        "LION21": "LION",
        "LIHV":   "LIPO",
        "LITO":   "LION",
        "SSS":    "LION",
        "SOLID":  "LION",
        "NIMH":   "LIPO",
    }
    chem_for_curve = chem_id
    avail_c = available_c_rates(discharge_pts, chem_for_curve)
    if not avail_c:
        chem_for_curve = CHEM_DISCHARGE_FALLBACK.get(chem_id, "LION")
        avail_c = available_c_rates(discharge_pts, chem_for_curve)
    if not avail_c:
        raise ValueError(
            f"No discharge profile found for chemistry '{chem_id}' "
            f"(also tried fallback '{chem_for_curve}')"
        )
    ocv_c_rate = min(avail_c)
    ocv_curve  = DischargeCurve(discharge_pts, chem_for_curve, ocv_c_rate, 25.0)
    # Note: OCV is approximated by the low-C-rate cell curve scaled to the pack

    # ── Thermal state ──────────────────────────────────────────────────────────
    thermal = ThermalState(
        temp_c=ambient_temp_c,
        ambient_c=ambient_temp_c,
        pack_weight_g=pack.pack_weight_g,
        chem_id=chem_id,
        total_cells=pack.total_cells,
    )

    # ── Result container ───────────────────────────────────────────────────────
    result = SimulationResult(
        pack_id=pack.battery_id,
        mission_id=mission.mission_id,
        uav_id=uav.uav_id,
        dt_s=dt_s,
        initial_soc=initial_soc_pct,
        ambient_temp_c=ambient_temp_c,
        peukert_k=peukert_k,
        cutoff_soc=cutoff_soc_pct,
        dod_limit=dod_limit_pct,
    )

    soc       = initial_soc_pct
    t         = 0.0
    cum_e_wh  = 0.0

    # ── Time-step loop ─────────────────────────────────────────────────────────
    for phase in mission.phases:
        phase_power_w = phase.effective_power_w(uav)
        phase_steps   = int(round(phase.duration_s / dt_s))

        for _ in range(phase_steps):
            # ── 1. Open-circuit voltage from curve (scaled to pack) ──
            soc_clamped = max(0.0, min(100.0, soc))
            v_ocv_cell  = ocv_curve.voltage_at_soc(soc_clamped)
            v_ocv_pack  = v_ocv_cell * pack.cells_series

            # ── 2. Terminal voltage + current (fixed-point) ──
            v_term, current, breakdown = terminal_voltage(
                power_w=phase_power_w,
                soc_pct=soc_clamped,
                temp_c=thermal.temp_c,
                v_ocv_pack=v_ocv_pack,
                r_pack_mohm=pack.internal_resistance_mohm,
                chem_id=chem_id,
                capacity_ah=pack.pack_capacity_ah,
                cells_series=pack.cells_series,
                cells_parallel=pack.cells_parallel,
            )

            # ── 3. SoC update (Peukert + temperature derating) ──
            t_factor  = temperature_derate_factor(chem_id, thermal.temp_c)
            cap_adj   = peukert_capacity(
                pack.pack_capacity_ah * t_factor, current, peukert_k
            ) if current > 0 else pack.pack_capacity_ah

            delta_soc = (current * dt_s / 3600) / cap_adj * 100.0 \
                        if cap_adj > 0 else 0.0
            soc       = max(cutoff_soc_pct, soc - delta_soc)

            # ── 4. Thermal step ──
            r_tot = total_pack_resistance_mohm(
                pack.internal_resistance_mohm,
                chem_id, thermal.temp_c, soc,
            )
            thermal.step(current, r_tot, dt_s)

            # ── 5. Record ──
            cum_e_wh += phase_power_w * dt_s / 3600.0
            result.time_s.append(round(t, 2))
            result.soc_pct.append(round(soc, 3))
            result.voltage_v.append(round(v_term, 4))
            result.current_a.append(round(current, 3))
            result.power_w.append(round(phase_power_w, 1))
            result.temp_c.append(round(thermal.temp_c, 3))
            result.energy_wh.append(round(cum_e_wh, 4))
            result.dv_ohmic.append(breakdown["dv_ohmic"])
            result.dv_ct.append(breakdown["dv_ct"])
            result.dv_conc.append(breakdown["dv_conc"])
            result.r_total.append(round(r_tot, 2))
            result.phase_type.append(phase.phase_type)

            t += dt_s

            # ── 6. Depletion check ──
            if soc <= cutoff_soc_pct:
                result.depleted = True
                result.cutoff_time_s = t
                return result

    return result


# ── Multi-battery comparison helper ──────────────────────────────────────────

def compare_batteries(
    packs:          list[BatteryPack],
    mission:        MissionProfile,
    uav:            UAVConfiguration,
    discharge_pts,
    ambient_temp_c: float = 25.0,
    peukert_k:      float = 1.05,
    cutoff_soc_pct: float = 10.0,
    dt_s:           float = 1.0,
) -> list[SimulationResult]:
    """Run the same mission for multiple battery packs, return all results."""
    results = []
    for pack in packs:
        r = run_simulation(
            pack=pack,
            mission=mission,
            uav=uav,
            discharge_pts=discharge_pts,
            ambient_temp_c=ambient_temp_c,
            peukert_k=peukert_k,
            cutoff_soc_pct=cutoff_soc_pct,
            dt_s=dt_s,
        )
        results.append(r)
    return results


# ── Temperature sensitivity sweep ────────────────────────────────────────────

def temperature_sweep(
    pack:           BatteryPack,
    mission:        MissionProfile,
    uav:            UAVConfiguration,
    discharge_pts,
    temperatures_c: list[float],
    peukert_k:      float = 1.05,
    cutoff_soc_pct: float = 10.0,
    dt_s:           float = 1.0,
) -> list[SimulationResult]:
    """
    Run the same mission at multiple ambient temperatures.
    Reveals chemistry-specific cold-weather degradation.
    """
    return [
        run_simulation(
            pack=pack,
            mission=mission,
            uav=uav,
            discharge_pts=discharge_pts,
            ambient_temp_c=t,
            peukert_k=peukert_k,
            cutoff_soc_pct=cutoff_soc_pct,
            dt_s=dt_s,
        )
        for t in temperatures_c
    ]
