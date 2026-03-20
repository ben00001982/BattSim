"""Fix cell f10a93ff in notebooks/04_simulation.ipynb:
- Remove hardcoded COMPARE_PACK_IDS (use the one loaded from analysis_config.json)
- Generate colors dynamically
- Scale chart for variable battery count
"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/04_simulation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

src = """\
# COMPARE_PACK_IDS is loaded from analysis_config.json in the cell above.
# Override here if you want a specific subset:
# COMPARE_PACK_IDS = ["BAT_MID_6S2P", "BAT_MID_6S4P"]

COMPARE_TEMP = 15.0   # ambient temperature for comparison run

# ── Filter to packs that exist in db ─────────────────────────────────────────
valid_ids = [pid for pid in COMPARE_PACK_IDS if pid in db.packs]
if not valid_ids:
    print('No valid pack IDs in COMPARE_PACK_IDS — check battery selector output.')
else:
    compare_packs = [db.packs[pid] for pid in valid_ids]
    compare_results = compare_batteries(
        packs=compare_packs, mission=mission, uav=uav,
        discharge_pts=db.discharge_pts, ambient_temp_c=COMPARE_TEMP, dt_s=2.0)
    for r in compare_results:
        print(r.summary()); print()

    n_packs = len(compare_packs)

    # ── Generate a colour per pack from a qualitative colourmap ──────────────
    import matplotlib.cm as _cm
    _cmap = _cm.get_cmap('tab20', max(n_packs, 1))
    palette = [_cmap(i) for i in range(n_packs)]

    # ── Chart — line width and legend font scale with battery count ───────────
    lw      = max(0.8, 2.2 - n_packs * 0.04)
    leg_fs  = max(5, min(9, int(130 / n_packs)))
    fig_h   = max(8, min(14, 8 + n_packs * 0.06))

    fig, axes = plt.subplots(2, 2, figsize=(14, fig_h))
    fig.suptitle(f"Battery Comparison @ {COMPARE_TEMP}\u00b0C  ({n_packs} packs)",
                 fontsize=13, fontweight="bold")

    for r, p, col in zip(compare_results, compare_packs, palette):
        label = f"{r.pack_id[:30]} ({p.pack_energy_wh:.0f} Wh)"
        t_arr = np.array(r.time_s)
        axes[0,0].plot(t_arr, r.soc_pct,      color=col, linewidth=lw, label=label)
        axes[0,1].plot(t_arr, r.voltage_v,     color=col, linewidth=lw)
        axes[1,0].plot(t_arr,
                       np.array(r.dv_ohmic) + np.array(r.dv_ct) + np.array(r.dv_conc),
                       color=col, linewidth=lw)
        axes[1,1].plot(t_arr, r.temp_c,        color=col, linewidth=lw)

    for ax, (title, ylabel) in zip(axes.flat, [
            ("SoC",         "SoC (%)"),
            ("Voltage",     "V (V)"),
            ("Total Sag",   "Sag (V)"),
            ("Temperature", "Temp (\u00b0C)"),
    ]):
        ax.set_title(title); ax.set_ylabel(ylabel); ax.set_xlabel("Time (s)")

    # Legend below chart when there are many packs, inside when few
    if n_packs <= 8:
        axes[0,0].legend(fontsize=leg_fs, loc="lower left")
    else:
        fig.legend(loc="lower center", ncol=min(n_packs, 4),
                   fontsize=leg_fs, bbox_to_anchor=(0.5, 0.0))
        plt.tight_layout(rect=[0, max(0.02, n_packs * 0.008), 1, 1])

    plt.tight_layout()
    plt.savefig("multi_battery_compare.png", bbox_inches="tight", dpi=120)
    plt.show()"""

for i, c in enumerate(nb['cells']):
    if c['id'] == 'f10a93ff':
        nb['cells'][i]['source'] = lines(src)
        print(f'Updated cell f10a93ff (index {i})')
        break

with open('notebooks/04_simulation.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
