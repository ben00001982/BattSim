"""
batteries/log_importer.py

Parse ArduPilot flight logs into a unified FlightLog dataclass.

Supported formats:
  • .bin   — ArduPilot binary DataFlash (requires pymavlink)
  • .log   — ArduPilot text DataFlash  (no extra dependencies)
  • .csv   — Mission Planner telemetry export

Key ArduPilot messages extracted:
  BAT   → Volt, VoltR, Curr, CurrTot, EnrgTot, Temp, Rem
  MODE  → flight mode changes (maps to phase types)
  GPS   → speed, altitude
  RCOU  → throttle channel output (phase proxy when MODE unavailable)
  ATT   → pitch, roll (flight dynamics)
"""
from __future__ import annotations
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import warnings

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from pymavlink import mavutil
    HAS_PYMAVLINK = True
except ImportError:
    HAS_PYMAVLINK = False


# ── ArduPilot flight mode → mission phase type map ───────────────────────────
# Covers ArduCopter + ArduPlane common modes
ARDUPILOT_MODE_MAP: dict[str, str] = {
    # ArduCopter
    "STABILIZE": "CRUISE", "ACRO": "CRUISE", "ALT_HOLD": "HOVER",
    "AUTO": "CRUISE",      "GUIDED": "CRUISE","LOITER": "HOVER",
    "RTL": "CRUISE",       "CIRCLE": "HOVER", "LAND": "LAND",
    "OF_LOITER": "HOVER",  "DRIFT": "CRUISE", "SPORT": "CRUISE",
    "AUTOTUNE": "HOVER",   "POSHOLD": "HOVER","BRAKE": "HOVER",
    "THROW": "TAKEOFF",    "AVOID_ADSB": "CRUISE","GUIDED_NOGPS": "HOVER",
    "SMART_RTL": "CRUISE", "FLOWHOLD": "HOVER",  "FOLLOW": "CRUISE",
    "ZIGZAG": "CRUISE",    "SYSTEMID": "HOVER",  "AUTOROTATE": "DESCEND",
    # ArduPlane
    "MANUAL": "CRUISE",    "CIRCLE_PLANE": "HOVER","CRUISE_PLANE": "CRUISE",
    "FLY_BY_WIRE_A": "CRUISE","FLY_BY_WIRE_B":"CRUISE","TRAINING": "CRUISE",
    "TAKEOFF_PLANE": "TAKEOFF","QHOVER": "HOVER","QLOITER": "HOVER",
    "QLAND": "LAND",       "QRTL": "CRUISE",  "QAUTOTUNE": "HOVER",
    "QACRO": "CRUISE",
    # Generic fallback
    "UNKNOWN": "CRUISE",
}

ARDUPILOT_COPTER_MODES = {
    0: "STABILIZE", 1: "ACRO",    2: "ALT_HOLD", 3: "AUTO",
    4: "GUIDED",    5: "LOITER",  6: "RTL",       7: "CIRCLE",
    9: "LAND",     11: "DRIFT",  13: "SPORT",    14: "AUTOTUNE",
    15: "POSHOLD", 16: "BRAKE",  17: "THROW",    18: "AVOID_ADSB",
    19: "GUIDED_NOGPS", 20: "SMART_RTL", 21: "FLOWHOLD",
    22: "FOLLOW",  23: "ZIGZAG", 24: "SYSTEMID", 25: "AUTOROTATE",
}

ARDUPILOT_PLANE_MODES = {
    0: "MANUAL",  1: "CIRCLE_PLANE",  2: "STABILIZE",  3: "TRAINING",
    4: "ACRO",    5: "FLY_BY_WIRE_A", 6: "FLY_BY_WIRE_B", 10: "AUTO",
    11: "RTL",   12: "LOITER",        15: "GUIDED",     17: "TAKEOFF_PLANE",
    19: "QSTABILIZE",20:"QHOVER",     21:"QLOITER",     22:"QLAND",
    23: "QRTL",  25: "QAUTOTUNE",     26: "QACRO",
}


# ── Core data container ───────────────────────────────────────────────────────

