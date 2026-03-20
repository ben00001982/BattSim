"""
batteries/discharge.py
Battery discharge models:
  1. Peukert equation
  2. Temperature derating
  3. PCHIP empirical curve interpolation from Discharge_Profiles data
"""
from __future__ import annotations
import math
from batteries.models import BatteryPack, DischargePoint

try:
    from scipy.interpolate import PchipInterpolator
    import numpy as np
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


# ── 1. Peukert Model ──────────────────────────────────────────────────────────

def peukert_capacity(
    nominal_capacity_ah: float,
    discharge_current_a: float,
    peukert_k: float = 1.05,
    reference_hours: float = 1.0,
) -> float:
    """
    Adjusted discharge capacity using Peukert's law.

    C_actual = C_nominal × (I_1h / I_actual)^(k-1)

    Args:
        nominal_capacity_ah: Rated capacity at 1h rate
        discharge_current_a: Actual discharge current
        peukert_k:           Peukert exponent (Li-Ion ~1.03–1.08, LFP ~1.02–1.05)
        reference_hours:     Hours basis for nominal rating (default 1h)

    Returns:
        Adjusted capacity (Ah)
    """
    if discharge_current_a <= 0:
        return nominal_capacity_ah
    i_ref = nominal_capacity_ah / reference_hours
    return nominal_capacity_ah * (i_ref / discharge_current_a) ** (peukert_k - 1)


def peukert_runtime(
    nominal_capacity_ah: float,
    discharge_current_a: float,
    peukert_k: float = 1.05,
) -> float:
    """
    Predicted discharge runtime (hours).

    t = (C_nominal / I)^k  ×  (C_nominal / I)^(1-k) ... simplified:
    t = C_adj / I

    Returns:
        Runtime in hours
    """
    c_adj = peukert_capacity(nominal_capacity_ah, discharge_current_a, peukert_k)
    return c_adj / discharge_current_a if discharge_current_a > 0 else float("inf")


# ── 2. Temperature Derating ───────────────────────────────────────────────────

# Approximate capacity derating factors relative to 25°C.
# Based on typical Li-Ion/LiPo behaviour.
_TEMP_DERATE_LIPO = {
    -20: 0.60, -10: 0.72, 0: 0.83, 10: 0.91,
    20:  0.97,  25: 1.00, 30: 1.00, 40: 0.98,
    50:  0.95,  60: 0.90,
}
_TEMP_DERATE_LFP = {
    -20: 0.50, -10: 0.65, 0: 0.80, 10: 0.92,
    20:  0.98,  25: 1.00, 30: 1.00, 40: 0.98,
    50:  0.94,  60: 0.87,
}
_TEMP_DERATE_LION = {
    -20: 0.65, -10: 0.75, 0: 0.85, 10: 0.93,
    20:  0.98,  25: 1.00, 30: 1.00, 40: 0.97,
    50:  0.93,  60: 0.87,
}

_CHEM_TEMP_MAP = {
    "LIPO": _TEMP_DERATE_LIPO, "LIHV": _TEMP_DERATE_LIPO,
    "LION": _TEMP_DERATE_LION, "LION21": _TEMP_DERATE_LION,
    "LIFEPO4": _TEMP_DERATE_LFP,
    "SSS": _TEMP_DERATE_LION, "SOLID": _TEMP_DERATE_LION,
    "NIMH": _TEMP_DERATE_LIPO, "LITO": _TEMP_DERATE_LION,
}


def temperature_derate_factor(chem_id: str, temp_c: float) -> float:
    """
    Return the capacity derating factor [0–1] for a given temperature.
    Uses linear interpolation between known table points.
    """
    table = _CHEM_TEMP_MAP.get(chem_id.upper(), _TEMP_DERATE_LION)
    temps = sorted(table.keys())

    if temp_c <= temps[0]:
        return table[temps[0]]
    if temp_c >= temps[-1]:
        return table[temps[-1]]

    for i in range(len(temps) - 1):
        t_lo, t_hi = temps[i], temps[i + 1]
        if t_lo <= temp_c <= t_hi:
            frac = (temp_c - t_lo) / (t_hi - t_lo)
            return table[t_lo] + frac * (table[t_hi] - table[t_lo])
    return 1.0


def derated_capacity(
    nominal_capacity_ah: float,
    chem_id: str,
    temp_c: float,
    discharge_current_a: float,
    peukert_k: float = 1.05,
) -> float:
    """
    Capacity adjusted for both temperature derating AND Peukert effect.
    """
    t_factor = temperature_derate_factor(chem_id, temp_c)
    c_temp = nominal_capacity_ah * t_factor
    return peukert_capacity(c_temp, discharge_current_a, peukert_k)


# ── 3. PCHIP Empirical Curve Interpolation ────────────────────────────────────

