"""
Rewrite cells in notebooks/04_simulation.ipynb so that sections 3, 4, and 7
run for ALL selected batteries from analysis_config.json instead of just the first.
"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/04_simulation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

# ── Cell a665107f  (config + run all simulations) ─────────────────────────────
cfg_src = """\
# ── Load settings from analysis_config.json (written by 02_configurator) ──────
import json as _json, os as _os
_CFG_PATH = _os.path.join(_os.path.dirname(_os.path.abspath('.')), 'analysis_config.json')
if not _os.path.exists(_CFG_PATH):
    _CFG_PATH = 'analysis_config.json'
_cfg = {}
if _os.path.exists(_CFG_PATH):
    with open(_CFG_PATH) as _f:
        _cfg = _json.load(_f)
    print(f'Loaded config from {_CFG_PATH}')
else:
    print('No analysis_config.json found — using defaults (run 02_configurator first)')

# ── Mission / UAV / temperature settings ──────────────────────────────────────
SIM_MISSION_ID = _cfg.get('mission_id',     'SURVEY_STD')
SIM_UAV_ID     = _cfg.get('uav_id',         'HEX_SURVEY_900')
AMBIENT_TEMP_C = _cfg.get('ambient_temp_c', 25.0)
TEMP_SWEEP     = _cfg.get('temp_sweep',     [-25, -10, 0, 15, 25, 40])

# ── Selected batteries (all of them) ──────────────────────────────────────────
_sel = _cfg.get('selected_batteries', ['BAT_MID_6S2P'])
selected_pack_ids = _sel if isinstance(_sel, list) else ['BAT_MID_6S2P']
COMPARE_PACK_IDS  = selected_pack_ids   # alias used by Section 5

# Filter to IDs that exist in the database
selected_pack_ids = [pid for pid in selected_pack_ids if pid in db.packs]
if not selected_pack_ids:
    selected_pack_ids = list(db.packs.keys())[:3]
    print(f'WARNING: no valid IDs from config — falling back to first 3 packs')

# ── Reconstruct combined pack if configured ────────────────────────────────────
_combo_cfg = _cfg.get('battery_combination')
if _combo_cfg:
    from batteries.builder import combine_packs as _combine_packs
    _combo_packs = [db.packs[bid] for bid in _combo_cfg.get('packs', []) if bid in db.packs]
    if len(_combo_packs) >= 2:
        _combined = _combine_packs(_combo_packs, topology=_combo_cfg.get('topology', 'series'))
        db.packs[_combined.battery_id] = _combined
        print(f'Combined pack registered: {_combined.battery_id}')

# ── Manual overrides ──────────────────────────────────────────────────────────
# selected_pack_ids = ['BAT_MID_6S2P', 'BAT_MID_6S4P']   # override selection
# AMBIENT_TEMP_C = 25.0

# ── Shared mission / UAV objects ──────────────────────────────────────────────
mission = db.missions[SIM_MISSION_ID]
uav     = db.uav_configs[SIM_UAV_ID]

# ── Run simulation for every selected battery ─────────────────────────────────
print(f'\\nRunning simulation for {len(selected_pack_ids)} pack(s) '
      f'on mission "{SIM_MISSION_ID}" @ {AMBIENT_TEMP_C}\\u00b0C ...')

all_results = {}
for _pid in selected_pack_ids:
    _pack = db.packs[_pid]
    all_results[_pid] = run_simulation(
        pack=_pack, mission=mission, uav=uav,
        discharge_pts=db.discharge_pts, initial_soc_pct=100.0,
        ambient_temp_c=AMBIENT_TEMP_C, peukert_k=1.05, dt_s=1.0)
    print(f'  {_pid[:50]:<50}  {all_results[_pid].summary().splitlines()[0]}')