@dataclass
class FlightLog:
    """
    Unified flight log — all time-series aligned to the same 1-second
    resampled grid after import.

    All lists are parallel arrays (same length).  Missing values are np.nan
    (or None if numpy is not available).
    """
    source_file:  str = ""
    log_format:   str = ""        # 'bin', 'log', 'csv'
    vehicle_type: str = "copter"  # 'copter' or 'plane'

    # ── Raw time-series (seconds from log start) ──
    time_s:       list[float] = field(default_factory=list)
    voltage_v:    list[float] = field(default_factory=list)
    voltage_rest_v: list[float] = field(default_factory=list)  # VoltR / resting
    current_a:    list[float] = field(default_factory=list)
    mah_used:     list[float] = field(default_factory=list)
    energy_wh:    list[float] = field(default_factory=list)
    temp_c:       list[float] = field(default_factory=list)
    soc_pct:      list[float] = field(default_factory=list)     # computed post-load

    # ── Flight phase labels ──
    phase_type:   list[str]   = field(default_factory=list)
    flight_mode:  list[str]   = field(default_factory=list)

    # ── Metadata ──
    fc_ir_mohm:        list[float] = field(default_factory=list)  # BAT.Res if present
    gps_speed_ms:      list[float] = field(default_factory=list)
    altitude_m:        list[float] = field(default_factory=list)
    throttle_pct:      list[float] = field(default_factory=list)

    # ── Aggregate stats (populated by compute_stats()) ──
    total_flight_s:    float = 0.0
    total_mah:         float = 0.0
    total_energy_wh:   float = 0.0
    initial_voltage:   float = 0.0
    final_voltage:     float = 0.0
    peak_current_a:    float = 0.0
    avg_current_a:     float = 0.0
    min_voltage_v:     float = 0.0
    max_temp_c:        float = 0.0
    initial_capacity_ah: float = 0.0  # estimated from mah consumed + final SoC

    def compute_stats(self, nominal_capacity_ah: Optional[float] = None):
        """Populate aggregate statistics after loading."""
        if not self.time_s:
            return
        self.total_flight_s  = self.time_s[-1] - self.time_s[0]
        self.initial_voltage = self.voltage_v[0] if self.voltage_v else 0
        self.final_voltage   = self.voltage_v[-1] if self.voltage_v else 0

        valid_v = [v for v in self.voltage_v if v and v > 0]
        valid_i = [i for i in self.current_a  if i and i > 0]
        valid_t = [t for t in self.temp_c     if t and t > -50]

        self.min_voltage_v = min(valid_v) if valid_v else 0
        self.peak_current_a= max(valid_i) if valid_i else 0
        self.avg_current_a = sum(valid_i) / len(valid_i) if valid_i else 0
        self.max_temp_c    = max(valid_t) if valid_t else 0

        if self.mah_used and self.mah_used[-1]:
            self.total_mah = max(self.mah_used)
        if self.energy_wh and self.energy_wh[-1]:
            self.total_energy_wh = max(self.energy_wh)

        # Compute SoC if not already set
        if nominal_capacity_ah and self.mah_used and not self.soc_pct:
            self.soc_pct = [
                max(0.0, min(100.0, 100.0 - m / nominal_capacity_ah * 100))
                for m in self.mah_used
            ]

    def summary(self) -> str:
        return (
            f"FlightLog: {Path(self.source_file).name}  [{self.log_format}]\n"
            f"  Duration    : {self.total_flight_s:.0f} s  ({self.total_flight_s/60:.1f} min)\n"
            f"  Samples     : {len(self.time_s)}\n"
            f"  V range     : {self.min_voltage_v:.2f} – {self.initial_voltage:.2f} V\n"
            f"  Peak I      : {self.peak_current_a:.1f} A  avg: {self.avg_current_a:.1f} A\n"
            f"  Total mAh   : {self.total_mah:.0f} mAh  "
            f"({self.total_energy_wh:.1f} Wh)\n"
            f"  Max temp    : {self.max_temp_c:.1f} °C\n"
            f"  Has temp    : {any(t > -50 for t in self.temp_c)}\n"
            f"  Has resting V: {any(v > 0 for v in self.voltage_rest_v)}"
        )


