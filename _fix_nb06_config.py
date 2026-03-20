"""
Fix notebook 06_reports.ipynb to loop over all batteries from analysis_config.json:
1. Cell d5f2fa08 (Sec 2 simulations): loop all selected packs → all_results dict
2. Cell 087b4889 (Sec 2 temp sweep): loop all selected packs → all_sweep_results / all_df_sweep
3. Cell gy83obmtfr5 (PDF report):
   - Page 2 SoC/Voltage: overlay all selected packs
   - Page 4 temperature sensitivity: overlay all packs on same charts
"""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')


def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])


with open('notebooks/06_reports.ipynb', encoding='utf-8') as f:
    nb = json.load(f)


# ── Cell d5f2fa08 — Simulations ───────────────────────────────────────────────
sim_src = """\
print('Running simulations...')

# Run simulation for ALL selected packs
all_results = {}
for _pid in COMPARE_PACK_IDS:
    if _pid not in db.packs:
        print(f'  [SKIP] {_pid} — not in database')
        continue
    _r = run_simulation(
        pack=db.packs[_pid], mission=mission, uav=uav,
        discharge_pts=db.discharge_pts,
        ambient_temp_c=AMBIENT_TEMP_C, dt_s=1.0
    )
    all_results[_pid] = _r
    print(_r.summary())

# Aliases kept for downstream compatibility
primary_result  = all_results.get(PRIMARY_PACK_ID, next(iter(all_results.values())))
compare_results = list(all_results.values())
compare_packs   = [db.packs[pid] for pid in COMPARE_PACK_IDS if pid in all_results]

print(f'\\nMulti-pack results ({len(compare_results)} packs):')
for r in compare_results:
    print(f'  {r.pack_id}: SoC={r.final_soc:.1f}%  Vmin={r.min_voltage:.3f}V  '
          f'depleted={r.depleted}')\
"""

for i, c in enumerate(nb['cells']):
    if c['id'] == 'd5f2fa08':
        nb['cells'][i]['source'] = lines(sim_src)
        print(f'Updated simulation cell d5f2fa08 (index {i})')
        break


# ── Cell 087b4889 — Temperature sweep ────────────────────────────────────────
sweep_src = """\
# Temperature sweep for ALL selected packs
print(f'Running temperature sweeps ({len(TEMP_SWEEP)} temps x {len(compare_packs)} packs)...')

all_sweep_results = {}   # {pack_id: [SimResult, ...]}
all_df_sweep      = {}   # {pack_id: DataFrame}

for _pid in COMPARE_PACK_IDS:
    if _pid not in all_results:
        continue
    _sw = temperature_sweep(
        pack=db.packs[_pid], mission=mission, uav=uav,
        discharge_pts=db.discharge_pts,
        temperatures_c=TEMP_SWEEP, dt_s=5.0
    )
    all_sweep_results[_pid] = _sw
    all_df_sweep[_pid] = pd.DataFrame([{
        'Ambient (C)':   t,
        'Final SoC (%)': round(r.final_soc, 1),
        'Peak sag (V)':  round(r.peak_sag_v, 3),
        'Min V (V)':     round(r.min_voltage, 3),
        'Max T (\\u00b0C)':  round(r.max_temp_c, 1),
        'Depleted':      r.depleted}
        for t, r in zip(TEMP_SWEEP, _sw)])
    print(f'\\n  {_pid}:')
    print(all_df_sweep[_pid].to_string(index=False))

# Primary aliases for backward compatibility
sweep_results = all_sweep_results.get(PRIMARY_PACK_ID,
                    next(iter(all_sweep_results.values())))
df_sweep      = all_df_sweep.get(PRIMARY_PACK_ID,
                    next(iter(all_df_sweep.values())))
print('\\nDone.')\
"""

for i, c in enumerate(nb['cells']):
    if c['id'] == '087b4889':
        nb['cells'][i]['source'] = lines(sweep_src)
        print(f'Updated temp-sweep cell 087b4889 (index {i})')
        break


# ── Cell gy83obmtfr5 — PDF report ─────────────────────────────────────────────
# Read the current source, apply targeted substitutions to:
#   a) Page 2 SoC/Voltage chart: overlay all packs instead of primary only
#   b) Page 4 temperature sensitivity: overlay all packs per metric

