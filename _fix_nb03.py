"""Fix notebook 03 syntax errors: literal newlines in strings + duplicate PHASE_COLORS."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/03_simulation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

fixes = 0

for i, c in enumerate(nb['cells']):
    if c['cell_type'] != 'code':
        continue
    cid = c['id']

    # ── cca03303: literal \n in print() strings ────────────────────────────────
    if cid == 'cca03303':
        src = """\
temps = np.linspace(-30, 55, 200)
chemistries = ["LIPO", "LION21", "LIFEPO4", "SSS", "LITO"]
R_REF = 28.0
fig, axes = plt.subplots(1, 2, figsize=(14, 5))
fig.suptitle("Pack Resistance vs Temperature", fontsize=13, fontweight="bold")
colors = ["#2196F3","#4CAF50","#FF9800","#9C27B0","#009688"]
for chem, color in zip(chemistries, colors):
    r_ohm = [r_ohmic_mohm(R_REF, chem, t) for t in temps]
    r_ct  = [r_ct_mohm(R_REF, chem, t, 80) for t in temps]
    r_tot = [ro+rc for ro,rc in zip(r_ohm,r_ct)]
    axes[0].plot(temps, r_ohm, color=color, linewidth=1.5, linestyle="--")
    axes[0].plot(temps, r_tot, color=color, linewidth=2.5, label=chem)
    axes[1].plot(temps, [r/R_REF for r in r_tot], color=color, linewidth=2, label=chem)
for ax in axes:
    ax.axvline(25,  color="black",    linewidth=0.8, linestyle=":", alpha=0.5)
    ax.axvline(0,   color="steelblue", linewidth=0.8, linestyle=":", alpha=0.4)
    ax.axvline(-25, color="red",       linewidth=0.8, linestyle=":", alpha=0.4)
axes[0].set_xlabel("Temperature (\u00b0C)"); axes[0].set_ylabel("Resistance (m\u03a9)")
axes[0].set_title("Absolute: dashed=R_ohmic, solid=R_total"); axes[0].legend(fontsize=8)
axes[1].set_xlabel("Temperature (\u00b0C)"); axes[1].set_ylabel("R(T)/R(25\u00b0C)")
axes[1].set_title("Normalised (1.0 = 25\u00b0C reference)    \u25c4 red line = \u221225\u00b0C")
axes[1].legend(fontsize=8)
plt.tight_layout(); plt.savefig("resistance_vs_temperature.png", bbox_inches="tight"); plt.show()

rows = []
for chem in chemistries:
    for t in [-25,-15,-5,0,15,25,40]:
        r = total_pack_resistance_mohm(R_REF, chem, t, 80)
        rows.append({"Chemistry":chem,"Temp (\u00b0C)":t,"Multiplier":round(r/R_REF,2)})
tbl = pd.DataFrame(rows).pivot_table(index="Chemistry", columns="Temp (\u00b0C)", values="Multiplier")
print("\\nResistance multiplier vs temperature (relative to 25\u00b0C):")
print(tbl.to_string())
print("\\nNote: multipliers >1 are physical \u2014 cold electrolyte raises both ohmic and")
print("      charge-transfer resistance via Arrhenius kinetics.")
print("      High values (e.g. 10x at -25\u00b0C for LIFEPO4) mean the pack will trigger")
print("      its voltage-cutoff BMS protection before SoC reaches zero.")"""
        nb['cells'][i]['source'] = lines(src)
        fixes += 1
        print(f'Fixed cca03303')

    # ── 0ab46ea4: shade_phases + dashboard — remove duplicate PHASE_COLORS ─────
    elif cid == '0ab46ea4':
        src = """\
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

