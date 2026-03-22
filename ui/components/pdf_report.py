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
import matplotlib.patches as mpatches
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


def _phase_color(phase_type: str) -> str:
    PHASE_COLORS = {
        "IDLE": "#BDBDBD", "TAKEOFF": "#FFC107", "CLIMB": "#FF9800",
        "CRUISE": "#2196F3", "HOVER": "#9C27B0", "DESCEND": "#03A9F4",
        "LAND": "#4CAF50", "PAYLOAD_OPS": "#F44336", "EMERGENCY": "#B71C1C",
        "VTOL_HOVER": "#CE93D8", "VTOL_TRANSITION": "#FFB74D",
        "FW_CRUISE": "#1565C0", "FW_CLIMB": "#E65100", "FW_DESCEND": "#0277BD",
    }
    return PHASE_COLORS.get(phase_type.upper(), "#EEEEEE")


def _resolve_phase_power(mission, uav, equipment_db=None) -> list[float]:
    """Return per-phase power list using equipment assignments if available."""
    powers = []
    for ph in sorted(mission.phases, key=lambda p: p.phase_seq):
        if ph.power_override_w is not None:
            powers.append(ph.power_override_w)
        elif equipment_db is not None:
            asgn_map = {a.equipment_id: a for a in mission.equipment_assignments
                        if a.phase_seq == ph.phase_seq}
            total = 0.0
            for eq, qty in uav.equipment_list:
                live = equipment_db.get(eq.equip_id, eq)
                asgn = asgn_map.get(eq.equip_id)
                if asgn is not None:
                    pw = live.resolve_power(asgn.state, asgn.custom_power_w)
                else:
                    pw = live.operating_power_w
                total += pw * qty
            powers.append(total)
        else:
            powers.append(ph.effective_power_w(uav))
    return powers


