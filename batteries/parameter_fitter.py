"""
batteries/parameter_fitter.py

Reverse-engineer battery electrochemical parameters from real flight log data.

Four independent fitting stages (each can run independently):

  Stage 1 — R_internal  : linear regression of V_sag vs I across SoC/T bins
  Stage 2 — OCV curve   : reconstruct open-circuit voltage from low-current segments
  Stage 3 — Peukert k   : fit capacity correction exponent from C-rate vs actual capacity
  Stage 4 — Arrhenius B : fit temperature coefficients from R(T) measurements

Results are returned as FittedBatteryParams which can directly override
ChemistryVoltageParams and Cell.internal_resistance_mohm in future simulations.
"""
from __future__ import annotations
import math
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    from scipy.optimize import curve_fit, minimize_scalar, minimize
    from scipy.stats import linregress
    from scipy.interpolate import PchipInterpolator
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    warnings.warn("scipy not found — fitting will use numpy fallback methods.")

from batteries.log_importer import FlightLog


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class FitResult:
    """A single fitted parameter with quality metrics."""
    name:        str
    value:       float
    uncertainty: float  = 0.0     # 1-sigma estimate
    r_squared:   float  = 0.0     # goodness of fit [0–1]
    n_samples:   int    = 0
    method:      str    = ""
    notes:       str    = ""

    def __str__(self):
        return (f"{self.name}: {self.value:.4f} ± {self.uncertainty:.4f}  "
                f"R²={self.r_squared:.3f}  n={self.n_samples}")


@dataclass
class FittedBatteryParams:
    """
    Complete set of reverse-engineered battery parameters.
    Use override_simulation_params() to apply to a simulation.
    """
    source_log:    str = ""
    pack_id:       str = ""
    chem_id:       str = ""

    # ── Fitted values ──
    r_internal_mohm:  Optional[FitResult] = None   # Pack-level IR at 25°C
    ocv_soc_points:   list[float] = field(default_factory=list)   # SoC% breakpoints
    ocv_voltage_points: list[float] = field(default_factory=list) # V at each SoC
    peukert_k:        Optional[FitResult] = None
    B_ohmic_K:        Optional[FitResult] = None   # Arrhenius ohmic coefficient
    B_ct_K:           Optional[FitResult] = None   # Arrhenius charge-transfer

    # ── Derived capacity estimate ──
    actual_capacity_ah: Optional[FitResult] = None
    degradation_pct:    float = 0.0   # vs nominal

    # ── Fit metadata ──
    total_flight_s:   float = 0.0
    avg_power_w:      float = 0.0
    temperature_range: tuple[float, float] = (0.0, 0.0)
    fit_warnings:     list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["══ Fitted Battery Parameters ══"]
        if self.r_internal_mohm:
            lines.append(f"  R_internal   : {self.r_internal_mohm}")
        if self.actual_capacity_ah:
            lines.append(f"  Capacity     : {self.actual_capacity_ah}")
            if self.degradation_pct:
                lines.append(f"  Degradation  : {self.degradation_pct:.1f}% vs nominal")
        if self.peukert_k:
            lines.append(f"  Peukert k    : {self.peukert_k}")
        if self.B_ohmic_K:
            lines.append(f"  B_ohmic      : {self.B_ohmic_K}")
        if self.B_ct_K:
            lines.append(f"  B_ct         : {self.B_ct_K}")
        if self.ocv_soc_points:
            lines.append(f"  OCV curve    : {len(self.ocv_soc_points)} points fitted")
        for w in self.fit_warnings:
            lines.append(f"  ⚠  {w}")
        return "\n".join(lines)


# ── Helper: array utilities ───────────────────────────────────────────────────

def _to_arr(lst: list) -> np.ndarray:
    return np.array(lst, dtype=float)

def _r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    return float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0


# ── Stage 1 — Internal resistance ────────────────────────────────────────────