# Keep first-pack aliases for cells that reference them directly
pack   = db.packs[selected_pack_ids[0]]
result = all_results[selected_pack_ids[0]]"""

# ── Cell 0ab46ea4  (Section 3: simulation dashboard — loop all packs) ─────────
dash_src = """\
PHASE_COLORS = {
    "IDLE":            "#AAAAAA",
    "TAKEOFF":         "#FF9944",
    "CLIMB":           "#FFCC44",
    "CRUISE":          "#44AA66",
    "HOVER":           "#4488FF",
    "DESCEND":         "#88AADD",
    "LAND":            "#CC88DD",
    "PAYLOAD_OPS":     "#FF6688",
    "EMERGENCY":       "#FF2222",
    "VTOL_TRANSITION": "#FF6611",
    "VTOL_HOVER":      "#22AAFF",
    "FW_CRUISE":       "#00CC77",
    "FW_CLIMB":        "#AACC44",
    "FW_DESCEND":      "#99CCEE",
}

def shade_phases(ax, res):
    prev, t0 = res.phase_type[0], res.time_s[0]
    for t, ph in zip(res.time_s[1:], res.phase_type[1:]):
        if ph != prev:
            ax.axvspan(t0, t, alpha=0.12, color=PHASE_COLORS.get(prev, "#CCC"))
            t0 = t
        prev = ph
    ax.axvspan(t0, res.time_s[-1], alpha=0.12, color=PHASE_COLORS.get(prev, "#CCC"))

for _pid in selected_pack_ids:
    _pack = db.packs[_pid]
    res   = all_results[_pid]
    t     = np.array(res.time_s)

    fig = plt.figure(figsize=(16, 14))
    gs  = GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)
    fig.suptitle(f"{_pid}  \\u00d7  {SIM_MISSION_ID} @ {AMBIENT_TEMP_C}\\u00b0C",
                 fontsize=13, fontweight="bold")

    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(t, res.soc_pct, "#2196F3", linewidth=2)
    ax1.axhline(20, color="orange", linestyle="--", linewidth=1, label="20% warning")
    ax1.axhline(10, color="red",    linestyle="--", linewidth=1, label="10% cutoff")
    shade_phases(ax1, res)
    ax1.set_ylabel("SoC (%)"); ax1.set_title("State of Charge")
    ax1.legend(fontsize=8); ax1.set_ylim(0, 105)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(t, res.voltage_v, "#E53935", linewidth=2, label="V_terminal")
    ax2.axhline(_pack.pack_voltage_cutoff, color="red", linestyle="--", linewidth=1,
                label=f"Cutoff ({_pack.pack_voltage_cutoff}V)")
    shade_phases(ax2, res)
    ax2.set_ylabel("Voltage (V)"); ax2.set_title("Terminal Voltage")
    ax2.legend(fontsize=8)

    ax3 = fig.add_subplot(gs[1, 0])
    ax3.stackplot(t, res.dv_ohmic, res.dv_ct, res.dv_conc,
                  labels=["dV_ohmic", "dV_ct", "dV_conc"],
                  colors=["#2196F3", "#FF9800", "#E91E63"], alpha=0.80, zorder=3)
    shade_phases(ax3, res)
    ax3.set_ylabel("Sag (V)"); ax3.set_title("Voltage Sag Decomposition")
    ax3.legend(fontsize=8, loc="upper right")

    ax4 = fig.add_subplot(gs[1, 1])
    ax4.plot(t, res.current_a, "#9C27B0", linewidth=1.8)
    ax4.axhline(_pack.max_cont_discharge_a, color="red", linestyle="--", linewidth=1,
                label=f"Max cont. ({_pack.max_cont_discharge_a}A)")
    shade_phases(ax4, res)
    ax4.set_ylabel("Current (A)"); ax4.set_title("Discharge Current")
    ax4.legend(fontsize=8)

    ax5 = fig.add_subplot(gs[2, 0])
    ax5.plot(t, res.temp_c, "#FF5722", linewidth=2, label="Cell temp")
    ax5.axhline(AMBIENT_TEMP_C, color="steelblue", linestyle="--", linewidth=1, label="Ambient")
    shade_phases(ax5, res)
    ax5.set_xlabel("Time (s)"); ax5.set_ylabel("Temp (\\u00b0C)")
    ax5.set_title("Cell Temperature"); ax5.legend(fontsize=8)

    ax6  = fig.add_subplot(gs[2, 1])
    ax6b = ax6.twinx()
    ax6.fill_between(t, res.energy_wh, alpha=0.3, color="firebrick")
    ax6.plot(t, res.energy_wh, "firebrick", linewidth=1.5, label="Cumul. energy")
    ax6b.plot(t, res.power_w, "#1565C0", linewidth=1.2, alpha=0.6)
    ax6.axhline(_pack.pack_energy_wh * 0.80, color="orange", linestyle="--", linewidth=1,
                label=f"80% DoD ({_pack.pack_energy_wh * 0.8:.0f} Wh)")
    ax6.set_xlabel("Time (s)")
    ax6.set_ylabel("Cumulative energy (Wh)", color="firebrick")
    ax6b.set_ylabel("Power (W)", color="#1565C0")
    ax6.set_title("Energy and Power")
    ax6.legend(fontsize=8, loc="upper left")

    patches = [mpatches.Patch(color=PHASE_COLORS.get(p, "#888"), label=p)
               for p in sorted(set(res.phase_type))]
    fig.legend(handles=patches, loc="lower center", ncol=8, fontsize=8,
               title="Flight phase")

    safe_id = _pid.replace("/", "_")[:60]
    plt.savefig(f"simulation_{safe_id}.png", bbox_inches="tight")
    plt.show()"""

# ── Cell a6f44c98  (Section 4: temperature sweep data — loop all packs) ───────
sweep_data_src = """\
TEMPS_SWEEP = [-25, -20, -15, -10, -5, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45]

