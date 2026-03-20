"""Fix notebook 02: add MISSION_ID/MISSION_NAME to config cell, repair PHASE_COLORS in chart cell."""
import json, sys
sys.stdout.reconfigure(encoding='utf-8')

def lines(s):
    ls = s.split('\n')
    return [l + '\n' for l in ls[:-1]] + ([ls[-1]] if ls[-1] else [])

with open('notebooks/02_equipment_power_profile.ipynb', encoding='utf-8') as f:
    nb = json.load(f)

# ── Cell 11 (41fb01d2): config + mission definition ───────────────────────────
cell11 = """\
# ── Load settings from 00_configurator.ipynb (analysis_config.json) ───────────
import json as _json, os as _os
_CFG_PATH = _os.path.join(_os.path.dirname(_os.path.abspath('')), 'analysis_config.json')
if not _os.path.exists(_CFG_PATH):
    _CFG_PATH = 'analysis_config.json'
_cfg = {}
if _os.path.exists(_CFG_PATH):
    with open(_CFG_PATH) as _f:
        _cfg = _json.load(_f)
    print(f'Loaded config from {_CFG_PATH}')
else:
    print('No analysis_config.json found — using defaults below (run 00_configurator first)')

# ── Values from configurator (override here if desired) ───────────────────────
UAV_ID       = _cfg.get('uav_id',       'HEX_SURVEY_900')
MISSION_ID   = _cfg.get('mission_id',   'MY_MISSION_01')
MISSION_NAME = _cfg.get('mission_name', 'Custom Mission')

# ═══════════════════════════════════════════════════════════════
# MISSION DEFINITION — edit this section
# ═══════════════════════════════════════════════════════════════
# Uncomment to override config values:
# MISSION_ID   = 'MY_MISSION_01'
# MISSION_NAME = 'Custom Grid Survey'
# UAV_ID       = 'HEX_SURVEY_900'   # Must exist in UAV_Configurations

# Phase definitions:
# (phase_name, phase_type, duration_s, distance_m, altitude_m, airspeed_ms, power_override_W)
PHASES = [
    ('Pre-arm',          'IDLE',        90,    0,    0,   0,   None),
    ('Takeoff',          'TAKEOFF',     25,    0,    20,  3,   None),
    ('Climb to 80m',     'CLIMB',       55,    150,  80,  4,   None),
    ('Transit to AOI',   'CRUISE',      120,   800,  80,  8,   None),
    ('Grid survey row1', 'CRUISE',      375,  3000,  80,  8,   None),
    ('Turn hover',       'HOVER',       15,    0,    80,  0,   None),
    ('Grid survey row2', 'CRUISE',      375,  3000,  80,  8,   None),
    ('Turn hover',       'HOVER',       15,    0,    80,  0,   None),
    ('Grid survey row3', 'CRUISE',      375,  3000,  80,  8,   None),
    ('RTH cruise',       'CRUISE',      160,   800,  80,  8,   None),
    ('Descend',          'DESCEND',     55,    0,    10,  3,   None),
    ('Land',             'LAND',        20,    0,    0,   1,   None),
]
# ═══════════════════════════════════════════════════════════════

uav = db.uav_configs[UAV_ID]

mission_phases = [
    MissionPhase(
        mission_id=MISSION_ID,
        mission_name=MISSION_NAME,
        uav_config_id=UAV_ID,
        phase_seq=i + 1,
        phase_name=name,
        phase_type=ptype,
        duration_s=dur,
        distance_m=dist,
        altitude_m=alt,
        airspeed_ms=spd,
        power_override_w=pov,
    )
    for i, (name, ptype, dur, dist, alt, spd, pov) in enumerate(PHASES)
]

my_mission = MissionProfile(
    mission_id=MISSION_ID,
    mission_name=MISSION_NAME,
    uav_config_id=UAV_ID,
    phases=mission_phases,
)

print(f'Mission: {my_mission.mission_name}')
print(f'  UAV             : {uav.name}')
print(f'  UAV weight      : {uav.total_weight_g():.0f} g')
print(f'  Total duration  : {my_mission.total_duration_s:.0f} s  '
      f'({my_mission.total_duration_s/60:.1f} min)')
print(f'  Total distance  : {my_mission.total_distance_m:.0f} m')
print(f'  Total energy    : {my_mission.total_energy_wh(uav):.1f} Wh')
print()

rows = []
t_acc = 0
for ph in my_mission.phases:
    pw = ph.effective_power_w(uav)
    rows.append({
        '#': ph.phase_seq,
        'Phase': ph.phase_name,
        'Type': ph.phase_type,
        'Duration (s)': ph.duration_s,
        'Distance (m)': ph.distance_m,
        'Altitude (m)': ph.altitude_m,
        'Speed (m/s)': ph.airspeed_ms,
        'Power (W)': round(pw, 1),
        'Energy (Wh)': round(ph.energy_wh(uav), 2),
        'Start T (s)': t_acc,
    })
    t_acc += ph.duration_s

df_my = pd.DataFrame(rows).set_index('#')
df_my"""

