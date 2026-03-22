"""
batteries/models.py
Typed dataclasses for UAV Battery Analysis Tool.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Chemistry:
    chem_id: str
    name: str
    short_code: str
    voltage_nominal: float
    voltage_cutoff: float
    energy_density_wh_kg: float
    energy_density_wh_l: float
    specific_power_w_kg: float
    cycle_life: int
    temp_min_c: float
    temp_max_c: float
    self_discharge_pct_month: float
    max_cont_discharge_c: float
    max_pulse_discharge_c: float
    charge_efficiency_pct: float
    safety_rating: str
    relative_cost: str
    notes: str = ""

    def __str__(self) -> str:
        return (f"{self.short_code} ({self.name}): "
                f"{self.voltage_nominal}V nom | "
                f"{self.energy_density_wh_kg} Wh/kg | "
                f"{self.cycle_life} cycles")


@dataclass
class Cell:
    cell_id: str
    manufacturer: str
    model: str
    chemistry_id: str
    cell_format: str
    voltage_nominal: float
    voltage_max: float
    voltage_cutoff: float
    capacity_ah: float
    energy_wh: float
    weight_g: float
    specific_energy_wh_kg: float
    volume_cm3: Optional[float]
    energy_density_wh_l: Optional[float]
    max_cont_discharge_a: float
    max_pulse_discharge_a: float
    max_charge_rate_c: float
    internal_resistance_mohm: float
    cycle_life: int
    notes: str = ""

    @property
    def max_cont_discharge_c(self) -> float:
        return self.max_cont_discharge_a / self.capacity_ah if self.capacity_ah else 0

    def __str__(self) -> str:
        return (f"{self.cell_id}: {self.manufacturer} {self.model} | "
                f"{self.capacity_ah}Ah @ {self.voltage_nominal}V | "
                f"{self.specific_energy_wh_kg:.0f} Wh/kg | "
                f"{self.max_cont_discharge_a}A cont.")


@dataclass
class BatteryPack:
    """
    Represents a complete battery pack — either from the catalog
    or assembled by the Custom_Pack_Builder.
    """
    battery_id: str
    name: str
    cell_id: str
    chemistry_id: str
    cells_series: int
    cells_parallel: int
    # Electrical
    pack_voltage_nom: float
    pack_voltage_max: float
    pack_voltage_cutoff: float
    pack_capacity_ah: float
    pack_energy_wh: float
    # Physical
    pack_weight_g: float
    specific_energy_wh_kg: float
    pack_volume_cm3: Optional[float]
    energy_density_wh_l: Optional[float]
    # Discharge
    max_cont_discharge_a: float
    max_cont_discharge_w: float
    cont_c_rate: float
    internal_resistance_mohm: float
    cycle_life: int
    uav_class: str = ""
    notes: str = ""

    @property
    def total_cells(self) -> int:
        return self.cells_series * self.cells_parallel

    @property
    def pack_weight_kg(self) -> float:
        return self.pack_weight_g / 1000

    def peukert_capacity(self, discharge_current_a: float,
                         peukert_k: float = 1.05) -> float:
        """
        Adjusted capacity using Peukert's law.
        C_adj = C_nom * (I_nom / I_actual)^(k-1)
        Uses 1C discharge as reference.
        """
        if discharge_current_a <= 0:
            return self.pack_capacity_ah
        i_nom = self.pack_capacity_ah  # 1C reference current
        return self.pack_capacity_ah * (i_nom / discharge_current_a) ** (peukert_k - 1)

    def usable_energy_wh(self, depth_of_discharge: float = 0.80) -> float:
        """Usable energy at given DoD (default 80%)."""
        return self.pack_energy_wh * depth_of_discharge

    def __str__(self) -> str:
        return (f"{self.battery_id}: {self.name} | "
                f"{self.cells_series}S{self.cells_parallel}P | "
                f"{self.pack_voltage_nom:.1f}V {self.pack_capacity_ah:.1f}Ah "
                f"({self.pack_energy_wh:.0f}Wh) | "
                f"{self.pack_weight_g:.0f}g")


@dataclass
class DischargePoint:
    """Single point on a discharge curve."""
    chem_id: str
    c_rate: float
    temperature_c: float
    soc_pct: float
    voltage_v: float
    normalised_capacity_pct: float


@dataclass
class Equipment:
    equip_id: str
    category: str
    manufacturer: str
    model: str
    nom_voltage_v: float
    nom_current_a: float
    idle_power_w: float       # minimum draw when powered on but not working
    operating_power_w: float  # normal working draw
    max_power_w: float        # peak draw (e.g. servo slewing, camera capturing)
    weight_g: float
    efficiency_pct: float
    duty_cycle_pct: float
    notes: str = ""
    active: bool = True

    def resolve_power(self, state: str,
                      custom_w: float | None = None,
                      custom_pct: float | None = None) -> float:
        """
        Return watts for a given assignment state.
          "off"    -> 0.0
          "idle"   -> self.idle_power_w
          "on"     -> self.operating_power_w
          "custom" -> custom_w  if custom_w is not None
                      self.max_power_w * custom_pct / 100.0  if custom_pct is not None
                      0.0 as fallback
        Raises ValueError for unknown state strings.
        """
        s = state.lower()
        if s == "off":
            return 0.0
        if s == "idle":
            return self.idle_power_w
        if s == "on":
            return self.operating_power_w
        if s == "custom":
            if custom_w is not None:
                return float(custom_w)
            if custom_pct is not None:
                return self.max_power_w * float(custom_pct) / 100.0
            return 0.0
        raise ValueError(f"Unknown equipment state: '{state}'. "
                         f"Valid states: 'off', 'idle', 'on', 'custom'.")

    def __str__(self) -> str:
        return (f"{self.equip_id} [{self.category}]: "
                f"{self.manufacturer} {self.model} | "
                f"Idle:{self.idle_power_w}W On:{self.operating_power_w}W "
                f"Max:{self.max_power_w}W | "
                f"{self.weight_g}g")


@dataclass
class EquipmentPhaseAssignment:
    """
    Records what state a single piece of equipment is in during one mission phase.
    One row per (mission_id, phase_seq, equipment_id) triplet.
    """
    mission_id:   str
    phase_seq:    int
    equipment_id: str   # matches Equipment.equip_id

    state: str   # "off" | "idle" | "on" | "custom"
                 # "on" means operating_power_w
                 # "custom" uses one of the two custom fields below

    custom_power_w:   float | None = None   # direct watts (only when state="custom")
    custom_power_pct: float | None = None   # % of max_power_w (only when state="custom")
                                            # custom_power_w takes priority if both set

    def effective_power(self, equipment: Equipment) -> float:
        """Convenience wrapper — calls equipment.resolve_power() with this assignment."""
        return equipment.resolve_power(
            self.state, self.custom_power_w, self.custom_power_pct
        )


@dataclass
class UAVConfiguration:
    """
    A UAV defined as a list of (Equipment, quantity) pairs.
    Computes aggregate power and weight.
    """
    uav_id: str
    name: str
    equipment_list: list[tuple[Equipment, int]] = field(default_factory=list)

    def total_weight_g(self) -> float:
        return sum(eq.weight_g * qty for eq, qty in self.equipment_list)

    def phase_power_w(self, phase_type: str = "",
                      overrides: Optional[dict[str, float]] = None) -> float:
        """
        Total power draw at operating level (all equipment ON).
        phase_type argument is accepted for backward compatibility but ignored —
        per-phase distinction is now handled via EquipmentPhaseAssignment.
        overrides: {equip_id: power_w} — override per-item if needed.
        """
        total = 0.0
        for eq, qty in self.equipment_list:
            if overrides and eq.equip_id in overrides:
                pw = overrides[eq.equip_id]
            else:
                pw = eq.operating_power_w
            total += pw * qty
        return total

    def power_breakdown(self, phase_type: str = "") -> dict[str, float]:
        """Return per-equipment power contribution (at operating level)."""
        return {
            eq.equip_id: eq.operating_power_w * qty
            for eq, qty in self.equipment_list
        }

    def __str__(self) -> str:
        return (f"{self.uav_id}: {self.name} | "
                f"{len(self.equipment_list)} items | "
                f"{self.total_weight_g():.0f}g total")


@dataclass
class MissionPhase:
    mission_id: str
    mission_name: str
    uav_config_id: str
    phase_seq: int
    phase_name: str
    phase_type: str          # IDLE / TAKEOFF / CLIMB / CRUISE / HOVER / DESCEND / LAND / PAYLOAD_OPS / EMERGENCY
                             # VTOL: VTOL_TRANSITION / VTOL_HOVER / FW_CRUISE / FW_CLIMB / FW_DESCEND
    duration_s: float
    distance_m: float = 0.0
    altitude_m: float = 0.0
    airspeed_ms: float = 0.0
    power_override_w: Optional[float] = None
    notes: str = ""

    def effective_power_w(self, uav: Optional[UAVConfiguration] = None) -> float:
        """Return power: override if set, else compute from UAV config (all ON)."""
        if self.power_override_w is not None:
            return self.power_override_w
        if uav is not None:
            return uav.phase_power_w()
        return 0.0

    def energy_wh(self, uav: Optional[UAVConfiguration] = None) -> float:
        return self.effective_power_w(uav) * self.duration_s / 3600


@dataclass
class MissionProfile:
    """Complete ordered mission made of phases."""
    mission_id: str
    mission_name: str
    uav_config_id: str
    phases: list[MissionPhase] = field(default_factory=list)
    equipment_assignments: list[EquipmentPhaseAssignment] = field(default_factory=list)

    @property
    def total_duration_s(self) -> float:
        return sum(p.duration_s for p in self.phases)

    @property
    def total_distance_m(self) -> float:
        return sum(p.distance_m for p in self.phases)

    def total_energy_wh(self, uav: Optional[UAVConfiguration] = None) -> float:
        return sum(p.energy_wh(uav) for p in self.phases)

    def assignments_for_phase(self, phase_seq: int) -> list[EquipmentPhaseAssignment]:
        return [a for a in self.equipment_assignments if a.phase_seq == phase_seq]

    def power_profile_w(self, uav: Optional[UAVConfiguration] = None,
                        resolution_s: float = 1.0) -> tuple[list[float], list[float]]:
        """
        Build time-series power profile at given resolution.
        Returns (time_s_list, power_w_list).
        """
        times, powers = [], []
        t = 0.0
        for phase in self.phases:
            pw = phase.effective_power_w(uav)
            end = t + phase.duration_s
            while t < end:
                times.append(t)
                powers.append(pw)
                t += resolution_s
        return times, powers

    def __str__(self) -> str:
        return (f"Mission '{self.mission_name}' ({self.mission_id}): "
                f"{len(self.phases)} phases | "
                f"{self.total_duration_s/60:.1f} min | "
                f"{self.total_distance_m:.0f}m")
