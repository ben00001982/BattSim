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

    # ── 2RC ECM (Phase 2) ──
    ecm_params:      Optional["ECMParameters"] = None
    ecm_diagnostics: dict = field(default_factory=dict)

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

def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    """Return weighted median of values."""
    order    = np.argsort(values)
    w_sorted = weights[order]
    w_cum    = np.cumsum(w_sorted) / w_sorted.sum()
    return float(values[order][np.searchsorted(w_cum, 0.5)])


def _sag_r2(v: np.ndarray, i: np.ndarray, soc: np.ndarray, r_mohm: float) -> float:
    """
    Compute R² of the IR sag model in the *sag domain*.

    Classic R² on raw terminal voltage is always poor because OCV drift
    (due to SoC change over the flight) dominates the variance and has
    nothing to do with IR fit quality.

    Instead we:
      1. Estimate V_ocv at every sample by fitting a smooth polynomial
         of (V_terminal + I*R) vs SoC — this removes OCV variation.
      2. Compute measured sag:  V_sag_meas = V_ocv_smooth − V_terminal
      3. Compute predicted sag: V_sag_pred = I × R / 1000
      4. Return R²(V_sag_meas, V_sag_pred).
    """
    if soc is None or len(soc) != len(v):
        return 0.0
    soc_range = float(soc.max() - soc.min())
    if soc_range < 5.0:
        return 0.0
    v_ocv_est = v + i * r_mohm / 1000.0
    try:
        deg = min(4, max(1, int(soc_range / 15)))
        coeffs    = np.polyfit(soc, v_ocv_est, deg)
        v_ocv_fit = np.polyval(coeffs, soc)
    except Exception:
        return 0.0
    v_sag_meas = v_ocv_fit - v
    v_sag_pred = i * r_mohm / 1000.0
    valid = v_sag_meas > 0.001
    if valid.sum() < 10:
        return 0.0
    return _r_squared(v_sag_meas[valid], v_sag_pred[valid])


def _delta_vi_estimates(v: np.ndarray, i: np.ndarray, t: np.ndarray,
                         valid: np.ndarray, min_di: float = 3.0,
                         max_dt: float = 4.0) -> np.ndarray:
    """
    ΔV/ΔI method: for consecutive sample pairs where current changes rapidly,
    OCV barely changes so ΔV ≈ −R × ΔI.  Much less sensitive to OCV drift
    than whole-flight regression.
    """
    r_vals = []
    idxs = np.where(valid)[0]
    for k in range(len(idxs) - 1):
        a, b = idxs[k], idxs[k + 1]
        if t[b] - t[a] > max_dt:
            continue
        di = float(i[b] - i[a])
        dv = float(v[b] - v[a])
        if abs(di) < min_di:
            continue
        if di * dv >= 0:          # must be opposing (more I → less V)
            continue
        r = -dv / di * 1000.0
        if 1.0 < r < 600.0:
            r_vals.append(r)
    return np.array(r_vals) if r_vals else np.array([])


def _detrended_window_estimates(v: np.ndarray, i: np.ndarray, t: np.ndarray,
                                 valid: np.ndarray,
                                 window_s: float = 5.0) -> tuple[np.ndarray, np.ndarray]:
    """
    Improved window regression: remove the linear OCV drift within each
    short window before regressing V against I.  The residual V after
    detrending is dominated by R×I, not by OCV(SoC).
    """
    r_vals, weights = [], []
    t_starts = np.arange(t[valid][0], t[valid][-1], window_s / 2) if valid.sum() > 0 else []
    for win_start in t_starts:
        win = valid & (t >= win_start) & (t < win_start + window_s)
        if win.sum() < 8:
            continue
        v_w = v[win]; i_w = i[win]; t_w = t[win]
        if i_w.max() - i_w.min() < 1.0:
            continue
        # Remove linear OCV trend within window (V drift due to SoC depletion)
        t_c = t_w - t_w.mean()
        try:
            trend = np.polyfit(t_c, v_w, 1)
        except Exception:
            continue
        v_detrended = v_w - np.polyval(trend, t_c)
        i_centered  = i_w - i_w.mean()
        if i_centered.max() - i_centered.min() < 0.5:
            continue
        try:
            coeffs = np.polyfit(i_centered, v_detrended, 1)
        except Exception:
            continue
        slope = coeffs[0]
        if slope >= -0.0005:
            continue
        r_est = -slope * 1000.0
        if not (1.0 < r_est < 600.0):
            continue
        y_pred = np.polyval(coeffs, i_centered)
        r2_win = _r_squared(v_detrended, y_pred)
        if r2_win <= 0:
            continue
        r_vals.append(r_est)
        weights.append((i_w.max() - i_w.min()) * r2_win)
    if not r_vals:
        return np.array([]), np.array([])
    return np.array(r_vals), np.array(weights)