# ── Text .log parser ──────────────────────────────────────────────────────────

class TextLogParser:
    """
    Parses ArduPilot ASCII .log files.

    Format:
      FMT, <type>, <length>, <name>, <format>, <columns...>
      <name>, <values...>
    """

    def __init__(self):
        self._fmt: dict[str, list[str]] = {}   # message_name → [col_names]

    def parse(self, path: Path) -> FlightLog:
        log = FlightLog(source_file=str(path), log_format="log")
        bat_rows, mode_rows, gps_rows, rcou_rows = [], [], [], []

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split(",")]
                if not parts:
                    continue

                msg = parts[0].upper()

                if msg == "FMT" and len(parts) >= 6:
                    # FMT, type, length, name, format_string, col1, col2, ...
                    name = parts[3].upper()
                    cols = [c.strip() for c in parts[5:]]
                    self._fmt[name] = cols

                elif msg == "BAT" and len(parts) >= 3:
                    bat_rows.append(parts[1:])
                elif msg == "MODE" and len(parts) >= 3:
                    mode_rows.append(parts[1:])
                elif msg == "GPS" and len(parts) >= 3:
                    gps_rows.append(parts[1:])
                elif msg == "RCOU" and len(parts) >= 3:
                    rcou_rows.append(parts[1:])

        if not bat_rows:
            raise ValueError(
                f"No BAT messages found in {path.name}. "
                "Ensure battery logging is enabled (LOG_BITMASK includes battery)."
            )

        self._fill_bat(log, bat_rows)
        self._fill_modes(log, mode_rows)
        self._fill_gps(log, gps_rows)
        self._fill_throttle(log, rcou_rows)
        self._infer_phases(log)
        log.compute_stats()
        return log

    def _safe_float(self, s, default=0.0):
        try:
            return float(s)
        except (ValueError, TypeError):
            return default

    def _fill_bat(self, log: FlightLog, rows: list):
        bat_cols = self._fmt.get("BAT", [])

        def col_idx(names):
            for n in names:
                n_up = n.upper()
                for i, c in enumerate(bat_cols):
                    if c.upper() == n_up:
                        return i
            return None

        # Column index discovery (handle format variations across AP versions)
        i_time  = col_idx(["TimeUS", "TimeMS"]) 
        i_volt  = col_idx(["Volt", "V"])
        i_voltr = col_idx(["VoltR", "VoltRest"])
        i_curr  = col_idx(["Curr", "I"])
        i_curtot= col_idx(["CurrTot", "mAh"])
        i_enrg  = col_idx(["EnrgTot", "Wh"])
        i_temp  = col_idx(["Temp", "T"])
        i_res   = col_idx(["Res", "IR"])

        t0 = None
        for row in rows:
            def g(idx, default=0.0):
                if idx is None or idx >= len(row):
                    return default
                return self._safe_float(row[idx], default)

            t_raw = g(i_time, 0.0)
            # TimeUS is microseconds, TimeMS is milliseconds
            if bat_cols and "TimeUS" in (bat_cols[0] if bat_cols else ""):
                t_s = t_raw / 1_000_000.0
            else:
                t_s = t_raw / 1_000.0

            if t0 is None:
                t0 = t_s
            t_s -= t0

            log.time_s.append(round(t_s, 3))
            log.voltage_v.append(g(i_volt, 0.0))
            log.voltage_rest_v.append(g(i_voltr, 0.0))
            log.current_a.append(g(i_curr, 0.0))
            log.mah_used.append(g(i_curtot, 0.0))
            log.energy_wh.append(g(i_enrg, 0.0))
            log.temp_c.append(g(i_temp, -999.0))
            log.fc_ir_mohm.append(g(i_res, 0.0) * 1000.0)  # Ω→mΩ if stored as Ω

    def _fill_modes(self, log: FlightLog, rows: list):
        """Build a time-indexed mode lookup from MODE messages."""
        mode_cols = self._fmt.get("MODE", [])
        i_time  = next((i for i, c in enumerate(mode_cols) if "TIME" in c.upper()), 0)
        i_mode  = next((i for i, c in enumerate(mode_cols) if "MODE" in c.upper()), 1)
        i_moden = next((i for i, c in enumerate(mode_cols) if "ASTEXT" in c.upper() or "NAME" in c.upper()), None)

        self._mode_events = []
        t0 = log.time_s[0] if log.time_s else 0
        for row in rows:
            try:
                t_us = float(row[i_time])
                t_s  = t_us / 1_000_000.0 - t0
                mode_num = int(float(row[i_mode]))
                if i_moden and i_moden < len(row):
                    mode_str = row[i_moden].strip().upper()
                else:
                    mode_str = ARDUPILOT_COPTER_MODES.get(mode_num, "UNKNOWN")
                self._mode_events.append((t_s, mode_str))
            except (ValueError, IndexError):
                continue

    def _fill_gps(self, log: FlightLog, rows: list):
        gps_cols = self._fmt.get("GPS", [])
        i_time = next((i for i, c in enumerate(gps_cols) if "TIME" in c.upper()), 0)
        i_spd  = next((i for i, c in enumerate(gps_cols) if "SPD" in c.upper() or "SPEED" in c.upper()), None)
        i_alt  = next((i for i, c in enumerate(gps_cols) if "ALT" in c.upper()), None)
        if not gps_cols:
            return
        t0 = log.time_s[0] if log.time_s else 0
        self._gps_events = []
        for row in rows:
            try:
                t_s = float(row[i_time]) / 1_000_000.0 - t0
                spd = float(row[i_spd]) if i_spd and i_spd < len(row) else 0.0
                alt = float(row[i_alt]) if i_alt and i_alt < len(row) else 0.0
                self._gps_events.append((t_s, spd, alt))
            except (ValueError, IndexError):
                continue

    def _fill_throttle(self, log: FlightLog, rows: list):
        rcou_cols = self._fmt.get("RCOU", [])
        i_time = next((i for i, c in enumerate(rcou_cols) if "TIME" in c.upper()), 0)
        i_c3   = next((i for i, c in enumerate(rcou_cols) if c.upper() in ("C3","CH3")), None)
        if not rcou_cols:
            return
        t0 = log.time_s[0] if log.time_s else 0
        self._throttle_events = []
        for row in rows:
            try:
                t_s = float(row[i_time]) / 1_000_000.0 - t0
                thr = float(row[i_c3]) if i_c3 and i_c3 < len(row) else 1500.0
                thr_pct = max(0.0, min(100.0, (thr - 1000.0) / 10.0))
                self._throttle_events.append((t_s, thr_pct))
            except (ValueError, IndexError):
                continue

    def _infer_phases(self, log: FlightLog):
        """Map mode events to phase types and assign to each BAT sample."""
        mode_map = getattr(self, "_mode_events", [])
        for t in log.time_s:
            phase = "CRUISE"
            mode  = "AUTO"
            for t_ev, m_str in reversed(mode_map):
                if t_ev <= t:
                    mode  = m_str
                    phase = ARDUPILOT_MODE_MAP.get(m_str, "CRUISE")
                    break
            log.phase_type.append(phase)
            log.flight_mode.append(mode)


