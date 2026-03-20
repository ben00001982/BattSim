"""Fix the PDF cell in 06_reports.ipynb — page 2 SoC/V and page 4 temp charts."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')


def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])


with open('notebooks/06_reports.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

for i, c in enumerate(nb['cells']):
    if c['id'] != 'gy83obmtfr5':
        continue

    src = ''.join(c['source'])

    # ── Page 2: replace single-pack SoC/Voltage with multi-pack ─────────────
    old_soc = (
        "    ax_sv = fig.add_subplot(gs[1, 1])\n"
        "    t_arr = np.array(primary_result.time_s)\n"
        "    ax_sv.plot(t_arr, primary_result.soc_pct, ACCENT, linewidth=2, label='SoC (%)')\n"
        "    ax2 = ax_sv.twinx()\n"
        "    ax2.plot(t_arr, primary_result.voltage_v, '#E53935', linewidth=1.5,\n"
        "             linestyle='--', alpha=0.8, label='Voltage (V)')\n"
        "    ax_sv.set_xlabel('Time (s)'); ax_sv.set_ylabel('SoC (%)', color=ACCENT)\n"
        "    ax2.set_ylabel('Voltage (V)', color='#E53935')\n"
        "    ax_sv.set_title(f'{PRIMARY_PACK_ID} \u2014 SoC & Voltage')\n"
        "    ax_sv.set_ylim(0, 110)"
    )

    new_soc = (
        "    ax_sv = fig.add_subplot(gs[1, 1])\n"
        "    import matplotlib.cm as _cm2\n"
        "    _cmap2 = _cm2.get_cmap('tab10', max(len(compare_results), 1))\n"
        "    ax2_v = ax_sv.twinx()\n"
        "    for _ri2, (_r2, _p2) in enumerate(zip(compare_results, compare_packs)):\n"
        "        _col2 = _cmap2(_ri2)\n"
        "        _t2 = np.array(_r2.time_s)\n"
        "        _lbl2 = _p2.battery_id[:22]\n"
        "        ax_sv.plot(_t2, _r2.soc_pct, color=_col2, linewidth=1.5, label=_lbl2)\n"
        "        ax2_v.plot(_t2, _r2.voltage_v, color=_col2, linewidth=1.0,\n"
        "                   linestyle='--', alpha=0.7)\n"
        "    ax_sv.set_xlabel('Time (s)'); ax_sv.set_ylabel('SoC (%)')\n"
        "    ax2_v.set_ylabel('Voltage (V)')\n"
        "    ax_sv.set_title(f'SoC & Voltage \u2014 {len(compare_results)} packs')\n"
        "    ax_sv.set_ylim(0, 110)\n"
        "    if len(compare_results) <= 8:\n"
        "        ax_sv.legend(fontsize=7, loc='lower left')"
    )

    if old_soc in src:
        src = src.replace(old_soc, new_soc)
        print('Updated PDF page 2 SoC/Voltage chart')
    else:
        print('WARNING: page 2 SoC/V block not found')

    # ── Page 4: replace single-pack temp sweep with multi-pack overlay ────────
    old_temp = (
        "    t_vals = df_sweep['Ambient (C)'].values\n"
        "    depleted_mask = df_sweep['Depleted'].values\n"
        "    dot_colors = ['#E53935' if d else ACCENT for d in depleted_mask]\n"
        "\n"
        "    metrics = [\n"
        "        ('Final SoC (%)',  'Final SoC (%)', '#2196F3'),\n"
        "        ('Peak sag (V)',   'Peak sag (V)',  '#FF9800'),\n"
        "        ('Min V (V)',      'Min V (V)',     '#E53935'),\n"
        "    ]\n"
        "    temp_rise = df_sweep['Max T (\u00b0C)'].values - df_sweep['Ambient (C)'].values\n"
        "\n"
        "    for i, (col, ylabel, color) in enumerate(metrics):\n"
        "        ax = fig.add_subplot(gs4[i // 2, i % 2])\n"
        "        y  = df_sweep[col].values\n"
        "        ax.plot(t_vals, y, color=color, linewidth=2)\n"
        "        ax.scatter(t_vals, y, c=dot_colors, s=40, zorder=4)\n"
        "        ax.set_xlabel('Ambient (\u00b0C)'); ax.set_ylabel(ylabel)\n"
        "        ax.set_title(ylabel)\n"
        "\n"
        "    ax4 = fig.add_subplot(gs4[1, 1])\n"
        "    ax4.plot(t_vals, temp_rise, '#9C27B0', linewidth=2)\n"
        "    ax4.scatter(t_vals, temp_rise, c=dot_colors, s=40, zorder=4)\n"
        "    ax4.set_xlabel('Ambient (\u00b0C)'); ax4.set_ylabel('Self-heating (\u00b0C)')\n"
        "    ax4.set_title('Cell Self-Heating')\n"
        "\n"
        "    legend_els = [mpatches.Patch(color=ACCENT, label='Completed'),\n"
        "                  mpatches.Patch(color='#E53935', label='Depleted')]\n"
        "    fig.legend(handles=legend_els, loc='lower center', ncol=2, fontsize=9,\n"
        "               bbox_to_anchor=(0.5, 0.01))"
    )

    new_temp = (
        "    import matplotlib.cm as _cm4\n"
        "    _cmap4 = _cm4.get_cmap('tab10', max(len(compare_packs), 1))\n"
        "\n"
        "    _axes4 = [fig.add_subplot(gs4[_r4, _c4])\n"
        "              for _r4, _c4 in [(0,0),(0,1),(1,0),(1,1)]]\n"
        "    _metrics4 = [\n"
        "        ('Final SoC (%)',  'Final SoC (%)'),\n"
        "        ('Peak sag (V)',   'Peak sag (V)'),\n"
        "        ('Min V (V)',      'Min V (V)'),\n"
        "        ('_self_heat',     'Self-heating (\u00b0C)'),\n"
        "    ]\n"
        "\n"
        "    for _pidx4, (_pid4, _df4) in enumerate(all_df_sweep.items()):\n"
        "        _col4 = _cmap4(_pidx4)\n"
        "        _lbl4 = _pid4[:22]\n"
        "        _t4   = _df4['Ambient (C)'].values\n"
        "        _dep4 = _df4['Depleted'].values\n"
        "        for _ax4, (_field4, _ylabel4) in zip(_axes4, _metrics4):\n"
        "            _y4 = (_df4['Max T (\u00b0C)'].values - _t4\n"
        "                   if _field4 == '_self_heat' else _df4[_field4].values)\n"
        "            _ax4.plot(_t4, _y4, color=_col4, linewidth=1.8, label=_lbl4)\n"
        "            _ax4.scatter(_t4, _y4,\n"
        "                         c=['#E53935' if d else _col4 for d in _dep4],\n"
        "                         s=30, zorder=4)\n"
        "\n"
        "    for _ax4, (_, _ylabel4) in zip(_axes4, _metrics4):\n"
        "        _ax4.set_xlabel('Ambient (\u00b0C)'); _ax4.set_ylabel(_ylabel4)\n"
        "        _ax4.set_title(_ylabel4)\n"
        "\n"
        "    if len(compare_packs) <= 6:\n"
        "        _axes4[0].legend(fontsize=7, loc='best')\n"
        "    else:\n"
        "        _handles4 = [mpatches.Patch(color=_cmap4(_ii4), label=_pp4.battery_id[:22])\n"
        "                     for _ii4, _pp4 in enumerate(compare_packs)]\n"
        "        fig.legend(handles=_handles4, loc='lower center',\n"
        "                   ncol=min(len(compare_packs), 4), fontsize=7,\n"
        "                   bbox_to_anchor=(0.5, 0.0))\n"
        "    _dep4_leg = [mpatches.Patch(color=ACCENT, label='Completed'),\n"
        "                 mpatches.Patch(color='#E53935', label='Depleted')]\n"
        "    fig.legend(handles=_dep4_leg, loc='lower right', ncol=2, fontsize=8)"
    )

    if old_temp in src:
        src = src.replace(old_temp, new_temp)
        print('Updated PDF page 4 temperature sensitivity')
    else:
        print('WARNING: page 4 temp block not found')
        # Show surrounding context for debugging
        idx = src.find("t_vals = df_sweep['Ambient (C)'].values")
        if idx >= 0:
            print('  Found at char', idx)
            print(repr(src[idx:idx+200]))

    nb['cells'][i]['source'] = lines(src)
    print(f'Saved PDF cell gy83obmtfr5 (index {i})')
    break

with open('notebooks/06_reports.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
