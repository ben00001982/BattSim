"""Build notebooks/00_battery_selector.ipynb"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def code_cell(source, cell_id):
    return {'cell_type': 'code', 'execution_count': None, 'id': cell_id,
            'metadata': {}, 'outputs': [], 'source': lines(source)}

def md_cell(source, cell_id):
    return {'cell_type': 'markdown', 'id': cell_id, 'metadata': {}, 'source': lines(source)}

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

cells = []

# ── Title ─────────────────────────────────────────────────────────────────────
cells.append(md_cell("""\
# UAV Battery Tool — Notebook 08: Battery Selection Tool

Filter the battery catalogue by mission requirements and add selected packs to
the configurator for analysis.

**Workflow:**
1. Set filter criteria (series rating, capacity, current, chemistry, weight)
2. Review the filtered and ranked list
3. Select batteries to carry forward
4. Save selection to `analysis_config.json` for use in all other notebooks\
""", 'nb08-title'))

# ── Imports ───────────────────────────────────────────────────────────────────
cells.append(code_cell("""\
import sys, os, json
sys.path.insert(0, os.path.abspath('..'))
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from batteries.database import BatteryDatabase

plt.rcParams.update({'figure.dpi': 120, 'font.size': 10,
                     'axes.grid': True, 'grid.alpha': 0.25})

DB_PATH = '../battery_db.xlsx'
db = BatteryDatabase(DB_PATH) if os.path.exists(DB_PATH) else BatteryDatabase()
db.load()

print(f'Catalogue loaded: {len(db.packs)} battery packs')
print(f'Chemistries available: {sorted(set(p.chemistry_id for p in db.packs.values()))}')
print()
print('All packs:')
for pid, p in db.packs.items():
    print(f'  {pid:<30} {p.chemistry_id:<10} {p.cells_series}S{p.cells_parallel}P  '
          f'{p.pack_capacity_ah*1000:.0f} mAh  {p.max_cont_discharge_a:.0f} A  '
          f'{p.pack_weight_g:.0f} g')\
""", 'nb08-imports'))

# ── Filters ───────────────────────────────────────────────────────────────────
cells.append(md_cell("## 1 · Set Filter Criteria", 'nb08-filter-hdr'))

cells.append(code_cell("""\
# ═══════════════════════════════════════════════════════════════════════════════
# FILTER CRITERIA  —  set None to skip a filter
# ═══════════════════════════════════════════════════════════════════════════════

CELLS_SERIES      = None    # e.g. 6  — exact series cell count (None = any)
MIN_CAPACITY_MAH  = 4000    # minimum pack capacity in mAh (None = any)
MIN_CONT_CURRENT  = 20.0    # minimum max continuous discharge current in A (None = any)
CHEMISTRY         = None    # e.g. 'LIPO', 'LION21', 'LIFEPO4' (None = any)
MAX_WEIGHT_G      = None    # maximum pack weight in grams (None = any)

