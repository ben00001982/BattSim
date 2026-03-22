"""
batteries/model_validator.py

Validates simulation voltage models against flight log data.

Usage:
    from batteries.model_validator import validate_against_log, compare_models, plot_validation
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ValidationResult:
    """Metrics and time-series from comparing one model mode against a log."""
    pack_id:     str = ""
    model_mode:  str = "FAST"
    rmse_v:      float = 0.0      # root mean square error [V]
    mae_v:       float = 0.0      # mean absolute error   [V]
    r_squared:   float = 0.0      # coefficient of determination
    bias_v:      float = 0.0      # mean signed error (sim − log) [V]
    n_points:    int   = 0

    time_s:         list[float] = field(default_factory=list)   # simulation time axis
    v_simulated:    list[float] = field(default_factory=list)   # simulated terminal V
    v_measured:     list[float] = field(default_factory=list)   # log V interpolated to sim axis

    notes: str = ""

    def summary(self) -> str:
        return (f"[{self.model_mode:8s}] RMSE={self.rmse_v:.4f} V  "
                f"MAE={self.mae_v:.4f} V  R²={self.r_squared:.4f}  "
                f"bias={self.bias_v:+.4f} V  n={self.n_points}")


def validate_against_log(
    pack,
    log,
    mission,
    uav,
    discharge_pts,
    mode,
    ecm_params=None,
    dt_s: float = 1.0,
    peukert_k: float = 1.05,
    cutoff_soc_pct: float = 10.0,
    dod_limit_pct: float = 80.0,
    initial_soc_pct: float = 100.0,
    ambient_temp_c: float = 25.0,
) -> ValidationResult:
    """
    Run simulation with the given ModelMode and compare against a FlightLog.

    Interpolates log voltage onto the simulation time axis for comparison.
    """
    from mission.simulator import run_simulation

    result = run_simulation(
        pack=pack, mission=mission, uav=uav,
        discharge_pts=discharge_pts,
        initial_soc_pct=initial_soc_pct,
        ambient_temp_c=ambient_temp_c,
        dt_s=dt_s,
        peukert_k=peukert_k,
        cutoff_soc_pct=cutoff_soc_pct,
        dod_limit_pct=dod_limit_pct,
        mode=mode,
        ecm_params=ecm_params,
    )

    t_sim = np.array(result.time_s)
    v_sim = np.array(result.voltage_v)
    t_log = np.array(log.time_s)
    v_log = np.array(log.voltage_v)

    if len(t_log) < 5 or len(v_log) < 5:
        vr = ValidationResult(pack_id=pack.battery_id, model_mode=mode.name,
                              notes="Log too short for comparison")
        return vr

    # Interpolate log voltage onto simulation time axis
    v_log_interp = np.interp(t_sim, t_log, v_log,
                              left=float(v_log[0]), right=float(v_log[-1]))

    residual = v_sim - v_log_interp
    rmse = float(np.sqrt(np.mean(residual ** 2)))
    mae  = float(np.mean(np.abs(residual)))
    bias = float(np.mean(residual))

    ss_res = float(np.sum(residual ** 2))
    ss_tot = float(np.sum((v_log_interp - v_log_interp.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    return ValidationResult(
        pack_id=pack.battery_id,
        model_mode=mode.name,
        rmse_v=round(rmse, 5),
        mae_v=round(mae, 5),
        r_squared=round(r2, 5),
        bias_v=round(bias, 5),
        n_points=int(len(t_sim)),
        time_s=result.time_s,
        v_simulated=result.voltage_v,
        v_measured=v_log_interp.tolist(),
    )


def compare_models(
    pack,
    log,
    mission,
    uav,
    discharge_pts,
    ecm_params=None,
    **kwargs,
) -> dict:
    """
    Run validate_against_log for FAST, STANDARD, and PRECISE modes.
    Returns dict keyed by mode name.
    """
    from batteries.voltage_model import ModelMode
    results = {}
    for mode in [ModelMode.FAST, ModelMode.STANDARD]:
        results[mode.name] = validate_against_log(
            pack, log, mission, uav, discharge_pts, mode=mode, **kwargs
        )
    if ecm_params is not None:
        results["PRECISE"] = validate_against_log(
            pack, log, mission, uav, discharge_pts,
            mode=ModelMode.PRECISE, ecm_params=ecm_params, **kwargs
        )
    return results


def plot_validation(
    results: dict,
    title: str = "Model Validation",
):
    """
    Create a matplotlib figure comparing model modes against log data.
    Returns the figure (caller must call plt.close(fig) when done).
    """
    import matplotlib.pyplot as plt
    MODE_COLORS = {
        "FAST":     "#2196F3",
        "STANDARD": "#FF9800",
        "PRECISE":  "#4CAF50",
    }

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    ax_v, ax_res = axes

    first = True
    for mode_name, vr in results.items():
        if not vr.time_s:
            continue
        col = MODE_COLORS.get(mode_name, "#9E9E9E")
        t = vr.time_s
        ax_v.plot(t, vr.v_simulated, color=col, linewidth=1.8,
                  label=f"{mode_name} (RMSE={vr.rmse_v:.4f} V)", alpha=0.9)
        residual = np.array(vr.v_simulated) - np.array(vr.v_measured)
        ax_res.plot(t, residual, color=col, linewidth=1.2, alpha=0.8)
        if first:
            ax_v.plot(t, vr.v_measured, color="#E53935", linewidth=1.5,
                      linestyle="--", label="Measured (log)", alpha=0.85)
            first = False

    ax_v.set_ylabel("Voltage (V)")
    ax_v.set_title(title)
    ax_v.legend(fontsize=8, loc="best")
    ax_v.grid(alpha=0.3)

    ax_res.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax_res.set_xlabel("Time (s)")
    ax_res.set_ylabel("Residual V_sim − V_log (V)")
    ax_res.set_title("Residual by Model Mode")
    ax_res.grid(alpha=0.3)

    fig.tight_layout()
    return fig
