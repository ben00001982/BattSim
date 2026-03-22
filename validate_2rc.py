"""
validate_2rc.py
Quick sanity-check for Phase 1: 2RC Thevenin ECM upgrade.

Run from project root:
    python validate_2rc.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from batteries.voltage_model import (
    terminal_voltage, ModelMode, ECMParameters,
    default_ecm_params, bilinear_interp,
)


def _make_test_pack():
    """Minimal stand-in for a BatteryPack for validation purposes."""
    class FakePack:
        pack_capacity_ah = 10.0
        cells_series     = 6
        cells_parallel   = 1
        internal_resistance_mohm = 50.0
        chemistry_id     = "LION21"
    return FakePack()


def main():
    pack = _make_test_pack()
    v_ocv = 24.0      # pack OCV at ~50% SoC
    power = 500.0     # 500 W discharge
    soc   = 50.0
    temp  = 25.0

    print("=" * 60)
    print("  BattSim Phase 1 — 2RC ECM Validation")
    print("=" * 60)

    # ── 1. FAST mode (must match old 3-component Rint behaviour) ─────────────
    vf, if_, rc1f, rc2f, bdf = terminal_voltage(
        power_w=power, soc_pct=soc, temp_c=temp,
        v_ocv_pack=v_ocv, r_pack_mohm=pack.internal_resistance_mohm,
        chem_id=pack.chemistry_id, capacity_ah=pack.pack_capacity_ah,
        cells_series=pack.cells_series, cells_parallel=pack.cells_parallel,
        mode=ModelMode.FAST,
    )
    print(f"\n[FAST]     V_term={vf:.4f} V  I={if_:.3f} A  v_rc1={rc1f}  v_rc2={rc2f}")
    print(f"           dv_ohmic={bdf['dv_ohmic']:.4f} V  dv_ct={bdf['dv_ct']:.4f} V"
          f"  dv_conc={bdf['dv_conc']:.4f} V")
    assert rc1f == 0.0 and rc2f == 0.0, "FAST mode must return zero RC states"

    # ── 2. STANDARD mode (2RC with default params) ───────────────────────────
    vs, is_, rc1s, rc2s, bds = terminal_voltage(
        power_w=power, soc_pct=soc, temp_c=temp,
        v_ocv_pack=v_ocv, r_pack_mohm=pack.internal_resistance_mohm,
        chem_id=pack.chemistry_id, capacity_ah=pack.pack_capacity_ah,
        cells_series=pack.cells_series, cells_parallel=pack.cells_parallel,
        mode=ModelMode.STANDARD, dt_s=1.0,
    )
    print(f"\n[STANDARD] V_term={vs:.4f} V  I={is_:.3f} A  v_rc1={rc1s:.5f}  v_rc2={rc2s:.5f}")
    print(f"           dv_ohmic={bds['dv_ohmic']:.4f} V  dv_ct={bds['dv_ct']:.4f} V"
          f"  dv_conc={bds['dv_conc']:.4f} V")

    # ── 3. RC state evolution over 10 steps ──────────────────────────────────
    print("\n[STANDARD] RC state evolution (10 steps at steady power):")
    v_rc1, v_rc2 = 0.0, 0.0
    for step in range(10):
        _, _, v_rc1, v_rc2, _ = terminal_voltage(
            power_w=power, soc_pct=soc, temp_c=temp,
            v_ocv_pack=v_ocv, r_pack_mohm=pack.internal_resistance_mohm,
            chem_id=pack.chemistry_id, capacity_ah=pack.pack_capacity_ah,
            cells_series=pack.cells_series, cells_parallel=pack.cells_parallel,
            mode=ModelMode.STANDARD, v_rc1=v_rc1, v_rc2=v_rc2, dt_s=1.0,
        )
        print(f"  step {step+1:2d}: V_RC1={v_rc1:.5f} V  V_RC2={v_rc2:.5f} V")

    # ── 4. bilinear_interp sanity check ──────────────────────────────────────
    ecm = default_ecm_params(pack.internal_resistance_mohm, pack.chemistry_id)
    r0_25 = bilinear_interp(ecm.R0_table, ecm.soc_breakpoints, ecm.temp_breakpoints, 50.0, 25.0)
    r0_m20 = bilinear_interp(ecm.R0_table, ecm.soc_breakpoints, ecm.temp_breakpoints, 50.0, -20.0)
    print(f"\n[ECM]  R0(SoC=50%, T=25C)  = {r0_25:.3f} mOhm")
    print(f"[ECM]  R0(SoC=50%, T=-20C) = {r0_m20:.3f} mOhm  (should be > R0@25C)")
    assert r0_m20 > r0_25, "Cold resistance should exceed reference resistance"

    print("\n[PASS] Phase 1 validation complete.")
    print("Phase 1 complete. Run validate_2rc.py to confirm.")


if __name__ == "__main__":
    main()
