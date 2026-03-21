"""
ui/components/db_helpers.py
Cached database loader, DataFrame converters, and shared chart helpers.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Optional

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import streamlit as st

from ui.config import DB_PATH, CFG_PATH, CHEM_COLORS, PHASE_COLORS, ACCENT


# ── Database loader ───────────────────────────────────────────────────────────

@st.cache_resource
def load_db():
    """Load BatteryDatabase once and cache for the session."""
    from batteries.database import BatteryDatabase
    return BatteryDatabase(DB_PATH).load()


def reload_db():
    """Force-reload the database (clears cache)."""
    load_db.clear()
    return load_db()


# ── Config helpers ────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Load analysis_config.json; return empty dict if missing."""
    if CFG_PATH.exists():
        with open(CFG_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(cfg: dict):
    """Save analysis_config.json to project root."""
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ── DataFrame builders ────────────────────────────────────────────────────────

def packs_to_df(packs) -> pd.DataFrame:
    """Convert a list/dict of BatteryPack objects to a display DataFrame."""
    if isinstance(packs, dict):
        packs = list(packs.values())
    rows = []
    for p in packs:
        rows.append({
            "ID":            p.battery_id,
            "Name":          p.name,
            "Chemistry":     p.chemistry_id,
            "Config":        f"{p.cells_series}S{p.cells_parallel}P",
            "Voltage (V)":   round(p.pack_voltage_nom, 1),
            "Capacity (Ah)": round(p.pack_capacity_ah, 2),
            "Energy (Wh)":   round(p.pack_energy_wh, 1),
            "Weight (g)":    round(p.pack_weight_g, 1),
            "Wh/kg":         round(p.specific_energy_wh_kg, 1),
            "Max I (A)":     round(p.max_cont_discharge_a, 1),
            "Max W (W)":     round(p.max_cont_discharge_w, 0),
            "C-rate":        round(p.cont_c_rate, 2),
            "IR (mΩ)":       round(p.internal_resistance_mohm, 2),
            "Cycles":        p.cycle_life,
            "UAV Class":     p.uav_class,
            "Notes":         p.notes,
        })
    return pd.DataFrame(rows)


def cells_to_df(cells) -> pd.DataFrame:
    if isinstance(cells, dict):
        cells = list(cells.values())
    rows = []
    for c in cells:
        rows.append({
            "ID":            c.cell_id,
            "Manufacturer":  c.manufacturer,
            "Model":         c.model,
            "Chemistry":     c.chemistry_id,
            "Format":        c.cell_format,
            "Voltage (V)":   c.voltage_nominal,
            "Capacity (Ah)": c.capacity_ah,
            "Energy (Wh)":   c.energy_wh,
            "Weight (g)":    c.weight_g,
            "Wh/kg":         c.specific_energy_wh_kg,
            "Max I (A)":     c.max_cont_discharge_a,
            "IR (mΩ)":       c.internal_resistance_mohm,
            "Cycles":        c.cycle_life,
        })
    return pd.DataFrame(rows)


def sim_results_to_df(results: list, packs: list) -> pd.DataFrame:
    """Build scorecard DataFrame from simulation results."""
    rows = []
    for r, p in zip(results, packs):
        margin = (r.final_soc - 10) / 90 * 100 if r.final_soc > 10 else 0
        status = ("PASS" if not r.depleted and margin > 10 else
                  "MARGINAL" if not r.depleted else "FAIL")
        rows.append({
            "Pack ID":       r.pack_id,
            "Chemistry":     p.chemistry_id,
            "Config":        f"{p.cells_series}S{p.cells_parallel}P",
            "Energy (Wh)":   round(p.pack_energy_wh, 1),
            "Weight (g)":    round(p.pack_weight_g, 1),
            "Wh/kg":         round(p.specific_energy_wh_kg, 1),
            "Used (Wh)":     round(r.total_energy_consumed_wh, 1),
            "Final SoC (%)": round(r.final_soc, 1),
            "Min V (V)":     round(r.min_voltage, 3),
            "Peak Sag (V)":  round(r.peak_sag_v, 3),
            "Max I (A)":     round(r.max_current, 1),
            "Max T (°C)":    round(r.max_temp_c, 1),
            "Margin (%)":    round(margin, 1),
            "Status":        status,
            "Depleted":      r.depleted,
        })
    return pd.DataFrame(rows)


# ── Chart helpers ─────────────────────────────────────────────────────────────

def chem_color(chem_id: str) -> str:
    return CHEM_COLORS.get(chem_id.upper(), "#9E9E9E")


def phase_color(phase_type: str) -> str:
    return PHASE_COLORS.get(phase_type.upper(), "#EEEEEE")


def plot_energy_vs_weight(packs, title="Energy vs Weight") -> plt.Figure:
    """Scatter plot: pack energy (Wh) vs weight (g), coloured by chemistry."""
    fig, ax = plt.subplots(figsize=(8, 5))
    groups: dict[str, list] = {}
    for p in (packs.values() if isinstance(packs, dict) else packs):
        groups.setdefault(p.chemistry_id, []).append(p)

    legend_patches = []
    for chem, grp in sorted(groups.items()):
        col = chem_color(chem)
        xs = [p.pack_weight_g for p in grp]
        ys = [p.pack_energy_wh for p in grp]
        ax.scatter(xs, ys, c=col, s=60, alpha=0.8, label=chem, zorder=4)
        legend_patches.append(mpatches.Patch(color=col, label=chem))

    ax.set_xlabel("Weight (g)")
    ax.set_ylabel("Energy (Wh)")
    ax.set_title(title)
    ax.legend(handles=legend_patches, fontsize=8, loc="upper left")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def plot_specific_energy_bar(packs, max_n: int = 30, title="Specific Energy (Wh/kg)") -> plt.Figure:
    """Horizontal bar chart of specific energy for top N packs."""
    pl = list(packs.values() if isinstance(packs, dict) else packs)
    pl = sorted(pl, key=lambda p: p.specific_energy_wh_kg, reverse=True)[:max_n]

    fig, ax = plt.subplots(figsize=(8, max(4, len(pl) * 0.35)))
    labels = [p.battery_id[:28] for p in pl]
    values = [p.specific_energy_wh_kg for p in pl]
    colors = [chem_color(p.chemistry_id) for p in pl]

    bars = ax.barh(range(len(labels)), values, color=colors, alpha=0.85)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=7)
    ax.set_xlabel("Specific Energy (Wh/kg)")
    ax.set_title(title)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.3)

    for bar, val in zip(bars, values):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height() / 2,
                f"{val:.0f}", va="center", fontsize=6)
    fig.tight_layout()
    return fig


