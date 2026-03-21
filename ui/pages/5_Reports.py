"""
ui/pages/5_Reports.py
Temperature sweep, battery scorecard, quick selection table, Excel and PDF report generation.
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
from datetime import datetime

st.set_page_config(page_title="Reports", page_icon="📄", layout="wide")

from ui.components.db_helpers import (
    load_db, load_config, sim_results_to_df, plot_temp_sweep, chem_color
)
from ui.config import REPORTS_DIR, ACCENT, PHASE_COLORS

st.title("📄 Reports")
st.caption("Temperature sensitivity sweep, battery scorecard, and report generation.")

db  = load_db()
cfg = load_config()

if not cfg:
    st.warning("No configuration found. Set up a mission in **Mission Configurator** first.")
    st.stop()

selected_ids = cfg.get("selected_batteries", [])
mission_id   = cfg.get("mission_id", "")
uav_id       = cfg.get("uav_id", "")
ambient_temp = cfg.get("ambient_temp_c", 25.0)
temp_sweep   = cfg.get("temp_sweep", list(range(-10, 46, 5)))

if not selected_ids:
    st.warning("No batteries selected. Go to **Mission Configurator**.")
    st.stop()
if mission_id not in db.missions:
    st.error(f"Mission `{mission_id}` not found.")
    st.stop()
if uav_id not in db.uav_configs:
    st.error(f"UAV `{uav_id}` not found.")
    st.stop()

mission = db.missions[mission_id]
uav     = db.uav_configs[uav_id]

valid_packs = [(pid, db.packs[pid]) for pid in selected_ids if pid in db.packs]
if not valid_packs:
    st.error("No valid packs found.")
    st.stop()

# ── Config summary ────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric("Mission", mission_id)
c2.metric("UAV", uav_id)
c3.metric("Ambient", f"{ambient_temp} °C")
c4.metric("Packs", len(valid_packs))

st.divider()

# ── Simulation parameters ─────────────────────────────────────────────────────
with st.expander("Simulation Parameters", expanded=False):
    c_p1, c_p2 = st.columns(2)
    with c_p1:
        dt_s_rep      = st.select_slider("Sim timestep (s)", [0.5, 1.0, 2.0, 5.0], value=1.0, key="rep_dt")
        peukert_k_rep = st.slider("Peukert k", 1.00, 1.15, 1.05, 0.01, key="rep_pk")
    with c_p2:
        cutoff_rep   = st.slider("Cutoff SoC (%)", 0, 20, 10, key="rep_cutoff")
        sweep_dt_rep = st.select_slider("Sweep timestep (s)", [1.0, 2.0, 5.0], value=5.0, key="rep_sw_dt")

# ── Run simulations ───────────────────────────────────────────────────────────
def run_main_sims():
    from mission.simulator import run_simulation
    results = {}
    prog = st.progress(0, "Running main simulations…")
    for i, (pid, pack) in enumerate(valid_packs):
        prog.progress(i / len(valid_packs), f"Simulating {pid}…")
        try:
            r = run_simulation(
                pack=pack, mission=mission, uav=uav,
                discharge_pts=db.discharge_pts,
                ambient_temp_c=ambient_temp, dt_s=dt_s_rep,
                peukert_k=peukert_k_rep, cutoff_soc_pct=cutoff_rep,
            )
            results[pid] = r
        except Exception as e:
            st.warning(f"Simulation failed for {pid}: {e}")
    prog.progress(1.0, "Done!")
    return results


def run_temp_sweep():
    from mission.simulator import temperature_sweep
    all_sweep = {}
    all_df    = {}
    prog = st.progress(0, "Running temperature sweeps…")
    for i, (pid, pack) in enumerate(valid_packs):
        prog.progress(i / len(valid_packs), f"Sweep for {pid}…")
        try:
            sw = temperature_sweep(
                pack=pack, mission=mission, uav=uav,
                discharge_pts=db.discharge_pts,
                temperatures_c=temp_sweep, dt_s=sweep_dt_rep,
                peukert_k=peukert_k_rep, cutoff_soc_pct=cutoff_rep,
            )
            all_sweep[pid] = sw
            all_df[pid] = pd.DataFrame([{
                "Ambient (C)":    t,
                "Final SoC (%)":  round(r.final_soc, 1),
                "Peak sag (V)":   round(r.peak_sag_v, 3),
                "Min V (V)":      round(r.min_voltage, 3),
                "Max T (°C)":     round(r.max_temp_c, 1),
                "Depleted":       r.depleted,
            } for t, r in zip(temp_sweep, sw)])
        except Exception as e:
            st.warning(f"Sweep failed for {pid}: {e}")
    prog.progress(1.0, "Done!")
    return all_sweep, all_df


col_run_main, col_run_sweep, col_clear = st.columns([1, 1, 2])
with col_run_main:
    if st.button("▶ Run Main Simulations", type="primary", key="rep_run_main"):
        st.session_state["sim_results"]    = run_main_sims()
        st.rerun()
with col_run_sweep:
    if st.button("🌡 Run Temperature Sweep", key="rep_run_sweep"):
        sw, df_sw = run_temp_sweep()
        st.session_state["sweep_results"]  = sw
        st.session_state["sweep_df"]       = df_sw
        st.rerun()
with col_clear:
    if st.button("Clear all results", key="rep_clear"):
        st.session_state["sim_results"]  = {}
        st.session_state["sweep_results"] = {}
        st.session_state.pop("sweep_df", None)
        st.rerun()

sim_results  = st.session_state.get("sim_results", {})
sweep_results= st.session_state.get("sweep_results", {})
sweep_df     = st.session_state.get("sweep_df", {})

st.divider()

# ── Battery Scorecard ─────────────────────────────────────────────────────────
st.subheader("Battery Scorecard")
if sim_results:
    result_list = [sim_results[pid] for pid, _ in valid_packs if pid in sim_results]
    pack_list   = [pack for pid, pack in valid_packs if pid in sim_results]
    scorecard = sim_results_to_df(result_list, pack_list)

    def sc_style(row):
        color = {"PASS": "#E2EFDA", "MARGINAL": "#FFF2CC", "FAIL": "#FFCCCC"}.get(row["Status"], "#FFF")
        return [f"background-color: {color}"] * len(row)

    st.dataframe(
        scorecard.drop(columns=["Depleted"]).style.apply(sc_style, axis=1).format({
            "Energy (Wh)": "{:.0f}", "Weight (g)": "{:.0f}", "Wh/kg": "{:.1f}",
            "Used (Wh)": "{:.1f}", "Final SoC (%)": "{:.1f}", "Min V (V)": "{:.3f}",
            "Peak Sag (V)": "{:.3f}", "Max I (A)": "{:.1f}", "Max T (°C)": "{:.1f}",
            "Margin (%)": "{:.1f}",
        }),
        use_container_width=True, hide_index=True
    )

    # Bar chart: Final SoC comparison
    fig_sc, ax_sc = plt.subplots(figsize=(max(6, len(result_list) * 1.2), 4))
    ids   = [r.pack_id[:20] for r in result_list]
    socs  = [r.final_soc for r in result_list]
    cols  = [(("#4CAF50" if s > 20 else "#FF9800" if s > 10 else "#F44336")) for s in socs]
    bars = ax_sc.bar(range(len(ids)), socs, color=cols, edgecolor="#666", linewidth=0.5)
    ax_sc.set_xticks(range(len(ids)))
    ax_sc.set_xticklabels(ids, rotation=35, ha="right", fontsize=8)
    ax_sc.axhline(10, color="red", linewidth=1.2, linestyle="--", label="10% cutoff")
    ax_sc.axhline(20, color="orange", linewidth=1, linestyle=":", label="20% margin")
    ax_sc.set_ylabel("Final SoC (%)")
    ax_sc.set_title("Final State of Charge — All Selected Packs")
    ax_sc.legend(fontsize=8)
    ax_sc.grid(axis="y", alpha=0.3)
    for bar, val in zip(bars, socs):
        ax_sc.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                   f"{val:.1f}%", ha="center", fontsize=7)
    fig_sc.tight_layout()
    st.pyplot(fig_sc, use_container_width=True)
    plt.close(fig_sc)
else:
    st.info("Run **Main Simulations** to see the scorecard.")

st.divider()

# ── Quick Selection Table ─────────────────────────────────────────────────────
st.subheader("Quick Battery Selection Table")
st.caption("Comprehensive comparison of selected packs with computed metrics.")

sel_rows = []
for pid, pack in valid_packs:
    r = sim_results.get(pid)
    margin = None
    status = "—"
    if r:
        margin = round((r.final_soc - 10) / 90 * 100 if r.final_soc > 10 else 0, 1)
        status = ("PASS" if not r.depleted and margin > 10 else
                  "MARGINAL" if not r.depleted else "FAIL")
    sel_rows.append({
        "Pack ID":         pack.battery_id,
        "Chemistry":       pack.chemistry_id,
        "Config":          f"{pack.cells_series}S{pack.cells_parallel}P",
        "Voltage (V)":     round(pack.pack_voltage_nom, 1),
        "Capacity (Ah)":   round(pack.pack_capacity_ah, 2),
        "Energy (Wh)":     round(pack.pack_energy_wh, 1),
        "Weight (g)":      round(pack.pack_weight_g, 1),
        "Wh/kg":           round(pack.specific_energy_wh_kg, 1),
        "Max I (A)":       round(pack.max_cont_discharge_a, 1),
        "IR (mΩ)":         round(pack.internal_resistance_mohm, 2),
        "Cycles":          pack.cycle_life,
        "Final SoC (%)":   round(r.final_soc, 1) if r else "—",
        "Min V (V)":       round(r.min_voltage, 3) if r else "—",
        "Peak Sag (V)":    round(r.peak_sag_v, 3) if r else "—",
        "Margin (%)":      margin,
        "Status":          status,
    })

sel_df = pd.DataFrame(sel_rows)
st.dataframe(sel_df, use_container_width=True, hide_index=True)

csv_sel = sel_df.to_csv(index=False).encode("utf-8")
st.download_button("Download selection table as CSV", data=csv_sel,
                   file_name="battery_selection.csv", mime="text/csv")

st.divider()

# ── Temperature Sweep ─────────────────────────────────────────────────────────
st.subheader("Temperature Sensitivity Sweep")
if sweep_df:
    # Chart
    fig_sw = plot_temp_sweep(sweep_df)
    st.pyplot(fig_sw, use_container_width=True)
    plt.close(fig_sw)

    # Self-heating chart
    st.write("**Self-heating (Max cell T − Ambient)**")
    fig_sh, ax_sh = plt.subplots(figsize=(10, 4))
    cmap_sh = plt.get_cmap("tab10")
    for idx, (pid, df) in enumerate(sweep_df.items()):
        t_arr   = df["Ambient (C)"].values
        heat    = df["Max T (°C)"].values - t_arr
        ax_sh.plot(t_arr, heat, color=cmap_sh(idx % 10), linewidth=2,
                   label=pid[:22], marker="o", markersize=4)
    ax_sh.set_xlabel("Ambient Temperature (°C)")
    ax_sh.set_ylabel("Self-heating (°C)")
    ax_sh.set_title("Cell Self-Heating vs Ambient Temperature")
    ax_sh.legend(fontsize=7)
    ax_sh.grid(alpha=0.3)
    fig_sh.tight_layout()
    st.pyplot(fig_sh, use_container_width=True)
    plt.close(fig_sh)

    # Detailed sweep tables
    sel_sweep_pack = st.selectbox("View sweep table for pack", sorted(sweep_df.keys()), key="rep_sweep_tbl")
    if sel_sweep_pack in sweep_df:
        df_show = sweep_df[sel_sweep_pack].copy()
        df_show["Self-heat (°C)"] = df_show["Max T (°C)"] - df_show["Ambient (C)"]

        def sweep_row_style(row):
            if row["Depleted"]:
                return ["background-color: #FFCCCC"] * len(row)
            if row["Final SoC (%)"] < 20:
                return ["background-color: #FFF2CC"] * len(row)
            return ["background-color: #E2EFDA"] * len(row)

        st.dataframe(
            df_show.style.apply(sweep_row_style, axis=1).format({
                "Final SoC (%)": "{:.1f}", "Peak sag (V)": "{:.3f}",
                "Min V (V)": "{:.3f}", "Max T (°C)": "{:.1f}",
                "Self-heat (°C)": "{:.1f}",
            }),
            use_container_width=True, hide_index=True
        )
else:
    st.info("Run **Temperature Sweep** to see sensitivity data.")

st.divider()

# ── Report Generation ─────────────────────────────────────────────────────────
st.subheader("Generate Reports")

if not sim_results:
    st.info("Run **Main Simulations** before generating reports.")
else:
    default_stem = f"BattSim_Report_{mission_id}_{datetime.now().strftime('%Y%m%d_%H%M')}"
    report_name = st.text_input("Report filename (without extension)",
                                value=default_stem, key="rep_filename")

    primary_pack_id = st.selectbox(
        "Primary pack (used for Mission Summary sheet)",
        [pid for pid, _ in valid_packs if pid in sim_results],
        key="rep_primary"
    )

    r_list  = [sim_results[pid] for pid, _ in valid_packs if pid in sim_results]
    p_list  = [pack for pid, pack in valid_packs if pid in sim_results]
    primary = db.packs.get(primary_pack_id)

    col_xlsx, col_pdf = st.columns(2)

    # ── Excel report ──────────────────────────────────────────────────────────
    with col_xlsx:
        st.write("**📊 Excel Report**")
        if st.button("Generate Excel Report", type="primary", key="rep_gen_xlsx"):
            from mission.report_generator import generate_report
            xlsx_name = report_name + ".xlsx"
            out_path  = REPORTS_DIR / xlsx_name
            sw_temps   = temp_sweep if sweep_results else None
            primary_sw = sweep_results.get(primary_pack_id) if sweep_results else None
            try:
                with st.spinner("Generating Excel report…"):
                    generate_report(
                        out_path=out_path,
                        results=r_list, packs=p_list,
                        mission=mission, uav_name=uav.name,
                        ambient_temp_c=ambient_temp,
                        temp_sweep_temps=sw_temps,
                        temp_sweep_results=primary_sw,
                        flight_log=st.session_state.get("flight_log"),
                        fitted_params=None,
                        primary_pack=primary,
                    )
                with open(out_path, "rb") as f:
                    xlsx_bytes = f.read()
                st.download_button(
                    label=f"⬇ Download {xlsx_name}",
                    data=xlsx_bytes,
                    file_name=xlsx_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="rep_dl_xlsx",
                )
                st.success(f"Excel saved to `{out_path}`")
            except Exception as e:
                st.error(f"Excel report failed: {e}")

    # ── PDF report ────────────────────────────────────────────────────────────
    with col_pdf:
        st.write("**📑 PDF Report**")
        if st.button("Generate PDF Report", type="primary", key="rep_gen_pdf"):
            from ui.components.pdf_report import generate_pdf_report
            pdf_name = report_name + ".pdf"
            try:
                with st.spinner("Generating PDF report…"):
                    pdf_bytes = generate_pdf_report(
                        results=r_list,
                        packs=p_list,
                        mission=mission,
                        uav_name=uav.name,
                        ambient_temp_c=ambient_temp,
                        sweep_df=sweep_df if sweep_df else None,
                        flight_log=st.session_state.get("flight_log"),
                    )
                st.download_button(
                    label=f"⬇ Download {pdf_name}",
                    data=pdf_bytes,
                    file_name=pdf_name,
                    mime="application/pdf",
                    key="rep_dl_pdf",
                )
                st.success(f"PDF ready for download ({len(pdf_bytes)//1024} KB).")
            except Exception as e:
                st.error(f"PDF report failed: {e}")