def generate_pdf_report(
    results: list,
    packs: list,
    mission,
    uav_name: str,
    ambient_temp_c: float,
    uav=None,
    equipment_db: Optional[dict] = None,
    sweep_df: Optional[dict] = None,
    flight_log=None,
) -> bytes:
    """
    Build a multi-page PDF and return it as bytes.

    Pages:
        1.  Cover
        2.  UAV Configuration summary  (new)
        3.  Mission Profile summary     (new)
        4.  Battery Scorecard table
        5.  SoC & Voltage time-series
        6.  Current & Power time-series
        7.  Temperature time-series
        8.  Energy vs Weight + Final SoC bar
        9.  Temperature sweep (if provided)
    """
    buf = io.BytesIO()
    cmap = plt.get_cmap("tab10")

    with PdfPages(buf) as pdf:

        # ── Page 1: Cover ─────────────────────────────────────────────────────
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
        ax.text(0.5, 0.33, f"Ambient temperature: {ambient_temp_c} °C", fontsize=14,
                color="#B0BEC5", ha="center", va="center", transform=ax.transAxes)
        ax.text(0.5, 0.24, f"Packs analysed: {len(packs)}", fontsize=14, color="#B0BEC5",
                ha="center", va="center", transform=ax.transAxes)

        from datetime import datetime
        ax.text(0.5, 0.10, datetime.now().strftime("%Y-%m-%d %H:%M"), fontsize=10,
                color="#78909C", ha="center", va="center", transform=ax.transAxes)

        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        # ── Page 2: UAV Configuration ─────────────────────────────────────────
        if uav is not None and uav.equipment_list:
            fig = plt.figure(figsize=(11.69, 8.27))
            fig.suptitle(f"UAV Configuration — {uav_name}", fontsize=14, fontweight="bold", y=0.98)

            gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.55, wspace=0.35,
                                   left=0.06, right=0.96, top=0.90, bottom=0.06)
            ax_tbl  = fig.add_subplot(gs[0, :])   # full-width table
            ax_bar  = fig.add_subplot(gs[1, 0])   # power bar
            ax_pie  = fig.add_subplot(gs[1, 1])   # weight pie

            ax_tbl.set_axis_off()

            # Equipment table data
            eq_rows = []
            cat_power: dict[str, float] = {}
            cat_weight: dict[str, float] = {}
            for eq, qty in uav.equipment_list:
                idle_tot = eq.idle_power_w * qty
                op_tot   = eq.operating_power_w * qty
                max_tot  = eq.max_power_w * qty
                wt_tot   = eq.weight_g * qty
                eq_rows.append([
                    eq.equip_id[:24], eq.category, str(qty),
                    f"{eq.idle_power_w:.0f}", f"{eq.operating_power_w:.0f}",
                    f"{eq.max_power_w:.0f}",
                    f"{op_tot:.0f}", f"{wt_tot:.0f}",
                ])
                cat_power[eq.category]  = cat_power.get(eq.category, 0) + op_tot
                cat_weight[eq.category] = cat_weight.get(eq.category, 0) + wt_tot

            col_labels_eq = [
                "Equipment ID", "Category", "Qty",
                "Idle\nW (ea)", "Operating\nW (ea)", "Max\nW (ea)",
                "Operating\nW (total)", "Weight\ng (total)",
            ]
            tbl = ax_tbl.table(
                cellText=eq_rows, colLabels=col_labels_eq,
                cellLoc="center", loc="center",
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(7.5)
            tbl.scale(1, 1.5)
            # Header style
            for j in range(len(col_labels_eq)):
                tbl[0, j].set_facecolor("#1A237E")
                tbl[0, j].set_text_props(color="white", fontweight="bold")
            ax_tbl.set_title("Equipment List", fontsize=10, fontweight="bold", pad=6)

            # Key metrics as text below header
            total_op_w  = uav.phase_power_w()
            total_wt_g  = uav.total_weight_g()
            fig.text(0.06, 0.91,
                     f"Total operating power: {total_op_w:.0f} W  |  "
                     f"Total weight (excl. battery): {total_wt_g:.0f} g  |  "
                     f"Equipment items: {len(uav.equipment_list)}",
                     fontsize=8, color="#333333")

            # Horizontal bar: operating power per equipment
            eq_ids   = [f"{eq.equip_id[:18]} ×{qty}" for eq, qty in uav.equipment_list]
            eq_pows  = [eq.operating_power_w * qty for eq, qty in uav.equipment_list]
            bar_cols = [plt.get_cmap("Set2")(i % 8) for i in range(len(eq_ids))]
            bars_h = ax_bar.barh(range(len(eq_ids)), eq_pows, color=bar_cols, alpha=0.85)
            ax_bar.set_yticks(range(len(eq_ids)))
            ax_bar.set_yticklabels(eq_ids, fontsize=7)
            ax_bar.invert_yaxis()
            ax_bar.set_xlabel("Operating Power (W)", fontsize=8)
            ax_bar.set_title("Power by Equipment", fontsize=9, fontweight="bold")
            ax_bar.grid(axis="x", alpha=0.3)
            for bar, val in zip(bars_h, eq_pows):
                if val > 0:
                    ax_bar.text(val + 0.5, bar.get_y() + bar.get_height() / 2,
                                f"{val:.0f}W", va="center", fontsize=6)

            # Pie: weight distribution by category
            if cat_weight:
                pie_labels = list(cat_weight.keys())
                pie_vals   = list(cat_weight.values())
                pie_cols   = [plt.get_cmap("Set3")(i % 12) for i in range(len(pie_labels))]
                ax_pie.pie(pie_vals, labels=pie_labels, colors=pie_cols,
                           autopct="%1.0f%%", startangle=140,
                           textprops={"fontsize": 7})
                ax_pie.set_title("Weight by Category", fontsize=9, fontweight="bold")

            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 3: Mission Profile ────────────────────────────────────────────
        if uav is not None and mission.phases:
            phases_sorted = sorted(mission.phases, key=lambda p: p.phase_seq)
            phase_powers  = _resolve_phase_power(mission, uav, equipment_db)

            fig = plt.figure(figsize=(11.69, 8.27))
            fig.suptitle(f"Mission Profile — {mission.mission_name}", fontsize=14,
                         fontweight="bold", y=0.98)

            gs = gridspec.GridSpec(2, 2, figure=fig, hspace=0.55, wspace=0.35,
                                   left=0.06, right=0.96, top=0.90, bottom=0.06)
            ax_mtbl = fig.add_subplot(gs[0, :])  # mission phase table
            ax_pbar = fig.add_subplot(gs[1, 0])  # phase power bar
            ax_tl   = fig.add_subplot(gs[1, 1])  # timeline Gantt

            ax_mtbl.set_axis_off()

            # Phase table
            cumulative_wh = 0.0
            ph_rows = []
            for ph, pw in zip(phases_sorted, phase_powers):
                wh = pw * ph.duration_s / 3600
                cumulative_wh += wh
                ph_rows.append([
                    str(ph.phase_seq), ph.phase_name[:20], ph.phase_type,
                    f"{ph.duration_s:.0f}", f"{ph.distance_m:.0f}",
                    f"{ph.altitude_m:.0f}", f"{pw:.0f}", f"{wh:.2f}",
                    f"{cumulative_wh:.2f}",
                ])
            col_labels_ph = [
                "#", "Phase Name", "Type",
                "Duration\n(s)", "Distance\n(m)", "Alt\n(m)",
                "Power\n(W)", "Energy\n(Wh)", "Cumul.\n(Wh)",
            ]
            tbl_m = ax_mtbl.table(
                cellText=ph_rows, colLabels=col_labels_ph,
                cellLoc="center", loc="center",
            )
            tbl_m.auto_set_font_size(False)
            tbl_m.set_fontsize(7.5)
            tbl_m.scale(1, 1.5)
            # Header style
            for j in range(len(col_labels_ph)):
                tbl_m[0, j].set_facecolor("#1A237E")
                tbl_m[0, j].set_text_props(color="white", fontweight="bold")
            # Phase type row colours
            for i, ph in enumerate(phases_sorted):
                col = _phase_color(ph.phase_type)
                for j in [2]:   # colour the Type column cell
                    tbl_m[i + 1, j].set_facecolor(col)
            ax_mtbl.set_title("Mission Phases", fontsize=10, fontweight="bold", pad=6)

            # Mission key metrics
            total_dur_min = mission.total_duration_s / 60
            total_dist_m  = mission.total_distance_m
            total_e_wh    = sum(pw * ph.duration_s / 3600
                                for ph, pw in zip(phases_sorted, phase_powers))
            fig.text(0.06, 0.91,
                     f"Duration: {total_dur_min:.1f} min  |  "
                     f"Distance: {total_dist_m:.0f} m  |  "
                     f"Total energy demand: {total_e_wh:.1f} Wh  |  "
                     f"Phases: {len(phases_sorted)}",
                     fontsize=8, color="#333333")

            # Bar chart: phase power
            ph_names_short = [f"{ph.phase_seq}. {ph.phase_name[:12]}" for ph in phases_sorted]
            bar_colors     = [_phase_color(ph.phase_type) for ph in phases_sorted]
            bars_ph = ax_pbar.bar(range(len(ph_names_short)), phase_powers,
                                  color=bar_colors, edgecolor="#555", linewidth=0.5)
            ax_pbar.set_xticks(range(len(ph_names_short)))
            ax_pbar.set_xticklabels(ph_names_short, rotation=35, ha="right", fontsize=6.5)
            ax_pbar.set_ylabel("Power (W)", fontsize=8)
            ax_pbar.set_title("Per-Phase Power (Equipment Assignments)", fontsize=9,
                              fontweight="bold")
            ax_pbar.grid(axis="y", alpha=0.3)
            for bar, pw in zip(bars_ph, phase_powers):
                if pw > 0:
                    ax_pbar.text(bar.get_x() + bar.get_width() / 2,
                                 bar.get_height() + max(phase_powers) * 0.01,
                                 f"{pw:.0f}", ha="center", fontsize=6)

            # Timeline Gantt
            t_cur = 0.0
            spans = []
            for ph, pw in zip(phases_sorted, phase_powers):
                spans.append((t_cur, ph.duration_s, ph, pw))
                t_cur += ph.duration_s
            total_t = t_cur or 1.0

            for ts, dur, ph, pw in spans:
                col = _phase_color(ph.phase_type)
                ax_tl.broken_barh([(ts, dur)], (0, 1),
                                  facecolors=col, edgecolors="#555", linewidth=0.5)
                if dur / total_t > 0.04:
                    ax_tl.text(ts + dur / 2, 0.5,
                               f"{ph.phase_name[:10]}\n{int(ph.duration_s)}s",
                               ha="center", va="center", fontsize=5.5,
                               fontweight="bold", clip_on=True)

            # Phase type legend
            seen_types = {}
            for ph in phases_sorted:
                if ph.phase_type not in seen_types:
                    seen_types[ph.phase_type] = _phase_color(ph.phase_type)
            legend_patches = [mpatches.Patch(color=c, label=t)
                              for t, c in seen_types.items()]
            ax_tl.legend(handles=legend_patches, fontsize=6,
                         loc="upper right", framealpha=0.8)

            ax_tl.set_xlim(0, total_t)
            ax_tl.set_ylim(0, 1)
            ax_tl.set_yticks([])
            ax_tl.set_xlabel("Time (s)", fontsize=8)
            ax_tl.set_title("Mission Timeline", fontsize=9, fontweight="bold")
            ax_tl.grid(axis="x", alpha=0.25)

            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 4: Battery Scorecard Table ───────────────────────────────────
        if results:
            fig, ax = plt.subplots(figsize=(16, max(4, len(results) * 0.6 + 2)))
            ax.set_axis_off()

            col_labels = ["Pack ID", "Chemistry", "Config", "Energy\n(Wh)", "Weight\n(g)",
                          "Wh/kg", "Final\nSoC %", "Min V\n(V)", "Peak Sag\n(V)",
                          "Max I\n(A)", "Max T\n(°C)", "Status"]
            rows_data = []
            for r, p in zip(results, packs):
                margin = round((r.final_soc - 10) / 90 * 100, 1) if r.final_soc > 10 else 0
                status = ("PASS" if not r.depleted and margin > 10
                          else "MARGINAL" if not r.depleted else "FAIL")
                rows_data.append([
                    r.pack_id[:22], p.chemistry_id,
                    f"{p.cells_series}S{p.cells_parallel}P",
                    f"{p.pack_energy_wh:.0f}", f"{p.pack_weight_g:.0f}",
                    f"{p.specific_energy_wh_kg:.1f}", f"{r.final_soc:.1f}",
                    f"{r.min_voltage:.3f}", f"{r.peak_sag_v:.3f}",
                    f"{r.max_current:.1f}", f"{r.max_temp_c:.1f}", status,
                ])

            tbl = ax.table(cellText=rows_data, colLabels=col_labels,
                           cellLoc="center", loc="center")
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(8)
            tbl.scale(1, 1.5)
            for j in range(len(col_labels)):
                tbl[0, j].set_facecolor("#1A237E")
                tbl[0, j].set_text_props(color="white", fontweight="bold")

            status_col_idx = len(col_labels) - 1
            status_colors = {"PASS": "#E2EFDA", "MARGINAL": "#FFF2CC", "FAIL": "#FFCCCC"}
            for i, row in enumerate(rows_data):
                tbl[i + 1, status_col_idx].set_facecolor(
                    status_colors.get(row[status_col_idx], "#FFFFFF"))

            ax.set_title("Battery Scorecard", fontsize=14, fontweight="bold", pad=20)
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 5: SoC & Voltage ──────────────────────────────────────────────
        if results:
            fig, (ax_soc, ax_v) = plt.subplots(2, 1, figsize=(14, 8), sharex=False)
            for idx, (r, p) in enumerate(zip(results, packs)):
                col = cmap(idx % 10)
                t = np.array(r.time_s)
                ax_soc.plot(t, r.soc_pct, color=col, linewidth=1.5,
                            label=r.pack_id[:20], alpha=0.85)
                ax_v.plot(t, r.voltage_v, color=col, linewidth=1.5, alpha=0.85,
                          label=r.pack_id[:20])
            ax_soc.set_ylabel("SoC (%)"); ax_soc.set_title("State of Charge")
            ax_soc.axhline(10, color="red", linestyle="--", linewidth=0.8,
                           alpha=0.6, label="10% cutoff")
            ax_soc.legend(fontsize=7, ncol=3); ax_soc.grid(alpha=0.3)
            ax_v.set_xlabel("Time (s)"); ax_v.set_ylabel("Voltage (V)")
            ax_v.set_title("Terminal Voltage")
            ax_v.legend(fontsize=7, ncol=3); ax_v.grid(alpha=0.3)
            fig.suptitle("SoC & Voltage — All Packs", fontsize=13, fontweight="bold")
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 6: Current & Power ────────────────────────────────────────────
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
            ax_p.set_title("Discharge Power")
            ax_p.legend(fontsize=7, ncol=3); ax_p.grid(alpha=0.3)
            fig.suptitle("Current & Power — All Packs", fontsize=13, fontweight="bold")
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 7: Temperature ────────────────────────────────────────────────
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

        # ── Page 8: Energy vs Weight + Final SoC bar ──────────────────────────
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
            ax_sc.set_title("Energy vs Weight"); ax_sc.legend(fontsize=8)
            ax_sc.grid(alpha=0.3)

            ids   = [r.pack_id[:18] for r in results]
            socs  = [r.final_soc for r in results]
            colors_bar = [("#4CAF50" if s > 20 else "#FF9800" if s > 10 else "#F44336")
                          for s in socs]
            bars = ax_bar.bar(range(len(ids)), socs, color=colors_bar,
                              edgecolor="#666", linewidth=0.5)
            ax_bar.set_xticks(range(len(ids)))
            ax_bar.set_xticklabels(ids, rotation=40, ha="right", fontsize=7)
            ax_bar.axhline(10, color="red", linewidth=1.2, linestyle="--", label="10% cutoff")
            ax_bar.axhline(20, color="orange", linewidth=1, linestyle=":", label="20% margin")
            ax_bar.set_ylabel("Final SoC (%)"); ax_bar.set_title("Final SoC — All Packs")
            ax_bar.legend(fontsize=8); ax_bar.grid(axis="y", alpha=0.3)
            for bar, val in zip(bars, socs):
                ax_bar.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                            f"{val:.1f}%", ha="center", fontsize=6)
            fig.suptitle("Pack Comparison", fontsize=13, fontweight="bold")
            fig.tight_layout()
            pdf.savefig(fig, bbox_inches="tight")
            plt.close(fig)

        # ── Page 9: Temperature Sweep ──────────────────────────────────────────
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