# ── Binary .bin parser (via pymavlink) ────────────────────────────────────────

class BinaryLogParser:
    """
    Parses ArduPilot binary .bin DataFlash logs using pymavlink.
    Falls back with a clear error message if pymavlink is not installed.
    """

    def parse(self, path: Path) -> FlightLog:
        if not HAS_PYMAVLINK:
            raise ImportError(
                "pymavlink is required to parse .bin files.\n"
                "Install with: pip install pymavlink"
            )

        log = FlightLog(source_file=str(path), log_format="bin")
        mlog = mavutil.mavlink_connection(str(path))

        bat_rows, mode_rows = [], []
        t0 = None

        while True:
            msg = mlog.recv_match(blocking=False)
            if msg is None:
                break
            mtype = msg.get_type()

            if mtype == "BAT":
                d = msg.to_dict()
                t_us = d.get("TimeUS", 0)
                if t0 is None:
                    t0 = t_us
                t_s = (t_us - t0) / 1_000_000.0
                log.time_s.append(round(t_s, 3))
                log.voltage_v.append(d.get("Volt", 0.0))
                log.voltage_rest_v.append(d.get("VoltR", 0.0))
                log.current_a.append(d.get("Curr", 0.0))
                log.mah_used.append(d.get("CurrTot", 0.0))
                log.energy_wh.append(d.get("EnrgTot", 0.0))
                log.temp_c.append(d.get("Temp", -999.0))
                log.fc_ir_mohm.append(d.get("Res", 0.0) * 1000.0)

            elif mtype == "MODE":
                d = msg.to_dict()
                t_us = d.get("TimeUS", 0)
                if t0:
                    t_s = (t_us - t0) / 1_000_000.0
                    mode_num = d.get("Mode", 0)
                    mode_str = d.get("ModeStr",
                                     ARDUPILOT_COPTER_MODES.get(mode_num, "AUTO"))
                    mode_rows.append((t_s, mode_str.upper()))

        if not log.time_s:
            raise ValueError(f"No BAT data found in {path.name}.")

        TextLogParser._fill_modes(self, log, [])
        self._mode_events_bin = mode_rows
        for t in log.time_s:
            phase, mode = "CRUISE", "AUTO"
            for t_ev, m_str in reversed(mode_rows):
                if t_ev <= t:
                    phase = ARDUPILOT_MODE_MAP.get(m_str, "CRUISE")
                    mode  = m_str
                    break
            log.phase_type.append(phase)
            log.flight_mode.append(mode)

        log.compute_stats()
        return log