# ───────────────────────────────────────────────────────────────────────────────
print('Active filters:')
print(f'  Cells series     : {CELLS_SERIES   if CELLS_SERIES   is not None else "any"}')
print(f'  Min capacity     : {MIN_CAPACITY_MAH if MIN_CAPACITY_MAH is not None else "any"} mAh')
print(f'  Min cont current : {MIN_CONT_CURRENT if MIN_CONT_CURRENT is not None else "any"} A')
print(f'  Chemistry        : {CHEMISTRY      if CHEMISTRY      is not None else "any"}')
print(f'  Max weight       : {MAX_WEIGHT_G   if MAX_WEIGHT_G   is not None else "any"} g')\
""", 'nb08-filters'))

# ── Apply filters & ranked table ──────────────────────────────────────────────
cells.append(md_cell("## 2 · Filtered & Ranked Results", 'nb08-results-hdr'))

cells.append(code_cell("""\
def filter_packs(packs_dict,
                 cells_series=None,
                 min_capacity_mah=None,
                 min_cont_current=None,
                 chemistry=None,
                 max_weight_g=None):
    \"\"\"
    Return a filtered, weight-sorted DataFrame of BatteryPack entries.

    Parameters
    ----------
    cells_series      : int   — exact series cell count
    min_capacity_mah  : float — minimum pack capacity [mAh]
    min_cont_current  : float — minimum max continuous discharge current [A]
    chemistry         : str   — chemistry ID (case-insensitive)
    max_weight_g      : float — maximum pack weight [g]
    \"\"\"
    rows = []
    for pid, p in packs_dict.items():
        # ── Apply each filter ────────────────────────────────────────────────
        if cells_series is not None and p.cells_series != int(cells_series):
            continue
        if min_capacity_mah is not None and p.pack_capacity_ah * 1000 < min_capacity_mah:
            continue
        if min_cont_current is not None and p.max_cont_discharge_a < min_cont_current:
            continue
        if chemistry is not None and p.chemistry_id.upper() != chemistry.upper():
            continue
        if max_weight_g is not None and p.pack_weight_g > max_weight_g:
            continue

        rows.append({
            'ID':              pid,
            'Name':            p.name,
            'Chemistry':       p.chemistry_id,
            'Config':          f'{p.cells_series}S{p.cells_parallel}P',
            'Capacity (mAh)':  int(p.pack_capacity_ah * 1000),
            'Voltage (V)':     p.pack_voltage_nom,
            'Energy (Wh)':     p.pack_energy_wh,
            'Max I cont (A)':  p.max_cont_discharge_a,
            'Max P cont (W)':  p.max_cont_discharge_w,
            'IR (m\u03a9)':       p.internal_resistance_mohm,
            'Weight (g)':      p.pack_weight_g,
            'Sp. Energy (Wh/kg)': p.specific_energy_wh_kg,
            'Cycles':          p.cycle_life,
            'UAV class':       p.uav_class or '\u2014',
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values('Weight (g)').reset_index(drop=True)


df_filtered = filter_packs(
    db.packs,
    cells_series=CELLS_SERIES,
    min_capacity_mah=MIN_CAPACITY_MAH,
    min_cont_current=MIN_CONT_CURRENT,
    chemistry=CHEMISTRY,
    max_weight_g=MAX_WEIGHT_G,
)

print(f'{len(df_filtered)} pack(s) match the criteria:')
print()
if df_filtered.empty:
    print('  No packs match. Try relaxing the filters.')
else:
    display_cols = ['ID','Chemistry','Config','Capacity (mAh)','Voltage (V)',
                    'Energy (Wh)','Max I cont (A)','IR (m\u03a9)','Weight (g)',
                    'Sp. Energy (Wh/kg)','Cycles']
    print(df_filtered[display_cols].to_string(index=True))
    print()
    print(f'Lightest : {df_filtered.iloc[0][\"ID\"]}  ({df_filtered.iloc[0][\"Weight (g)\"]:.0f} g)')
    print(f'Highest energy: {df_filtered.loc[df_filtered[\"Energy (Wh)\"].idxmax(), \"ID\"]}  '
          f'({df_filtered[\"Energy (Wh)\"].max():.0f} Wh)')\
""", 'nb08-apply'))

# ── Comparison chart ──────────────────────────────────────────────────────────
cells.append(md_cell("## 3 · Visual Comparison", 'nb08-chart-hdr'))

cells.append(code_cell("""\
CHEM_COLORS = {
    'LIPO':    '#FFB347',
    'LION21':  '#4488FF',
    'LION':    '#82B4FF',
    'LIFEPO4': '#66BB6A',
    'SSS':     '#AB47BC',
    'LITO':    '#26C6DA',
    'SOLID':   '#FF7043',
    'NIMH':    '#90A4AE',
}

if not df_filtered.empty:
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle('Filtered Battery Comparison', fontsize=13, fontweight='bold')

    colors = [CHEM_COLORS.get(c, '#888') for c in df_filtered['Chemistry']]

    # ── Energy vs Weight ──────────────────────────────────────────────────────
    ax = axes[0]
    ax.scatter(df_filtered['Weight (g)'], df_filtered['Energy (Wh)'],
               c=colors, s=120, edgecolors='black', linewidths=0.6, zorder=4)
    for _, row in df_filtered.iterrows():
        ax.annotate(row['ID'], (row['Weight (g)'], row['Energy (Wh)']),
                    textcoords='offset points', xytext=(5, 4), fontsize=7)
    ax.set_xlabel('Weight (g)')
    ax.set_ylabel('Energy (Wh)')
    ax.set_title('Energy vs Weight')

    # ── Specific Energy bar chart ─────────────────────────────────────────────
    ax = axes[1]
    ax.barh(df_filtered['ID'], df_filtered['Sp. Energy (Wh/kg)'],
            color=colors, edgecolor='black', linewidth=0.5)
    ax.set_xlabel('Specific Energy (Wh/kg)')
    ax.set_title('Specific Energy')

    # ── Max Continuous Current bar chart ─────────────────────────────────────
    ax = axes[2]
    ax.barh(df_filtered['ID'], df_filtered['Max I cont (A)'],
            color=colors, edgecolor='black', linewidth=0.5)
    ax.set_xlabel('Max Cont. Current (A)')
    ax.set_title('Max Continuous Current')

    # Legend
    present_chems = df_filtered['Chemistry'].unique()
    patches = [mpatches.Patch(color=CHEM_COLORS.get(c, '#888'), label=c)
               for c in present_chems]
    fig.legend(handles=patches, loc='lower center', ncol=len(present_chems),
               fontsize=9, title='Chemistry')
    plt.tight_layout(rect=[0, 0.06, 1, 1])
    plt.savefig('battery_selection_comparison.png', bbox_inches='tight')
    plt.show()
else:
    print('No results to plot.')\
""", 'nb08-chart'))

# ── Select and save ───────────────────────────────────────────────────────────
cells.append(md_cell("## 4 · Select Batteries & Save to Configurator", 'nb08-select-hdr'))

cells.append(code_cell("""\
# ── Choose which batteries to carry forward ────────────────────────────────────
# Set to 'ALL' to include every result, or list specific IDs from the table above.

SELECTION = 'ALL'     # e.g. ['BAT_MID_6S2P', 'BAT_MID_6S4P']

# ─────────────────────────────────────────────────────────────────────────────
if df_filtered.empty:
    print('No batteries to select \u2014 adjust filters first.')
else:
    if SELECTION == 'ALL':
        selected_ids = df_filtered['ID'].tolist()
    else:
        unknown = [bid for bid in SELECTION if bid not in df_filtered['ID'].values]
        if unknown:
            raise ValueError(f'IDs not in filtered results: {unknown}\\n'
                             f'Choose from: {df_filtered[\"ID\"].tolist()}')
        selected_ids = list(SELECTION)

    print(f'Selected {len(selected_ids)} pack(s):')
    for bid in selected_ids:
        row = df_filtered[df_filtered['ID'] == bid].iloc[0]
        print(f'  {bid:<30} {row[\"Chemistry\"]:<10} {row[\"Capacity (mAh)\"]:.0f} mAh  '
              f'{row[\"Weight (g)\"]:.0f} g  {row[\"Energy (Wh)\"]:.0f} Wh')\
""", 'nb08-select'))

cells.append(code_cell("""\
def save_selection_to_config(battery_ids, cfg_path='analysis_config.json'):
    \"\"\"
    Merge the selected battery IDs into analysis_config.json.
    Existing keys (UAV, mission, temperature) are preserved.
    \"\"\"
    # Load existing config if present
    cfg = {}
    if os.path.exists(cfg_path):
        with open(cfg_path) as f:
            cfg = json.load(f)

    cfg['selected_batteries'] = battery_ids

    with open(cfg_path, 'w') as f:
        json.dump(cfg, f, indent=2)

    print(f'Saved {len(battery_ids)} batteries to {cfg_path}:')
    for bid in battery_ids:
        print(f'  \u2713 {bid}')
    print()
    print('These will be loaded automatically by Notebooks 03, 05, and 07.')
    return cfg


# ── Run to save ───────────────────────────────────────────────────────────────
CFG_PATH = 'analysis_config.json'
if not os.path.exists(CFG_PATH):
    CFG_PATH = os.path.join('..', 'analysis_config.json')

if df_filtered.empty:
    print('Nothing to save.')
else:
    saved_cfg = save_selection_to_config(selected_ids, CFG_PATH)\
""", 'nb08-save'))

# ── Build notebook ─────────────────────────────────────────────────────────────
nb = {
    'nbformat': 4,
    'nbformat_minor': 5,
    'metadata': {
        'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
        'language_info': {'name': 'python', 'version': '3.10.0'},
    },
    'cells': cells,
}

out_path = 'notebooks/00_battery_selector.ipynb'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print(f'Written: {out_path}  ({len(cells)} cells)')
