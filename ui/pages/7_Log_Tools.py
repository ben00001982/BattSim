"""
ui/pages/7_Log_Tools.py
Log Tools: Log Analysis, Log Registry, and ECM Parameter Viewer.
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
import tempfile, os

st.set_page_config(page_title="Log Tools", page_icon="📋", layout="wide")

from ui.components.db_helpers import load_db, load_config, reload_db
from ui.config import ACCENT, PHASE_COLORS, PHASE_TYPES as _ALL_PHASE_TYPES

st.title("📋 Log Tools")
st.caption("Log Analysis, Log Registry, ECM Parameter Viewer, and Log → Mission Extractor.")
st.caption("📖 New to BattSim? See **[User Guide → Log Tools](8_User_Guide#log-tools)** and **[Log → Mission](8_User_Guide#log-mission)** for walkthroughs.")

db  = load_db()
cfg = load_config()

tab_log, tab_registry, tab_ecm_viewer, tab_log_mission = st.tabs(
    ["Log Analysis", "Log Registry", "ECM Parameter Viewer", "Log → Mission"]
)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — LOG ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
with tab_log:
    st.subheader("📊 Log Analysis")
    st.caption("Upload ArduPilot flight logs and compare against simulation predictions.")

    uploaded = st.file_uploader(
        "Select flight log file",
        type=["bin", "log", "txt", "csv"],
        help="Supported formats: ArduPilot .bin (requires pymavlink), .log (DataFlash), .csv (Mission Planner export)",
        key="log_uploader",
    )

    vehicle_type = st.radio("Vehicle type", ["copter", "plane"], horizontal=True, key="log_vehicle")
    nom_cap_ah = st.number_input(
        "Battery nominal capacity (Ah) — for SoC calculation (0 to skip)",
        min_value=0.0, max_value=500.0, value=0.0, step=0.1, key="log_capacity"
    )

    # ── Generate synthetic test log ───────────────────────────────────────────
    with st.expander("🧪 Generate Synthetic Test Log", expanded=False):
        st.caption("Create a simulated flight log from a battery pack and mission. "
                   "Useful for testing the analysis workflow without real flight data.")
        pack_ids_cfg  = sorted(db.packs.keys())
        mission_ids_t = sorted(db.missions.keys())
        uav_ids_t     = sorted(db.uav_configs.keys())

        if not (pack_ids_cfg and mission_ids_t and uav_ids_t):
            st.warning("Need at least one pack, mission, and UAV config in the database.")
        else:
            st.caption("Match these parameters to those used on the Simulation page for a close comparison.")

            col_t1, col_t2, col_t3 = st.columns(3)
            with col_t1:
                tl_pack_id    = st.selectbox("Battery pack", pack_ids_cfg, key="tl_pack")
                tl_mission_id = st.selectbox("Mission", mission_ids_t, key="tl_mission")
                tl_uav_id     = st.selectbox("UAV config", uav_ids_t, key="tl_uav")
            with col_t2:
                tl_ambient    = st.number_input("Ambient temp (°C)", -20, 55, 25, key="tl_temp")
                tl_initial_soc = st.slider("Initial SoC (%)", 80, 100, 100, key="tl_soc")
                tl_peukert    = st.slider("Peukert k", 1.00, 1.15, 1.05, 0.01, key="tl_peukert")
            with col_t3:
                tl_noise_v    = st.slider("Voltage noise (V)", 0.0, 0.5, 0.02, 0.01, key="tl_noise_v")
                tl_noise_i    = st.slider("Current noise (A)", 0.0, 5.0, 0.5, 0.1, key="tl_noise_i")
                tl_cutoff_soc = st.slider("Cutoff SoC (%)", 0, 20, 10, key="tl_cutoff")

            if st.button("⚡ Generate Test Log", type="primary", key="tl_generate"):
                try:
                    from batteries.log_importer import generate_synthetic_log
                    tl_pack    = db.packs[tl_pack_id]
                    tl_mission = db.missions[tl_mission_id]
                    tl_uav     = db.uav_configs[tl_uav_id]
                    with st.spinner("Generating synthetic log…"):
                        synth_log = generate_synthetic_log(
                            pack=tl_pack, mission=tl_mission, uav=tl_uav,
                            discharge_pts=db.discharge_pts,
                            ambient_temp_c=tl_ambient,
                            noise_v=tl_noise_v, noise_i=tl_noise_i,
                            initial_soc_pct=float(tl_initial_soc),
                            peukert_k=tl_peukert,
                            cutoff_soc_pct=float(tl_cutoff_soc),
                        )
                    st.session_state["flight_log"] = synth_log
                    st.success(f"Synthetic log generated: {synth_log.total_flight_s:.0f} s, "
                               f"{len(synth_log.time_s)} samples. "
                               f"Scroll down to view the analysis.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to generate log: {e}")

    st.divider()

    log_ready = False

    if uploaded is None:
        if st.session_state.get("flight_log") is not None:
            log = st.session_state["flight_log"]
            src = Path(log.source_file).name if log.source_file else "synthetic"
            st.success(f"Using previously loaded log: `{src}`")
            log_ready = True
        else:
            st.info("Upload a flight log file above, or generate a synthetic test log.")
    else:
        suffix = Path(uploaded.name).suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = Path(tmp.name)
        try:
            from batteries.log_importer import load_log
            with st.spinner(f"Parsing {uploaded.name}…"):
                log = load_log(
                    path=tmp_path,
                    nominal_capacity_ah=nom_cap_ah if nom_cap_ah > 0 else None,
                    vehicle_type=vehicle_type,
                )
            st.session_state["flight_log"] = log
            st.success(f"Loaded {uploaded.name}: {log.total_flight_s:.0f} s, {len(log.time_s)} samples")
            log_ready = True
        except ImportError as e:
            st.error(f"Import error: {e}\nFor .bin files, install pymavlink: `pip install pymavlink`")
        except Exception as e:
            st.error(f"Failed to parse log: {e}")

    if log_ready:
        log = st.session_state["flight_log"]

        st.divider()
        st.subheader("Flight Summary")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Duration",     f"{log.total_flight_s:.0f} s ({log.total_flight_s/60:.1f} min)")
        c2.metric("Samples",      len(log.time_s))
        c3.metric("Peak current", f"{log.peak_current_a:.1f} A")
        c4.metric("Total mAh",    f"{log.total_mah:.0f} mAh")
        c5.metric("Max cell temp",f"{log.max_temp_c:.1f} °C" if log.max_temp_c > -50 else "N/A")

        c6, c7, c8 = st.columns(3)
        c6.metric("Voltage range", f"{log.min_voltage_v:.2f} – {log.initial_voltage:.2f} V")
        c7.metric("Total energy",  f"{log.total_energy_wh:.2f} Wh")
        c8.metric("Source file",   Path(log.source_file).name)

        st.divider()
        st.subheader("Flight Data Charts")

        t_log = np.array(log.time_s)

        tab_volt, tab_curr, tab_soc, tab_temp, tab_phase = st.tabs([
            "Voltage", "Current", "SoC", "Temperature", "Phase Timeline"
        ])

        with tab_volt:
            fig, ax = plt.subplots(figsize=(11, 4))
            if log.voltage_v:
                ax.plot(t_log, log.voltage_v, color="#2196F3", linewidth=1.5, label="Terminal V")
            if any(v > 0 for v in log.voltage_rest_v):
                ax.plot(t_log, log.voltage_rest_v, color="#4CAF50", linewidth=1.2, linestyle="--",
                        label="Resting V", alpha=0.8)
            ax.set_xlabel("Time (s)"); ax.set_ylabel("Voltage (V)")
            ax.set_title("Battery Voltage"); ax.legend(fontsize=9); ax.grid(alpha=0.3)
            fig.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        with tab_curr:
            fig, ax = plt.subplots(figsize=(11, 4))
            if log.current_a:
                ax.plot(t_log, log.current_a, color="#FF9800", linewidth=1.2)
                avg_i = log.avg_current_a
                ax.axhline(avg_i, color="red", linewidth=1, linestyle="--", alpha=0.6,
                           label=f"Avg: {avg_i:.1f} A")
            ax.set_xlabel("Time (s)"); ax.set_ylabel("Current (A)")
            ax.set_title("Discharge Current"); ax.legend(fontsize=9); ax.grid(alpha=0.3)
            fig.tight_layout()
            st.pyplot(fig, use_container_width=True)
            plt.close(fig)

        with tab_soc:
            if log.soc_pct and any(s > 0 for s in log.soc_pct):
                fig, ax = plt.subplots(figsize=(11, 4))
                ax.plot(t_log, log.soc_pct, color=ACCENT, linewidth=1.5)
                ax.set_xlabel("Time (s)"); ax.set_ylabel("SoC (%)")
                ax.set_title("State of Charge"); ax.set_ylim(0, 105); ax.grid(alpha=0.3)
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)
            else:
                st.info("SoC data not available. Provide nominal capacity (Ah) above to compute SoC.")

        with tab_temp:
            valid_temp = [t for t in log.temp_c if t > -50]
            if valid_temp:
                fig, ax = plt.subplots(figsize=(11, 4))
                display_temp = [t if t > -50 else None for t in log.temp_c]
                ax.plot(t_log, display_temp, color="#F44336", linewidth=1.5)
                ax.set_xlabel("Time (s)"); ax.set_ylabel("Temperature (°C)")
                ax.set_title("Battery Temperature"); ax.grid(alpha=0.3)
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)
            else:
                st.info("No temperature data found in this log.")

        with tab_phase:
            if log.phase_type:
                fig, ax = plt.subplots(figsize=(11, 2))
                prev_ph = log.phase_type[0]
                t_start = t_log[0]
                for i, ph in enumerate(log.phase_type):
                    if ph != prev_ph or i == len(log.phase_type) - 1:
                        t_end = t_log[i]
                        ax.barh(0, t_end - t_start, left=t_start, height=1,
                                color=PHASE_COLORS.get(prev_ph, "#CCCCCC"),
                                edgecolor="white", linewidth=0.3)
                        ax.text((t_start + t_end) / 2, 0, prev_ph,
                                ha="center", va="center", fontsize=6)
                        t_start = t_log[i]
                        prev_ph = ph
                ax.set_xlim(t_log[0], t_log[-1])
                ax.set_yticks([])
                ax.set_xlabel("Time (s)")
                ax.set_title("Flight Phase Timeline")
                fig.tight_layout()
                st.pyplot(fig, use_container_width=True)
                plt.close(fig)

                modes_seen = sorted(set(zip(log.flight_mode, log.phase_type)))
                mode_df = pd.DataFrame([{"Flight Mode": m, "Phase Type": p} for m, p in modes_seen])
                st.dataframe(mode_df, use_container_width=True, hide_index=True)
            else:
                st.info("No phase data available.")

        st.divider()
        st.subheader("Simulation Comparison")

        sim_results = st.session_state.get("sim_results", {})
        if not sim_results:
            st.info("No simulation results available. Run a simulation on the **Simulation** page first.")
        else:
            sel_sim_pack = st.selectbox("Compare with simulation for pack",
                                        sorted(sim_results.keys()), key="log_sim_pack")
            r_sim = sim_results[sel_sim_pack]

            fig_cmp, axes_cmp = plt.subplots(2, 2, figsize=(13, 8))
            fig_cmp.suptitle(f"Log vs Simulation — {sel_sim_pack}", fontsize=12, fontweight="bold")
            t_sim = np.array(r_sim.time_s)

            axes_cmp[0, 0].plot(t_sim, r_sim.voltage_v, "b-", linewidth=2, label="Simulation", alpha=0.9)
            if log.voltage_v:
                axes_cmp[0, 0].plot(t_log, log.voltage_v, "r--", linewidth=1.5, label="Real log", alpha=0.8)
            axes_cmp[0, 0].set_title("Terminal Voltage"); axes_cmp[0, 0].set_ylabel("V (V)")
            axes_cmp[0, 0].legend(fontsize=8); axes_cmp[0, 0].grid(alpha=0.3)

            axes_cmp[0, 1].plot(t_sim, r_sim.current_a, "b-", linewidth=2, label="Simulation", alpha=0.9)
            if log.current_a:
                axes_cmp[0, 1].plot(t_log, log.current_a, "r--", linewidth=1.5, label="Real log", alpha=0.8)
            axes_cmp[0, 1].set_title("Discharge Current"); axes_cmp[0, 1].set_ylabel("I (A)")
            axes_cmp[0, 1].legend(fontsize=8); axes_cmp[0, 1].grid(alpha=0.3)

            if log.soc_pct and any(s > 0 for s in log.soc_pct):
                axes_cmp[1, 0].plot(t_sim, r_sim.soc_pct, "b-", linewidth=2, label="Simulation")
                axes_cmp[1, 0].plot(t_log, log.soc_pct, "r--", linewidth=1.5, label="Real log")
                axes_cmp[1, 0].set_title("State of Charge"); axes_cmp[1, 0].set_ylabel("SoC (%)")
                axes_cmp[1, 0].legend(fontsize=8); axes_cmp[1, 0].grid(alpha=0.3)
            else:
                axes_cmp[1, 0].text(0.5, 0.5, "SoC not available\nin log",
                                    ha="center", va="center",
                                    transform=axes_cmp[1, 0].transAxes, fontsize=10)

            if log.voltage_v and len(t_log) > 10:
                v_log_interp = np.interp(t_sim, t_log, np.array(log.voltage_v),
                                          left=log.voltage_v[0], right=log.voltage_v[-1])
                residual = np.array(r_sim.voltage_v) - v_log_interp
                rmse = float(np.sqrt(np.mean(residual ** 2)))
                axes_cmp[1, 1].plot(t_sim, residual, color="purple", linewidth=1.5)
                axes_cmp[1, 1].axhline(0, color="black", linewidth=0.8, linestyle="--")
                axes_cmp[1, 1].fill_between(t_sim, residual, alpha=0.2, color="purple")
                axes_cmp[1, 1].set_title(f"Voltage Residual  RMSE={rmse:.4f} V")
                axes_cmp[1, 1].set_ylabel("ΔV (V)"); axes_cmp[1, 1].grid(alpha=0.3)

            for ax in axes_cmp.flat:
                ax.set_xlabel("Time (s)")
            fig_cmp.tight_layout()
            st.pyplot(fig_cmp, use_container_width=True)
            plt.close(fig_cmp)

            if log.voltage_v and len(t_log) > 10:
                v_log_interp = np.interp(t_sim, t_log, np.array(log.voltage_v),
                                          left=log.voltage_v[0], right=log.voltage_v[-1])
                residual = np.array(r_sim.voltage_v) - v_log_interp
                rmse_v = float(np.sqrt(np.mean(residual ** 2)))
                bias_v = float(np.mean(residual))
                m1, m2, m3 = st.columns(3)
                m1.metric("Voltage RMSE", f"{rmse_v:.4f} V")
                m2.metric("Voltage bias (sim − log)", f"{bias_v:+.4f} V")
                m3.metric("Simulation duration",
                          f"{r_sim.total_duration_s:.0f} s vs log {log.total_flight_s:.0f} s")

        # ── Parameter Fitter ─────────────────────────────────────────────────
        st.divider()
        st.subheader("Parameter Fitter")
        st.caption("Fit 2RC ECM parameters from this log and register it for PRECISE-mode simulation.")

        pack_ids_fit = sorted(db.packs.keys())
        if not pack_ids_fit:
            st.info("No battery packs in database.")
        else:
            col_pf1, col_pf2 = st.columns(2)
            with col_pf1:
                fit_pack_id  = st.selectbox("Battery pack", pack_ids_fit, key="pf_pack")
                _fp = db.packs.get(fit_pack_id)
                fit_nom_cap  = st.number_input(
                    "Nominal capacity (Ah)", 0.1, 500.0,
                    value=float(_fp.pack_capacity_ah) if _fp else 10.0,
                    step=0.1, key="pf_cap",
                )
                fit_cutoff_v = st.number_input(
                    "Pack cutoff voltage (V)", 1.0, 200.0,
                    value=float(_fp.pack_voltage_cutoff) if _fp else 18.0,
                    step=0.1, key="pf_cutoff",
                )
            with col_pf2:
                fit_chem = st.text_input(
                    "Chemistry hint",
                    value=_fp.chemistry_id if _fp else "LION21",
                    key="pf_chem",
                )
                _valid_temps = [t for t in log.temp_c if t > -50]
                _default_temp = float(np.mean(_valid_temps)) if _valid_temps else 25.0
                fit_temp_c = st.number_input(
                    "Mean flight temperature (°C)", -40.0, 80.0,
                    value=round(_default_temp, 1), step=0.5, key="pf_temp",
                )
                fit_notes = st.text_input("Notes (optional)", key="pf_notes")

            if st.button("Fit & Register Log", type="primary", key="pf_run"):
                try:
                    from batteries.parameter_fitter import build_ecm_parameters_from_log
                    from batteries.ecm_store import LogRegistry, make_entry

                    _pack_proxy = db.packs[fit_pack_id]
                    with st.spinner("Fitting ECM parameters..."):
                        ecm, fit_summary, _ = build_ecm_parameters_from_log(
                            log, _pack_proxy, fit_chem
                        )

                    _mean_temp = fit_temp_c
                    _log_name  = Path(log.source_file).name if log.source_file else "unknown"
                    entry = make_entry(
                        pack_id=fit_pack_id,
                        log_filename=_log_name,
                        temperature_c=_mean_temp,
                        ecm_params=ecm,
                        fit_summary=fit_summary,
                        notes=fit_notes,
                    )
                    _reg = LogRegistry()
                    _reg.load()
                    _reg.add(entry)

                    st.success(
                        f"Registered `{_log_name}` for pack `{fit_pack_id}` "
                        f"at {_mean_temp:.1f} C.  "
                        f"R0={fit_summary.get('R0_mohm', '?')} mO  "
                        f"tau1={fit_summary.get('tau1_s', '?')} s  "
                        f"({fit_summary.get('n_steps', 0)} step events, "
                        f"{fit_summary.get('n_recovery', 0)} recovery events)"
                    )
                except Exception as _pf_err:
                    st.error(f"Fitting failed: {_pf_err}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — LOG REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
with tab_registry:
    st.subheader("Flight Log Registry")
    st.caption(
        "Registered flight logs with fitted ECM parameters. "
        "PRECISE-mode simulation interpolates between entries by temperature."
    )

    from batteries.ecm_store import LogRegistry as _LogRegistry

    _lr = _LogRegistry()
    _lr.load()
    _all_entries = _lr.all_entries()

    if not _all_entries:
        st.info(
            "No logs registered yet. Load a flight log in **Log Analysis**, "
            "then use the **Parameter Fitter** section to fit and register it."
        )
    else:
        _reg_packs = sorted(set(e.pack_id for e in _all_entries))
        _reg_filter = st.selectbox(
            "Filter by pack", ["All"] + _reg_packs, key="reg_filter"
        )
        _show_entries = [
            e for e in _all_entries
            if _reg_filter == "All" or e.pack_id == _reg_filter
        ]

        st.write(f"**{len(_show_entries)}** entr{'y' if len(_show_entries) == 1 else 'ies'} shown")

        for _e in _show_entries:
            _label = (
                f"{_e.pack_id}  |  {_e.log_filename}"
                f"  @  {_e.temperature_c:.1f} C  |  {_e.fitted_at[:10]}"
            )
            with st.expander(_label, expanded=False):
                _c1, _c2, _c3 = st.columns(3)
                _c1.write(f"**Pack:** {_e.pack_id}")
                _c1.write(f"**Log file:** {_e.log_filename}")
                _c2.write(f"**Temperature:** {_e.temperature_c:.1f} C")
                _c2.write(f"**Fitted at:** {_e.fitted_at[:19].replace('T', ' ')} UTC")
                if _e.fit_summary:
                    _fs = _e.fit_summary
                    _c3.write(f"**R0:** {_fs.get('R0_mohm', '?')} mO")
                    _c3.write(
                        f"**R1:** {_fs.get('R1_mohm', '?')} mO  "
                        f"tau1: {_fs.get('tau1_s', '?')} s"
                    )
                    _c3.write(
                        f"**R2:** {_fs.get('R2_mohm', '?')} mO  "
                        f"tau2: {_fs.get('tau2_s', '?')} s"
                    )
                if _e.notes:
                    st.caption(f"Notes: {_e.notes}")
                st.caption(f"Entry ID: {_e.entry_id}")
                if st.button("Delete entry", key=f"reg_del_{_e.entry_id}"):
                    _lr.remove(_e.entry_id)
                    st.success("Entry removed.")
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ECM PARAMETER VIEWER
# ══════════════════════════════════════════════════════════════════════════════
with tab_ecm_viewer:
    st.subheader("ECM Parameter Viewer")
    st.caption(
        "View fitted ECM parameters across temperature for a battery pack. "
        "Each point represents one registered flight log."
    )

    from batteries.ecm_store import LogRegistry as _ECMReg

    _ecm_reg = _ECMReg()
    _ecm_reg.load()
    _ecm_all = _ecm_reg.all_entries()

    if not _ecm_all:
        st.info(
            "No registered entries. Use the **Log Analysis** tab to fit and register a flight log first."
        )
    else:
        _ecm_packs = sorted(set(e.pack_id for e in _ecm_all))
        _ecm_sel_pack = st.selectbox("Select battery pack", _ecm_packs, key="ecm_viewer_pack")

        _pack_entries = sorted(
            _ecm_reg.entries_for_pack(_ecm_sel_pack),
            key=lambda e: e.temperature_c,
        )

        if not _pack_entries:
            st.warning(f"No entries for pack `{_ecm_sel_pack}`.")
        else:
            st.write(
                f"**{len(_pack_entries)}** entr{'y' if len(_pack_entries) == 1 else 'ies'} "
                f"for `{_ecm_sel_pack}`"
            )

            # ── Build data arrays from fit_summary ───────────────────────────
            temps   = [e.temperature_c for e in _pack_entries]
            r0_vals = [e.fit_summary.get("R0_mohm") for e in _pack_entries]
            r1_vals = [e.fit_summary.get("R1_mohm") for e in _pack_entries]
            r2_vals = [e.fit_summary.get("R2_mohm") for e in _pack_entries]
            t1_vals = [e.fit_summary.get("tau1_s")  for e in _pack_entries]
            t2_vals = [e.fit_summary.get("tau2_s")  for e in _pack_entries]

            def _clean(vals):
                """Replace None with nan for plotting."""
                return [float(v) if v is not None else float("nan") for v in vals]

            r0_arr = _clean(r0_vals)
            r1_arr = _clean(r1_vals)
            r2_arr = _clean(r2_vals)
            t1_arr = _clean(t1_vals)
            t2_arr = _clean(t2_vals)

            # ── Resistance chart ─────────────────────────────────────────────
            st.subheader("Resistance Parameters vs Temperature")
            fig_r, ax_r = plt.subplots(figsize=(10, 4))
            ax_r.plot(temps, r0_arr, "o-", color="#F44336", linewidth=1.8,
                      markersize=7, label="R0 (DC internal)")
            ax_r.plot(temps, r1_arr, "s-", color="#2196F3", linewidth=1.8,
                      markersize=7, label="R1 (RC1)")
            ax_r.plot(temps, r2_arr, "^-", color="#4CAF50", linewidth=1.8,
                      markersize=7, label="R2 (RC2)")
            for i, e in enumerate(_pack_entries):
                lbl = Path(e.log_filename).stem[:12]
                ax_r.annotate(lbl, (temps[i], r0_arr[i]),
                              textcoords="offset points", xytext=(4, 4), fontsize=7, alpha=0.7)
            ax_r.set_xlabel("Temperature (°C)")
            ax_r.set_ylabel("Resistance (mΩ)")
            ax_r.set_title(f"ECM Resistance vs Temperature — {_ecm_sel_pack}")
            ax_r.legend(fontsize=9)
            ax_r.grid(alpha=0.3)
            fig_r.tight_layout()
            st.pyplot(fig_r, use_container_width=True)
            plt.close(fig_r)

            # ── Time-constant chart ──────────────────────────────────────────
            st.subheader("RC Time Constants vs Temperature")
            fig_t, ax_t = plt.subplots(figsize=(10, 4))
            ax_t.plot(temps, t1_arr, "o-", color="#9C27B0", linewidth=1.8,
                      markersize=7, label="τ1 (RC1 time constant)")
            ax_t.plot(temps, t2_arr, "s-", color="#FF9800", linewidth=1.8,
                      markersize=7, label="τ2 (RC2 time constant)")
            ax_t.set_xlabel("Temperature (°C)")
            ax_t.set_ylabel("Time constant (s)")
            ax_t.set_title(f"RC Time Constants vs Temperature — {_ecm_sel_pack}")
            ax_t.legend(fontsize=9)
            ax_t.grid(alpha=0.3)
            fig_t.tight_layout()
            st.pyplot(fig_t, use_container_width=True)
            plt.close(fig_t)

            # ── Summary table ────────────────────────────────────────────────
            st.subheader("Entry Summary")
            _rows = []
            for e in _pack_entries:
                fs = e.fit_summary
                _rows.append({
                    "Log file":    e.log_filename,
                    "Temp (°C)":   e.temperature_c,
                    "R0 (mΩ)":     fs.get("R0_mohm", "—"),
                    "R1 (mΩ)":     fs.get("R1_mohm", "—"),
                    "R2 (mΩ)":     fs.get("R2_mohm", "—"),
                    "τ1 (s)":      fs.get("tau1_s",  "—"),
                    "τ2 (s)":      fs.get("tau2_s",  "—"),
                    "Step events": fs.get("n_steps",    "—"),
                    "Fitted at":   e.fitted_at[:10],
                })
            st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — LOG → MISSION
# ══════════════════════════════════════════════════════════════════════════════
with tab_log_mission:
    st.subheader("Log → Mission Extractor")
    st.caption(
        "Upload a flight log to extract mission phases from real flight data. "
        "Choose whether to import power estimates alongside phase durations, "
        "then edit and save the result as a new mission profile."
    )

    existing_log = st.session_state.get("flight_log")
    use_existing = False

    col_src, col_cfg_lm = st.columns([1, 1])
    with col_src:
        st.markdown("**Log source**")
        if existing_log:
            st.info(
                f"Log in session: `{Path(existing_log.source_file).name}`  "
                f"({existing_log.total_flight_s / 60:.1f} min, "
                f"{len(existing_log.time_s)} samples)"
            )
            use_existing = st.checkbox(
                "Use this log", value=True, key="lm_use_existing"
            )
        if not use_existing:
            lm_upload = st.file_uploader(
                "Upload flight log (.bin, .log, .csv)",
                type=["bin", "log", "csv"],
                key="lm_log_upload",
            )
            if lm_upload:
                st.caption(f"{lm_upload.name}  ({lm_upload.size / 1024:.1f} KB)")

    with col_cfg_lm:
        st.markdown("**Extraction settings**")
        lm_min_dur = st.slider(
            "Minimum phase duration (s)",
            2, 60, 8, key="lm_min_dur",
            help="Phases shorter than this are flagged as transient.",
        )

    st.markdown("**Import mode**")
    _lm_import_mode = st.radio(
        "What to import from the log",
        options=[
            "Phase + duration only",
            "Phase + duration + estimated power",
        ],
        index=1,
        key="lm_import_mode",
        horizontal=True,
        help=(
            "**Phase + duration only**: power_override_w is left blank on all phases. "
            "The equipment model supplies power values at simulation time.\n\n"
            "**Phase + duration + estimated power**: mean measured power (V × I) from "
            "the log is stored as power_override_w on each phase. High and medium "
            "confidence phases get the measured value; low confidence phases are left blank."
        ),
    )
    _include_power = (_lm_import_mode == "Phase + duration + estimated power")

    if _include_power:
        st.caption(
            "Measured power values will be stored on each phase as `power_override_w`. "
            "Low-confidence phases will fall back to the equipment model."
        )
    else:
        st.caption(
            "No power values will be stored. Simulations will use the equipment "
            "model to compute power for each phase."
        )

    if st.button("🔍 Extract phases", type="primary", key="lm_extract"):
        if use_existing and existing_log:
            _log = existing_log
        elif not use_existing:
            _up = st.session_state.get("lm_log_upload")
            if not _up:
                st.warning("Upload a log file above or generate a synthetic log in Log Analysis.")
                st.stop()
            _suffix = Path(_up.name).suffix.lower()
            if _suffix == ".bin":
                try:
                    import pymavlink  # noqa
                except ImportError:
                    st.error("pymavlink required for .bin files: pip install pymavlink")
                    st.stop()
            with tempfile.NamedTemporaryFile(suffix=_suffix, delete=False) as _tmp:
                _tmp.write(_up.getvalue())
                _tmp_path = _tmp.name
            try:
                from batteries.log_importer import load_log
                _log = load_log(_tmp_path)
                _log.source_file = _up.name
            finally:
                try:
                    os.unlink(_tmp_path)
                except OSError:
                    pass
        else:
            st.warning("Select a log source above.")
            st.stop()

        from missions.log_to_mission import segment_log
        with st.spinner("Segmenting log into mission phases..."):
            try:
                _raw_segs = segment_log(_log, min_duration_s=lm_min_dur)
            except ValueError as _ve:
                st.error(str(_ve))
                st.stop()

        if not _raw_segs:
            st.warning("No segments extracted. Ensure MODE messages are present.")
            st.stop()

        st.session_state["lm_segments"]      = _raw_segs
        st.session_state["lm_log_name"]      = Path(_log.source_file).stem
        st.session_state["lm_log_total_s"]   = _log.total_flight_s
        st.session_state["lm_log_total_mah"] = _log.total_mah
        st.session_state.pop("lm_pending_merge", None)
        st.rerun()

    if st.session_state.get("lm_segments"):
        from missions.log_to_mission import MissionSegment

        segs: list[MissionSegment] = st.session_state["lm_segments"]
        log_name = st.session_state.get("lm_log_name", "extracted_mission")

        _include_power = (
            st.session_state.get("lm_import_mode", "Phase + duration + estimated power")
            == "Phase + duration + estimated power"
        )

        # ── Summary metrics ──────────────────────────────────────────────────
        _total_dur_s = sum(s.duration_s for s in segs)
        _total_wh    = sum(s.energy_wh  for s in segs)
        _mean_pw     = _total_wh / (_total_dur_s / 3600) if _total_dur_s > 0 else 0
        _mc1, _mc2, _mc3, _mc4 = st.columns(4)
        _mc1.metric("Phases",       len(segs))
        _mc2.metric("Flight time",  f"{_total_dur_s / 60:.1f} min")
        _mc3.metric("Total energy", f"{_total_wh:.1f} Wh")
        if _include_power:
            _mc4.metric("Mean power", f"{_mean_pw:.0f} W")
        else:
            _mc4.metric("Mean power", "— (not imported)")

        st.divider()

        # ── Edit table ───────────────────────────────────────────────────────
        st.markdown("**Edit phase values**")
        st.caption(
            "Rename phases, change mode type, and adjust duration."
            + (" Power values are editable and will be stored on save."
               if _include_power
               else " Power column shown as reference only — values will NOT be stored on save.")
        )

        _edit_rows = []
        for _s in segs:
            _edit_rows.append({
                "seq":            _s.seq,
                "Phase name":     _s.phase_name,
                "Mode (type)":    _s.mode_name,
                "Duration (s)":   round(_s.duration_s, 1),
                "Mean power (W)": round(_s.mean_power_w, 1),
                "Energy (Wh)":    round(_s.energy_wh, 3),
                "Altitude (m)":   round(_s.mean_altitude_m, 1),
                "Speed (m/s)":    round(_s.mean_speed_ms, 1),
                "Confidence":     _s.confidence,
                "Transient":      _s.is_transient,
                "Notes":          _s.notes,
            })

        _power_col_config = (
            st.column_config.NumberColumn("Mean power (W) [reference only]",
                                          disabled=True, min_value=0.0)
            if not _include_power
            else st.column_config.NumberColumn("Mean power (W)", min_value=0.0, step=1.0)
        )

        _edited_df = st.data_editor(
            pd.DataFrame(_edit_rows),
            use_container_width=True,
            num_rows="fixed",
            hide_index=True,
            column_config={
                "seq":            st.column_config.NumberColumn("Seq", disabled=True, width="small"),
                "Mode (type)":    st.column_config.SelectboxColumn(
                                      "Mode (type)", options=_ALL_PHASE_TYPES, required=True,
                                  ),
                "Confidence":     st.column_config.SelectboxColumn(
                                      "Confidence", options=["high", "medium", "low"],
                                  ),
                "Transient":      st.column_config.CheckboxColumn("Transient", width="small"),
                "Duration (s)":   st.column_config.NumberColumn("Duration (s)", min_value=1.0, step=1.0),
                "Mean power (W)": _power_col_config,
            },
            key="lm_edit_df",
        )

        if _edited_df is not None:
            _df_dict = {int(row["seq"]): row for _, row in _edited_df.iterrows()}
            for _s in segs:
                if _s.seq in _df_dict:
                    _r = _df_dict[_s.seq]
                    _s.phase_name   = str(_r.get("Phase name",     _s.phase_name))
                    _s.mode_name    = str(_r.get("Mode (type)",    _s.mode_name)).upper()
                    _s.duration_s   = float(_r.get("Duration (s)", _s.duration_s) or _s.duration_s)
                    _s.mean_power_w = float(_r.get("Mean power (W)", _s.mean_power_w) or _s.mean_power_w)
                    _s.energy_wh    = float(_r.get("Energy (Wh)",   _s.energy_wh) or _s.energy_wh)
                    _s.confidence   = str(_r.get("Confidence",      _s.confidence))
                    _s.is_transient = bool(_r.get("Transient",      _s.is_transient))
                    _s.notes        = str(_r.get("Notes",           _s.notes))

        # ── Power profile chart ──────────────────────────────────────────────
        _fig_lm, _ax_lm = plt.subplots(figsize=(10, 3))
        _bar_labels  = [f"{_s.phase_name}\n{_s.duration_s:.0f}s" for _s in segs]
        _bar_powers  = [_s.mean_power_w for _s in segs]
        _bar_colors  = [PHASE_COLORS.get(_s.mode_name.upper(), "#DDDDDD") for _s in segs]
        _bars_lm = _ax_lm.bar(range(len(segs)), _bar_powers, color=_bar_colors,
                               edgecolor="#666", linewidth=0.5,
                               alpha=1.0 if _include_power else 0.45)
        _ax_lm.set_xticks(range(len(segs)))
        _ax_lm.set_xticklabels(_bar_labels, fontsize=8)
        _ax_lm.set_ylabel("Mean power (W)")
        _ax_lm.set_title(
            f"Measured power by phase — {log_name}"
            if _include_power
            else f"Measured power (reference only, not imported) — {log_name}",
            fontsize=9,
        )
        _ax_lm.grid(axis="y", alpha=0.3)
        for _bar, _pw in zip(_bars_lm, _bar_powers):
            if _pw > 0:
                _ax_lm.text(_bar.get_x() + _bar.get_width() / 2,
                            _bar.get_height() + 3,
                            f"{_pw:.0f}W", ha="center", fontsize=7)
        _fig_lm.tight_layout()
        st.pyplot(_fig_lm, use_container_width=True)
        plt.close(_fig_lm)

        st.divider()

        # ── DELETE ───────────────────────────────────────────────────────────
        st.markdown("**Delete a phase**")
        _del_opts = {
            f"Seq {_s.seq}: {_s.phase_name} ({_s.mode_name}, {_s.duration_s:.0f}s)": _s
            for _s in segs
        }
        _del_label = st.selectbox(
            "Phase to delete", list(_del_opts.keys()),
            key="lm_del_sel", label_visibility="collapsed"
        )
        _del_seg = _del_opts[_del_label]
        st.write(
            f"Will delete: **Seq {_del_seg.seq} — {_del_seg.phase_name}** "
            f"({_del_seg.mode_name}, {_del_seg.duration_s:.0f} s)"
        )
        if st.button("🗑️ Confirm delete", key="lm_del_confirm"):
            _new_segs = [_s for _s in segs if _s.seq != _del_seg.seq]
            for _i, _s in enumerate(_new_segs, start=1):
                _s.seq = _i
            st.session_state["lm_segments"] = _new_segs
            st.session_state.pop("lm_pending_merge", None)
            st.rerun()

        st.divider()

        # ── MERGE ────────────────────────────────────────────────────────────
        st.markdown("**Merge two adjacent phases**")
        st.caption("Only consecutive phases can be merged.")
        _seq_labels = {
            _s.seq: f"Seq {_s.seq}: {_s.phase_name} ({_s.mode_name}, {_s.duration_s:.0f}s)"
            for _s in segs
        }

        if len(segs) >= 2:
            _merge_cols = st.columns([3, 1])
            with _merge_cols[0]:
                _merge_sel = st.multiselect(
                    "Select exactly 2 consecutive phases",
                    options=[_s.seq for _s in segs],
                    max_selections=2,
                    key="lm_merge_sel",
                    format_func=lambda _sq: _seq_labels[_sq],
                )
            with _merge_cols[1]:
                st.write("")
                _merge_stage_btn = st.button(
                    "Stage merge →", key="lm_merge_stage_btn",
                    disabled=(len(_merge_sel) != 2),
                )

            if _merge_stage_btn and len(_merge_sel) == 2:
                _sorted_sel   = sorted(_merge_sel)
                _current_seqs = [_s.seq for _s in segs]
                _idx_a = _current_seqs.index(_sorted_sel[0])
                _idx_b = _current_seqs.index(_sorted_sel[1])
                if abs(_idx_a - _idx_b) != 1:
                    st.warning("Only adjacent phases can be merged.")
                else:
                    _seg_a   = segs[min(_idx_a, _idx_b)]
                    _seg_b   = segs[max(_idx_a, _idx_b)]
                    _dur_tot = _seg_a.duration_s + _seg_b.duration_s
                    _w_pw    = (
                        _seg_a.mean_power_w * _seg_a.duration_s
                        + _seg_b.mean_power_w * _seg_b.duration_s
                    ) / _dur_tot if _dur_tot > 0 else 0.0
                    st.session_state["lm_pending_merge"] = {
                        "seq_a": _seg_a.seq, "seq_b": _seg_b.seq,
                        "suggested_w": round(_w_pw, 1),
                    }
                    st.rerun()

            _pending = st.session_state.get("lm_pending_merge")
            if _pending:
                _sa = next((_s for _s in segs if _s.seq == _pending["seq_a"]), None)
                _sb = next((_s for _s in segs if _s.seq == _pending["seq_b"]), None)
                if _sa and _sb:
                    st.info(
                        f"Merging **Seq {_sa.seq}: {_sa.phase_name}** "
                        f"({_sa.duration_s:.0f} s)  +  "
                        f"**Seq {_sb.seq}: {_sb.phase_name}** "
                        f"({_sb.duration_s:.0f} s)  "
                        f"→ total {_sa.duration_s + _sb.duration_s:.0f} s"
                    )
                    if _include_power:
                        _pm_cols = st.columns([2, 2, 1])
                    else:
                        _pm_cols = st.columns([2, 1])

                    with _pm_cols[0]:
                        _merged_name = st.text_input(
                            "Merged phase name", value=_sa.phase_name, key="lm_merge_name"
                        )
                    _merged_pw = None
                    if _include_power:
                        with _pm_cols[1]:
                            _merged_pw = st.number_input(
                                "Power for merged phase (W)",
                                min_value=0.0, value=float(_pending["suggested_w"]),
                                step=1.0, key="lm_merge_pw",
                                help="Duration-weighted mean pre-filled.",
                            )
                        _confirm_col = _pm_cols[2]
                    else:
                        st.caption("Power not imported — no power value needed for merge.")
                        _confirm_col = _pm_cols[1]

                    with _confirm_col:
                        st.write("")
                        _confirm_merge = st.button(
                            "✓ Confirm merge", type="primary", key="lm_merge_confirm_btn"
                        )

                    if st.button("✕ Cancel", key="lm_merge_cancel"):
                        st.session_state.pop("lm_pending_merge", None)
                        st.rerun()

                    if _confirm_merge:
                        _merged_seg = _sa.merge_with(
                            _sb,
                            override_power_w=_merged_pw if _include_power else None,
                        )
                        _merged_seg.phase_name = _merged_name
                        _new_segs  = [_s for _s in segs if _s.seq not in (_sa.seq, _sb.seq)]
                        _insert_at = min(segs.index(_sa), segs.index(_sb))
                        _new_segs.insert(_insert_at, _merged_seg)
                        for _i, _s in enumerate(_new_segs, start=1):
                            _s.seq = _i
                        st.session_state["lm_segments"] = _new_segs
                        st.session_state.pop("lm_pending_merge", None)
                        st.rerun()
        else:
            st.caption("Need at least 2 phases to merge.")

        st.divider()

        # ── SAVE ─────────────────────────────────────────────────────────────
        st.subheader("Save as new mission")

        if _include_power:
            st.info(
                "Saving in **Phase + duration + estimated power** mode. "
                "Measured power values stored as `power_override_w` on high/medium confidence phases."
            )
        else:
            st.info(
                "Saving in **Phase + duration only** mode. "
                "No power values stored — equipment model supplies power at simulation time."
            )

        _save_col1, _save_col2 = st.columns([1, 1])
        with _save_col1:
            _default_mid = (
                st.session_state.get("lm_log_name", "LOG")
                .upper().replace(" ", "_").replace("-", "_")[:30]
            )
            _lm_mission_id = st.text_input("Mission ID *", value=_default_mid, key="lm_mission_id")
            if _lm_mission_id and _lm_mission_id in db.missions:
                st.warning(f"`{_lm_mission_id}` already exists — choose a different ID.")
            _lm_mission_name = st.text_input(
                "Mission name",
                value=f"From log: {st.session_state.get('lm_log_name', '')}",
                key="lm_mission_name",
            )
        with _save_col2:
            _lm_uav_id = st.selectbox(
                "UAV config *",
                options=sorted(db.uav_configs.keys()) if db.uav_configs else ["—"],
                key="lm_uav_id",
            )

        st.caption(
            f"{len(segs)} phases · "
            f"{sum(s.duration_s for s in segs) / 60:.1f} min · "
            f"UAV: {_lm_uav_id} · "
            f"Mode: {'power included' if _include_power else 'duration only'}"
        )

        _save_disabled = (
            not _lm_mission_id
            or _lm_mission_id in db.missions
            or not db.uav_configs
            or not segs
        )

        if st.button("💾 Save mission", type="primary", disabled=_save_disabled, key="lm_save_btn"):
            from missions.log_to_mission import to_mission_phases, save_mission

            _final_phases = to_mission_phases(
                segs, _lm_mission_id, _lm_mission_name, _lm_uav_id,
                include_power=_include_power,
            )
            try:
                save_mission(db, _final_phases, _lm_mission_id, _lm_mission_name, _lm_uav_id)
                reload_db()
                _power_note = (
                    "with measured power values"
                    if _include_power
                    else "without power values (equipment model will be used)"
                )
                st.success(
                    f"Mission `{_lm_mission_id}` saved with {len(_final_phases)} phases "
                    f"{_power_note}. Open the Mission Configurator to review and simulate it."
                )
                for _k in ("lm_segments", "lm_log_name", "lm_log_total_s",
                           "lm_log_total_mah", "lm_pending_merge"):
                    st.session_state.pop(_k, None)
                st.rerun()
            except ValueError as _ve:
                st.error(str(_ve))
            except Exception as _e:
                st.error(f"Save failed: {_e}")

    else:
        st.info(
            "Use **Log Analysis** tab to load or generate a flight log, then return here "
            "to extract mission phases from it. Or upload a log file directly above."
        )
