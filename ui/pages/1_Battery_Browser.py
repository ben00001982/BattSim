"""
ui/pages/1_Battery_Browser.py
Browse, filter, and compare all battery packs in the database.
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

st.set_page_config(page_title="Battery Browser", page_icon="🔍", layout="wide")

from ui.components.db_helpers import (
    load_db, load_config, save_config, packs_to_df,
    plot_energy_vs_weight, plot_specific_energy_bar, chem_color
)
from ui.config import CHEM_COLORS

st.title("🔍 Battery Browser")
st.caption("Explore, filter, and compare all battery packs in the database.")

db = load_db()
all_packs = list(db.packs.values())

# ── Sidebar filters ───────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    all_chems = sorted(set(p.chemistry_id for p in all_packs))
    sel_chems = st.multiselect("Chemistry", all_chems, default=all_chems)

    energies = [p.pack_energy_wh for p in all_packs if p.pack_energy_wh > 0]
    e_min, e_max = (int(min(energies)), int(max(energies))) if energies else (0, 10000)
    sel_energy = st.slider("Energy (Wh)", e_min, e_max, (e_min, e_max))

    weights = [p.pack_weight_g for p in all_packs if p.pack_weight_g > 0]
    w_min, w_max = (int(min(weights)), int(max(weights))) if weights else (0, 50000)
    sel_weight = st.slider("Weight (g)", w_min, w_max, (w_min, w_max))

    # Capacity in mAh
    caps_mah = [p.pack_capacity_ah * 1000 for p in all_packs if p.pack_capacity_ah > 0]
    c_min, c_max = (int(min(caps_mah)), int(max(caps_mah))) if caps_mah else (0, 100000)
    sel_cap = st.slider("Capacity (mAh)", c_min, c_max, (c_min, c_max))

    # Max continuous current
    currents = [p.max_cont_discharge_a for p in all_packs if p.max_cont_discharge_a > 0]
    i_min, i_max = (int(min(currents)), int(max(currents))) if currents else (0, 1000)
    sel_current = st.slider("Max cont. current (A)", i_min, i_max, (i_min, i_max))

    all_series = sorted(set(p.cells_series for p in all_packs))
    sel_series = st.multiselect("Cells in series (S)", all_series, default=all_series)

    all_sources = sorted(set(
        ("TATTU" if p.battery_id.startswith("TATTU") else
         "GREPOW" if p.battery_id.startswith("GREPOW") else
         "Custom/Manual")
        for p in all_packs
    ))
    sel_sources = st.multiselect("Source", all_sources, default=all_sources)

    sort_col = st.selectbox("Sort by", ["Energy (Wh)", "Weight (g)", "Wh/kg",
                                         "Capacity (Ah)", "Voltage (V)", "Max I (A)"])
    sort_asc = st.checkbox("Ascending", value=False)

# ── Apply filters ─────────────────────────────────────────────────────────────
def source_of(p):
    if p.battery_id.startswith("TATTU"):  return "TATTU"
    if p.battery_id.startswith("GREPOW"): return "GREPOW"
    return "Custom/Manual"

filtered = [
    p for p in all_packs
    if p.chemistry_id in sel_chems
    and sel_energy[0]  <= p.pack_energy_wh          <= sel_energy[1]
    and sel_weight[0]  <= p.pack_weight_g            <= sel_weight[1]
    and sel_cap[0]     <= p.pack_capacity_ah * 1000  <= sel_cap[1]
    and sel_current[0] <= p.max_cont_discharge_a     <= sel_current[1]
    and p.cells_series in sel_series
    and source_of(p) in sel_sources
]

st.write(f"Showing **{len(filtered)}** of {len(all_packs)} packs")

if not filtered:
    st.warning("No packs match the current filters.")
    st.stop()

# ── Table ─────────────────────────────────────────────────────────────────────
df = packs_to_df(filtered)
df = df.sort_values(sort_col, ascending=sort_asc).reset_index(drop=True)

def row_style(row):
    col = chem_color(row["Chemistry"])
    return [f"background-color: {col}18"] * len(row)

st.dataframe(
    df.style.apply(row_style, axis=1).format({
        "Energy (Wh)": "{:.0f}",
        "Weight (g)":  "{:.0f}",
        "Wh/kg":       "{:.1f}",
        "Max W (W)":   "{:.0f}",
    }),
    use_container_width=True,
    height=320,
)

# ── Pack selection + add to config ────────────────────────────────────────────
st.divider()
st.subheader("Select Packs")

filtered_ids = [p.battery_id for p in filtered]

col_pick, col_btn = st.columns([3, 1])
with col_pick:
    browser_sel = st.multiselect(
        "Pick packs from filtered results",
        filtered_ids,
        default=st.session_state.get("browser_selected_packs", []),
        key="browser_picklist",
        help="These selections are available to import into Mission Configurator.",
    )
    # Persist selection so Mission Configurator can read it
    st.session_state["browser_selected_packs"] = browser_sel

with col_btn:
    st.write("")  # vertical alignment spacer
    st.write("")
    if st.button("➕ Add selection to analysis config", key="browser_add_cfg",
                 disabled=not browser_sel):
        cfg = load_config()
        existing = cfg.get("selected_batteries", [])
        merged = list(dict.fromkeys(existing + browser_sel))
        cfg["selected_batteries"] = merged
        save_config(cfg)
        st.session_state["config"] = cfg
        st.success(f"Added {len(browser_sel)} pack(s) to analysis config "
                   f"({len(merged)} total selected).")

if browser_sel:
    st.caption(f"{len(browser_sel)} pack(s) selected: {', '.join(p[:30] for p in browser_sel)}")

# ── Pack detail ───────────────────────────────────────────────────────────────
with st.expander("Pack Detail", expanded=False):
    sel_id = st.selectbox("Select pack to inspect", filtered_ids, key="browser_detail")
    if sel_id:
        pack = db.packs[sel_id]
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**{pack.name}**")
            st.write(f"Chemistry: `{pack.chemistry_id}`")
            st.write(f"Config: `{pack.cells_series}S{pack.cells_parallel}P` ({pack.total_cells} cells)")
            st.write(f"Cell: `{pack.cell_id}`")
            st.write(f"Cycle life: {pack.cycle_life}")
            st.write(f"UAV class: {pack.uav_class or '—'}")
        with c2:
            st.metric("Voltage (nom)", f"{pack.pack_voltage_nom:.1f} V")
            st.metric("Capacity",      f"{pack.pack_capacity_ah:.2f} Ah  ({pack.pack_capacity_ah*1000:.0f} mAh)")
            st.metric("Energy",        f"{pack.pack_energy_wh:.0f} Wh")
        with c3:
            st.metric("Weight",             f"{pack.pack_weight_g:.0f} g")
            st.metric("Specific energy",    f"{pack.specific_energy_wh_kg:.0f} Wh/kg")
            st.metric("Max cont. discharge",f"{pack.max_cont_discharge_a:.0f} A / {pack.max_cont_discharge_w:.0f} W")
        if pack.notes:
            st.caption(pack.notes)

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────
tab_scatter, tab_bar, tab_discharge = st.tabs(["Energy vs Weight", "Specific Energy", "Discharge Curve"])

with tab_scatter:
    fig = plot_energy_vs_weight(filtered)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

with tab_bar:
    max_bars = st.slider("Max packs to show", 10, min(100, len(filtered)), 30, key="browser_bar_n")
    fig = plot_specific_energy_bar(filtered, max_n=max_bars)
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

with tab_discharge:
    avail_chems = sorted(set(p.chemistry_id for p in filtered))
    sel_chem_dc = st.selectbox("Chemistry", avail_chems, key="browser_dc_chem")
    c_rates = sorted(set(pt.c_rate for pt in db.discharge_pts if pt.chem_id == sel_chem_dc))

    if not c_rates:
        st.info(f"No discharge curve data found for {sel_chem_dc}.")
    else:
        sel_crate = st.selectbox("C-rate", c_rates, key="browser_dc_crate")
        pts = [pt for pt in db.discharge_pts
               if pt.chem_id == sel_chem_dc and abs(pt.c_rate - sel_crate) < 0.01]
        pts_sorted = sorted(pts, key=lambda p: p.soc_pct)
        if pts_sorted:
            fig2, ax2 = plt.subplots(figsize=(7, 4))
            ax2.plot([pt.soc_pct for pt in pts_sorted],
                     [pt.voltage_v for pt in pts_sorted],
                     color=chem_color(sel_chem_dc), linewidth=2, marker="o", markersize=4)
            ax2.set_xlabel("State of Charge (%)")
            ax2.set_ylabel("Cell Voltage (V)")
            ax2.set_title(f"{sel_chem_dc} — {sel_crate}C discharge curve")
            ax2.grid(alpha=0.3)
            ax2.invert_xaxis()
            fig2.tight_layout()
            st.pyplot(fig2, use_container_width=True)
            plt.close(fig2)

st.divider()
csv = df.to_csv(index=False).encode("utf-8")
st.download_button("Export filtered packs as CSV", data=csv,
                   file_name="battery_packs_filtered.csv", mime="text/csv")