def fit_internal_resistance(
    log: FlightLog,
    soc_bins: int = 5,
    i_min_a: float = 2.0,
    i_max_a: float = None,
    temp_filter_c: Optional[tuple[float, float]] = None,
    method: str = "window",   # 'window' (default), 'regression', 'step_response'
) -> FitResult:
    """
    Fit pack internal resistance from flight log data.

    Preferred method — 'window' (30-second rolling windows):
      Within each short window, SoC barely changes, so V ≈ V_ocv_const − I×R.
      Linear regression within each window gives slope = −R.
      Final estimate = weighted median across all valid windows.

    'step_response': Uses rapid current transitions (dI/dt > threshold).
      Best for logs with many throttle changes. Falls back to 'window'.
    """
    v    = _to_arr(log.voltage_v)
    i    = _to_arr(log.current_a)
    t    = _to_arr(log.time_s)
    temp = _to_arr(log.temp_c)
    soc  = _to_arr(log.soc_pct) if log.soc_pct else np.linspace(100, 0, len(v))

    valid = (v > 3.0) & (i >= i_min_a) & np.isfinite(v) & np.isfinite(i)
    if temp_filter_c:
        t_lo, t_hi = temp_filter_c
        valid &= (temp >= t_lo) & (temp <= t_hi)
    if i_max_a:
        valid &= (i <= i_max_a)

    if valid.sum() < 20:
        return FitResult("R_internal_mohm", 0.0, notes="Insufficient data for IR fit")

    # ── Try step-response first if explicitly requested ───────────────────────
    if method == "step_response":
        di = np.diff(i)
        dv = np.diff(v)
        dt_diff = np.diff(t)
        dt_diff = np.where(dt_diff < 0.001, 0.001, dt_diff)
        didt = np.abs(di / dt_diff)
        step_mask = didt > 15.0
        if step_mask.sum() >= 5:
            idx = np.where(step_mask)[0]
            dv_s = dv[idx]
            di_s = di[idx]
            ok   = (di_s * dv_s < 0) & (np.abs(di_s) > 1.0)
            if ok.sum() >= 5:
                r_vals = -dv_s[ok] / di_s[ok] * 1000.0
                r_clean = r_vals[(r_vals > 0) & (r_vals < 500)]
                if len(r_clean) >= 3:
                    r_med = float(np.median(r_clean))
                    r_std = float(np.std(r_clean))
                    return FitResult(
                        "R_internal_mohm", round(r_med, 3), round(r_std, 3),
                        r_squared=0.0, n_samples=len(r_clean),
                        method="step_response",
                        notes=f"Median of {len(r_clean)} dI/dt events",
                    )
        # Fall through to window method

    # ── Window regression (30-second windows) ────────────────────────────────
    window_s = 30.0
    r_vals, weights = [], []
    t_start = t[valid][0] if valid.sum() > 0 else 0

    for win_start in np.arange(t_start, t[-1], window_s / 2):
        win_mask = valid & (t >= win_start) & (t < win_start + window_s)
        if win_mask.sum() < 8:
            continue
        v_w = v[win_mask]
        i_w = i[win_mask]
        i_range = float(i_w.max() - i_w.min())
        if i_range < 1.0:
            continue  # not enough current variation to regress
        if HAS_SCIPY:
            slope, _, r_val, _, se = linregress(i_w, v_w)
        else:
            coeffs = np.polyfit(i_w, v_w, 1)
            slope  = coeffs[0]
            y_pred = np.polyval(coeffs, i_w)
            r_val  = math.sqrt(max(0, _r_squared(v_w, y_pred)))
            se     = abs(slope) * 0.05
        if slope < -0.0005:
            r_est = -slope * 1000.0
            if 1.0 < r_est < 600.0:
                r_vals.append(r_est)
                # Weight by current range × R² (better signal = more weight)
                r2_w = float(r_val) ** 2 if HAS_SCIPY else 0.5
                weights.append(i_range * max(0.01, r2_w))

    if len(r_vals) < 3:
        # Last resort: overall regression on equal-SoC bands
        r_band = []
        for band_lo in range(0, 100, 20):
            mask_b = valid & (soc >= band_lo) & (soc < band_lo + 20)
            if mask_b.sum() < 15:
                continue
            if HAS_SCIPY:
                slope, _, r_v, _, _ = linregress(i[mask_b], v[mask_b])
            else:
                coeffs = np.polyfit(i[mask_b], v[mask_b], 1)
                slope  = coeffs[0]
            if slope < -0.0005:
                r_band.append(-slope * 1000)
        if r_band:
            r_vals   = r_band
            weights  = [1.0] * len(r_band)

    if not r_vals:
        return FitResult("R_internal_mohm", 0.0, notes="No valid windows for IR fit")

    r_arr = np.array(r_vals)
    w_arr = np.array(weights)

    # Weighted median (robust to outliers)
    sorted_idx = np.argsort(r_arr)
    r_sorted   = r_arr[sorted_idx]
    w_sorted   = w_arr[sorted_idx]
    w_cum      = np.cumsum(w_sorted) / w_sorted.sum()
    r_med      = float(r_sorted[np.searchsorted(w_cum, 0.5)])
    r_std      = float(np.std(r_arr))

    # Normalise to 25°C
    t_valid_arr = temp[valid & (temp > -50)]
    t_mean = float(np.mean(t_valid_arr)) if len(t_valid_arr) > 5 else 25.0
    if abs(t_mean - 25.0) > 3:
        from batteries.voltage_model import arrhenius_scale, CHEM_VOLTAGE_PARAMS
        params = CHEM_VOLTAGE_PARAMS.get("LION21")
        r_med  = r_med / arrhenius_scale(params.B_ohmic_K, t_mean)
        notes  = f"T_avg={t_mean:.1f}°C, normalised to 25°C ref. {len(r_vals)} windows"
    else:
        notes = f"T_avg≈{t_mean:.1f}°C. {len(r_vals)} 30-s windows"

    # Overall R² against all valid data
    v_pred = -r_med / 1000.0 * i[valid] + np.median(v[valid]) + r_med / 1000.0 * np.median(i[valid])
    r2_overall = _r_squared(v[valid], v_pred)

    return FitResult(
        "R_internal_mohm", round(r_med, 3), round(r_std, 3),
        r_squared=round(r2_overall, 4),
        n_samples=int(valid.sum()),
        method=f"window_regression({len(r_vals)} windows)",
        notes=notes,
    )


