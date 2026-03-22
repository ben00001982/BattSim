"""
ui/pages/3_Simulation.py
Run discharge simulations for all batteries selected in analysis_config.json.
Shows time-series charts, phase energy breakdown, and voltage sag analysis.
"""
import sys
from pathlib import Path
_PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

st.set_page_config(page_title="Simulation", page_icon="▶️", layout="wide")

from ui.components.db_helpers import (
    load_db, load_config, plot_sim_timeseries, phase_color, sim_results_to_df
)
from ui.config import PHASE_COLORS, CHEM_COLORS, ACCENT

st.title("▶️ Simulation")
st.caption("Run physics-based discharge simulations for all selected battery packs.")

db = load_db()
cfg = load_config()

# ── Config check ──────────────────────────────────────────────────────────────
if not cfg:
    st.warning("No configuration found. Please set up a mission in **Mission Configurator** first.")
    st.stop()

selected_ids = cfg.get("selected_batteries", [])
mission_id   = cfg.get("mission_id", "")
uav_id       = cfg.get("uav_id", "")
ambient_temp = cfg.get("ambient_temp_c", 25.0)

if not selected_ids:
    st.warning("No batteries selected. Go to **Mission Configurator** to select batteries.")
    st.stop()
if mission_id not in db.missions:
    st.error(f"Mission `{mission_id}` not found in database.")
    st.stop()
if uav_id not in db.uav_configs:
    st.error(f"UAV `{uav_id}` not found in database.")
    st.stop()

mission = db.missions[mission_id]
uav     = db.uav_configs[uav_id]

# Resolve packs (skip missing)
valid_packs = [(pid, db.packs[pid]) for pid in selected_ids if pid in db.packs]
missing     = [pid for pid in selected_ids if pid not in db.packs]

if missing:
    st.warning(f"These pack IDs are in config but not in DB (skipped): {', '.join(missing)}")
if not valid_packs:
    st.error("None of the selected batteries were found in the database.")
    st.stop()

# ── Config summary ────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Mission", mission_id)
col2.metric("UAV", uav_id)
col3.metric("Ambient Temp", f"{ambient_temp} °C")
col4.metric("Batteries", len(valid_packs))

