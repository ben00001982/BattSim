"""Update 01_configurator: load battery pre-selection from 00_battery_selector output."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/01_configurator.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

new_src = """\
# ── SELECT BATTERIES TO ANALYSE ───────────────────────────────────────────────
# Run 00_battery_selector first to pre-select batteries via filters.
# If a selection was saved there, it is loaded automatically below.
# Override by setting SELECTED_BATTERIES to a list of IDs or 'ALL'.

# Load pre-selection from 00_battery_selector (analysis_config.json)
import json as _j, os as _o
_pre = None
if _o.path.exists(CFG_PATH):
    with open(CFG_PATH) as _f:
        _pre = _j.load(_f).get('selected_batteries')

if _pre:
    print(f'Pre-selection loaded from 00_battery_selector: {len(_pre)} pack(s)')
    SELECTED_BATTERIES = _pre
else:
    SELECTED_BATTERIES = 'ALL'   # <── override: e.g. ['BAT_MID_6S2P', 'BAT_MID_6S4P']

# ─────────────────────────────────────────────────────────────────────────────
if SELECTED_BATTERIES == 'ALL':
    selected_ids = list(db.packs.keys())
else:
    missing = [b for b in SELECTED_BATTERIES if b not in db.packs]
    if missing:
        raise ValueError(f'Unknown battery IDs: {missing}')
    selected_ids = list(SELECTED_BATTERIES)

selected_packs = {bid: db.packs[bid] for bid in selected_ids}
print(f'Batteries selected for analysis ({len(selected_ids)}):')
for bid in selected_ids:
    p = db.packs[bid]
    print(f'  {bid:<30} {p.chemistry_id:<10} {p.pack_energy_wh:.0f} Wh  {p.pack_weight_g:.0f} g')

# Energy vs weight comparison chart
fig, ax = plt.subplots(figsize=(10, 5))
fig.suptitle('Selected Batteries \u2014 Energy vs Weight', fontweight='bold')
chem_colors = {'LIPO':'#FFB347','LION21':'#4488FF','LIFEPO4':'#66BB6A',
               'SSS':'#AB47BC','LITO':'#26C6DA','LION':'#FF7043'}
for bid in selected_ids:
    p = db.packs[bid]
    color = chem_colors.get(p.chemistry_id, '#888')
    ax.scatter(p.pack_weight_g, p.pack_energy_wh, s=120, color=color,
               edgecolors='black', linewidths=0.6, zorder=4)
    ax.annotate(bid, (p.pack_weight_g, p.pack_energy_wh),
                textcoords='offset points', xytext=(6, 4), fontsize=8)
ax.set_xlabel('Pack weight (g)'); ax.set_ylabel('Pack energy (Wh)')
patches = [mpatches.Patch(color=c, label=k) for k, c in chem_colors.items()
           if any(db.packs[b].chemistry_id == k for b in selected_ids)]
ax.legend(handles=patches, fontsize=9)
plt.tight_layout(); plt.show()"""

for i, c in enumerate(nb['cells']):
    if c['id'] == 'cfg-batteries-select':
        nb['cells'][i]['source'] = lines(new_src)
        print(f'Updated cell cfg-batteries-select (index {i})')
        break

# Also update the save message in nb08-save to reference notebook 01 not 03,05,07
for i, c in enumerate(nb['cells']):
    if c['id'] == 'cfg-save':
        src = ''.join(c['source'])
        # Update any old notebook number references in the save output
        src = src.replace("Notebooks 03, 05, and 07", "Notebooks 02, 04, and 06")
        nb['cells'][i]['source'] = lines(src)
        print(f'Updated cell cfg-save notebook references')
        break

with open('notebooks/01_configurator.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