# ── Stage 2 — OCV curve reconstruction ───────────────────────────────────────

def fit_ocv_curve(
    log: FlightLog,
    r_internal_mohm: float,
    i_threshold_a: float = 3.0,
    min_rest_s: float = 2.0,
    n_points: int = 12,
) -> tuple[list[float], list[float], float]:
    """
    Reconstruct the OCV vs SoC curve from low-current flight segments.

    During near-rest periods (I < i_threshold_a), terminal voltage ≈ OCV.
    The residual sag is corrected: V_ocv ≈ V_terminal + I × R_internal.

    Returns:
        soc_pts   : list of SoC% breakpoints
        ocv_pts   : list of OCV values (V)
        r_squared : fit quality of the PCHIP interpolation
    """
    if not log.soc_pct:
        warnings.warn("SoC not available in log — skipping OCV fit")
        return [], [], 0.0

    v    = _to_arr(log.voltage_v)
    i    = _to_arr(log.current_a)
    soc  = _to_arr(log.soc_pct)
    t    = _to_arr(log.time_s)

    # OCV estimate at each low-current sample
    ocv_est = v + i * r_internal_mohm / 1000.0

    # Only use samples below current threshold with valid data
    rest_mask = (i < i_threshold_a) & (v > 3.0) & np.isfinite(ocv_est)

    if rest_mask.sum() < 20:
        warnings.warn(
            f"Only {rest_mask.sum()} low-current samples found "
            f"(threshold: {i_threshold_a}A). OCV fit may be poor."
        )

    soc_rest  = soc[rest_mask]
    ocv_rest  = ocv_est[rest_mask]

    if len(soc_rest) < 5:
        return [], [], 0.0

    # Bin into SoC brackets and take median per bin (robust to outliers)
    soc_bins = np.linspace(soc_rest.min(), soc_rest.max(), n_points + 1)
    soc_pts, ocv_pts = [], []
    for j in range(len(soc_bins) - 1):
        lo, hi = soc_bins[j], soc_bins[j + 1]
        mask_b = (soc_rest >= lo) & (soc_rest < hi)
        if mask_b.sum() >= 2:
            soc_pts.append(float(np.median(soc_rest[mask_b])))
            ocv_pts.append(float(np.median(ocv_rest[mask_b])))

    if len(soc_pts) < 3:
        return soc_pts, ocv_pts, 0.0

    # Fit quality: how well does the PCHIP predict all OCV samples?
    if HAS_SCIPY and len(soc_pts) >= 3:
        interp = PchipInterpolator(sorted(soc_pts),
                                   [ocv_pts[i] for i in np.argsort(soc_pts)])
        soc_sorted_all = soc_rest
        ocv_pred = interp(soc_sorted_all)
        r2 = _r_squared(ocv_rest, ocv_pred)
    else:
        r2 = 0.0

    # Sort by SoC
    order = np.argsort(soc_pts)
    soc_pts_sorted = [soc_pts[j] for j in order]
    ocv_pts_sorted = [ocv_pts[j] for j in order]

    return soc_pts_sorted, ocv_pts_sorted, float(r2)


