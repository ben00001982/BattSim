"""Fix notebook 06 cell gy83obmtfr5: remove PHASE_COLORS injections, fix df_sweep column names."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/06_reports.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

src = '''\
import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

# ── Configuration ──────────────────────────────────────────────────────────────
PDF_OUT_PATH  = 'UAV_Battery_Report.pdf'
COMPANY_NAME  = 'Pen Aviation Sdn Bhd'

PHASE_COLORS = {
    'IDLE':            '#AAAAAA',
    'TAKEOFF':         '#FF9944',
    'CLIMB':           '#FFCC44',
    'CRUISE':          '#44AA66',
    'HOVER':           '#4488FF',
    'DESCEND':         '#88AADD',
    'LAND':            '#CC88DD',
    'PAYLOAD_OPS':     '#FF6688',
    'EMERGENCY':       '#FF2222',
    'VTOL_TRANSITION': '#FF6611',
    'VTOL_HOVER':      '#22AAFF',
    'FW_CRUISE':       '#00CC77',
    'FW_CLIMB':        '#AACC44',
    'FW_DESCEND':      '#99CCEE',
}
CHEM_COLORS  = {'LIPO':'#FFB347','LION21':'#4488FF','LIFEPO4':'#66BB6A',
                 'SSS':'#AB47BC','LITO':'#26C6DA','LION':'#FF7043','LIHV':'#FF6E40'}

DARK  = '#1A237E'
ACCENT= '#2196F3'
LIGHT = '#F5F7FA'
TEXT  = '#212121'

plt.rcParams.update({'font.family': 'DejaVu Sans', 'axes.grid': True,
                     'grid.alpha': 0.2, 'axes.spines.top': False,
                     'axes.spines.right': False, 'figure.facecolor': 'white'})

def _header(fig, title, subtitle='', page_num=None):
    ax_h = fig.add_axes([0, 0.93, 1, 0.07])
    ax_h.set_facecolor(DARK); ax_h.set_xlim(0,1); ax_h.set_ylim(0,1)
    ax_h.axis('off')
    ax_h.text(0.02, 0.55, title, color='white', fontsize=14, fontweight='bold', va='center')
    if subtitle:
        ax_h.text(0.02, 0.15, subtitle, color='#90CAF9', fontsize=9, va='center')
    if page_num:
        ax_h.text(0.98, 0.5, str(page_num), color='#90CAF9', fontsize=9,
                  ha='right', va='center')
    ax_h.axhline(0, color=ACCENT, linewidth=3)

def _footer(fig, left='', right=''):
    ax_f = fig.add_axes([0, 0, 1, 0.035])
    ax_f.set_facecolor('#ECEFF1'); ax_f.set_xlim(0,1); ax_f.set_ylim(0,1)
    ax_f.axis('off')
    ax_f.text(0.02, 0.5, left,  color='#607D8B', fontsize=7, va='center')
    ax_f.text(0.98, 0.5, right, color='#607D8B', fontsize=7, va='center', ha='right')

def _pill(ax, x, y, text, color, width=0.18, height=0.08):
    from matplotlib.patches import FancyBboxPatch
    box = FancyBboxPatch((x-width/2, y-height/2), width, height,
                          boxstyle='round,pad=0.01', facecolor=color,
                          edgecolor='none', transform=ax.transAxes, clip_on=False,
                          zorder=5)
    ax.add_patch(box)
    ax.text(x, y, text, transform=ax.transAxes, ha='center', va='center',
            color='white', fontsize=8, fontweight='bold', zorder=6)

now_str  = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
run_info = (f'Mission: {MISSION_ID}  |  UAV: {UAV_ID}  |  '
            f'Temp: {AMBIENT_TEMP_C}\u00b0C  |  Generated: {now_str}')

with PdfPages(PDF_OUT_PATH) as pdf:

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 1 — COVER
    # ══════════════════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(11.69, 8.27))
    fig.patch.set_facecolor(DARK)

    fig.text(0.5, 0.72, 'UAV Battery Analysis', color='white',
             fontsize=38, fontweight='bold', ha='center', va='center')
    fig.text(0.5, 0.62, 'Performance, Simulation & Scorecard Report',
             color='#90CAF9', fontsize=18, ha='center', va='center')

    ax_bar = fig.add_axes([0.15, 0.56, 0.70, 0.004])
    ax_bar.set_facecolor(ACCENT); ax_bar.axis('off')

    meta = (f'{COMPANY_NAME}\\n\\n'
            f'Mission          {MISSION_ID}\\n'
            f'UAV config       {UAV_ID}\\n'
            f'Primary pack     {PRIMARY_PACK_ID}\\n'
            f'Temperature      {AMBIENT_TEMP_C}\u00b0C\\n'
            f'Generated        {now_str}')
    fig.text(0.5, 0.35, meta, color='#CFD8DC', fontsize=12,
             ha='center', va='center', linespacing=1.8,
             fontfamily='monospace')

    ax_pill = fig.add_axes([0.35, 0.08, 0.30, 0.10])
    ax_pill.set_facecolor(ACCENT); ax_pill.axis('off')
    ax_pill.text(0.5, 0.6, f'{len(compare_packs)} batteries analysed',
                 color='white', fontsize=14, fontweight='bold',
                 ha='center', va='center', transform=ax_pill.transAxes)
    ax_pill.text(0.5, 0.2, f'across {len(TEMP_SWEEP)} temperature points',
                 color='#E3F2FD', fontsize=10,
                 ha='center', va='center', transform=ax_pill.transAxes)

    pdf.savefig(fig, bbox_inches='tight'); plt.close(fig)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 2 — MISSION PROFILE + EQUIPMENT SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(11.69, 8.27))
    _header(fig, 'Mission Profile', run_info, 'p.2')
    _footer(fig, COMPANY_NAME, PDF_OUT_PATH)

    gs = gridspec.GridSpec(2, 2, figure=fig, left=0.06, right=0.97,
                           top=0.89, bottom=0.08, hspace=0.45, wspace=0.35)

    ax_gantt = fig.add_subplot(gs[0, :])
    x_pos = 0
    for ph in mission.phases:
        color = PHASE_COLORS.get(ph.phase_type, '#CCC')
        ax_gantt.barh(0, ph.duration_s, left=x_pos, height=0.5,
                      color=color, edgecolor='white', linewidth=0.5)
        if ph.duration_s > 30:
            ax_gantt.text(x_pos + ph.duration_s/2, 0,
                          ph.phase_type + '\\n' + str(int(ph.duration_s)) + 's',
                          ha='center', va='center', fontsize=8,
                          fontweight='bold', color='white')
        x_pos += ph.duration_s
    ax_gantt.set_xlim(0, x_pos); ax_gantt.set_yticks([])
    ax_gantt.set_xlabel('Time (s)'); ax_gantt.set_title('Mission Phase Timeline')

    ax_pie = fig.add_subplot(gs[1, 0])
    durations = [ph.duration_s for ph in mission.phases]
    labels    = [ph.phase_type for ph in mission.phases]
    colors_p  = [PHASE_COLORS.get(l, '#888') for l in labels]
    ax_pie.pie(durations, labels=labels, colors=colors_p, autopct='%1.0f%%',
               startangle=90, textprops={'fontsize': 8})
    ax_pie.set_title('Phase breakdown')

    ax_sv = fig.add_subplot(gs[1, 1])
    t_arr = np.array(primary_result.time_s)
    ax_sv.plot(t_arr, primary_result.soc_pct, ACCENT, linewidth=2, label='SoC (%)')
    ax2 = ax_sv.twinx()
    ax2.plot(t_arr, primary_result.voltage_v, '#E53935', linewidth=1.5,
             linestyle='--', alpha=0.8, label='Voltage (V)')
    ax_sv.set_xlabel('Time (s)'); ax_sv.set_ylabel('SoC (%)', color=ACCENT)
    ax2.set_ylabel('Voltage (V)', color='#E53935')
    ax_sv.set_title(f'{PRIMARY_PACK_ID} \u2014 SoC & Voltage')
    ax_sv.set_ylim(0, 110)

    pdf.savefig(fig, bbox_inches='tight'); plt.close(fig)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 3 — BATTERY SCORECARD
    # ══════════════════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(11.69, 8.27))
    _header(fig, 'Battery Scorecard', run_info, 'p.3')
    _footer(fig, COMPANY_NAME, PDF_OUT_PATH)

    ax_sc = fig.add_axes([0.04, 0.08, 0.92, 0.80])
    ax_sc.axis('off')

    col_labels = ['Battery', 'Chemistry', 'Energy\\n(Wh)', 'Weight\\n(g)',
                  'Wh/kg', 'Final SoC\\n(%)', 'Min V\\n(V)',
                  'Peak sag\\n(V)', 'Max I\\n(A)', 'Status']
    col_widths = [0.18, 0.09, 0.07, 0.07, 0.06, 0.09, 0.07, 0.08, 0.07, 0.09]

    y = 0.95; row_h = 0.075
    x = 0.0
    for lbl, w in zip(col_labels, col_widths):
        ax_sc.text(x + w/2, y, lbl, ha='center', va='center', fontsize=8,
                   fontweight='bold', color='white',
                   bbox=dict(boxstyle='square,pad=0.3', facecolor=DARK, edgecolor='none'))
        x += w

    for idx, (r, p) in enumerate(zip(compare_results, compare_packs)):
        y -= row_h
        bg = '#FAFAFA' if idx % 2 == 0 else 'white'
        status = 'PASS' if not r.depleted and r.final_soc > 15 else \\
                 ('MARGINAL' if not r.depleted else 'FAIL')
        status_color = {'PASS': '#2E7D32', 'MARGINAL': '#F57F17', 'FAIL': '#C62828'}[status]
        vals = [p.battery_id, p.chemistry_id, f'{p.pack_energy_wh:.0f}',
                f'{p.pack_weight_g:.0f}',
                f'{getattr(p, "specific_energy_wh_kg", p.pack_energy_wh/p.pack_weight_g*1000):.0f}',
                f'{r.final_soc:.1f}', f'{r.min_voltage:.3f}',
                f'{r.peak_sag_v:.3f}', f'{r.max_current:.1f}', status]
        x = 0.0
        for v, w in zip(vals, col_widths):
            color = status_color if v == status else TEXT
            fw    = 'bold' if v == status else 'normal'
            ax_sc.text(x + w/2, y + row_h/2, v, ha='center', va='center',
                       fontsize=8, color=color, fontweight=fw,
                       bbox=dict(boxstyle='square,pad=0.3',
                                 facecolor=bg, edgecolor='#E0E0E0', linewidth=0.4))
            x += w

    legend_patches = [mpatches.Patch(facecolor=color, label=label, alpha=0.85)
                      for label, color in [('PASS','#2E7D32'),('MARGINAL','#F57F17'),('FAIL','#C62828')]]
    ax_sc.legend(handles=legend_patches, loc='lower right', fontsize=8, title='Status', framealpha=0.9)

    pdf.savefig(fig, bbox_inches='tight'); plt.close(fig)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 4 — TEMPERATURE SENSITIVITY
    # ══════════════════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(11.69, 8.27))
    _header(fig, 'Temperature Sensitivity', run_info, 'p.4')
    _footer(fig, COMPANY_NAME, PDF_OUT_PATH)

    gs4 = gridspec.GridSpec(2, 2, figure=fig, left=0.08, right=0.96,
                            top=0.89, bottom=0.08, hspace=0.45, wspace=0.35)

    t_vals = df_sweep['Ambient (C)'].values
    depleted_mask = df_sweep['Depleted'].values
    dot_colors = ['#E53935' if d else ACCENT for d in depleted_mask]

    metrics = [
        ('Final SoC (%)',  'Final SoC (%)', '#2196F3'),
        ('Peak sag (V)',   'Peak sag (V)',  '#FF9800'),
        ('Min V (V)',      'Min V (V)',     '#E53935'),
    ]
    temp_rise = df_sweep['Max T (\u00b0C)'].values - df_sweep['Ambient (C)'].values

    for i, (col, ylabel, color) in enumerate(metrics):
        ax = fig.add_subplot(gs4[i // 2, i % 2])
        y  = df_sweep[col].values
        ax.plot(t_vals, y, color=color, linewidth=2)
        ax.scatter(t_vals, y, c=dot_colors, s=40, zorder=4)
        ax.set_xlabel('Ambient (\u00b0C)'); ax.set_ylabel(ylabel)
        ax.set_title(ylabel)

    ax4 = fig.add_subplot(gs4[1, 1])
    ax4.plot(t_vals, temp_rise, '#9C27B0', linewidth=2)
    ax4.scatter(t_vals, temp_rise, c=dot_colors, s=40, zorder=4)
    ax4.set_xlabel('Ambient (\u00b0C)'); ax4.set_ylabel('Self-heating (\u00b0C)')
    ax4.set_title('Cell Self-Heating')

    legend_els = [mpatches.Patch(color=ACCENT, label='Completed'),
                  mpatches.Patch(color='#E53935', label='Depleted')]
    fig.legend(handles=legend_els, loc='lower center', ncol=2, fontsize=9,
               bbox_to_anchor=(0.5, 0.01))

    pdf.savefig(fig, bbox_inches='tight'); plt.close(fig)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 5 — MULTI-BATTERY COMPARISON CHARTS
    # ══════════════════════════════════════════════════════════════════════════
    fig = plt.figure(figsize=(11.69, 8.27))
    _header(fig, 'Battery Comparison Curves', run_info, 'p.5')
    _footer(fig, COMPANY_NAME, PDF_OUT_PATH)

    gs5 = gridspec.GridSpec(2, 2, figure=fig, left=0.08, right=0.96,
                            top=0.89, bottom=0.08, hspace=0.45, wspace=0.35)
    palette = [ACCENT, '#FF9800', '#4CAF50', '#E91E63', '#9C27B0']

    axes5 = [fig.add_subplot(gs5[r, c]) for r in range(2) for c in range(2)]
    fields = [('soc_pct', 'SoC (%)'), ('voltage_v', 'Voltage (V)'),
              ('current_a', 'Current (A)'), ('temp_c', 'Temp (\u00b0C)')]

    for (field, ylabel), ax in zip(fields, axes5):
        for r, p, col in zip(compare_results, compare_packs, palette):
            t_r = np.array(r.time_s)
            y_r = np.array(getattr(r, field))
            ax.plot(t_r, y_r, color=col, linewidth=1.8,
                    label=f'{p.battery_id} ({p.pack_energy_wh:.0f}Wh)')
        ax.set_xlabel('Time (s)'); ax.set_ylabel(ylabel); ax.set_title(ylabel)

    axes5[0].legend(fontsize=7, loc='lower left')

    pdf.savefig(fig, bbox_inches='tight'); plt.close(fig)

    # ══════════════════════════════════════════════════════════════════════════
    # PAGE 6 — FITTED PARAMETERS (if log available)
    # ══════════════════════════════════════════════════════════════════════════
    if fitted:
        fig = plt.figure(figsize=(11.69, 8.27))
        _header(fig, 'Reverse-Engineered Battery Parameters', run_info, 'p.6')
        _footer(fig, COMPANY_NAME, PDF_OUT_PATH)

        ax_fp = fig.add_axes([0.05, 0.10, 0.90, 0.78])
        ax_fp.axis('off')

        rows_fp = [
            ('Parameter', 'Fitted value', 'Catalog value', '\u0394 vs catalog', 'R\u00b2', 'Confidence'),
            ('R_internal (m\u03a9)',
             f'{fitted.r_internal_mohm.value:.2f} \u00b1 {fitted.r_internal_mohm.uncertainty:.2f}' if fitted.r_internal_mohm else '\u2014',
             f'{primary_pack.internal_resistance_mohm:.1f}',
             f'{fitted.r_internal_mohm.value - primary_pack.internal_resistance_mohm:+.1f}' if fitted.r_internal_mohm else '\u2014',
             f'{fitted.r_internal_mohm.r_squared:.3f}' if fitted.r_internal_mohm else '\u2014',
             'Good' if fitted.r_internal_mohm and fitted.r_internal_mohm.r_squared > 0.5 else 'Low'),
            ('Peukert k',
             f'{fitted.peukert_k.value:.4f}' if fitted.peukert_k else '\u2014',
             '1.050', '\u2014', '\u2014', '\u2014'),
            ('Capacity (Ah)',
             f'{fitted.actual_capacity_ah.value:.3f}' if fitted.actual_capacity_ah else '\u2014',
             f'{primary_pack.pack_capacity_ah:.3f}',
             f'{fitted.actual_capacity_ah.value - primary_pack.pack_capacity_ah:+.3f}' if fitted.actual_capacity_ah else '\u2014',
             '\u2014', '\u2014'),
            ('Degradation', f'{fitted.degradation_pct:.1f}%', '0%', '\u2014', '\u2014', '\u2014'),
        ]

        col_x = [0.0, 0.25, 0.42, 0.57, 0.70, 0.80]
        col_w = [0.25, 0.17, 0.15, 0.13, 0.10, 0.20]
        y_fp = 0.92; row_fp = 0.11

        for ridx, row_data in enumerate(rows_fp):
            bg = DARK if ridx == 0 else ('#F5F5F5' if ridx % 2 == 0 else 'white')
            fc = 'white' if ridx == 0 else TEXT
            fw = 'bold' if ridx == 0 else 'normal'
            for cidx, (val, x, w) in enumerate(zip(row_data, col_x, col_w)):
                if ridx > 0 and cidx == 5:
                    fc2 = '#2E7D32' if val == 'Good' else ('#F57F17' if val == 'Low' else TEXT)
                else:
                    fc2 = fc
                ax_fp.text(x + w/2, y_fp - ridx * row_fp + row_fp/2,
                           val, ha='center', va='center', fontsize=9,
                           color=fc2, fontweight=fw,
                           bbox=dict(boxstyle='square,pad=0.3',
                                     facecolor=bg, edgecolor='#E0E0E0',
                                     linewidth=0.5))

        if fitted.fit_warnings:
            wtext = '  \u26a0  ' + '   \u26a0  '.join(fitted.fit_warnings)
            ax_fp.text(0.5, 0.05, wtext, ha='center', va='center',
                       fontsize=8, color='#E65100',
                       bbox=dict(boxstyle='round,pad=0.4', facecolor='#FFF3E0',
                                 edgecolor='#FF9800'))

        pdf.savefig(fig, bbox_inches='tight'); plt.close(fig)

print(f'PDF report saved: {PDF_OUT_PATH}')
print(f'Pages: cover + mission + scorecard + temperature + comparison' +
      (' + fitted params' if fitted else ''))'''

for i, c in enumerate(nb['cells']):
    if c['id'] == 'gy83obmtfr5':
        nb['cells'][i]['source'] = lines(src)
        print(f'Fixed cell gy83obmtfr5 (index {i})')
        break

with open('notebooks/06_reports.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)

# Verify
import ast
with open('notebooks/06_reports.ipynb', encoding='utf-8') as f:
    nb2 = json.load(f)
errs = 0
for c in nb2['cells']:
    if c['cell_type'] != 'code': continue
    try: ast.parse(''.join(c['source']))
    except SyntaxError as e:
        print(f'  ERROR {c["id"]}: {e}')
        errs += 1
print(f'Done — {errs} error(s) remaining')