# ── Cell 12 (b4d3749a): power profile chart — remove duplicate PHASE_COLORS ───
cell12 = """\
# ── Power Profile Chart ────────────────────────────────────────────────────
times, powers = my_mission.power_profile_w(uav, resolution_s=1.0)

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

fig, axes = plt.subplots(3, 1, figsize=(14, 10),
                          gridspec_kw={'height_ratios': [3, 1, 1]})
fig.suptitle(f'{my_mission.mission_name} — Power Profile', fontsize=14, fontweight='bold')

ax_p = axes[0]
ax_p.plot(times, powers, color='#1F3864', linewidth=1.5, zorder=3)
ax_p.fill_between(times, powers, alpha=0.15, color='#1F3864', zorder=2)

t_start = 0
phase_handles = {}
for ph in my_mission.phases:
    t_end  = t_start + ph.duration_s
    color  = PHASE_COLORS.get(ph.phase_type, '#CCC')
    ax_p.axvspan(t_start, t_end, alpha=0.12, color=color, zorder=1)
    if ph.phase_type not in phase_handles:
        phase_handles[ph.phase_type] = mpatches.Patch(
            color=color, alpha=0.5, label=ph.phase_type
        )
    t_start = t_end

ax_p.set_ylabel('Power Draw (W)')
ax_p.set_title('Total UAV Power vs Time')
ax_p.legend(handles=list(phase_handles.values()),
            ncol=5, loc='upper right', fontsize=8)
ax_p.grid(alpha=0.25)
ax_p.set_xlim(0, max(times))

ax_alt = axes[1]
t_alt, alts = [], []
t_now = 0
for ph in my_mission.phases:
    for s in range(int(ph.duration_s)):
        frac = s / max(1, ph.duration_s)
        prev_alt = my_mission.phases[my_mission.phases.index(ph) - 1].altitude_m \\
                   if my_mission.phases.index(ph) > 0 else 0
        interp_alt = prev_alt + (ph.altitude_m - prev_alt) * frac
        t_alt.append(t_now + s)
        alts.append(interp_alt)
    t_now += ph.duration_s
ax_alt.fill_between(t_alt, alts, alpha=0.3, color='steelblue')
ax_alt.plot(t_alt, alts, color='steelblue', linewidth=1)
ax_alt.set_ylabel('Altitude (m)')
ax_alt.set_title('Altitude Profile')
ax_alt.grid(alpha=0.25)
ax_alt.set_xlim(0, max(times))

ax_e = axes[2]
cumulative_e = np.cumsum(np.array(powers) * 1 / 3600)
ax_e.plot(times, cumulative_e, color='firebrick', linewidth=1.5)
ax_e.fill_between(times, cumulative_e, alpha=0.15, color='firebrick')
ax_e.set_xlabel('Time (s)')
ax_e.set_ylabel('Cumulative Energy (Wh)')
ax_e.set_title(f'Cumulative Energy  (total: {my_mission.total_energy_wh(uav):.1f} Wh)')
ax_e.grid(alpha=0.25)
ax_e.set_xlim(0, max(times))

def fmt_time(x, _):
    return f'{int(x//60)}:{int(x%60):02d}'
for ax in axes:
    ax.xaxis.set_major_formatter(plt.FuncFormatter(fmt_time))

plt.tight_layout()
plt.savefig('power_profile.png', dpi=120, bbox_inches='tight')
plt.show()"""

nb['cells'][11]['source'] = lines(cell11)
nb['cells'][12]['source'] = lines(cell12)

with open('notebooks/02_equipment_power_profile.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1, ensure_ascii=False)
print('Fixed: cells 11 (MISSION_ID/MISSION_NAME added) and 12 (PHASE_COLORS deduped)')
