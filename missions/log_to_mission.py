"""
missions/log_to_mission.py

Pure Python — zero Streamlit imports.
Segment a FlightLog into MissionSegments and convert to MissionPhase objects.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from batteries.log_importer import FlightLog
    from batteries.models import MissionPhase
    from batteries.database import BatteryDatabase


# ── MissionSegment dataclass ──────────────────────────────────────────────────

@dataclass
class MissionSegment:
    seq:             int
    mode_name:       str      # ArduPilot mode name — used as phase_type
    phase_name:      str      # editable display label
    duration_s:      float
    mean_power_w:    float    # measured mean power (V*I) from log
    min_power_w:     float
    max_power_w:     float
    power_std_w:     float
    n_power_samples: int
    energy_wh:       float
    delta_mah:       float
    mean_altitude_m: float = 0.0
    mean_speed_ms:   float = 0.0
    start_time_s:    float = 0.0
    end_time_s:      float = 0.0
    is_transient:    bool  = False
    confidence:      str   = "high"   # "high" | "medium" | "low"
    notes:           str   = ""

    def merge_with(
        self,
        other: "MissionSegment",
        override_power_w: Optional[float] = None,
    ) -> "MissionSegment":
        """
        Merge self and other. Duration-weighted mean used for scalar fields.
        override_power_w: if provided, use as mean_power_w (user confirmed).
                          If None, compute duration-weighted mean (for UI suggestion only).
        seq and phase_name taken from self.
        mode_name: keep if identical, else "MIXED".
        confidence: take the lower of the two.
        """
        total_dur = self.duration_s + other.duration_s
        if total_dur == 0:
            return self
        ws = self.duration_s  / total_dur
        wo = other.duration_s / total_dur
        weighted_power = self.mean_power_w * ws + other.mean_power_w * wo
        _conf_rank = {"high": 2, "medium": 1, "low": 0}
        return MissionSegment(
            seq             = self.seq,
            mode_name       = (self.mode_name if self.mode_name == other.mode_name
                               else "MIXED"),
            phase_name      = self.phase_name,
            duration_s      = total_dur,
            mean_power_w    = override_power_w if override_power_w is not None
                              else weighted_power,
            min_power_w     = min(self.min_power_w, other.min_power_w),
            max_power_w     = max(self.max_power_w, other.max_power_w),
            power_std_w     = self.power_std_w * ws + other.power_std_w * wo,
            n_power_samples = self.n_power_samples + other.n_power_samples,
            energy_wh       = self.energy_wh + other.energy_wh,
            delta_mah       = self.delta_mah + other.delta_mah,
            mean_altitude_m = self.mean_altitude_m * ws + other.mean_altitude_m * wo,
            mean_speed_ms   = self.mean_speed_ms   * ws + other.mean_speed_ms   * wo,
            start_time_s    = min(self.start_time_s, other.start_time_s),
            end_time_s      = max(self.end_time_s,   other.end_time_s),
            is_transient    = False,
            confidence      = min(self.confidence, other.confidence,
                                  key=lambda c: _conf_rank.get(c, 0)),
            notes           = self.notes,
        )


# ── segment_log ───────────────────────────────────────────────────────────────

def segment_log(
    log: "FlightLog",
    min_duration_s: float = 8.0,
    min_power_samples: int = 3,
) -> list[MissionSegment]:
    """
    Split FlightLog into MissionSegments at every mode/phase_type change.

    Raises ValueError if log.phase_type is empty.

    Algorithm:
      1. Walk log.phase_type finding contiguous runs of the same mode name.
      2. For each run collect aligned BAT samples in that index range.
      3. power_w[i] = voltage_v[i] * current_a[i]
      4. energy_wh  = sum(power_w[i] * dt_i / 3600)
             dt_i = time_s[i+1] - time_s[i], or 1.0 for the last sample.
      5. delta_mah  = mah_used[end_idx] - mah_used[start_idx]
             (skip if mah_used is empty or all-zero).
      6. altitude / speed: mean of slice — 0.0 if list is empty.
      7. Confidence:
             "high"   if n_power_samples >= 10 AND power_std_w < mean_power_w*0.35
             "medium" if n_power_samples >= min_power_samples
             "low"    otherwise
      8. Mark is_transient = True if duration_s < min_duration_s.
      9. Filter pre-arm/post-land idle: skip first or last segment if
             mean_power_w < 5.0 W AND mode_name in ("STABILIZE","MANUAL","GUIDED_NOGPS")
      10. Re-number seq 1…N.

    NOTE: power is ALWAYS measured and stored regardless of whether the
    caller intends to use it. The import-mode decision is made in
    to_mission_phases(), not here.
    """
    if not log.phase_type:
        raise ValueError(
            "log.phase_type is empty — no mode data available to segment log."
        )

    n = len(log.phase_type)

    # ── Step 1: find contiguous runs ──────────────────────────────────────────
    runs = []  # list of (mode_name, start_idx, end_idx_inclusive)
    i = 0
    while i < n:
        mode = log.phase_type[i]
        j = i + 1
        while j < n and log.phase_type[j] == mode:
            j += 1
        runs.append((mode, i, j - 1))
        i = j

    segments: list[MissionSegment] = []

    for mode_name, start_idx, end_idx in runs:
        # ── Time bounds ───────────────────────────────────────────────────────
        times_slice = log.time_s[start_idx:end_idx + 1]
        if not times_slice:
            continue
        start_time_s = times_slice[0]
        end_time_s   = times_slice[-1]
        duration_s   = end_time_s - start_time_s

        # ── Step 3 & 4: power and energy ─────────────────────────────────────
        v_slice = log.voltage_v[start_idx:end_idx + 1]  if log.voltage_v  else []
        i_slice = log.current_a[start_idx:end_idx + 1]  if log.current_a  else []

        power_w_list: list[float] = []
        for v, cur in zip(v_slice, i_slice):
            if v is not None and cur is not None:
                pw = float(v) * float(cur)
                power_w_list.append(pw if pw >= 0 else 0.0)

        n_power_samples = len(power_w_list)
        mean_power_w    = sum(power_w_list) / n_power_samples if power_w_list else 0.0
        min_power_w     = min(power_w_list) if power_w_list else 0.0
        max_power_w     = max(power_w_list) if power_w_list else 0.0

        if n_power_samples > 1:
            variance    = sum((p - mean_power_w) ** 2 for p in power_w_list) / n_power_samples
            power_std_w = math.sqrt(variance)
        else:
            power_std_w = 0.0

        # energy_wh via step-integration
        energy_wh = 0.0
        for k, pw in enumerate(power_w_list):
            if k < len(times_slice) - 1:
                dt = times_slice[k + 1] - times_slice[k]
                if dt <= 0:
                    dt = 1.0
            else:
                dt = 1.0
            energy_wh += pw * dt / 3600.0

        # ── Step 5: delta_mah ─────────────────────────────────────────────────
        delta_mah = 0.0
        if (log.mah_used
                and len(log.mah_used) > end_idx
                and any(m for m in log.mah_used)):
            start_mah = log.mah_used[start_idx] if start_idx < len(log.mah_used) else 0.0
            end_mah   = log.mah_used[end_idx]
            delta_mah = (end_mah or 0.0) - (start_mah or 0.0)

        # ── Step 6: altitude / speed ──────────────────────────────────────────
        alt_slice = log.altitude_m[start_idx:end_idx + 1]   if log.altitude_m   else []
        spd_slice = log.gps_speed_ms[start_idx:end_idx + 1] if log.gps_speed_ms else []

        valid_alt = [float(a) for a in alt_slice if a is not None and float(a) > -9000]
        valid_spd = [float(s) for s in spd_slice if s is not None]

        mean_altitude_m = sum(valid_alt) / len(valid_alt) if valid_alt else 0.0
        mean_speed_ms   = sum(valid_spd) / len(valid_spd) if valid_spd else 0.0

        # ── Step 7: confidence ────────────────────────────────────────────────
        if (n_power_samples >= 10
                and mean_power_w > 0
                and power_std_w < mean_power_w * 0.35):
            confidence = "high"
        elif n_power_samples >= min_power_samples:
            confidence = "medium"
        else:
            confidence = "low"

        # ── Step 8: transient flag ────────────────────────────────────────────
        is_transient = duration_s < min_duration_s

        seg = MissionSegment(
            seq             = len(segments) + 1,  # will be re-numbered
            mode_name       = mode_name.upper(),
            phase_name      = mode_name.upper(),
            duration_s      = round(duration_s, 3),
            mean_power_w    = round(mean_power_w, 3),
            min_power_w     = round(min_power_w, 3),
            max_power_w     = round(max_power_w, 3),
            power_std_w     = round(power_std_w, 3),
            n_power_samples = n_power_samples,
            energy_wh       = round(energy_wh, 6),
            delta_mah       = round(delta_mah, 3),
            mean_altitude_m = round(mean_altitude_m, 2),
            mean_speed_ms   = round(mean_speed_ms, 3),
            start_time_s    = start_time_s,
            end_time_s      = end_time_s,
            is_transient    = is_transient,
            confidence      = confidence,
            notes           = "",
        )
        segments.append(seg)

    # ── Step 9: filter pre-arm / post-land idle ───────────────────────────────
    _IDLE_MODES = {"STABILIZE", "MANUAL", "GUIDED_NOGPS"}
    filtered = list(segments)
    if (filtered
            and filtered[0].mean_power_w < 5.0
            and filtered[0].mode_name in _IDLE_MODES):
        filtered = filtered[1:]
    if (filtered
            and filtered[-1].mean_power_w < 5.0
            and filtered[-1].mode_name in _IDLE_MODES):
        filtered = filtered[:-1]

    # ── Step 10: re-number ────────────────────────────────────────────────────
    for idx, s in enumerate(filtered, start=1):
        s.seq = idx

    return filtered


# ── to_mission_phases ─────────────────────────────────────────────────────────

def to_mission_phases(
    segments:      list[MissionSegment],
    mission_id:    str,
    mission_name:  str,
    uav_id:        str,
    include_power: bool = True,
) -> list["MissionPhase"]:
    """
    Convert segments to MissionPhase objects.

    include_power=True  ("Phase + duration + estimated power"):
      power_override_w = round(segment.mean_power_w, 1)
      EXCEPT when segment.confidence == "low": set to None (unreliable).

    include_power=False ("Phase + duration only"):
      power_override_w = None for ALL phases regardless of confidence.
      The equipment model will supply power at simulation time.

    Column mapping (matches Mission_Profiles sheet / _load_missions()):
      mission_id, mission_name, uav_config_id, phase_seq, phase_name,
      phase_type, duration_s, distance_m, altitude_m, airspeed_ms,
      power_override_w, notes

    notes includes the confidence and sample count regardless of include_power.
    When include_power=False, prepend "power not imported | " to notes.
    """
    from batteries.models import MissionPhase

    phases: list[MissionPhase] = []
    for seg in segments:
        # Determine power override
        if include_power:
            if seg.confidence == "low":
                power_override_w = None
            else:
                power_override_w = round(seg.mean_power_w, 1)
        else:
            power_override_w = None

        # Build notes
        base_notes = (
            f"Extracted from log | conf:{seg.confidence} | "
            f"n={seg.n_power_samples} samples"
        )
        if seg.notes:
            base_notes += f" | {seg.notes}"
        if not include_power:
            notes = "power not imported | " + base_notes
        else:
            notes = base_notes

        phases.append(MissionPhase(
            mission_id       = mission_id,
            mission_name     = mission_name,
            uav_config_id    = uav_id,
            phase_seq        = seg.seq,
            phase_name       = seg.phase_name,
            phase_type       = seg.mode_name,
            duration_s       = seg.duration_s,
            distance_m       = 0.0,
            altitude_m       = seg.mean_altitude_m,
            airspeed_ms      = seg.mean_speed_ms,
            power_override_w = power_override_w,
            notes            = notes,
        ))
    return phases


# ── save_mission ──────────────────────────────────────────────────────────────

def save_mission(
    db:           "BatteryDatabase",
    phases:       list["MissionPhase"],
    mission_id:   str,
    mission_name: str,
    uav_id:       str,
) -> None:
    """
    Append phases to Mission_Profiles sheet.

    1. Raise ValueError(f"Mission '{mission_id}' already exists.") if present.
    2. openpyxl.load_workbook(db.path)
    3. ws.append() each phase with column order:
         mission_id, mission_name, uav_config_id, phase_seq, phase_name,
         phase_type, duration_s, distance_m, altitude_m, airspeed_ms,
         power_override_w, notes
    4. wb.save(db.path).
    5. Do NOT call reload_db().
    """
    import openpyxl

    if mission_id in db.missions:
        raise ValueError(f"Mission '{mission_id}' already exists.")

    wb = openpyxl.load_workbook(db.path)
    ws = wb["Mission_Profiles"]

    for phase in phases:
        ws.append([
            mission_id,
            mission_name,
            uav_id,
            phase.phase_seq,
            phase.phase_name,
            phase.phase_type,
            phase.duration_s,
            phase.distance_m,
            phase.altitude_m,
            phase.airspeed_ms,
            phase.power_override_w,
            phase.notes,
        ])

    wb.save(db.path)
