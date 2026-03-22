"""
validate_equipment_model.py
Validates the 3-level equipment power model (Steps 1-7).

Run from project root:
    python validate_equipment_model.py
"""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

errors: list[str] = []


# ── 1. Model imports ──────────────────────────────────────────────────────────
print("1. batteries/models.py — imports and new fields")
from batteries.models import (
    Equipment, EquipmentPhaseAssignment,
    UAVConfiguration, MissionProfile, MissionPhase,
)

# Equipment has the 3 new fields
eq = Equipment(
    equip_id="TEST_MOTORS",
    category="MOTORS_PROPS",
    manufacturer="TestCo",
    model="X5000",
    nom_voltage_v=24.0,
    nom_current_a=10.0,
    idle_power_w=5.0,
    operating_power_w=200.0,
    max_power_w=350.0,
    weight_g=800.0,
    efficiency_pct=90.0,
    duty_cycle_pct=100.0,
)
assert eq.idle_power_w      == 5.0,   "idle_power_w wrong"
assert eq.operating_power_w == 200.0, "operating_power_w wrong"
assert eq.max_power_w       == 350.0, "max_power_w wrong"
assert not hasattr(eq, "hover_power_w"),  "hover_power_w must not exist"
assert not hasattr(eq, "climb_power_w"),  "climb_power_w must not exist"
assert not hasattr(eq, "cruise_power_w"), "cruise_power_w must not exist"
print("   OK Equipment fields")


# ── 2. Equipment.resolve_power() ──────────────────────────────────────────────
print("\n2. Equipment.resolve_power()")
assert eq.resolve_power("off")            == 0.0,   "off state wrong"
assert eq.resolve_power("idle")           == 5.0,   "idle state wrong"
assert eq.resolve_power("on")             == 200.0, "on state wrong"
assert eq.resolve_power("custom", custom_w=123.0) == 123.0, "custom_w wrong"
assert eq.resolve_power("custom", custom_pct=50.0) == 175.0, "custom_pct wrong"
assert eq.resolve_power("custom", custom_w=99.0, custom_pct=50.0) == 99.0, \
    "custom_w should take priority"
try:
    eq.resolve_power("unknown_state")
    errors.append("resolve_power: expected ValueError for unknown state")
except ValueError:
    pass
print("   OK resolve_power all cases")


# ── 3. EquipmentPhaseAssignment ───────────────────────────────────────────────
print("\n3. EquipmentPhaseAssignment")
asgn = EquipmentPhaseAssignment(
    mission_id="M1",
    phase_seq=2,
    equipment_id="TEST_MOTORS",
    state="on",
)
assert asgn.effective_power(eq) == 200.0, "effective_power (on) wrong"

asgn_off = EquipmentPhaseAssignment(
    mission_id="M1",
    phase_seq=2,
    equipment_id="TEST_MOTORS",
    state="off",
)
assert asgn_off.effective_power(eq) == 0.0, "effective_power (off) wrong"
print("   OK EquipmentPhaseAssignment.effective_power()")


# ── 4. UAVConfiguration.phase_power_w() ──────────────────────────────────────
print("\n4. UAVConfiguration.phase_power_w()")
eq2 = Equipment(
    equip_id="CAMERA",
    category="CAMERA",
    manufacturer="Sony",
    model="A7",
    nom_voltage_v=12.0,
    nom_current_a=1.0,
    idle_power_w=3.0,
    operating_power_w=25.0,
    max_power_w=40.0,
    weight_g=300.0,
    efficiency_pct=95.0,
    duty_cycle_pct=80.0,
)
uav = UAVConfiguration(
    uav_id="TEST_UAV",
    name="Test UAV",
    equipment_list=[(eq, 4), (eq2, 1)],  # 4×motors + 1×camera
)
expected_op = 4 * 200.0 + 1 * 25.0
assert uav.phase_power_w() == expected_op, \
    f"phase_power_w() expected {expected_op}, got {uav.phase_power_w()}"
print(f"   OK phase_power_w() = {uav.phase_power_w():.0f} W")


# ── 5. MissionProfile.assignments_for_phase() ────────────────────────────────
print("\n5. MissionProfile.assignments_for_phase()")
ph1 = MissionPhase(
    mission_id="M1", mission_name="Test", uav_config_id="TEST_UAV",
    phase_seq=1, phase_name="Cruise", phase_type="CRUISE",
    duration_s=60.0,
)
ph2 = MissionPhase(
    mission_id="M1", mission_name="Test", uav_config_id="TEST_UAV",
    phase_seq=2, phase_name="Hover", phase_type="HOVER",
    duration_s=30.0,
)
asgn1 = EquipmentPhaseAssignment("M1", 1, "TEST_MOTORS", "on")
asgn2 = EquipmentPhaseAssignment("M1", 2, "CAMERA",      "idle")

mp = MissionProfile(
    mission_id="M1",
    mission_name="Test",
    uav_config_id="TEST_UAV",
    phases=[ph1, ph2],
    equipment_assignments=[asgn1, asgn2],
)
assert len(mp.assignments_for_phase(1)) == 1
assert mp.assignments_for_phase(1)[0].equipment_id == "TEST_MOTORS"
assert len(mp.assignments_for_phase(2)) == 1
assert mp.assignments_for_phase(2)[0].equipment_id == "CAMERA"
print("   OK assignments_for_phase()")