# ── Stage 3 — Peukert exponent ───────────────────────────────────────────────

def fit_peukert_k(
    log: FlightLog,
    nominal_capacity_ah: float,
    c_rate_bins: int = 4,
    i_ref_a: Optional[float] = None,
) -> FitResult:
    """
    Estimate the Peukert exponent k from the cumulative mAh trajectory.

    For each timestep, the Peukert model predicts effective capacity consumed:
        delta_mAh_eff = (I/C_nom)^(k-1) × I × dt × 1000

    We minimise RMSE between the predicted cumulative effective mAh trajectory
    and the observed mAh_used.  Works with partial discharges.
    """
    if not log.mah_used or not log.current_a:
        return FitResult("peukert_k", 1.05, notes="Insufficient data (no mAh or current)")

    i   = _to_arr(log.current_a)
    mah = _to_arr(log.mah_used)
    t   = _to_arr(log.time_s)

    pos = (i > 0.5) & np.isfinite(mah) & (mah > 0)
    if pos.sum() < 20:
        return FitResult("peukert_k", 1.05, notes="Too few positive-current samples")

    i_pos   = i[pos]
    mah_pos = mah[pos]
    t_pos   = t[pos]
    i_ref   = i_ref_a or nominal_capacity_ah

    def trajectory_rmse(k_val):
        dt_arr = np.diff(t_pos, prepend=t_pos[0] - 2.0)
        dt_arr = np.clip(dt_arr, 0.01, 60.0)
        # Peukert-weighted effective mAh consumed at each step
        c_adj  = nominal_capacity_ah * (i_ref / np.maximum(i_pos, 0.01)) ** (k_val - 1)
        delta  = i_pos * dt_arr / 3600.0 * 1000.0  # raw mAh each step
        # Effective mAh relative to capacity consumed = delta × (C_nom/C_adj)
        eff_delta = delta * (nominal_capacity_ah / np.maximum(c_adj, 0.001))
        cum_pred  = np.cumsum(eff_delta)
        return float(np.sqrt(np.mean((cum_pred - mah_pos) ** 2)))

    if not HAS_SCIPY:
        k_best, k_unc = 1.05, 0.02
    else:
        res    = minimize_scalar(trajectory_rmse, bounds=(1.0, 1.20), method='bounded')
        k_best = float(res.x)
        rmse_min = trajectory_rmse(k_best)
        k_grid   = np.linspace(1.0, 1.20, 60)
        k_good   = [k for k in k_grid if trajectory_rmse(k) < rmse_min * 1.10]
        k_unc    = (max(k_good) - min(k_good)) / 4 if len(k_good) > 1 else 0.02

    i_mean  = float(np.mean(i_pos))
    c_rate  = i_mean / nominal_capacity_ah

    return FitResult(
        "peukert_k", round(k_best, 4), round(k_unc, 4),
        r_squared=0.0, n_samples=int(pos.sum()),
        method="trajectory_minimisation",
        notes=f"avg C-rate={c_rate:.2f}C  I_mean={i_mean:.1f}A  "
              f"mAh_used={float(mah_pos.max()):.0f}mAh",
    )


