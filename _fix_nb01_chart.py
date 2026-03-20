"""Rewrite nb08-chart cell in notebooks/01_battery_selector.ipynb."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/01_battery_selector.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

src = """\
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

if df_filtered.empty:
    print('No results to plot.')
else:
    n = len(df_filtered)

    # ── Shorten IDs for axis labels ───────────────────────────────────────────
    MAX_LABEL = 28
    df_plot = df_filtered.copy()
    df_plot['_label'] = df_plot['ID'].str[:MAX_LABEL]
    # De-duplicate truncated labels by appending a counter where needed
    seen = {}
    labels = []
    for lbl in df_plot['_label']:
        if lbl in seen:
            seen[lbl] += 1
            labels.append(f'{lbl[:MAX_LABEL-2]}~{seen[lbl]}')
        else:
            seen[lbl] = 0
            labels.append(lbl)
    df_plot['_label'] = labels

    colors = [CHEM_COLORS.get(c, '#888') for c in df_plot['Chemistry']]

    # ── Figure 1: scatter  Energy vs Weight ──────────────────────────────────
    fig1, ax1 = plt.subplots(figsize=(9, 6))
    fig1.suptitle('Energy vs Weight', fontsize=12, fontweight='bold')

    ax1.scatter(df_plot['Weight (g)'], df_plot['Energy (Wh)'],
                c=colors, s=80, edgecolors='black', linewidths=0.5, zorder=4)

    # Only annotate when the number of points is manageable
    if n <= 25:
        for _, row in df_plot.iterrows():
            ax1.annotate(row['_label'],
                         (row['Weight (g)'], row['Energy (Wh)']),
                         textcoords='offset points', xytext=(5, 3), fontsize=6.5,
                         clip_on=True)
    else:
        # Annotate with short index numbers instead
        for idx, (_, row) in enumerate(df_plot.iterrows()):
            ax1.annotate(str(idx + 1),
                         (row['Weight (g)'], row['Energy (Wh)']),
                         textcoords='offset points', xytext=(3, 2), fontsize=6,
                         clip_on=True)
        ax1.set_title(f'Energy vs Weight  (numbers = row index in table above)',
                      fontsize=9)

    ax1.set_xlabel('Weight (g)')
    ax1.set_ylabel('Energy (Wh)')

    present_chems = df_plot['Chemistry'].unique()
    patches = [mpatches.Patch(color=CHEM_COLORS.get(c, '#888'), label=c)
               for c in present_chems]
    ax1.legend(handles=patches, fontsize=8, title='Chemistry',
               loc='upper left', framealpha=0.8)
    plt.tight_layout()
    plt.savefig('battery_selection_scatter.png', bbox_inches='tight', dpi=120)
    plt.show()

    # ── Figure 2: horizontal bar charts ──────────────────────────────────────
    BAR_H   = max(0.28, min(0.5, 12.0 / n))   # row height in inches, clamped
    fig_h   = max(4.0, n * BAR_H + 1.5)
    tick_fs = max(5, min(9, int(180 / n)))     # tick font size

    fig2, (axA, axB) = plt.subplots(1, 2, figsize=(14, fig_h))
    fig2.suptitle('Specific Energy & Max Continuous Current', fontsize=12,
                  fontweight='bold')

    y_pos = range(n)

    axA.barh(y_pos, df_plot['Sp. Energy (Wh/kg)'],
             color=colors, edgecolor='black', linewidth=0.4)
    axA.set_yticks(y_pos)
    axA.set_yticklabels(df_plot['_label'], fontsize=tick_fs)
    axA.set_xlabel('Specific Energy (Wh/kg)', fontsize=9)
    axA.set_title('Specific Energy', fontsize=10)
    axA.invert_yaxis()   # top-to-bottom matches table order

    axB.barh(y_pos, df_plot['Max I cont (A)'],
             color=colors, edgecolor='black', linewidth=0.4)
    axB.set_yticks(y_pos)
    axB.set_yticklabels(df_plot['_label'], fontsize=tick_fs)
    axB.set_xlabel('Max Cont. Current (A)', fontsize=9)
    axB.set_title('Max Continuous Current', fontsize=10)
    axB.invert_yaxis()

    patches2 = [mpatches.Patch(color=CHEM_COLORS.get(c, '#888'), label=c)
                for c in present_chems]
    fig2.legend(handles=patches2, loc='lower center',
                ncol=min(len(present_chems), 6), fontsize=8,
                title='Chemistry', bbox_to_anchor=(0.5, 0.0))
    plt.tight_layout(rect=[0, 0.04, 1, 1])
    plt.savefig('battery_selection_bars.png', bbox_inches='tight', dpi=120)
    plt.show()

    if n > 25:
        print(f'\\n{n} batteries plotted. Scatter labels are row numbers (1-{n}).')
        print('See the table above for the full ID list.')"""

for i, c in enumerate(nb['cells']):
    if c['id'] == 'nb08-chart':
        nb['cells'][i]['source'] = lines(src)
        print(f'Updated cell nb08-chart (index {i})')
        break

with open('notebooks/01_battery_selector.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
