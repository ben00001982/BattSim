import sys
sys.path.insert(0, '.')

from batteries.database import BatteryDatabase
from batteries.log_importer import generate_synthetic_log, FlightLog
from missions.log_to_mission import (
    MissionSegment, segment_log, to_mission_phases, save_mission
)

db      = BatteryDatabase('battery_db.xlsx').load()
pack    = db.packs[sorted(db.packs.keys())[0]]
mission = db.missions[sorted(db.missions.keys())[0]]
uav     = db.uav_configs[sorted(db.uav_configs.keys())[0]]

print(f"Pack: {pack.battery_id}  Mission: {mission.mission_id}  UAV: {uav.uav_id}")

# 1. Generate synthetic log
print("\n[1] Generating synthetic log...")
log = generate_synthetic_log(
    pack=pack, mission=mission, uav=uav,
    discharge_pts=db.discharge_pts,
    ambient_temp_c=22.0, dt_s=2.0, noise_v=0.03, noise_i=0.8,
)
print(log.summary())

# 2. Segment
print("\n[2] Segmenting...")
segs = segment_log(log, min_duration_s=5.0)
assert len(segs) > 0, "No segments extracted"
for s in segs:
    print(f"  [{s.seq}] {s.mode_name:20s} {s.duration_s:6.1f}s  "
          f"{s.mean_power_w:5.1f}W  conf={s.confidence}")

# 3. ValueError on empty phase_type
print("\n[3] Testing ValueError on empty phase_type...")
_el = FlightLog()
_el.time_s    = [0.0, 1.0, 2.0]
_el.voltage_v = [22.0, 21.9, 21.8]
_el.current_a = [10.0, 10.0, 10.0]
try:
    segment_log(_el)
    assert False, "Should have raised ValueError"
except ValueError:
    print("  ValueError raised correctly")

# 4. Merge — weighted and override
if len(segs) >= 2:
    print("\n[4] Merge test...")
    _a, _b = segs[0], segs[1]
    _dur_total = _a.duration_s + _b.duration_s
    _weighted  = (_a.mean_power_w * _a.duration_s
                  + _b.mean_power_w * _b.duration_s) / _dur_total

    _m_auto = _a.merge_with(_b, override_power_w=None)
    assert abs(_m_auto.mean_power_w - _weighted) < 0.01, "Auto weighted power wrong"
    assert _m_auto.duration_s == _dur_total
    assert _m_auto.energy_wh  == _a.energy_wh + _b.energy_wh

    _m_ovr = _a.merge_with(_b, override_power_w=777.0)
    assert _m_ovr.mean_power_w == 777.0, "Override not applied"
    assert _m_ovr.duration_s   == _dur_total
    print(f"  Auto power: {_m_auto.mean_power_w:.1f}W  Override: {_m_ovr.mean_power_w}W  OK")

# 5. to_mission_phases — both modes
print("\n[5] to_mission_phases — include_power=True...")
phases_with = to_mission_phases(segs, "TEST_LM_WITH", "Test With Power", uav.uav_id,
                                include_power=True)
assert len(phases_with) == len(segs)
for p, s in zip(phases_with, segs):
    assert p.mission_id    == "TEST_LM_WITH"
    assert p.phase_seq     == s.seq
    assert p.phase_type    == s.mode_name
    assert p.uav_config_id == uav.uav_id
    if s.confidence != "low":
        assert p.power_override_w is not None, f"Seq {s.seq}: expected power set"
    else:
        assert p.power_override_w is None, f"Seq {s.seq}: low-conf should be None"
    assert "power not imported" not in (p.notes or "")
print("  include_power=True: column mapping OK")

print("\n[5b] to_mission_phases — include_power=False...")
phases_without = to_mission_phases(segs, "TEST_LM_WITHOUT", "Test Without Power", uav.uav_id,
                                   include_power=False)
assert len(phases_without) == len(segs)
for p in phases_without:
    assert p.power_override_w is None, "include_power=False: all overrides must be None"
    assert "power not imported" in (p.notes or ""), "Notes should flag power-not-imported"
print("  include_power=False: all power_override_w are None  OK")

# 6. save_mission + reload + duplicate check + cleanup
_TEST_ID = "_VALIDATE_LM_TEMP"
if _TEST_ID not in db.missions:
    print(f"\n[6] Saving test mission '{_TEST_ID}'...")
    save_mission(db, phases_with, _TEST_ID, "Validate Test", uav.uav_id)

    db2 = BatteryDatabase('battery_db.xlsx').load()
    assert _TEST_ID in db2.missions
    _saved = db2.missions[_TEST_ID]
    assert len(_saved.phases) == len(phases_with)
    assert _saved.phases[0].phase_type == phases_with[0].phase_type
    print(f"  Saved and reloaded OK — {len(_saved.phases)} phases")

    try:
        save_mission(db2, phases_with, _TEST_ID, "Dup", uav.uav_id)
        assert False, "Should raise ValueError"
    except ValueError:
        print("  Duplicate rejection: OK")

    import openpyxl
    from ui.config import DB_PATH
    _wb = openpyxl.load_workbook(DB_PATH)
    _ws = _wb["Mission_Profiles"]
    for _row in reversed([r for r in _ws.iter_rows(min_row=2, values_only=False)
                           if r[0].value == _TEST_ID]):
        _ws.delete_rows(_row[0].row)
    _wb.save(DB_PATH)
    print("  Test rows cleaned up.")
else:
    print(f"\n[6] Skipping save test — {_TEST_ID} already exists.")

print("\nAll validations passed.")