def fit_internal_resistance(
    log: FlightLog,
    soc_bins: int = 5,
    i_min_a: float = 2.0,
    i_max_a: float = None,
    temp_filter_c: Optional[tuple[float, float]] = None,
    method: str = "auto",   # 'auto' (default), 'delta_vi', 'detrended_window', 'window', 'step_response'
) -> FitResult:
    """
    Fit pack internal resistance from flight log data.

    method='auto' (default): Tries three methods and selects the one with
      the highest sag-domain R² (see _sag_r2).  Reports which was chosen.

    method='delta_vi': ΔV/ΔI on consecutive sample pairs where current
      changes significantly.  Immune to OCV drift — best when the log has
      frequent throttle steps.

    method='detrended_window': 15-second windows with OCV drift removed by
      linear detrending before V–I regression.  Better than raw 'window'.

    method='window': Original 30-second rolling window regression (legacy).

    method='step_response': Explicit dI/dt threshold detection (legacy).

    R² is computed in the *sag domain* (V_sag_pred vs V_sag_meas) rather
    than on raw terminal voltage, so it reflects actual fit quality rather
    than being dominated by OCV variation across the flight.
    """
    v    = _to_arr(log.voltage_v)
    i    = _to_arr(log.current_a)
    t    = _to_arr(log.time_s)
    temp = _to_arr(log.temp_c)
    soc  = _to_arr(log.soc_pct) if log.soc_pct else None

    valid = (v > 3.0) & (i >= i_min_a) & np.isfinite(v) & np.isfinite(i)
    if temp_filter_c:
        t_lo, t_hi = temp_filter_c
        valid &= (temp >= t_lo) & (temp <= t_hi)
    if i_max_a:
        valid &= (i <= i_max_a)

    if valid.sum() < 20:
        return FitResult("R_internal_mohm", 0.0, notes="Insufficient data for IR fit")

    # Temperature info for normalisation note
    t_valid_arr = temp[valid & (temp > -50)]
    t_mean = float(np.mean(t_valid_arr)) if len(t_valid_arr) > 5 else 25.0

    def _normalise_to_25c(r_mohm: float) -> float:
        if abs(t_mean - 25.0) > 3:
            from batteries.voltage_model import arrhenius_scale, CHEM_VOLTAGE_PARAMS
            params = CHEM_VOLTAGE_PARAMS.get("LION21")
            return r_mohm / arrhenius_scale(params.B_ohmic_K, t_mean)
        return r_mohm

    candidates = {}  # method_name → (r_med, r_std, n, sag_r2, note)

    # ── Method 1: ΔV/ΔI on current steps ─────────────────────────────────────
    if method in ("auto", "delta_vi"):
        r_dv = _delta_vi_estimates(v, i, t, valid, min_di=3.0, max_dt=4.0)
        if len(r_dv) >= 5:
            r_med = float(np.median(r_dv))
            r_med = _normalise_to_25c(r_med)
            r2    = _sag_r2(v[valid], i[valid],
                            soc[valid] if soc is not None else None, r_med)
            candidates["delta_vi"] = (
                r_med, float(np.std(r_dv)), len(r_dv), r2,
                f"ΔV/ΔI on {len(r_dv)} current steps, T_avg={t_mean:.1f}°C"
            )

    # ── Method 2: Detrended window regression ─────────────────────────────────
    if method in ("auto", "detrended_window"):
        # Adaptive window: target ~15 samples per window
        _dt_arr = np.diff(t[valid]) if valid.sum() > 1 else np.array([1.0])
        _dt_med = float(np.median(_dt_arr)) if len(_dt_arr) > 0 else 1.0
        _window_s = max(5.0, min(60.0, 15.0 * _dt_med))
        r_dw, w_dw = _detrended_window_estimates(v, i, t, valid, window_s=_window_s)
        if len(r_dw) >= 3:
            r_med = _weighted_median(r_dw, w_dw)
            r_med = _normalise_to_25c(r_med)
            r2    = _sag_r2(v[valid], i[valid],
                            soc[valid] if soc is not None else None, r_med)
            candidates["detrended_window"] = (
                r_med, float(np.std(r_dw)), len(r_dw), r2,
                f"{len(r_dw)} detrended 15-s windows, T_avg={t_mean:.1f}°C"
            )

    # ── Method 3: Original 5-s window regression (fallback) ───────────────────
    if method in ("auto", "window", "step_response") or not candidates:
        window_s = 5.0
        r_vals, weights = [], []
        t_start = t[valid][0] if valid.sum() > 0 else 0
        for win_start in np.arange(t_start, t[-1], window_s / 2):
            win_mask = valid & (t >= win_start) & (t < win_start + window_s)
            if win_mask.sum() < 8:
                continue
            v_w = v[win_mask]; i_w = i[win_mask]
            i_range = float(i_w.max() - i_w.min())
            if i_range < 1.0:
                continue
            if HAS_SCIPY:
                slope, _, r_val, _, _ = linregress(i_w, v_w)
                r2_w = float(r_val) ** 2
            else:
                coeffs = np.polyfit(i_w, v_w, 1)
                slope  = coeffs[0]
                r2_w   = max(0.01, _r_squared(v_w, np.polyval(coeffs, i_w)))
            if slope < -0.0005:
                r_est = -slope * 1000.0
                if 1.0 < r_est < 600.0:
                    r_vals.append(r_est)
                    weights.append(i_range * max(0.01, r2_w))

        if len(r_vals) < 3:
            # SoC-band fallback
            soc_proxy = soc if soc is not None else np.linspace(100, 0, len(v))
            for band_lo in range(0, 100, 20):
                mask_b = valid & (soc_proxy >= band_lo) & (soc_proxy < band_lo + 20)
                if mask_b.sum() < 15:
                    continue
                coeffs = np.polyfit(i[mask_b], v[mask_b], 1)
                if coeffs[0] < -0.0005:
                    r_vals.append(-coeffs[0] * 1000)
                    weights.append(1.0)

        if r_vals:
            r_arr = np.array(r_vals); w_arr = np.array(weights)
            r_med = _weighted_median(r_arr, w_arr)
            r_med = _normalise_to_25c(r_med)
            r2    = _sag_r2(v[valid], i[valid],
                            soc[valid] if soc is not None else None, r_med)
            candidates["window"] = (
                r_med, float(np.std(r_arr)), len(r_vals), r2,
                f"{len(r_vals)} 30-s windows, T_avg={t_mean:.1f}°C"
            )

    if not candidates:
        return FitResult("R_internal_mohm", 0.0, notes="No valid windows for IR fit")

    # ── Select best candidate by sag R² ───────────────────────────────────────
    best_method = max(candidates, key=lambda k: candidates[k][3])
    r_med, r_std, n_used, r2_sag, note = candidates[best_method]

    if method == "auto" and len(candidates) > 1:
        r2_summary = "  ".join(f"{m}:R²={v[3]:.3f}" for m, v in candidates.items())
        note += f"  [auto selected {best_method} — {r2_summary}]"

    return FitResult(
        "R_internal_mohm", round(r_med, 3), round(r_std, 3),
        r_squared=round(r2_sag, 4),
        n_samples=int(valid.sum()),
        method=best_method,
        notes=note,
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

    # ── Stage 6: 2RC ECM parameters ──────────────────────────────────────────
    print("  [6/6] Fitting 2RC ECM parameters...")
    try:
        from batteries.voltage_model import ECMParameters
        # Build a minimal pack proxy for build_ecm_parameters_from_log
        class _PackProxy:
            internal_resistance_mohm = r_val
        ecm, fit_summary, _diag = build_ecm_parameters_from_log(log, _PackProxy(), chem_id)
        params.ecm_params = ecm
        params.ecm_diagnostics = fit_summary
        print(f"        R0={fit_summary.get('R0_mohm', 0):.2f} mO  "
              f"R1={fit_summary.get('R1_mohm', 0):.2f} mO  "
              f"R2={fit_summary.get('R2_mohm', 0):.2f} mO")
        print(f"        t1={fit_summary.get('tau1_s', 0):.1f} s  "
              f"t2={fit_summary.get('tau2_s', 0):.1f} s")
    except Exception as _ecm_err:
        params.fit_warnings.append(f"ECM fitting failed: {_ecm_err}")
        print(f"        ECM fit failed: {_ecm_err}")

    print("Phase 2 complete.")

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
    # ECM params are attached but not mutated (they reference the pack-level R)
    if hasattr(fitted, "ecm_params") and fitted.ecm_params is not None:
        p._ecm_params = fitted.ecm_params
    return p


# ── ECM fitting helpers ────────────────────────────────────────────────────────

def fit_R0_from_steps(
    log: "FlightLog",
    min_di_a: float = 5.0,
    max_dt_s: float = 0.5,
    r_bounds: tuple[float, float] = (0.5, 600.0),
) -> FitResult:
    """
    Estimate R0 (pure ohmic resistance) from instantaneous current steps.

    At dt < 0.5 s, only the ohmic branch responds (RC branches haven't
    charged yet), so ΔV/ΔI ≈ R0.  With 1 Hz logs this gives combined
    R0+RC1 at the first sample, which is the best achievable estimate.

    Returns R0 in mΩ.
    """
    v = _to_arr(log.voltage_v)
    i = _to_arr(log.current_a)
    t = _to_arr(log.time_s)

    r_vals = []
    for k in range(len(t) - 1):
        dt = float(t[k + 1] - t[k])
        if dt > max_dt_s or dt <= 0:
            continue
        di = float(i[k + 1] - i[k])
        dv = float(v[k + 1] - v[k])
        if abs(di) < min_di_a:
            continue
        if di * dv >= 0:     # current rise must cause voltage drop
            continue
        r_est = -dv / di * 1000.0
        if r_bounds[0] < r_est < r_bounds[1]:
            r_vals.append(r_est)

    if len(r_vals) < 3:
        return FitResult(
            "R0_mohm", 0.0, notes=f"Insufficient step responses ({len(r_vals)} found)"
        )

    r_arr = np.array(r_vals)
    r_med = float(np.median(r_arr))
    r_std = float(np.std(r_arr))
    return FitResult(
        "R0_mohm", round(r_med, 3), round(r_std, 3),
        r_squared=0.0, n_samples=len(r_vals),
        method="delta_vi_fast_steps",
        notes=f"{len(r_vals)} current steps | ΔI_min={min_di_a}A | dt_max={max_dt_s}s",
    )


def fit_rc_time_constants(
    log: "FlightLog",
    r0_mohm: float,
    min_di_drop_a: float = 5.0,
    recovery_window_s: float = 60.0,
    min_recovery_pts: int = 10,
) -> tuple[FitResult, FitResult, FitResult, FitResult]:
    """
    Fit 2RC time constants from voltage recovery after current steps down.

    After a large current drop (throttle-down), voltage recovers as:
        V(t) = V_inf - A * exp(-t/τ1) - B * exp(-t/τ2)

    Returns (τ1_result, τ2_result, R1_result, R2_result) — all in SI units
    except R values which are in mΩ.  Returns zero-value FitResults if
    insufficient recovery data is found.
    """
    if not HAS_SCIPY:
        return (
            FitResult("tau1_s",  0.0, notes="scipy required for RC fitting"),
            FitResult("tau2_s",  0.0, notes="scipy required for RC fitting"),
            FitResult("R1_mohm", 0.0, notes="scipy required for RC fitting"),
            FitResult("R2_mohm", 0.0, notes="scipy required for RC fitting"),
        )

    v = _to_arr(log.voltage_v)
    i = _to_arr(log.current_a)
    t = _to_arr(log.time_s)

    tau1_vals, tau2_vals, r1_vals, r2_vals = [], [], [], []

    for k in range(len(t) - 1):
        di = float(i[k] - i[k + 1])        # drop in current (positive = drop)
        if di < min_di_drop_a:
            continue
        dt_step = float(t[k + 1] - t[k])
        if dt_step > 5.0:
            continue

        # Collect recovery window
        i_new = float(i[k + 1])
        t0    = float(t[k + 1])
        mask  = (t >= t0) & (t <= t0 + recovery_window_s)
        if mask.sum() < min_recovery_pts:
            continue
        t_rec = t[mask] - t0
        v_rec = v[mask]
        i_rec = i[mask]

        # Skip if current is not stable during recovery
        if float(i_rec.max() - i_rec.min()) > min_di_drop_a * 0.5:
            continue

        # Model: V(t) = V_inf - A*exp(-t/τ1) - B*exp(-t/τ2)
        v_inf_est = float(v_rec[-1]) + i_new * r0_mohm / 1000.0

        def double_exp(t_arr, v_inf, A, tau1, B, tau2):
            return v_inf - A * np.exp(-t_arr / tau1) - B * np.exp(-t_arr / tau2)

        try:
            p0 = [v_inf_est, 0.05, 10.0, 0.02, 100.0]
            bounds = ([v_rec[0] - 0.5, 0, 0.5, 0, 10],
                      [v_rec[0] + 2.0, 2.0, 50.0, 2.0, 600.0])
            popt, _ = curve_fit(double_exp, t_rec, v_rec, p0=p0,
                                bounds=bounds, maxfev=2000)
            _, A_fit, tau1_fit, B_fit, tau2_fit = popt

            # Ensure τ1 < τ2
            if tau1_fit > tau2_fit:
                tau1_fit, tau2_fit = tau2_fit, tau1_fit
                A_fit, B_fit = B_fit, A_fit

            if 0.5 < tau1_fit < 50 and 10 < tau2_fit < 600:
                r1_est = A_fit / (i_new + 0.001) * 1000.0 if i_new > 0.1 else 0.0
                r2_est = B_fit / (i_new + 0.001) * 1000.0 if i_new > 0.1 else 0.0
                if 0.1 < r1_est < 600 and 0.1 < r2_est < 600:
                    tau1_vals.append(tau1_fit)
                    tau2_vals.append(tau2_fit)
                    r1_vals.append(r1_est)
                    r2_vals.append(r2_est)
        except Exception:
            continue

    def _make_result(name, vals, unit=""):
        if not vals:
            return FitResult(name, 0.0, notes="No valid recovery segments found")
        arr = np.array(vals)
        return FitResult(
            name, round(float(np.median(arr)), 4), round(float(np.std(arr)), 4),
            n_samples=len(vals), method="double_exp_fit",
            notes=f"{len(vals)} recovery segments fitted{unit}",
        )

    return (
        _make_result("tau1_s",  tau1_vals, " | τ1 [s]"),
        _make_result("tau2_s",  tau2_vals, " | τ2 [s]"),
        _make_result("R1_mohm", r1_vals,   " | R1 [mΩ]"),
        _make_result("R2_mohm", r2_vals,   " | R2 [mΩ]"),
    )


def build_ecm_parameters_from_log(
    log: "FlightLog",
    pack,
    chem_id: str = "LION21",
) -> "ECMParameters":
    """
    Fit ECMParameters from a flight log.

    Procedure:
      1. Fit R0 from current steps (or fall back to default if insufficient data)
      2. Fit τ1, τ2, R1, R2 from recovery curves
      3. Build a default ECMParameters table and scale R0/R1/R2 to fitted values
         while retaining the Arrhenius temperature shape and SoC variation

    Returns an ECMParameters object ready for ModelMode.PRECISE.
    """
    from batteries.voltage_model import default_ecm_params, ECMParameters, bilinear_interp

    r_pack = pack.internal_resistance_mohm

    # Step 1 — R0 from steps
    r0_fit = fit_R0_from_steps(log)
    r0_mohm = r0_fit.value if r0_fit.value > 1.0 else r_pack * 0.5

    # Step 2 — RC time constants
    tau1_r, tau2_r, r1_r, r2_r = fit_rc_time_constants(log, r0_mohm)
    r1_mohm = r1_r.value if r1_r.value > 1.0 else r_pack * 0.5
    r2_mohm = r2_r.value if r2_r.value > 0.1 else r1_mohm * 0.30
    tau1 = tau1_r.value if tau1_r.value > 0.5 else 10.0
    tau2 = tau2_r.value if tau2_r.value > 5.0 else 120.0

    # Step 3 — Build ECM using chemistry shape, scaled to fitted values at 25°C
    base = default_ecm_params(r_pack, chem_id)

    # Scale factors at 25°C, SoC=50% (reference point)
    r0_base = bilinear_interp(base.R0_table, base.soc_breakpoints, base.temp_breakpoints, 50, 25)
    r1_base = bilinear_interp(base.R1_table, base.soc_breakpoints, base.temp_breakpoints, 50, 25)
    r2_base = bilinear_interp(base.R2_table, base.soc_breakpoints, base.temp_breakpoints, 50, 25)

    scale_r0 = r0_mohm / r0_base if r0_base > 0 else 1.0
    scale_r1 = r1_mohm / r1_base if r1_base > 0 else 1.0
    scale_r2 = r2_mohm / r2_base if r2_base > 0 else 1.0

    new_R0 = [[v * scale_r0 for v in row] for row in base.R0_table]
    new_R1 = [[v * scale_r1 for v in row] for row in base.R1_table]
    new_R2 = [[v * scale_r2 for v in row] for row in base.R2_table]

    # Recompute C tables from fitted time constants × scaled R
    new_C1, new_C2 = [], []
    for si, soc in enumerate(base.soc_breakpoints):
        c1_row, c2_row = [], []
        for ti in range(len(base.temp_breakpoints)):
            r1_ohm = new_R1[si][ti] / 1000.0
            r2_ohm = new_R2[si][ti] / 1000.0
            c1_row.append(round(tau1 / r1_ohm if r1_ohm > 0 else 1.0, 3))
            c2_row.append(round(tau2 / r2_ohm if r2_ohm > 0 else 1.0, 3))
        new_C1.append(c1_row)
        new_C2.append(c2_row)

    ecm = ECMParameters(
        soc_breakpoints=base.soc_breakpoints,
        temp_breakpoints=base.temp_breakpoints,
        R0_table=[[round(v, 4) for v in row] for row in new_R0],
        R1_table=[[round(v, 4) for v in row] for row in new_R1],
        C1_table=new_C1,
        R2_table=[[round(v, 4) for v in row] for row in new_R2],
        C2_table=new_C2,
    )
    fit_summary = {
        "R0_mohm":    round(r0_mohm, 3),
        "R1_mohm":    round(r1_mohm, 3),
        "R2_mohm":    round(r2_mohm, 3),
        "tau1_s":     round(tau1, 3),
        "tau2_s":     round(tau2, 3),
        "n_steps":    r0_fit.n_samples,
        "n_recovery": tau1_r.n_samples,
    }
    diagnostics = {
        "r0_fit":  str(r0_fit),
        "tau1_fit": str(tau1_r),
        "tau2_fit": str(tau2_r),
        "r1_fit":  str(r1_r),
        "r2_fit":  str(r2_r),
    }
    return ecm, fit_summary, diagnostics
