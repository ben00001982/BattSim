"""Fix cfg-batteries-select scatter chart in notebooks/02_configurator.ipynb."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/02_configurator.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

# Replace only the chart portion — keep the battery selection logic above it intact
old_chart = """\
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

new_chart = """\
# Energy vs weight comparison chart
MAX_LABEL = 24
chem_colors = {'LIPO':'#FFB347','LION21':'#4488FF','LIFEPO4':'#66BB6A',
               'SSS':'#AB47BC','LITO':'#26C6DA','LION':'#FF7043'}
n_sel = len(selected_ids)
fig_w = max(9, min(14, 7 + n_sel * 0.05))
fig, ax = plt.subplots(figsize=(fig_w, 6))
fig.suptitle(f'Selected Batteries \u2014 Energy vs Weight ({n_sel} packs)',
             fontweight='bold')

for idx, bid in enumerate(selected_ids):
    p = db.packs[bid]
    color = chem_colors.get(p.chemistry_id, '#888')
    ax.scatter(p.pack_weight_g, p.pack_energy_wh, s=100, color=color,
               edgecolors='black', linewidths=0.5, zorder=4)
    if n_sel <= 20:
        lbl = bid[:MAX_LABEL]
        ax.annotate(lbl, (p.pack_weight_g, p.pack_energy_wh),
                    textcoords='offset points', xytext=(5, 3), fontsize=7,
                    clip_on=True)
    else:
        ax.annotate(str(idx + 1), (p.pack_weight_g, p.pack_energy_wh),
                    textcoords='offset points', xytext=(3, 2), fontsize=6,
                    clip_on=True)

ax.set_xlabel('Pack weight (g)')
ax.set_ylabel('Pack energy (Wh)')
patches = [mpatches.Patch(color=c, label=k) for k, c in chem_colors.items()
           if any(db.packs[b].chemistry_id == k for b in selected_ids)]
ax.legend(handles=patches, fontsize=9, loc='upper left', framealpha=0.8)
if n_sel > 20:
    ax.set_title(f'Labels are row numbers (1\u2013{n_sel}); see table above for IDs.',
                 fontsize=8)
plt.tight_layout()
plt.show()"""

for i, c in enumerate(nb['cells']):
    if c['id'] == 'cfg-batteries-select':
        src = ''.join(c['source'])
        if old_chart in src:
            new_src = src.replace(old_chart, new_chart)
            nb['cells'][i]['source'] = lines(new_src)
            print(f'Updated cfg-batteries-select chart (index {i})')
        else:
            print('WARNING: could not find old chart block — showing current source tail:')
            print(src[-300:])
        break

with open('notebooks/02_configurator.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