# ── CSV parser (Mission Planner telemetry export) ─────────────────────────────

class CSVLogParser:
    """
    Parses Mission Planner CSV telemetry exports.
    Column names are flexible — matched by keyword.
    """

    VOLTAGE_KEYS  = ["voltage", "volt", "bat_volt", "battery_voltage"]
    CURRENT_KEYS  = ["current", "curr", "bat_curr", "battery_current"]
    MAH_KEYS      = ["batusedmah", "mah", "current_total", "curr_tot"]
    ENERGY_KEYS   = ["energy_wh", "wh", "enrg_tot"]
    TEMP_KEYS     = ["bat_temp", "temperature", "temp"]
    TIME_KEYS     = ["time_boot_ms", "time_s", "timems", "time_usec", "timestamp"]

    def _find_col(self, header: list[str], keys: list[str]) -> Optional[int]:
        for k in keys:
            for i, h in enumerate(header):
                if k.lower() in h.lower().replace(" ", "").replace("_",""):
                    return i
        return None

    def parse(self, path: Path) -> FlightLog:
        log = FlightLog(source_file=str(path), log_format="csv")

        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            header = [h.strip() for h in next(reader)]

            i_t    = self._find_col(header, self.TIME_KEYS)
            i_v    = self._find_col(header, self.VOLTAGE_KEYS)
            i_i    = self._find_col(header, self.CURRENT_KEYS)
            i_mah  = self._find_col(header, self.MAH_KEYS)
            i_wh   = self._find_col(header, self.ENERGY_KEYS)
            i_temp = self._find_col(header, self.TEMP_KEYS)

            if i_v is None:
                raise ValueError(
                    f"Cannot find voltage column in {path.name}.\n"
                    f"Available: {header}"
                )

            def g(row, idx, default=0.0):
                if idx is None or idx >= len(row):
                    return default
                try:
                    return float(row[idx])
                except (ValueError, TypeError):
                    return default

            t0 = None
            mah_prev = 0.0
            for row_num, row in enumerate(reader):
                if not any(row):
                    continue
                t_raw = g(row, i_t, row_num)
                t_s   = t_raw / 1000.0 if t_raw > 1e6 else t_raw
                if t0 is None:
                    t0 = t_s
                t_s -= t0

                mah = g(row, i_mah, 0.0)
                if mah == 0.0 and row_num > 0:
                    # If mAh not directly available, leave as 0 (fitter will skip)
                    pass

                log.time_s.append(round(t_s, 3))
                log.voltage_v.append(g(row, i_v, 0.0))
                log.voltage_rest_v.append(0.0)
                log.current_a.append(g(row, i_i, 0.0))
                log.mah_used.append(mah)
                log.energy_wh.append(g(row, i_wh, 0.0))
                log.temp_c.append(g(row, i_temp, -999.0))
                log.fc_ir_mohm.append(0.0)
                log.phase_type.append("CRUISE")
                log.flight_mode.append("AUTO")

        if not log.time_s:
            raise ValueError(f"No data rows found in {path.name}.")
        log.compute_stats()
        return log