for i, c in enumerate(nb['cells']):
    if c['id'] != 'gy83obmtfr5':
        continue

    src = ''.join(c['source'])

    # ── a) Page 2 SoC/Voltage: replace single-pack plot with multi-pack ──────
    old_soc_v = """\
    ax_sv = fig.add_subplot(gs[1, 1])
    t_arr = np.array(primary_result.time_s)
    ax_sv.plot(t_arr, primary_result.soc_pct, ACCENT, linewidth=2, label='SoC (%)')
    ax2 = ax_sv.twinx()
    ax2.plot(t_arr, primary_result.voltage_v, '#E53935', linewidth=1.5,
             linestyle='--', alpha=0.8, label='Voltage (V)')
    ax_sv.set_xlabel('Time (s)'); ax_sv.set_ylabel('SoC (%)', color=ACCENT)
    ax2.set_ylabel('Voltage (V)', color='#E53935')
    ax_sv.set_title(f'{PRIMARY_PACK_ID} \\u2014 SoC & Voltage')
    ax_sv.set_ylim(0, 110)"""

    new_soc_v = """\
    ax_sv = fig.add_subplot(gs[1, 1])
    import matplotlib.cm as _cm2
    _cmap2 = _cm2.get_cmap('tab10', max(len(compare_results), 1))
    ax2_v = ax_sv.twinx()
    for _ri, (_r2, _p2) in enumerate(zip(compare_results, compare_packs)):
        _col2 = _cmap2(_ri)
        _t2 = np.array(_r2.time_s)
        _lbl2 = _p2.battery_id[:24]
        ax_sv.plot(_t2, _r2.soc_pct, color=_col2, linewidth=1.5, label=_lbl2)
        ax2_v.plot(_t2, _r2.voltage_v, color=_col2, linewidth=1.0, linestyle='--', alpha=0.7)
    ax_sv.set_xlabel('Time (s)'); ax_sv.set_ylabel('SoC (%)')
    ax2_v.set_ylabel('Voltage (V)')
    ax_sv.set_title(f'SoC & Voltage \\u2014 {len(compare_results)} packs')
    ax_sv.set_ylim(0, 110)
    if len(compare_results) <= 8:
        ax_sv.legend(fontsize=7, loc='lower left')"""

    if old_soc_v in src:
        src = src.replace(old_soc_v, new_soc_v)
        print(f'  Updated PDF page 2 SoC/Voltage chart')
    else:
        print(f'  WARNING: could not find page 2 SoC/Voltage block')

    # ── b) Page 4 temperature sensitivity: replace single-pack plots ─────────
    old_temp = """\
    t_vals = df_sweep['Ambient (C)'].values
    depleted_mask = df_sweep['Depleted'].values
    dot_colors = ['#E53935' if d else ACCENT for d in depleted_mask]

    metrics = [
        ('Final SoC (%)',  'Final SoC (%)', '#2196F3'),
        ('Peak sag (V)',   'Peak sag (V)',  '#FF9800'),
        ('Min V (V)',      'Min V (V)',     '#E53935'),
    ]
    temp_rise = df_sweep['Max T (\\u00b0C)'].values - df_sweep['Ambient (C)'].values

    for i, (col, ylabel, color) in enumerate(metrics):
        ax = fig.add_subplot(gs4[i // 2, i % 2])
        y  = df_sweep[col].values
        ax.plot(t_vals, y, color=color, linewidth=2)
        ax.scatter(t_vals, y, c=dot_colors, s=40, zorder=4)
        ax.set_xlabel('Ambient (\\u00b0C)'); ax.set_ylabel(ylabel)
        ax.set_title(ylabel)

    ax4 = fig.add_subplot(gs4[1, 1])
    ax4.plot(t_vals, temp_rise, '#9C27B0', linewidth=2)
    ax4.scatter(t_vals, temp_rise, c=dot_colors, s=40, zorder=4)
    ax4.set_xlabel('Ambient (\\u00b0C)'); ax4.set_ylabel('Self-heating (\\u00b0C)')
    ax4.set_title('Cell Self-Heating')

    legend_els = [mpatches.Patch(color=ACCENT, label='Completed'),
                  mpatches.Patch(color='#E53935', label='Depleted')]
    fig.legend(handles=legend_els, loc='lower center', ncol=2, fontsize=9,
               bbox_to_anchor=(0.5, 0.01))"""

    new_temp = """\
    import matplotlib.cm as _cm4
    _cmap4 = _cm4.get_cmap('tab10', max(len(compare_packs), 1))

    _axes4 = [fig.add_subplot(gs4[r, c]) for r in range(2) for c in range(2)]
    _metrics4 = [
        ('Final SoC (%)',  'Final SoC (%)'),
        ('Peak sag (V)',   'Peak sag (V)'),
        ('Min V (V)',      'Min V (V)'),
        ('_self_heat',     'Self-heating (\\u00b0C)'),
    ]

    for _pidx, (_pid4, _df4) in enumerate(all_df_sweep.items()):
        _col4 = _cmap4(_pidx)
        _lbl4 = _pid4[:24]
        _t4   = _df4['Ambient (C)'].values
        _dep4 = _df4['Depleted'].values
        for _ax4, (_field4, _ylabel4) in zip(_axes4, _metrics4):
            if _field4 == '_self_heat':
                _y4 = _df4['Max T (\\u00b0C)'].values - _t4
            else:
                _y4 = _df4[_field4].values
            _ax4.plot(_t4, _y4, color=_col4, linewidth=1.8, label=_lbl4)
            _dots4 = ['#E53935' if d else _col4 for d in _dep4]
            _ax4.scatter(_t4, _y4, c=_dots4, s=30, zorder=4)

    for _ax4, (_, _ylabel4) in zip(_axes4, _metrics4):
        _ax4.set_xlabel('Ambient (\\u00b0C)'); _ax4.set_ylabel(_ylabel4)
        _ax4.set_title(_ylabel4)

    if len(compare_packs) <= 8:
        _axes4[0].legend(fontsize=7, loc='best')
    else:
        _handles4 = [mpatches.Patch(color=_cmap4(_i), label=_p.battery_id[:24])
                     for _i, _p in enumerate(compare_packs)]
        fig.legend(handles=_handles4, loc='lower center',
                   ncol=min(len(compare_packs), 4), fontsize=7,
                   bbox_to_anchor=(0.5, 0.0))

    _dep_legend = [mpatches.Patch(color=ACCENT, label='Completed'),
                   mpatches.Patch(color='#E53935', label='Depleted')]
    fig.legend(handles=_dep_legend, loc='lower right', ncol=2, fontsize=8)"""

    if old_temp in src:
        src = src.replace(old_temp, new_temp)
        print(f'  Updated PDF page 4 temperature sensitivity')
    else:
        print(f'  WARNING: could not find page 4 temp sensitivity block')

    nb['cells'][i]['source'] = lines(src)
    print(f'Updated PDF cell gy83obmtfr5 (index {i})')
    break


with open('notebooks/06_reports.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