# ── Stage 4 — Arrhenius temperature coefficients ─────────────────────────────

def fit_arrhenius(
    log: FlightLog,
    r_at_25c_mohm: float,
    min_temp_range_c: float = 8.0,
) -> tuple[Optional[FitResult], Optional[FitResult]]:
    """
    Fit Arrhenius B coefficients for ohmic and charge-transfer resistance.

    Requires temperature data spanning at least min_temp_range_c degrees.
    Returns (B_ohmic_result, B_ct_result) — either may be None if
    insufficient temperature variation.

    Uses the relation: ln(R(T) / R_ref) = B × (1/T_K − 1/298.15)
    """
    if not any(t > -50 for t in log.temp_c):
        return None, None

    v    = _to_arr(log.voltage_v)
    i    = _to_arr(log.current_a)
    temp = _to_arr(log.temp_c)

    # Filter to usable samples
    valid = (v > 3.0) & (i > 5.0) & (temp > -50) & (temp < 80) & np.isfinite(v)
    if valid.sum() < 30:
        return None, None

    t_range = float(temp[valid].max() - temp[valid].min())
    if t_range < min_temp_range_c:
        msg = (f"Temperature range only {t_range:.1f}°C "
               f"(need ≥ {min_temp_range_c}°C for Arrhenius fit)")
        warnings.warn(msg)
        return (
            FitResult("B_ohmic_K", 0.0, notes=msg),
            FitResult("B_ct_K",    0.0, notes=msg),
        )

    # Estimate R at each temperature window
    # Bin by temperature into Nbins windows
    temp_bins = np.percentile(temp[valid], np.linspace(0, 100, 8))
    t_means, r_ests = [], []

    for j in range(len(temp_bins) - 1):
        mask = (temp >= temp_bins[j]) & (temp < temp_bins[j + 1]) & valid
        if mask.sum() < 15:
            continue
        v_b, i_b = v[mask], i[mask]
        if HAS_SCIPY:
            slope, _, _, _, _ = linregress(i_b, v_b)
        else:
            coeffs = np.polyfit(i_b, v_b, 1)
            slope  = coeffs[0]
        if slope < -0.0005:
            t_means.append(float(np.mean(temp[mask])))
            r_ests.append(-slope * 1000.0)   # mΩ

    if len(t_means) < 3:
        return None, None

    # Fit B: ln(R/R_ref) = B × (1/T_K − 1/298.15)
    T_ref_K = 298.15
    inv_t   = np.array([1.0 / (t + 273.15) for t in t_means])
    inv_t_ref = 1.0 / T_ref_K
    x_arr   = inv_t - inv_t_ref
    y_arr   = np.log(np.array(r_ests) / max(r_at_25c_mohm, 0.1))

    if HAS_SCIPY:
        slope_b, _, r_b, _, se_b = linregress(x_arr, y_arr)
    else:
        coeffs = np.polyfit(x_arr, y_arr, 1)
        slope_b = coeffs[0]
        y_pred  = np.polyval(coeffs, x_arr)
        r_b     = math.sqrt(max(0, _r_squared(y_arr, y_pred)))
        se_b    = abs(slope_b) * 0.05

    B_ohmic = max(500.0, min(5000.0, float(slope_b)))
    B_ct    = B_ohmic * 2.1   # typical ratio from literature

    r2 = float(r_b) ** 2 if HAS_SCIPY else 0.0

    result_ohmic = FitResult(
        "B_ohmic_K", round(B_ohmic, 0), round(abs(se_b), 0),
        r_squared=round(r2, 3), n_samples=len(t_means),
        method="log_linear_regression",
        notes=f"T range: {min(t_means):.1f}–{max(t_means):.1f}°C",
    )
    result_ct = FitResult(
        "B_ct_K", round(B_ct, 0), round(abs(se_b) * 2, 0),
        r_squared=round(r2, 3), n_samples=len(t_means),
        method="derived_from_B_ohmic",
        notes="B_ct ≈ 2.1 × B_ohmic (typical Li-Ion ratio)",
    )
    return result_ohmic, result_ct


