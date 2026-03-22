"""
validate_modes.py
Validates the ArduPilot mode labels implementation (Steps 1–7).

Run from project root:
    python validate_modes.py
"""
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

errors: list[str] = []


# ── 1. ardupilot_modes module ─────────────────────────────────────────────────
print("1. ardupilot_modes module")
from batteries.ardupilot_modes import (
    ALL_MODES, COPTER_MODES, PLANE_MODES, POWER_CATEGORIES,
    ALL_VALID_PHASE_TYPES, MODE_TO_CATEGORY,
    mode_name_to_category, copter_num_to_name, plane_num_to_name,
    modes_by_vehicle, modes_by_category,
)

for name, mode in ALL_MODES.items():
    if name != mode.name:
        errors.append(f"  ALL_MODES key mismatch: '{name}' != mode.name '{mode.name}'")
    if mode.power_category not in POWER_CATEGORIES:
        errors.append(f"  Mode '{name}': unknown power_category '{mode.power_category}'")

print(f"   ALL_MODES: {len(ALL_MODES)} modes")
print(f"   COPTER_MODES: {len(COPTER_MODES)} modes")
print(f"   PLANE_MODES: {len(PLANE_MODES)} modes")
print(f"   ALL_VALID_PHASE_TYPES: {len(ALL_VALID_PHASE_TYPES)} types")

# Specific lookups
assert copter_num_to_name(5)  == "LOITER",  f"Expected LOITER, got {copter_num_to_name(5)}"
assert copter_num_to_name(9)  == "LAND",    f"Expected LAND, got {copter_num_to_name(9)}"
assert copter_num_to_name(17) == "THROW",   f"Expected THROW, got {copter_num_to_name(17)}"
assert copter_num_to_name(999) == "UNKNOWN"

assert plane_num_to_name(22) == "QLAND",   f"Expected QLAND, got {plane_num_to_name(22)}"
assert plane_num_to_name(0)  == "MANUAL",  f"Expected MANUAL, got {plane_num_to_name(0)}"
assert plane_num_to_name(5)  == "FLY_BY_WIRE_A"

# mode_name_to_category
assert mode_name_to_category("LOITER")  == "HOVER"
assert mode_name_to_category("HOVER")   == "HOVER",   "category should pass through"
assert mode_name_to_category("LAND")    == "LAND",    "LAND is both category and mode"
assert mode_name_to_category("AUTO")    in POWER_CATEGORIES
assert mode_name_to_category("THROW")  == "TAKEOFF"
assert mode_name_to_category("AUTOROTATE") == "DESCEND"
assert mode_name_to_category("TOTALLY_UNKNOWN") == "CRUISE"  # fallback

print("   All ardupilot_modes assertions passed.")


# ── 2. models.py — power_for_phase with ArduPilot mode names ─────────────────
print("\n2. models.py — Equipment.power_for_phase()")
from batteries.models import Equipment

dummy = Equipment(
    equip_id="TEST", category="motor", manufacturer="X", model="X",
    nom_voltage_v=22.2, nom_current_a=10.0,
    idle_power_w=50, hover_power_w=300, climb_power_w=400, cruise_power_w=250,
    max_power_w=600, weight_g=200, efficiency_pct=90, duty_cycle_pct=100,
)

# Legacy categories still work
assert dummy.power_for_phase("HOVER")   == 300
assert dummy.power_for_phase("CRUISE")  == 250
assert dummy.power_for_phase("TAKEOFF") == 600
assert dummy.power_for_phase("LAND")    == dummy.hover_power_w * 0.85

# ArduPilot mode names
assert dummy.power_for_phase("LOITER")     == 300,  "LOITER -> HOVER"
assert dummy.power_for_phase("AUTO")       == 250,  "AUTO -> CRUISE"
assert dummy.power_for_phase("THROW")      == 600,  "THROW -> TAKEOFF"
assert dummy.power_for_phase("AUTOROTATE") == dummy.cruise_power_w * 0.70  # DESCEND

# Unknown mode falls back to cruise
assert dummy.power_for_phase("MYSTERY_MODE") == 250

# All valid phase types return non-negative power
for pt in ALL_VALID_PHASE_TYPES:
    pw = dummy.power_for_phase(pt)
    if pw < 0:
        errors.append(f"  phase_type '{pt}' returned negative power: {pw}")

print(f"   All {len(ALL_VALID_PHASE_TYPES)} phase types return non-negative power.")
print("   ArduPilot mode name lookup assertions passed.")


# ── 3. log_importer — no longer exports old dicts ────────────────────────────
print("\n3. log_importer — old module-level dicts removed")
import batteries.log_importer as li