# ── Simulation parameters ─────────────────────────────────────────────────────
with st.expander("Simulation Parameters", expanded=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        dt_s = st.select_slider("Timestep (s)", [0.1, 0.25, 0.5, 1.0, 2.0, 5.0], value=1.0)
        peukert_k = st.slider("Peukert k", 1.00, 1.15, 1.05, 0.01)
    with c2:
        cutoff_soc = st.slider("Cutoff SoC (%)", 0, 20, 10)
        dod_limit  = st.slider("DoD limit (%)", 50, 100, 80)
    with c3:
        initial_soc = st.slider("Initial SoC (%)", 80, 100, 100)
        model_mode_name = st.radio(
            "Voltage model",
            ["FAST", "STANDARD", "PRECISE"],
            index=0,
            help="FAST: Rint (fastest). STANDARD: 2RC ECM with default params. PRECISE: 2RC ECM with fitted params (requires ECM fitting via Log Analysis).",
            key="sim_model_mode",
        )

st.divider()

# ── PRECISE mode pre-run registry check ───────────────────────────────────────
if model_mode_name == "PRECISE":
    from batteries.ecm_store import LogRegistry, get_ecm_with_info as _gwi
    _pre_reg = LogRegistry()
    _pre_reg.load()
    _no_data_packs = []
    for _pid, _ in valid_packs:
        _, _pinfo = _gwi(_pre_reg, _pid, ambient_temp)
        if _pinfo["status"] == "none":
            _no_data_packs.append(_pid)
        elif _pinfo["status"] == "extrapolated":
            st.warning(
                f"PRECISE — **{_pid}**: {_pinfo['description']}"
            )
        elif _pinfo["status"] == "single":
            delta = abs(_pinfo["entries_used"][0]["temperature_c"] - ambient_temp)
            if delta > 5.0:
                st.info(f"PRECISE — **{_pid}**: {_pinfo['description']}")
    if _no_data_packs:
        st.warning(
            f"**PRECISE mode**: no registered ECM log data for "
            f"{', '.join('`' + p + '`' for p in _no_data_packs)}. "
            "These packs will use STANDARD default parameters instead. "
            "Go to **Tools > Log Analysis > Parameter Fitter** to register a log."
        )

# ── Run simulation ────────────────────────────────────────────────────────────
def _get_sim_mode(mode_name: str):
    from batteries.voltage_model import ModelMode
    return {"FAST": ModelMode.FAST, "STANDARD": ModelMode.STANDARD,
            "PRECISE": ModelMode.PRECISE}.get(mode_name, ModelMode.FAST)

def _load_sim_ecm(mode_name: str, pack_id: str):
    if mode_name != "PRECISE":
        return None
    try:
        from batteries.ecm_store import LogRegistry, get_ecm_with_info
        _reg = LogRegistry()
        _reg.load()
        ecm, info = get_ecm_with_info(_reg, pack_id, ambient_temp)
        if "ecm_source_info" not in st.session_state:
            st.session_state["ecm_source_info"] = {}
        st.session_state["ecm_source_info"][pack_id] = info
        return ecm
    except Exception:
        return None

def run_all_simulations():
    from mission.simulator import run_simulation
    results = {}
    progress = st.progress(0, text="Running simulations…")
    for i, (pid, pack) in enumerate(valid_packs):
        progress.progress((i) / len(valid_packs), text=f"Simulating {pid}…")
        try:
            r = run_simulation(
                pack=pack,
                mission=mission,
                uav=uav,
                discharge_pts=db.discharge_pts,
                initial_soc_pct=initial_soc,
                ambient_temp_c=ambient_temp,
                dt_s=dt_s,
                peukert_k=peukert_k,
                cutoff_soc_pct=cutoff_soc,
                dod_limit_pct=dod_limit,
                mode=_get_sim_mode(model_mode_name),
                ecm_params=_load_sim_ecm(model_mode_name, pid),
                equipment_db=db.equipment,
            )
            results[pid] = r
        except Exception as e:
            st.error(f"Simulation failed for {pid}: {e}")
    progress.progress(1.0, text="Done!")
    return results

col_run, col_clear = st.columns([1, 4])
with col_run:
    run_btn = st.button("▶ Run Simulations", type="primary", key="sim_run")
with col_clear:
    if st.button("Clear results", key="sim_clear"):
        st.session_state["sim_results"] = {}
        st.rerun()

if run_btn:
    st.session_state["ecm_source_info"] = {}   # clear stale info before new run
    st.session_state["sim_results"] = run_all_simulations()
    st.rerun()

results = st.session_state.get("sim_results", {})

if not results:
    st.info("Press **Run Simulations** to start.")
    st.stop()

# ── Scorecard ─────────────────────────────────────────────────────────────────
st.subheader("Results Scorecard")
result_list = [results[pid] for pid, _ in valid_packs if pid in results]
pack_list   = [pack for pid, pack in valid_packs if pid in results]

scorecard = sim_results_to_df(result_list, pack_list)

def scorecard_row_style(row):
    color = {"PASS": "#E2EFDA", "MARGINAL": "#FFF2CC", "FAIL": "#FFCCCC"}.get(row["Status"], "#FFFFFF")
    return [f"background-color: {color}"] * len(row)

st.dataframe(
    scorecard.drop(columns=["Depleted"]).style.apply(scorecard_row_style, axis=1).format({
        "Energy (Wh)": "{:.0f}", "Weight (g)": "{:.0f}", "Wh/kg": "{:.1f}",
        "Used (Wh)": "{:.1f}", "Final SoC (%)": "{:.1f}", "Min V (V)": "{:.3f}",
        "Peak Sag (V)": "{:.3f}", "Max I (A)": "{:.1f}", "Max T (°C)": "{:.1f}",
        "Margin (%)": "{:.1f}",
    }),
    use_container_width=True, hide_index=True
)

# ── PRECISE mode ECM source info ───────────────────────────────────────────────
_ecm_info = st.session_state.get("ecm_source_info", {})
if _ecm_info and any(r.model_mode == "PRECISE" for r in result_list):
    _STATUS_STYLE = {
        "interpolated": ("Interpolated",  "#E2EFDA"),
        "extrapolated": ("Extrapolated",  "#FFF2CC"),
        "single":       ("Single entry",  "#DDEEFF"),
        "none":         ("No data (STANDARD used)", "#FFCCCC"),
    }
    with st.expander("PRECISE Mode — ECM Parameter Sources", expanded=True):
        st.caption(
            f"Ambient temperature used for ECM lookup: **{ambient_temp} °C**"
        )
        _rows = []
        for _pid, _info in _ecm_info.items():
            _label, _bg = _STATUS_STYLE.get(_info["status"], ("Unknown", "#FFFFFF"))
            _eu = _info.get("entries_used", [])
            _logs = " + ".join(
                f"{e['log_filename']} ({e['temperature_c']:.1f}°C, {e['fitted_at']})"
                for e in _eu
            ) if _eu else "—"
            _rows.append({
                "Pack":        _pid,
                "Method":      _label,
                "Log(s) used": _logs,
                "Details":     _info["description"],
            })
        _info_df = pd.DataFrame(_rows)
        # Colour each row by resolution method
        _bg_map = {
            "Interpolated":            "#E2EFDA",
            "Extrapolated":            "#FFF2CC",
            "Single entry":            "#DDEEFF",
            "No data (STANDARD used)": "#FFCCCC",
        }

        def _ecm_row_style(row):
            bg = _bg_map.get(row["Method"], "#FFFFFF")
            return [f"background-color: {bg}"] * len(row)

        st.dataframe(
            _info_df.style.apply(_ecm_row_style, axis=1),
            use_container_width=True, hide_index=True,
        )

st.divider()

# ── Time-series charts ────────────────────────────────────────────────────────
st.subheader("Time-Series Charts")

tab_overview, tab_sag, tab_phase, tab_single = st.tabs([
    "All Packs Overview", "Voltage Sag Breakdown", "Phase Energy", "Single Pack Detail"
])

with tab_overview:
    fig = plot_sim_timeseries(result_list, pack_list)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

with tab_sag:
    # Voltage sag breakdown for each pack
    sel_sag_id = st.selectbox("Select pack", [r.pack_id for r in result_list], key="sim_sag_pack")
    r_sag = results.get(sel_sag_id)
    if r_sag and r_sag.dv_ohmic:
        fig_sag, ax_sag = plt.subplots(figsize=(10, 5))
        t = np.array(r_sag.time_s)
        ax_sag.fill_between(t, 0,
                            np.array(r_sag.dv_ohmic),
                            alpha=0.7, label="Ohmic (I·R0)", color="#2196F3")
        ax_sag.fill_between(t,
                            np.array(r_sag.dv_ohmic),
                            np.array(r_sag.dv_ohmic) + np.array(r_sag.dv_ct),
                            alpha=0.7, label="RC1 / Charge-transfer", color="#FF9800")
        ax_sag.fill_between(t,
                            np.array(r_sag.dv_ohmic) + np.array(r_sag.dv_ct),
                            np.array(r_sag.dv_ohmic) + np.array(r_sag.dv_ct) + np.array(r_sag.dv_conc),
                            alpha=0.7, label="RC2 / Concentration", color="#F44336")
        ax_sag.set_xlabel("Time (s)")
        ax_sag.set_ylabel("Voltage Sag (V)")
        ax_sag.set_title(f"{sel_sag_id} — Voltage Sag Breakdown")
        ax_sag.legend(fontsize=9)
        ax_sag.grid(alpha=0.3)
        fig_sag.tight_layout()
        st.pyplot(fig_sag, use_container_width=True)
        plt.close(fig_sag)

        col_s1, col_s2, col_s3 = st.columns(3)
        peak_total = r_sag.peak_sag_v
        col_s1.metric("Peak total sag", f"{peak_total:.3f} V")
        col_s2.metric("Min terminal voltage", f"{r_sag.min_voltage:.3f} V")
        col_s3.metric("Status", "DEPLETED" if r_sag.depleted else "COMPLETED")

with tab_phase:
    # Per-phase energy bar chart for each pack
    sel_phase_id = st.selectbox("Select pack", [r.pack_id for r in result_list], key="sim_phase_pack")
    r_ph = results.get(sel_phase_id)
    if r_ph and r_ph.phase_type:
        # Accumulate energy per phase type
        phase_energy: dict[str, float] = {}
        phase_power:  dict[str, list]  = {}
        prev_ph = r_ph.phase_type[0]
        seg_pw  = []
        seg_soc_start = r_ph.soc_pct[0]
        phase_soc_ranges = []
        for i, ph in enumerate(r_ph.phase_type):
            if ph != prev_ph:
                total_e = sum(p * r_ph.dt_s / 3600 for p in seg_pw)
                phase_energy[prev_ph] = phase_energy.get(prev_ph, 0) + total_e
                phase_soc_ranges.append((prev_ph, seg_soc_start, r_ph.soc_pct[i-1]))
                seg_soc_start = r_ph.soc_pct[i]
                seg_pw = []
                prev_ph = ph
            seg_pw.append(r_ph.power_w[i])
        # Last segment
        total_e = sum(p * r_ph.dt_s / 3600 for p in seg_pw)
        phase_energy[prev_ph] = phase_energy.get(prev_ph, 0) + total_e

        fig_ph, ax_ph = plt.subplots(figsize=(8, 4))
        ph_names = list(phase_energy.keys())
        ph_vals  = list(phase_energy.values())
        ph_cols  = [phase_color(p) for p in ph_names]
        bars = ax_ph.bar(ph_names, ph_vals, color=ph_cols, edgecolor="#666", linewidth=0.5)
        for bar, val in zip(bars, ph_vals):
            ax_ph.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1,
                       f"{val:.1f}", ha="center", fontsize=8)
        ax_ph.set_xlabel("Phase Type")
        ax_ph.set_ylabel("Energy consumed (Wh)")
        ax_ph.set_title(f"{sel_phase_id} — Energy per Phase Type")
        ax_ph.grid(axis="y", alpha=0.3)
        fig_ph.tight_layout()
        st.pyplot(fig_ph, use_container_width=True)
        plt.close(fig_ph)

        phase_rows = [{"Phase": k, "Energy (Wh)": round(v, 2), "% of total": round(v / r_ph.total_energy_consumed_wh * 100, 1)}
                      for k, v in sorted(phase_energy.items(), key=lambda x: -x[1])]
        st.dataframe(pd.DataFrame(phase_rows), use_container_width=True, hide_index=True)

