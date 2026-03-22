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
import tempfile

st.set_page_config(page_title="Log Tools", page_icon="📋", layout="wide")

from ui.components.db_helpers import load_db, load_config
from ui.config import ACCENT, PHASE_COLORS

st.title("📋 Log Tools")
st.caption("Log Analysis, Log Registry, and ECM Parameter Viewer.")

db  = load_db()
cfg = load_config()

tab_log, tab_registry, tab_ecm_viewer = st.tabs(
    ["Log Analysis", "Log Registry", "ECM Parameter Viewer"]
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
