"""Fix notebook 05 cell 3f8d0fd2: remove duplicate PHASE_COLORS injections."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/05_log_analysis.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

src = """\
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
def shade(ax, log_obj):
    if not log_obj.phase_type: return
    prev, t0 = log_obj.phase_type[0], log_obj.time_s[0]
    for t, ph in zip(log_obj.time_s[1:], log_obj.phase_type[1:]):
        if ph != prev:
            ax.axvspan(t0, t, alpha=0.12, color=PHASE_COLORS.get(prev, '#CCC'))
            t0, prev = t, ph
    ax.axvspan(t0, log_obj.time_s[-1], alpha=0.12, color=PHASE_COLORS.get(prev, '#CCC'))

t   = np.array(log.time_s)
v   = np.array(log.voltage_v)
i   = np.array(log.current_a)
mah = np.array(log.mah_used)
tmp = np.array(log.temp_c)

fig, axes = plt.subplots(2, 2, figsize=(14, 9))
fig.suptitle('Flight Log \u2014 Raw Signals', fontsize=13, fontweight='bold')

axes[0,0].plot(t, v, '#2196F3', linewidth=1.5)
shade(axes[0,0], log)
axes[0,0].set_ylabel('Voltage (V)'); axes[0,0].set_title('Terminal Voltage')

axes[0,1].plot(t, i, '#E53935', linewidth=1.5)
shade(axes[0,1], log)
axes[0,1].set_ylabel('Current (A)'); axes[0,1].set_title('Discharge Current')

axes[1,0].plot(t, mah, '#FF9800', linewidth=1.5)
shade(axes[1,0], log)
axes[1,0].set_ylabel('mAh consumed'); axes[1,0].set_title('Cumulative mAh')

if any(x > -50 for x in log.temp_c):
    axes[1,1].plot(t, tmp, '#9C27B0', linewidth=1.5)
    shade(axes[1,1], log)
    axes[1,1].set_ylabel('Temperature (C)'); axes[1,1].set_title('Cell Temperature')
else:
    axes[1,1].text(0.5, 0.5, 'No temperature data', transform=axes[1,1].transAxes, ha='center')

for ax in axes.flat: ax.set_xlabel('Time (s)')
patches = [mpatches.Patch(color=PHASE_COLORS.get(p, '#888'), label=p)
           for p in sorted(set(log.phase_type))]
fig.legend(handles=patches, loc='lower center', ncol=6, fontsize=8)
plt.tight_layout(rect=[0,0.05,1,1])
plt.savefig('log_raw_signals.png', bbox_inches='tight'); plt.show()"""

for i, c in enumerate(nb['cells']):
    if c['id'] == '3f8d0fd2':
        nb['cells'][i]['source'] = lines(src)
        print(f'Fixed cell 3f8d0fd2 (index {i})')
        break

with open('notebooks/05_log_analysis.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Done')