# ── Public entry point ────────────────────────────────────────────────────────

def load_log(
    path: str | Path,
    nominal_capacity_ah: Optional[float] = None,
    vehicle_type: str = "copter",
) -> FlightLog:
    """
    Load an ArduPilot flight log from any supported format.

    Args:
        path                : Path to .bin, .log, or .csv file
        nominal_capacity_ah : Battery capacity for SoC calculation (optional)
        vehicle_type        : 'copter' or 'plane' (affects mode mapping)

    Returns:
        FlightLog with all available signals populated
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".bin":
        parser = BinaryLogParser()
    elif suffix in (".log", ".txt"):
        parser = TextLogParser()
    elif suffix == ".csv":
        parser = CSVLogParser()
    else:
        # Try text parser as fallback
        warnings.warn(f"Unknown extension '{suffix}', attempting text parse.")
        parser = TextLogParser()

    log = parser.parse(path)
    log.vehicle_type = vehicle_type

    if nominal_capacity_ah and not log.soc_pct:
        log.compute_stats(nominal_capacity_ah)

    return log


def generate_synthetic_log(
    pack,
    mission,
    uav,
    discharge_pts,
    ambient_temp_c: float = 25.0,
    dt_s: float = 1.0,
    noise_v: float = 0.02,
    noise_i: float = 0.5,
    initial_soc_pct: float = 100.0,
    peukert_k: float = 1.05,
    cutoff_soc_pct: float = 10.0,
    dod_limit_pct: float = 80.0,
) -> FlightLog:
    """
    Generate a synthetic FlightLog from a simulation result.
    Useful for testing the parameter fitter without real flight data.
    Adds realistic sensor noise to voltage and current.
    All simulation parameters match those exposed on the Simulation page.
    """
    import random
    from mission.simulator import run_simulation

    result = run_simulation(
        pack=pack, mission=mission, uav=uav,
        discharge_pts=discharge_pts,
        ambient_temp_c=ambient_temp_c, dt_s=dt_s,
        initial_soc_pct=initial_soc_pct,
        peukert_k=peukert_k,
        cutoff_soc_pct=cutoff_soc_pct,
        dod_limit_pct=dod_limit_pct,
    )

    rng = random.Random(42)
    log = FlightLog(source_file="synthetic", log_format="synthetic")

    mah_cum = 0.0
    wh_cum  = 0.0
    for i, t in enumerate(result.time_s):
        v_noisy = result.voltage_v[i] + rng.gauss(0, noise_v)
        i_noisy = max(0, result.current_a[i] + rng.gauss(0, noise_i))
        dt = (result.time_s[i] - result.time_s[i - 1]) if i > 0 else dt_s
        mah_cum += i_noisy * dt / 3600 * 1000
        wh_cum  += v_noisy * i_noisy * dt / 3600

        log.time_s.append(t)
        log.voltage_v.append(round(v_noisy, 4))
        log.voltage_rest_v.append(0.0)
        log.current_a.append(round(i_noisy, 3))
        log.mah_used.append(round(mah_cum, 2))
        log.energy_wh.append(round(wh_cum, 4))
        log.temp_c.append(round(result.temp_c[i], 2))
        log.soc_pct.append(result.soc_pct[i])
        log.fc_ir_mohm.append(0.0)
        log.phase_type.append(result.phase_type[i])
        log.flight_mode.append(result.phase_type[i])

    log.compute_stats(pack.pack_capacity_ah)
    return log
