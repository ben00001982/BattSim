"""
validate_ecm_store.py
Validates the LogRegistry / get_ecm_for_temperature implementation (Steps 1-5).

Run from project root:
    python validate_ecm_store.py
"""
import sys
import warnings
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).parent))

errors: list[str] = []


# ── 1. Module imports ─────────────────────────────────────────────────────────
print("1. ecm_store imports")
from batteries.ecm_store import (
    LogRegistryEntry, LogRegistry, get_ecm_for_temperature, make_entry,
    _TEMP_THRESHOLD,
)
from batteries.voltage_model import ECMParameters, default_ecm_params
print("   OK imports passed")


# ── Build a reusable ECMParameters fixture ─────────────────────────────────────
def _make_ecm(r0_scale: float = 1.0) -> ECMParameters:
    """Return a default ECM param set, optionally scaled."""
    base = default_ecm_params(20.0, "LION21")
    if r0_scale == 1.0:
        return base
    new_r0 = [[v * r0_scale for v in row] for row in base.R0_table]
    return ECMParameters(
        soc_breakpoints=base.soc_breakpoints,
        temp_breakpoints=base.temp_breakpoints,
        R0_table=new_r0,
        R1_table=base.R1_table,
        C1_table=base.C1_table,
        R2_table=base.R2_table,
        C2_table=base.C2_table,
    )


# ── 2. LogRegistryEntry round-trip ────────────────────────────────────────────
print("\n2. LogRegistryEntry serialisation round-trip")
ecm_a = _make_ecm(1.0)
entry_a = make_entry(
    pack_id="TEST_PACK",
    log_filename="flight001.bin",
    temperature_c=25.0,
    ecm_params=ecm_a,
    fit_summary={"R0_mohm": 10.0, "R1_mohm": 5.0, "tau1_s": 12.0},
    notes="cold morning",
)
assert entry_a.pack_id == "TEST_PACK"
assert entry_a.temperature_c == 25.0
d = entry_a.to_dict()
entry_back = LogRegistryEntry.from_dict(d)
assert entry_back.entry_id == entry_a.entry_id
assert entry_back.temperature_c == 25.0
assert entry_back.fit_summary["R0_mohm"] == 10.0
print("   OK round-trip passed")


# ── 3. LogRegistry add / remove / persist ─────────────────────────────────────
print("\n3. LogRegistry persistence")
with tempfile.TemporaryDirectory() as tmp_dir:
    reg_path = Path(tmp_dir) / "test_registry.json"
    reg = LogRegistry(path=reg_path)
    reg.load()   # empty

    assert reg.all_entries() == []

    reg.add(entry_a)
    assert len(reg.entries_for_pack("TEST_PACK")) == 1

    # Reload from disk
    reg2 = LogRegistry(path=reg_path)
    reg2.load()
    assert len(reg2.entries_for_pack("TEST_PACK")) == 1
    assert reg2.all_entries()[0].entry_id == entry_a.entry_id

    # Remove
    removed = reg2.remove(entry_a.entry_id)
    assert removed is True
    assert len(reg2.entries_for_pack("TEST_PACK")) == 0

    # Second remove returns False
    assert reg2.remove(entry_a.entry_id) is False

    print("   OK persistence, add, remove all passed")


# ── Build a shared in-memory registry for interpolation tests ─────────────────
def _build_registry(entries: list[LogRegistryEntry]) -> LogRegistry:
    with tempfile.TemporaryDirectory() as tmp:
        reg = LogRegistry(path=Path(tmp) / "reg.json")
        for e in entries:
            reg.add(e)
    # Return reg with entries in-memory (file deleted but entries still in _entries)
    return reg


ecm_0c  = _make_ecm(r0_scale=1.20)   # colder -> higher R0
ecm_25c = _make_ecm(r0_scale=1.00)
ecm_45c = _make_ecm(r0_scale=0.85)

entry_0c  = make_entry("PACK_A", "log_0c.bin",  0.0,  ecm_0c,  {"R0_mohm": 24.0})
entry_25c = make_entry("PACK_A", "log_25c.bin", 25.0, ecm_25c, {"R0_mohm": 20.0})
entry_45c = make_entry("PACK_A", "log_45c.bin", 45.0, ecm_45c, {"R0_mohm": 17.0})


# ── Case 1 — interpolation (2 entries within threshold) ────────────────────────
print("\n4. get_ecm_for_temperature — Case 1: interpolation within threshold")
with tempfile.TemporaryDirectory() as tmp:
    reg = LogRegistry(path=Path(tmp) / "r.json")
    reg.add(entry_0c)
    reg.add(entry_25c)

    # Interpolate at 12.5 degrees (midpoint) — within threshold of both
    ecm_mid = get_ecm_for_temperature(reg, "PACK_A", 12.5)
    assert ecm_mid is not None, "Case 1: expected ECMParameters, got None"

    # R0 at midpoint should be between R0_0c and R0_25c (larger table value)
    # Just check it's not None and has tables
    assert ecm_mid.R0_table, "Case 1: R0_table missing"
    print("   OK Case 1: interpolation returned ECMParameters")