with tab_single:
    sel_single_id = st.selectbox("Select pack", [r.pack_id for r in result_list], key="sim_single_pack")
    r_single = results.get(sel_single_id)
    if r_single:
        p_single = db.packs.get(sel_single_id)
        fig_s, axes_s = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
        t = np.array(r_single.time_s)

        # Phase shading
        for ax in axes_s:
            prev_ph = r_single.phase_type[0] if r_single.phase_type else "CRUISE"
            t_start = t[0]
            for i, ph in enumerate(r_single.phase_type):
                if ph != prev_ph or i == len(r_single.phase_type) - 1:
                    ax.axvspan(t_start, t[i], alpha=0.15,
                               color=phase_color(prev_ph), zorder=0)
                    t_start = t[i]
                    prev_ph = ph

        # SoC + Voltage
        ax1 = axes_s[0]
        ax1.plot(t, r_single.soc_pct, color=ACCENT, linewidth=2, label="SoC (%)")
        ax1_v = ax1.twinx()
        ax1_v.plot(t, r_single.voltage_v, color="#E53935", linewidth=1.5, linestyle="--", label="Voltage (V)", alpha=0.8)
        ax1.set_ylabel("SoC (%)", color=ACCENT)
        ax1_v.set_ylabel("Voltage (V)", color="#E53935")
        ax1.set_title(f"{sel_single_id} — State of Charge & Voltage")
        ax1.set_ylim(0, 110)
        ax1.legend(loc="upper right", fontsize=8)

        # Current
        axes_s[1].plot(t, r_single.current_a, color="#2196F3", linewidth=1.5)
        axes_s[1].set_ylabel("Current (A)")
        axes_s[1].set_title("Discharge Current")
        axes_s[1].grid(alpha=0.3)

        # Temperature
        axes_s[2].plot(t, r_single.temp_c, color="#FF9800", linewidth=1.5)
        axes_s[2].set_xlabel("Time (s)")
        axes_s[2].set_ylabel("Temp (°C)")
        axes_s[2].set_title("Cell Temperature")
        axes_s[2].grid(alpha=0.3)

        fig_s.tight_layout()
        st.pyplot(fig_s, use_container_width=True)
        plt.close(fig_s)

        # Summary metrics
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Final SoC",      f"{r_single.final_soc:.1f} %")
        c2.metric("Energy consumed", f"{r_single.total_energy_consumed_wh:.1f} Wh")
        c3.metric("Min voltage",    f"{r_single.min_voltage:.3f} V")
        c4.metric("Max temp",       f"{r_single.max_temp_c:.1f} °C")
        if r_single.depleted:
            st.error(f"⚠ Battery depleted at {r_single.cutoff_time_s:.0f} s ({r_single.cutoff_reason} cutoff)")
        else:
            st.success("Mission completed without depletion.")