print(f'Running temperature sweep for {len(selected_pack_ids)} pack(s) '
      f'over {len(TEMPS_SWEEP)} temperatures ...')

all_sweeps   = {}   # pid -> (list of SimResult)
all_df_sweep = {}   # pid -> DataFrame

for _pid in selected_pack_ids:
    _pack = db.packs[_pid]
    _res  = temperature_sweep(
        pack=_pack, mission=mission, uav=uav,
        discharge_pts=db.discharge_pts,
        temperatures_c=TEMPS_SWEEP, dt_s=5.0)
    all_sweeps[_pid] = _res
    all_df_sweep[_pid] = pd.DataFrame([{
        "Ambient (C)":      t,
        "Final SoC (%)":    round(r.final_soc, 1),
        "Duration (s)":     round(r.total_duration_s, 0),
        "Energy used (Wh)": round(r.total_energy_consumed_wh, 1),
        "Min V (V)":        round(r.min_voltage, 3),
        "Peak sag (V)":     round(r.peak_sag_v, 3),
        "Max I (A)":        round(r.max_current, 1),
        "Max T (\\u00b0C)":   round(r.max_temp_c, 1),
        "Depleted":         r.depleted,
        "Cutoff":           r.cutoff_reason or "none",
    } for t, r in zip(TEMPS_SWEEP, _res)])
    print(f'\\n{_pid}:')
    print(all_df_sweep[_pid].to_string(index=False))

# Keep first-pack alias for the chart cell
df_sweep = all_df_sweep[selected_pack_ids[0]]"""

# ── Cell 79526b12  (Section 4: temperature sweep chart — all packs overlaid) ──
sweep_chart_src = """\
import matplotlib.cm as _cm2

n_sw    = len(selected_pack_ids)
_cmap2  = _cm2.get_cmap('tab20', max(n_sw, 1))
sw_cols = [_cmap2(i) for i in range(n_sw)]
lw_sw   = max(0.9, 2.2 - n_sw * 0.06)
leg_sw  = max(5, min(9, int(130 / n_sw)))

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle(f"Temperature Sensitivity — {len(selected_pack_ids)} pack(s)",
             fontsize=13, fontweight="bold")