# ── 6. simulator._total_equipment_power() ────────────────────────────────────
print("\n6. mission/simulator._total_equipment_power()")
from mission.simulator import _total_equipment_power

equip_db = {"TEST_MOTORS": eq, "CAMERA": eq2}
asgns_ph1 = [
    EquipmentPhaseAssignment("M1", 1, "TEST_MOTORS", "on"),
    EquipmentPhaseAssignment("M1", 1, "CAMERA",      "off"),
]
total_ph1 = _total_equipment_power(1, uav, equip_db, asgns_ph1)
expected_ph1 = 4 * 200.0 + 1 * 0.0
assert abs(total_ph1 - expected_ph1) < 1e-6, \
    f"_total_equipment_power phase 1 expected {expected_ph1}, got {total_ph1}"

# No assignment for CAMERA in phase 2 → falls back to operating_power_w
asgns_ph2 = [
    EquipmentPhaseAssignment("M1", 2, "TEST_MOTORS", "idle"),
    # CAMERA has no assignment → default "on" (operating_power_w)
]
total_ph2 = _total_equipment_power(2, uav, equip_db, asgns_ph2)
expected_ph2 = 4 * 5.0 + 1 * 25.0  # motors idle + camera fallback operating
assert abs(total_ph2 - expected_ph2) < 1e-6, \
    f"_total_equipment_power phase 2 expected {expected_ph2}, got {total_ph2}"
print(f"   OK _total_equipment_power: phase1={total_ph1:.0f}W  phase2={total_ph2:.0f}W")


# ── 7. run_simulation with equipment_db ──────────────────────────────────────
print("\n7. run_simulation() with equipment_db")
try:
    from mission.simulator import run_simulation, SimulationResult
    from batteries.models import BatteryPack

    pack = BatteryPack(
        battery_id="TEST_PACK",
        name="Test",
        cell_id="TEST",
        chemistry_id="LIPO",
        cells_series=6,
        cells_parallel=1,
        pack_voltage_nom=22.2,
        pack_voltage_max=25.2,
        pack_voltage_cutoff=18.0,
        pack_capacity_ah=5.0,
        pack_energy_wh=111.0,
        pack_weight_g=500.0,
        specific_energy_wh_kg=222.0,
        pack_volume_cm3=None,
        energy_density_wh_l=None,
        max_cont_discharge_a=50.0,
        max_cont_discharge_w=1110.0,
        cont_c_rate=10.0,
        internal_resistance_mohm=15.0,
        cycle_life=300,
    )

    mp_simple = MissionProfile(
        mission_id="M_SIMPLE",
        mission_name="Simple Test",
        uav_config_id="TEST_UAV",
        phases=[ph1],
        equipment_assignments=[
            EquipmentPhaseAssignment("M_SIMPLE", 1, "TEST_MOTORS", "on"),
            EquipmentPhaseAssignment("M_SIMPLE", 1, "CAMERA",      "on"),
        ],
    )

    # Minimal discharge_pts stub
    from batteries.models import DischargePoint
    discharge_pts = [
        DischargePoint("LIPO", 0.1, 25.0, soc_pct=100.0, voltage_v=4.2, normalised_capacity_pct=100.0),
        DischargePoint("LIPO", 0.1, 25.0, soc_pct=50.0,  voltage_v=3.7, normalised_capacity_pct=100.0),
        DischargePoint("LIPO", 0.1, 25.0, soc_pct=0.0,   voltage_v=3.0, normalised_capacity_pct=100.0),
    ]

    result = run_simulation(
        pack=pack,
        mission=mp_simple,
        uav=uav,
        discharge_pts=discharge_pts,
        equipment_db=equip_db,
        dt_s=1.0,
    )
    assert isinstance(result, SimulationResult), "run_simulation must return SimulationResult"
    assert len(result.equipment_power_w) == len(result.time_s), \
        "equipment_power_w must align with time_s"
    assert all(v > 0 for v in result.equipment_power_w), \
        "expected non-zero equipment power"
    print(f"   OK run_simulation: {len(result.time_s)} steps, "
          f"avg equipment_power_w={sum(result.equipment_power_w)/len(result.equipment_power_w):.0f}W")
except Exception as _e:
    errors.append(f"  run_simulation with equipment_db: {_e}")
    print(f"   WARN (non-fatal): {_e}")


# ── 8. run_simulation without equipment_db (backward compat) ─────────────────
print("\n8. run_simulation() backward compat (equipment_db=None)")
try:
    result_bc = run_simulation(
        pack=pack,
        mission=mp_simple,
        uav=uav,
        discharge_pts=discharge_pts,
        equipment_db=None,
        dt_s=1.0,
    )
    assert all(v == 0.0 for v in result_bc.equipment_power_w), \
        "equipment_power_w should be 0 when equipment_db=None"
    print("   OK backward compat: equipment_power_w all 0.0")
except Exception as _e:
    errors.append(f"  backward compat: {_e}")
    print(f"   WARN (non-fatal): {_e}")


# ── Result ────────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"FAILED -- {len(errors)} error(s):")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("Equipment power model complete.")