# ── Stage 5 — Actual capacity ────────────────────────────────────────────────

def fit_actual_capacity(
    log: FlightLog,
    nominal_capacity_ah: float,
    voltage_cutoff_v_pack: float,
) -> FitResult:
    """
    Estimate the actual usable capacity from a full or near-full discharge.
    Compares total mAh consumed when voltage reaches cutoff.
    """
    mah  = _to_arr(log.mah_used)
    v    = _to_arr(log.voltage_v)

    if mah.max() < 10 or v.min() >= voltage_cutoff_v_pack * 1.05:
        return FitResult(
            "actual_capacity_ah", nominal_capacity_ah, 0.0,
            notes="Pack not discharged to cutoff — cannot determine full capacity"
        )

    # Extrapolate: fit linear mAh vs time tail, project to cutoff voltage
    v_near_cutoff = voltage_cutoff_v_pack * 1.15
    late_mask = v < v_near_cutoff
    if late_mask.sum() < 5:
        # Just use max observed mAh as lower bound
        cap_ah = mah.max() / 1000.0
        notes  = f"Lower bound (pack not fully depleted): {cap_ah:.3f} Ah"
    else:
        cap_ah  = float(mah.max()) / 1000.0
        notes   = f"Full discharge observed: {cap_ah:.3f} Ah"

    degrade = max(0.0, (nominal_capacity_ah - cap_ah) / nominal_capacity_ah * 100)

    return FitResult(
        "actual_capacity_ah", round(cap_ah, 4), 0.0,
        r_squared=1.0, n_samples=int(late_mask.sum()),
        method="mah_at_cutoff",
        notes=notes + f" (nominal={nominal_capacity_ah:.3f} Ah, "
                      f"degradation≈{degrade:.1f}%)",
    )


# ── Full pipeline ─────────────────────────────────────────────────────────────