# ── Case 2 — extrapolation (no entries within threshold) ─────────────────────
print("\n5. get_ecm_for_temperature — Case 2: extrapolation outside threshold")
with tempfile.TemporaryDirectory() as tmp:
    reg = LogRegistry(path=Path(tmp) / "r.json")
    reg.add(entry_0c)
    reg.add(entry_25c)

    with warnings.catch_warnings(record=True) as w_list:
        warnings.simplefilter("always")
        ecm_hot = get_ecm_for_temperature(reg, "PACK_A", 60.0)   # far outside range
        assert ecm_hot is not None, "Case 2: expected ECMParameters, got None"
        assert len(w_list) >= 1, "Case 2: expected extrapolation warning"
        warn_msg = str(w_list[0].message).lower()
        assert "extrapolat" in warn_msg, f"Case 2: warning text unexpected: {warn_msg}"
    print("   OK Case 2: extrapolation issued warning and returned ECMParameters")


# ── Case 3 — single entry ─────────────────────────────────────────────────────
print("\n6. get_ecm_for_temperature — Case 3: single entry")
with tempfile.TemporaryDirectory() as tmp:
    reg = LogRegistry(path=Path(tmp) / "r.json")
    reg.add(entry_25c)

    # Request near temperature — no warning expected
    with warnings.catch_warnings(record=True) as w_list:
        warnings.simplefilter("always")
        ecm_near = get_ecm_for_temperature(reg, "PACK_A", 28.0)
        assert ecm_near is not None
        user_warnings = [w for w in w_list if issubclass(w.category, UserWarning)]
        assert len(user_warnings) == 0, "Case 3a: unexpected warning for near temperature"

    # Request far temperature — warning expected
    with warnings.catch_warnings(record=True) as w_list:
        warnings.simplefilter("always")
        ecm_far = get_ecm_for_temperature(reg, "PACK_A", -20.0)
        assert ecm_far is not None
        user_warnings = [w for w in w_list if issubclass(w.category, UserWarning)]
        assert len(user_warnings) == 1, f"Case 3b: expected 1 warning, got {len(user_warnings)}"
    print("   OK Case 3: single entry returns ECM, warns only when far")


# ── Case 4 — no entries ───────────────────────────────────────────────────────
print("\n7. get_ecm_for_temperature — Case 4: no entries")
with tempfile.TemporaryDirectory() as tmp:
    reg = LogRegistry(path=Path(tmp) / "r.json")
    ecm_none = get_ecm_for_temperature(reg, "PACK_A", 25.0)
    assert ecm_none is None, f"Case 4: expected None, got {ecm_none}"
    print("   OK Case 4: no entries returns None")


# ── 8. parameter_fitter — build_ecm_parameters_from_log returns 3-tuple ───────
print("\n8. parameter_fitter.build_ecm_parameters_from_log returns 3-tuple")
try:
    from batteries.parameter_fitter import build_ecm_parameters_from_log
    from batteries.log_importer import FlightLog
    import numpy as np

    # Build a minimal synthetic log
    t_arr = list(np.linspace(0, 300, 300))
    v_arr = [24.0 - 0.01 * t for t in t_arr]
    i_arr = [20.0 + 5.0 * np.sin(t / 30) for t in t_arr]
    fl = FlightLog(source_file="synthetic")
    fl.time_s    = t_arr
    fl.voltage_v = v_arr
    fl.current_a = i_arr
    fl.temp_c    = [25.0] * len(t_arr)
    fl.mah_used  = [i * (t_arr[1] - t_arr[0]) / 3.6 for i, t in zip(i_arr, t_arr)]
    fl.soc_pct   = [max(0, 100 - m / 10.0) for m in fl.mah_used]

    class _Pack:
        internal_resistance_mohm = 20.0

    result = build_ecm_parameters_from_log(fl, _Pack(), "LION21")
    assert isinstance(result, tuple) and len(result) == 3, \
        f"Expected 3-tuple, got {type(result)}"
    ecm_out, fit_sum, diag = result
    assert isinstance(ecm_out, ECMParameters), "First element must be ECMParameters"
    assert isinstance(fit_sum, dict), "Second element must be dict"
    assert "R0_mohm" in fit_sum, "fit_summary must contain R0_mohm"
    print(f"   OK 3-tuple: R0={fit_sum.get('R0_mohm')} mO  tau1={fit_sum.get('tau1_s')} s")
except Exception as _e:
    errors.append(f"  build_ecm_parameters_from_log: {_e}")
    print(f"   WARN (non-fatal): {_e}")


# ── Result ────────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"FAILED -- {len(errors)} error(s):")
    for e in errors:
        print(e)
    sys.exit(1)
else:
    print("ECM store replacement complete.")