for _pid, col in zip(selected_pack_ids, sw_cols):
    df = all_df_sweep[_pid]
    _pack = db.packs[_pid]
    t_vals = df["Ambient (C)"].values
    lbl    = _pid[:30]

    axes[0, 0].plot(t_vals, df["Final SoC (%)"],    color=col, linewidth=lw_sw, label=lbl)
    axes[0, 1].plot(t_vals, df["Peak sag (V)"],     color=col, linewidth=lw_sw)
    axes[1, 0].plot(t_vals, df["Min V (V)"],        color=col, linewidth=lw_sw)
    axes[1, 1].plot(t_vals, df["Max T (\\u00b0C)"] - t_vals, color=col, linewidth=lw_sw)

axes[0, 0].axhline(20, color="orange", linestyle="--", linewidth=1)
axes[0, 0].axhline(10, color="red",    linestyle="--", linewidth=1)
axes[0, 0].set_xlabel("Ambient (\\u00b0C)"); axes[0, 0].set_ylabel("Final SoC (%)")
axes[0, 0].set_title("Final SoC")

axes[0, 1].fill_between(t_vals, 0, all_df_sweep[selected_pack_ids[0]]["Peak sag (V)"],
                         alpha=0.08, color="grey")
axes[0, 1].set_xlabel("Ambient (\\u00b0C)"); axes[0, 1].set_ylabel("Peak sag (V)")
axes[0, 1].set_title("Peak Voltage Sag")

axes[1, 0].set_xlabel("Ambient (\\u00b0C)"); axes[1, 0].set_ylabel("Min V (V)")
axes[1, 0].set_title("Min Terminal Voltage")

axes[1, 1].set_xlabel("Ambient (\\u00b0C)"); axes[1, 1].set_ylabel("Temp rise (\\u00b0C)")
axes[1, 1].set_title("Self-heating (rise above ambient)")

if n_sw <= 8:
    axes[0, 0].legend(fontsize=leg_sw, loc="lower left")
else:
    fig.legend(loc="lower center", ncol=min(n_sw, 4),
               fontsize=leg_sw, bbox_to_anchor=(0.5, 0.0))
    plt.tight_layout(rect=[0, max(0.03, n_sw * 0.009), 1, 1])

plt.tight_layout()
plt.savefig("temperature_sensitivity.png", bbox_inches="tight", dpi=120)
plt.show()"""

# ── Cell 404cb353  (Section 7: export all results) ────────────────────────────
export_src = """\
import os as _os2
_export_dir = 'simulation_results'
_os2.makedirs(_export_dir, exist_ok=True)

for _pid, res in all_results.items():
    df_out = pd.DataFrame({
        "time_s":       res.time_s,
        "phase":        res.phase_type,
        "soc_pct":      res.soc_pct,
        "voltage_v":    res.voltage_v,
        "current_a":    res.current_a,
        "power_w":      res.power_w,
        "temp_c":       res.temp_c,
        "energy_wh":    res.energy_wh,
        "dv_ohmic":     res.dv_ohmic,
        "dv_ct":        res.dv_ct,
        "dv_conc":      res.dv_conc,
        "r_total_mohm": res.r_total,
    })
    safe = _pid.replace("/", "_")[:60]
    fname = _os2.path.join(_export_dir,
                           f"{safe}_{SIM_MISSION_ID}_{int(AMBIENT_TEMP_C)}C.csv")
    df_out.to_csv(fname, index=False)
    print(f'Saved {len(df_out):>5} rows  \\u2192  {fname}')

print(f'\\nExported {len(all_results)} file(s) to ./{_export_dir}/')
all_results[selected_pack_ids[0]]   # display last result object"""

# ── Apply all cell updates ─────────────────────────────────────────────────────
updates = {
    'a665107f': cfg_src,
    '0ab46ea4': dash_src,
    'a6f44c98': sweep_data_src,
    '79526b12': sweep_chart_src,
    '404cb353': export_src,
}

for i, c in enumerate(nb['cells']):
    if c['id'] in updates:
        nb['cells'][i]['source'] = lines(updates[c['id']])
        print(f'Updated cell {c["id"]} (index {i})')

with open('notebooks/04_simulation.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
