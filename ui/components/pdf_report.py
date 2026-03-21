"""
ui/components/pdf_report.py
Generate a multi-page PDF report using matplotlib PdfPages.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import io

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np
import pandas as pd


def _chem_color(chem_id: str) -> str:
    COLORS = {
        "LiPo": "#2196F3", "Li-Ion": "#4CAF50", "LiFePO4": "#FF9800",
        "LiHV": "#9C27B0", "NiMH": "#F44336", "SolidState": "#00BCD4",
    }
    for k, v in COLORS.items():
        if k.lower() in chem_id.lower():
            return v
    return "#607D8B"


def generate_pdf_report(
    results: list,
    packs: list,
    mission,
    uav_name: str,
    ambient_temp_c: float,
    sweep_df: Optional[dict] = None,
    flight_log=None,
) -> bytes:
    """
    Build a multi-page PDF and return it as bytes.

    Pages:
        1. Cover / Summary
        2. Battery Scorecard table
        3. SoC & Voltage time-series (all packs)
        4. Current & Power time-series (all packs)
        5. Temperature time-series (all packs)
        6. Energy vs Weight scatter + Specific energy bar
        7. Temperature sweep (if sweep_df provided)
    """
    buf = io.BytesIO()

    with PdfPages(buf) as pdf:
        # ── Page 1: Cover ────────────────────────────────────────────────────
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.patch.set_facecolor("#1A237E")
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()

        ax.text(0.5, 0.72, "BattSim", fontsize=56, color="white",
                ha="center", va="center", fontweight="bold", transform=ax.transAxes)
        ax.text(0.5, 0.60, "UAV Battery Analysis Report", fontsize=26, color="#90CAF9",
                ha="center", va="center", transform=ax.transAxes)
        ax.text(0.5, 0.47, f"Mission: {mission.mission_name}", fontsize=18, color="white",
                ha="center", va="center", transform=ax.transAxes)
        ax.text(0.5, 0.40, f"UAV: {uav_name}", fontsize=16, color="#B0BEC5",
                ha="center", va="center", transform=ax.transAxes)
        ax.text(0.5, 0.33, f"Ambient temperature: {ambient_temp_c} °C", fontsize=14, color="#B0BEC5",
                ha="center", va="center", transform=ax.transAxes)
        ax.text(0.5, 0.24, f"Packs analysed: {len(packs)}", fontsize=14, color="#B0BEC5",
                ha="center", va="center", transform=ax.transAxes)

        from datetime import datetime
        ax.text(0.5, 0.10, datetime.now().strftime("%Y-%m-%d %H:%M"), fontsize=10,
                color="#78909C", ha="center", va="center", transform=ax.transAxes)

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # ── Page 2: Scorecard Table ───────────────────────────────────────────
        if results:
            fig, ax = plt.subplots(figsize=(16, max(4, len(results) * 0.6 + 2)))
            ax.set_axis_off()

            rows_data = []
            col_labels = ["Pack ID", "Chemistry", "Config", "Energy\n(Wh)", "Weight\n(g)",
                          "Wh/kg", "Final\nSoC %", "Min V\n(V)", "Peak Sag\n(V)",
                          "Max I\n(A)", "Max T\n(°C)", "Status"]
            for r, p in zip(results, packs):
                margin = round((r.final_soc - 10) / 90 * 100, 1) if r.final_soc > 10 else 0
                status = "PASS" if not r.depleted and margin > 10 else ("MARGINAL" if not r.depleted else "FAIL")
                rows_data.append([
                    r.pack_id[:22], p.chemistry_id,
                    f"{p.cells_series}S{p.cells_parallel}P",
                    f"{p.pack_energy_wh:.0f}", f"{p.pack_weight_g:.0f}",
                    f"{p.specific_energy_wh_kg:.1f}", f"{r.final_soc:.1f}",
                    f"{r.min_voltage:.3f}", f"{r.peak_sag_v:.3f}",
                    f"{r.max_current:.1f}", f"{r.max_temp_c:.1f}", status,
                ])

            tbl = ax.table(
                cellText=rows_data,
                colLabels=col_labels,
                cellLoc="center",
                loc="center",
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            tbl.scale(1, 1.5)

            # Colour status cells
            status_col_idx = len(col_labels) - 1
            status_colors = {"PASS": "#E2EFDA", "MARGINAL": "#FFF2CC", "FAIL": "#FFCCCC"}
            for i, row in enumerate(rows_data):
                status = row[status_col_idx]
                cell = tbl[i + 1, status_col_idx]
                cell.set_facecolor(status_colors.get(status, "#FFFFFF"))

            ax.set_title("Battery Scorecard", fontsize=14, fontweight="bold", pad=20)
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 3: SoC & Voltage ─────────────────────────────────────────────
        if results:
            fig, (ax_soc, ax_v) = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
            cmap = plt.get_cmap("tab10")
            for idx, (r, p) in enumerate(zip(results, packs)):
                col = cmap(idx % 10)
                t = np.array(r.time_s)
                ax_soc.plot(t, r.soc_pct, color=col, linewidth=1.5,
                            label=r.pack_id[:20], alpha=0.85)
                ax_v.plot(t, r.voltage_v, color=col, linewidth=1.5, alpha=0.85,
                          label=r.pack_id[:20])
            ax_soc.set_ylabel("SoC (%)"); ax_soc.set_title("State of Charge")
            ax_soc.axhline(10, color="red", linestyle="--", linewidth=0.8, alpha=0.6, label="10% cutoff")
            ax_soc.legend(fontsize=7, ncol=3); ax_soc.grid(alpha=0.3)
            ax_v.set_xlabel("Time (s)"); ax_v.set_ylabel("Voltage (V)")
            ax_v.set_title("Terminal Voltage"); ax_v.legend(fontsize=7, ncol=3); ax_v.grid(alpha=0.3)
            fig.suptitle("SoC & Voltage — All Packs", fontsize=13, fontweight="bold")
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 4: Current & Power ───────────────────────────────────────────
        if results:
            fig, (ax_i, ax_p) = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
            for idx, (r, p) in enumerate(zip(results, packs)):
                col = cmap(idx % 10)
                t = np.array(r.time_s)
                ax_i.plot(t, r.current_a, color=col, linewidth=1.2,
                          label=r.pack_id[:20], alpha=0.85)
                ax_p.plot(t, r.power_w, color=col, linewidth=1.2, alpha=0.85,
                          label=r.pack_id[:20])
            ax_i.set_ylabel("Current (A)"); ax_i.set_title("Discharge Current")
            ax_i.legend(fontsize=7, ncol=3); ax_i.grid(alpha=0.3)
            ax_p.set_xlabel("Time (s)"); ax_p.set_ylabel("Power (W)")
            ax_p.set_title("Discharge Power"); ax_p.legend(fontsize=7, ncol=3); ax_p.grid(alpha=0.3)
            fig.suptitle("Current & Power — All Packs", fontsize=13, fontweight="bold")
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 5: Temperature ───────────────────────────────────────────────
        if results:
            fig, ax_t = plt.subplots(figsize=(14, 5))
            for idx, (r, p) in enumerate(zip(results, packs)):
                col = cmap(idx % 10)
                t = np.array(r.time_s)
                ax_t.plot(t, r.temp_c, color=col, linewidth=1.5,
                          label=r.pack_id[:20], alpha=0.85)
            ax_t.set_xlabel("Time (s)"); ax_t.set_ylabel("Cell Temperature (°C)")
            ax_t.set_title("Cell Temperature — All Packs", fontsize=13, fontweight="bold")
            ax_t.legend(fontsize=7, ncol=3); ax_t.grid(alpha=0.3)
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 6: Energy vs Weight scatter ─────────────────────────────────
        if packs:
            fig, (ax_sc, ax_bar) = plt.subplots(1, 2, figsize=(14, 6))
            chems_seen = set()
            for r, p in zip(results, packs):
                c = _chem_color(p.chemistry_id)
                label = p.chemistry_id if p.chemistry_id not in chems_seen else ""
                chems_seen.add(p.chemistry_id)
                ax_sc.scatter(p.pack_weight_g, p.pack_energy_wh, color=c, s=60,
                              alpha=0.8, label=label, edgecolors="white", linewidths=0.5)
                ax_sc.annotate(r.pack_id[:14], (p.pack_weight_g, p.pack_energy_wh),
                               fontsize=5.5, alpha=0.7)
            ax_sc.set_xlabel("Weight (g)"); ax_sc.set_ylabel("Energy (Wh)")
            ax_sc.set_title("Energy vs Weight"); ax_sc.legend(fontsize=8); ax_sc.grid(alpha=0.3)

            # Bar chart: final SoC
            ids = [r.pack_id[:18] for r in results]
            socs = [r.final_soc for r in results]
            colors = [("#4CAF50" if s > 20 else "#FF9800" if s > 10 else "#F44336") for s in socs]
            bars = ax_bar.bar(range(len(ids)), socs, color=colors, edgecolor="#666", linewidth=0.5)
            ax_bar.set_xticks(range(len(ids)))
            ax_bar.set_xticklabels(ids, rotation=40, ha="right", fontsize=7)
            ax_bar.axhline(10, color="red", linewidth=1.2, linestyle="--", label="10% cutoff")
            ax_bar.axhline(20, color="orange", linewidth=1, linestyle=":", label="20% margin")
            ax_bar.set_ylabel("Final SoC (%)"); ax_bar.set_title("Final SoC — All Packs")
            ax_bar.legend(fontsize=8); ax_bar.grid(axis="y", alpha=0.3)
            for bar, val in zip(bars, socs):
                ax_bar.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                            f"{val:.1f}%", ha="center", fontsize=6)
            fig.suptitle("Pack Comparison", fontsize=13, fontweight="bold")
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 7: Temperature Sweep ─────────────────────────────────────────
        if sweep_df:
            fig, (ax_sw_soc, ax_sw_v) = plt.subplots(1, 2, figsize=(14, 6))
            cmap_sw = plt.get_cmap("tab10")
            for idx, (pid, df) in enumerate(sweep_df.items()):
                col = cmap_sw(idx % 10)
                t_arr = df["Ambient (C)"].values
                ax_sw_soc.plot(t_arr, df["Final SoC (%)"].values, color=col,
                               linewidth=2, marker="o", markersize=4, label=pid[:20])
                ax_sw_v.plot(t_arr, df["Min V (V)"].values, color=col,
                             linewidth=2, marker="s", markersize=4, label=pid[:20])
            ax_sw_soc.axhline(10, color="red", linestyle="--", linewidth=0.8, label="10% cutoff")
            ax_sw_soc.set_xlabel("Ambient Temp (°C)"); ax_sw_soc.set_ylabel("Final SoC (%)")
            ax_sw_soc.set_title("Final SoC vs Temperature")
            ax_sw_soc.legend(fontsize=7); ax_sw_soc.grid(alpha=0.3)
            ax_sw_v.set_xlabel("Ambient Temp (°C)"); ax_sw_v.set_ylabel("Min Voltage (V)")
            ax_sw_v.set_title("Min Voltage vs Temperature")
            ax_sw_v.legend(fontsize=7); ax_sw_v.grid(alpha=0.3)
            fig.suptitle("Temperature Sensitivity Sweep", fontsize=13, fontweight="bold")
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

    buf.seek(0)
    return buf.read()
