"""
ui/Main_Dashboard.py
BattSim — UAV Battery Analysis Tool
Streamlit home dashboard.

Run from project root:
    streamlit run ui/Main_Dashboard.py
"""
import sys
from pathlib import Path
# Ensure project root is on sys.path so 'ui' and 'batteries' packages resolve
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import streamlit as st

# Must be first Streamlit call
st.set_page_config(
    page_title="Main Dashboard",
    page_icon="🔋",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.components.db_helpers import load_db, load_config
from ui.config import CHEM_COLORS, ACCENT

# ── Session state initialisation ─────────────────────────────────────────────
if "sim_results" not in st.session_state:
    st.session_state["sim_results"] = {}   # {pack_id: SimulationResult}
if "sweep_results" not in st.session_state:
    st.session_state["sweep_results"] = {}  # {pack_id: list[SimulationResult]}
if "flight_log" not in st.session_state:
    st.session_state["flight_log"] = None
if "config" not in st.session_state:
    st.session_state["config"] = load_config()

# ── Load database ─────────────────────────────────────────────────────────────
try:
    db = load_db()
    db_ok = True
except Exception as e:
    db_ok = False
    st.error(f"Failed to load database: {e}")

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🔋 BattSim — UAV Battery Analysis Tool")
st.caption("Physics-based battery discharge simulation and selection tool for UAV missions.")
st.caption("📖 First time here? Check the **[User Guide](8_User_Guide)** for a complete walkthrough of all features.")

if not db_ok:
    st.stop()

# ── KPI cards ─────────────────────────────────────────────────────────────────
cfg = st.session_state["config"]

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("Battery Packs", len(db.packs))
with col2:
    st.metric("Cell Types", len(db.cells))
with col3:
    st.metric("Missions", len(db.missions))
with col4:
    st.metric("UAV Configs", len(db.uav_configs))
with col5:
    st.metric("Chemistries", len(db.chemistries))

st.divider()

# ── Active config summary ─────────────────────────────────────────────────────
col_cfg, col_status = st.columns([2, 1])

with col_cfg:
    st.subheader("Active Configuration")
    if cfg:
        sel_bats = cfg.get("selected_batteries", [])
        st.write(f"**Mission:** `{cfg.get('mission_id', '—')}`")
        st.write(f"**UAV:** `{cfg.get('uav_id', '—')}`")
        st.write(f"**Ambient temperature:** {cfg.get('ambient_temp_c', 25.0)} °C")
        st.write(f"**Selected batteries ({len(sel_bats)}):**")
        if sel_bats:
            for bid in sel_bats:
                pack = db.packs.get(bid)
                if pack:
                    st.write(f"  - `{bid}` — {pack.pack_energy_wh:.0f} Wh, {pack.pack_weight_g:.0f} g, {pack.chemistry_id}")
                else:
                    st.write(f"  - `{bid}` ⚠ not found in DB")
        sweep = cfg.get("temp_sweep", [])
        if sweep:
            st.write(f"**Temp sweep:** {min(sweep)}°C → {max(sweep)}°C ({len(sweep)} points)")
    else:
        st.info("No configuration found. Go to **Mission Configurator** to set up a mission.")

with col_status:
    st.subheader("Simulation Status")
    sim_count = len(st.session_state["sim_results"])
    sweep_count = len(st.session_state["sweep_results"])
    log_loaded = st.session_state["flight_log"] is not None

    st.metric("Simulation results", sim_count)
    st.metric("Temp sweep results", sweep_count)
    if log_loaded:
        log = st.session_state["flight_log"]
        st.success(f"Flight log: {log.total_flight_s:.0f} s ({log.total_flight_s/60:.1f} min)")
    else:
        st.info("No flight log loaded")

    st.divider()
    st.write("**Reset**")
    if st.button("🔄 Reset Analysis Config", key="dash_reset_cfg",
                 help="Clears selected batteries, mission, UAV and all simulation results."):
        from ui.components.db_helpers import save_config
        empty_cfg = {
            "mission_id": None,
            "uav_id": None,
            "ambient_temp_c": 25.0,
            "temp_sweep": list(range(-10, 46, 5)),
            "selected_batteries": [],
            "custom_equipment": {},
            "battery_combination": None,
            "combined_pack_id": None,
        }
        save_config(empty_cfg)
        st.session_state["config"] = empty_cfg
        st.session_state["sim_results"] = {}
        st.session_state["sweep_results"] = {}
        st.session_state["flight_log"] = None
        st.session_state.pop("cfg_batteries", None)
        st.session_state.pop("browser_selected_packs", None)
        st.success("Analysis config reset.")
        st.rerun()

st.divider()

# ── Database overview ─────────────────────────────────────────────────────────
st.subheader("Database Overview")

col_a, col_b = st.columns(2)

with col_a:
    st.write("**Chemistry breakdown**")
    chem_counts: dict[str, int] = {}
    for p in db.packs.values():
        chem_counts[p.chemistry_id] = chem_counts.get(p.chemistry_id, 0) + 1
    chem_df_data = {
        "Chemistry": list(chem_counts.keys()),
        "Packs": list(chem_counts.values()),
    }
    import pandas as pd
    chem_df = pd.DataFrame(chem_df_data).sort_values("Packs", ascending=False)
    st.dataframe(chem_df, use_container_width=True, hide_index=True)

with col_b:
    st.write("**Energy range by chemistry**")
    rows = []
    for chem in sorted(chem_counts.keys()):
        packs_c = [p for p in db.packs.values() if p.chemistry_id == chem]
        energies = [p.pack_energy_wh for p in packs_c]
        rows.append({
            "Chemistry": chem,
            "Min Wh": round(min(energies), 0),
            "Max Wh": round(max(energies), 0),
            "Avg Wh/kg": round(sum(p.specific_energy_wh_kg for p in packs_c) / len(packs_c), 0),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

st.divider()

# ── Quick navigation ──────────────────────────────────────────────────────────
st.subheader("Quick Navigation")
nav_cols = st.columns(6)
pages = [
    ("1 Battery Browser",     "Browse and compare all battery packs in the database"),
    ("2 UAV Configurator",    "Add equipment, build and edit UAV power profiles"),
    ("3 Mission Configurator","Select batteries, mission, and UAV — save analysis config"),
    ("4 Simulation",          "Run discharge simulations for all selected battery packs"),
    ("5 Reports",             "Generate Excel/PDF reports and temperature sweeps"),
    ("6 Tools",               "Pack Builder, Log Analysis, and Bulk Data Upload"),
]
for col, (name, desc) in zip(nav_cols, pages):
    with col:
        st.info(f"**{name}**\n\n{desc}")