def plot_sim_timeseries(results: list, packs: list) -> plt.Figure:
    """Multi-pack SoC, voltage, current, and temperature overlay charts."""
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    cmap = plt.get_cmap("tab10")

    ax_soc, ax_v, ax_i, ax_t = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

    for idx, (r, p) in enumerate(zip(results, packs)):
        col = cmap(idx % 10)
        lbl = p.battery_id[:22]
        t = np.array(r.time_s)
        ax_soc.plot(t, r.soc_pct,   color=col, linewidth=1.5, label=lbl)
        ax_v.plot(  t, r.voltage_v, color=col, linewidth=1.5, label=lbl)
        ax_i.plot(  t, r.current_a, color=col, linewidth=1.2, label=lbl, alpha=0.8)
        ax_t.plot(  t, r.temp_c,    color=col, linewidth=1.2, label=lbl, alpha=0.8)

    for ax, ylabel, title in [
        (ax_soc, "SoC (%)",     "State of Charge"),
        (ax_v,   "Voltage (V)", "Terminal Voltage"),
        (ax_i,   "Current (A)", "Discharge Current"),
        (ax_t,   "Temp (°C)",   "Cell Temperature"),
    ]:
        ax.set_xlabel("Time (s)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(alpha=0.3)
        if len(results) <= 8:
            ax.legend(fontsize=7, loc="best")

    fig.tight_layout()
    return fig


def plot_phase_power(mission, uav) -> plt.Figure:
    """Bar chart of power per mission phase."""
    fig, ax = plt.subplots(figsize=(9, 4))
    phases = mission.phases
    names  = [f"{p.phase_seq}. {p.phase_name}" for p in phases]
    powers = [p.effective_power_w(uav) for p in phases]
    colors = [phase_color(p.phase_type) for p in phases]

    bars = ax.bar(range(len(names)), powers, color=colors, edgecolor="#666", linewidth=0.5)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Power (W)")
    ax.set_title(f"Mission Phase Power — {mission.mission_name}")
    ax.grid(axis="y", alpha=0.3)

    for bar, pw in zip(bars, powers):
        if pw > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                    f"{pw:.0f}W", ha="center", fontsize=7)
    fig.tight_layout()
    return fig


def plot_temp_sweep(all_df_sweep: dict) -> plt.Figure:
    """Temperature sweep: Final SoC vs ambient temp for multiple packs."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    cmap = plt.get_cmap("tab10")

    for idx, (pid, df) in enumerate(all_df_sweep.items()):
        col = cmap(idx % 10)
        lbl = pid[:22]
        t   = df["Ambient (C)"].values
        axes[0].plot(t, df["Final SoC (%)"].values,  color=col, linewidth=2,  label=lbl, marker="o", markersize=4)
        axes[1].plot(t, df["Min V (V)"].values,       color=col, linewidth=2,  label=lbl, marker="o", markersize=4)

    for ax, ylabel, title in [
        (axes[0], "Final SoC (%)", "SoC vs Ambient Temperature"),
        (axes[1], "Min V (V)",     "Min Voltage vs Temperature"),
    ]:
        ax.set_xlabel("Ambient Temperature (°C)")
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=7, loc="best")

    fig.tight_layout()
    return fig
