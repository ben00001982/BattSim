"""
Fix notebook 04:
1. Move config cell (a665107f) to index 2 (right after imports) so
   selected_pack_ids is available to all subsequent cells.
2. Rewrite Section 2 cell (0edd417b) to loop over all selected packs.
3. Update Section 3 header to reflect it now runs for all packs.
"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/04_simulation.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

# ── 1. Move config cell (a665107f) to position 2 (after imports) ──────────────
cells = nb['cells']
cfg_idx = next(i for i, c in enumerate(cells) if c['id'] == 'a665107f')
cfg_cell = cells.pop(cfg_idx)

# Insert right after the imports cell (d91d289a, which is index 1)
imports_idx = next(i for i, c in enumerate(cells) if c['id'] == 'd91d289a')
cells.insert(imports_idx + 1, cfg_cell)
print(f'Moved config cell a665107f to index {imports_idx + 1}')

# ── 2. Rewrite Section 2 cell (0edd417b) to loop all selected packs ───────────
sec2_src = """\
TEMPS_SAG  = [25, 0, -15]
SOC_FIXED  = 70.0

for _pid in selected_pack_ids:
    _pack  = db.packs[_pid]
    _powers = np.linspace(10, _pack.max_cont_discharge_w * 0.9, 120)
    _v_ocv  = _pack.pack_voltage_nom * 0.92

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle(f"{_pid} \\u2014 Voltage sag decomposition @ SoC={SOC_FIXED:.0f}%",
                 fontsize=12, fontweight="bold")

    for ax, temp in zip(axes, TEMPS_SAG):
        v_terms, dv_ohm, dv_ct, dv_conc = [], [], [], []
        for pw in _powers:
            v, i, bk = terminal_voltage(
                power_w=pw, soc_pct=SOC_FIXED, temp_c=temp,
                v_ocv_pack=_v_ocv,
                r_pack_mohm=_pack.internal_resistance_mohm,
                chem_id=_pack.chemistry_id,
                capacity_ah=_pack.pack_capacity_ah,
                cells_series=_pack.cells_series,
                cells_parallel=_pack.cells_parallel)
            v_terms.append(v)
            dv_ohm.append(bk["dv_ohmic"])
            dv_ct.append(bk["dv_ct"])
            dv_conc.append(bk["dv_conc"])

        ax.stackplot(_powers, dv_ohm, dv_ct, dv_conc,
                     labels=["Ohmic", "Charge transfer", "Concentration"],
                     colors=["#2196F3", "#FF9800", "#E91E63"], alpha=0.75)
        ax2 = ax.twinx()
        ax2.plot(_powers, v_terms, "k-", linewidth=2, label="V_terminal")
        ax2.set_ylabel("V_terminal (V)"); ax2.set_ylim(bottom=0)
        ax.set_xlabel("Power (W)"); ax.set_ylabel("Sag (V)")
        ax.set_title(f"T = {temp}\\u00b0C")
        if ax is axes[0]:
            ax.legend(loc="upper left", fontsize=8)

    safe_id = _pid.replace("/", "_")[:60]
    plt.tight_layout()
    plt.savefig(f"voltage_sag_{safe_id}.png", bbox_inches="tight")
    plt.show()"""

for i, c in enumerate(cells):
    if c['id'] == '0edd417b':
        cells[i]['source'] = lines(sec2_src)
        print(f'Updated Section 2 cell 0edd417b (index {i})')
        break

# ── 3. Update Section 3 header (b44c5e97) ─────────────────────────────────────
for i, c in enumerate(cells):
    if c['id'] == 'b44c5e97':
        cells[i]['source'] = lines('## 3 · Mission Simulation (all selected batteries)')
        print(f'Updated Section 3 header b44c5e97 (index {i})')
        break

nb['cells'] = cells

with open('notebooks/04_simulation.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