class DischargeCurve:
    """
    Voltage vs SoC discharge curve built from Discharge_Profiles data.
    Uses PCHIP (Piecewise Cubic Hermite Interpolating Polynomial)
    for smooth, monotone interpolation — no spurious oscillations.
    Falls back to linear interpolation if scipy is unavailable.
    """

    def __init__(
        self,
        discharge_points: list[DischargePoint],
        chem_id: str,
        c_rate: float,
        temp_c: float = 25.0,
    ):
        self.chem_id = chem_id
        self.c_rate  = c_rate
        self.temp_c  = temp_c

        pts = [p for p in discharge_points
               if p.chem_id == chem_id
               and abs(p.c_rate - c_rate) < 0.01
               and abs(p.temperature_c - temp_c) < 1.0]

        if not pts:
            raise ValueError(
                f"No discharge data for chem={chem_id} C-rate={c_rate} T={temp_c}°C"
            )

        pts_sorted = sorted(pts, key=lambda p: p.soc_pct)
        self._soc = [p.soc_pct  for p in pts_sorted]
        self._v   = [p.voltage_v for p in pts_sorted]

        self._interp = None
        if HAS_SCIPY:
            self._interp = PchipInterpolator(self._soc, self._v)

    def voltage_at_soc(self, soc_pct: float) -> float:
        """Return interpolated voltage at a given SoC%."""
        soc_pct = max(self._soc[0], min(self._soc[-1], soc_pct))
        if self._interp is not None:
            return float(self._interp(soc_pct))
        return self._linear_interp(soc_pct)

    def _linear_interp(self, soc_pct: float) -> float:
        soc_pct = max(self._soc[0], min(self._soc[-1], soc_pct))
        for i in range(len(self._soc) - 1):
            if self._soc[i] <= soc_pct <= self._soc[i + 1]:
                frac = (soc_pct - self._soc[i]) / (self._soc[i+1] - self._soc[i])
                return self._v[i] + frac * (self._v[i+1] - self._v[i])
        return self._v[-1]

    def soc_array(self, n: int = 101) -> list[float]:
        lo, hi = self._soc[0], self._soc[-1]
        step = (hi - lo) / (n - 1) if n > 1 else 0
        return [lo + i * step for i in range(n)]

    def voltage_array(self, n: int = 101) -> list[float]:
        return [self.voltage_at_soc(s) for s in self.soc_array(n)]

    def voltage_array_for_pack(self, pack: BatteryPack, n: int = 101) -> list[float]:
        """Scale cell voltage curve to pack voltage (×series)."""
        return [v * pack.cells_series for v in self.voltage_array(n)]


# ── 4. Closest C-rate selector ────────────────────────────────────────────────

def closest_c_rate(available_c_rates: list[float], target_c: float) -> float:
    """Return the closest available C-rate to target."""
    return min(available_c_rates, key=lambda c: abs(c - target_c))


def available_c_rates(
    discharge_points: list[DischargePoint], chem_id: str
) -> list[float]:
    """Return sorted list of available C-rates for a chemistry."""
    rates = {p.c_rate for p in discharge_points if p.chem_id == chem_id}
    return sorted(rates)


# ── 5. SoC step simulation ────────────────────────────────────────────────────

def simulate_discharge_step(
    soc_pct: float,
    power_w: float,
    pack: BatteryPack,
    curve: DischargeCurve,
    dt_s: float = 1.0,
    temp_c: float = 25.0,
    peukert_k: float = 1.05,
    cutoff_soc_pct: float = 10.0,
) -> tuple[float, float, float, bool]:
    """
    Advance one timestep of the discharge simulation.

    Returns:
        (new_soc_pct, terminal_voltage_v, current_a, is_depleted)
    """
    if soc_pct <= cutoff_soc_pct:
        v = curve.voltage_at_soc(cutoff_soc_pct) * pack.cells_series
        return soc_pct, v, 0.0, True

    v_terminal = curve.voltage_at_soc(soc_pct) * pack.cells_series
    current_a  = power_w / v_terminal if v_terminal > 0 else 0.0

    # Capacity adjusted for temperature and Peukert
    t_factor   = temperature_derate_factor(pack.chemistry_id, temp_c)
    cap_adj    = peukert_capacity(
        pack.pack_capacity_ah * t_factor, current_a, peukert_k
    )

    # SoC decrement: ΔSoC = (I × dt_s / 3600) / C_adj × 100%
    delta_soc  = (current_a * dt_s / 3600) / cap_adj * 100.0 if cap_adj > 0 else 0
    new_soc    = max(cutoff_soc_pct, soc_pct - delta_soc)

    depleted   = new_soc <= cutoff_soc_pct
    return new_soc, v_terminal, current_a, depleted