for old_name in ("ARDUPILOT_MODE_MAP", "ARDUPILOT_COPTER_MODES", "ARDUPILOT_PLANE_MODES"):
    if hasattr(li, old_name):
        errors.append(f"  log_importer still exports '{old_name}' — should be removed")
    else:
        print(f"   OK {old_name} correctly removed")

# copter_num_to_name is now imported in log_importer
assert hasattr(li, "copter_num_to_name"), "copter_num_to_name not imported in log_importer"
print("   copter_num_to_name imported correctly")


# ── 4. ui/config.py — PHASE_COLORS includes mode names ───────────────────────
print("\n4. ui/config.py — PHASE_COLORS and PHASE_TYPES")
from ui.config import PHASE_COLORS, PHASE_TYPES, PHASE_DESCRIPTIONS

assert "HOVER"  in PHASE_COLORS, "HOVER missing from PHASE_COLORS"
assert "CRUISE" in PHASE_COLORS, "CRUISE missing from PHASE_COLORS"
assert "LOITER" in PHASE_COLORS, "LOITER (mode name) missing from PHASE_COLORS"
assert "AUTO"   in PHASE_COLORS, "AUTO missing from PHASE_COLORS"
assert "QLAND"  in PHASE_COLORS, "QLAND missing from PHASE_COLORS"

# Mode colors should equal their category color
from ui.config import _CATEGORY_COLORS
assert PHASE_COLORS["LOITER"] == _CATEGORY_COLORS["HOVER"],  "LOITER should have HOVER color"
assert PHASE_COLORS["AUTO"]   == _CATEGORY_COLORS["CRUISE"], "AUTO should have CRUISE color"

assert "LOITER" in PHASE_TYPES, "LOITER missing from PHASE_TYPES"
assert "HOVER"  in PHASE_TYPES, "HOVER missing from PHASE_TYPES (legacy category)"
assert "LOITER" in PHASE_DESCRIPTIONS, "LOITER missing from PHASE_DESCRIPTIONS"

print(f"   PHASE_COLORS: {len(PHASE_COLORS)} entries ({len(ALL_MODES)} modes + categories)")
print(f"   PHASE_TYPES: {len(PHASE_TYPES)} types")
print("   All ui/config assertions passed.")


# ── 5. database.py — _validate_phase_type ────────────────────────────────────
print("\n5. database.py — _validate_phase_type()")
from batteries.database import BatteryDatabase

db_dummy = BatteryDatabase.__new__(BatteryDatabase)  # skip __init__

assert db_dummy._validate_phase_type("HOVER",   "M1", "Test") == "HOVER"
assert db_dummy._validate_phase_type("LOITER",  "M1", "Test") == "LOITER"
assert db_dummy._validate_phase_type("hover",   "M1", "Test") == "HOVER",  "should uppercase"

with warnings.catch_warnings(record=True) as w_list:
    warnings.simplefilter("always")
    result = db_dummy._validate_phase_type("TOTALLY_BOGUS", "M1", "Test")
    assert result == "CRUISE", f"Expected CRUISE, got {result}"
    assert len(w_list) == 1, f"Expected 1 warning, got {len(w_list)}"
    assert "unknown phase_type" in str(w_list[0].message).lower()

print("   _validate_phase_type() correct: valid->uppercase, invalid->CRUISE+warning")


# ── 6. Legacy compat — simulation still runs ─────────────────────────────────
print("\n6. Legacy compat — run_simulation with legacy phase types")
DB_PATH = Path(__file__).parent / "battery_db.xlsx"
if DB_PATH.exists():
    db = BatteryDatabase(DB_PATH).load()
    pack_id = next(iter(db.packs))
    mission_id = next(iter(db.missions))
    uav_id = next(iter(db.uav_configs))
    pack    = db.packs[pack_id]
    mission = db.missions[mission_id]
    uav     = db.uav_configs[uav_id]

    from mission.simulator import run_simulation
    result = run_simulation(
        pack=pack, mission=mission, uav=uav,
        discharge_pts=db.discharge_pts,
        initial_soc_pct=100, ambient_temp_c=25.0, dt_s=5.0,
    )
    assert result.time_s, "Simulation returned empty time series"
    print(f"   Simulation ran OK: {result.total_duration_s:.0f}s, "
          f"final SoC={result.final_soc:.1f}%")
else:
    print("   (battery_db.xlsx not found — skipping live simulation test)")


# ── Result ────────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"FAILED — {len(errors)} error(s):")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("ArduPilot mode labels complete.")