t = np.array(result.time_s)
fig = plt.figure(figsize=(16,14))
gs  = GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)
fig.suptitle(f"{SIM_PACK_ID} x {SIM_MISSION_ID} @ {AMBIENT_TEMP_C}C", fontsize=14, fontweight="bold")
ax1 = fig.add_subplot(gs[0,0])
ax1.plot(t, result.soc_pct, "#2196F3", linewidth=2)
ax1.axhline(20, color="orange", linestyle="--", linewidth=1, label="20% warning")
ax1.axhline(10, color="red",    linestyle="--", linewidth=1, label="10% cutoff")
shade_phases(ax1, result); ax1.set_ylabel("SoC (%)"); ax1.set_title("State of Charge")
ax1.legend(fontsize=8); ax1.set_ylim(0,105)
ax2 = fig.add_subplot(gs[0,1])
ax2.plot(t, result.voltage_v, "#E53935", linewidth=2, label="V_terminal")
ax2.axhline(pack.pack_voltage_cutoff, color="red", linestyle="--", linewidth=1,
            label=f"Cutoff ({pack.pack_voltage_cutoff}V)")
shade_phases(ax2, result); ax2.set_ylabel("Voltage (V)"); ax2.set_title("Terminal Voltage")
ax2.legend(fontsize=8)
ax3 = fig.add_subplot(gs[1,0])
ax3.stackplot(t, result.dv_ohmic, result.dv_ct, result.dv_conc,
    labels=["dV_ohmic","dV_ct","dV_conc"],
    colors=["#2196F3","#FF9800","#E91E63"], alpha=0.80, zorder=3)
shade_phases(ax3, result); ax3.set_ylabel("Sag (V)"); ax3.set_title("Voltage Sag Decomposition")
ax3.legend(fontsize=8, loc="upper right")
ax4 = fig.add_subplot(gs[1,1])
ax4.plot(t, result.current_a, "#9C27B0", linewidth=1.8)
ax4.axhline(pack.max_cont_discharge_a, color="red", linestyle="--", linewidth=1,
            label=f"Max cont. ({pack.max_cont_discharge_a}A)")
shade_phases(ax4, result); ax4.set_ylabel("Current (A)"); ax4.set_title("Discharge Current")
ax4.legend(fontsize=8)
ax5 = fig.add_subplot(gs[2,0])
ax5.plot(t, result.temp_c, "#FF5722", linewidth=2, label="Cell temp")
ax5.axhline(AMBIENT_TEMP_C, color="steelblue", linestyle="--", linewidth=1, label="Ambient")
shade_phases(ax5, result); ax5.set_xlabel("Time (s)"); ax5.set_ylabel("Temp (C)")
ax5.set_title("Cell Temperature"); ax5.legend(fontsize=8)
ax6  = fig.add_subplot(gs[2,1]); ax6b = ax6.twinx()
ax6.fill_between(t, result.energy_wh, alpha=0.3, color="firebrick")
ax6.plot(t, result.energy_wh, "firebrick", linewidth=1.5, label="Cumul. energy")
ax6b.plot(t, result.power_w, "#1565C0", linewidth=1.2, alpha=0.6)
ax6.axhline(pack.pack_energy_wh * 0.80, color="orange", linestyle="--", linewidth=1,
            label=f"80% DoD ({pack.pack_energy_wh*0.8:.0f}Wh)")
ax6.set_xlabel("Time (s)"); ax6.set_ylabel("Cumulative energy (Wh)", color="firebrick")
ax6b.set_ylabel("Power (W)", color="#1565C0"); ax6.set_title("Energy and Power")
ax6.legend(fontsize=8, loc="upper left")
patches = [mpatches.Patch(color=PHASE_COLORS.get(p, "#888"), label=p)
           for p in sorted(set(result.phase_type))]
fig.legend(handles=patches, loc="lower center", ncol=8, fontsize=8, title="Flight phase")
plt.savefig("simulation_dashboard.png", bbox_inches="tight"); plt.show()"""
        nb['cells'][i]['source'] = lines(src)
        fixes += 1
        print(f'Fixed 0ab46ea4')

    # ── a6f44c98: literal \n in print() string ─────────────────────────────────
    elif cid == 'a6f44c98':
        src = ''.join(c['source'])
        src = src.replace(
            'print("\n' + 'Note: Voltage cutoff = pack BMS triggers before SoC depletes (common in cold temps)")',
            'print("\\nNote: Voltage cutoff = pack BMS triggers before SoC depletes (common in cold temps)")'
        )
        nb['cells'][i]['source'] = lines(src)
        fixes += 1
        print(f'Fixed a6f44c98')

with open('notebooks/03_simulation.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print(f'Done — {fixes} cell(s) fixed')