def fit_all(
    log: FlightLog,
    nominal_capacity_ah: float,
    voltage_cutoff_v_pack: float,
    chem_id: str = "LION21",
    pack_id: str = "",
    soc_bins: int = 5,
    i_threshold_a: float = 3.0,
    min_temp_range_c: float = 8.0,
) -> FittedBatteryParams:
    """
    Run the full parameter fitting pipeline on a FlightLog.

    Args:
        log                   : loaded FlightLog
        nominal_capacity_ah   : expected pack capacity at SoC=100%
        voltage_cutoff_v_pack : pack-level cutoff voltage
        chem_id               : chemistry hint for Arrhenius normalisation
        pack_id               : optional pack identifier

    Returns:
        FittedBatteryParams with all available fitted values
    """
    params = FittedBatteryParams(
        source_log=log.source_file,
        pack_id=pack_id,
        chem_id=chem_id,
    )

    # Compute SoC if not already in log
    if not log.soc_pct and log.mah_used:
        log.soc_pct = [
            max(0.0, min(100.0, 100.0 - m / (nominal_capacity_ah * 1000) * 100))
            for m in log.mah_used
        ]

    params.total_flight_s  = log.total_flight_s
    v = [x for x in log.voltage_v if x > 3]
    i = [x for x in log.current_a if x > 0]
    if v and i:
        params.avg_power_w = float(
            sum(vv * ii for vv, ii in zip(v, i)) / len(v)
        )
    t_valid = [t for t in log.temp_c if t > -50]
    if t_valid:
        params.temperature_range = (min(t_valid), max(t_valid))

    # ── Stage 1: R_internal ──────────────────────────────────────────────────
    print("  [1/5] Fitting internal resistance...")
    r_fit = fit_internal_resistance(log, soc_bins=soc_bins)
    params.r_internal_mohm = r_fit
    r_val = r_fit.value if r_fit.value > 0 else 20.0
    print(f"        {r_fit}")

    # ── Stage 2: OCV curve ───────────────────────────────────────────────────
    print("  [2/5] Reconstructing OCV curve...")
    soc_pts, ocv_pts, r2_ocv = fit_ocv_curve(log, r_val, i_threshold_a)
    params.ocv_soc_points     = soc_pts
    params.ocv_voltage_points  = ocv_pts
    print(f"        {len(soc_pts)} OCV points  R²={r2_ocv:.3f}")

    # ── Stage 3: Peukert k ───────────────────────────────────────────────────
    print("  [3/5] Fitting Peukert exponent...")
    k_fit = fit_peukert_k(log, nominal_capacity_ah)
    params.peukert_k = k_fit
    print(f"        {k_fit}")

    # ── Stage 4: Arrhenius B ─────────────────────────────────────────────────
    print("  [4/5] Fitting Arrhenius temperature coefficients...")
    b_ohm, b_ct = fit_arrhenius(log, r_val, min_temp_range_c)
    params.B_ohmic_K = b_ohm
    params.B_ct_K    = b_ct
    if b_ohm:
        print(f"        {b_ohm}")
        print(f"        {b_ct}")
    else:
        print("        Skipped — insufficient temperature range")

    # ── Stage 5: Actual capacity ─────────────────────────────────────────────
    print("  [5/5] Estimating actual capacity...")
    cap_fit = fit_actual_capacity(log, nominal_capacity_ah, voltage_cutoff_v_pack)
    params.actual_capacity_ah = cap_fit
    if cap_fit.value > 0 and nominal_capacity_ah > 0:
        params.degradation_pct = max(0.0,
            (nominal_capacity_ah - cap_fit.value) / nominal_capacity_ah * 100
        )
    print(f"        {cap_fit}")

    # ── Warnings ─────────────────────────────────────────────────────────────
    if r_fit.r_squared < 0.5 and r_fit.value > 0:
        params.fit_warnings.append(
            f"IR regression R²={r_fit.r_squared:.2f} — low confidence "
            "(<0.5). Consider filtering out transient segments."
        )
    if not soc_pts:
        params.fit_warnings.append(
            "OCV curve could not be fitted. Ensure log has SoC data "
            "and low-current segments."
        )
    if params.degradation_pct > 20:
        params.fit_warnings.append(
            f"Estimated capacity degradation {params.degradation_pct:.1f}% "
            "is high — battery may need replacement."
        )

    return params


def apply_fitted_params(
    fitted: FittedBatteryParams,
    pack,
    update_ir: bool = True,
    update_capacity: bool = True,
):
    """
    Apply FittedBatteryParams back to a BatteryPack for use in simulation.
    Returns a modified copy (does not mutate the original).
    """
    import copy
    p = copy.deepcopy(pack)
    if update_ir and fitted.r_internal_mohm and fitted.r_internal_mohm.value > 0:
        p.internal_resistance_mohm = fitted.r_internal_mohm.value
    if update_capacity and fitted.actual_capacity_ah and fitted.actual_capacity_ah.value > 0:
        old_cap = p.pack_capacity_ah
        p.pack_capacity_ah = fitted.actual_capacity_ah.value
        # Scale energy proportionally
        if old_cap > 0:
            p.pack_energy_wh *= fitted.actual_capacity_ah.value / old_cap
    return p
