"""
batteries/builder.py
Build a BatteryPack from a Cell and S×P configuration.
"""
from __future__ import annotations
from batteries.models import Cell, BatteryPack


def build_pack(
    cell: Cell,
    series: int,
    parallel: int,
    pack_id: str = "",
    name: str = "",
    overhead_pct: float = 12.0,
    volume_factor: float = 1.30,
    uav_class: str = "",
    notes: str = "",
) -> BatteryPack:
    """
    Build a BatteryPack from a single cell type in S×P arrangement.

    Args:
        cell:           Source Cell object
        series:         Cells in series (sets voltage)
        parallel:       Cells in parallel (sets capacity)
        pack_id:        Identifier string (auto-generated if empty)
        name:           Descriptive name (auto-generated if empty)
        overhead_pct:   Weight overhead for BMS, wiring, enclosure (%)
        volume_factor:  Volume multiplier for packaging (pack vol / cell vol sum)
        uav_class:      UAV class label
        notes:          Free text notes

    Returns:
        BatteryPack with all calculated fields populated.
    """
    if series < 1 or parallel < 1:
        raise ValueError("Series and parallel counts must be ≥ 1")

    # Auto IDs
    if not pack_id:
        pack_id = f"CUSTOM_{cell.cell_id}_{series}S{parallel}P"
    if not name:
        name = f"{cell.manufacturer} {cell.model} {series}S{parallel}P"

    # Electrical
    v_nom = cell.voltage_nominal * series
    v_max = cell.voltage_max * series
    v_cut = cell.voltage_cutoff * series
    cap_ah = cell.capacity_ah * parallel
    energy_wh = v_nom * cap_ah

    # Physical
    cell_weight_total = cell.weight_g * series * parallel
    pack_weight = cell_weight_total * (1 + overhead_pct / 100)
    spec_energy = energy_wh / (pack_weight / 1000) if pack_weight > 0 else 0

    if cell.volume_cm3:
        vol = cell.volume_cm3 * series * parallel * volume_factor
        e_density = energy_wh / (vol / 1000) if vol > 0 else None
    else:
        vol = None
        e_density = None

    # Discharge
    i_cont = cell.max_cont_discharge_a * parallel
    i_pulse = cell.max_pulse_discharge_a * parallel
    p_cont = v_nom * i_cont
    c_rate_cont = i_cont / cap_ah if cap_ah > 0 else 0

    # Internal resistance: series adds, parallel divides
    ir = cell.internal_resistance_mohm * series / parallel

    return BatteryPack(
        battery_id=pack_id,
        name=name,
        cell_id=cell.cell_id,
        chemistry_id=cell.chemistry_id,
        cells_series=series,
        cells_parallel=parallel,
        pack_voltage_nom=round(v_nom, 2),
        pack_voltage_max=round(v_max, 2),
        pack_voltage_cutoff=round(v_cut, 2),
        pack_capacity_ah=round(cap_ah, 2),
        pack_energy_wh=round(energy_wh, 1),
        pack_weight_g=round(pack_weight, 1),
        specific_energy_wh_kg=round(spec_energy, 1),
        pack_volume_cm3=round(vol, 1) if vol else None,
        energy_density_wh_l=round(e_density, 1) if e_density else None,
        max_cont_discharge_a=round(i_cont, 1),
        max_cont_discharge_w=round(p_cont, 0),
        cont_c_rate=round(c_rate_cont, 2),
        internal_resistance_mohm=round(ir, 2),
        cycle_life=cell.cycle_life,
        uav_class=uav_class,
        notes=notes,
    )


def compare_configurations(
    cell: Cell,
    configs: list[tuple[int, int]],
    overhead_pct: float = 12.0,
) -> list[BatteryPack]:
    """
    Build multiple S×P packs from the same cell for comparison.

    Args:
        cell:    Source cell
        configs: List of (series, parallel) tuples
        overhead_pct: Weight overhead %

    Returns:
        List of BatteryPack objects
    """
    return [
        build_pack(cell, s, p, overhead_pct=overhead_pct)
        for s, p in configs
    ]


def pack_comparison_table(packs: list[BatteryPack]) -> list[dict]:
    """
    Return a list of dicts suitable for pandas DataFrame display.
    """
    return [
        {
            "ID": p.battery_id,
            "Config": f"{p.cells_series}S{p.cells_parallel}P",
            "Voltage (V)": p.pack_voltage_nom,
            "Capacity (Ah)": p.pack_capacity_ah,
            "Energy (Wh)": p.pack_energy_wh,
            "Weight (g)": p.pack_weight_g,
            "Sp. Energy (Wh/kg)": p.specific_energy_wh_kg,
            "Max I cont (A)": p.max_cont_discharge_a,
            "Max P cont (W)": p.max_cont_discharge_w,
            "C-rate cont": p.cont_c_rate,
            "IR (mΩ)": p.internal_resistance_mohm,
            "Cycles": p.cycle_life,
        }
        for p in packs
    ]
